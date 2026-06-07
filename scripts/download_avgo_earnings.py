"""
Download AVGO earnings materials for the last 4 reported quarters and organize
them with the same structure as the CRDO folder.

Strategy:
  - Download HTML from SEC EDGAR using our authenticated client (proper User-Agent).
  - Convert the local HTML file to PDF with Chrome headless (no SEC bot detection).
  - Covers: Earnings Releases (8-K ex99) and 10-Q/10-K filings.
  - Note: Broadcom does NOT publish separate investor slide decks for quarterly
    earnings (unlike CRDO). No presentations to download.
  - Transcripts: README points to Seeking Alpha / IR webcasts.

Output:
  AVGO/
  ├── FY2025/
  │   ├── Earnings_Releases/
  │   └── SEC_Filings/
  ├── FY2026/
  │   ├── Earnings_Releases/
  │   └── SEC_Filings/
  ├── README.md
  └── DOCUMENT_INVENTORY.md

Usage:
    uv run python scripts/download_avgo_earnings.py
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path

import httpx

from tickerlens.config import get_settings

# ── constants ────────────────────────────────────────────────────────────────

TICKER = "AVGO"
CIK = "1730168"
OUTPUT_ROOT = Path("AVGO")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Last 4 reported quarters as of 2026-06-02
QUARTERS = [
    {
        "label": "Q2 FY2025",
        "fy": "FY2025",
        "period_end": "2025-05-04",
        "er_url": "https://www.sec.gov/Archives/edgar/data/1730168/000173016825000061/avgo-05042025x8kxex99.htm",
        "sec_url": "https://www.sec.gov/Archives/edgar/data/1730168/000173016825000064/avgo-20250504.htm",
        "sec_type": "10-Q",
    },
    {
        "label": "Q3 FY2025",
        "fy": "FY2025",
        "period_end": "2025-08-03",
        "er_url": "https://www.sec.gov/Archives/edgar/data/1730168/000173016825000094/avgo-08032025x8kxex99.htm",
        "sec_url": "https://www.sec.gov/Archives/edgar/data/1730168/000173016825000098/avgo-20250803.htm",
        "sec_type": "10-Q",
    },
    {
        "label": "Q4 FY2025",
        "fy": "FY2025",
        "period_end": "2025-11-02",
        "er_url": "https://www.sec.gov/Archives/edgar/data/1730168/000173016825000116/avgo-11022025x8kxex99.htm",
        "sec_url": "https://www.sec.gov/Archives/edgar/data/1730168/000173016825000121/avgo-20251102.htm",
        "sec_type": "10-K",
    },
    {
        "label": "Q1 FY2026",
        "fy": "FY2026",
        "period_end": "2026-02-01",
        "er_url": "https://www.sec.gov/Archives/edgar/data/1730168/000173016826000011/avgo-02012026x8kxex99.htm",
        "sec_url": "https://www.sec.gov/Archives/edgar/data/1730168/000173016826000016/avgo-20260201.htm",
        "sec_type": "10-Q",
    },
]

# ── helpers ──────────────────────────────────────────────────────────────────

def _banner(text: str) -> None:
    print(f"\n{'─'*55}")
    print(f"  {text}")
    print(f"{'─'*55}")


def _fetch_html(url: str, client: httpx.Client, last: list[float]) -> bytes | None:
    """Download HTML from EDGAR using the authenticated client."""
    elapsed = time.monotonic() - last[0]
    if elapsed < 0.15:
        time.sleep(0.15 - elapsed)
    last[0] = time.monotonic()
    print(f"    [DL  ] {url.split('/')[-1]}")
    try:
        r = client.get(url, timeout=60.0)
        r.raise_for_status()
        if b"Undeclared Automated Tool" in r.content[:2000]:
            print(f"    [ERR ] SEC rate-limited — retry later")
            return None
        print(f"    [OK  ] {len(r.content)//1024} KB downloaded")
        return r.content
    except Exception as e:
        print(f"    [ERR ] {e}")
        return None


def _html_to_pdf(html: bytes, dest: Path, timeout_sec: int = 120) -> bool:
    """Write HTML to a temp file and convert to PDF with Chrome headless."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".htm", delete=False) as tmp:
        tmp.write(html)
        tmp_path = tmp.name

    print(f"    [PDF ] → {dest.name}  (Chrome headless, up to {timeout_sec}s)")
    try:
        result = subprocess.run(
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
        )
        if dest.exists() and dest.stat().st_size > 10_000:
            size_kb = dest.stat().st_size // 1024
            # Quick page count
            try:
                info = subprocess.run(
                    ["pdfinfo", str(dest)], capture_output=True, text=True, timeout=5
                )
                pages_line = next((l for l in info.stdout.splitlines() if "Pages:" in l), "")
                pages = pages_line.split()[-1] if pages_line else "?"
            except Exception:
                pages = "?"
            print(f"    [OK  ] {dest.name}  ({size_kb} KB, {pages} pages)")
            return True
        stderr = result.stderr[:300].decode(errors="replace") if result.stderr else ""
        print(f"    [ERR ] Chrome exit {result.returncode}. {stderr}")
        return False
    except subprocess.TimeoutExpired:
        print(f"    [ERR ] Chrome timed out after {timeout_sec}s")
        return False
    except Exception as e:
        print(f"    [ERR ] {e}")
        return False
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _convert(url: str, dest: Path, client: httpx.Client, last: list[float], timeout: int) -> bool:
    """Full pipeline: skip if exists, otherwise download + convert."""
    if dest.exists() and dest.stat().st_size > 10_000:
        try:
            info = subprocess.run(["pdfinfo", str(dest)], capture_output=True, text=True, timeout=5)
            pages_line = next((l for l in info.stdout.splitlines() if "Pages:" in l), "")
            pages = pages_line.split()[-1] if pages_line else "?"
        except Exception:
            pages = "?"
        print(f"    [skip] {dest.name}  ({dest.stat().st_size//1024} KB, {pages} pages)")
        return True
    html = _fetch_html(url, client, last)
    if html is None:
        return False
    return _html_to_pdf(html, dest, timeout_sec=timeout)


# ── main ─────────────────────────────────────────────────────────────────────

def run() -> None:
    settings = get_settings()
    client = httpx.Client(
        headers={"User-Agent": settings.edgar_user_agent, "Accept-Encoding": "gzip, deflate"},
        follow_redirects=True,
    )
    last = [0.0]

    print(f"\n{'='*55}")
    print(f"  AVGO earnings download  (last 4 quarters)")
    print(f"  Output: {OUTPUT_ROOT.resolve()}")
    print(f"{'='*55}")

    downloaded: list[dict] = []

    for q in QUARTERS:
        label = q["label"]
        fy = q["fy"]
        slug = label.replace(" ", "_")

        _banner(f"{label}  (period end {q['period_end']})")

        er_dir = OUTPUT_ROOT / fy / "Earnings_Releases"
        sec_dir = OUTPUT_ROOT / fy / "SEC_Filings"

        # ── Earnings Release ─────────────────────────────────────────────────
        print(f"\n  Earnings Release (8-K ex99):")
        er_dest = er_dir / f"AVGO_{slug}_Earnings_Release.pdf"
        if _convert(q["er_url"], er_dest, client, last, timeout=90):
            downloaded.append({"quarter": label, "fy": fy, "type": "Earnings Release", "file": str(er_dest)})

        # ── 10-Q / 10-K ──────────────────────────────────────────────────────
        sec_type = q["sec_type"]
        print(f"\n  {sec_type}:")
        timeout = 240 if sec_type == "10-K" else 150
        sec_dest = sec_dir / f"AVGO_{slug}_{sec_type}.pdf"
        if _convert(q["sec_url"], sec_dest, client, last, timeout=timeout):
            downloaded.append({"quarter": label, "fy": fy, "type": sec_type, "file": str(sec_dest)})

    # ── Summary + meta files ─────────────────────────────────────────────────
    print(f"\n\n{'='*55}")
    print(f"  Complete — {len(downloaded)} files")
    print(f"{'='*55}")
    for d in downloaded:
        p = Path(d["file"])
        size = p.stat().st_size // 1024 if p.exists() else 0
        print(f"  {d['quarter']:15s}  {d['type']:16s}  {size:>5} KB  {p.name}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    _write_readme()
    _write_inventory(downloaded)
    print(f"\n  README.md and DOCUMENT_INVENTORY.md written.\n")


def _write_readme() -> None:
    (OUTPUT_ROOT / "README.md").write_text(
        "# AVGO (Broadcom Inc.) Earnings Research Materials\n\n"
        "## Company Profile\n\n"
        "| Field | Value |\n"
        "|-------|-------|\n"
        "| Name | Broadcom Inc. |\n"
        "| Ticker | AVGO (Nasdaq) |\n"
        f"| CIK | {CIK} |\n"
        "| Sector | Semiconductors / Infrastructure Software |\n"
        "| Investor Relations | https://investors.broadcom.com |\n"
        "| SEC EDGAR | https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001730168 |\n\n"
        "## Coverage — Last 4 Reported Quarters\n\n"
        "| Quarter | Period End | Fiscal Year |\n"
        "|---------|------------|-------------|\n"
        + "\n".join(f"| {q['label']} | {q['period_end']} | {q['fy']} |" for q in QUARTERS)
        + "\n\n"
        "## Folder Structure\n\n"
        "```\n"
        "AVGO/\n"
        "├── FY2025/\n"
        "│   ├── Earnings_Releases/   # Press release PDFs (from SEC EDGAR 8-K exhibit 99)\n"
        "│   └── SEC_Filings/         # 10-Q PDFs\n"
        "├── FY2026/\n"
        "│   ├── Earnings_Releases/\n"
        "│   └── SEC_Filings/         # 10-K (FY2025) + 10-Q\n"
        "├── README.md\n"
        "└── DOCUMENT_INVENTORY.md\n"
        "```\n\n"
        "## Notes on Document Types\n\n"
        "### Earnings Presentations\n"
        "Broadcom does **not** publish a separate investor slide deck for quarterly earnings\n"
        "(unlike some peers such as CRDO). There is no standalone presentation PDF.\n\n"
        "### Earnings Call Transcripts\n"
        "Not automatically downloaded. Retrieve from:\n"
        "- https://seekingalpha.com/symbol/AVGO/earnings/transcripts\n"
        "- https://investors.broadcom.com (Webcasts & Events section)\n\n"
        "Add transcripts to the relevant `FY*/Transcripts/` subfolder.\n\n"
        f"**Generated:** {date.today().isoformat()}\n"
        "**Source:** SEC EDGAR (rendered to PDF via Chrome headless)\n"
    )


def _write_inventory(downloaded: list[dict]) -> None:
    rows = "\n".join(
        f"| {d['quarter']} | {d['type']} | {Path(d['file']).name} |"
        for d in downloaded
    )
    (OUTPUT_ROOT / "DOCUMENT_INVENTORY.md").write_text(
        "# AVGO Document Inventory\n\n"
        f"**Generated:** {date.today().isoformat()}\n"
        "**Company:** Broadcom Inc. (AVGO)\n\n"
        "## Downloaded Files\n\n"
        "| Quarter | Type | File |\n"
        "|---------|------|------|\n"
        + rows
        + "\n\n"
        "## Transcript Sources\n\n"
        "| Platform | URL |\n"
        "|----------|-----|\n"
        "| Seeking Alpha | https://seekingalpha.com/symbol/AVGO/earnings/transcripts |\n"
        "| Investing.com | https://www.investing.com/equities/broadcom-inc-earnings |\n"
        "| Broadcom IR | https://investors.broadcom.com/company-information/events-presentations |\n"
    )


if __name__ == "__main__":
    run()
