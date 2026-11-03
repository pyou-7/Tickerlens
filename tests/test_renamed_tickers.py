"""Renamed-symbol redirects (batch 119): /company/MMC -> /company/MRSH."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from tickerlens import routes
from tickerlens.main import app
from tickerlens.routes.company import resolve_renamed_ticker
from tickerlens.services.financials import CompanyNotFoundError


# ── map helper ────────────────────────────────────────────────────────────────

def test_resolve_renamed_ticker_known_rename() -> None:
    assert resolve_renamed_ticker("MMC") == "MRSH"


def test_resolve_renamed_ticker_case_insensitive() -> None:
    assert resolve_renamed_ticker("mmc") == "MRSH"


def test_resolve_renamed_ticker_unknown_returns_none() -> None:
    assert resolve_renamed_ticker("ZZZZ") is None
    assert resolve_renamed_ticker("MRSH") is None  # the current ticker itself


# ── HTTP middleware ───────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch) -> TestClient:
    """App with the financials service stubbed to raise for unknown tickers."""
    mock_svc = MagicMock()
    mock_svc.get_overview.side_effect = CompanyNotFoundError("Unknown ticker")
    mock_svc.get_detail.side_effect = CompanyNotFoundError("Unknown ticker")
    mock_svc.fetch_and_persist.side_effect = CompanyNotFoundError("Unknown ticker")
    monkeypatch.setattr(routes.company, "_svc", mock_svc)
    return TestClient(app, raise_server_exceptions=False)


def test_renamed_overview_redirects_permanently(client: TestClient) -> None:
    resp = client.get("/company/MMC", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/company/MRSH"


def test_renamed_redirect_is_case_insensitive(client: TestClient) -> None:
    resp = client.get("/company/mmc", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/company/MRSH"


def test_renamed_redirect_preserves_subpath_and_query(client: TestClient) -> None:
    resp = client.get("/company/MMC/detail?granularity=yearly", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/company/MRSH/detail?granularity=yearly"


def test_renamed_redirect_preserves_vs_other_side(client: TestClient) -> None:
    resp = client.get("/company/MMC/vs/AAPL", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/company/MRSH/vs/AAPL"


def test_non_renamed_ticker_not_redirected(client: TestClient) -> None:
    resp = client.get("/company/ZZZZ", follow_redirects=False)
    assert resp.status_code == 404


def test_renamed_ticker_post_not_redirected(client: TestClient) -> None:
    # POST forms keep their own semantics: the watch handler (mocked, no
    # exception) answers with its own 303 back to /company/MMC, never a
    # 301 to MRSH — no silent action on a different company.
    resp = client.post("/company/MMC/watch", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/company/MMC"
