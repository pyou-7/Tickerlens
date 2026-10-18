#!/usr/bin/env python3
"""One-off backfill of Item 1A risk factors for companies missing them.

Usage:
    .venv/bin/python scripts/backfill_risk_factors.py [--limit N]

Finds every company with NULL/empty risk_factors, fetches its latest 10-K
from EDGAR and extracts Item 1A via FinancialsService._fetch_risk_factors.
Persists only on successful extraction (never-wipe: a transient failure
never clears a previously-good value) and never raises — per-ticker
failures are counted and reported in the summary.

Polite to SEC: ~0.5s between companies (each is 2 requests: submissions
JSON + the 10-K document), well under the 10 req/s guideline.
"""

import argparse
import logging
import sys
import time

sys.path.insert(0, "src")

from tickerlens.models.company import Company  # noqa: E402
from tickerlens.models.database import get_session  # noqa: E402
from tickerlens.services.financials import FinancialsService  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

SLEEP_SECONDS = 0.5


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="backfill at most N companies")
    args = parser.parse_args()

    svc = FinancialsService()
    session = get_session()

    try:
        missing: list[Company] = (
            session.query(Company)
            .filter((Company.risk_factors.is_(None)) | (Company.risk_factors == ""))
            .order_by(Company.ticker)
            .all()
        )
        if args.limit:
            missing = missing[: args.limit]
        print(f"{len(missing)} companies missing risk_factors")

        rescued = 0
        failed: list[str] = []
        for i, company in enumerate(missing, 1):
            try:
                text, source = svc._fetch_risk_factors(company.cik)
            except Exception as exc:  # never raise: count and continue
                failed.append(f"{company.ticker} (error: {type(exc).__name__})")
                print(f"[{i}/{len(missing)}] {company.ticker}: error {type(exc).__name__}")
                continue
            if text:
                company.risk_factors = text
                company.risk_factors_source = source
                session.commit()
                rescued += 1
                print(f"[{i}/{len(missing)}] {company.ticker}: OK ({len(text)} chars, {source})")
            else:
                failed.append(f"{company.ticker} (no extractable Item 1A)")
                print(f"[{i}/{len(missing)}] {company.ticker}: no extractable Item 1A")
            time.sleep(SLEEP_SECONDS)

        print(f"\nrescued={rescued} still_missing={len(failed)}")
        for f in failed:
            print("  -", f)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
