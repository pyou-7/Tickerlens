from __future__ import annotations

import json
from tickerlens.services.comparison import ComparisonService, ComparisonContext


def test_comparison_service_default_peers():
    svc = ComparisonService()
    ctx = svc.get_comparison()

    assert isinstance(ctx, ComparisonContext)
    assert len(ctx.peers) >= 2
    tickers = [p.ticker for p in ctx.peers]
    assert "NVDA" in tickers
    assert "INTC" in tickers

    for p in ctx.peers:
        assert p.ticker is not None
        assert p.name is not None
        assert p.latest_period is not None
        assert len(p.quarters) > 0
        assert p.revenue is not None

    assert ctx.metric == "revenue_yoy"
    assert "NVDA" in ctx.tickers_str


def test_comparison_service_custom_tickers():
    svc = ComparisonService()
    ctx = svc.get_comparison(tickers=["AAPL", "MSFT"], metric="net_margin")

    assert ctx.metric == "net_margin"
    assert len(ctx.peers) == 2
    tickers = [p.ticker for p in ctx.peers]
    assert "AAPL" in tickers
    assert "MSFT" in tickers

    # Validate margins calculated
    for p in ctx.peers:
        assert p.net_margin is not None
        assert p.net_margin > 0  # AAPL & MSFT have positive net margins


def test_comparison_service_leaderboard():
    svc = ComparisonService()
    ctx = svc.get_comparison(tickers=["NVDA", "INTC", "MRVL"])

    assert ctx.leaderboard is not None
    assert ctx.leaderboard.top_revenue_growth == "NVDA"
    assert ctx.leaderboard.top_net_margin == "NVDA"
    assert ctx.leaderboard.top_market_cap == "NVDA"


def test_comparison_service_max_peers_limit():
    svc = ComparisonService()
    ctx = svc.get_comparison(tickers=["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "INTC"])
    assert len(ctx.peers) <= 5
    assert len(ctx.selected_tickers) <= 5


def test_comparison_service_chart_payload():
    svc = ComparisonService()
    ctx = svc.get_comparison(tickers=["AAPL", "MSFT"], metric="revenue_yoy")

    payload = json.loads(ctx.chart_payload_json)
    assert payload["activeMetric"] == "revenue_yoy"
    assert len(payload["peers"]) == 2

    peer_0 = payload["peers"][0]
    assert "ticker" in peer_0
    assert "color" in peer_0
    assert "quarters" in peer_0
    assert len(peer_0["quarters"]) > 0

    first_q = peer_0["quarters"][0]
    assert "date" in first_q
    assert "label" in first_q
    assert "revenue" in first_q
