"""Tests for PWA and Mobile App integration."""
from fastapi.testclient import TestClient
from tickerlens.main import app


def test_pwa_manifest_route() -> None:
    client = TestClient(app)
    resp = client.get("/static/manifest.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Tickerlens — Financial Research"
    assert data["short_name"] == "Tickerlens"
    assert data["display"] == "standalone"
    assert data["start_url"] == "/"
    assert len(data["icons"]) >= 2


def test_pwa_service_worker_route() -> None:
    client = TestClient(app)
    resp = client.get("/static/sw.js")
    assert resp.status_code == 200
    assert "CACHE_NAME" in resp.text
    assert "PRECACHE_ASSETS" in resp.text


def test_pwa_icons_routes() -> None:
    client = TestClient(app)
    # SVG
    resp_svg = client.get("/static/icons/icon.svg")
    assert resp_svg.status_code == 200
    assert "<svg" in resp_svg.text

    # 192x192 PNG
    resp_192 = client.get("/static/icons/icon-192.png")
    assert resp_192.status_code == 200
    assert resp_192.content.startswith(b"\x89PNG")

    # 512x512 PNG
    resp_512 = client.get("/static/icons/icon-512.png")
    assert resp_512.status_code == 200
    assert resp_512.content.startswith(b"\x89PNG")


def test_base_template_mobile_meta_tags() -> None:
    client = TestClient(app)
    resp = client.get("/calendar")
    assert resp.status_code == 200
    html = resp.text
    assert 'manifest.json' in html
    assert 'viewport-fit=cover' in html
    assert 'apple-mobile-web-app-capable' in html
    assert 'apple-mobile-web-app-status-bar-style' in html
    assert 'safe-area-inset-top' in html
    assert 'safe-area-inset-bottom' in html
