"""Batch 300 regression tests: comparative-only label inheritance.

A period that only ever appeared as a comparative column in a later
filing inherits that filing's ``fy`` (Circle's pre-IPO quarters, first
carried by its 2025 10-Qs with fy=2025; GOOGL/AWK/ETR quarters under a
revenue tag the filer adopted later). The inherited chain is uniformly
one year high yet internally consistent, so ``_dedupe_period_labels``
read each correct later claim as one year behind its expectation and
relabeled the *correct* rows forward (CRCL's Sep-2026 quarter rendered
"FY2027 Q3" at periods=12). Filing lag breaks the tie: a period first
appearing >270 days after its end was never carried by an original
filing, so its fy is the inherited one.

Fix: ``first_filed`` provenance threaded from ``_choose_fact_for_end``
through ``PeriodMetric`` to the revenue-anchored rows; dedupe forces
the legacy walk-back when the earlier end is comparative-only and the
later end prompt; ``_repair_sequence_breaks`` may walk comparative-only
rows from a promptly-filed backbone without a strict majority (closes
the Q1 swaps dedupe's walk-back overshoot leaves behind).
"""
import datetime as dt
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.xbrl import (
    QuarterlyFinancials,
    _dedupe_period_labels,
    _label_lag_days,
    _repair_sequence_breaks,
    extract_recent_quarterly_financials,
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


# Circle (CRCL) Revenues facts, verbatim from live companyfacts
# (probe 2026-11-22): pre-IPO periods exist only as comparatives in
# 2025/2026 filings; Q2/Q3 2025 also have originals (fy=2025).
CRCL_REVENUE = [
    ("2023-01-01", "2023-12-31", 1450466000.0, 2025, "FY", "2026-03-09"),
    ("2024-01-01", "2024-06-30", 795124000.0, 2025, "Q2", "2025-08-12"),
    ("2024-04-01", "2024-06-30", 430030000.0, 2025, "Q2", "2025-08-12"),
    ("2024-01-01", "2024-09-30", 1240886000.0, 2025, "Q3", "2025-11-12"),
    ("2024-07-01", "2024-09-30", 445762000.0, 2025, "Q3", "2025-11-12"),
    ("2024-01-01", "2024-12-31", 1676253000.0, 2025, "FY", "2026-03-09"),
    ("2025-01-01", "2025-03-31", 578573000.0, 2026, "Q1", "2026-05-11"),
    ("2025-01-01", "2025-06-30", 1236651000.0, 2025, "Q2", "2025-08-12"),
    ("2025-04-01", "2025-06-30", 658078000.0, 2025, "Q2", "2025-08-12"),
    ("2025-01-01", "2025-06-30", 1236651000.0, 2026, "Q2", "2026-08-05"),
    ("2025-04-01", "2025-06-30", 658078000.0, 2026, "Q2", "2026-08-05"),
    ("2025-01-01", "2025-09-30", 1976410000.0, 2025, "Q3", "2025-11-12"),
    ("2025-07-01", "2025-09-30", 739759000.0, 2025, "Q3", "2025-11-12"),
    ("2025-01-01", "2025-09-30", 1976410000.0, 2026, "Q3", "2026-11-04"),
    ("2025-07-01", "2025-09-30", 739759000.0, 2026, "Q3", "2026-11-04"),
    ("2025-01-01", "2025-12-31", 2746642000.0, 2025, "FY", "2026-03-09"),
    ("2026-01-01", "2026-03-31", 694133000.0, 2026, "Q1", "2026-05-11"),
    ("2026-01-01", "2026-06-30", 1395448000.0, 2026, "Q2", "2026-08-05"),
    ("2026-04-01", "2026-06-30", 701315000.0, 2026, "Q2", "2026-08-05"),
    ("2026-01-01", "2026-09-30", 2260336000.0, 2026, "Q3", "2026-11-04"),
    ("2026-07-01", "2026-09-30", 864888000.0, 2026, "Q3", "2026-11-04"),
]


def crcl_companyfacts():
    ni = [(s, e, v / 10, fy, fp, f) for (s, e, v, fy, fp, f) in CRCL_REVENUE]
    eps = [(s, e, 1.0, fy, fp, f) for (s, e, v, fy, fp, f) in CRCL_REVENUE]
    return {
        "facts": {
            "us-gaap": {
                "Revenues": units("USD", CRCL_REVENUE),
                "NetIncomeLoss": units("USD", ni),
                "EarningsPerShareBasic": units("USD/shares", eps),
                "EarningsPerShareDiluted": units("USD/shares", eps),
                "NetCashProvidedByUsedInOperatingActivities": units("USD", []),
                "PaymentsToAcquirePropertyPlantAndEquipment": units("USD", []),
            }
        }
    }


def test_crcl_comparative_only_history_labels_calendar_true():
    rows = extract_recent_quarterly_financials(
        crcl_companyfacts(), fiscal_year_end="1231", periods=12, sic="6199"
    )
    by_end = {row.end.isoformat(): row for row in rows}
    expected = {
        "2024-03-31": (2024, "Q1"),
        "2024-06-30": (2024, "Q2"),
        "2024-09-30": (2024, "Q3"),
        "2024-12-31": (2024, "Q4"),
        "2025-03-31": (2025, "Q1"),
        "2025-06-30": (2025, "Q2"),
        "2025-09-30": (2025, "Q3"),
        "2025-12-31": (2025, "Q4"),
        "2026-03-31": (2026, "Q1"),
        "2026-06-30": (2026, "Q2"),
        "2026-09-30": (2026, "Q3"),
    }
    assert {end: (r.fy, r.fp) for end, r in by_end.items()} == expected
    # Values are the filed standalones / derivations, untouched.
    assert by_end["2024-03-31"].revenue == 365094000.0  # 6M − Q2
    assert by_end["2024-12-31"].revenue == 435367000.0  # FY − 9M
    assert by_end["2026-09-30"].revenue == 864888000.0
    # Provenance: the 2024-06-30 quarter first appeared in the Q2-2025
    # 10-Q comparative; the 2025-06-30 quarter in its own 10-Q.
    assert by_end["2024-06-30"].first_filed == dt.date(2025, 8, 12)
    assert by_end["2025-06-30"].first_filed == dt.date(2025, 8, 12)
    assert _label_lag_days(by_end["2024-06-30"]) > 270
    assert _label_lag_days(by_end["2025-06-30"]) <= 270


def _row(fy, fp, end, first_filed=None):
    return QuarterlyFinancials(
        fy=fy, fp=fp, end=end, revenue=1.0, first_filed=first_filed
    )


def test_dedupe_comparative_only_earlier_walks_back_despite_stale_signature():
    """CRCL's Q2 collision in miniature: the comparative-only 2024 chain
    is grounded, and the correct 2025 claim matches the stale-fy
    signature — without the lag guard dedupe relabels the correct row
    forward to FY2026 Q2."""
    rows = [
        _row(2025, "Q1", dt.date(2024, 3, 31), dt.date(2025, 8, 12)),
        _row(2025, "Q2", dt.date(2024, 6, 30), dt.date(2025, 8, 12)),
        _row(2026, "Q1", dt.date(2025, 3, 31), dt.date(2026, 5, 11)),
        _row(2025, "Q2", dt.date(2025, 6, 30), dt.date(2025, 8, 12)),
    ]
    fixed = _dedupe_period_labels(rows)
    by_end = {r.end: (r.fy, r.fp) for r in fixed}
    assert by_end[dt.date(2024, 6, 30)] == (2024, "Q2")
    assert by_end[dt.date(2025, 6, 30)] == (2025, "Q2")
    assert len({(r.fy, r.fp) for r in fixed}) == len(fixed)


def test_dedupe_both_prompt_stale_signature_still_relabels_later():
    """MTD's shape with prompt filing lags: the batch-291 stale-fy
    arbitration is unchanged when both ends were filed promptly."""
    rows = [
        _row(2024, "Q4", dt.date(2024, 12, 31), dt.date(2025, 2, 20)),
        _row(2024, "Q1", dt.date(2025, 3, 31), dt.date(2025, 5, 5)),  # stale fy
        _row(2024, "Q2", dt.date(2025, 6, 30), dt.date(2025, 8, 4)),  # stale fy
        _row(2025, "Q3", dt.date(2025, 9, 30), dt.date(2025, 11, 3)),  # correct
        _row(2025, "Q4", dt.date(2025, 12, 31), dt.date(2026, 2, 19)),
        _row(2026, "Q1", dt.date(2026, 3, 31), dt.date(2026, 5, 4)),
        _row(2026, "Q2", dt.date(2026, 6, 30), dt.date(2026, 8, 3)),
        _row(2025, "Q3", dt.date(2026, 9, 30), dt.date(2026, 11, 2)),  # stale fy
    ]
    fixed = _dedupe_period_labels(rows)
    by_end = {r.end: (r.fy, r.fp) for r in fixed}
    assert by_end[dt.date(2025, 9, 30)] == (2025, "Q3")
    assert by_end[dt.date(2026, 9, 30)] == (2026, "Q3")
    assert len({(r.fy, r.fp) for r in fixed}) == len(fixed)


def _googl_shaped_rows(q1_2024_first_filed):
    """GOOGL's post-dedupe shape: Q1 ends hold each other's labels (no
    collision), backbone is the prompt 2025Q2–2026Q3 run (6 of 12)."""
    return [
        _row(2023, "Q4", dt.date(2023, 12, 31), dt.date(2024, 1, 31)),
        _row(2025, "Q1", dt.date(2024, 3, 31), q1_2024_first_filed),
        _row(2024, "Q2", dt.date(2024, 6, 30), dt.date(2025, 7, 24)),
        _row(2024, "Q3", dt.date(2024, 9, 30), dt.date(2025, 10, 30)),
        _row(2024, "Q4", dt.date(2024, 12, 31), dt.date(2026, 2, 5)),
        _row(2024, "Q1", dt.date(2025, 3, 31), dt.date(2026, 4, 30)),
        _row(2025, "Q2", dt.date(2025, 6, 30), dt.date(2025, 7, 24)),
        _row(2025, "Q3", dt.date(2025, 9, 30), dt.date(2025, 10, 30)),
        _row(2025, "Q4", dt.date(2025, 12, 31), dt.date(2026, 2, 5)),
        _row(2026, "Q1", dt.date(2026, 3, 31), dt.date(2026, 4, 30)),
        _row(2026, "Q2", dt.date(2026, 6, 30), dt.date(2026, 7, 23)),
        _row(2026, "Q3", dt.date(2026, 9, 30), dt.date(2026, 10, 29)),
    ]


def test_sequence_extension_repairs_comparative_only_q1_swap_without_majority():
    rows = _googl_shaped_rows(dt.date(2025, 7, 24))  # comparative-only
    fixed = _repair_sequence_breaks(rows)
    by_end = {r.end: (r.fy, r.fp) for r in fixed}
    assert by_end[dt.date(2024, 3, 31)] == (2024, "Q1")
    assert by_end[dt.date(2025, 3, 31)] == (2025, "Q1")
    assert by_end[dt.date(2023, 12, 31)] == (2023, "Q4")
    assert by_end[dt.date(2026, 9, 30)] == (2026, "Q3")
    assert len({(r.fy, r.fp) for r in fixed}) == len(fixed)


def test_sequence_extension_leaves_prompt_rows_alone_without_majority():
    """A promptly-filed row keeps the strict-majority protection: a
    minority backbone never settles a dispute between original filings."""
    rows = _googl_shaped_rows(dt.date(2024, 4, 26))  # prompt
    fixed = _repair_sequence_breaks(rows)
    by_end = {r.end: (r.fy, r.fp) for r in fixed}
    # The prompt Q1-2024 claim stands, and because it holds (2025, Q1)
    # the comparative-only Q1-2025 row cannot take its expectation
    # either — the held-target guard leaves the swap untouched rather
    # than collide labels.
    assert by_end[dt.date(2024, 3, 31)] == (2025, "Q1")
    assert by_end[dt.date(2025, 3, 31)] == (2024, "Q1")


def test_sequence_extension_abstains_when_backbone_comparative_only():
    """No prompt anchor, no walk: a comparative-only backbone cannot
    vouch for its own convention."""
    rows = [
        _row(2025, "Q1", dt.date(2024, 3, 31), dt.date(2025, 8, 12)),
        _row(2025, "Q2", dt.date(2024, 6, 30), dt.date(2025, 8, 12)),
        _row(2025, "Q3", dt.date(2024, 9, 30), dt.date(2025, 11, 12)),
        _row(2025, "Q4", dt.date(2024, 12, 31), dt.date(2026, 3, 9)),
        _row(2024, "Q1", dt.date(2025, 3, 31), dt.date(2026, 5, 11)),
        _row(2025, "Q2", dt.date(2025, 6, 30), dt.date(2025, 8, 12)),
        _row(2025, "Q3", dt.date(2025, 9, 30), dt.date(2025, 11, 12)),
        _row(2025, "Q4", dt.date(2025, 12, 31), dt.date(2026, 3, 9)),
    ]
    fixed = _repair_sequence_breaks(rows)
    assert [(r.fy, r.fp) for r in fixed] == [(r.fy, r.fp) for r in rows]


def test_label_lag_days():
    assert _label_lag_days(_row(2025, "Q2", dt.date(2025, 6, 30))) is None
    row = _row(2025, "Q2", dt.date(2025, 6, 30), dt.date(2025, 8, 12))
    assert _label_lag_days(row) == 43
