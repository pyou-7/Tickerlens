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
    # 100% growth is clamped to 40% -> fair P/E clamped to 40x -> target 200.
    # Pin a low 10y yield so the batch-12 rate guardrail stays dormant here.
    v = _base(eps_growth_pct=100.0, ten_year_yield_pct=2.0)
    assert v.fair_multiple == pytest.approx(40.0)
    assert v.target_price == pytest.approx(200.0)


def test_rate_guardrail_binds_at_high_yield():
    # 30% growth -> raw 45x -> clamped 40x; 10y at 5.3% caps at
    # 100 / (5.3 * 0.6) ~= 31.4x. Confidence capped, note added.
    v = _base(eps_growth_pct=30.0, ten_year_yield_pct=5.3)
    assert v.fair_multiple == pytest.approx(100.0 / (5.3 * 0.6), abs=0.05)
    assert v.confidence == "Medium"
    assert any("10-year Treasury" in p for p in v.reasoning)


def test_rate_guardrail_dormant_at_low_yield():
    # 10y at 2% -> cap at 83x; the 40x clamp binds first, no rate note.
    v = _base(eps_growth_pct=100.0, ten_year_yield_pct=2.0)
    assert v.fair_multiple == pytest.approx(40.0)
    assert not any("10-year Treasury" in p for p in v.reasoning)


def test_rate_guardrail_default_yield():
    # None -> 4.5% default benchmark -> cap at ~37.0x.
    v = _base(eps_growth_pct=100.0)
    assert v.fair_multiple == pytest.approx(100.0 / (4.5 * 0.6), abs=0.05)
    assert any("10-year Treasury" in p for p in v.reasoning)


def test_rate_guardrail_ignores_nonsense_yield():
    # Zero/negative yields fall back to the default benchmark, never crash.
    for bad in (0.0, -2.0):
        v = _base(eps_growth_pct=100.0, ten_year_yield_pct=bad)
        assert v.fair_multiple == pytest.approx(100.0 / (4.5 * 0.6), abs=0.05)


def test_rate_guardrail_can_temper_signal():
    # 5.0 EPS, 30% growth, price 140: no guardrail -> 200 target (+42.9%,
    # Strong Buy); 5.3% yield -> ~157 target (+12%, Buy).
    v = _base(current_price=140.0, eps_growth_pct=30.0, ten_year_yield_pct=5.3)
    assert v.signal == "Buy"
    v_noguard = _base(current_price=140.0, eps_growth_pct=30.0, ten_year_yield_pct=2.0)
    assert v_noguard.signal == "Strong Buy"
    # near-zero growth is clamped to 2% -> fair P/E clamped to 8x floor
    v = _base(eps_growth_pct=0.5)
    assert v.fair_multiple == pytest.approx(8.0)


def test_sales_fallback_for_negative_earnings():
    # Loss-maker with no positive margin to anchor a sales multiple (the Ford
    # case, batch 26): the old margin-blind 0.5 x growth curve emitted a
    # +641% Strong Buy. Now the model refuses to fabricate a target.
    v = _base(ttm_eps_diluted=-1.0, eps_growth_pct=None, current_price=50.0,
              ttm_net_income=-100_000_000.0)
    assert v.signal == "Watch"
    assert v.method == "unavailable"
    assert v.target_price is None
    assert v.confidence == "Low"
    assert any("anchor a sales multiple" in r for r in v.reasoning)


def test_sales_fallback_zero_margin_is_watch():
    v = _base(ttm_eps_diluted=-1.0, eps_growth_pct=None, current_price=50.0,
              ttm_net_income=0.0)
    assert v.signal == "Watch"
    assert v.target_price is None


def test_sales_fallback_margin_anchored():
    # Negative EPS but a positive TTM net margin: fair P/S = fair P/E x
    # margin (the accounting identity). 10% margin x 15x fair P/E (10%
    # growth, PEG 1.5) = 1.5x P/S -> target = 1e9 * 1.5 / 1e7 = 150.
    v = _base(ttm_eps_diluted=-1.0, eps_growth_pct=None, current_price=50.0,
              ttm_net_income=100_000_000.0)
    assert v.method == "sales"
    assert v.fair_multiple == pytest.approx(1.5)
    assert v.target_price == pytest.approx(150.0)
    assert v.signal == "Strong Buy"
    assert any("10.0% × fair P/E 15.0×" in r for r in v.reasoning)


def test_sales_fallback_turnaround_positive_eps_no_growth():
    # Positive EPS with no computable growth (prior-year EPS was negative):
    # the sales path still works, anchored on the positive margin.
    v = _base(ttm_eps_diluted=2.0, eps_growth_pct=None, current_price=50.0,
              ttm_net_income=100_000_000.0)
    assert v.method == "sales"
    assert v.fair_multiple == pytest.approx(1.5)
    assert v.target_price == pytest.approx(150.0)


def test_sales_fallback_copy_honest_about_earnings():
    # Batch 33: the sales path is only reachable with a positive TTM net
    # margin, so TTM earnings ARE positive — the old "No positive TTM
    # earnings" bullet was false for every company on this path (e.g. ET, an
    # MLP with positive net income but no XBRL EPS facts).
    v = _base(ttm_eps_diluted=None, eps_growth_pct=None, current_price=50.0,
              ttm_net_income=100_000_000.0)
    assert v.method == "sales"
    assert not any("No positive TTM earnings" in r for r in v.reasoning)
    assert any("No per-share earnings to anchor a P/E multiple" in r
               for r in v.reasoning)


def test_sales_fallback_ps_cap_and_rate_guardrail():    # 40% growth -> fair P/E 40x, rate-guarded to ~37.0x at the 4.5%
    # benchmark; 60% margin -> raw P/S 22.2x, capped at 10x with a note.
    v = _base(ttm_eps_diluted=-1.0, eps_growth_pct=None, current_price=50.0,
              revenue_growth_pct=40.0, ttm_net_income=600_000_000.0)
    assert v.method == "sales"
    assert v.fair_multiple == pytest.approx(10.0)
    assert v.confidence == "Medium"
    assert any("fair P/S hit the 10× cap" in p for p in v.reasoning)
    assert any("10-year Treasury" in p for p in v.reasoning)


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


# ── FCF-yield cross-check + guardrail honesty (PRD §4.11) ─────────────────────

def test_fcf_note_supports_bullish_signal():
    v = _base(ttm_free_cash_flow=60_000_000.0, market_cap=1_000_000_000.0)
    assert v.signal == "Strong Buy"
    assert "FCF yield 6.0%" in v.fcf_note
    assert "above the 4% hurdle" in v.fcf_note
    assert "Supports the signal" in v.fcf_note


def test_fcf_note_tempers_bullish_signal():
    v = _base(ttm_free_cash_flow=10_000_000.0, market_cap=1_000_000_000.0)
    assert v.signal == "Strong Buy"
    assert "FCF yield 1.0%" in v.fcf_note
    assert "below the 4% hurdle" in v.fcf_note
    assert "Tempers the signal" in v.fcf_note


def test_fcf_note_supports_bearish_signal_when_cash_expensive():
    # growth 2% -> floor P/E 8x -> target 40 vs price 100 -> Strong Sell
    v = _base(eps_growth_pct=2.0, ttm_free_cash_flow=10_000_000.0,
              market_cap=1_000_000_000.0)
    assert v.signal == "Strong Sell"
    assert "Supports the signal" in v.fcf_note


def test_fcf_note_tempers_bearish_signal_when_cash_cheap():
    v = _base(eps_growth_pct=2.0, ttm_free_cash_flow=80_000_000.0,
              market_cap=1_000_000_000.0)
    assert v.signal == "Strong Sell"
    assert "Tempers the signal" in v.fcf_note


def test_fcf_note_negative_cash_flow_bullish():
    v = _base(ttm_free_cash_flow=-50_000_000.0, market_cap=1_000_000_000.0)
    assert "negative" in v.fcf_note
    assert "burning cash" in v.fcf_note


def test_fcf_note_negative_cash_flow_bearish():
    v = _base(eps_growth_pct=2.0, ttm_free_cash_flow=-50_000_000.0,
              market_cap=1_000_000_000.0)
    assert "consistent with the Strong Sell signal" in v.fcf_note


def test_fcf_note_unavailable_without_inputs():
    v = _base()
    assert v.fcf_note == "Cross-check unavailable: TTM free cash flow or market cap not reported."


def test_guardrail_caps_confidence_and_names_bound():
    # Mirror the JNJ case: negative growth slams into both the growth floor
    # and the P/E floor; High confidence would overstate the model's certainty.
    v = _base(current_price=271.85, ttm_eps_diluted=8.62, eps_growth_pct=-7.8)
    assert v.signal == "Strong Sell"
    assert v.confidence == "Medium"
    notes = [p for p in v.reasoning if p.startswith("Note:")]
    assert len(notes) == 1
    assert "growth -7.8% hit the 2% floor" in notes[0]
    assert "fair P/E hit the 8× floor" in notes[0]


def test_guardrail_cap_on_growth_cap_side():
    v = _base(eps_growth_pct=95.0)
    assert v.confidence == "Medium"
    assert any("hit the 40% cap" in p for p in v.reasoning)


def test_no_guardrail_keeps_high_confidence():
    v = _base()
    assert v.confidence == "High"
    assert not any(p.startswith("Note:") for p in v.reasoning)


# ── Batch 27: honest floor-multiple copy for flat/declining earnings ─────────
def test_negative_eps_growth_uses_honest_floor_copy():
    # Mirror the UBER case: -23.6% growth slams into the 2% floor, so the 8x
    # is a distressed-earnings floor, not a PEG implication — the card must
    # not claim "a PEG of 1.5 on that growth implies…".
    v = _base(eps_growth_pct=-23.6, ten_year_yield_pct=2.0)
    assert v.method == "peg"
    assert v.fair_multiple == pytest.approx(8.0)
    assert v.confidence == "Medium"  # guardrail drove the target
    assert not any("on that growth implies" in p for p in v.reasoning)
    assert any("declining" in p and "8.0×" in p for p in v.reasoning)
    assert any("hit the 2% floor" in p for p in v.reasoning)


def test_flat_eps_growth_uses_honest_floor_copy():
    # 0–2% growth gets no growth premium either; same honest framing.
    v = _base(eps_growth_pct=1.7, ten_year_yield_pct=2.0)
    assert v.fair_multiple == pytest.approx(8.0)
    assert v.confidence == "Medium"
    assert not any("on that growth implies" in p for p in v.reasoning)
    assert any("essentially flat" in p for p in v.reasoning)


def test_positive_growth_keeps_peg_copy():
    v = _base(eps_growth_pct=20.0, ten_year_yield_pct=2.0)
    assert any("A PEG of 1.5 on that growth implies" in p for p in v.reasoning)
