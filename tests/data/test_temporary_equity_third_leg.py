"""Temporary-equity third-leg render gate — batch 83.

The same gate that batch 60 built for redeemable NCI applies to the new
parent-temporary-equity mezzanine leg: the row only renders where the
temporary equity explains an identity gap. KDP-shaped: A=73140M, L=39540M,
E=29182M, temp equity=4418M (convertible preferred stock financing the
JDE Peet's acquisition, filed Q1 FY2026).
"""

import datetime as dt

from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.services.financials import _to_bs


def _row(a, l, e, temp) -> QuarterlyFinancial:
    return QuarterlyFinancial(
        cik="0001418135",
        period_end=dt.date(2026, 6, 30),
        fiscal_year=2026,
        fiscal_period="Q2",
        total_assets=a,
        total_liabilities=l,
        total_equity=e,
        temporary_equity=temp,
    )


def test_to_bs_keeps_temporary_equity_when_it_explains_gap() -> None:
    # KDP 2026-06-30: A-L-E = +4418M = temp equity.
    bs = _to_bs(_row(87_619_000_000, 53_973_000_000, 29_228_000_000, 4_418_000_000))
    assert bs.temporary_equity == 4_418_000_000


def test_to_bs_hides_temporary_equity_when_identity_already_closes() -> None:
    # Equity already includes the mezzanine line: identity closes without it.
    bs = _to_bs(_row(87_619_000_000, 53_973_000_000, 33_646_000_000, 4_418_000_000))
    assert bs.temporary_equity is None


def test_property_mirrors_gate() -> None:
    assert _row(87_619_000_000, 53_973_000_000, 29_228_000_000, 4_418_000_000).temporary_equity_is_third_leg
    assert not _row(87_619_000_000, 53_973_000_000, 33_646_000_000, 4_418_000_000).temporary_equity_is_third_leg


def test_to_bs_keeps_both_mezzanine_legs() -> None:
    # Filer carrying both legs: each is gated independently.
    r = _row(80_000_000_000, 40_000_000_000, 33_582_000_000, 4_418_000_000)
    r.redeemable_nci = 2_000_000_000
    bs = _to_bs(r)
    assert bs.temporary_equity == 4_418_000_000
    assert bs.redeemable_nci == 2_000_000_000
