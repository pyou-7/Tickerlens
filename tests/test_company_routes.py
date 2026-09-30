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
