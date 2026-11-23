"""Batch 289 blast 2: full report to file, mezzanine changes classified
as FILED (a temp/rnci tag has a fact at that end) vs DERIVED (residual).

Reuses the EdgarClient disk cache warmed by batch289_blast.py.
DRY RUN only. Report: scripts/batch289_blast2_report.txt
Usage: .venv/bin/python scripts/batch289_blast2.py
"""
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient, companyfacts_with_predecessors
from tickerlens.data.xbrl import extract_recent_quarterly_financials
from tickerlens.models.quarterly_financial import identity_tolerance

DB = "tickerlens.db"
OUT = "scripts/batch289_blast2_report.txt"
TEMP_TAGS = (
    "TemporaryEquityCarryingAmountAttributableToParent",
    "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests",
)
RNCI_TAGS = ("RedeemableNoncontrollingInterestEquityCarryingAmount",)


def closes(a, l, e, rnci, temp) -> bool | None:
    if None in (a, l, e):
        return None
    return abs(a - l - (rnci or 0) - (temp or 0) - e) <= identity_tolerance(a)


def filed_at(facts: dict, tags: tuple, end: str) -> bool:
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        for f in gaap.get(tag, {}).get("units", {}).get("USD", []):
            if f.get("end") == end and "start" not in f:
                return True
    return False


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
    out = []
    leg_changes, mezz_filed, mezz_derived = [], [], []
    breaks_before, breaks_after, fixed, errors = [], [], [], []

    for ticker, cik, fye, sic in companies:
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
            na, nl, ne = (row.total_assets, row.total_liabilities,
                          row.total_equity)
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
            end = row.end.isoformat()
            for label, old, new, tags in (
                ("rnci", srnci, nrnci, RNCI_TAGS),
                ("temp", stemp, ntemp, TEMP_TAGS),
            ):
                if old != new and not (
                    old is not None and new is not None
                    and abs(old - new) <= 1.0
                ):
                    rec = (key, label, old, new)
                    if filed_at(facts, tags, end):
                        mezz_filed.append(rec)
                    else:
                        mezz_derived.append(rec)

    out.append(f"Errors: {len(errors)}")
    out += [f"  {e}" for e in errors[:10]]
    out.append(f"\nIdentity breaks BEFORE (stored): {len(breaks_before)}")
    out.append(f"Identity breaks AFTER (new code): {len(breaks_after)}")
    out += [f"  still broken: {k}" for k in breaks_after]
    out.append(f"Fixed by new code: {len(fixed)}")
    out += [f"  fixed: {k}" for k in fixed]
    out.append(f"\nA/L/E leg changes: {len(leg_changes)}")
    out += [f"  {k} {lb}: {o} -> {n}" for k, lb, o, n in leg_changes]
    out.append(f"\nMezzanine changes FILED (tag present): {len(mezz_filed)}")
    out += [f"  {k} {lb}: {o} -> {n}" for k, lb, o, n in mezz_filed]
    out.append(f"\nMezzanine changes DERIVED (residual): {len(mezz_derived)}")
    out += [f"  {k} {lb}: {o} -> {n}" for k, lb, o, n in mezz_derived]

    text = "\n".join(out)
    with open(OUT, "w") as fh:
        fh.write(text + "\n")
    print(text[:4000])
    print(f"\n... full report in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
