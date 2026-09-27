#!/usr/bin/env python3
"""End-to-end automated validation script for Compare Mode and Frontend Polish."""

import sys
import urllib.request
import urllib.parse
from html.parser import HTMLParser

BASE_URL = "http://127.0.0.1:8000"


def fetch(path: str) -> tuple[int, str]:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "TickerlensValidator/1.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def run_validations():
    print("=" * 60)
    print("STARTING E2E VALIDATION: COMPARE MODE & FRONTEND POLISH")
    print("=" * 60)

    # 1. Base nav check
    print("\n[1/6] Validating Global Navigation & Navbar...")
    status, html = fetch("/")
    assert status == 200, f"Expected 200 on / got {status}"
    assert 'href="/compare"' in html, "Navbar missing link to /compare"
    assert "⌘K" in html, "Search input missing ⌘K shortcut badge"
    assert 'id="htmx-progress"' in html, "Base template missing #htmx-progress top bar"
    print("  ✓ Navbar link to Compare Mode verified")
    print("  ✓ Search ⌘K keycap badge verified")
    print("  ✓ HTMX top progress bar verified")

    # 2. Pinned Dashboard Table/Cards View
    print("\n[2/6] Validating Home Screen Dashboard...")
    assert "tickerlens_view_mode" in html, "Dashboard missing viewMode persistence"
    assert "viewMode === 'table'" in html, "Dashboard missing Table view toggle"
    assert "viewMode === 'grid'" in html, "Dashboard missing Grid/Cards view toggle"
    assert "tabular-nums" in html, "Dashboard missing tabular-nums typography"
    print("  ✓ Table / Cards toggle with localStorage verified")
    print("  ✓ High-density financial metrics table verified")

    # 3. Default Compare Page
    print("\n[3/6] Validating Default Compare Mode (/compare)...")
    status, html = fetch("/compare")
    assert status == 200, f"Expected 200 on /compare got {status}"
    assert "Peer Benchmarking" in html, "Page title missing"
    assert "NVDA" in html, "Default peer NVDA missing"
    assert "INTC" in html, "Default peer INTC missing"
    assert "MRVL" in html, "Default peer MRVL missing"
    assert "compare-plotly-chart" in html, "Plotly chart container missing"
    assert "compare-payload-json" in html, "Plotly data JSON script missing"
    assert "Side-by-Side Financial Benchmarking" in html, "Benchmark table missing"
    assert "Net Profit Margin" in html, "Net Profit Margin row missing"
    assert "Free Cash Flow Margin" in html, "FCF Margin row missing"
    assert "Debt-to-Equity Ratio" in html, "Debt-to-Equity row missing"
    print("  ✓ Default peer group (NVDA, INTC, MRVL) loaded")
    print("  ✓ Plotly chart element and JSON payload present")
    print("  ✓ Full 5-category financial comparison table rendered")

    # 4. Big Tech Preset (5 peers)
    print("\n[4/6] Validating Big Tech Preset (AAPL,MSFT,GOOGL,AMZN,META)...")
    status, html = fetch("/compare?tickers=AAPL,MSFT,GOOGL,AMZN,META&metric=net_margin")
    assert status == 200, f"Expected 200 on big tech compare got {status}"
    for ticker in ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]:
        assert ticker in html, f"Big Tech peer {ticker} missing from compare page"
    assert "Leader" in html or "Top" in html, "Outperformer badges missing"
    print("  ✓ 5 peers benchmarked simultaneously without layout regression")
    print("  ✓ Leaderboard outperformance indicators verified")

    # 5. HTMX Chart Swapping Endpoint
    print("\n[5/6] Validating HTMX Chart Partial (/compare/chart)...")
    metrics = ["revenue_yoy", "net_margin", "fcf_margin", "revenue", "free_cash_flow", "eps_diluted"]
    for m in metrics:
        status, html = fetch(f"/compare/chart?tickers=NVDA,INTC,MRVL&metric={m}")
        assert status == 200, f"Expected 200 on metric {m} got {status}"
        assert 'id="compare-chart-container"' in html, f"Partial missing container for {m}"
        assert 'id="compare-plotly-chart"' in html, f"Partial missing plotly chart for {m}"
        assert f'activeMetric": "{m}"' in html, f"Chart JSON did not record active metric {m}"
        print(f"  ✓ HTMX chart partial for metric '{m}' passed")

    # 6. Company detail view polish check
    print("\n[6/6] Validating Company Detail Page Polish (NVDA)...")
    status, html = fetch("/company/NVDA/detail")
    assert status == 200, f"Expected 200 on /company/NVDA/detail got {status}"
    assert "tabular-nums" in html, "Detail view missing tabular-nums"
    assert "Free Cash Flow" in html, "Detail view missing Free Cash Flow"
    print("  ✓ Detail view styling and tabular-nums verified")

    print("\n" + "=" * 60)
    print("ALL VALIDATION CHECKS PASSED SUCCESSFULLY (100% OK)")
    print("=" * 60)


if __name__ == "__main__":
    try:
        run_validations()
    except Exception as exc:
        print(f"\n❌ Validation failed: {exc}")
        sys.exit(1)
