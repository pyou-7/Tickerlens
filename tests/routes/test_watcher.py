from fastapi.testclient import TestClient

from tickerlens.main import app

client = TestClient(app)


def test_watcher_status_endpoint() -> None:
    response = client.get("/watcher/status")
    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert "recent_events" in data
    assert isinstance(data["recent_events"], list)


def test_watcher_check_endpoint(monkeypatch) -> None:
    from tickerlens.routes import watcher
    from tickerlens.services.filing_watcher import WatcherCheckSummary
    monkeypatch.setattr(watcher._svc, 'check_watchlist', lambda **kwargs:
                        WatcherCheckSummary(checked_count=2, failed_tickers=['TEST']))
    response = client.post("/watcher/check")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'Scan incomplete' in response.text
    assert 'TEST' in response.text
    assert 'All Watched Companies Up to Date' not in response.text
