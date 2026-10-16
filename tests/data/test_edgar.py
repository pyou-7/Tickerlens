"""Unit tests for EdgarClient ticker resolution."""

import pytest

import httpx

from tickerlens.data.edgar import EdgarClient


def _client_with_tickers(monkeypatch) -> EdgarClient:
    client = EdgarClient()
    monkeypatch.setattr(
        client,
        "company_tickers",
        lambda: {
            "0": {"ticker": "BRK-B", "cik_str": "1067983", "title": "Berkshire Hathaway Inc"},
            "1": {"ticker": "AAPL", "cik_str": "320193", "title": "Apple Inc"},
        },
    )
    return client


def test_cik_for_ticker_exact_match(monkeypatch) -> None:
    client = _client_with_tickers(monkeypatch)
    assert client.cik_for_ticker("aapl") == "0000320193"


def test_cik_for_ticker_normalizes_dot_and_slash_to_hyphen(monkeypatch) -> None:
    # Everyone types BRK.B / BRK/A; SEC lists BRK-B / BRK-A.
    client = _client_with_tickers(monkeypatch)
    assert client.cik_for_ticker("BRK.B") == "0001067983"
    assert client.cik_for_ticker("brk.b") == "0001067983"


def test_cik_for_ticker_still_raises_for_unknown(monkeypatch) -> None:
    client = _client_with_tickers(monkeypatch)
    with pytest.raises(KeyError):
        client.cik_for_ticker("ZZZZ")


# ── disk-cache TTL (batch 37) ────────────────────────────────────────────────

import os
import time as _time
from unittest.mock import MagicMock


def _stub_get(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return MagicMock(return_value=resp)


def _fresh_client(tmp_path, **kwargs) -> EdgarClient:
    # A client whose User-Agent comes from settings (as in production) but
    # whose disk cache is an empty tmp dir, so every test starts uncached.
    return EdgarClient(cache_dir=str(tmp_path), **kwargs)


def test_fetch_json_serves_fresh_cache_without_http(tmp_path) -> None:
    client = _fresh_client(tmp_path, cache_ttl_seconds=3600)
    client._get = _stub_get({"n": 1})
    url = "https://data.sec.gov/submissions/CIK0000320193.json"

    assert client.fetch_json(url) == {"n": 1}

    client._get = _stub_get({"n": 999})  # would be returned if HTTP ran
    assert client.fetch_json(url) == {"n": 1}
    client._get.assert_not_called()


def test_fetch_json_refetches_stale_cache(tmp_path) -> None:
    client = _fresh_client(tmp_path, cache_ttl_seconds=60)
    client._get = _stub_get({"n": 1})
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    assert client.fetch_json(url) == {"n": 1}

    # Age the cache file beyond the TTL: the next read must go live again.
    cache_file = client._cache_file(url)
    old = _time.time() - 3600
    os.utime(cache_file, (old, old))

    client._get = _stub_get({"n": 2})
    assert client.fetch_json(url) == {"n": 2}
    assert client._get.call_count == 1


def test_companyfacts_fresh_kwarg_bypasses_cache(tmp_path) -> None:
    client = _fresh_client(tmp_path, cache_ttl_seconds=3600)
    client._get = _stub_get({"n": 1})
    assert client.companyfacts("0000320193") == {"n": 1}

    client._get = _stub_get({"n": 2})
    assert client.companyfacts("0000320193", fresh=True) == {"n": 2}
    assert client._get.call_count == 1


def test_submissions_fresh_kwarg_bypasses_cache(tmp_path) -> None:
    client = _fresh_client(tmp_path, cache_ttl_seconds=3600)
    client._get = _stub_get({"n": 1})
    assert client.submissions("0000320193") == {"n": 1}

    client._get = _stub_get({"n": 2})
    assert client.submissions("0000320193", fresh=True) == {"n": 2}
    assert client._get.call_count == 1


# ── serve-stale-on-error (batch 76) ──────────────────────────────────────────


def _age_cache(client: EdgarClient, url: str, *, suffix: str = ".json") -> None:
    cache_file = client._cache_file(url)
    if suffix != ".json":
        cache_file = cache_file.with_suffix(suffix)
    old = _time.time() - 3600
    os.utime(cache_file, (old, old))


def _stub_get_raises(exc: Exception = httpx.ConnectTimeout("boom")) -> MagicMock:
    return MagicMock(side_effect=exc)


def test_fetch_json_serves_stale_cache_on_fetch_error(tmp_path) -> None:
    client = _fresh_client(tmp_path, cache_ttl_seconds=60)
    client._get = _stub_get({"n": 1})
    url = "https://www.sec.gov/files/company_tickers.json"
    assert client.fetch_json(url) == {"n": 1}

    _age_cache(client, url)

    client._get = _stub_get_raises()
    assert client.fetch_json(url) == {"n": 1}  # stale, never raises


def test_fetch_json_still_raises_with_no_cache(tmp_path) -> None:
    client = _fresh_client(tmp_path, cache_ttl_seconds=60)
    client._get = _stub_get_raises()
    url = "https://www.sec.gov/files/company_tickers.json"
    with pytest.raises(httpx.ConnectTimeout):
        client.fetch_json(url)


def test_fetch_json_serves_stale_on_http_error_status(tmp_path) -> None:
    client = _fresh_client(tmp_path, cache_ttl_seconds=60)
    client._get = _stub_get({"n": 1})
    url = "https://www.sec.gov/files/company_tickers.json"
    assert client.fetch_json(url) == {"n": 1}

    _age_cache(client, url)

    bad = MagicMock()
    bad.raise_for_status.side_effect = httpx.HTTPStatusError(
        "503", request=MagicMock(), response=MagicMock()
    )
    client._get = MagicMock(return_value=bad)
    assert client.fetch_json(url) == {"n": 1}


def test_fetch_json_failure_cooldown_skips_live_retry(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(EdgarClient, "FAILURE_COOLDOWN_SECONDS", 300)
    client = _fresh_client(tmp_path, cache_ttl_seconds=60)
    client._get = _stub_get({"n": 1})
    url = "https://www.sec.gov/files/company_tickers.json"
    assert client.fetch_json(url) == {"n": 1}

    _age_cache(client, url)

    client._get = _stub_get_raises()
    assert client.fetch_json(url) == {"n": 1}
    assert client._get.call_count == 1

    # Within the cooldown the live fetch is not attempted again: the stale
    # copy is served straight away (this is what prevented the ~10 min
    # stall in the batch-75 incident).
    assert client.fetch_json(url) == {"n": 1}
    assert client._get.call_count == 1


def test_fetch_json_recovers_after_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(EdgarClient, "FAILURE_COOLDOWN_SECONDS", 0)
    client = _fresh_client(tmp_path, cache_ttl_seconds=60)
    client._get = _stub_get({"n": 1})
    url = "https://www.sec.gov/files/company_tickers.json"
    assert client.fetch_json(url) == {"n": 1}

    _age_cache(client, url)

    client._get = _stub_get_raises()
    assert client.fetch_json(url) == {"n": 1}

    # Once the cooldown lapses the live fetch is retried and success clears
    # the failure record (next failure goes live again, not to stale-only).
    client._get = _stub_get({"n": 2})
    assert client.fetch_json(url) == {"n": 2}
    assert client._get.call_count == 1

    _age_cache(client, url)
    client._get = _stub_get_raises()
    assert client.fetch_json(url) == {"n": 2}
    assert client._get.call_count == 1


def test_fetch_text_serves_stale_on_error(tmp_path) -> None:
    client = _fresh_client(tmp_path, cache_ttl_seconds=60)
    text_stub = MagicMock()
    text_stub.text = "<html>old</html>"
    client._get = MagicMock(return_value=text_stub)
    url = "https://www.sec.gov/Archives/edgar/data/320193/index.html"
    assert client.fetch_text(url) == "<html>old</html>"

    _age_cache(client, url, suffix=".html")

    client._get = _stub_get_raises()
    assert client.fetch_text(url) == "<html>old</html>"
