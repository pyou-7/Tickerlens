"""Batch 111 verify: re-extract all contact-class target quarters with the
new extractor and print old vs new headlines for manual verification.
Usage: batch111_verify.py <targets-json> <output-json>"""
import json
import sys
from datetime import date

sys.path.insert(0, "src")

from sqlalchemy import select

from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.services.financials import FinancialsService
from tickerlens.services.ir_download import discover_earnings_filings


def main() -> None:
    targets = json.load(open(sys.argv[1]))
    out_path = sys.argv[2]
    db = get_session()
    svc = FinancialsService()
    results = {}
    for ticker, pes in sorted(targets.items()):
        cik = db.execute(
            select(Company.cik).where(Company.ticker == ticker)
        ).scalar_one()
        try:
            periods = discover_earnings_filings(
                ticker, svc.edgar_client, n_quarters=8,
                oldest_period_end=date.fromisoformat(min(pes)),
            )
        except Exception as e:
            print(f"{ticker}: discovery failed ({e})", flush=True)
            results[ticker] = {"error": f"discovery: {e}"}
            continue
        by_pe = {str(p.period_end): p for p in periods}
        for pe in pes:
            qrow = db.execute(
                select(QuarterlyFinancial).where(
                    QuarterlyFinancial.cik == cik,
                    QuarterlyFinancial.period_end == date.fromisoformat(pe),
                )
            ).scalar_one_or_none()
            if qrow is None:
                print(f"{ticker} {pe}: no DB row", flush=True)
                continue
            old_head = (qrow.press_release_highlights or "").split("\n\n")[0].strip()
            period = by_pe.get(pe)
            if period is None:
                print(f"{ticker} {pe}: no matching earnings period", flush=True)
                results[f"{ticker} {pe}"] = {"old": old_head, "new": None, "note": "no period"}
                continue
            try:
                hl, hl_src, *_ = svc._fetch_press_release_disclosures(cik, period)
            except Exception as e:
                print(f"{ticker} {pe}: fetch failed ({type(e).__name__})", flush=True)
                results[f"{ticker} {pe}"] = {"old": old_head, "new": None, "note": "fetch failed"}
                continue
            new_head = (hl or "").split("\n\n")[0].strip() if hl else None
            results[f"{ticker} {pe}"] = {"old": old_head, "new": new_head}
            print(f"--- {ticker} {pe} ---", flush=True)
            print(f"OLD: {old_head[:90]}", flush=True)
            print(f"NEW: {(new_head or '')[:110]}", flush=True)
    json.dump(results, open(out_path, "w"), indent=1)
    print(f"wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
