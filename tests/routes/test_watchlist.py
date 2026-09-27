from __future__ import annotations

from fastapi.testclient import TestClient

from tickerlens.main import app

client = TestClient(app)


def test_home_page_renders_pinned_dashboard():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "pinned-dashboard" in resp.text


def test_watchlist_toggle_button():
    # Ensure clean starting state
    client.delete("/watchlist/AAPL")

    # Toggle AAPL (unpinned -> pinned)
    resp = client.post("/watchlist/toggle/AAPL?view=button")
    assert resp.status_code == 200
    assert 'id="watchlist-btn-AAPL"' in resp.text
    assert "Pinned" in resp.text

    # Toggle again (pinned -> unpinned)
    resp2 = client.post("/watchlist/toggle/AAPL?view=button")
    assert resp2.status_code == 200
    assert 'id="watchlist-btn-AAPL"' in resp2.text
    assert "Pin to Home" in resp2.text


def test_watchlist_toggle_dashboard():
    # Ensure clean starting state
    client.delete("/watchlist/AAPL")

    # Toggle to pin
    resp = client.post("/watchlist/toggle/AAPL?view=dashboard")
    assert resp.status_code == 200
    assert 'id="pinned-dashboard"' in resp.text
    assert "AAPL" in resp.text


def test_watchlist_delete():
    # Pin first to ensure it's there
    client.post("/watchlist/toggle/AAPL?view=dashboard")

    # Delete
    resp = client.delete("/watchlist/AAPL?view=dashboard")
    assert resp.status_code == 200
    assert 'id="pinned-dashboard"' in resp.text



def test_overview_renders_watchlist_button():
    resp = client.get("/company/AAPL")
    assert resp.status_code == 200
    assert 'id="watchlist-btn-AAPL"' in resp.text


def test_detail_renders_watchlist_button():
    resp = client.get("/company/AAPL/detail")
    assert resp.status_code == 200
    assert 'id="watchlist-btn-AAPL"' in resp.text
