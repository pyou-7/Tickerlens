"""Batch 110 blast-radius: extract highlights for tickers with known-good
headlines; run once with new code, once stashed (old code), diff the two.
Usage: batch111_blast.py <output-json>"""
import json
import sys
from datetime import date

sys.path.insert(0, "src")

from sqlalchemy import select

from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.services.financials import FinancialsService
from tickerlens.services.ir_download import discover_earnings_filings

# Tickers whose stored headlines are currently good (batch-108 sample + recent
# fix tickers). Two most recent quarters each.
TICKERS = ["AAPL", "JPM", "LLY", "WM", "MRK", "MSFT", "NVDA", "XOM",
           "CHD", "GEV", "SO", "SPG", "APH", "DHR", "MA", "ELV", "PGR", "AAL"]


def main() -> None:
    out_path = sys.argv[1]
    db = get_session()
    svc = FinancialsService()
    results = {}
    for ticker in TICKERS:
        try:
            cik = db.execute(
                select(Company.cik).where(Company.ticker == ticker)
            ).scalar_one()
        except Exception as e:
            results[ticker] = {"error": f"no cik: {e}"}
            continue
        try:
            periods = discover_earnings_filings(
                ticker, svc.edgar_client, n_quarters=2
            )
        except Exception as e:
            results[ticker] = {"error": f"discovery: {e}"}
            continue
        for p in periods[-2:]:
            key = f"{ticker} {p.period_end}"
            try:
                hl, *_ = svc._fetch_press_release_disclosures(cik, p)
            except Exception as e:
                results[key] = {"error": f"fetch: {type(e).__name__}"}
                continue
            results[key] = {
                "headline": (hl or "").split("\n\n")[0].strip()[:150] if hl else None,
                "len": len(hl) if hl else 0,
            }
            print(f"done {key}", flush=True)
    json.dump(results, open(out_path, "w"), indent=1)
    print(f"wrote {out_path} ({len(results)} entries)", flush=True)


if __name__ == "__main__":
    main()
