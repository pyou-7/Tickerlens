#!/usr/bin/env python3
"""
Comprehensive Ingestion and Validation Script for 10 Working Companies.
Validates:
1. Stock price chart data and Yahoo Finance integration.
2. Financial trend chart data (dates, labels, metrics).
3. YoY and QoQ KPI and table calculations.
4. Income statement, Balance sheet, and Cash flow (OCF, Capex, FCF) tables.
5. Narrative disclosures: Risk factors, Press releases, Guidance, Executive commentary.
6. Full FastAPI HTTP endpoints for all 10 companies.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient
from tickerlens.main import app
from tickerlens.services.financials import FinancialsService
from tickerlens.data.yahoo import get_price_history
from tickerlens.models.database import get_session
from tickerlens.models.company import Company
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from sqlalchemy import select

TARGET_TICKERS = [
    "AAPL",
    "MSFT",
    "ORCL",
    "NVDA",
    "TSLA",
    "AMZN",
    "GOOGL",
    "INTC",
    "MRVL",
    "META",
]

def ingest_and_validate():
    svc = FinancialsService()
    client = TestClient(app)
    results = {}

    print(f"=== Starting Ingestion & Validation for {len(TARGET_TICKERS)} Companies ===")

    for ticker in TARGET_TICKERS:
        print(f"\n[{ticker}] Ingesting and enriching...")
        try:
            # 1. Fetch & persist financials
            financials = svc.fetch_and_persist(ticker, periods=8)
            print(f"  [{ticker}] Financial periods persisted: {len(financials)}")

            # 2. Enrich company (Price, Market Cap, Description, Risk Factors)
            svc.enrich_company(ticker)
            print(f"  [{ticker}] Company enriched (Quote, Description, Risk Factors)")

            # 3. Enrich earnings releases (Press release highlights, Guidance, Commentary)
            pr_updated = svc.enrich_press_releases(ticker, periods=8)
            print(f"  [{ticker}] Press releases/exhibits updated: {pr_updated} quarters")

            # 4. Fetch and cache stock price history
            history = get_price_history(ticker, "1y")
            print(f"  [{ticker}] Price history points: {len(history.prices)}")

        except Exception as e:
            print(f"  [{ticker}] ERROR during ingestion: {e}")
            results[ticker] = {"status": "FAILED_INGESTION", "error": str(e)}
            continue

        # Validation Checks
        checks = {}

        # 5. Check Overview data
        try:
            overview = svc.get_overview(ticker)
            checks["has_overview"] = True
            checks["latest_label"] = overview.latest_label
            checks["yoy_revenue"] = overview.yoy.revenue is not None
            checks["ttm_revenue"] = overview.ttm_kpi.revenue is not None
            checks["last_price"] = overview.last_price is not None
        except Exception as e:
            checks["has_overview"] = False
            checks["overview_error"] = str(e)

        # 6. Check Detail context
        try:
            ctx = svc.get_detail(ticker, granularity="quarterly")
            checks["has_detail"] = True
            checks["quarter_count"] = len(ctx.quarter_options)
            checks["has_risk_factors"] = bool(ctx.risk_factors and len(ctx.risk_factors) > 100)
            
            # Check current period financials
            curr = ctx.current
            kpi = curr.kpi
            bs = curr.balance_sheet

            checks["income_statement_complete"] = (
                kpi.revenue is not None
                and kpi.net_income is not None
                and kpi.eps_diluted is not None
            )
            checks["balance_sheet_complete"] = (
                bs.total_assets is not None
                and bs.total_liabilities is not None
                and bs.total_equity is not None
                and bs.cash_and_equivalents is not None
            )
            checks["cash_flow_complete"] = (
                kpi.free_cash_flow is not None
                and kpi.operating_cash_flow is not None
                and kpi.capex is not None
            )

            # Check YoY and QoQ
            checks["yoy_revenue_present"] = curr.yoy.revenue is not None
            checks["qoq_revenue_present"] = curr.qoq is not None and curr.qoq.revenue is not None

            # Check disclosures
            checks["has_press_release"] = bool(curr.press_release)
            checks["has_guidance_or_commentary"] = bool(curr.guidance or curr.executive_commentary)

            # Check chart metrics
            chart_keys = set(ctx.chart_metrics.keys())
            required_keys = {
                "revenue", "net_income", "free_cash_flow",
                "operating_cash_flow", "capex",
                "total_assets", "total_liabilities", "total_equity", "cash_and_equivalents",
            }
            checks["all_chart_metrics_present"] = required_keys.issubset(chart_keys)
            checks["chart_dates_chronological"] = ctx.chart_dates == sorted(ctx.chart_dates)

        except Exception as e:
            checks["has_detail"] = False
            checks["detail_error"] = str(e)

        # 7. Check HTTP Endpoints via TestClient
        try:
            resp_ov = client.get(f"/company/{ticker}")
            checks["http_overview_200"] = resp_ov.status_code == 200

            resp_det = client.get(f"/company/{ticker}/detail")
            checks["http_detail_200"] = resp_det.status_code == 200

            resp_data = client.get(f"/company/{ticker}/detail/data")
            checks["http_detail_data_200"] = resp_data.status_code == 200

            resp_price = client.get(f"/company/{ticker}/price-history?range_key=1y")
            checks["http_price_200"] = (
                resp_price.status_code == 200
                and len(resp_price.json().get("prices", [])) > 0
            )
        except Exception as e:
            checks["http_error"] = str(e)

        # Overall validation status
        passed = (
            checks.get("has_overview", False)
            and checks.get("has_detail", False)
            and checks.get("income_statement_complete", False)
            and checks.get("balance_sheet_complete", False)
            and checks.get("cash_flow_complete", False)
            and checks.get("has_risk_factors", False)
            and checks.get("all_chart_metrics_present", False)
            and checks.get("chart_dates_chronological", False)
            and checks.get("http_overview_200", False)
            and checks.get("http_detail_200", False)
            and checks.get("http_detail_data_200", False)
            and checks.get("http_price_200", False)
        )

        results[ticker] = {
            "passed": passed,
            "checks": checks,
        }

        print(f"  [{ticker}] Result: {'PASSED' if passed else 'FAILED'}")
        for k, v in checks.items():
            print(f"     - {k}: {v}")

    # Summary
    print("\n" + "=" * 60)
    print("FINAL VALIDATION SUMMARY:")
    passed_count = sum(1 for r in results.values() if r.get("passed"))
    print(f"Passed: {passed_count} / {len(TARGET_TICKERS)} Companies")
    for t, r in results.items():
        status = "PASSED" if r.get("passed") else "FAILED"
        print(f"  {t:5s}: {status}")

    if passed_count < 10:
        print(f"\nFAILED: Expected at least 10 working companies, but got {passed_count}")
        sys.exit(1)
    else:
        print(f"\nSUCCESS: All {passed_count} companies passed validation!")
        sys.exit(0)

if __name__ == "__main__":
    ingest_and_validate()
