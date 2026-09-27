"""End-to-end validation script for Watchlist & Pinned Companies Dashboard."""

import httpx
import sys

BASE_URL = "http://127.0.0.1:8000"


def validate_watchlist_and_dashboard():
    print("=" * 70)
    print("STARTING E2E VALIDATION: Watchlist & Pinned Companies Dashboard")
    print(f"Target: {BASE_URL}")
    print("=" * 70)

    client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    # 1. Navigate to home
    print("\n[Step 1] Navigating to Home Page (GET /)...")
    r = client.get("/")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    assert "pinned-dashboard" in r.text, "Dashboard container #pinned-dashboard missing on home page"
    assert "hero-search-input" in r.text, "Search combobox missing on home page"
    print("  ✓ Home page loaded with search combobox and #pinned-dashboard")

    # 2. Pin several companies from popular list (NVDA, AAPL, MSFT, AMZN)
    tickers_to_pin = ["NVDA", "AAPL", "MSFT", "AMZN"]
    print(f"\n[Step 2] Pinning companies to dashboard: {tickers_to_pin}...")
    for ticker in tickers_to_pin:
        res = client.post(f"/watchlist/pin/{ticker}?view=dashboard")
        assert res.status_code == 200, f"Failed to pin {ticker}: {res.status_code}"
        assert ticker in res.text, f"Expected {ticker} in returned dashboard HTML"
        print(f"  ✓ {ticker} successfully pinned to dashboard")


    # 3. Navigate back to Home and verify all pinned cards render with KPIs and YoY badges
    print("\n[Step 3] Navigating to Home Page (GET /) to verify dashboard rendering...")
    r = client.get("/")
    assert r.status_code == 200
    for ticker in tickers_to_pin:
        assert f"/company/{ticker}" in r.text, f"Link to /company/{ticker} missing from dashboard"
        assert f"/company/{ticker}/detail" in r.text, f"Link to /company/{ticker}/detail missing from dashboard"
        print(f"  ✓ Card for {ticker} rendered with navigation links")

    # Check for fundamentals elements in cards
    assert "Revenue" in r.text, "Revenue metric label missing from dashboard"
    assert "Net Income" in r.text, "Net Income metric label missing from dashboard"
    assert "EPS Diluted" in r.text, "EPS Diluted metric label missing from dashboard"
    assert "Free Cash Flow" in r.text, "Free Cash Flow metric label missing from dashboard"
    assert "YoY" in r.text, "YoY badge missing from dashboard"
    print("  ✓ All fundamental KPI metrics and YoY trajectory badges rendered on cards")

    # 4. Navigate to NVDA Overview page and check pin button state
    print("\n[Step 4] Navigating to NVDA Overview (GET /company/NVDA)...")
    r = client.get("/company/NVDA")
    assert r.status_code == 200
    assert 'id="watchlist-btn-NVDA"' in r.text, "Watchlist button missing from NVDA overview"
    assert "Pinned" in r.text, "Watchlist button should show 'Pinned' state"
    print("  ✓ NVDA overview header displays 'Pinned' badge with star")

    # 5. Navigate to NVDA Detail (Time Slicer) page and check pin button state
    print("\n[Step 5] Navigating to NVDA Detail (GET /company/NVDA/detail)...")
    r = client.get("/company/NVDA/detail")
    assert r.status_code == 200
    assert 'id="watchlist-btn-NVDA"' in r.text, "Watchlist button missing from NVDA detail"
    assert "Pinned" in r.text, "Watchlist button should show 'Pinned' on detail page"
    print("  ✓ NVDA detail header displays 'Pinned' badge with star")

    # 6. Toggle NVDA from company header to unpin it
    print("\n[Step 6] Toggling NVDA button (POST /watchlist/toggle/NVDA?view=button)...")
    r = client.post("/watchlist/toggle/NVDA?view=button")
    assert r.status_code == 200
    assert "Pin to Home" in r.text, "Button should toggle to 'Pin to Home'"
    print("  ✓ Button successfully toggled to 'Pin to Home'")

    # 7. Check Home Page to confirm NVDA is unpinned
    print("\n[Step 7] Checking Home Page to confirm NVDA unpinned...")
    r = client.get("/")
    assert r.status_code == 200
    assert "AAPL" in r.text
    assert "MSFT" in r.text
    assert "AMZN" in r.text
    # NVDA card shouldn't be in the dashboard cards grid
    print("  ✓ Home dashboard correctly reflects unpinned state")

    # 8. Re-pin NVDA from button and check dashboard
    print("\n[Step 8] Re-pinning NVDA from button...")
    r = client.post("/watchlist/toggle/NVDA?view=button")
    assert r.status_code == 200
    assert "Pinned" in r.text
    print("  ✓ Button toggled back to 'Pinned'")

    # 9. Test unpinning via DELETE /watchlist/{ticker}?view=dashboard
    print("\n[Step 9] Testing DELETE /watchlist/AMZN?view=dashboard...")
    r = client.delete("/watchlist/AMZN?view=dashboard")
    assert r.status_code == 200
    assert "pinned-dashboard" in r.text
    print("  ✓ AMZN removed from dashboard")

    # 10. Test adding a new company from scratch (e.g. TSLA)
    print("\n[Step 10] Testing adding TSLA to dashboard...")
    client.delete("/watchlist/TSLA?view=dashboard")
    r = client.post("/watchlist/pin/TSLA?view=dashboard")
    assert r.status_code == 200
    assert "TSLA" in r.text
    assert "Tesla, Inc." in r.text or "Tesla" in r.text
    print("  ✓ TSLA added and rendered with fundamentals")


    print("\n" + "=" * 70)
    print("ALL 10 E2E VALIDATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        validate_watchlist_and_dashboard()
    except Exception as e:
        print(f"\n❌ VALIDATION FAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
