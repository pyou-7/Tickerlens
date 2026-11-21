"""Batch 290 repair: re-seed CRWD/GPC/KMX with the fixed EPS clamp.

The batch-290 fix extends _reconcile_eps_basic_diluted to loss
quarters where the Q4-derived diluted leg came out more negative
than basic (GAAP-impossible). Stored rows affected:
  CRWD 2025-01-31: -0.3953 / -0.4431 -> diluted := -0.3953
  GPC  2025-12-31: -4.224  / -4.2493 -> diluted := -4.224
  KMX  2026-02-28: -0.8508 / -0.8618 -> diluted := -0.8508

Re-seed = FinancialsService.fetch_and_persist (live EDGAR pull,
upsert). Before/after diff over every stored column of the three
tickers; the only expected changes are the three diluted values.
Final gate: DB-wide anti-dilution census (loss quarters with
diluted != basic, profit quarters with diluted > basic) must be 0.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch290_repair.py
       .venv/bin/python scripts/batch290_repair.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient
from tickerlens.services.financials import FinancialsService

TICKERS = ("CRWD", "GPC", "KMX")
TARGETS = {
    ("CRWD", "2025-01-31"): -0.3953,
    ("GPC", "2025-12-31"): -4.224,
    ("KMX", "2026-02-28"): -0.8508,
}
DB = "tickerlens.db"
DRY_RUN = os.environ.get("DRY_RUN") == "1"
COLS = (
    "period_end, fiscal_year, fiscal_period, revenue, net_income, "
    "eps_basic, eps_diluted, free_cash_flow, total_assets, "
    "total_liabilities, total_equity, cash_and_equivalents, "
    "redeemable_nci, temporary_equity, ffo"
)


def snapshot(con: sqlite3.Connection, ticker: str) -> dict:
    rows = con.execute(
        f"SELECT {COLS} FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik WHERE c.ticker = ? "
        "ORDER BY q.period_end",
        (ticker,),
    ).fetchall()
    return {r[0]: r[1:] for r in rows}


def census(con: sqlite3.Connection) -> list:
    return con.execute(
        "SELECT c.ticker, q.period_end, q.eps_basic, q.eps_diluted, q.net_income "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.eps_basic IS NOT NULL AND q.eps_diluted IS NOT NULL AND ("
        "  q.eps_diluted > q.eps_basic + 0.0001"
        "  OR (q.eps_basic < 0 AND q.eps_diluted < q.eps_basic - 0.0001)"
        ") ORDER BY c.ticker, q.period_end"
    ).fetchall()


def main() -> int:
    con = sqlite3.connect(DB)
    before = {t: snapshot(con, t) for t in TICKERS}
    print("=== BEFORE census (anti-dilution violations) ===")
    for row in census(con):
        print(" ", row)
    con.close()

    if DRY_RUN:
        print("\nDRY RUN — no re-seed performed.")
        return 0

    service = FinancialsService(edgar_client=EdgarClient())
    for t in TICKERS:
        rows = service.fetch_and_persist(t, periods=12)
        print(f"{t}: re-seeded {len(rows)} quarters")

    con = sqlite3.connect(DB)
    after = {t: snapshot(con, t) for t in TICKERS}
    print("\n=== DIFF (before -> after) ===")
    unexpected = []
    for t in TICKERS:
        for end in sorted(set(before[t]) | set(after[t])):
            b, a = before[t].get(end), after[t].get(end)
            if b == a:
                continue
            if b is None or a is None:
                print(f"  {t} {end}: row {'added' if b is None else 'removed'}")
                unexpected.append((t, end, "row added/removed"))
                continue
            names = [c.strip() for c in COLS.split(",")][1:]
            for name, bv, av in zip(names, b, a):
                if bv != av:
                    tag = "EXPECTED" if (t, end) in TARGETS and name == "eps_diluted" else "UNEXPECTED"
                    print(f"  {t} {end} {name}: {bv} -> {av} [{tag}]")
                    if tag == "UNEXPECTED":
                        unexpected.append((t, end, name))

    print("\n=== TARGET verification ===")
    ok = True
    for (t, end), expected_basic in TARGETS.items():
        row = con.execute(
            "SELECT q.eps_basic, q.eps_diluted FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = ? AND q.period_end = ?",
            (t, end),
        ).fetchone()
        good = row is not None and row[0] == expected_basic and row[1] == expected_basic
        ok &= good
        print(f"  {t} {end}: basic={row[0] if row else None} diluted={row[1] if row else None} "
              f"expected both {expected_basic} -> {'OK' if good else 'FAIL'}")

    print("\n=== AFTER census (anti-dilution violations) ===")
    remaining = census(con)
    for row in remaining:
        print(" ", row)
    print(f"remaining: {len(remaining)}")
    con.close()

    print(f"\nunexpected changes: {len(unexpected)}")
    return 0 if (ok and not remaining and not unexpected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
