from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from tickerlens.main import app
from tickerlens.services.search import CompanySearchResult

client = TestClient(app)


def test_api_search_empty_query():
    resp = client.get("/api/search?q=")
    assert resp.status_code == 200
    assert resp.json() == []


def test_api_search_success():
    mock_results = [
        CompanySearchResult(
            ticker="AAPL",
            name="Apple Inc.",
            cik="0000320193",
            market_cap=3_000_000_000_000.0,
        )
    ]
    with patch("tickerlens.routes.search._search_service.search", return_value=mock_results):
        resp = client.get("/api/search?q=aapl&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"
        assert data[0]["name"] == "Apple Inc."
        assert data[0]["cik"] == "0000320193"
        assert data[0]["market_cap"] == 3_000_000_000_000.0


def test_home_page_renders_hero_search():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "hero-search-input" in resp.text
    assert "Search 10,000+ US public companies" in resp.text


def test_overview_page_renders_nav_search():
    # If AAPL is in the local DB, overview renders 200 with nav-search-input
    resp = client.get("/company/AAPL")
    assert resp.status_code == 200
    assert "nav-search-input" in resp.text
