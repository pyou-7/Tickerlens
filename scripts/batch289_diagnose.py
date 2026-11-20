"""Batch 289 diagnose: why do 39 quarters still break after the fix?

For each still-broken (ticker, end) from the blast, inspect the chosen
balance-sheet facts: leg accns, filed mezzanine, residual, slot state.
Also diffs stored-break set vs after-break set to find NEW breaks.
DRY RUN only.
Usage: .venv/bin/python scripts/batch289_diagnose.py
"""
import sqlite3
import sys
from datetime import date

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient, companyfacts_with_predecessors
from tickerlens.data.xbrl import (
    BALANCE_SHEET_METRICS,
    Metric,
    _balance_sheet_facts,
    _reconcile_balance_sheet_identity,
)
from tickerlens.models.quarterly_financial import identity_tolerance

DB = "tickerlens.db"
STILL = [
    ("APLD", "2024-08-31"), ("APLD", "2024-11-30"), ("APLD", "2025-05-31"),
    ("APLD", "2025-08-31"), ("APLD", "2025-11-30"),
    ("BLK", "2025-09-30"), ("BLK", "2026-03-31"), ("BLK", "2026-06-30"),
    ("CART", "2024-09-30"), ("CART", "2024-12-31"), ("CART", "2025-03-31"),
    ("CART", "2025-06-30"), ("CART", "2025-09-30"), ("CART", "2026-03-31"),
    ("CART", "2026-06-30"),
    ("KKR", "2024-09-30"), ("KKR", "2024-12-31"), ("KKR", "2025-03-31"),
    ("KKR", "2025-06-30"), ("KKR", "2025-09-30"), ("KKR", "2025-12-31"),
    ("KKR", "2026-03-31"), ("KKR", "2026-06-30"),
    ("NEE", "2024-12-31"),
    ("PRU", "2024-12-31"), ("PRU", "2025-03-31"), ("PRU", "2025-06-30"),
    ("PRU", "2025-09-30"), ("PRU", "2025-12-31"), ("PRU", "2026-03-31"),
    ("PRU", "2026-06-30"),
    ("TDG", "2026-06-27"),
    ("WELL", "2024-06-30"), ("WELL", "2024-09-30"), ("WELL", "2025-03-31"),
    ("WELL", "2025-06-30"), ("WELL", "2025-09-30"), ("WELL", "2026-03-31"),
    ("WELL", "2026-06-30"),
]


def closes(a, l, e, rnci, temp) -> bool | None:
    if None in (a, l, e):
        return None
    return abs(a - l - (rnci or 0) - (temp or 0) - e) <= identity_tolerance(a)


def main() -> int:
    con = sqlite3.connect(DB)
    meta = {t: (cik, fye) for t, cik, fye in con.execute(
        "SELECT ticker, cik, fiscal_year_end FROM companies")}
    before = set()
    for (ticker, pe, a, l, e, rnci, temp) in con.execute(
        "SELECT c.ticker, q.period_end, q.total_assets, "
        "q.total_liabilities, q.total_equity, q.redeemable_nci, "
        "q.temporary_equity FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik"
    ):
        if closes(a, l, e, rnci, temp) is False:
            before.add((ticker, pe))
    con.close()
    after = set(STILL)
    print(f"Stored breaks: {len(before)}; after breaks: {len(after)}")
    print(f"NEW breaks (after, not before): {sorted(after - before)}")
    print(f"Fixed: {len(before - after)}")

    client = EdgarClient()
    cache = {}
    for ticker, end_s in STILL:
        cik, fye = meta[ticker]
        if cik not in cache:
            cache[cik] = companyfacts_with_predecessors(client, cik)
        facts = cache[cik]
        end = date.fromisoformat(end_s)
        bs = {}
        for m in BALANCE_SHEET_METRICS:
            try:
                bs[m] = _balance_sheet_facts(facts, m, fye)
            except KeyError:
                bs[m] = {}
        _reconcile_balance_sheet_identity(bs, facts, fye)
        a = bs[Metric.TOTAL_ASSETS].get(end)
        l = bs[Metric.TOTAL_LIABILITIES].get(end)
        e = bs[Metric.TOTAL_EQUITY].get(end)
        rnci = bs[Metric.REDEEMABLE_NCI].get(end)
        temp = bs[Metric.TEMPORARY_EQUITY].get(end)
        if None in (a, l, e):
            print(f"{ticker} {end_s}: missing leg A={a} L={l} E={e}")
            continue
        filed_mezz = (rnci.val if rnci else 0) + (temp.val if temp else 0)
        residual = a.val - l.val - e.val - filed_mezz
        print(
            f"{ticker} {end_s}: residual={residual:,.0f} "
            f"tol={identity_tolerance(a.val):,.0f} "
            f"A.accn={a.accn} L.accn={l.accn} E.accn={e.accn} "
            f"rnci={rnci.val if rnci else None} "
            f"temp={temp.val if temp else None} "
            f"A.filed={a.filed} L.filed={l.filed} E.filed={e.filed}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
