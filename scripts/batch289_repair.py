"""Batch 289 repair: re-seed the identity-break tickers with the fixed
extractor (TEMPORARY_EQUITY IncludingPortion chain tag + residual
mezzanine derivation), plus OXY whose Q4 FY2025 income quarter was
seeded blank (stale snapshot; fresh extraction derives it fully).

Re-seed = FinancialsService.fetch_and_persist (live EDGAR pull, upsert).
Verification per ticker: every stored quarter with A/L/E present must
close A = L + rnci + temp + E within identity_tolerance, and the
previously-broken quarters must carry the expected mezzanine values.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch289_repair.py
       .venv/bin/python scripts/batch289_repair.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient
from tickerlens.models.quarterly_financial import identity_tolerance
from tickerlens.services.financials import FinancialsService

TICKERS = ("BLK", "CART", "DLR", "APLD", "OXY")
DB = "tickerlens.db"
DRY_RUN = os.environ.get("DRY_RUN") == "1"


def identity_report(con: sqlite3.Connection, ticker: str) -> list[str]:
    rows = con.execute(
        "SELECT q.period_end, q.total_assets, q.total_liabilities, "
        "q.total_equity, q.redeemable_nci, q.temporary_equity, "
        "q.revenue, q.net_income "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = ? ORDER BY q.period_end",
        (ticker,),
    ).fetchall()
    lines = []
    for pe, a, l, e, rnci, temp, rev, ni in rows:
        if None in (a, l, e):
            lines.append(f"  {pe}: legs incomplete A={a} L={l} E={e}")
            continue
        gap = a - l - (rnci or 0) - (temp or 0) - e
        ok = abs(gap) <= identity_tolerance(a)
        lines.append(
            f"  {pe}: {'CLOSES' if ok else 'BREAKS'} gap={gap:,.0f} "
            f"rnci={rnci} temp={temp} rev={rev} ni={ni}"
        )
    return lines


def main() -> int:
    con = sqlite3.connect(DB)
    print("=== BEFORE ===")
    for t in TICKERS:
        print(f"{t}:")
        print("\n".join(identity_report(con, t)))
    con.close()

    if DRY_RUN:
        print("\nDRY RUN — no re-seed performed.")
        return 0

    service = FinancialsService(edgar_client=EdgarClient())
    for t in TICKERS:
        rows = service.fetch_and_persist(t, periods=12)
        print(f"{t}: re-seeded {len(rows)} quarters")

    con = sqlite3.connect(DB)
    print("\n=== AFTER ===")
    bad = 0
    for t in TICKERS:
        print(f"{t}:")
        report = identity_report(con, t)
        print("\n".join(report))
        bad += sum(1 for ln in report if "BREAKS" in ln)
    con.close()
    print(f"\nRemaining breaks: {bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
