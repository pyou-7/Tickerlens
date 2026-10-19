#!/usr/bin/env python3
"""Backfill per-period press-release disclosures for zero-highlight companies.

Usage:
    .venv/bin/python scripts/backfill_disclosures.py [--limit N] [--ticker XYZ]

Finds every company whose stored quarters ALL lack press_release_highlights
(the zero-highlight cohort: undiscovered exhibit-naming conventions, or
companies the lazy page-view trigger never reached), then runs
FinancialsService._enrich_press_release_highlights for each with no time
budget. Fill-only: a transient failure never wipes a previously-good value;
per-ticker failures are counted and reported, never raised.

Polite to SEC: ~0.5s between companies (each is ~1 submissions fetch + one
filing-index + one exhibit fetch per missing quarter), well under 10 req/s.

Must run with cwd=repo root so .env loads and the DB resolves to
./tickerlens.db.
"""

import argparse
import logging
import sys
import time

sys.path.insert(0, "src")

from tickerlens.models.company import Company  # noqa: E402
from tickerlens.models.database import get_session  # noqa: E402
from tickerlens.models.quarterly_financial import QuarterlyFinancial  # noqa: E402
from tickerlens.services.financials import FinancialsService  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

SLEEP_SECONDS = 0.5


def _zero_highlight_tickers(session) -> list[tuple[str, str]]:
    """(ticker, cik) for companies with zero quarters carrying highlights."""
    out = []
    for company in session.query(Company).order_by(Company.ticker).all():
        rows = (
            session.query(QuarterlyFinancial)
            .filter(QuarterlyFinancial.cik == company.cik)
            .all()
        )
        if not rows:
            continue
        if all(not (r.press_release_highlights or "").strip() for r in rows):
            out.append((company.ticker, company.cik))
    return out


def _filled_count(session, cik: str) -> int:
    return (
        session.query(QuarterlyFinancial)
        .filter(QuarterlyFinancial.cik == cik)
        .filter(QuarterlyFinancial.press_release_highlights.isnot(None))
        .filter(QuarterlyFinancial.press_release_highlights != "")
        .filter(QuarterlyFinancial.press_release_highlights != "[]")
        .count()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="backfill at most N companies")
    parser.add_argument("--ticker", default="", help="backfill a single ticker")
    args = parser.parse_args()

    svc = FinancialsService()
    session = get_session()
    try:
        targets = _zero_highlight_tickers(session)
        if args.ticker:
            targets = [t for t in targets if t[0] == args.ticker.upper()]
        if args.limit:
            targets = targets[: args.limit]
        print(f"{len(targets)} zero-highlight companies")

        rescued = 0
        failed: list[str] = []
        for i, (ticker, cik) in enumerate(targets, 1):
            try:
                before = _filled_count(session, cik)
                svc._enrich_press_release_highlights(session, ticker, cik, deadline=None)
                session.commit()
                after = _filled_count(session, cik)
            except Exception as exc:  # never raise: count and continue
                session.rollback()
                failed.append(f"{ticker} (error: {type(exc).__name__})")
                print(f"[{i}/{len(targets)}] {ticker}: error {type(exc).__name__}")
                time.sleep(SLEEP_SECONDS)
                continue
            gained = after - before
            if gained:
                rescued += 1
                print(f"[{i}/{len(targets)}] {ticker}: +{gained} quarters with highlights")
            else:
                failed.append(f"{ticker} (no exhibit discovered/extracted)")
                print(f"[{i}/{len(targets)}] {ticker}: still zero")
            time.sleep(SLEEP_SECONDS)

        print(f"\nrescued={rescued} still_zero={len(failed)}")
        for f in failed:
            print("  -", f)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
