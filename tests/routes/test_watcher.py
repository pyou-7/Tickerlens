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


def test_watcher_check_endpoint() -> None:
    response = client.post("/watcher/check")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Watched Companies" in response.text or "New SEC Filing" in response.text
