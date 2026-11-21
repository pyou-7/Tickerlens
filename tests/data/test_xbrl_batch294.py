"""Batch 294 regression tests: placeholder zero-assets balance sheets.

Skydance Corp (SKYD) filed pre-merger shell 10-Qs in May/Aug 2025 with
literal ``Assets=0`` / ``LiabilitiesAndStockholdersEquity=0`` placeholder
facts, while later filings carry predecessor comparative equity
(``StockholdersEquityIncludingPortion…`` $16.928B / $17.111B) at the same
ends. The extractor took the zero assets at face value and the identity
derivation fabricated liabilities of −$16.928B — total liabilities can
never be negative, and a consolidated total-assets instant of zero is
never a real balance sheet for a filer with revenue.

Fixes: ``_balance_sheet_facts`` skips non-positive TOTAL_ASSETS instants
(so the end renders "—" and a later chain tag's real value can fill it),
and ``_derive_missing_balance_sheet`` abstains when the derived
liabilities leg would be negative. Derived *equity* stays unguarded —
negative equity is real for buyback-heavy filers.
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.xbrl import extract_recent_quarterly_financials

END = "2025-03-31"
END2 = "2025-06-30"


def _instant(end, val, filed="2025-05-14"):
    return {"end": end, "val": val, "fy": 2025, "fp": "Q1",
            "form": "10-Q", "filed": filed}


def _rev(start, end, val):
    return {"start": start, "end": end, "val": val, "fy": 2025, "fp": "Q1",
            "form": "10-Q", "filed": "2025-05-14"}


def _facts(**tags):
    gaap = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {
            "units": {"USD": [_rev("2025-01-01", END, 7_192_000_000),
                              _rev("2025-04-01", END2, 6_849_000_000)]}
        },
    }
    for tag, values in tags.items():
        gaap[tag] = {"units": {"USD": values}}
    return {"facts": {"us-gaap": gaap}}


def _rows(companyfacts):
    rows = extract_recent_quarterly_financials(
        companyfacts, fiscal_year_end="1231", periods=8
    )
    return {row.end.isoformat(): row for row in rows}


def test_skyd_shape_zero_assets_abstains():
    """Assets=0 + comparative equity: assets/liabilities "—", equity kept."""
    rows = _rows(_facts(
        Assets=[_instant(END, 0), _instant(END2, 0)],
        LiabilitiesAndStockholdersEquity=[_instant(END, 0), _instant(END2, 0)],
        StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest=[
            _instant(END, 16_928_000_000, "2026-05-04"),
            _instant(END2, 17_111_000_000, "2025-11-10"),
        ],
    ))
    for end, equity in ((END, 16_928_000_000), (END2, 17_111_000_000)):
        assert rows[end].total_assets is None
        assert rows[end].total_liabilities is None
        assert rows[end].total_equity == equity


def test_zero_primary_assets_fallback_tag_fills():
    """A zero under Assets must not block a real LiabilitiesAndStockholdersEquity."""
    rows = _rows(_facts(
        Assets=[_instant(END, 0)],
        LiabilitiesAndStockholdersEquity=[_instant(END, 46_172_000_000)],
        Liabilities=[_instant(END, 29_390_000_000)],
        StockholdersEquity=[_instant(END, 16_782_000_000)],
    ))
    assert rows[END].total_assets == 46_172_000_000
    assert rows[END].total_liabilities == 29_390_000_000


def test_negative_filed_assets_skipped():
    rows = _rows(_facts(
        Assets=[_instant(END, -5_000_000)],
        StockholdersEquity=[_instant(END, 1_000_000)],
    ))
    assert rows[END].total_assets is None
    assert rows[END].total_liabilities is None


def test_derived_liabilities_negative_abstains():
    """Equity > assets (inconsistent bases): no fabricated negative leg."""
    rows = _rows(_facts(
        Assets=[_instant(END, 10_000_000_000)],
        StockholdersEquity=[_instant(END, 12_000_000_000)],
    ))
    assert rows[END].total_assets == 10_000_000_000
    assert rows[END].total_liabilities is None


def test_normal_liabilities_derivation_intact():
    rows = _rows(_facts(
        Assets=[_instant(END, 10_000_000_000)],
        StockholdersEquity=[_instant(END, 4_000_000_000)],
    ))
    assert rows[END].total_liabilities == 6_000_000_000


def test_negative_derived_equity_still_derived():
    """Negative equity is real (buyback filers) — derivation unguarded."""
    rows = _rows(_facts(
        Assets=[_instant(END, 10_000_000_000)],
        Liabilities=[_instant(END, 12_000_000_000)],
    ))
    assert rows[END].total_equity == -2_000_000_000


def test_zero_assets_end_does_not_break_other_quarters():
    rows = _rows(_facts(
        Assets=[_instant(END, 0), _instant(END2, 44_411_000_000)],
        Liabilities=[_instant(END2, 31_601_000_000)],
        StockholdersEquity=[_instant(END, 0), _instant(END2, 12_810_000_000)],
    ))
    assert rows[END].total_assets is None
    assert rows[END2].total_assets == 44_411_000_000
    assert rows[END2].total_liabilities == 31_601_000_000
    assert rows[END2].total_equity == 12_810_000_000
