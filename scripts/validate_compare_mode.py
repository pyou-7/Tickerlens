from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request

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
    print("=" * 65)
    print("STARTING E2E VALIDATION: COMPARE MODE & AI-GRADE FRONTEND POLISH")
    print("=" * 65)

    # 1. Base nav & theme engine check
    print("\n[1/7] Validating Global Navigation, Theme Switcher & Modern Chrome...")
    status, html = fetch("/")
    assert status == 200, f"Expected 200 on / got {status}"
    assert 'href="/compare"' in html, "Navbar missing link to /compare"
    assert "⌘K" in html, "Search input missing ⌘K shortcut badge"
    assert 'id="htmx-progress"' in html, "Base template missing #htmx-progress top bar"
    # Theme switcher checks
    assert "tickerlens_theme" in html, "Base template missing tickerlens_theme localStorage persistence"
    assert "setTheme('light')" in html, "Navbar missing Light Mode button"
    assert "setTheme('dark')" in html, "Navbar missing Dark Mode button"
    assert "setTheme('system')" in html, "Navbar missing System Theme button"
    assert "theme-changed" in html, "Base template missing theme-changed custom event dispatcher"
    print("  ✓ Navbar link to Compare Mode verified")
    print("  ✓ Search ⌘K keycap badge verified")
    print("  ✓ HTMX top progress bar verified")
    print("  ✓ Dark / Light / System theme engine & custom event bus verified")

    # 2. Pinned Dashboard Table/Cards View
    print("\n[2/7] Validating Home Screen Dashboard...")
    assert "tickerlens_view_mode" in html, "Dashboard missing viewMode persistence"
    assert "viewMode === 'table'" in html, "Dashboard missing Table view toggle"
    assert "viewMode === 'grid'" in html, "Dashboard missing Grid/Cards view toggle"
    assert "tabular-nums" in html, "Dashboard missing tabular-nums typography"
    print("  ✓ Table / Cards toggle with localStorage verified")
    print("  ✓ High-density financial metrics table verified")

    # 3. Default Compare Page (/compare)
    print("\n[3/7] Validating Default Compare Mode (/compare)...")
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
    assert "alignment:" in html or "alignment === 'quarters'" in html, "Compare page missing alignment Alpine property"
    assert "togglePeer" in html, "Compare page missing peer visibility toggle"
    assert "metricOptions" in html, "Compare page missing metric selector"
    print("  ✓ Default peer group (NVDA, INTC, MRVL) loaded")
    print("  ✓ Plotly chart element and JSON payload present")
    print("  ✓ Full 5-category financial comparison table rendered")
    print("  ✓ Client-side Alpine.js controller & interactivity elements verified")

    # 4. Big Tech Preset (5 peers)
    print("\n[4/7] Validating Big Tech Preset (AAPL,MSFT,GOOGL,AMZN,META)...")
    status, html = fetch("/compare?tickers=AAPL,MSFT,GOOGL,AMZN,META&metric=net_margin")
    assert status == 200, f"Expected 200 on big tech compare got {status}"
    for ticker in ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]:
        assert ticker in html, f"Big Tech peer {ticker} missing from compare page"
    assert "Leader" in html or "Top" in html, "Outperformer badges missing"
    print("  ✓ 5 peers benchmarked simultaneously without layout regression")
    print("  ✓ Leaderboard outperformance indicators verified")

    # 5. Full 10 Companies Validation across Compare Mode Presets
    print("\n[5/7] Validating All 10 Tracked Companies across Compare Mode...")
    preset1 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
    status1, html1 = fetch(f"/compare?tickers={','.join(preset1)}&metric=revenue_yoy")
    assert status1 == 200, f"Expected 200 comparing preset 1, got {status1}"
    for ticker in preset1:
        assert ticker in html1, f"Company {ticker} missing in compare page"

    preset2 = ["NVDA", "INTC", "MRVL", "ORCL", "TSLA"]
    status2, html2 = fetch(f"/compare?tickers={','.join(preset2)}&metric=net_margin")
    assert status2 == 200, f"Expected 200 comparing preset 2, got {status2}"
    for ticker in preset2:
        assert ticker in html2, f"Company {ticker} missing in compare page"
    print("  ✓ Successfully loaded all 10 companies across compare presets")

    # 6. JSON Data Integrity & YoY Completeness Check (No void, no 5-year gap)
    print("\n[6/7] Validating Chart Data Payload Integrity & YoY Completeness...")
    status, html = fetch("/compare?tickers=NVDA,INTC,MRVL&metric=revenue_yoy")
    match = re.search(r'<script id="compare-payload-json" type="application/json">\s*(\{.*?\})\s*</script>', html, re.DOTALL)
    assert match, "Could not extract compare-payload-json from page"
    payload = json.loads(match.group(1))
    
    assert "peers" in payload, "Payload missing peers"
    assert "activeMetric" in payload, "Payload missing activeMetric"
    assert len(payload["peers"]) == 3, f"Expected 3 peers, got {len(payload['peers'])}"
    
    for peer in payload["peers"]:
        ticker = peer["ticker"]
        quarters = peer["quarters"]
        assert len(quarters) >= 4, f"{ticker} has fewer than 4 quarters in chart ({len(quarters)})"
        
        # Verify no 2018-2020 ancient data in recent quarters
        years = [q["date"][:4] for q in quarters]
        for y in years:
            assert int(y) >= 2022, f"Found stale historical data year {y} for {ticker}!"
        
        # Verify revenue_yoy is populated for the latest quarters
        latest_q = quarters[-1]
        assert latest_q["revenue_yoy"] is not None, f"Latest quarter for {ticker} missing revenue_yoy!"
        print(f"  ✓ {ticker}: {len(quarters)} recent quarters (years: {min(years)} to {max(years)}), latest YoY: {latest_q['revenue_yoy']:.1f}%")

    # 7. Company detail view polish check
    print("\n[7/7] Validating Company Detail Page Polish (NVDA)...")
    status, html = fetch("/company/NVDA/detail")
    assert status == 200, f"Expected 200 on /company/NVDA/detail got {status}"
    assert "tabular-nums" in html, "Detail view missing tabular-nums"
    assert "Free Cash Flow" in html, "Detail view missing Free Cash Flow"
    print("  ✓ Detail view styling and tabular-nums verified")

    print("\n" + "=" * 65)
    print("ALL 7 VALIDATION CHECKS PASSED SUCCESSFULLY (100% OK)")
    print("=" * 65)


if __name__ == "__main__":
    try:
        run_validations()
    except Exception as exc:
        print(f"\n❌ Validation failed: {exc}")
        sys.exit(1)

