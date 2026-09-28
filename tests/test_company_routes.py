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
