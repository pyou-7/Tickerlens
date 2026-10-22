"""Batch 111 live repair: re-extract contact-class junk-headline quarters.

The stored headlines ('Qualcomm Contact:', 'INVESTOR RELATIONS:', 'Frank
Morgan', 'Jill Chapman McLean, VA 22102', '24-Hour: 800.559.3853',
'For investors', 'Analyst Contact: Abby Motsinger') were contact-block
residue picked by older code. The current extractor (with the batch-111
QCOM/BLK fixes) recovers the real headlines from the same exhibits.

A row is overwritten only when the fresh extraction yields a different,
non-None headline. A transient fetch failure (None) never wipes a stored
value. Only press_release_highlights (+source) are touched.
"""
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

TARGETS = json.load(open("/tmp/batch111_targets.json"))


def main() -> None:
    db = get_session()
    svc = FinancialsService()
    changed, skipped, failed = 0, 0, 0

    for ticker, pes in sorted(TARGETS.items()):
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
            failed += len(pes)
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
                failed += 1
                continue
            old_headline = (qrow.press_release_highlights or "").split("\n\n")[0].strip()
            period = by_pe.get(pe)
            if period is None:
                print(f"{ticker} {pe}: no matching earnings period", flush=True)
                skipped += 1
                continue
            try:
                hl, hl_src, _, _, _, _ = svc._fetch_press_release_disclosures(
                    cik, period
                )
            except Exception as e:
                print(f"{ticker} {pe}: fetch failed ({type(e).__name__})", flush=True)
                failed += 1
                continue
            if hl is None:
                # Transient failure: never wipe the stored value.
                print(f"{ticker} {pe}: no extraction (skip)", flush=True)
                skipped += 1
                continue
            new_headline = hl.split("\n\n")[0].strip()
            if new_headline == old_headline:
                print(f"{ticker} {pe}: unchanged", flush=True)
                skipped += 1
                continue
            qrow.press_release_highlights = hl
            if hl_src:
                qrow.press_release_source = hl_src
            changed += 1
            print(f"{ticker} {pe}: {old_headline[:45]!r} -> {new_headline[:60]!r}",
                  flush=True)
    db.commit()
    print(f"CHANGED={changed} SKIPPED={skipped} FAILED={failed}", flush=True)


if __name__ == "__main__":
    main()
