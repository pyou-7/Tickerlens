"""
Export the last N quarters of earnings for a ticker to a ZIP file containing a CSV.

Usage:
    uv run python scripts/export_earnings_zip.py AVGO
    uv run python scripts/export_earnings_zip.py AVGO --periods 4 --out avgo_earnings.zip
"""

from __future__ import annotations

import argparse
import csv
import io
import zipfile
from datetime import date
from pathlib import Path

from tickerlens.data.edgar import EdgarClient
from tickerlens.services.financials import FinancialsService


def _fmt(value: float | None, divisor: float = 1_000_000, decimals: int = 1) -> str:
    if value is None:
        return ""
    return f"{value / divisor:.{decimals}f}"


def export(ticker: str, periods: int, out_path: Path) -> None:
    client = EdgarClient()
    cik = client.cik_for_ticker(ticker)
    print(f"{ticker} → CIK {cik}")

    svc = FinancialsService(edgar_client=client)
    quarters = svc.recent_quarterly_financials(cik, periods=periods)

    if not quarters:
        raise RuntimeError(f"No quarterly data returned for {ticker}")

    as_of = date.today().isoformat()

    # Build CSV in memory
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Period", "Period End",
        "Revenue ($M)", "Net Income ($M)",
        "EPS Basic ($)", "EPS Diluted ($)",
        "Free Cash Flow ($M)",
    ])
    for q in quarters:
        writer.writerow([
            q.period,
            q.end.isoformat(),
            _fmt(q.revenue),
            _fmt(q.net_income),
            _fmt(q.eps_basic, divisor=1, decimals=2),
            _fmt(q.eps_diluted, divisor=1, decimals=2),
            _fmt(q.free_cash_flow),
        ])

    csv_filename = f"{ticker.lower()}_earnings_last{periods}q.csv"

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(csv_filename, buf.getvalue())
        zf.writestr(
            "README.txt",
            f"Tickerlens earnings export\n"
            f"Ticker: {ticker.upper()}  CIK: {cik}\n"
            f"Periods: last {periods} quarters\n"
            f"As of: {as_of}\n"
            f"\nRevenue and cash-flow values are in millions USD.\n"
            f"EPS values are in USD per share.\n"
            f"Source: SEC EDGAR companyfacts API.\n",
        )

    print(f"Written: {out_path}  ({out_path.stat().st_size} bytes)")
    print(f"\nPreview ({csv_filename}):")
    print(buf.getvalue())


def main() -> None:
    parser = argparse.ArgumentParser(description="Export earnings ZIP for a ticker")
    parser.add_argument("ticker", type=str.upper)
    parser.add_argument("--periods", type=int, default=4)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    out = args.out or Path(f"{args.ticker.lower()}_earnings_last{args.periods}q.zip")
    export(args.ticker, args.periods, out)


if __name__ == "__main__":
    main()
