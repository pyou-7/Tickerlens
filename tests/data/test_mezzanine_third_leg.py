"""Mezzanine third-leg render gate — batch 60.

Batch 59 backfilled redeemable NCI and rendered it as a third balance-sheet
leg wherever the tag exists. The round-17 DB-wide identity audit found five
filers (T, TMO, ACN, WMT, ET) where Assets - Liabilities - Equity already
closes to the dollar *with* a redeemable-NCI value filed — their extracted
total equity already includes it, so the mezzanine row double-counts. The row
must only render when the mezzanine explains an identity gap.
"""

import datetime as dt

from tickerlens.models.quarterly_financial import (
    QuarterlyFinancial,
    mezzanine_is_third_leg,
)
from tickerlens.services.financials import _to_bs


def _row(a, l, e, mezz) -> QuarterlyFinancial:
    return QuarterlyFinancial(
        cik="0001234567",
        period_end=dt.date(2026, 6, 30),
        fiscal_year=2026,
        fiscal_period="Q2",
        total_assets=a,
        total_liabilities=l,
        total_equity=e,
        redeemable_nci=mezz,
    )


def test_to_bs_hides_mezzanine_when_equity_already_includes_it() -> None:
    # T-shaped: identity closes without the mezzanine leg.
    bs = _to_bs(_row(428_359_000_000, 301_925_000_000, 126_434_000_000, 2_005_000_000))
    assert bs.redeemable_nci is None
    assert bs.total_equity == 126_434_000_000


def test_to_bs_keeps_mezzanine_when_it_explains_gap() -> None:
    # SPGI-shaped: the mezzanine is the missing leg.
    bs = _to_bs(_row(60_792_000_000, 24_587_000_000, 31_288_000_000, 4_917_000_000))
    assert bs.redeemable_nci == 4_917_000_000


def test_third_leg_when_mezzanine_explains_gap() -> None:
    # SPGI 2026-03-31: A-L-E = +4917M = mezz.
    assert mezzanine_is_third_leg(60_792_000_000, 24_587_000_000, 31_288_000_000, 4_917_000_000)


def test_not_third_leg_when_identity_already_closes() -> None:
    # T 2026-06-30: A-L-E = 0 with mezz filed — equity already includes it.
    assert not mezzanine_is_third_leg(428_359_000_000, 301_925_000_000, 126_434_000_000, 2_005_000_000)
    # TMO 2026-06-27.
    assert not mezzanine_is_third_leg(113_174_000_000, 60_488_000_000, 52_686_000_000, 121_000_000)
    # ACN 2026-05-31.
    assert not mezzanine_is_third_leg(68_807_000_000, 35_793_000_000, 33_014_000_000, 494_000_000)
    # WMT 2026-04-30.
    assert not mezzanine_is_third_leg(289_607_000_000, 188_925_000_000, 100_682_000_000, 293_000_000)


def test_third_leg_when_mezzanine_partially_explains_gap() -> None:
    # APLD 2026-08-31: gap 2192M, mezz 2011M — same direction, no overshoot.
    assert mezzanine_is_third_leg(11_707_000_000, 7_907_000_000, 1_608_000_000, 2_011_000_000)


def test_not_third_leg_when_mezzanine_overshoots_gap() -> None:
    assert not mezzanine_is_third_leg(10_000_000_000, 6_000_000_000, 3_900_000_000, 500_000_000)


def test_not_third_leg_when_no_mezzanine() -> None:
    assert not mezzanine_is_third_leg(10_000_000_000, 6_000_000_000, 3_000_000_000, None)


def test_third_leg_when_legs_missing() -> None:
    # Identity can't be evaluated — show the filed value (legacy behavior).
    assert mezzanine_is_third_leg(None, 6_000_000_000, 3_000_000_000, 500_000_000)
    assert mezzanine_is_third_leg(10_000_000_000, None, 3_000_000_000, 500_000_000)
