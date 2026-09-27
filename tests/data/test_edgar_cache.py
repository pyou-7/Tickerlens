import os
import time

import httpx

from tickerlens.data.edgar import EdgarClient


def test_mutable_cache_expires_and_scan_bypasses_cache(tmp_path):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"version": len(calls)})

    client = EdgarClient(user_agent="Test test@example.com", cache_dir=tmp_path,
                         min_request_interval_seconds=0,
                         http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    assert client.submissions(1)["version"] == 1
    assert client.submissions(1)["version"] == 1
    for path in tmp_path.iterdir():
        os.utime(path, (time.time() - 901, time.time() - 901))
    assert client.submissions(1)["version"] == 2
    assert client.submissions(1, force_refresh=True)["version"] == 3
    assert client.companyfacts(1)["version"] == 4
    assert client.companyfacts(1)["version"] == 5


def test_failed_refresh_does_not_replace_good_cache(tmp_path):
    responses = iter([httpx.Response(200, json={"ok": True}), httpx.Response(503)])
    client = EdgarClient(user_agent="Test test@example.com", cache_dir=tmp_path,
                         min_request_interval_seconds=0,
                         http_client=httpx.Client(transport=httpx.MockTransport(lambda r: next(responses))))
    client.submissions(1)
    import pytest
    with pytest.raises(httpx.HTTPStatusError):
        client.submissions(1, force_refresh=True)
    assert client.submissions(1) == {"ok": True}
