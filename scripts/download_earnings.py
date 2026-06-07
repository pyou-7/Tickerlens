"""
Download and organize quarterly earnings materials for any US public company.

For each of the last N reported quarters this script downloads:
  - Earnings Release: SEC 8-K exhibit 99 (the press release)
  - SEC Filing: 10-Q or 10-K (annual)

Both are rendered to PDF via Chrome headless from the EDGAR HTML source.

Output structure:
  {TICKER}/
  ├── {FY}/
  │   ├── Earnings_Releases/  TICKER_Qx_FYyyyy_Earnings_Release.pdf
  │   └── SEC_Filings/        TICKER_Qx_FYyyyy_10-Q.pdf  (or 10-K)
  └── ...

Usage:
    uv run python scripts/download_earnings.py AVGO
    uv run python scripts/download_earnings.py CRWD --periods 4
    uv run python scripts/download_earnings.py AAPL --periods 8 --out ~/Research
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

from tickerlens.config import get_settings
from tickerlens.data.edgar import EdgarClient, normalize_cik
from tickerlens.services.ir_download import (
    EarningsPeriod,
    discover_earnings_filings,
    er_doc_url,
    sec_doc_url,
)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


# ── download + convert pipeline ───────────────────────────────────────────────

def fetch_html(url: str, edgar_client: EdgarClient, last_req: list[float]) -> bytes | None:
    """Download an EDGAR HTML document using the authenticated client."""
    elapsed = time.monotonic() - last_req[0]
    if elapsed < 0.15:
        time.sleep(0.15 - elapsed)
    last_req[0] = time.monotonic()

    print(f"    [DL  ] {url.split('/')[-1]}")
    try:
        # Use a raw httpx client with the same User-Agent — EdgarClient throttles
        # the data.sec.gov endpoints; archive.sec.gov is a different host.
        r = httpx.get(
            url,
            headers={"User-Agent": edgar_client.user_agent, "Accept-Encoding": "gzip, deflate"},
            follow_redirects=True,
            timeout=60.0,
        )
        r.raise_for_status()
        if b"Undeclared Automated Tool" in r.content[:2000]:
            print("    [ERR ] SEC rate-limited this IP — wait and retry")
            return None
        print(f"    [OK  ] {len(r.content) // 1024} KB")
        return r.content
    except Exception as e:
        print(f"    [ERR ] {e}")
        return None


def html_to_pdf(html: bytes, dest: Path, timeout_sec: int = 120) -> bool:
    """Write HTML to a temp file and render to PDF with Chrome headless."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not Path(CHROME).exists():
        print(f"    [ERR ] Chrome not found at {CHROME}")
        return False

    with tempfile.NamedTemporaryFile(suffix=".htm", delete=False) as tmp:
        tmp.write(html)
        tmp_path = tmp.name

    print(f"    [PDF ] → {dest.name}")
    try:
        subprocess.run(
            [
                CHROME,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                f"--print-to-pdf={dest}",
                "--print-to-pdf-no-header",
                f"file://{tmp_path}",
            ],
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
        if dest.exists() and dest.stat().st_size > 10_000:
            try:
                info = subprocess.run(
                    ["pdfinfo", str(dest)], capture_output=True, text=True, timeout=5
                )
                pages_line = next(
                    (l for l in info.stdout.splitlines() if "Pages:" in l), ""
                )
                pages = pages_line.split()[-1] if pages_line else "?"
            except Exception:
                pages = "?"
            print(f"    [OK  ] {dest.stat().st_size // 1024} KB, {pages} pages")
            return True
        print("    [ERR ] Chrome produced no output")
        return False
    except subprocess.TimeoutExpired:
        print(f"    [ERR ] Chrome timed out after {timeout_sec}s")
        return False
    except Exception as e:
        print(f"    [ERR ] {e}")
        return False
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def download_period(
    ticker: str,
    cik: str,
    period: EarningsPeriod,
    out_root: Path,
    edgar_client: EdgarClient,
    last_req: list[float],
) -> dict:
    """Download earnings release + SEC filing for one quarter. Returns a status dict."""
    slug = period.quarter_label.replace(" ", "_")
    fy_dir = out_root / period.fiscal_year
    er_dir = fy_dir / "Earnings_Releases"
    sec_dir = fy_dir / "SEC_Filings"

    result = {"quarter": period.quarter_label, "er": None, "sec": None}

    # ── Earnings Release ─────────────────────────────────────────────────────
    print(f"\n  Earnings Release ({period.er_accession or 'not found'}):")
    er_url = er_doc_url(cik, period)
    er_dest = er_dir / f"{ticker}_{slug}_Earnings_Release.pdf"

    if er_dest.exists() and er_dest.stat().st_size > 10_000:
        _print_skip(er_dest)
        result["er"] = str(er_dest)
    elif er_url:
        html = fetch_html(er_url, edgar_client, last_req)
        if html and html_to_pdf(html, er_dest, timeout_sec=90):
            result["er"] = str(er_dest)
    else:
        print("    [SKIP] No earnings release found for this quarter")

    # ── 10-Q / 10-K ──────────────────────────────────────────────────────────
    print(f"\n  {period.sec_form} ({period.sec_accession}):")
    sec_url = sec_doc_url(cik, period)
    sec_dest = sec_dir / f"{ticker}_{slug}_{period.sec_form}.pdf"
    timeout = 240 if period.sec_form == "10-K" else 150

    if sec_dest.exists() and sec_dest.stat().st_size > 10_000:
        _print_skip(sec_dest)
        result["sec"] = str(sec_dest)
    else:
        html = fetch_html(sec_url, edgar_client, last_req)
        if html and html_to_pdf(html, sec_dest, timeout_sec=timeout):
            result["sec"] = str(sec_dest)

    return result


def _print_skip(path: Path) -> None:
    try:
        info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=5)
        pages_line = next((l for l in info.stdout.splitlines() if "Pages:" in l), "")
        pages = pages_line.split()[-1] if pages_line else "?"
    except Exception:
        pages = "?"
    print(f"    [skip] {path.name}  ({path.stat().st_size // 1024} KB, {pages} pages)")


# ── main ─────────────────────────────────────────────────────────────────────

def run(ticker: str, periods: int, out_root: Path) -> None:
    ticker = ticker.upper()
    settings = get_settings()
    edgar_client = EdgarClient()
    last_req: list[float] = [0.0]

    # Always nest under output/{TICKER}/ — create if needed, add-only if exists
    company_dir = out_root / ticker
    company_dir.mkdir(parents=True, exist_ok=True)
    action = "Adding to existing" if any(company_dir.iterdir()) else "Creating"

    print(f"\n{'='*55}")
    print(f"  {ticker} — last {periods} quarters")
    print(f"  {action}: {company_dir.resolve()}")
    print(f"{'='*55}\n")

    print("Discovering filings from EDGAR...")
    quarters = discover_earnings_filings(ticker, edgar_client, n_quarters=periods)
    cik = normalize_cik(edgar_client.cik_for_ticker(ticker))

    print(f"Found {len(quarters)} quarters:\n")
    for q in quarters:
        er_status = f"ER: {q.er_doc or 'not found':35s}"
        print(f"  {q.quarter_label:12s}  {q.period_end}  {q.sec_form}  {er_status}")

    results = []
    for q in quarters:
        print(f"\n{'─'*55}")
        print(f"  {q.quarter_label}  (period end {q.period_end})")
        print(f"{'─'*55}")
        r = download_period(ticker, cik, q, company_dir, edgar_client, last_req)
        results.append(r)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n\n{'='*55}")
    print(f"  Done — {ticker}")
    print(f"{'='*55}")
    for r in results:
        er_name = Path(r["er"]).name if r["er"] else "MISSING"
        sec_name = Path(r["sec"]).name if r["sec"] else "MISSING"
        print(f"  {r['quarter']:12s}  ER: {er_name}")
        print(f"               SEC: {sec_name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download quarterly earnings materials for a US public company"
    )
    parser.add_argument("ticker", type=str.upper, help="Stock ticker (e.g. AVGO, CRWD)")
    parser.add_argument("--periods", type=int, default=4, help="Number of quarters (default: 4)")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("output"),
        help="Root output directory (default: output/). Company folder is created inside.",
    )
    args = parser.parse_args()
    run(args.ticker, args.periods, args.out)


if __name__ == "__main__":
    main()
