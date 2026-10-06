from __future__ import annotations

import datetime as dt
import pytest

from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.services.financials import CompanyOverview, DetailContext, PeriodData, KPISnapshot, KPIChange
from tickerlens.services.valuation import ValuationSignal
from tickerlens.services.ai_analysis import generate_ai_analysis, AIAnalysis


def test_generate_ai_analysis_mega_cap_invest() -> None:
    overview = CompanyOverview(
        cik="0001045810",
        name="NVIDIA CORP",
        ticker="NVDA",
        sector="Technology",
        last_price=225.0,
        market_cap=5_000_000_000_000.0,
        latest_label="Q2 FY2026",
        latest_period_end=dt.date(2026, 7, 28),
        latest_kpi=KPISnapshot(revenue=30000.0, net_income=16000.0, eps_diluted=0.68, free_cash_flow=13000.0),
        yoy=KPIChange(revenue=35.0, net_income=40.0, eps_diluted=38.0, free_cash_flow=30.0),
        ttm_kpi=KPISnapshot(revenue=100000.0, net_income=55000.0, eps_diluted=2.30, free_cash_flow=45000.0),
        ttm_quarters=4,
    )
    val = ValuationSignal(
        ticker="NVDA",
        current_price=225.0,
        target_price=280.0,
        upside_pct=24.4,
        signal="Buy",
        confidence="high",
        method="peg",
        fair_multiple=32.0,
        current_multiple=25.0,
        growth_pct=22.0,
        reasoning=["Strong secular AI tailwinds"],
    )
    rows = [
        QuarterlyFinancial(
            cik="0001045810",
            period_end=dt.date(2026, 7, 28),
            fiscal_year=2026,
            fiscal_period="Q2",
            revenue=30000.0,
            net_income=16000.0,
            eps_diluted=0.68,
            free_cash_flow=13000.0,
            total_assets=85000.0,
            total_liabilities=25000.0,
            total_equity=60000.0,
            cash_and_equivalents=34000.0,
        )
    ] * 4

    analysis = generate_ai_analysis(overview=overview, valuation=val, rows=rows)
    assert isinstance(analysis, AIAnalysis)
    assert analysis.ticker == "NVDA"
    assert analysis.cap_tier == "Mega-Cap"
    assert analysis.signal in ["Invest", "Swing"]
    assert analysis.confidence == "High"
    assert analysis.composite_score >= 70
    assert len(analysis.theses) >= 3
    assert len(analysis.risks) >= 3


def test_generate_ai_analysis_unprofitable_small_cap() -> None:
    overview = CompanyOverview(
        cik="0000999999",
        name="Small Growth Corp",
        ticker="SGC",
        sector="Technology",
        last_price=10.0,
        market_cap=500_000_000.0,  # < $2B => Small-Cap
        latest_label="Q1 FY2026",
        latest_period_end=dt.date(2026, 3, 31),
        latest_kpi=KPISnapshot(revenue=20.0, net_income=-15.0, eps_diluted=-0.50, free_cash_flow=-20.0),
        yoy=KPIChange(revenue=-10.0, net_income=-50.0, eps_diluted=-40.0, free_cash_flow=-60.0),
        ttm_kpi=KPISnapshot(revenue=80.0, net_income=-60.0, eps_diluted=-2.00, free_cash_flow=-80.0),
        ttm_quarters=4,
    )
    val = ValuationSignal(
        ticker="SGC",
        current_price=10.0,
        target_price=6.0,
        upside_pct=-40.0,
        signal="Strong Sell",
        confidence="medium",
        method="sales",
        fair_multiple=1.5,
        current_multiple=2.5,
        growth_pct=-10.0,
        reasoning=["Negative cash flow"],
    )

    analysis = generate_ai_analysis(overview=overview, valuation=val, rows=[])
    assert analysis.cap_tier == "Small-Cap"
    assert analysis.signal == "Avoid"
    assert analysis.composite_score < 50


def test_determine_cap_tier_unknown_focus_is_none() -> None:
    from tickerlens.services.ai_analysis import _determine_cap_tier

    tier, focus = _determine_cap_tier(None)
    assert tier == "Unknown"
    assert focus is None
    tier, focus = _determine_cap_tier(0)
    assert (tier, focus) == ("Unknown", None)
    # Known tiers still carry a focus string for the copy sites.
    tier, focus = _determine_cap_tier(5_000_000_000_000.0)
    assert (tier, focus) == ("Mega-Cap", "Capital Allocation & Moat Durability")


def test_ai_analysis_unknown_tier_copy_reads_clean() -> None:
    """Batch 18 follow-up: Unknown tier must not render 'a Unknown filer
    prioritizing insufficient market data' in the briefing copy."""
    overview = CompanyOverview(
        cik="0001067983",
        name="BERKSHIRE HATHAWAY INC",
        ticker="BRK.B",
        sector="Financial Conglomerates",
        last_price=None,
        market_cap=None,  # missing quote → Unknown tier
        latest_label="Q2 FY2026",
        latest_period_end=dt.date(2026, 6, 30),
        latest_kpi=KPISnapshot(revenue=80000.0, net_income=25000.0, eps_diluted=11.0, free_cash_flow=30000.0),
        yoy=KPIChange(revenue=3.0, net_income=5.0, eps_diluted=4.0, free_cash_flow=2.0),
        ttm_kpi=KPISnapshot(revenue=300000.0, net_income=90000.0, eps_diluted=40.0, free_cash_flow=100000.0),
        ttm_quarters=4,
    )

    analysis = generate_ai_analysis(overview=overview, valuation=None, rows=[])
    assert analysis.cap_tier == "Unknown"

    summary = analysis.executive_summary
    assert "a Unknown" not in summary
    assert "prioritizing insufficient market data" not in summary
    assert "No size tier is assigned" in summary

    assert all("Unknown bracket" not in t for t in analysis.theses)
    assert any("no size-tier emphasis is assigned" in t for t in analysis.theses)

    # A known tier keeps the original phrasing.
    known = generate_ai_analysis(
        overview=CompanyOverview(
            cik="0001045810",
            name="NVIDIA CORP",
            ticker="NVDA",
            sector="Technology",
            last_price=225.0,
            market_cap=5_000_000_000_000.0,
            latest_label="Q2 FY2026",
            latest_period_end=dt.date(2026, 7, 28),
            latest_kpi=KPISnapshot(revenue=30000.0, net_income=16000.0, eps_diluted=0.68, free_cash_flow=13000.0),
            yoy=KPIChange(revenue=35.0, net_income=40.0, eps_diluted=38.0, free_cash_flow=30.0),
            ttm_kpi=KPISnapshot(revenue=100000.0, net_income=55000.0, eps_diluted=2.30, free_cash_flow=45000.0),
            ttm_quarters=4,
        ),
        valuation=None,
        rows=[],
    )
    assert "Evaluated as a Mega-Cap filer prioritizing capital allocation & moat durability." in known.executive_summary
    assert any("Mega-Cap bracket" in t for t in known.theses)
