"""Batch 292 regression tests: middle-quarter derivation + negative guard.

SEC's companyfacts occasionally lacks an entire 10-Q's facts while the
next quarter's filing (with YTD + standalone facts) is present — DOW, ED,
EIX and URI all filed Q2 2026 10-Qs in Jul/Aug 2026 that carry no
companyfacts facts, while their Q3 10-Qs' 9M and Q3-standalone facts are
present. ``_derive_missing_quarters`` recovers the missing quarter as
YTD − Σ(known standalones) (share-implied for EPS), gated on exactly one
missing constituent, the discontinued-ops basis-break guard, month-end
end-date inference, and a negative-revenue abstention.

The same negative-revenue abstention now guards ``_derive_q4_income``:
APLD FY2025 paired a reclassified 10-K annual ($144.2M) with a stale 9M
($177.5M) and fabricated a −$33.3M Q4 revenue. Filers whose tag
genuinely goes negative (mREIT net interest income) file negative
standalones and keep their derived negatives.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.xbrl import (
    Metric,
    XbrlFact,
    _derive_missing_quarters,
    extract_recent_quarterly_financials,
)


def fact(start, end, val, fy, fp, filed="2026-04-22"):
    return {
        "start": start,
        "end": end,
        "val": val,
        "fy": fy,
        "fp": fp,
        "form": "10-Q" if fp != "FY" else "10-K",
        "filed": filed,
    }


def units(unit_name, values):
    return {"units": {unit_name: [fact(*value) for value in values]}}


def make_companyfacts(revenue, net_income, basic_eps, diluted_eps):
    return {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": units("USD", revenue),
                "NetIncomeLoss": units("USD", net_income),
                "EarningsPerShareBasic": units("USD/shares", basic_eps),
                "EarningsPerShareDiluted": units("USD/shares", diluted_eps),
                "NetCashProvidedByUsedInOperatingActivities": units("USD", []),
                "PaymentsToAcquirePropertyPlantAndEquipment": units("USD", []),
            }
        }
    }


def rows_by_end(companyfacts, periods=8):
    rows = extract_recent_quarterly_financials(
        companyfacts, fiscal_year_end="1231", periods=periods
    )
    return {row.end.isoformat(): row for row in rows}


# DOW shape: Q1 + Q3 standalones and the 9M span; Q2's filing is absent
# from companyfacts. Shares are a constant 10 (NI/EPS), so the
# share-implied Q2 EPS is exactly NI_Q2 / 10.
DOW_REVENUE = [
    ("2026-01-01", "2026-03-31", 100.0, 2026, "Q1"),
    ("2026-01-01", "2026-09-30", 600.0, 2026, "Q3"),
    ("2026-07-01", "2026-09-30", 300.0, 2026, "Q3"),
]
DOW_NI = [
    ("2026-01-01", "2026-03-31", 10.0, 2026, "Q1"),
    ("2026-01-01", "2026-09-30", 60.0, 2026, "Q3"),
    ("2026-07-01", "2026-09-30", 30.0, 2026, "Q3"),
]
DOW_EPS = [
    ("2026-01-01", "2026-03-31", 1.0, 2026, "Q1"),
    ("2026-01-01", "2026-09-30", 6.0, 2026, "Q3"),
    ("2026-07-01", "2026-09-30", 3.0, 2026, "Q3"),
]


def test_missing_q2_derived_from_9m_span():
    rows = rows_by_end(make_companyfacts(DOW_REVENUE, DOW_NI, DOW_EPS, DOW_EPS))
    q2 = rows["2026-06-30"]
    assert (q2.fy, q2.fp) == (2026, "Q2")
    assert q2.revenue == 200.0  # 600 − 100 − 300
    assert q2.net_income == 20.0  # 60 − 10 − 30
    assert q2.eps_basic == 2.0  # share-implied: 20 / 10 shares
    assert q2.eps_diluted == 2.0


def test_missing_q2_derived_from_6m_span():
    revenue = [
        ("2026-01-01", "2026-03-31", 100.0, 2026, "Q1"),
        ("2026-01-01", "2026-06-30", 250.0, 2026, "Q2"),
    ]
    ni = [
        ("2026-01-01", "2026-03-31", 10.0, 2026, "Q1"),
        ("2026-01-01", "2026-06-30", 25.0, 2026, "Q2"),
    ]
    eps = [
        ("2026-01-01", "2026-03-31", 1.0, 2026, "Q1"),
        ("2026-01-01", "2026-06-30", 2.5, 2026, "Q2"),
    ]
    rows = rows_by_end(make_companyfacts(revenue, ni, eps, eps))
    q2 = rows["2026-06-30"]
    assert (q2.fy, q2.fp) == (2026, "Q2")
    assert q2.revenue == 150.0
    assert q2.net_income == 15.0
    assert q2.eps_basic == 1.5


def test_missing_q3_derived_as_last_constituent_of_9m_span():
    revenue = [
        ("2026-01-01", "2026-03-31", 100.0, 2026, "Q1"),
        ("2026-04-01", "2026-06-30", 150.0, 2026, "Q2"),
        ("2026-01-01", "2026-09-30", 600.0, 2026, "Q3"),
    ]
    ni = [
        ("2026-01-01", "2026-03-31", 10.0, 2026, "Q1"),
        ("2026-04-01", "2026-06-30", 15.0, 2026, "Q2"),
        ("2026-01-01", "2026-09-30", 60.0, 2026, "Q3"),
    ]
    eps = [
        ("2026-01-01", "2026-03-31", 1.0, 2026, "Q1"),
        ("2026-04-01", "2026-06-30", 1.5, 2026, "Q2"),
        ("2026-01-01", "2026-09-30", 6.0, 2026, "Q3"),
    ]
    rows = rows_by_end(make_companyfacts(revenue, ni, eps, eps))
    q3 = rows["2026-09-30"]
    assert (q3.fy, q3.fp) == (2026, "Q3")
    assert q3.revenue == 350.0
    assert q3.net_income == 35.0
    assert q3.eps_basic == 3.5


def test_two_missing_constituents_abstain():
    revenue = [
        ("2026-01-01", "2026-03-31", 100.0, 2026, "Q1"),
        ("2026-01-01", "2026-09-30", 600.0, 2026, "Q3"),
    ]
    ni = [("2026-01-01", "2026-03-31", 10.0, 2026, "Q1")]
    eps = [("2026-01-01", "2026-03-31", 1.0, 2026, "Q1")]
    rows = rows_by_end(make_companyfacts(revenue, ni, eps, eps))
    assert list(rows) == ["2026-03-31"]


def test_filed_standalone_wins_no_derivation_override():
    revenue = [
        ("2026-01-01", "2026-03-31", 100.0, 2026, "Q1"),
        ("2026-04-01", "2026-06-30", 999.0, 2026, "Q2"),
        ("2026-07-01", "2026-09-30", 300.0, 2026, "Q3"),
        ("2026-01-01", "2026-09-30", 600.0, 2026, "Q3"),
    ]
    ni = [("2026-01-01", "2026-03-31", 10.0, 2026, "Q1")]
    eps = [("2026-01-01", "2026-03-31", 1.0, 2026, "Q1")]
    rows = rows_by_end(make_companyfacts(revenue, ni, eps, eps))
    assert rows["2026-06-30"].revenue == 999.0


def test_negative_derived_q4_revenue_abstains():
    # APLD FY2025 shape: standalones sum to 120, the 9M fact says 177,
    # the 10-K annual says 144 — FY − 9M would fabricate −33.
    revenue = [
        ("2026-01-01", "2026-03-31", 30.0, 2026, "Q1"),
        ("2026-04-01", "2026-06-30", 40.0, 2026, "Q2"),
        ("2026-07-01", "2026-09-30", 50.0, 2026, "Q3"),
        ("2026-01-01", "2026-09-30", 177.0, 2026, "Q3"),
        ("2026-01-01", "2026-12-31", 144.0, 2026, "FY"),
    ]
    ni = [("2026-01-01", "2026-03-31", 10.0, 2026, "Q1")]
    eps = [("2026-01-01", "2026-03-31", 1.0, 2026, "Q1")]
    rows = rows_by_end(make_companyfacts(revenue, ni, eps, eps))
    assert "2026-12-31" not in rows
    assert all(row.revenue >= 0 for row in rows.values())


def test_negative_derived_q4_revenue_allowed_with_negative_standalones():
    # mREIT shape: the tag genuinely goes negative (filed Q1 −10), so a
    # derived negative Q4 is plausible and kept.
    revenue = [
        ("2026-01-01", "2026-03-31", -10.0, 2026, "Q1"),
        ("2026-04-01", "2026-06-30", 20.0, 2026, "Q2"),
        ("2026-07-01", "2026-09-30", 30.0, 2026, "Q3"),
        ("2026-01-01", "2026-09-30", 40.0, 2026, "Q3"),
        ("2026-01-01", "2026-12-31", 30.0, 2026, "FY"),
    ]
    ni = [("2026-01-01", "2026-03-31", 10.0, 2026, "Q1")]
    eps = [("2026-01-01", "2026-03-31", 1.0, 2026, "Q1")]
    rows = rows_by_end(make_companyfacts(revenue, ni, eps, eps))
    assert rows["2026-12-31"].revenue == -10.0


def test_eps_middle_abstains_without_ni_span():
    # Revenue derives Q2, but the NI 9M leg is absent, so the
    # share-implied EPS derivation abstains (never subtraction).
    ni = [
        ("2026-01-01", "2026-03-31", 10.0, 2026, "Q1"),
        ("2026-07-01", "2026-09-30", 30.0, 2026, "Q3"),
    ]
    rows = rows_by_end(make_companyfacts(DOW_REVENUE, ni, DOW_EPS, DOW_EPS))
    q2 = rows["2026-06-30"]
    assert q2.revenue == 200.0
    assert q2.eps_basic is None
    assert q2.eps_diluted is None


def xfact(start, end, val, fy, fp):
    return XbrlFact(
        start=dt.date.fromisoformat(start) if start else None,
        end=dt.date.fromisoformat(end),
        val=val,
        fy=fy,
        fp=fp,
        form="10-Q",
        filed=dt.date(2026, 4, 22),
    )


def test_52_week_filer_abstains_on_inferred_end():
    # Saturday quarter ends: Q2 is the non-last missing constituent, so
    # its end would have to be inferred — abstain.
    facts = [
        xfact("2025-12-28", "2026-03-28", 100.0, 2026, "Q1"),
        xfact("2025-12-28", "2026-09-26", 600.0, 2026, "Q3"),
        xfact("2026-06-28", "2026-09-26", 300.0, 2026, "Q3"),
    ]
    derived = _derive_missing_quarters(facts, "Revenues", Metric.REVENUE, "0926")
    assert derived == []


def test_52_week_filer_derives_last_constituent_with_real_end():
    facts = [
        xfact("2025-12-28", "2026-03-28", 100.0, 2026, "Q1"),
        xfact("2026-03-29", "2026-06-27", 150.0, 2026, "Q2"),
        xfact("2025-12-28", "2026-09-26", 600.0, 2026, "Q3"),
    ]
    derived = _derive_missing_quarters(facts, "Revenues", Metric.REVENUE, "0926")
    assert len(derived) == 1
    assert derived[0].end == dt.date(2026, 9, 26)
    assert derived[0].fp == "Q3"
    assert derived[0].value == 350.0


def test_basis_break_start_skips_middle_derivation():
    facts = [
        xfact("2026-01-01", "2026-03-31", 100.0, 2026, "Q1"),
        xfact("2026-01-01", "2026-09-30", 600.0, 2026, "Q3"),
        xfact("2026-07-01", "2026-09-30", 300.0, 2026, "Q3"),
    ]
    derived = _derive_missing_quarters(
        facts,
        "Revenues",
        Metric.REVENUE,
        "1231",
        basis_break_starts={dt.date(2026, 1, 1)},
    )
    assert derived == []


def test_negative_derived_middle_revenue_abstains():
    facts = [
        xfact("2026-01-01", "2026-03-31", 100.0, 2026, "Q1"),
        xfact("2026-01-01", "2026-09-30", 350.0, 2026, "Q3"),
        xfact("2026-07-01", "2026-09-30", 300.0, 2026, "Q3"),
    ]
    derived = _derive_missing_quarters(facts, "Revenues", Metric.REVENUE, "1231")
    assert derived == []
