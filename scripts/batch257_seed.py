"""Batch 257 seed: backfill AMT's three missing quarters (2023-12-31,
2024-03-31, 2024-06-30).

Diagnosis (scripts/batch257_probe.py): AMT has quarterly_financials
rows only from 2024-09-30 onward, although the blast cache holds
exhibits back to 2023-12-31. AMT was seeded with the default
``periods=8`` window ending 2026-06-30, so Q4 FY2023 / Q1-Q2 FY2024
were never in the window — a seeding gap, not an extraction defect
(the three quarters' exhibits extract cleanly: 7-bullet highlights
each, in-sync with the stored rows' shape).

This script re-seeds AMT with ``periods=12`` through the production
path (XBRL upsert, then the highlights/guidance/transcript
enrichment for the blank rows), and prints a before/after
verification: the 3 new rows present with financials + highlights,
and the 9 pre-existing rows byte-identical on their financials.

Usage: .venv/bin/python scripts/batch257_seed.py
"""
import sqlite3
import sys
import time

sys.path.insert(0, "src")

from tickerlens.services.financials import FinancialsService

DB = "tickerlens.db"
MISSING = ["2023-12-31", "2024-03-31", "2024-06-30"]


def snapshot(con):
    return con.execute(
        "SELECT period_end, revenue, net_income, eps_diluted, "
        "total_assets, press_release_highlights IS NOT NULL "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = 'AMT' ORDER BY period_end"
    ).fetchall()


def main() -> int:
    con = sqlite3.connect(DB)
    before = {r[0]: r[1:] for r in snapshot(con)}
    print(f"before: {len(before)} AMT rows")
    con.close()

    svc = FinancialsService()
    t0 = time.monotonic()
    rows = svc.fetch_and_persist("AMT", periods=12)
    print(f"fetch_and_persist: {len(rows)} quarters "
          f"in {time.monotonic() - t0:.1f}s", flush=True)

    # Fill highlights/guidance/transcripts for the blank rows (the
    # refresh path does this after a pull; the seed path does not).
    from sqlalchemy import select

    from tickerlens.models.company import Company
    from tickerlens.models.database import get_session

    db = get_session()
    try:
        cik = db.scalar(select(Company.cik).where(Company.ticker == "AMT"))
        svc._enrich_press_release_highlights(db, "AMT", cik)
        db.commit()
    finally:
        db.close()

    con = sqlite3.connect(DB)
    after = {r[0]: r[1:] for r in snapshot(con)}
    print(f"after: {len(after)} AMT rows")
    for pe in MISSING:
        r = after.get(pe)
        if r is None:
            print(f"  MISSING STILL: {pe}")
        else:
            print(f"  NEW {pe}: rev={r[0]} ni={r[1]} eps_d={r[2]} "
                  f"assets={r[3]} has_highlights={bool(r[4])}")
    changed = [pe for pe in before if before[pe] != after.get(pe)]
    print(f"pre-existing rows changed: {changed if changed else 'none'}")
    con.close()
    return 0 if all(pe in after for pe in MISSING) else 1


if __name__ == "__main__":
    raise SystemExit(main())
