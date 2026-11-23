"""Batch 289 repair v2 (supersedes batch289_repair.py's 5-ticker plan).

The blast showed the extractor fix changes stored balance-sheet values
well beyond the 4 audit tickers: 83 identity breaks fixed, 102 filed
mezzanine fills, 34 restated legs. Repair = targeted balance-sheet
update across all 303 companies: fresh extraction (periods=12) vs
stored rows on (cik, period_end); where any of total_assets /
total_liabilities / total_equity / redeemable_nci / temporary_equity
differs, UPDATE just those columns (+ updated_at). Income metrics are
left untouched (restatement refresh is a separate concern) — except
OXY, whose Q4 FY2025 income quarter was seeded blank and gets a full
FinancialsService.fetch_and_persist re-seed first.

Verification: whole-DB identity check after the update must show 0
breaks. Usage:
  DRY_RUN=1 .venv/bin/python scripts/batch289_repair2.py
  .venv/bin/python scripts/batch289_repair2.py
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient, companyfacts_with_predecessors
from tickerlens.data.xbrl import extract_recent_quarterly_financials
from tickerlens.models.quarterly_financial import identity_tolerance
from tickerlens.services.financials import FinancialsService

DB = "tickerlens.db"
DRY_RUN = os.environ.get("DRY_RUN") == "1"
BS_FIELDS = (
    "total_assets",
    "total_liabilities",
    "total_equity",
    "redeemable_nci",
    "temporary_equity",
)


def differs(old, new) -> bool:
    if old is None or new is None:
        return old is not new
    return abs(old - new) > 1.0


def identity_breaks(con: sqlite3.Connection) -> list[tuple]:
    out = []
    for (ticker, pe, a, l, e, rnci, temp) in con.execute(
        "SELECT c.ticker, q.period_end, q.total_assets, "
        "q.total_liabilities, q.total_equity, q.redeemable_nci, "
        "q.temporary_equity FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik"
    ):
        if None in (a, l, e):
            continue
        if abs(a - l - (rnci or 0) - (temp or 0) - e) > identity_tolerance(a):
            out.append((ticker, pe))
    return out


def main() -> int:
    con = sqlite3.connect(DB)
    before = identity_breaks(con)
    print(f"Identity breaks BEFORE: {len(before)}")
    companies = con.execute(
        "SELECT ticker, cik, fiscal_year_end, sic FROM companies "
        "ORDER BY ticker"
    ).fetchall()
    stored = {}
    for row in con.execute(
        "SELECT cik, period_end, total_assets, total_liabilities, "
        "total_equity, redeemable_nci, temporary_equity "
        "FROM quarterly_financials"
    ):
        stored[(row[0], row[1])] = row[2:]
    con.close()

    client = EdgarClient()
    updates = []  # (cik, period_end, new5tuple, changed_fields, ticker)
    errors = []
    for ticker, cik, fye, sic in companies:
        try:
            facts = companyfacts_with_predecessors(client, cik)
            rows = extract_recent_quarterly_financials(
                facts, fiscal_year_end=fye, periods=12, sic=sic
            )
        except Exception as exc:  # noqa: BLE001 - repair sweep
            errors.append((ticker, repr(exc)[:120]))
            continue
        for row in rows:
            key = (cik, row.end.isoformat())
            if key not in stored:
                continue
            new = (
                row.total_assets,
                row.total_liabilities,
                row.total_equity,
                row.redeemable_nci,
                row.temporary_equity,
            )
            old = stored[key]
            changed = [
                BS_FIELDS[i] for i in range(5) if differs(old[i], new[i])
            ]
            if changed:
                updates.append((cik, key[1], new, changed, ticker))

    print(f"Extraction errors: {len(errors)} {errors[:5]}")
    print(f"Rows to update: {len(updates)} "
          f"across {len({u[4] for u in updates})} tickers")
    for cik, pe, new, changed, ticker in updates:
        print(f"  {ticker} {pe}: {', '.join(changed)} -> {new}")

    if DRY_RUN:
        print("\nDRY RUN — no writes performed.")
        return 0

    # OXY: full re-seed (blank Q4 FY2025 income quarter + restatement).
    service = FinancialsService(edgar_client=client)
    oxy_rows = service.fetch_and_persist("OXY", periods=12)
    print(f"OXY: re-seeded {len(oxy_rows)} quarters")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    con = sqlite3.connect(DB)
    with con:
        for cik, pe, new, _changed, _ticker in updates:
            con.execute(
                "UPDATE quarterly_financials SET total_assets=?, "
                "total_liabilities=?, total_equity=?, redeemable_nci=?, "
                "temporary_equity=?, updated_at=? "
                "WHERE cik=? AND period_end=?",
                (*new, now, cik, pe),
            )
    after = identity_breaks(con)
    oxy = con.execute(
        "SELECT q.period_end, q.revenue, q.net_income, q.eps_diluted, "
        "q.free_cash_flow FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik WHERE c.ticker='OXY' "
        "ORDER BY q.period_end DESC LIMIT 4"
    ).fetchall()
    con.close()
    print(f"\nIdentity breaks AFTER: {len(after)} {after[:10]}")
    print("OXY latest quarters (pe, rev, ni, eps_d, fcf):")
    for r in oxy:
        print(f"  {r}")
    return 0 if not after else 1


if __name__ == "__main__":
    raise SystemExit(main())
