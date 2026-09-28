from __future__ import annotations

from unittest.mock import patch

import httpx

from tickerlens.data.wikipedia import _fetch_extract, _search_title


def _boom(*args, **kwargs):
    raise httpx.InvalidURL("Invalid port: ':1]'")


def test_search_title_invalid_url_returns_none() -> None:
    """httpx.InvalidURL is not an HTTPError subclass; it must still be
    swallowed per this module's None-on-network-error contract."""
    with patch("tickerlens.data.wikipedia.httpx.get", side_effect=_boom):
        assert _search_title("Apple Inc") is None


def test_fetch_extract_invalid_url_returns_none() -> None:
    with patch("tickerlens.data.wikipedia.httpx.get", side_effect=_boom):
        assert _fetch_extract("Apple Inc.") is None
