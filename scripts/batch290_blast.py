"""Batch 290 blast: old vs new EPS-clamp predicate over all 303 companies.

For each company: fetch live companyfacts (cached), run the EPS legs
through quarterly_income_metric + _fill_missing_eps_basic (extraction
order), then apply the batch-87 predicate (diluted > basic) and the
batch-290 predicate (diluted > basic OR (basic < 0 AND diluted <
basic)) to the same pre-clamp legs. Report every end where the two
predicates disagree — those are exactly the rows the fix changes.

Also verifies the fixed _reconcile_eps_basic_diluted leaves no
more-extreme diluted leg anywhere in the extracted history.
"""
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient
from tickerlens.data.xbrl import (
    Metric,
    _fill_missing_eps_basic,
    _reconcile_eps_basic_diluted,
    quarterly_income_metric,
)


def old_clamp(basic_val: float, diluted_val: float) -> float:
    return basic_val if diluted_val > basic_val else diluted_val


def new_clamp(basic_val: float, diluted_val: float) -> float:
    if diluted_val > basic_val or (basic_val < 0 and diluted_val < basic_val):
        return basic_val
    return diluted_val


def main() -> int:
    con = sqlite3.connect("tickerlens.db")
    companies = con.execute(
        "SELECT ticker, cik, fiscal_year_end FROM companies ORDER BY ticker"
    ).fetchall()
    con.close()
    client = EdgarClient()
    disagreements = []
    residual_violations = []
    errors = []
    for ticker, cik, fye in companies:
        try:
            facts = client.companyfacts(cik)
            basic = quarterly_income_metric(facts, Metric.EPS_BASIC, fye)
            diluted = quarterly_income_metric(facts, Metric.EPS_DILUTED, fye)
        except Exception as exc:  # noqa: BLE001 - blast must not die on one filer
            errors.append((ticker, repr(exc)))
            continue
        basic = _fill_missing_eps_basic(basic, diluted)
        by_end = {m.end: m for m in basic}
        for m in diluted:
            b = by_end.get(m.end)
            if b is None:
                continue
            o, n = old_clamp(b.value, m.value), new_clamp(b.value, m.value)
            if o != n:
                disagreements.append(
                    (ticker, str(m.end), b.value, m.value, o, n)
                )
        fixed = _reconcile_eps_basic_diluted(basic, diluted)
        for m in fixed:
            b = by_end.get(m.end)
            if b is None:
                continue
            if m.value > b.value or (b.value < 0 and m.value != b.value):
                residual_violations.append((ticker, str(m.end), b.value, m.value))

    print(f"companies scanned: {len(companies)}, errors: {len(errors)}")
    for e in errors:
        print("  ERROR", e)
    print(f"\nold-vs-new predicate disagreements: {len(disagreements)}")
    for d in disagreements:
        print(
            f"  {d[0]} {d[1]}: basic={d[2]} diluted_pre={d[3]} "
            f"old={d[4]} new={d[5]}"
        )
    print(f"\nresidual violations after fixed clamp: {len(residual_violations)}")
    for v in residual_violations:
        print("  VIOLATION", v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
