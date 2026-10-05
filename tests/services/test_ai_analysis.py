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
