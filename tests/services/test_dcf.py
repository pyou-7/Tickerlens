"""Unit tests for the DCF intrinsic valuation model and sensitivity matrix."""

import pytest

from tickerlens.services.dcf import (
    DCFModelResult,
    compute_dcf,
)


def test_dcf_positive_fcf_generates_valid_schedule_and_matrix():
    # Model test case: $10B FCF, 1B shares, $100 price, 15% growth
    result = compute_dcf(
        ticker="TECH",
        ttm_free_cash_flow=10_000_000_000.0,
        shares_outstanding=1_000_000_000.0,
        current_price=100.0,
        eps_growth_pct=15.0,
        sic="7372",
    )

    assert result.is_applicable is True
    assert result.unavailability_reason is None
    assert result.base_fcf == 10_000_000_000.0
    assert result.base_growth_rate_pct == 15.0
    assert result.base_discount_rate_pct == 9.0
    assert result.base_terminal_growth_pct == 2.5

    # 5-year projections schedule
    assert len(result.projections) == 5
    assert result.projections[0].year == 1
    assert result.projections[4].year == 5
    # Projections should be increasing with positive growth
    assert result.projections[0].projected_fcf < result.projections[4].projected_fcf

    # Intrinsic values
    assert result.enterprise_value is not None
    assert result.enterprise_value > 0
    assert result.fair_value_per_share is not None
    assert result.fair_value_per_share > 0
    assert result.upside_pct is not None

    # 5x5 sensitivity matrix
    assert len(result.matrix) == 5
    for row in result.matrix:
        assert len(row) == 5

    # Check base case cell
    base_cells = [cell for row in result.matrix for cell in row if cell.is_base_case]
    assert len(base_cells) == 1
    base_cell = base_cells[0]
    assert base_cell.discount_rate_pct == 9.0
    assert base_cell.terminal_growth_pct == 2.5
    assert base_cell.fair_value_per_share == result.fair_value_per_share


def test_dcf_negative_fcf_is_not_applicable():
    result = compute_dcf(
        ticker="LOSS",
        ttm_free_cash_flow=-500_000_000.0,
        shares_outstanding=100_000_000.0,
        current_price=25.0,
        eps_growth_pct=10.0,
    )
    assert result.is_applicable is False
    assert "Trailing Free Cash Flow is negative" in (result.unavailability_reason or "")
    assert result.matrix == []


def test_dcf_finance_sic_is_suppressed():
    # Banks and insurers (SIC 6000-6999)
    result = compute_dcf(
        ticker="BANK",
        ttm_free_cash_flow=20_000_000_000.0,
        shares_outstanding=2_000_000_000.0,
        current_price=150.0,
        sic="6021",
    )
    assert result.is_applicable is False
    assert "financial institutions" in (result.unavailability_reason or "")
    assert result.matrix == []


def test_dcf_missing_quote_or_shares():
    res1 = compute_dcf(
        ticker="XYZ",
        ttm_free_cash_flow=1_000_000.0,
        shares_outstanding=None,
        current_price=50.0,
    )
    assert res1.is_applicable is False
    assert "Shares outstanding" in (res1.unavailability_reason or "")

    res2 = compute_dcf(
        ticker="XYZ",
        ttm_free_cash_flow=1_000_000.0,
        shares_outstanding=100_000.0,
        current_price=None,
    )
    assert res2.is_applicable is False
    assert "market quote" in (res2.unavailability_reason or "")


def test_dcf_growth_clamping():
    # Extreme growth (e.g. 150%) should be clamped to 25% max base growth
    res_high = compute_dcf(
        ticker="HIGH",
        ttm_free_cash_flow=5_000_000_000.0,
        shares_outstanding=500_000_000.0,
        current_price=80.0,
        eps_growth_pct=150.0,
    )
    assert res_high.is_applicable is True
    assert res_high.base_growth_rate_pct == 25.0

    # Negative growth should fall back to default 8% base growth
    res_neg = compute_dcf(
        ticker="DOWN",
        ttm_free_cash_flow=5_000_000_000.0,
        shares_outstanding=500_000_000.0,
        current_price=80.0,
        eps_growth_pct=-15.0,
    )
    assert res_neg.is_applicable is True
    assert res_neg.base_growth_rate_pct == 8.0
