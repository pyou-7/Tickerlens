"""Rules-based valuation signal: model target price vs current price.

v1 methodology (PRD §4.11) — deliberately a simple, explainable heuristic, not
a DCF. All inputs come from the company's own EDGAR-derived financials plus a
Yahoo quote; every number on the card is auditable from the reasoning bullets.

Primary method ("peg"): PEG-implied P/E for profitable companies.
    fair_pe = PEG_TARGET * eps_growth_pct   (growth clamped, P/E clamped)
    target  = ttm_diluted_eps * fair_pe

Fallback ("sales"): for companies without positive earnings.
    fair_ps = 0.5 * revenue_growth_pct      (growth clamped, P/S clamped)
    target  = ttm_revenue * fair_ps / shares_outstanding

Signal thresholds are on implied upside = (target - price) / price.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# PEG of 1.5 ~= "fair" multiple for a quality grower (Peter Lynch's rule of
# thumb is PEG <= 1 for cheap; 1.5 leaves headroom so only genuine growers
# screen as Buys).
PEG_TARGET = 1.5
# Growth above 40% rarely persists; below 2% deserves no growth premium.
_MIN_GROWTH_PCT = 2.0
_MAX_GROWTH_PCT = 40.0
# Sanity clamps so the model never emits a 200x P/E or a distressed 3x.
_MIN_PE = 8.0
_MAX_PE = 40.0
_MIN_PS = 1.0
_MAX_PS = 10.0

_STRONG_BUY_UP = 30.0
_BUY_UP = 10.0
_SELL_DOWN = -10.0
_STRONG_SELL_DOWN = -25.0


class ValuationSignal(BaseModel):
    """Everything the Overview valuation card needs."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    current_price: float | None
    target_price: float | None
    upside_pct: float | None  # implied upside in percent, e.g. 23.5
    signal: str  # Strong Buy | Buy | Hold | Sell | Strong Sell | Watch
    confidence: str  # High | Medium | Low
    method: str  # "peg" | "sales" | "unavailable"
    fair_multiple: float | None  # the P/E or P/S the model deemed fair
    current_multiple: float | None  # where the market prices it today
    growth_pct: float | None  # the growth input, in percent
    reasoning: list[str]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _signal_for_upside(upside_pct: float) -> str:
    if upside_pct >= _STRONG_BUY_UP:
        return "Strong Buy"
    if upside_pct >= _BUY_UP:
        return "Buy"
    if upside_pct >= _SELL_DOWN:
        return "Hold"
    if upside_pct >= _STRONG_SELL_DOWN:
        return "Sell"
    return "Strong Sell"


def compute_valuation(
    *,
    ticker: str,
    current_price: float | None,
    ttm_eps_diluted: float | None,
    eps_growth_pct: float | None,
    ttm_revenue: float | None,
    revenue_growth_pct: float | None,
    shares_outstanding: float | None,
    ttm_quarters: int = 4,
    growth_is_fallback: bool = False,
) -> ValuationSignal:
    """Compute the valuation signal from TTM financials and a market price.

    Pure function — all inputs are plain numbers so the math is unit-testable
    without a database. ``growth_is_fallback`` marks that the growth input
    came from a quarterly YoY / net-income proxy rather than TTM-over-TTM.
    """
    if current_price is None or current_price <= 0:
        return ValuationSignal(
            ticker=ticker,
            current_price=current_price,
            target_price=None,
            upside_pct=None,
            signal="Watch",
            confidence="Low",
            method="unavailable",
            fair_multiple=None,
            current_multiple=None,
            growth_pct=None,
            reasoning=[
                "No current price available — refresh the company to fetch a quote.",
                "Target price needs a market price to compare against.",
            ],
        )

    confidence = (
        "High"
        if ttm_quarters >= 4 and not growth_is_fallback
        else "Medium"
    )

    # ── Primary: PEG-implied P/E ──────────────────────────────────────────
    if ttm_eps_diluted is not None and ttm_eps_diluted > 0 and eps_growth_pct is not None:
        growth = _clamp(eps_growth_pct, _MIN_GROWTH_PCT, _MAX_GROWTH_PCT)
        fair_pe = _clamp(PEG_TARGET * growth, _MIN_PE, _MAX_PE)
        target = ttm_eps_diluted * fair_pe
        current_pe = current_price / ttm_eps_diluted
        upside = (target - current_price) / current_price * 100.0
        return ValuationSignal(
            ticker=ticker,
            current_price=current_price,
            target_price=round(target, 2),
            upside_pct=round(upside, 1),
            signal=_signal_for_upside(upside),
            confidence=confidence,
            method="peg",
            fair_multiple=round(fair_pe, 1),
            current_multiple=round(current_pe, 1),
            growth_pct=round(eps_growth_pct, 1),
            reasoning=[
                f"TTM diluted EPS ${ttm_eps_diluted:.2f}, growing {eps_growth_pct:.1f}% year over year.",
                f"A PEG of {PEG_TARGET} on that growth implies a fair P/E of {fair_pe:.1f}× "
                f"(current P/E is {current_pe:.1f}×).",
                f"Fair value ≈ ${target:.2f} vs ${current_price:.2f} today "
                f"({upside:+.1f}% implied upside).",
            ],
        )

    # ── Fallback: sales-based target when earnings are unusable ────────────
    if (
        ttm_revenue is not None
        and ttm_revenue > 0
        and revenue_growth_pct is not None
        and shares_outstanding is not None
        and shares_outstanding > 0
    ):
        growth = _clamp(revenue_growth_pct, _MIN_GROWTH_PCT, _MAX_GROWTH_PCT)
        fair_ps = _clamp(0.5 * growth, _MIN_PS, _MAX_PS)
        target = ttm_revenue * fair_ps / shares_outstanding
        current_ps = current_price * shares_outstanding / ttm_revenue
        upside = (target - current_price) / current_price * 100.0
        return ValuationSignal(
            ticker=ticker,
            current_price=current_price,
            target_price=round(target, 2),
            upside_pct=round(upside, 1),
            signal=_signal_for_upside(upside),
            confidence="Medium" if confidence == "High" else confidence,
            method="sales",
            fair_multiple=round(fair_ps, 1),
            current_multiple=round(current_ps, 1),
            growth_pct=round(revenue_growth_pct, 1),
            reasoning=[
                "No positive TTM earnings — valuing on sales instead (less reliable).",
                f"TTM revenue growing {revenue_growth_pct:.1f}% implies a fair P/S of {fair_ps:.1f}× "
                f"(current P/S is {current_ps:.1f}×).",
                f"Fair value ≈ ${target:.2f} vs ${current_price:.2f} today "
                f"({upside:+.1f}% implied upside).",
            ],
        )

    # ── Nothing usable ────────────────────────────────────────────────────
    return ValuationSignal(
        ticker=ticker,
        current_price=current_price,
        target_price=None,
        upside_pct=None,
        signal="Watch",
        confidence="Low",
        method="unavailable",
        fair_multiple=None,
        current_multiple=None,
        growth_pct=None,
        reasoning=[
            "Not enough earnings history to build a target price.",
            "Watch the fundamentals until TTM earnings turn positive.",
        ],
    )
