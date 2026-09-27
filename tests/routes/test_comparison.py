from __future__ import annotations

from fastapi.testclient import TestClient

from tickerlens.main import app

client = TestClient(app)


def test_compare_page_default():
    response = client.get("/compare")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    text = response.text
    assert "Peer Benchmarking" in text
    assert "NVDA" in text
    assert "INTC" in text
    assert "compare-plotly-chart" in text
    assert "Side-by-Side Financial Benchmarking" in text


def test_compare_page_custom_tickers_and_metric():
    response = client.get("/compare?tickers=AAPL,MSFT&metric=net_margin")
    assert response.status_code == 200
    text = response.text
    assert "AAPL" in text
    assert "MSFT" in text
    assert "Net Margin %" in text


def test_compare_chart_htmx_partial():
    response = client.get("/compare/chart?tickers=NVDA,INTC,MRVL&metric=revenue")
    assert response.status_code == 200
    text = response.text
    assert 'id="compare-chart-container"' in text
    assert "compare-plotly-chart" in text
    assert "Revenue ($)" in text


def test_compare_page_empty_tickers():
    # If empty or whitespace tickers param is passed, falls back to default peer group
    response = client.get("/compare?tickers=")
    assert response.status_code == 200
    text = response.text
    assert "NVDA" in text
    assert "INTC" in text


def test_compare_page_theme_and_alignment_controls():
    response = client.get("/compare")
    assert response.status_code == 200
    text = response.text
    # Check for dark mode and theme switcher
    assert "tickerlens_theme" in text
    assert "setTheme('dark')" in text
    assert "setTheme('light')" in text
    assert "setTheme('system')" in text
    # Check for alignment controls
    assert "Aligned Quarters" in text
    assert "Calendar Dates" in text
    # Check for peer toggle
    assert "togglePeer" in text

