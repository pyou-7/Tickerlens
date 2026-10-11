"""Discounted Cash Flow (DCF) model and sensitivity matrix.

Provides an intrinsic cash-flow valuation cross-check and a multi-dimensional
sensitivity grid (Discount Rate vs. Terminal Growth Rate) based on EDGAR-derived
Free Cash Flow.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# Standard institutional base parameters
_DEFAULT_BASE_GROWTH_PCT = 8.0
_MIN_BASE_GROWTH_PCT = 2.0
_MAX_BASE_GROWTH_PCT = 25.0

_BASE_DISCOUNT_RATE_PCT = 9.0
_DISCOUNT_RATES_PCT = [7.0, 8.0, 9.0, 10.0, 11.0]

_BASE_TERMINAL_GROWTH_PCT = 2.5
_TERMINAL_GROWTH_RATES_PCT = [1.5, 2.0, 2.5, 3.0, 3.5]

_MIN_RATE_SPREAD = 0.015  # Minimum denominator guard (WACC - g_term >= 1.5%)


class DCFProjectionYear(BaseModel):
    """A single projected year in the 5-year DCF schedule."""

    model_config = ConfigDict(frozen=True)

    year: int
    projected_fcf: float
    pv_fcf: float
    growth_rate_pct: float


class DCFSensitivityCell(BaseModel):
    """A single cell in the discount rate vs terminal growth rate matrix."""

    model_config = ConfigDict(frozen=True)

    discount_rate_pct: float
    terminal_growth_pct: float
    fair_value_per_share: float
    upside_pct: float | None
    is_base_case: bool = False


class DCFModelResult(BaseModel):
    """Complete DCF valuation output, projections, and sensitivity matrix."""

    model_config = ConfigDict(frozen=True)

    is_applicable: bool
    unavailability_reason: str | None = None

    # Baseline Inputs
    base_fcf: float | None = None
    current_price: float | None = None
    shares_outstanding: float | None = None

    # Model Parameters
    base_growth_rate_pct: float | None = None
    base_discount_rate_pct: float | None = None
    base_terminal_growth_pct: float | None = None

    # Intrinsic Valuation Outputs
    enterprise_value: float | None = None
    pv_projected_fcf_sum: float | None = None
    pv_terminal_value: float | None = None
    fair_value_per_share: float | None = None
    upside_pct: float | None = None

    # 5-Year Schedule
    projections: list[DCFProjectionYear] = []

    # 5x5 Sensitivity Matrix
    discount_rates: list[float] = []
    terminal_growth_rates: list[float] = []
    matrix: list[list[DCFSensitivityCell]] = []


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def compute_dcf(
    *,
    ticker: str,
    ttm_free_cash_flow: float | None,
    shares_outstanding: float | None,
    current_price: float | None,
    eps_growth_pct: float | None = None,
    sic: str | None = None,
) -> DCFModelResult:
    """Compute a 5-year DCF model and 5x5 sensitivity matrix.

    Returns is_applicable=False with an honest explanatory reason if:
    - SIC is in 6000-6999 (financial institution / lender / insurer)
    - TTM Free Cash Flow is non-positive or missing
    - Shares outstanding or current price are non-positive or missing
    """
    ticker_upper = ticker.upper()

    # Financial institutions: FCF is not an operational cash-generation metric
    if sic and sic.isdigit() and 6000 <= int(sic) <= 6999:
        return DCFModelResult(
            is_applicable=False,
            unavailability_reason=(
                f"DCF intrinsic valuation is not suitable for financial institutions "
                f"({ticker_upper}, SIC {sic}). Operating cash flow for banks and insurers "
                f"is dominated by loan issuances, deposits, and investment portfolio flows "
                f"rather than enterprise cash generation."
            ),
        )

    if ttm_free_cash_flow is None:
        return DCFModelResult(
            is_applicable=False,
            unavailability_reason=(
                f"Free Cash Flow data is not reported for {ticker_upper}. "
                f"A DCF valuation requires reported operating cash flow and capital expenditures."
            ),
        )

    if ttm_free_cash_flow <= 0:
        fcf_b = ttm_free_cash_flow / 1e9
        return DCFModelResult(
            is_applicable=False,
            base_fcf=round(ttm_free_cash_flow, 2),
            current_price=current_price,
            unavailability_reason=(
                f"Trailing Free Cash Flow is negative (${fcf_b:.2f}B). "
                f"Discounted Cash Flow models require positive normalized cash generation "
                f"to establish intrinsic enterprise value. Explore multiple-based sensitivity above."
            ),
        )

    if not shares_outstanding or shares_outstanding <= 0:
        return DCFModelResult(
            is_applicable=False,
            base_fcf=round(ttm_free_cash_flow, 2),
            current_price=current_price,
            unavailability_reason="Shares outstanding data unavailable to compute per-share DCF value.",
        )

    if not current_price or current_price <= 0:
        return DCFModelResult(
            is_applicable=False,
            base_fcf=round(ttm_free_cash_flow, 2),
            shares_outstanding=shares_outstanding,
            unavailability_reason="Current market quote unavailable to compare against DCF value.",
        )

    # Growth rate selection: use trailing growth rate if positive, clamped to [2%, 25%]
    if eps_growth_pct is not None and eps_growth_pct > 0:
        base_growth = _clamp(eps_growth_pct, _MIN_BASE_GROWTH_PCT, _MAX_BASE_GROWTH_PCT)
    else:
        base_growth = _DEFAULT_BASE_GROWTH_PCT

    base_wacc = _BASE_DISCOUNT_RATE_PCT
    base_g_term = _BASE_TERMINAL_GROWTH_PCT

    # 5-year FCF schedule with gradual growth decay (1.0 -> 0.9 -> 0.8 -> 0.7 -> 0.6)
    decay_factors = [1.0, 0.90, 0.80, 0.70, 0.60]
    projections: list[DCFProjectionYear] = []
    curr_fcf = ttm_free_cash_flow

    for year_idx, decay in enumerate(decay_factors, start=1):
        year_growth_pct = base_growth * decay
        curr_fcf = curr_fcf * (1.0 + year_growth_pct / 100.0)
        pv_fcf = curr_fcf / pow(1.0 + base_wacc / 100.0, year_idx)
        projections.append(
            DCFProjectionYear(
                year=year_idx,
                projected_fcf=round(curr_fcf, 2),
                pv_fcf=round(pv_fcf, 2),
                growth_rate_pct=round(year_growth_pct, 1),
            )
        )

    # Base case valuation
    pv_projected_fcf_sum = sum(p.pv_fcf for p in projections)
    fcf_year_5 = projections[-1].projected_fcf

    spread = max(_MIN_RATE_SPREAD, (base_wacc - base_g_term) / 100.0)
    terminal_value = (fcf_year_5 * (1.0 + base_g_term / 100.0)) / spread
    pv_terminal_value = terminal_value / pow(1.0 + base_wacc / 100.0, 5)

    enterprise_value = pv_projected_fcf_sum + pv_terminal_value
    fair_value_per_share = enterprise_value / shares_outstanding
    upside_pct = (fair_value_per_share - current_price) / current_price * 100.0

    # Build 5x5 sensitivity matrix
    matrix: list[list[DCFSensitivityCell]] = []
    for r_pct in _DISCOUNT_RATES_PCT:
        row: list[DCFSensitivityCell] = []
        r_dec = r_pct / 100.0
        # Recompute PV of 5-year schedule under this discount rate
        pv_fcf_for_r = sum(
            p.projected_fcf / pow(1.0 + r_dec, p.year) for p in projections
        )

        for gt_pct in _TERMINAL_GROWTH_RATES_PCT:
            gt_dec = gt_pct / 100.0
            r_spread = max(_MIN_RATE_SPREAD, r_dec - gt_dec)
            tv = (fcf_year_5 * (1.0 + gt_dec)) / r_spread
            pv_tv = tv / pow(1.0 + r_dec, 5)
            ev = pv_fcf_for_r + pv_tv
            per_share = ev / shares_outstanding
            cell_upside = (per_share - current_price) / current_price * 100.0
            is_base = (r_pct == base_wacc and gt_pct == base_g_term)

            row.append(
                DCFSensitivityCell(
                    discount_rate_pct=r_pct,
                    terminal_growth_pct=gt_pct,
                    fair_value_per_share=round(per_share, 2),
                    upside_pct=round(cell_upside, 1),
                    is_base_case=is_base,
                )
            )
        matrix.append(row)

    return DCFModelResult(
        is_applicable=True,
        base_fcf=round(ttm_free_cash_flow, 2),
        current_price=round(current_price, 2),
        shares_outstanding=round(shares_outstanding, 2),
        base_growth_rate_pct=round(base_growth, 1),
        base_discount_rate_pct=round(base_wacc, 1),
        base_terminal_growth_pct=round(base_g_term, 1),
        enterprise_value=round(enterprise_value, 2),
        pv_projected_fcf_sum=round(pv_projected_fcf_sum, 2),
        pv_terminal_value=round(pv_terminal_value, 2),
        fair_value_per_share=round(fair_value_per_share, 2),
        upside_pct=round(upside_pct, 1),
        projections=projections,
        discount_rates=_DISCOUNT_RATES_PCT,
        terminal_growth_rates=_TERMINAL_GROWTH_RATES_PCT,
        matrix=matrix,
    )
