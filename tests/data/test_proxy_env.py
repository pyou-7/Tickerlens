"""Regression test: bracketed IPv6 literals in no_proxy must not break httpx."""

from __future__ import annotations

import os

import httpx
import pytest

from tickerlens.data.proxy_env import sanitize_proxy_env


@pytest.fixture()
def bracketed_no_proxy(monkeypatch):
    monkeypatch.setenv(
        "no_proxy",
        "localhost,127.0.0.1,::1,[::1],198.19.0.1,fd8b:4f84:7d32:99::1,[fd8b:4f84:7d32:99::1]",
    )
    monkeypatch.setenv("NO_PROXY", os.environ["no_proxy"])


def test_sanitize_strips_brackets_from_ipv6(bracketed_no_proxy):
    assert sanitize_proxy_env() is True
    for var in ("no_proxy", "NO_PROXY"):
        entries = os.environ[var].split(",")
        assert not any(e.startswith("[") for e in entries)
        assert "::1" in entries  # same hosts still present, bare form


def test_sanitize_is_idempotent(bracketed_no_proxy):
    sanitize_proxy_env()
    assert sanitize_proxy_env() is False


def test_httpx_proxy_map_parses_after_sanitize(bracketed_no_proxy):
    """The real failure: httpx.Client() raised InvalidURL on the raw env."""
    from httpx._utils import URLPattern, get_environment_proxies

    sanitize_proxy_env()
    for key in get_environment_proxies():
        URLPattern(key)  # must not raise
    httpx.Client(timeout=5).close()
