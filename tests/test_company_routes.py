from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from tickerlens import routes
from tickerlens.main import app
from tickerlens.services.financials import (
    CompanyNotFoundError,
    FinancialsService,
    _resolve_cik,
)


# ── _resolve_cik ──────────────────────────────────────────────────────────────

def test_resolve_cik_converts_keyerror_to_company_not_found() -> None:
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.side_effect = KeyError("Ticker not found: ZZZZ")
    with pytest.raises(CompanyNotFoundError, match="Unknown ticker"):
        _resolve_cik(mock_edgar, "ZZZZ")


def test_get_overview_unknown_ticker_raises_company_not_found() -> None:
    mock_edgar = MagicMock()
    mock_edgar.cik_for_ticker.side_effect = KeyError("Ticker not found: ZZZZ")
    svc = FinancialsService(edgar_client=mock_edgar)
    with pytest.raises(CompanyNotFoundError):
        svc.get_overview("ZZZZ")


# ── HTTP routes: unknown ticker renders a friendly 404 page ───────────────────

@pytest.fixture
def client(monkeypatch) -> TestClient:
    """App with the financials service stubbed to raise for unknown tickers."""
    mock_svc = MagicMock()
    mock_svc.get_overview.side_effect = CompanyNotFoundError("Unknown ticker: ZZZZ")
    mock_svc.get_detail.side_effect = CompanyNotFoundError("Unknown ticker: ZZZZ")
    mock_svc.fetch_and_persist.side_effect = CompanyNotFoundError("Unknown ticker: ZZZZ")
    monkeypatch.setattr(routes.company, "_svc", mock_svc)
    return TestClient(app, raise_server_exceptions=False)


def test_unknown_ticker_overview_returns_404_html(client: TestClient) -> None:
    resp = client.get("/company/ZZZZ")
    assert resp.status_code == 404
    assert "text/html" in resp.headers["content-type"]
    assert "Couldn't find that company" in resp.text


def test_unknown_ticker_detail_returns_404(client: TestClient) -> None:
    resp = client.get("/company/ZZZZ/detail")
    assert resp.status_code == 404


def test_unknown_ticker_404_suggests_close_matches(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tickerlens import main as main_module

    monkeypatch.setattr(
        main_module,
        "get_search_entries",
        lambda edgar_client: [
            {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193"},
            {"ticker": "APLE", "name": "Apple Hospitality REIT", "cik": "0001418126"},
        ],
    )
    resp = client.get("/company/APPL")
    assert resp.status_code == 404
    assert "Did you mean" in resp.text
    assert "/company/AAPL" in resp.text


def test_unknown_ticker_404_without_suggestions_when_lookup_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tickerlens import main as main_module

    def _boom(edgar_client):  # noqa: ANN001, ANN202
        raise RuntimeError("entries unavailable")

    monkeypatch.setattr(main_module, "get_search_entries", _boom)
    resp = client.get("/company/ZZZZ")
    assert resp.status_code == 404
    assert "Did you mean" not in resp.text
    assert "Couldn't find that company" in resp.text


# ── per-period CSV download (PRD §4.3 #7) ─────────────────────────────────────

def _detail_ctx():
    from tickerlens.services.financials import (
        BalanceSheet,
        BalanceSheetChange,
        DetailContext,
        KPIChange,
        KPISnapshot,
        PeriodData,
    )

    cur = PeriodData(
        label="Q3 FY2025",
        period_end=__import__("datetime").date(2025, 9, 28),
        fiscal_year=2025,
        fiscal_period="Q3",
        kpi=KPISnapshot(revenue=94_930.0, net_income=23_630.0, eps_basic=1.57,
                        eps_diluted=1.55, free_cash_flow=26_800.0),
        yoy=KPIChange(revenue=5.0, net_income=None, eps_basic=None,
                      eps_diluted=None, free_cash_flow=None),
        qoq=KPIChange(revenue=10.7, net_income=None, eps_basic=None,
                      eps_diluted=None, free_cash_flow=None),
        balance_sheet=BalanceSheet(total_assets=365_000.0, total_liabilities=None,
                                   total_equity=None, cash_and_equivalents=30_000.0),
        balance_sheet_yoy=BalanceSheetChange(),
        balance_sheet_qoq=None,
    )
    return DetailContext(
        cik="0000320193", name="Apple Inc.", ticker="AAPL", sector="Technology",
        last_price=341.07, market_cap=5e12,
        granularity="quarterly", quarter_options=["Q3 FY2025"],
        year_options=[2025], selected_quarter="Q3 FY2025", selected_year=2025,
        current=cur, chart_labels=["Q3 FY2025"], chart_revenue=[94_930.0],
        chart_eps=[1.55],
    )


def test_download_csv_returns_attachment(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes

    mock_svc = MagicMock()
    mock_svc.get_detail.return_value = _detail_ctx()
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/AAPL/detail/download?granularity=quarterly&quarter=Q3%20FY2025")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.headers["content-disposition"] == 'attachment; filename="AAPL_Q3-FY2025.csv"'
    body = resp.text
    assert "metric,value,yoy_pct,qoq_pct" in body
    assert "Revenue,94930.0,5.0,10.7" in body
    assert "Cash & Equivalents,30000.0,," in body
    assert "# Period,Q3 FY2025" in body


def test_build_period_csv_none_values_render_empty() -> None:
    from tickerlens.services.financials import build_period_csv, download_filename

    ctx = _detail_ctx()
    csv_text = build_period_csv(ctx)
    # Net income YoY/QoQ are None -> empty cells, not "None"
    assert "Net Income,23630.0,," in csv_text
    assert "None" not in csv_text
    assert download_filename(ctx) == "AAPL_Q3-FY2025.csv"


# ── /api/search autocomplete (PRD §4.10) ─────────────────────────────────────

SEARCH_FIXTURES = [
    {"ticker": "AAPL", "name": "Apple Inc.", "cik": "0000320193"},
    {"ticker": "TSLA", "name": "Tesla, Inc.", "cik": "0001318605"},
]


@pytest.fixture
def search_client(monkeypatch) -> TestClient:
    monkeypatch.setattr(
        routes.company, "get_search_entries", lambda edgar_client: SEARCH_FIXTURES
    )
    return TestClient(app, raise_server_exceptions=False)


def test_api_search_ranks_ticker_prefix_first(search_client: TestClient) -> None:
    resp = search_client.get("/api/search", params={"q": "aap"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results[0]["ticker"] == "AAPL"
    assert results[0]["cik"] == "0000320193"


def test_api_search_matches_company_name(search_client: TestClient) -> None:
    resp = search_client.get("/api/search", params={"q": "tesla"})
    assert resp.status_code == 200
    assert resp.json()["results"][0]["ticker"] == "TSLA"


def test_api_search_empty_query_returns_no_results(search_client: TestClient) -> None:
    resp = search_client.get("/api/search", params={"q": ""})
    assert resp.status_code == 200
    assert resp.json()["results"] == []


def test_api_search_no_match_returns_empty_list(search_client: TestClient) -> None:
    resp = search_client.get("/api/search", params={"q": "zzz-no-such"})
    assert resp.status_code == 200
    assert resp.json()["results"] == []


# ── full-history ZIP download (PRD §4.8, first slice) ──────────────────────────

def test_history_zip_route_returns_attachment(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes

    mock_svc = MagicMock()
    mock_svc.get_history_zip_entries.return_value = (
        "AAPL",
        [("AAPL/AAPL_Q3-FY2025.csv", "metric,value,yoy_pct,qoq_pct\nRevenue,100.0,,\n")],
    )
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/AAPL/download/history.zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert resp.headers["content-disposition"] == 'attachment; filename="AAPL_history.zip"'

    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        assert zf.namelist() == ["AAPL/AAPL_Q3-FY2025.csv"]
        assert "Revenue,100.0" in zf.read("AAPL/AAPL_Q3-FY2025.csv").decode()


def test_history_zip_route_unknown_ticker_404(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes
    from tickerlens.services.financials import CompanyNotFoundError

    mock_svc = MagicMock()
    mock_svc.get_history_zip_entries.side_effect = CompanyNotFoundError("Unknown ticker: ZZZZ")
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/ZZZZ/download/history.zip")
    assert resp.status_code == 404


# ── compare ZIP download (PRD §4.8, second slice) ─────────────────────────────

def test_compare_zip_route_returns_attachment(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes

    mock_svc = MagicMock()
    mock_svc.get_compare_zip_entries.return_value = (
        "AAPL",
        [
            ("AAPL/AAPL_Q3-FY2025.csv", "metric,value,yoy_pct,qoq_pct\n"),
            ("AAPL/AAPL_Q3-FY2024.csv", "metric,value,yoy_pct,qoq_pct\n"),
            ("AAPL/AAPL_compare_summary.csv", "metric,period_a,period_b,delta,delta_pct\n"),
        ],
    )
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/AAPL/compare/download?preset=yoy")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert resp.headers["content-disposition"] == 'attachment; filename="AAPL_compare.zip"'
    mock_svc.get_compare_zip_entries.assert_called_once_with(
        "AAPL", period_a=None, period_b=None, preset="yoy",
        mode="quarterly", year_a=None, year_b=None,
    )

    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        assert zf.namelist() == [
            "AAPL/AAPL_Q3-FY2025.csv",
            "AAPL/AAPL_Q3-FY2024.csv",
            "AAPL/AAPL_compare_summary.csv",
        ]


def test_compare_zip_route_unknown_ticker_404(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes
    from tickerlens.services.financials import CompanyNotFoundError

    mock_svc = MagicMock()
    mock_svc.get_compare_zip_entries.side_effect = CompanyNotFoundError("Unknown ticker: ZZZZ")
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/ZZZZ/compare/download")
    assert resp.status_code == 404


def test_compare_zip_route_rejects_bad_preset(client: TestClient, monkeypatch) -> None:
    """FastAPI validates the preset Literal — an unknown value 422s."""
    resp = client.get("/company/AAPL/compare/download?preset=decade")
    assert resp.status_code == 422


def test_render_compare_csv_matches_compare_table() -> None:
    """Summary CSV renders the same metric × (A | B | Δ | Δ%) table the page shows."""
    import csv
    import io as _io

    from tickerlens.services.financials import (
        BalanceSheet,
        BalanceSheetChange,
        CompareContext,
        CompareDeltas,
        KPIChange,
        KPISnapshot,
        MetricDelta,
        PeriodData,
        render_compare_csv,
    )

    def period(revenue: float | None) -> PeriodData:
        return PeriodData(
            label="Q3 FY2025", period_end=None, fiscal_year=2025,
            fiscal_period="Q3",
            kpi=KPISnapshot(revenue=revenue, eps_diluted=1.0),
            yoy=KPIChange(), qoq=None,
            balance_sheet=BalanceSheet(),
            balance_sheet_yoy=BalanceSheetChange(), balance_sheet_qoq=None,
        )

    ctx = CompareContext(
        cik="0000320193", name="Apple Inc.", ticker="AAPL", sector=None,
        last_price=None, market_cap=None,
        quarter_options=["Q3 FY2025", "Q3 FY2024"],
        period_a_label="Q3 FY2025", period_b_label="Q3 FY2024", preset=None,
        a=period(revenue=94_930.0), b=period(revenue=91_000.0),
        deltas=CompareDeltas(
            revenue=MetricDelta(absolute=3_930.0, pct=4.3187),
            eps_diluted=MetricDelta(absolute=0.0, pct=0.0),
        ),
    )

    rows = list(csv.reader(_io.StringIO(render_compare_csv("Apple Inc.", "AAPL", ctx))))
    assert rows[0] == ["# Company", "Apple Inc. (AAPL)"]
    assert rows[5] == ["metric", "period_a", "period_b", "delta", "delta_pct"]
    by_metric = {r[0]: r for r in rows[6:]}
    assert by_metric["Revenue"] == ["Revenue", "94930.0", "91000.0", "3930.0", "4.32"]
    assert by_metric["EPS Diluted"] == ["EPS Diluted", "1.0", "1.0", "0.0", "0.0"]
    assert by_metric["Total Assets"] == ["Total Assets", "", "", "", ""]


# ── watchlist quote refresh (PRD §4.6, slice 2) ───────────────────────────────

def test_watchlist_refresh_plain_post_redirects_home(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes

    mock_svc = MagicMock()
    mock_svc.refresh_watchlist_quotes.return_value = {"updated": 2, "failed": 0}
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.post("/watchlist/refresh", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    mock_svc.refresh_watchlist_quotes.assert_called_once_with()


def test_watchlist_refresh_htmx_returns_pins_partial(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes
    from tickerlens.services.financials import WatchlistRow

    mock_svc = MagicMock()
    mock_svc.refresh_watchlist_quotes.return_value = {"updated": 1, "failed": 0}
    mock_svc.get_watchlist.return_value = [
        WatchlistRow(cik="0000320193", ticker="AAPL", name="Apple Inc.",
                     last_price=400.0, market_cap=6e12, signal="Buy")
    ]
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.post("/watchlist/refresh", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert 'id="watchlist-section"' in resp.text
    assert "AAPL" in resp.text
    assert "400.00" in resp.text


# ── chart range window (PRD §4.2, range-mode slice 1) ──────────────────────────

def test_detail_data_passes_chart_range_params(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes

    mock_svc = MagicMock()
    mock_svc.get_detail.return_value = _detail_ctx()
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/AAPL/detail/data?chart_from=Q1%20FY2025&chart_to=Q3%20FY2025")
    assert resp.status_code == 200
    _, kwargs = mock_svc.get_detail.call_args
    assert kwargs["chart_from"] == "Q1 FY2025"
    assert kwargs["chart_to"] == "Q3 FY2025"


# ── range-mode hero KPIs (PRD §4.2, slice 3) ───────────────────────────────────

def test_detail_data_renders_range_kpi_branch(client: TestClient, monkeypatch) -> None:
    """When ctx.range_kpi is set, the hero cards show window aggregates with
    a 'vs prior NQ' caption instead of the YoY/QoQ toggle."""
    from tickerlens import routes
    from tickerlens.services.financials import KPIChange, KPISnapshot, RangeKPIData

    ctx = _detail_ctx()
    ctx.range_kpi = RangeKPIData(
        label="Q1 FY2025 → Q2 FY2025",
        quarters=2,
        kpi=KPISnapshot(revenue=181_136.0, net_income=46_228.0,
                        eps_basic=3.08, eps_diluted=3.04,
                        free_cash_flow=53_000.0),
        change=KPIChange(revenue=-13.98, net_income=None, eps_basic=None,
                         eps_diluted=None, free_cash_flow=None),
        prior_label="Q3 FY2024 → Q4 FY2024",
        prior_quarters=2,
    )
    mock_svc = MagicMock()
    mock_svc.get_detail.return_value = ctx
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/AAPL/detail/data?chart_from=Q1%20FY2025&chart_to=Q2%20FY2025")
    assert resp.status_code == 200
    assert "Q1 FY2025 → Q2 FY2025" in resp.text
    assert "(2 quarters, summed)" in resp.text
    assert "vs Q3 FY2024 → Q4 FY2024" in resp.text
    assert "vs prior 2Q" in resp.text
    # Aggregated revenue renders in the hero cards ($181136). The tabbed
    # tables still follow ctx.range_table (None in this fixture), so the
    # single-period $94930 legitimately appears there too.
    assert "$181136" in resp.text
    # No YoY/QoQ toggle in range mode.
    assert "Change comparison mode" not in resp.text


def test_detail_data_renders_period_kpi_branch_by_default(
    client: TestClient, monkeypatch
) -> None:
    """Without range_kpi the hero cards stay on the selected period."""
    from tickerlens import routes

    mock_svc = MagicMock()
    mock_svc.get_detail.return_value = _detail_ctx()
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/AAPL/detail/data")
    assert resp.status_code == 200
    assert "Q3 FY2025" in resp.text
    assert "(2 quarters, summed)" not in resp.text


# ── unwatch from home (PRD §4.6, slice 3) ─────────────────────────────────────

def test_unwatch_from_home_plain_post_redirects_home(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes

    mock_svc = MagicMock()
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.post("/company/AAPL/watch/remove?next=home", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    mock_svc.unwatch_ticker.assert_called_once_with("AAPL")


def test_unwatch_from_home_htmx_returns_pins_partial(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes
    from tickerlens.services.financials import WatchlistRow

    mock_svc = MagicMock()
    mock_svc.get_watchlist.return_value = [
        WatchlistRow(cik="0000789019", ticker="MSFT", name="Microsoft Corp.",
                     last_price=500.0, market_cap=3e12, signal="Hold")
    ]
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.post("/company/AAPL/watch/remove?next=home", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert 'id="watchlist-section"' in resp.text
    assert "MSFT" in resp.text
    assert "AAPL" not in resp.text
    mock_svc.unwatch_ticker.assert_called_once_with("AAPL")


def test_unwatch_from_overview_still_swaps_button(client: TestClient, monkeypatch) -> None:
    """The Overview-header toggle keeps its old behavior without ?next=home."""
    from tickerlens import routes

    mock_svc = MagicMock()
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.post("/company/AAPL/watch/remove", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert "watchlist-section" not in resp.text

    resp = client.post("/company/AAPL/watch/remove", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/company/AAPL"


def test_watch_from_home_plain_post_redirects_home(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes

    mock_svc = MagicMock()
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.post("/company/NVDA/watch?next=home", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    mock_svc.watch_ticker.assert_called_once_with("NVDA")


def test_watch_from_home_htmx_returns_pins_partial(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes
    from tickerlens.services.financials import WatchlistRow

    mock_svc = MagicMock()
    mock_svc.get_watchlist.return_value = [
        WatchlistRow(cik="0001045810", ticker="NVDA", name="NVIDIA Corp.",
                     last_price=225.0, market_cap=5e12, signal="Strong Buy")
    ]
    mock_svc.get_benchmarks.return_value = []
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.post("/company/NVDA/watch?next=home", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert 'id="watchlist-section"' in resp.text
    assert "NVDA" in resp.text
    mock_svc.watch_ticker.assert_called_once_with("NVDA")


# ── compare yearly mode (PRD §4.2, compare-mode slice 2) ──────────────────────

def test_compare_yearly_passes_mode_and_years(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes

    mock_svc = MagicMock()
    monkeypatch.setattr(routes.company, "_svc", mock_svc)
    mock_ctx = MagicMock()
    mock_ctx.ticker = "AAPL"
    mock_ctx.name = "Apple Inc."
    mock_ctx.sector = None
    mock_ctx.mode = "yearly"
    mock_ctx.quarter_options = []
    mock_ctx.year_options = [2025, 2024]
    mock_ctx.period_a_label = "FY2025"
    mock_ctx.period_b_label = "FY2024"
    mock_ctx.preset = None
    for side in ("a", "b"):
        kpi = getattr(mock_ctx, side).kpi
        kpi.revenue = 400_000.0
        kpi.net_income = 90_000.0
        kpi.eps_basic = 5.0
        kpi.eps_diluted = 4.9
        kpi.free_cash_flow = 100_000.0
        bs = getattr(mock_ctx, side).balance_sheet
        bs.total_assets = 350_000.0
        bs.total_liabilities = 250_000.0
        bs.total_equity = 100_000.0
        bs.cash_and_equivalents = 50_000.0
    for field in ("revenue", "net_income", "eps_basic", "eps_diluted",
                  "free_cash_flow", "total_assets", "total_liabilities",
                  "total_equity", "cash_and_equivalents"):
        getattr(mock_ctx.deltas, field).absolute = 1_000.0
        getattr(mock_ctx.deltas, field).pct = 5.0
    mock_svc.get_compare.return_value = mock_ctx

    resp = client.get("/company/AAPL/compare?mode=yearly&year_a=2025&year_b=2024")
    assert resp.status_code == 200
    assert "FY2025" in resp.text and "FY2024" in resp.text
    assert 'name="year_a"' in resp.text
    mock_svc.get_compare.assert_called_once_with(
        "AAPL", period_a=None, period_b=None, preset=None,
        mode="yearly", year_a=2025, year_b=2024,
    )


# ── single-year ZIP download (PRD §4.8, fourth slice) ──────────────────────────

def test_year_zip_route_returns_attachment(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes

    mock_svc = MagicMock()
    mock_svc.get_year_zip_entries.return_value = (
        "AAPL",
        2025,
        [("AAPL/AAPL_Q1-FY2025.csv", "metric,value,yoy_pct,qoq_pct\nRevenue,100.0,,\n")],
    )
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/AAPL/download/year.zip?year=2025")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert resp.headers["content-disposition"] == 'attachment; filename="AAPL_year_FY2025.zip"'
    mock_svc.get_year_zip_entries.assert_called_once_with("AAPL", year=2025)


def test_year_zip_route_unknown_ticker_404(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes
    from tickerlens.services.financials import CompanyNotFoundError

    mock_svc = MagicMock()
    mock_svc.get_year_zip_entries.side_effect = CompanyNotFoundError("Unknown ticker: ZZZZ")
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/ZZZZ/download/year.zip")
    assert resp.status_code == 404


# ── watchlist tags (PRD §4.6, tags slice) ─────────────────────────────────────

def test_save_watch_tags_htmx_returns_partial(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes

    mock_svc = MagicMock()
    mock_svc.set_watchlist_tags.return_value = ["dividend", "ai"]
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.post("/company/AAPL/watch/tags", data={"tags": "dividend, ai"},
                       headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert 'id="watch-tags"' in resp.text
    assert "dividend" in resp.text and "ai" in resp.text
    mock_svc.set_watchlist_tags.assert_called_once_with("AAPL", "dividend, ai")


def test_save_watch_tags_plain_post_redirects(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes

    mock_svc = MagicMock()
    mock_svc.set_watchlist_tags.return_value = ["ai"]
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.post("/company/AAPL/watch/tags", data={"tags": "ai"},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/company/AAPL"


def test_save_watch_tags_404_when_not_watching(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes
    from tickerlens.services.financials import CompanyNotFoundError

    mock_svc = MagicMock()
    mock_svc.set_watchlist_tags.side_effect = CompanyNotFoundError("AAPL is not on the watchlist")
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.post("/company/AAPL/watch/tags", data={"tags": "ai"},
                       headers={"HX-Request": "true"})
    assert resp.status_code == 404


def test_watch_tags_partial_renders_chips() -> None:
    """The tags partial shows existing tags as chips and prefills the input."""
    from starlette.requests import Request
    from tickerlens.routes.company import templates

    req = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    resp = templates.TemplateResponse(
        request=req,
        name="partials/watch_tags.html",
        context={"ticker": "AAPL", "tags": ["dividend", "ai"]},
    )
    body = resp.body.decode()
    assert "dividend" in body and "ai" in body
    assert 'value="dividend, ai"' in body
    assert "/company/AAPL/watch/tags" in body


# ── cross-company compare (PRD §4.2, compare slice) ────────────────────────────

def _vs_ctx():
    from tickerlens.services.financials import (
        CompanyVs, KPIChange, KPISnapshot, VsCompany,
    )

    def side(ticker, name, rev, rev_yoy, eps, signal):
        return VsCompany(
            ticker=ticker, name=name, sector="Technology",
            period_label="Q2 FY2025",
            kpi=KPISnapshot(revenue=rev, net_income=rev * 0.25,
                            eps_basic=eps, eps_diluted=eps,
                            free_cash_flow=rev * 0.3),
            yoy=KPIChange(revenue=rev_yoy, net_income=None, eps_basic=None,
                          eps_diluted=None, free_cash_flow=None),
            last_price=100.0, market_cap=1e12,
            signal=signal, upside_pct=12.5,
        )

    return CompanyVs(
        a=side("AAPL", "Apple Inc.", 85_777.0, 7.2, 1.40, "Buy"),
        b=side("MSFT", "Microsoft Corp.", 64_000.0, 6.7, 3.60, "Hold"),
    )


def test_company_vs_renders_both_sides(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes

    mock_svc = MagicMock()
    mock_svc.get_company_vs.return_value = _vs_ctx()
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/AAPL/vs/MSFT")
    assert resp.status_code == 200
    assert "AAPL" in resp.text and "MSFT" in resp.text
    assert "Apple Inc." in resp.text and "Microsoft Corp." in resp.text
    assert "$85777" in resp.text  # AAPL revenue via fmt_large
    assert "$64000" in resp.text  # MSFT revenue via fmt_large
    assert "Buy" in resp.text and "Hold" in resp.text
    mock_svc.get_company_vs.assert_called_once_with("AAPL", "MSFT")


def test_company_vs_404_when_peer_unloadable(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes
    from tickerlens.services.financials import CompanyNotFoundError

    mock_svc = MagicMock()
    mock_svc.get_detail.side_effect = CompanyNotFoundError("No data for ZZZZ")
    mock_svc.fetch_and_persist.side_effect = Exception("EDGAR unreachable")
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/AAPL/vs/ZZZZ")
    assert resp.status_code == 404


def test_earnings_calendar_route(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes
    from tickerlens.data.calendar import EarningsEvent

    mock_svc = MagicMock()
    mock_svc.get_upcoming_earnings.return_value = [
        EarningsEvent(
            ticker="NVDA",
            company_name="NVIDIA Corp",
            earnings_date="2026-11-17",
            days_until=44,
            eps_estimate_avg=2.47,
            revenue_estimate_avg=108995000000.0,
            dividend_date="2026-09-30",
            ex_dividend_date="2026-09-09",
            is_watchlist=True,
        )
    ]
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/calendar")
    assert resp.status_code == 200
    assert "Earnings Calendar" in resp.text
    assert "NVDA" in resp.text
    assert "2026-11-17" in resp.text
    assert "$2.47" in resp.text
    assert "$109.00B" in resp.text

    # Watchlist filter
    resp_watch = client.get("/calendar?filter=watchlist")
    assert resp_watch.status_code == 200
    mock_svc.get_upcoming_earnings.assert_called_with(watchlist_only=True)


def test_company_tearsheet_route(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes
    from tickerlens.services.financials import CompanyOverview, DetailContext, PeriodData, KPISnapshot, KPIChange
    from tickerlens.services.valuation import ValuationSignal
    from tickerlens.models.quarterly_financial import QuarterlyFinancial
    import datetime as dt

    mock_svc = MagicMock()
    mock_svc.get_overview.return_value = CompanyOverview(
        cik="0000320193",
        name="Apple Inc.",
        ticker="AAPL",
        description="Consumer electronics",
        sector="Technology",
        last_price=341.0,
        market_cap=5000000000000.0,
        latest_label="Q3 FY2025",
        latest_period_end=dt.date(2025, 9, 28),
        latest_kpi=KPISnapshot(revenue=94930.0, net_income=23630.0, eps_diluted=1.55, free_cash_flow=26800.0),
        yoy=KPIChange(revenue=5.0, net_income=7.0, eps_diluted=6.0, free_cash_flow=8.0),
        ttm_kpi=KPISnapshot(revenue=380000.0, net_income=100000.0, eps_diluted=6.20, free_cash_flow=110000.0),
        ttm_quarters=4,
    )
    mock_svc.get_detail.return_value = _detail_ctx()
    mock_svc.get_valuation.return_value = ValuationSignal(
        ticker="AAPL",
        current_price=341.0,
        target_price=380.0,
        upside_pct=15.0,
        signal="Buy",
        confidence="high",
        method="peg",
        fair_multiple=25.0,
        current_multiple=22.0,
        growth_pct=16.0,
        reasoning=["Strong growth"],
    )
    mock_svc.get_stored_quarters.return_value = [
        QuarterlyFinancial(
            cik="0000320193",
            period_end=dt.date(2025, 9, 28),
            fiscal_year=2025,
            fiscal_period="Q3",
            revenue=94930.0,
            net_income=23630.0,
            eps_diluted=1.55,
            free_cash_flow=26800.0,
            total_assets=365000.0,
            total_liabilities=200000.0,
            total_equity=165000.0,
            cash_and_equivalents=30000.0,
        )
    ]
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/AAPL/tearsheet")
    assert resp.status_code == 200
    assert "INSTITUTIONAL TEARSHEET" in resp.text
    assert "Apple Inc." in resp.text or "AAPL" in resp.text
    assert "Q3 FY2025" in resp.text


def test_overview_triggers_refresh_company_quote(client: TestClient, monkeypatch) -> None:
    from tickerlens import routes
    from tickerlens.services.financials import CompanyOverview, KPISnapshot, KPIChange
    from tickerlens.services.valuation import ValuationSignal
    import datetime as dt

    mock_svc = MagicMock()
    mock_svc.get_overview.return_value = CompanyOverview(
        cik="0001144879",
        name="Applied Digital Corp.",
        ticker="APLD",
        description="Data center infrastructure",
        sector="Technology",
        last_price=24.70,
        market_cap=7389503488.0,
        latest_label="Q3 FY2025",
        latest_period_end=dt.date(2025, 2, 28),
        latest_kpi=KPISnapshot(revenue=40.0, net_income=-10.0, eps_diluted=-0.08, free_cash_flow=-20.0),
        yoy=KPIChange(revenue=10.0, net_income=None, eps_diluted=None, free_cash_flow=None),
        ttm_kpi=KPISnapshot(revenue=150.0, net_income=-40.0, eps_diluted=-0.35, free_cash_flow=-80.0),
        ttm_quarters=4,
    )
    mock_svc.get_valuation.return_value = ValuationSignal(
        ticker="APLD",
        current_price=24.70,
        target_price=25.0,
        upside_pct=1.2,
        signal="Hold",
        confidence="medium",
        method="peg",
        fair_multiple=20.0,
        current_multiple=19.5,
        growth_pct=10.0,
        reasoning=["Fairly valued"],
    )
    mock_svc.get_signal_change.return_value = None
    mock_svc.is_watching.return_value = False
    mock_svc.get_watchlist_note.return_value = None
    mock_svc.get_watchlist_tags.return_value = []
    mock_svc.get_sibling_tickers.return_value = []
    mock_svc.get_peers.return_value = []
    mock_svc.get_ai_analysis.return_value = None
    monkeypatch.setattr(routes.company, "_svc", mock_svc)

    resp = client.get("/company/APLD")
    assert resp.status_code == 200
    mock_svc.refresh_company_quote.assert_called_with("APLD")



