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


def _bank_overview(**kw):
    """JPMorgan-like overview: levered balance sheet, decent growth."""
    base = dict(
        cik="0000019617",
        name="JPMORGAN CHASE & CO",
        ticker="JPM",
        sector="Banking",
        last_price=300.0,
        market_cap=900_000_000_000.0,
        latest_label="Q2 FY2026",
        latest_period_end=dt.date(2026, 6, 30),
        latest_kpi=KPISnapshot(revenue=40000.0, net_income=13000.0, eps_diluted=4.50, free_cash_flow=20000.0),
        yoy=KPIChange(revenue=10.0, net_income=12.0, eps_diluted=11.0, free_cash_flow=8.0),
        ttm_kpi=KPISnapshot(revenue=150000.0, net_income=49000.0, eps_diluted=16.50, free_cash_flow=60000.0),
        ttm_quarters=4,
    )
    base.update(kw)
    return CompanyOverview(**base)


def _bank_row(ratio: float = 1.08):
    return QuarterlyFinancial(
        cik="0000019617",
        period_end=dt.date(2026, 6, 30),
        fiscal_year=2026,
        fiscal_period="Q2",
        revenue=40000.0,
        net_income=13000.0,
        total_assets=4000000.0,
        total_liabilities=4000000.0 / ratio,
        total_equity=4000000.0 - 4000000.0 / ratio,
    )


def test_solvency_score_sector_aware() -> None:
    """Batch 25: the industrial solvency ladder misread structurally-levered
    balance sheets as distress (every bank scored 40/100 at ~1.08x)."""
    from tickerlens.services.ai_analysis import _solvency_score

    # Financials: 1.05–1.15x assets/liabilities is the business model.
    assert _solvency_score(1.20, "Banking") == 85
    assert _solvency_score(1.08, "Banking") == 75
    assert _solvency_score(1.08, "Securities & Investments") == 75
    assert _solvency_score(1.04, "Insurance") == 65
    assert _solvency_score(1.01, "Banking") == 40  # genuinely thin still fails
    # REITs: levered, but less extremely than banks.
    assert _solvency_score(2.22, "Real Estate") == 85
    assert _solvency_score(1.35, "Real Estate") == 75
    assert _solvency_score(1.19, "Real Estate") == 65
    assert _solvency_score(1.05, "Real Estate") == 40
    # Industrials keep the original ladder.
    assert _solvency_score(2.50, "Manufacturing") == 90
    assert _solvency_score(2.04, "Manufacturing") == 80
    assert _solvency_score(1.50, "Manufacturing") == 65
    assert _solvency_score(1.08, "Manufacturing") == 40
    assert _solvency_score(1.08, None) == 40


def test_ai_analysis_bank_solvency_not_penalized() -> None:
    """Batch 25: a bank at 1.08x assets/liabilities must not score 40/100
    solvency, and its revenue thesis must not talk about 'commercial
    segments'."""
    analysis = generate_ai_analysis(overview=_bank_overview(), valuation=None, rows=[_bank_row(1.08)])
    assert analysis.solvency_score == 75
    rev_thesis = next(t for t in analysis.theses if "YoY in Q2 FY2026" in t)
    assert "commercial segments" not in rev_thesis
    assert "balance-sheet growth and fee-income momentum" in rev_thesis


def test_ai_analysis_reit_solvency_partial_credit() -> None:
    """Batch 25: a REIT at 1.19x gets neutral 65, not distress 40."""
    overview = _bank_overview(sector="Real Estate", ticker="SPG", name="SIMON PROPERTY GROUP INC.")
    analysis = generate_ai_analysis(overview=overview, valuation=None, rows=[_bank_row(1.19)])
    assert analysis.solvency_score == 65


def test_ai_analysis_strong_sell_divergence_note() -> None:
    """Batch 25: when the valuation card says Strong Sell but the
    fundamentals-driven signal is Watch, the briefing must reconcile the two
    instead of silently contradicting the card on the same page."""
    val = ValuationSignal(
        ticker="TSLA",
        current_price=357.45,
        target_price=8.64,
        upside_pct=-97.6,
        signal="Strong Sell",
        confidence="medium",
        method="peg",
        fair_multiple=8.0,
        current_multiple=100.0,
        growth_pct=25.0,
        reasoning=["Deep downside"],
    )
    overview = CompanyOverview(
        cik="0001318605",
        name="Tesla, Inc.",
        ticker="TSLA",
        sector="Manufacturing",
        last_price=357.45,
        market_cap=1_100_000_000_000.0,
        latest_label="Q2 FY2026",
        latest_period_end=dt.date(2026, 6, 30),
        latest_kpi=KPISnapshot(revenue=25000.0, net_income=1200.0, eps_diluted=0.40, free_cash_flow=2000.0),
        yoy=KPIChange(revenue=25.0, net_income=10.0, eps_diluted=8.0, free_cash_flow=5.0),
        ttm_kpi=KPISnapshot(revenue=97000.0, net_income=5000.0, eps_diluted=1.60, free_cash_flow=8000.0),
        ttm_quarters=4,
    )
    rows = [
        QuarterlyFinancial(
            cik="0001318605",
            period_end=dt.date(2026, 6, 30),
            fiscal_year=2026,
            fiscal_period="Q2",
            revenue=25000.0,
            net_income=1200.0,
            total_assets=110000.0,
            total_liabilities=45000.0,
            total_equity=65000.0,
        )
    ] * 4
    analysis = generate_ai_analysis(overview=overview, valuation=val, rows=rows)
    assert analysis.signal == "Watch"  # strong fundamentals, terrible price
    note = next(t for t in analysis.theses if t.startswith("Valuation check:"))
    assert "Strong Sell" in note
    assert "-97.6%" in note
    assert "$8.64" in note


def test_ai_analysis_no_divergence_note_when_aligned() -> None:
    """Batch 25: no reconciliation note when the briefing already says Avoid,
    or when the valuation is not a Strong Sell."""
    weak = _bank_overview(
        sector="Manufacturing",
        ticker="SGC2",
        name="Weak Corp",
        yoy=KPIChange(revenue=-20.0, net_income=-60.0, eps_diluted=-50.0, free_cash_flow=-40.0),
        ttm_kpi=KPISnapshot(revenue=80000.0, net_income=-60000.0, eps_diluted=-2.0, free_cash_flow=-80000.0),
    )
    strong_sell = ValuationSignal(
        ticker="SGC2", current_price=10.0, target_price=6.0, upside_pct=-40.0,
        signal="Strong Sell", confidence="medium", method="sales",
        fair_multiple=1.5, current_multiple=2.5, growth_pct=-10.0,
        reasoning=["Negative cash flow"],
    )
    analysis = generate_ai_analysis(overview=weak, valuation=strong_sell, rows=[])
    assert analysis.signal == "Avoid"
    assert not any(t.startswith("Valuation check:") for t in analysis.theses)

    # Bullish valuation → no note either.
    bullish = ValuationSignal(
        ticker="JPM", current_price=300.0, target_price=390.0, upside_pct=30.0,
        signal="Strong Buy", confidence="high", method="peg",
        fair_multiple=12.0, current_multiple=9.0, growth_pct=10.0,
        reasoning=["Cheap"],
    )
    analysis = generate_ai_analysis(overview=_bank_overview(), valuation=bullish, rows=[_bank_row(1.08)])
    assert not any(t.startswith("Valuation check:") for t in analysis.theses)


def test_ai_analysis_missing_yoy_growth_neutral() -> None:
    """Batch 25: missing YoY data is unknown, not flat — growth scores
    neutral 50 instead of the 55 the flat-growth ladder would award, and no
    revenue thesis is fabricated."""
    overview = _bank_overview(yoy=KPIChange())
    analysis = generate_ai_analysis(overview=overview, valuation=None, rows=[])
    assert analysis.growth_score == 50
    assert not any("YoY in Q2 FY2026" in t for t in analysis.theses)
