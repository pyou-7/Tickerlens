"""Batch 298 regression tests: gated diluted<-basic EPS fill.

LEN's FY2025 10-K filed the FY ``EarningsPerShareBasic`` fact (7.98) but
no FY diluted fact, so Q4 FY2025 diluted EPS was underivable (stored
NULL, rendered "—") while basic share-derived to 1.9181. LEN has no
dilutive securities in its current era — every filed basic/diluted pair
has been exactly equal since 2023 — so the missing diluted leg equals
basic. ``_fill_missing_eps_diluted`` fills such gaps, gated on nearby
filed pairs all being equal (LEN's 2013-2022 convert-era pairs genuinely
differ, so the evidence window is local to the gap), plus loss quarters
where diluted == basic by definition (ASC 260). A 303-ticker blast found
exactly one stored row in this shape (LEN 2025-11-30); the remaining
full-history hits are deep-history ends (KMI 2018-19, TDG 2014-21,
ENPH/PLUG loss quarters) outside every stored window.
"""
import datetime as dt
import sys

sys.path.insert(0, "src")

from tickerlens.data.xbrl import (
    Metric,
    PeriodMetric,
    _fill_missing_eps_diluted,
    extract_recent_quarterly_financials,
)


def pm(metric, end, value, fy=2025, fp="Q1", tag=None):
    return PeriodMetric(
        metric=metric,
        fy=fy,
        fp=fp,
        end=end,
        value=value,
        source_tag=tag or ("EarningsPerShareBasic" if metric is Metric.EPS_BASIC else "EarningsPerShareDiluted"),
    )


def basic(end, value, **kw):
    return pm(Metric.EPS_BASIC, end, value, **kw)


def diluted(end, value, **kw):
    return pm(Metric.EPS_DILUTED, end, value, **kw)


def by_end(series):
    return {p.end: p for p in series}


def test_len_shape_recent_equal_pairs_fill_gap_ancient_dilution_ignored():
    """LEN shape: 2014 pair genuinely diluted, 2024-2026 pairs all equal,
    diluted missing at the 2025-11-30 gap -> filled from basic."""
    ends = [
        dt.date(2024, 11, 30), dt.date(2025, 2, 28), dt.date(2025, 5, 31),
        dt.date(2025, 8, 31), dt.date(2026, 2, 28), dt.date(2026, 5, 31),
    ]
    vals = [4.0614, 1.96, 1.81, 2.29, 0.93, 1.24]
    b = [basic(dt.date(2014, 11, 30), 1.20, fy=2014, fp="Q4")]
    d = [diluted(dt.date(2014, 11, 30), 1.07, fy=2014, fp="Q4")]
    for e, v in zip(ends, vals):
        b.append(basic(e, v))
        d.append(diluted(e, v))
    gap = dt.date(2025, 11, 30)
    b.append(basic(gap, 1.9181, fy=2025, fp="Q4"))

    out = by_end(_fill_missing_eps_diluted(b, d))
    assert out[gap].value == 1.9181
    assert out[gap].metric is Metric.EPS_DILUTED
    # Provenance: the filled fact carries the basic fact's source tag.
    assert out[gap].source_tag == "EarningsPerShareBasic"
    # Filed diluted values are untouched.
    assert out[dt.date(2014, 11, 30)].value == 1.07
    assert out[dt.date(2025, 8, 31)].value == 2.29


def test_gate_blocks_when_nearby_pair_shows_dilution():
    """A filer with real dilution near the gap gets no fill."""
    ends = [dt.date(2025, 3, 31), dt.date(2025, 6, 30),
            dt.date(2025, 9, 30), dt.date(2026, 3, 31)]
    b = [basic(e, 1.00) for e in ends]
    d = [diluted(e, 0.95) for e in ends]  # diluted < basic: real dilution
    gap = dt.date(2025, 12, 31)
    b.append(basic(gap, 1.10, fp="Q4"))

    out = by_end(_fill_missing_eps_diluted(b, d))
    assert gap not in out


def test_gate_blocks_with_too_few_nearby_overlaps():
    """Fewer than 4 overlapping pairs within the window -> no fill."""
    ends = [dt.date(2025, 6, 30), dt.date(2025, 9, 30), dt.date(2026, 3, 31)]
    b = [basic(e, 1.00) for e in ends]
    d = [diluted(e, 1.00) for e in ends]
    gap = dt.date(2025, 12, 31)
    b.append(basic(gap, 1.10, fp="Q4"))

    out = by_end(_fill_missing_eps_diluted(b, d))
    assert gap not in out


def test_gate_ignores_overlaps_outside_evidence_window():
    """Equal pairs more than 730 days from the gap are not evidence."""
    # 4 equal pairs in 2020-2021; gap in 2026 -> all >730 days away.
    ends = [dt.date(2020, 12, 31), dt.date(2021, 3, 31),
            dt.date(2021, 6, 30), dt.date(2021, 9, 30)]
    b = [basic(e, 1.00) for e in ends]
    d = [diluted(e, 1.00) for e in ends]
    gap = dt.date(2026, 3, 31)
    b.append(basic(gap, 1.10))

    out = by_end(_fill_missing_eps_diluted(b, d))
    assert gap not in out


def test_gate_tolerance_boundary():
    """Diff of exactly half a cent counts as equal; 0.006 blocks."""
    ends = [dt.date(2025, 3, 31), dt.date(2025, 6, 30),
            dt.date(2025, 9, 30), dt.date(2026, 3, 31)]
    gap = dt.date(2025, 12, 31)

    b = [basic(e, 1.000) for e in ends] + [basic(gap, 1.10, fp="Q4")]
    d = [diluted(e, 0.995) for e in ends]  # diff 0.005 -> equal
    assert gap in by_end(_fill_missing_eps_diluted(b, d))

    d = [diluted(e, 0.994) for e in ends]  # diff 0.006 -> dilution
    assert gap not in by_end(_fill_missing_eps_diluted(b, d))


def test_loss_quarter_fills_without_gate():
    """ASC 260: in a loss quarter diluted == basic by definition, even
    for a filer whose profit quarters show real dilution (ENPH/PLUG
    deep-history shape)."""
    ends = [dt.date(2025, 3, 31), dt.date(2025, 6, 30),
            dt.date(2025, 9, 30), dt.date(2026, 3, 31)]
    b = [basic(e, 1.00) for e in ends]
    d = [diluted(e, 0.90) for e in ends]  # gate would block
    gap = dt.date(2025, 12, 31)
    b.append(basic(gap, -0.40, fp="Q4"))  # loss quarter

    out = by_end(_fill_missing_eps_diluted(b, d))
    assert out[gap].value == -0.40


def test_no_diluted_series_gets_no_fills():
    """A filer that never files diluted EPS (BRK.B/V shape) stays "—",
    loss quarters included."""
    b = [basic(dt.date(2025, 3, 31), 1.00), basic(dt.date(2025, 6, 30), -0.50)]
    assert _fill_missing_eps_diluted(b, []) == []
    assert _fill_missing_eps_diluted([], []) == []


def test_filed_diluted_never_overwritten():
    """Ends with a filed diluted value keep it, whatever basic says."""
    end = dt.date(2025, 3, 31)
    out = by_end(_fill_missing_eps_diluted(
        [basic(end, 1.00)], [diluted(end, 0.97)]
    ))
    assert out[end].value == 0.97
    assert out[end].source_tag == "EarningsPerShareDiluted"


def fact(start, end, val, fy, fp, filed):
    return {
        "start": start, "end": end, "val": val, "fy": fy, "fp": fp,
        "form": "10-Q" if fp != "FY" else "10-K", "filed": filed,
    }


def len_shaped_facts():
    """LEN-shaped companyfacts: Nov FYE; basic==diluted filed pairs
    around a Q4 whose diluted leg is missing (standalone gap here; the
    real LEN gap is the underivable Q4 derivation)."""
    quarters = [
        # (start, end, fy, fp, filed, revenue, eps)
        ("2024-06-01", "2024-08-31", 2024, "Q3", "2024-10-03", 9_400_000_000, 4.26),
        ("2024-09-01", "2024-11-30", 2024, "Q4", "2025-01-29", 9_900_000_000, 4.06),
        ("2024-12-01", "2025-02-28", 2025, "Q1", "2025-04-04", 7_600_000_000, 1.96),
        ("2025-03-01", "2025-05-31", 2025, "Q2", "2025-07-01", 8_400_000_000, 1.81),
        ("2025-06-01", "2025-08-31", 2025, "Q3", "2025-10-03", 8_800_000_000, 2.29),
        ("2025-09-01", "2025-11-30", 2025, "Q4", "2026-01-28", 9_100_000_000, 1.92),
        ("2025-12-01", "2026-02-28", 2026, "Q1", "2026-04-09", 7_300_000_000, 0.93),
        ("2026-03-01", "2026-05-31", 2026, "Q2", "2026-06-29", 8_000_000_000, 1.24),
    ]
    gap_end = "2025-11-30"
    gaap = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": []}},
        "EarningsPerShareBasic": {"units": {"USD/shares": []}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": []}},
    }
    for start, end, fy, fp, filed, rev, eps in quarters:
        gaap["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"].append(
            fact(start, end, rev, fy, fp, filed))
        gaap["EarningsPerShareBasic"]["units"]["USD/shares"].append(
            fact(start, end, eps, fy, fp, filed))
        if end != gap_end:
            gaap["EarningsPerShareDiluted"]["units"]["USD/shares"].append(
                fact(start, end, eps, fy, fp, filed))
    return {"facts": {"us-gaap": gaap}}


def test_end_to_end_len_gap_filled_through_extraction():
    rows = extract_recent_quarterly_financials(len_shaped_facts(), periods=8)
    by_end = {r.end: r for r in rows}
    gap = by_end[dt.date(2025, 11, 30)]
    assert gap.eps_basic == 1.92
    assert gap.eps_diluted == 1.92
    # Neighbors keep their filed values.
    assert by_end[dt.date(2025, 8, 31)].eps_diluted == 2.29
    assert by_end[dt.date(2026, 2, 28)].eps_diluted == 0.93
