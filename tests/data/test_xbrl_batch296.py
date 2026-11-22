"""Batch 296 regression tests: Undistributed EPS must never win on freshness.

Northern Trust filed generic ``EarningsPerShareBasic/Diluted`` through
Q1 2026 (newest quarterly end 2026-03-31), then tagged Q2/Q3 2026 EPS
only under the ``...Undistributed`` tags (newest 2026-09-30). The
183-day lag exceeds the 180-day abandonment threshold, so
``_chain_candidates`` crowned the sparse 8-fact Undistributed tag over
the dense 213-fact generic tag. As winner, its share-implied middle
derivations (Q1 2025: 1.9144 basic / 1.9045 diluted; Q1 2026: 2.7413 /
2.7228) blocked the generic tag's filed values (1.91 / 1.90; 2.72 /
2.71) in the gap-fill merge — approximations displacing reported EPS
on the same definition, violating the batch-66 gap-fill-only design.

``_demote_undistributed_eps_winner`` moves Undistributed to the tail
whenever the generic tag is also a candidate; a filer with no generic
candidate keeps Undistributed as winner.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.xbrl import (
    Metric,
    XbrlFact,
    _demote_undistributed_eps_winner,
    extract_recent_quarterly_financials,
    quarterly_income_metric,
)


def fact(start, end, val, fy, fp, filed):
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


def ntrs_shape_companyfacts():
    """NTRS Q1 2025–Q3 2026 shape with real values (see module docstring).

    Generic EPS stops at Q1 2026; Undistributed carries the 2025
    comparatives plus Q2/Q3 2026. NI standalones + YTDs are included
    so the share-implied middle derivation *would* fire for the
    Undistributed tag pre-fix (reproducing 1.9144 / 2.7413).
    """
    revenue = [
        ("2025-01-01", "2025-03-31", 2_000_000_000, 2025, "Q1", "2025-04-30"),
        ("2025-04-01", "2025-06-30", 2_100_000_000, 2025, "Q2", "2025-07-30"),
        ("2025-07-01", "2025-09-30", 2_200_000_000, 2025, "Q3", "2025-10-30"),
        ("2025-10-01", "2025-12-31", 2_300_000_000, 2025, "Q4", "2026-02-24"),
        ("2026-01-01", "2026-03-31", 2_205_600_000, 2026, "Q1", "2026-04-30"),
        ("2026-04-01", "2026-06-30", 2_698_000_000, 2026, "Q2", "2026-07-30"),
        ("2026-07-01", "2026-09-30", 2_400_000_000, 2026, "Q3", "2026-10-29"),
    ]
    net_income = [
        ("2025-01-01", "2025-03-31", 392_000_000, 2025, "Q1", "2025-04-30"),
        ("2025-04-01", "2025-06-30", 421_300_000, 2025, "Q2", "2025-07-30"),
        ("2025-01-01", "2025-06-30", 813_300_000, 2025, "Q2", "2025-07-30"),
        ("2025-07-01", "2025-09-30", 457_600_000, 2025, "Q3", "2025-10-30"),
        ("2025-01-01", "2025-09-30", 1_270_900_000, 2025, "Q3", "2025-10-30"),
        ("2025-01-01", "2025-12-31", 1_736_900_000, 2025, "FY", "2026-02-24"),
        ("2026-01-01", "2026-03-31", 525_500_000, 2026, "Q1", "2026-04-30"),
        ("2026-04-01", "2026-06-30", 792_200_000, 2026, "Q2", "2026-07-30"),
        ("2026-01-01", "2026-06-30", 1_317_700_000, 2026, "Q2", "2026-07-30"),
        ("2026-07-01", "2026-09-30", 642_900_000, 2026, "Q3", "2026-10-29"),
        ("2026-01-01", "2026-09-30", 1_960_600_000, 2026, "Q3", "2026-10-29"),
    ]
    basic_eps = [
        ("2025-01-01", "2025-03-31", 1.91, 2025, "Q1", "2025-04-30"),
        ("2025-04-01", "2025-06-30", 2.14, 2025, "Q2", "2025-07-30"),
        ("2025-01-01", "2025-06-30", 4.05, 2025, "Q2", "2025-07-30"),
        ("2025-07-01", "2025-09-30", 2.30, 2025, "Q3", "2025-10-30"),
        ("2025-01-01", "2025-09-30", 6.34, 2025, "Q3", "2025-10-30"),
        ("2025-01-01", "2025-12-31", 8.78, 2025, "FY", "2026-02-24"),
        ("2026-01-01", "2026-03-31", 2.72, 2026, "Q1", "2026-04-30"),
    ]
    diluted_eps = [
        ("2025-01-01", "2025-03-31", 1.90, 2025, "Q1", "2025-04-30"),
        ("2025-04-01", "2025-06-30", 2.13, 2025, "Q2", "2025-07-30"),
        ("2025-01-01", "2025-06-30", 4.03, 2025, "Q2", "2025-07-30"),
        ("2025-07-01", "2025-09-30", 2.29, 2025, "Q3", "2025-10-30"),
        ("2025-01-01", "2025-09-30", 6.32, 2025, "Q3", "2025-10-30"),
        ("2025-01-01", "2025-12-31", 8.74, 2025, "FY", "2026-02-24"),
        ("2026-01-01", "2026-03-31", 2.71, 2026, "Q1", "2026-04-30"),
    ]
    undistributed_basic = [
        ("2025-01-01", "2025-06-30", 4.05, 2026, "Q2", "2026-07-30"),
        ("2025-04-01", "2025-06-30", 2.14, 2026, "Q2", "2026-07-30"),
        ("2025-01-01", "2025-09-30", 6.34, 2026, "Q3", "2026-10-29"),
        ("2025-07-01", "2025-09-30", 2.30, 2026, "Q3", "2026-10-29"),
        ("2026-01-01", "2026-06-30", 6.97, 2026, "Q2", "2026-07-30"),
        ("2026-04-01", "2026-06-30", 4.25, 2026, "Q2", "2026-07-30"),
        ("2026-01-01", "2026-09-30", 10.38, 2026, "Q3", "2026-10-29"),
        ("2026-07-01", "2026-09-30", 3.42, 2026, "Q3", "2026-10-29"),
    ]
    undistributed_diluted = [
        ("2025-01-01", "2025-06-30", 4.03, 2026, "Q2", "2026-07-30"),
        ("2025-04-01", "2025-06-30", 2.13, 2026, "Q2", "2026-07-30"),
        ("2025-01-01", "2025-09-30", 6.32, 2026, "Q3", "2026-10-29"),
        ("2025-07-01", "2025-09-30", 2.29, 2026, "Q3", "2026-10-29"),
        ("2026-01-01", "2026-06-30", 6.93, 2026, "Q2", "2026-07-30"),
        ("2026-04-01", "2026-06-30", 4.23, 2026, "Q2", "2026-07-30"),
        ("2026-01-01", "2026-09-30", 10.33, 2026, "Q3", "2026-10-29"),
        ("2026-07-01", "2026-09-30", 3.40, 2026, "Q3", "2026-10-29"),
    ]
    return {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": units("USD", revenue),
                "NetIncomeLoss": units("USD", net_income),
                "EarningsPerShareBasic": units("USD/shares", basic_eps),
                "EarningsPerShareDiluted": units("USD/shares", diluted_eps),
                "EarningsPerShareBasicUndistributed": units("USD/shares", undistributed_basic),
                "EarningsPerShareDilutedUndistributed": units("USD/shares", undistributed_diluted),
                "NetCashProvidedByUsedInOperatingActivities": units("USD", []),
                "PaymentsToAcquirePropertyPlantAndEquipment": units("USD", []),
            }
        }
    }


def test_undistributed_never_wins_over_generic_on_freshness() -> None:
    companyfacts = ntrs_shape_companyfacts()
    basic = {m.end: m for m in quarterly_income_metric(companyfacts, Metric.EPS_BASIC, "1231")}
    diluted = {
        m.end: m for m in quarterly_income_metric(companyfacts, Metric.EPS_DILUTED, "1231")
    }
    q1_25, q1_26 = dt.date(2025, 3, 31), dt.date(2026, 3, 31)
    q2_26, q3_26 = dt.date(2026, 6, 30), dt.date(2026, 9, 30)
    # Filed generic values win — not the Undistributed share-implied
    # derivations (1.9144 / 2.7413 basic, 1.9045 / 2.7228 diluted).
    assert basic[q1_25].value == 1.91
    assert basic[q1_25].source_tag == "EarningsPerShareBasic"
    assert basic[q1_26].value == 2.72
    assert basic[q1_26].source_tag == "EarningsPerShareBasic"
    assert diluted[q1_25].value == 1.90
    assert diluted[q1_25].source_tag == "EarningsPerShareDiluted"
    assert diluted[q1_26].value == 2.71
    assert diluted[q1_26].source_tag == "EarningsPerShareDiluted"
    # Undistributed still gap-fills the quarters generic lacks.
    assert basic[q2_26].value == 4.25
    assert basic[q2_26].source_tag == "EarningsPerShareBasicUndistributed"
    assert basic[q3_26].value == 3.42
    assert basic[q3_26].source_tag == "EarningsPerShareBasicUndistributed"
    assert diluted[q2_26].value == 4.23
    assert diluted[q3_26].value == 3.40


def test_ntrs_shape_end_to_end() -> None:
    rows = extract_recent_quarterly_financials(
        ntrs_shape_companyfacts(), fiscal_year_end="1231", periods=12
    )
    by_end = {r.end: r for r in rows}
    assert by_end[dt.date(2025, 3, 31)].eps_basic == 1.91
    assert by_end[dt.date(2025, 3, 31)].eps_diluted == 1.90
    assert by_end[dt.date(2026, 3, 31)].eps_basic == 2.72
    assert by_end[dt.date(2026, 3, 31)].eps_diluted == 2.71
    assert by_end[dt.date(2026, 6, 30)].eps_basic == 4.25
    assert by_end[dt.date(2026, 6, 30)].eps_diluted == 4.23
    assert by_end[dt.date(2026, 9, 30)].eps_basic == 3.42
    assert by_end[dt.date(2026, 9, 30)].eps_diluted == 3.40


def test_undistributed_still_wins_when_generic_absent() -> None:
    # A filer tagging EPS only as Undistributed keeps it as winner —
    # demotion applies only when the generic tag is also a candidate.
    companyfacts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": units(
                    "USD",
                    [("2026-01-01", "2026-03-31", 1_000_000_000, 2026, "Q1", "2026-04-30")],
                ),
                "NetIncomeLoss": units(
                    "USD",
                    [("2026-01-01", "2026-03-31", 100_000_000, 2026, "Q1", "2026-04-30")],
                ),
                "EarningsPerShareBasicUndistributed": units(
                    "USD/shares",
                    [("2026-01-01", "2026-03-31", 1.50, 2026, "Q1", "2026-04-30")],
                ),
                "NetCashProvidedByUsedInOperatingActivities": units("USD", []),
                "PaymentsToAcquirePropertyPlantAndEquipment": units("USD", []),
            }
        }
    }
    series = quarterly_income_metric(companyfacts, Metric.EPS_BASIC, "1231")
    assert len(series) == 1
    assert series[0].value == 1.50
    assert series[0].source_tag == "EarningsPerShareBasicUndistributed"


def _candidate(tag: str) -> tuple[str, list[XbrlFact]]:
    return (tag, [])


def test_demote_helper_cases() -> None:
    undistributed = _candidate("EarningsPerShareBasicUndistributed")
    generic = _candidate("EarningsPerShareBasic")
    # Undistributed winner + generic present -> demoted to tail.
    assert _demote_undistributed_eps_winner(
        [undistributed, generic], Metric.EPS_BASIC
    ) == [generic, undistributed]
    # Generic already winner -> unchanged.
    assert _demote_undistributed_eps_winner(
        [generic, undistributed], Metric.EPS_BASIC
    ) == [generic, undistributed]
    # Sole Undistributed candidate -> unchanged (still wins).
    assert _demote_undistributed_eps_winner(
        [undistributed], Metric.EPS_BASIC
    ) == [undistributed]
    # Undistributed winner without generic (per-unit tail) -> unchanged.
    per_unit = _candidate("NetIncomeLossPerOutstandingLimitedPartnershipUnitBasicNetOfTax")
    assert _demote_undistributed_eps_winner(
        [undistributed, per_unit], Metric.EPS_BASIC
    ) == [undistributed, per_unit]
    # Non-EPS metric -> unchanged.
    assert _demote_undistributed_eps_winner(
        [undistributed, generic], Metric.NET_INCOME
    ) == [undistributed, generic]
