"""Batch 289 blast: re-extract every stored ticker with the new code
and compare balance-sheet legs vs the stored DB.

Checks:
- Identity closure (A vs L + rnci + temp + E, code tolerance) before
  (stored) and after (new extraction) for every quarter.
- Every A/L/E value change (restatement/staleness review).
- Every mezzanine (rnci/temp) change — expected only where a gap
  existed (DLR chain fill + BLK/CART/APLD residual derivation).

Fetches companyfacts via EdgarClient (disk-cached). DRY RUN only.
Usage: .venv/bin/python scripts/batch289_blast.py
"""
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient, companyfacts_with_predecessors
from tickerlens.data.xbrl import extract_recent_quarterly_financials
from tickerlens.models.quarterly_financial import identity_tolerance

DB = "tickerlens.db"


def closes(a, l, e, rnci, temp) -> bool | None:
    if None in (a, l, e):
        return None
    return abs(a - l - (rnci or 0) - (temp or 0) - e) <= identity_tolerance(a)


def main() -> int:
    con = sqlite3.connect(DB)
    companies = con.execute(
        "SELECT ticker, cik, fiscal_year_end, sic FROM companies "
        "ORDER BY ticker"
    ).fetchall()
    stored = {}
    for (ticker, pe, a, l, e, rnci, temp) in con.execute(
        "SELECT c.ticker, q.period_end, q.total_assets, "
        "q.total_liabilities, q.total_equity, q.redeemable_nci, "
        "q.temporary_equity FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik"
    ):
        stored[(ticker, pe)] = (a, l, e, rnci, temp)
    con.close()

    client = EdgarClient()
    leg_changes = []
    mezz_changes = []
    breaks_before = []
    breaks_after = []
    fixed = []
    errors = []

    for i, (ticker, cik, fye, sic) in enumerate(companies, 1):
        if i % 50 == 0:
            print(f"... {i}/{len(companies)}", flush=True)
        try:
            facts = companyfacts_with_predecessors(client, cik)
            rows = extract_recent_quarterly_financials(
                facts, fiscal_year_end=fye, periods=12, sic=sic
            )
        except Exception as exc:  # noqa: BLE001 - blast
            errors.append((ticker, repr(exc)[:120]))
            continue
        for row in rows:
            key = (ticker, row.end.isoformat())
            if key not in stored:
                continue
            sa, sl, se, srnci, stemp = stored[key]
            na, nl, ne = row.total_assets, row.total_liabilities, row.total_equity
            nrnci, ntemp = row.redeemable_nci, row.temporary_equity
            cb = closes(sa, sl, se, srnci, stemp)
            ca = closes(na, nl, ne, nrnci, ntemp)
            if cb is False:
                breaks_before.append(key)
            if ca is False:
                breaks_after.append(key)
            if cb is False and ca is True:
                fixed.append(key)
            for label, old, new in (("A", sa, na), ("L", sl, nl),
                                    ("E", se, ne)):
                if old != new and not (
                    old is not None and new is not None
                    and abs(old - new) <= 1.0
                ):
                    leg_changes.append((key, label, old, new))
            for label, old, new in (("rnci", srnci, nrnci),
                                    ("temp", stemp, ntemp)):
                if old != new and not (
                    old is not None and new is not None
                    and abs(old - new) <= 1.0
                ):
                    mezz_changes.append((key, label, old, new))

    print(f"\nErrors: {len(errors)}")
    for e in errors[:10]:
        print("  ", e)
    print(f"\nIdentity breaks BEFORE (stored): {len(breaks_before)}")
    print(f"Identity breaks AFTER (new code): {len(breaks_after)}")
    for k in breaks_after[:20]:
        print("   still broken:", k)
    print(f"Fixed by new code: {len(fixed)}")
    for k in fixed:
        print("   fixed:", k)
    print(f"\nA/L/E leg changes: {len(leg_changes)}")
    for k, label, old, new in leg_changes[:30]:
        print(f"   {k} {label}: {old} -> {new}")
    print(f"\nMezzanine changes: {len(mezz_changes)}")
    for k, label, old, new in mezz_changes:
        print(f"   {k} {label}: {old} -> {new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
