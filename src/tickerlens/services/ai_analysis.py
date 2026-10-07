from __future__ import annotations

import re
from typing import Literal
from pydantic import BaseModel

from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.services.financials import CompanyOverview, DetailContext
from tickerlens.services.valuation import ValuationSignal


class AIAnalysis(BaseModel):
    """Integrated fundamental research & AI synthesis briefing (PRD §4.4)."""

    ticker: str
    signal: Literal["Invest", "Swing", "Watch", "Avoid"]
    confidence: Literal["High", "Medium", "Low"]
    cap_tier: str  # "Mega-Cap", "Large-Cap", "Mid-Cap", "Small-Cap", or "Unknown"
    sector: str | None
    composite_score: int  # 0 to 100
    growth_score: int     # 0 to 100
    profitability_score: int  # 0 to 100
    solvency_score: int   # 0 to 100
    valuation_score: int  # 0 to 100
    theses: list[str]     # 3–6 analytical takeaways citing filing metrics
    risks: list[str]      # 3–5 key risks flagged from 10-K & 8-K
    executive_summary: str


def _determine_cap_tier(market_cap: float | None) -> tuple[str, str | None]:
    if not market_cap or market_cap <= 0:
        # Unknown is unknown — never present a confident wrong tier
        # (Berkshire once rendered "Mid-Cap" because its quote was missing).
        # Focus is None so copy sites render an honest "no tier assigned"
        # phrasing instead of claiming to prioritize "insufficient market data".
        return "Unknown", None
    if market_cap >= 200_000_000_000:
        return "Mega-Cap", "Capital Allocation & Moat Durability"
    if market_cap >= 10_000_000_000:
        return "Large-Cap", "Free Cash Flow & Operating Leverage"
    if market_cap >= 2_000_000_000:
        return "Mid-Cap", "Growth-to-Profitability Transition"
    return "Small-Cap", "Cash Runway & Balance Sheet Defense"


def _solvency_score(assets_to_liabilities: float, sector: str | None) -> int:
    """Balance-sheet score on the assets/liabilities ratio, sector-aware.

    The industrial ladder below treats a ratio under 1.2x as weak — but for
    deposit-/premium-funded financials a 1.05–1.15x ratio is the business
    model, not distress (JPMorgan scored 40/100 "solvency" at 1.08x, dragging
    every bank's composite down ~5 points and flipping MET's signal). REITs
    are structurally levered too, though less extremely. Sector ladders keep
    the same 40-point floor for genuinely thin balance sheets.
    """
    sec = (sector or "").lower()
    if any(k in sec for k in ("bank", "securit", "insurance", "financ")):
        if assets_to_liabilities >= 1.15:
            return 85
        if assets_to_liabilities >= 1.08:
            return 75
        if assets_to_liabilities >= 1.03:
            return 65
        return 40
    if "real estate" in sec:
        if assets_to_liabilities >= 1.5:
            return 85
        if assets_to_liabilities >= 1.3:
            return 75
        if assets_to_liabilities >= 1.15:
            return 65
        return 40
    if assets_to_liabilities >= 2.5:
        return 90
    if assets_to_liabilities >= 1.8:
        return 80
    if assets_to_liabilities >= 1.2:
        return 65
    return 40


def _revenue_thesis_tail(sector: str | None) -> str:
    """Sector-aware close for the revenue-growth thesis.

    "Healthy demand across commercial segments" is wrong-register for banks,
    insurers, and brokers, whose "revenue" is net interest / fee income.
    """
    sec = (sector or "").lower()
    if any(k in sec for k in ("bank", "securit", "insurance", "financ")):
        return "reflecting balance-sheet growth and fee-income momentum."
    return "reflecting healthy demand across commercial segments."


def _extract_key_risks(
    risk_factors: str | None,
    guidance: str | None,
    sector: str | None,
) -> list[str]:
    """Flag 3–5 top contextual risk vectors from Item 1A and Guidance."""
    risks: list[str] = []
    text_corpus = f"{risk_factors or ''}\n{guidance or ''}".lower()

    # Rule-based thematic risk detectors
    if any(k in text_corpus for k in ["competition", "competitive pressure", "market share", "rival"]):
        risks.append("Intensified competitive pressure and pricing elasticity in core operating markets.")
    if any(k in text_corpus for k in ["supply chain", "supplier", "components", "manufacturing delays", "vendor"]):
        risks.append("Supply chain dependencies, specialized hardware yields, and input cost volatility.")
    if any(k in text_corpus for k in ["regulatory", "antitrust", "investigation", "compliance", "trade restrictions", "export control"]):
        risks.append("Geopolitical export controls, antitrust inquiries, and tightening regulatory compliance.")
    if any(k in text_corpus for k in ["capex", "capital expenditure", "infrastructure cost", "datacenter", "capacity"]):
        risks.append("High capital expenditure cycles and depreciation drag on near-term operating margins.")
    if any(k in text_corpus for k in ["foreign exchange", "currency", "macroeconomic", "inflation", "interest rate"]):
        risks.append("Macroeconomic headwinds and foreign exchange volatility impacting international sales.")
    if any(k in text_corpus for k in ["customer concentration", "single customer", "enterprise spending"]):
        risks.append("Enterprise customer budget scrutiny and potential customer revenue concentration.")

    # Sector fallbacks if filing text was sparse or missing
    if not risks:
        sec = (sector or "").lower()
        if "tech" in sec:
            risks = [
                "Rapid technological obsolescence and accelerated R&D capital requirements.",
                "Customer procurement and enterprise budget approval cycles.",
                "Global semiconductor and component supply chain capacity.",
            ]
        elif "bank" in sec or "financ" in sec:
            risks = [
                "Net interest margin compression across changing yield curve environments.",
                "Credit loss provisions and commercial loan default rate exposure.",
                "Capital reserve requirements and stringent regulatory stress testing.",
            ]
        else:
            risks = [
                "Macroeconomic consumer demand shifts and discretionary spending elasticity.",
                "Operating margin compression from wage and logistics inflation.",
                "Competitive promotional intensity impacting gross margin realization.",
            ]

    return risks[:5]


def generate_ai_analysis(
    overview: CompanyOverview,
    detail: DetailContext | None = None,
    valuation: ValuationSignal | None = None,
    rows: list[QuarterlyFinancial] | None = None,
) -> AIAnalysis:
    """Generate institutional AI fundamental analysis synthesis (PRD §4.4)."""
    tier_label, tier_focus = _determine_cap_tier(overview.market_cap)

    # 1. Growth Evaluation
    rev_yoy = overview.yoy.revenue if overview.yoy and overview.yoy.revenue is not None else 0.0
    ni_yoy = overview.yoy.net_income if overview.yoy and overview.yoy.net_income is not None else 0.0
    eps_yoy = overview.yoy.eps_diluted if overview.yoy and overview.yoy.eps_diluted is not None else 0.0

    # Missing YoY (e.g. first-seeded tickers) is unknown, not flat — score it
    # neutral 50 rather than the 55 the flat-growth ladder would award.
    has_rev_yoy = overview.yoy is not None and overview.yoy.revenue is not None
    growth_score = 50
    if has_rev_yoy:
        if rev_yoy >= 25.0:
            growth_score = 95
        elif rev_yoy >= 15.0:
            growth_score = 85
        elif rev_yoy >= 5.0:
            growth_score = 70
        elif rev_yoy >= 0.0:
            growth_score = 55
        else:
            growth_score = max(20, int(50 + rev_yoy * 1.5))

    # 2. Profitability & Cash Generation
    ttm_rev = overview.ttm_kpi.revenue or 1.0
    ttm_ni = overview.ttm_kpi.net_income or 0.0
    ttm_fcf = overview.ttm_kpi.free_cash_flow or 0.0

    net_margin = (ttm_ni / ttm_rev) * 100.0 if ttm_rev > 0 else 0.0
    fcf_conversion = (ttm_fcf / ttm_ni) * 100.0 if ttm_ni > 0 else 0.0

    profit_score = 50
    if net_margin >= 25.0:
        profit_score = 92
    elif net_margin >= 15.0:
        profit_score = 80
    elif net_margin >= 5.0:
        profit_score = 65
    elif net_margin > 0.0:
        profit_score = 50
    else:
        profit_score = 30

    if fcf_conversion >= 85.0:
        profit_score = min(100, profit_score + 8)
    elif fcf_conversion < 40.0 and ttm_ni > 0:
        profit_score = max(20, profit_score - 10)

    # 3. Solvency & Balance Sheet (sector-aware: banks/insurers/REITs are
    # structurally levered; the industrial ladder misreads that as distress)
    solvency_score = 65
    latest_row = rows[-1] if rows else None
    if latest_row and latest_row.total_assets and latest_row.total_liabilities:
        solvency_score = _solvency_score(
            latest_row.total_assets / latest_row.total_liabilities,
            overview.sector,
        )

    # 4. Valuation Alignment
    upside = valuation.upside_pct if valuation and valuation.upside_pct is not None else 0.0
    val_score = 50
    if upside >= 30.0:
        val_score = 95
    elif upside >= 10.0:
        val_score = 80
    elif upside >= -10.0:
        val_score = 65
    elif upside >= -25.0:
        val_score = 45
    else:
        val_score = 25

    # Composite Score
    composite_score = int(
        (growth_score * 0.30)
        + (profit_score * 0.30)
        + (solvency_score * 0.20)
        + (val_score * 0.20)
    )

    # Signal Mapping (PRD §4.4: Invest, Swing, Watch, Avoid)
    if composite_score >= 78 and upside >= 5.0:
        signal = "Invest"
    elif composite_score >= 68 and upside >= 15.0:
        signal = "Swing"
    elif composite_score >= 50:
        signal = "Watch"
    else:
        signal = "Avoid"

    # Confidence calculation
    if len(rows or []) >= 4 and valuation and valuation.confidence.lower() == "high":
        confidence = "High"
    elif len(rows or []) >= 2:
        confidence = "Medium"
    else:
        confidence = "Low"

    # Theses points (citing exact metrics)
    theses: list[str] = []
    if rev_yoy != 0:
        theses.append(
            f"Top-line revenue grew {rev_yoy:+.1f}% YoY in {overview.latest_label}, "
            f"{_revenue_thesis_tail(overview.sector)}"
        )
    if net_margin > 0:
        theses.append(
            f"Trailing net margin of {net_margin:.1f}% demonstrates operational leverage and pricing discipline."
        )
    if ttm_fcf > 0:
        theses.append(
            f"Generated ${ttm_fcf/1e9:.2f}B in trailing Free Cash Flow, supporting ongoing organic reinvestment and balance sheet liquidity."
        )
    elif ttm_fcf < 0:
        theses.append(
            f"Free cash flow burn of -${abs(ttm_fcf)/1e9:.2f}B indicates elevated capital expenditure intensity or cyclical working capital requirements."
        )

    if valuation and valuation.target_price:
        theses.append(
            f"Model price target of ${valuation.target_price:.2f} implies {upside:+.1f}% upside against current trading quote of ${overview.last_price or 0:.2f}."
        )
        # Reconcile with the valuation card: when the model rates the stock a
        # Strong Sell but the fundamentals-driven signal is Watch or better,
        # say so explicitly instead of silently contradicting the card on the
        # same page (e.g. TSLA: Watch 66/100 next to Strong Sell −97.6%).
        if (
            valuation.signal == "Strong Sell"
            and valuation.upside_pct is not None
            and signal in ("Invest", "Swing", "Watch")
        ):
            theses.append(
                f"Valuation check: the model rates {overview.ticker} a Strong Sell "
                f"({valuation.upside_pct:+.1f}% implied downside to the "
                f"${valuation.target_price:.2f} target) — the '{signal}' rating "
                "above rests on fundamentals, not on price."
            )

    if tier_focus is not None:
        theses.append(
            f"Positioned in the {tier_label} bracket with institutional emphasis on {tier_focus.lower()}."
        )
    else:
        # No market cap → no honest tier emphasis; say so instead of
        # claiming to prioritize "insufficient market data".
        theses.append(
            "Market capitalization data is unavailable, so no size-tier emphasis is assigned — "
            "the score stands on fundamentals alone."
        )

    # Flagged Risks
    rf = detail.risk_factors if detail else None
    mg = detail.management_guidance if detail else None
    risks = _extract_key_risks(rf, mg, overview.sector)

    # Executive Summary
    # "a {tier}" is grammatical for every known tier (Mega-/Large-/Mid-/Small-Cap);
    # Unknown never reaches the article branch — it gets the honest phrasing instead.
    tier_clause = (
        f"Evaluated as a {tier_label} filer prioritizing {tier_focus.lower()}."
        if tier_focus is not None
        else "No size tier is assigned — market capitalization data is insufficient."
    )
    summary = (
        f"{overview.name} ({overview.ticker}) scores {composite_score}/100 in fundamental strength with an "
        f"'{signal}' rating ({confidence} confidence). {tier_clause}"
    )

    return AIAnalysis(
        ticker=overview.ticker or "",
        signal=signal,
        confidence=confidence,
        cap_tier=tier_label,
        sector=overview.sector,
        composite_score=composite_score,
        growth_score=growth_score,
        profitability_score=profit_score,
        solvency_score=solvency_score,
        valuation_score=val_score,
        theses=theses[:6],
        risks=risks,
        executive_summary=summary,
    )
