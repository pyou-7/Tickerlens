"""Unit tests for the rules-based valuation signal (PRD §4.11)."""

from __future__ import annotations

import pytest

from tickerlens.services.valuation import compute_valuation


def _base(**overrides):
    kwargs = dict(
        ticker="TEST",
        current_price=100.0,
        ttm_eps_diluted=5.0,
        eps_growth_pct=20.0,
        ttm_revenue=1_000_000_000.0,
        revenue_growth_pct=10.0,
        shares_outstanding=10_000_000.0,
        ttm_quarters=4,
    )
    kwargs.update(overrides)
    return compute_valuation(**kwargs)


def test_peg_strong_buy():
    v = _base()
    assert v.signal == "Strong Buy"
    assert v.method == "peg"
    assert v.target_price == pytest.approx(150.0)  # 5.0 EPS * (1.5 * 20) P/E
    assert v.upside_pct == pytest.approx(50.0)
    assert v.confidence == "High"
    assert v.fair_multiple == pytest.approx(30.0)
    assert v.current_multiple == pytest.approx(20.0)
    assert len(v.reasoning) >= 3


def test_peg_hold_near_fair_value():
    # 5.0 EPS * 15 P/E = 75 target vs 72 price -> +4.2% -> Hold
    v = _base(current_price=72.0, eps_growth_pct=10.0)
    assert v.signal == "Hold"
    assert v.upside_pct == pytest.approx(4.2, abs=0.1)


def test_peg_sell_and_strong_sell_thresholds():
    v = _base(current_price=170.0)  # 150 target -> -11.8%
    assert v.signal == "Sell"
    v = _base(current_price=220.0)  # 150 target -> -31.8%
    assert v.signal == "Strong Sell"


def test_peg_buy_threshold():
    v = _base(current_price=130.0)  # 150 target -> +15.4%
    assert v.signal == "Buy"


def test_growth_clamped():
    # 100% growth is clamped to 40% -> fair P/E clamped to 40x -> target 200
    v = _base(eps_growth_pct=100.0)
    assert v.fair_multiple == pytest.approx(40.0)
    assert v.target_price == pytest.approx(200.0)
    # near-zero growth is clamped to 2% -> fair P/E clamped to 8x floor
    v = _base(eps_growth_pct=0.5)
    assert v.fair_multiple == pytest.approx(8.0)


def test_sales_fallback_for_negative_earnings():
    v = _base(ttm_eps_diluted=-1.0, eps_growth_pct=None, current_price=50.0)
    assert v.method == "sales"
    assert v.signal == "Strong Buy"
    # fair P/S = 0.5 * 10% rev growth = 5x -> target = 1e9 * 5 / 1e7 = 500
    assert v.target_price == pytest.approx(500.0)
    assert any("sales" in r for r in v.reasoning)


def test_missing_price_is_watch():
    v = _base(current_price=None)
    assert v.signal == "Watch"
    assert v.method == "unavailable"
    assert v.target_price is None
    assert v.confidence == "Low"


def test_no_usable_financials_is_watch():
    v = _base(ttm_eps_diluted=None, eps_growth_pct=None, ttm_revenue=None)
    assert v.signal == "Watch"
    assert v.method == "unavailable"


def test_partial_history_lowers_confidence():
    v = _base(ttm_quarters=2)
    assert v.confidence == "Medium"
    v = _base(growth_is_fallback=True)
    assert v.confidence == "Medium"
