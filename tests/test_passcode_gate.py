"""Shared-passcode gate (tickerlens.auth): cookie + Bearer + exemptions."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tickerlens.config import get_settings
from tickerlens.main import app

PASSCODE = "test-passcode-123"


@pytest.fixture
def gated_client(monkeypatch):
    """App with TICKERLENS_PASSCODE set (gate on)."""
    monkeypatch.setenv("TICKERLENS_PASSCODE", PASSCODE)
    get_settings.cache_clear()
    yield TestClient(app, raise_server_exceptions=False)
    get_settings.cache_clear()


@pytest.fixture
def open_client(monkeypatch):
    """App with no passcode configured (gate off, local-dev behaviour)."""
    monkeypatch.delenv("TICKERLENS_PASSCODE", raising=False)
    get_settings.cache_clear()
    yield TestClient(app, raise_server_exceptions=False)
    get_settings.cache_clear()


def _login(client: TestClient, passcode: str = PASSCODE, next_url: str = "/"):
    return client.post(
        "/login",
        data={"passcode": passcode, "next": next_url},
        follow_redirects=False,
    )


# ── Gate off (default / local dev) ──────────────────────────────────────────


def test_gate_off_home_loads_without_auth(open_client: TestClient) -> None:
    assert open_client.get("/").status_code == 200


def test_gate_off_login_page_redirects_home(open_client: TestClient) -> None:
    resp = open_client.get("/login", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


# ── Gate on: unauthenticated visitors are redirected ────────────────────────


def test_gate_on_home_redirects_to_login(gated_client: TestClient) -> None:
    resp = gated_client.get("/", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login?next=%2F"


def test_gate_on_company_page_redirects_to_login(gated_client: TestClient) -> None:
    resp = gated_client.get("/company/AAPL", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login?next=%2Fcompany%2FAAPL"


def test_gate_on_api_redirects_to_login(gated_client: TestClient) -> None:
    resp = gated_client.get("/api/search?q=AAPL", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"].startswith("/login?next=")


# ── Login page ──────────────────────────────────────────────────────────────


def test_login_page_renders_form(gated_client: TestClient) -> None:
    resp = gated_client.get("/login")
    assert resp.status_code == 200
    assert "passcode" in resp.text.lower()
    assert 'name="passcode"' in resp.text
    assert 'action="/login"' in resp.text


def test_login_page_keeps_next_param(gated_client: TestClient) -> None:
    resp = gated_client.get("/login?next=/company/AAPL")
    assert resp.status_code == 200
    assert 'value="/company/AAPL"' in resp.text


# ── Login submit ────────────────────────────────────────────────────────────


def test_login_wrong_passcode_is_rejected(gated_client: TestClient) -> None:
    resp = _login(gated_client, passcode="wrong-passcode")
    assert resp.status_code == 401
    assert "Incorrect passcode" in resp.text
    assert "tickerlens_auth" not in resp.headers.get("set-cookie", "")


def test_login_correct_passcode_sets_cookie_and_redirects(
    gated_client: TestClient,
) -> None:
    resp = _login(gated_client)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert "tickerlens_auth=" in resp.headers["set-cookie"]
    assert "httponly" in resp.headers["set-cookie"].lower()


def test_login_correct_passcode_honours_safe_next(gated_client: TestClient) -> None:
    resp = _login(gated_client, next_url="/company/AAPL")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/company/AAPL"


def test_login_rejects_offsite_next(gated_client: TestClient) -> None:
    resp = _login(gated_client, next_url="https://evil.example.com/")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


# ── Cookie + Bearer auth ────────────────────────────────────────────────────


def test_cookie_from_login_unlocks_pages(gated_client: TestClient) -> None:
    _login(gated_client)
    assert gated_client.get("/").status_code == 200
    assert gated_client.get("/company/AAPL").status_code == 200


def test_bearer_passcode_unlocks_pages(gated_client: TestClient) -> None:
    resp = gated_client.get("/", headers={"Authorization": f"Bearer {PASSCODE}"})
    assert resp.status_code == 200


def test_wrong_bearer_stays_locked(gated_client: TestClient) -> None:
    resp = gated_client.get(
        "/", headers={"Authorization": "Bearer not-the-passcode"},
        follow_redirects=False,
    )
    assert resp.status_code == 307


def test_logout_clears_cookie_and_relocks(gated_client: TestClient) -> None:
    _login(gated_client)
    assert gated_client.get("/").status_code == 200
    resp = gated_client.get("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert "tickerlens_auth=" in resp.headers["set-cookie"]
    assert gated_client.get("/", follow_redirects=False).status_code == 307


# ── Exemptions ──────────────────────────────────────────────────────────────


def test_healthz_is_open_without_auth(gated_client: TestClient) -> None:
    resp = gated_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_static_is_open_without_auth(gated_client: TestClient) -> None:
    resp = gated_client.get("/static/js/search.js")
    assert resp.status_code == 200
