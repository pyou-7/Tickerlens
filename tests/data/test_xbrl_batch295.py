"""Batch 295 regression tests: recast comparative quarters after an FYE change.

When a filer changes its fiscal year end, the first 10-Q on the new
calendar carries recast comparative quarters sliced on the new calendar
(FedEx's May→Dec FYE change: the Sep-2026 10-Q recasts Jul–Sep 2025 as
a standalone quarter). Those recasts overlap the old-calendar quarters
they slice across — FedEx stored both Jun–Aug 2025 ($22.2B) and the
recast Jul–Sep 2025 ($20.4B) as separate quarters, corrupting every
trend/YoY computation. ``_recast_overlap_ends`` drops a standalone only
when it overlaps a promptly-filed standalone by >20 days and its own
first appearance lags its period end by >180 days; delinquent filers
and comparative-only histories (which tile normally) are untouched.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.xbrl import (
    XbrlFact,
    _dedup_by_end,
    _recast_overlap_ends,
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


def make_companyfacts(revenue, net_income, eps):
    return {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": units("USD", revenue),
                "NetIncomeLoss": units("USD", net_income),
                "EarningsPerShareBasic": units("USD/shares", eps),
                "EarningsPerShareDiluted": units("USD/shares", eps),
                "NetCashProvidedByUsedInOperatingActivities": units("USD", []),
                "PaymentsToAcquirePropertyPlantAndEquipment": units("USD", []),
            }
        }
    }


def rows_by_end(companyfacts, periods=12):
    rows = extract_recent_quarterly_financials(
        companyfacts, fiscal_year_end="1231", periods=periods
    )
    return {row.end.isoformat(): row for row in rows}


# FedEx shape: May-FYE quarters (Jun–Aug, Sep–Nov, Dec–Feb, Mar–May)
# filed promptly, then a Dec-FYE 10-Q filed 2026-10-28 carrying the
# recast Jul–Sep 2025 comparative and the real Jul–Sep 2026 quarter.
FDX_REVENUE = [
    ("2025-06-01", "2025-08-31", 22244.0, 2026, "Q1", "2025-09-25"),
    ("2025-09-01", "2025-11-30", 23469.0, 2026, "Q2", "2025-12-22"),
    ("2025-12-01", "2026-02-28", 24000.0, 2026, "Q3", "2026-03-20"),
    ("2026-03-01", "2026-05-31", 25007.0, 2026, "Q4", "2026-06-25"),
    ("2025-07-01", "2025-09-30", 20432.0, 2026, "Q3", "2026-10-28"),  # recast
    ("2026-07-01", "2026-09-30", 22855.0, 2026, "Q3", "2026-10-28"),
]
FDX_NI = [
    ("2025-06-01", "2025-08-31", 824.0, 2026, "Q1", "2025-09-25"),
    ("2025-09-01", "2025-11-30", 956.0, 2026, "Q2", "2025-12-22"),
    ("2025-12-01", "2026-02-28", 1056.0, 2026, "Q3", "2026-03-20"),
    ("2026-03-01", "2026-05-31", 1597.0, 2026, "Q4", "2026-06-25"),
    ("2025-07-01", "2025-09-30", 920.0, 2026, "Q3", "2026-10-28"),  # recast
    ("2026-07-01", "2026-09-30", 290.0, 2026, "Q3", "2026-10-28"),
]
FDX_EPS = [
    ("2025-06-01", "2025-08-31", 3.3, 2026, "Q1", "2025-09-25"),
    ("2025-09-01", "2025-11-30", 3.9, 2026, "Q2", "2025-12-22"),
    ("2025-12-01", "2026-02-28", 4.3, 2026, "Q3", "2026-03-20"),
    ("2026-03-01", "2026-05-31", 6.5, 2026, "Q4", "2026-06-25"),
    ("2025-07-01", "2025-09-30", 3.7, 2026, "Q3", "2026-10-28"),  # recast
    ("2026-07-01", "2026-09-30", 1.2, 2026, "Q3", "2026-10-28"),
]


def test_recast_comparative_quarter_dropped():
    rows = rows_by_end(make_companyfacts(FDX_REVENUE, FDX_NI, FDX_EPS))
    assert list(rows) == [
        "2025-08-31",
        "2025-11-30",
        "2026-02-28",
        "2026-05-31",
        "2026-09-30",
    ]
    # The recast's values never surface under any surviving end.
    assert all(row.revenue != 20432.0 for row in rows.values())
    assert all(row.net_income != 920.0 for row in rows.values())
    # Old-calendar quarters keep their filed values and labels.
    assert rows["2025-08-31"].revenue == 22244.0
    assert (rows["2026-02-28"].fy, rows["2026-02-28"].fp) == (2026, "Q3")
    # The new-calendar quarter survives; its (2026, Q3) claim collides
    # with the old-calendar Q3, so the label dedupe sequence-relabels it.
    assert rows["2026-09-30"].revenue == 22855.0
    assert (rows["2026-09-30"].fy, rows["2026-09-30"].fp) == (2027, "Q1")
    labels = [(row.fy, row.fp) for row in rows.values()]
    assert len(labels) == len(set(labels))


def test_prompt_overlapping_quarters_both_kept():
    # Two overlapping standalones, both filed promptly: no recast
    # signature (the lag leg fails), so the filter abstains.
    revenue = [
        ("2026-01-01", "2026-03-31", 100.0, 2026, "Q1", "2026-05-01"),
        ("2026-02-01", "2026-04-30", 110.0, 2026, "Q2", "2026-06-01"),
    ]
    ni = [("2026-01-01", "2026-03-31", 10.0, 2026, "Q1", "2026-05-01")]
    eps = [("2026-01-01", "2026-03-31", 1.0, 2026, "Q1", "2026-05-01")]
    rows = rows_by_end(make_companyfacts(revenue, ni, eps))
    assert set(rows) == {"2026-03-31", "2026-04-30"}


def test_late_filed_nonoverlapping_quarter_kept():
    # Delinquent filer: Q1's 10-Q arrives 300 days after period end,
    # but the quarters tile normally — no overlap, no drop.
    revenue = [
        ("2026-01-01", "2026-03-31", 100.0, 2026, "Q1", "2027-01-25"),
        ("2026-04-01", "2026-06-30", 110.0, 2026, "Q2", "2026-08-10"),
        ("2026-07-01", "2026-09-30", 120.0, 2026, "Q3", "2026-11-05"),
    ]
    ni = [("2026-01-01", "2026-03-31", 10.0, 2026, "Q1", "2027-01-25")]
    eps = [("2026-01-01", "2026-03-31", 1.0, 2026, "Q1", "2027-01-25")]
    rows = rows_by_end(make_companyfacts(revenue, ni, eps))
    assert set(rows) == {"2026-03-31", "2026-06-30", "2026-09-30"}
    assert rows["2026-03-31"].revenue == 100.0


def test_comparative_only_history_kept():
    # XOM new-CIK shape: the year-ago quarter first appears as a
    # comparative column a year later (lag > 180d) but tiles with its
    # neighbors — kept.
    revenue = [
        ("2025-04-01", "2025-06-30", 100.0, 2026, "Q2", "2026-07-31"),
        ("2026-04-01", "2026-06-30", 110.0, 2026, "Q2", "2026-07-31"),
    ]
    ni = [("2026-04-01", "2026-06-30", 10.0, 2026, "Q2", "2026-07-31")]
    eps = [("2026-04-01", "2026-06-30", 1.0, 2026, "Q2", "2026-07-31")]
    rows = rows_by_end(make_companyfacts(revenue, ni, eps))
    assert set(rows) == {"2025-06-30", "2026-06-30"}


def xfact(start, end, val, fy, fp, filed):
    return XbrlFact(
        start=dt.date.fromisoformat(start) if start else None,
        end=dt.date.fromisoformat(end),
        val=val,
        fy=fy,
        fp=fp,
        form="10-Q",
        filed=dt.date.fromisoformat(filed),
    )


def test_recast_ends_helper_uses_earliest_filed_not_latest():
    # The genuine quarter also appears as a comparative a year later;
    # its deduped `filed` is the latest, but the lag signature must use
    # the earliest appearance so it stays "prompt" and the recast that
    # overlaps it is still identified.
    facts = [
        xfact("2025-06-01", "2025-08-31", 100.0, 2026, "Q1", "2025-09-25"),
        xfact("2025-06-01", "2025-08-31", 100.0, 2027, "Q1", "2026-09-25"),
        xfact("2025-07-01", "2025-09-30", 90.0, 2026, "Q3", "2026-10-28"),
    ]
    standalone = _dedup_by_end(facts, 70, 115, "1231")
    assert _recast_overlap_ends(facts, standalone) == {dt.date(2025, 9, 30)}


def test_recast_ends_helper_abstains_when_neighbor_also_late():
    # Both overlapping quarters first appear late: no prompt anchor,
    # so nothing is dropped.
    facts = [
        xfact("2025-06-01", "2025-08-31", 100.0, 2026, "Q1", "2026-09-25"),
        xfact("2025-07-01", "2025-09-30", 90.0, 2026, "Q3", "2026-10-28"),
    ]
    standalone = _dedup_by_end(facts, 70, 115, "1231")
    assert _recast_overlap_ends(facts, standalone) == set()
