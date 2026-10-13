"""Redeemable noncontrolling interest (mezzanine equity) — batch 59.

Round-16 hunt found 14 of 138 DB companies carry redeemable NCI between
liabilities and permanent equity (SPGI $4.9B, APLD $2.0B, T $2.0B,
UNH $1.4B, OTIS $106M, ICE $32M, SNPS $30M on one quarter). The app
extracted total_equity correctly but dropped the mezzanine line, so every
affected balance sheet rendered Assets != Liabilities + Equity — and the
A=L+E derivation would mis-derive a missing leg by the mezzanine amount.
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


def _spgi_shaped() -> dict:
    """Mirror S&P Global's 2026-03-31 10-Q: A=60792, L=24587, E(incl)=31288,
    redeemable NCI 4917 (mezzanine)."""
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [_rev("2026-01-01", "2026-03-31", 4170)]}},
                "Assets": {"units": {"USD": [_instant("2026-03-31", 60792, 2026, "Q1")]}},
                "Liabilities": {
                    "units": {"USD": [_instant("2026-03-31", 24587, 2026, "Q1")]}
                },
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {
                    "units": {"USD": [_instant("2026-03-31", 31288, 2026, "Q1")]}
                },
                "RedeemableNoncontrollingInterestEquityCarryingAmount": {
                    "units": {"USD": [_instant("2026-03-31", 4917, 2026, "Q1")]}
                },
            }
        }
    }


def test_redeemable_nci_extracted_from_carrying_amount_tag() -> None:
    rows = extract_recent_quarterly_financials(_spgi_shaped(), fiscal_year_end="1231", periods=4)
    assert len(rows) == 1
    assert rows[0].redeemable_nci == 4917


def test_total_equity_not_inflated_by_mezzanine() -> None:
    # The filing's total equity is 31288 — mezzanine is neither liability
    # nor equity, so it must not be folded into total_equity.
    rows = extract_recent_quarterly_financials(_spgi_shaped(), fiscal_year_end="1231", periods=4)
    assert rows[0].total_equity == 31288
    # And the three-leg identity now closes exactly.
    assert (
        rows[0].total_liabilities + rows[0].redeemable_nci + rows[0].total_equity
        == rows[0].total_assets
    )


def test_redeemable_nci_none_when_filer_has_no_mezzanine() -> None:
    facts = _spgi_shaped()
    del facts["facts"]["us-gaap"]["RedeemableNoncontrollingInterestEquityCarryingAmount"]
    rows = extract_recent_quarterly_financials(facts, fiscal_year_end="1231", periods=4)
    assert rows[0].redeemable_nci is None


def test_balance_sheet_metric_returns_mezzanine_by_end() -> None:
    mezz = balance_sheet_metric(_spgi_shaped(), Metric.REDEEMABLE_NCI, "1231")
    assert mezz == {dt.date(2026, 3, 31): 4917}


def test_derived_liabilities_subtract_known_mezzanine() -> None:
    """Assets + Equity + mezzanine filed, no Liabilities: the derived leg
    must be A − E − mezz, not A − E (which would overstate liabilities by
    the mezzanine amount)."""
    facts = _spgi_shaped()
    del facts["facts"]["us-gaap"]["Liabilities"]
    rows = extract_recent_quarterly_financials(facts, fiscal_year_end="1231", periods=4)
    assert rows[0].total_liabilities == 60792 - 31288 - 4917


def test_derived_equity_subtracts_known_mezzanine() -> None:
    """Assets + Liabilities + mezzanine filed, no equity tag: derived
    equity must be A − L − mezz."""
    facts = _spgi_shaped()
    del facts["facts"]["us-gaap"][
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    ]
    rows = extract_recent_quarterly_financials(facts, fiscal_year_end="1231", periods=4)
    assert rows[0].total_equity == 60792 - 24587 - 4917


def test_derivation_unchanged_when_mezzanine_unknown() -> None:
    """No mezzanine facts at all: the old two-leg formula still applies."""
    facts = _spgi_shaped()
    del facts["facts"]["us-gaap"]["Liabilities"]
    del facts["facts"]["us-gaap"]["RedeemableNoncontrollingInterestEquityCarryingAmount"]
    rows = extract_recent_quarterly_financials(facts, fiscal_year_end="1231", periods=4)
    assert rows[0].total_liabilities == 60792 - 31288


def test_explicit_legs_never_overwritten_when_mezzanine_present() -> None:
    rows = extract_recent_quarterly_financials(_spgi_shaped(), fiscal_year_end="1231", periods=4)
    assert rows[0].total_assets == 60792
    assert rows[0].total_liabilities == 24587
    assert rows[0].total_equity == 31288
    assert rows[0].redeemable_nci == 4917
