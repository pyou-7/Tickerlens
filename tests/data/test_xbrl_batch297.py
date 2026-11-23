"""Batch 297 regression tests: stale gap-fill tags that fill an interior
hole in the winner's coverage are admitted regardless of lag.

The 365-day ``_GAP_FILL_MAX_STALENESS_DAYS`` gate measures a tail tag's
newest fact against the chain's freshest. For a mid-history tag switch the
lag grows without bound as the winner advances, so the gate eventually
revokes fills that were correct when seeded:

- Halliburton cash: ``CashAndCashEquivalentsAtCarryingValue`` (newest
  2026-09-30) lacks 2024-09-30 / 2025-03-31 / 2025-06-30; the restricted
  composite (newest 2025-06-30, 457 days behind) has all three. Stored
  2024-09-30 ($2,178M) became irreproducible; 2025 Q1/Q2 rendered "—".
- Entergy revenue: ``Revenues`` eras flank a 2018-2023 hole filed under
  the contract tag (newest 2024-09-30 vs winner 2026-03-31, 547 days).
- Alphabet revenue: same shape, 2021-2023 hole (548 days).

``_chain_candidates`` now also admits a stale tag when it has facts at
ends strictly inside the winner's coverage that the winner lacks (the
tag-switch signature). A merely ancient tag whose ends only predate or
overlap the winner's coverage stays excluded.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.xbrl import (
    CONCEPTS,
    Metric,
    XbrlFact,
    _QUARTERLY_FACT_WINDOW,
    _chain_candidates,
    _window_ends,
    balance_sheet_metric,
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


def instant(end, val, fy, fp, filed):
    return {
        "end": end,
        "val": val,
        "fy": fy,
        "fp": fp,
        "form": "10-Q" if fp != "FY" else "10-K",
        "filed": filed,
    }


def hal_cash_facts():
    """HAL shape: winner cash tag skips interior ends the stale composite has."""
    return {
        "facts": {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {
                        "USD": [
                            instant("2024-12-31", 2_618_000_000, 2024, "FY", "2025-02-12"),
                            instant("2025-09-30", 2_026_000_000, 2025, "Q3", "2025-10-24"),
                            instant("2025-12-31", 2_206_000_000, 2025, "FY", "2026-02-06"),
                            instant("2026-09-30", 1_843_000_000, 2026, "Q3", "2026-10-23"),
                        ]
                    }
                },
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": {
                    "units": {
                        "USD": [
                            instant("2024-09-30", 2_178_000_000, 2024, "Q3", "2024-11-07"),
                            instant("2024-12-31", 2_618_000_000, 2024, "FY", "2025-02-12"),
                            instant("2025-03-31", 1_804_000_000, 2025, "Q1", "2025-04-25"),
                            instant("2025-06-30", 2_038_000_000, 2025, "Q2", "2025-07-25"),
                        ]
                    }
                },
            }
        }
    }


def etr_revenue_facts():
    """ETR shape: Revenues eras flank a contract-tag hole (values scaled)."""
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            fact("2018-04-01", "2018-06-30", 2668.0, 2018, "Q2", "2018-08-01"),
                            fact("2023-07-01", "2023-09-30", 3595.0, 2023, "Q3", "2023-11-01"),
                            fact("2023-10-01", "2023-12-31", 2724.0, 2023, "Q4", "2024-02-20"),
                            fact("2026-01-01", "2026-03-31", 3187.0, 2026, "Q1", "2026-04-30"),
                        ]
                    }
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            fact("2018-07-01", "2018-09-30", 3104.0, 2018, "Q3", "2018-11-06"),
                            fact("2018-10-01", "2018-12-31", 2512.0, 2018, "Q4", "2019-02-26"),
                            fact("2023-04-01", "2023-06-30", 2846.0, 2023, "Q2", "2023-08-01"),
                            fact("2024-07-01", "2024-09-30", 3389.0, 2024, "Q3", "2024-11-01"),
                        ]
                    }
                },
            }
        }
    }


def test_hal_cash_stale_composite_admitted_and_fills_interior_ends():
    facts = hal_cash_facts()
    spec = CONCEPTS[Metric.CASH_AND_EQUIVALENTS]
    cands = _chain_candidates(
        facts, spec.tags, spec.unit, instant=True, metric_name="cash"
    )
    assert [t for t, _ in cands] == [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ]
    cash = balance_sheet_metric(facts, Metric.CASH_AND_EQUIVALENTS)
    # Interior ends only the stale composite has are filled...
    assert cash[dt.date(2024, 9, 30)] == 2_178_000_000
    assert cash[dt.date(2025, 3, 31)] == 1_804_000_000
    assert cash[dt.date(2025, 6, 30)] == 2_038_000_000
    # ...and winner-supplied ends are unchanged.
    assert cash[dt.date(2024, 12, 31)] == 2_618_000_000
    assert cash[dt.date(2026, 9, 30)] == 1_843_000_000


def test_etr_revenue_stale_contract_tag_admitted_and_fills_hole():
    facts = etr_revenue_facts()
    spec = CONCEPTS[Metric.REVENUE]
    cands = _chain_candidates(
        facts,
        spec.tags,
        spec.unit,
        staleness_window=_QUARTERLY_FACT_WINDOW,
        metric_name="revenue",
    )
    assert [t for t, _ in cands] == [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
    ]
    series = quarterly_income_metric(facts, Metric.REVENUE, None)
    by_end = {p.end: p for p in series}
    assert by_end[dt.date(2018, 9, 30)].value == 3104.0
    assert by_end[dt.date(2018, 9, 30)].source_tag == (
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    )
    assert by_end[dt.date(2023, 6, 30)].value == 2846.0
    # Winner ends keep the winner's values.
    assert by_end[dt.date(2023, 9, 30)].value == 3595.0
    assert by_end[dt.date(2023, 9, 30)].source_tag == "Revenues"


def test_ancient_tag_without_interior_hole_stays_excluded():
    """Insurer guard: a stale tag whose ends only predate the winner's
    coverage (no interior hole) is still excluded by the 365-day gate."""
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            fact("2024-01-01", "2024-03-31", 100.0, 2024, "Q1", "2024-04-30"),
                            fact("2026-01-01", "2026-03-31", 120.0, 2026, "Q1", "2026-04-30"),
                        ]
                    }
                },
                "SalesRevenueNet": {
                    "units": {
                        "USD": [
                            fact("2019-01-01", "2019-03-31", 90.0, 2019, "Q1", "2019-04-30"),
                            fact("2020-01-01", "2020-03-31", 95.0, 2020, "Q1", "2020-04-30"),
                        ]
                    }
                },
            }
        }
    }
    spec = CONCEPTS[Metric.REVENUE]
    cands = _chain_candidates(
        facts,
        spec.tags,
        spec.unit,
        staleness_window=_QUARTERLY_FACT_WINDOW,
        metric_name="revenue",
    )
    assert [t for t, _ in cands] == ["Revenues"]


def test_window_ends_duration_rules():
    facts = [
        XbrlFact.model_validate(fact("2026-01-01", "2026-03-31", 1.0, 2026, "Q1", "2026-04-30")),
        XbrlFact.model_validate(fact("2026-01-01", "2026-12-31", 4.0, 2026, "FY", "2027-02-01")),
        XbrlFact.model_validate(instant("2026-06-30", 2.0, 2026, "Q2", "2026-07-30")),
    ]
    assert _window_ends(facts, _QUARTERLY_FACT_WINDOW) == {dt.date(2026, 3, 31)}
    assert _window_ends(facts, None) == {
        dt.date(2026, 3, 31),
        dt.date(2026, 12, 31),
        dt.date(2026, 6, 30),
    }
