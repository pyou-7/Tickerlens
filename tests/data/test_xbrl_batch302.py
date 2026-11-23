"""Batch 302 regression tests: rounding-uncertainty guard on
share-implied EPS derivations.

Filed EPS is rounded to the cent, so an NI/EPS pair implies the share
count only within ±half a cent of EPS. When a leg's EPS is tiny
(near-zero FY net income), that rounding is a huge share-count error
and the share-month residual (12·FY − 9·9M)/3 amplifies it: DraftKings
FY2025 (NI $3.71M, basic EPS $0.01; 9M NI −$132.7M, EPS −$0.27)
derived Q4 basic EPS 14.55 from a 9.4M-share residual against a true
~496M. ``_implied_q4_eps`` / ``_implied_missing_eps`` now reject the
derivation when the residual's rounding interval includes zero or its
relative half-width exceeds 10% (Q4 falls back to subtraction; middle
quarters abstain, as before).
"""
import datetime as dt
import sys

sys.path.insert(0, "src")

from tickerlens.data.xbrl import (
    Metric,
    _implied_shares_interval,
    _residual_shares_reliable,
    extract_recent_quarterly_financials,
    quarterly_income_metric,
)


def fact(start, end, val, fy, fp, filed="2026-02-13"):
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


def eps_by_end(companyfacts, metric):
    return {
        m.end: m.value
        for m in quarterly_income_metric(companyfacts, metric, "1231")
    }


# DraftKings FY2025, verbatim legs (10-K filed 2026-02-13; 10-Qs
# 2025-05-09 / 2025-08-07 / 2025-11-07). FY net income is $3.71M, so
# FY basic EPS rounds to $0.01 and NI/EPS implies 371M shares against
# the filed 495.6M weighted average.
DKNG_NI = [
    ("2025-01-01", "2025-03-31", -33_864_000, 2025, "Q1"),
    ("2025-04-01", "2025-06-30", 157_936_000, 2025, "Q2"),
    ("2025-07-01", "2025-09-30", -256_788_000, 2025, "Q3"),
    ("2025-01-01", "2025-09-30", -132_716_000, 2025, "Q3"),
    ("2025-01-01", "2025-12-31", 3_710_000, 2025, "FY"),
]
DKNG_BASIC = [
    ("2025-01-01", "2025-03-31", -0.07, 2025, "Q1"),
    ("2025-04-01", "2025-06-30", 0.32, 2025, "Q2"),
    ("2025-07-01", "2025-09-30", -0.52, 2025, "Q3"),
    ("2025-01-01", "2025-09-30", -0.27, 2025, "Q3"),
    ("2025-01-01", "2025-12-31", 0.01, 2025, "FY"),
]
DKNG_DILUTED = [
    ("2025-01-01", "2025-03-31", -0.07, 2025, "Q1"),
    ("2025-04-01", "2025-06-30", 0.30, 2025, "Q2"),
    ("2025-07-01", "2025-09-30", -0.52, 2025, "Q3"),
    ("2025-01-01", "2025-09-30", -0.27, 2025, "Q3"),
    ("2025-01-01", "2025-12-31", -0.01, 2025, "FY"),
]


def test_q4_eps_near_zero_fy_income_falls_back_to_subtraction():
    # Pre-fix: Q4 basic EPS derived 14.5478 (Q4 NI $136.4M over a
    # 9.4M-share residual). The residual's rounding interval spans
    # zero, so the derivation is rejected and subtraction yields the
    # filer's own FY − 9M arithmetic: 0.01 − (−0.27) = 0.28 basic,
    # −0.01 − (−0.27) = 0.26 diluted (filed-share-count truth ≈ 0.275).
    facts = make_companyfacts([], DKNG_NI, DKNG_BASIC, DKNG_DILUTED)
    q4 = dt.date(2025, 12, 31)
    assert eps_by_end(facts, Metric.EPS_BASIC)[q4] == 0.28
    assert eps_by_end(facts, Metric.EPS_DILUTED)[q4] == 0.26


def test_q4_eps_tight_interval_still_share_implied():
    # Share drift with precise EPS legs: FY 240M/2.00 = 120M shares,
    # 9M 160M/1.60 = 100M; residual 180M, Q4 NI 80M -> 0.4444.
    # Subtraction would give 0.40; the interval is ~1% wide, so the
    # share-implied value stands.
    ni = [
        ("2025-01-01", "2025-09-30", 160_000_000, 2025, "Q3"),
        ("2025-01-01", "2025-12-31", 240_000_000, 2025, "FY"),
    ]
    basic = [
        ("2025-01-01", "2025-09-30", 1.60, 2025, "Q3"),
        ("2025-01-01", "2025-12-31", 2.00, 2025, "FY"),
    ]
    facts = make_companyfacts([], ni, basic, [])
    assert eps_by_end(facts, Metric.EPS_BASIC)[dt.date(2025, 12, 31)] == 0.4444


def test_q4_eps_wide_interval_falls_back():
    # FY EPS $0.02 on $10M NI implies 500M shares ±25%; the residual
    # interval is ~86% wide even though the FY/9M averages look
    # coherent (11% apart) — the rounding guard, not the coherence
    # check, must catch it. Fallback: 0.02 − 0.30 = −0.28.
    ni = [
        ("2025-01-01", "2025-09-30", 135_000_000, 2025, "Q3"),
        ("2025-01-01", "2025-12-31", 10_000_000, 2025, "FY"),
    ]
    basic = [
        ("2025-01-01", "2025-09-30", 0.30, 2025, "Q3"),
        ("2025-01-01", "2025-12-31", 0.02, 2025, "FY"),
    ]
    facts = make_companyfacts([], ni, basic, [])
    assert eps_by_end(facts, Metric.EPS_BASIC)[dt.date(2025, 12, 31)] == -0.28


def test_middle_eps_abstains_on_rounding_garbage():
    # 6M span, Q2 missing. Point-implied shares are a coherent 100
    # (Q1: 2/0.02, H1: 3/0.03), but both legs' EPS are tiny, so the
    # residual interval is ~61% wide — EPS abstains while the dollar
    # metrics still derive.
    revenue = [
        ("2026-01-01", "2026-03-31", 100.0, 2026, "Q1"),
        ("2026-01-01", "2026-06-30", 250.0, 2026, "Q2"),
    ]
    ni = [
        ("2026-01-01", "2026-03-31", 2.0, 2026, "Q1"),
        ("2026-01-01", "2026-06-30", 3.0, 2026, "Q2"),
    ]
    eps = [
        ("2026-01-01", "2026-03-31", 0.02, 2026, "Q1"),
        ("2026-01-01", "2026-06-30", 0.03, 2026, "Q2"),
    ]
    rows = {
        r.end.isoformat(): r
        for r in extract_recent_quarterly_financials(
            make_companyfacts(revenue, ni, eps, eps),
            fiscal_year_end="1231", periods=8)
    }
    q2 = rows["2026-06-30"]
    assert q2.revenue == 150.0
    assert q2.net_income == 1.0
    assert q2.eps_basic is None
    assert q2.eps_diluted is None


def test_middle_eps_precise_legs_still_derive():
    # Control: same 6M shape with cent-precise EPS legs at scale —
    # residual interval ~1% wide, derivation proceeds.
    revenue = [
        ("2026-01-01", "2026-03-31", 100.0, 2026, "Q1"),
        ("2026-01-01", "2026-06-30", 250.0, 2026, "Q2"),
    ]
    ni = [
        ("2026-01-01", "2026-03-31", 100.0, 2026, "Q1"),
        ("2026-01-01", "2026-06-30", 150.0, 2026, "Q2"),
    ]
    eps = [
        ("2026-01-01", "2026-03-31", 1.0, 2026, "Q1"),
        ("2026-01-01", "2026-06-30", 1.5, 2026, "Q2"),
    ]
    rows = {
        r.end.isoformat(): r
        for r in extract_recent_quarterly_financials(
            make_companyfacts(revenue, ni, eps, eps),
            fiscal_year_end="1231", periods=8)
    }
    assert rows["2026-06-30"].eps_basic == 0.5  # Q2 NI 50 / 100 shares


def test_implied_shares_interval():
    lo, hi = _implied_shares_interval(100.0, 2.00)
    assert abs(lo - 100 / 2.005) < 1e-9
    assert abs(hi - 100 / 1.995) < 1e-9
    # Trailing-zero float (filed 0.10 -> 0.1) floors at 2dp precision.
    lo, hi = _implied_shares_interval(10.0, 0.1)
    assert abs(lo - 10 / 0.105) < 1e-9
    assert abs(hi - 10 / 0.095) < 1e-9
    # Negative pair: interval stays positive and ordered.
    lo, hi = _implied_shares_interval(-132_716_000.0, -0.27)
    assert 0 < lo < hi
    # Zero EPS -> unbounded.
    assert _implied_shares_interval(100.0, 0.0) is None


def test_residual_shares_reliable():
    assert _residual_shares_reliable(100.0, 99.0, 101.0)
    assert not _residual_shares_reliable(100.0, -5.0, 205.0)  # spans zero
    assert not _residual_shares_reliable(100.0, 50.0, 150.0)  # 50% wide
    assert not _residual_shares_reliable(0.0, 0.0, 1.0)
    assert not _residual_shares_reliable(-10.0, -20.0, -1.0)
