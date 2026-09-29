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
