"""Parent-attributable temporary equity (mezzanine) — batch 83.

Round-29 hunt found Keurig Dr Pepper carries $4.418B of convertible
preferred stock in mezzanine equity (``us-gaap:TemporaryEquityCarryingAmount
AttributableToParent``, issued Q1 FY2026 to finance the JDE Peet's
acquisition). The app extracted total_equity correctly but dropped the
mezzanine leg, so KDP's Q1/Q2 FY2026 balance sheets rendered
Assets != Liabilities + Equity (5-6% gaps), and the A=L+E derivation would
mis-derive a missing leg by the mezzanine amount — the same defect class
batch 59 fixed for redeemable NCI (``test_redeemable_nci.py``).
"""

import datetime as dt

from tickerlens.data.xbrl import (
    Metric,
    balance_sheet_metric,
    extract_recent_quarterly_financials,
)


def _instant(end: str, val: float, fy: int, fp: str) -> dict:
    return {
        "end": end,
        "val": val,
        "fy": fy,
        "fp": fp,
        "form": "10-Q",
        "filed": "2026-07-28",
    }


def _rev(start: str, end: str, val: float) -> dict:
    return {
        "start": start,
        "end": end,
        "val": val,
        "fy": 2026,
        "fp": "Q2",
        "form": "10-Q",
        "filed": "2026-07-28",
    }


def _kdp_shaped() -> dict:
    """Mirror Keurig Dr Pepper's 2026-03-31 10-Q (in $M):
    A=73140, L=39540, E=29182 (parent 25261 + NCI 3921), temp equity 4418."""
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [_rev("2026-01-01", "2026-03-31", 3981)]}},
                "Assets": {"units": {"USD": [_instant("2026-03-31", 73140, 2026, "Q1")]}},
                "Liabilities": {
                    "units": {"USD": [_instant("2026-03-31", 39540, 2026, "Q1")]}
                },
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {
                    "units": {"USD": [_instant("2026-03-31", 29182, 2026, "Q1")]}
                },
                "TemporaryEquityCarryingAmountAttributableToParent": {
                    "units": {"USD": [_instant("2026-03-31", 4418, 2026, "Q1")]}
                },
            }
        }
    }


def test_temporary_equity_extracted_from_carrying_amount_tag() -> None:
    rows = extract_recent_quarterly_financials(_kdp_shaped(), fiscal_year_end="1231", periods=4)
    assert len(rows) == 1
    assert rows[0].temporary_equity == 4418


def test_total_equity_not_inflated_by_temporary_equity() -> None:
    # The filing's total equity is 29182 — temporary equity is neither
    # liability nor equity, so it must not be folded into total_equity.
    rows = extract_recent_quarterly_financials(_kdp_shaped(), fiscal_year_end="1231", periods=4)
    assert rows[0].total_equity == 29182
    # And the three-leg identity now closes exactly.
    assert (
        rows[0].total_liabilities
        + rows[0].temporary_equity
        + rows[0].total_equity
        == rows[0].total_assets
    )


def test_temporary_equity_none_when_filer_has_no_mezzanine() -> None:
    facts = _kdp_shaped()
    del facts["facts"]["us-gaap"]["TemporaryEquityCarryingAmountAttributableToParent"]
    rows = extract_recent_quarterly_financials(facts, fiscal_year_end="1231", periods=4)
    assert rows[0].temporary_equity is None


def test_balance_sheet_metric_returns_temporary_equity_by_end() -> None:
    mezz = balance_sheet_metric(_kdp_shaped(), Metric.TEMPORARY_EQUITY, "1231")
    assert mezz == {dt.date(2026, 3, 31): 4418}


def test_derived_liabilities_subtract_known_temporary_equity() -> None:
    """Assets + Equity + temp equity filed, no Liabilities: the derived leg
    must be A − E − temp, not A − E (which would overstate liabilities by
    the mezzanine amount)."""
    facts = _kdp_shaped()
    del facts["facts"]["us-gaap"]["Liabilities"]
    rows = extract_recent_quarterly_financials(facts, fiscal_year_end="1231", periods=4)
    assert rows[0].total_liabilities == 73140 - 29182 - 4418


def test_derived_equity_subtracts_known_temporary_equity() -> None:
    """Assets + Liabilities + temp equity filed, no equity tag: derived
    equity must be A − L − temp."""
    facts = _kdp_shaped()
    del facts["facts"]["us-gaap"][
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    ]
    rows = extract_recent_quarterly_financials(facts, fiscal_year_end="1231", periods=4)
    assert rows[0].total_equity == 73140 - 39540 - 4418


def test_derivation_unchanged_when_temporary_equity_unknown() -> None:
    """No temporary-equity facts at all: the old two-leg formula still applies."""
    facts = _kdp_shaped()
    del facts["facts"]["us-gaap"]["Liabilities"]
    del facts["facts"]["us-gaap"]["TemporaryEquityCarryingAmountAttributableToParent"]
    rows = extract_recent_quarterly_financials(facts, fiscal_year_end="1231", periods=4)
    assert rows[0].total_liabilities == 73140 - 29182


def test_both_mezzanine_legs_sum_in_derivation() -> None:
    """A filer carrying redeemable NCI *and* parent temporary equity: the
    derived leg subtracts both."""
    facts = _kdp_shaped()
    del facts["facts"]["us-gaap"]["Liabilities"]
    facts["facts"]["us-gaap"]["RedeemableNoncontrollingInterestEquityCarryingAmount"] = {
        "units": {"USD": [_instant("2026-03-31", 1000, 2026, "Q1")]}
    }
    rows = extract_recent_quarterly_financials(facts, fiscal_year_end="1231", periods=4)
    assert rows[0].total_liabilities == 73140 - 29182 - 4418 - 1000
    assert rows[0].temporary_equity == 4418
    assert rows[0].redeemable_nci == 1000
