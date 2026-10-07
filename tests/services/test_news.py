"""Tests for the latest-news service (Google News RSS, TTL cache, never-raise)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tickerlens.services.news import (
    NewsCache,
    NewsItem,
    _build_query,
    get_company_news,
    parse_news_feed,
)

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>"AAPL stock" - Google News</title>
<item>
  <title>Apple unveils new chip - Reuters</title>
  <link>https://news.google.com/rss/articles/abc123</link>
  <pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate>
  <source url="https://www.reuters.com">Reuters</source>
</item>
<item>
  <title>iPhone sales beat estimates</title>
  <link>https://news.google.com/rss/articles/def456</link>
  <pubDate>Sun, 04 Oct 2026 08:30:00 GMT</pubDate>
</item>
<item>
  <title>Broken item with no link</title>
</item>
</channel></rss>"""


def test_parse_news_feed_extracts_items() -> None:
    items = parse_news_feed(_SAMPLE_RSS)
    assert len(items) == 2  # the link-less item is skipped
    assert items[0].title == "Apple unveils new chip"
    assert items[0].source == "Reuters"
    assert items[0].url == "https://news.google.com/rss/articles/abc123"
    assert items[0].published_at == datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)


def test_parse_news_feed_source_fallback() -> None:
    items = parse_news_feed(_SAMPLE_RSS)
    # second item has no "- Source" suffix and no <source> element
    assert items[1].source == "News"


def test_parse_news_feed_respects_limit() -> None:
    items = parse_news_feed(_SAMPLE_RSS, limit=1)
    assert len(items) == 1


def test_parse_news_feed_never_raises_on_garbage() -> None:
    assert parse_news_feed("not xml at all") == []
    assert parse_news_feed("<rss><channel></channel></rss>") == []


def test_news_item_age_label() -> None:
    now = datetime.now(timezone.utc)
    assert NewsItem(title="t", url="u", source="s", published_at=now).age_label == "just now"
    assert NewsItem(title="t", url="u", source="s",
                    published_at=now - timedelta(minutes=5)).age_label == "5m ago"
    assert NewsItem(title="t", url="u", source="s",
                    published_at=now - timedelta(hours=3)).age_label == "3h ago"
    assert NewsItem(title="t", url="u", source="s",
                    published_at=now - timedelta(days=2)).age_label == "2d ago"
    assert NewsItem(title="t", url="u", source="s").age_label == ""


def _fake_fetch(query: str, limit: int) -> list[NewsItem]:
    return [
        NewsItem(title=f"{query} headline {i}", url=f"https://x/{i}", source="Test")
        for i in range(limit)
    ]


def test_build_query_prefers_company_name() -> None:
    # single-letter tickers are ambiguous under a bare ticker query:
    # "T stock" resolves to Japanese 6098.T and quote-page placeholders
    assert _build_query("T", "AT&T Inc.") == "AT&T Inc. stock"
    assert _build_query("F", "Ford Motor Company") == "Ford Motor Company stock"
    assert _build_query("AAPL", None) == "AAPL stock"
    assert _build_query("AAPL", "  ") == "AAPL stock"


def test_parse_news_feed_drops_quote_page_artifacts() -> None:
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>Ford Motor Company (F) Stock Price, News, Quote &amp; History - Yahoo Finance</title>
  <link>https://news.google.com/rss/articles/a</link>
</item>
<item>
  <title>symbol__ Stock Quote Price and Forecast - CNN</title>
  <link>https://news.google.com/rss/articles/b</link>
</item>
<item>
  <title>Ford signs battery deal - Reuters</title>
  <link>https://news.google.com/rss/articles/c</link>
</item>
</channel></rss>"""
    items = parse_news_feed(rss)
    assert [i.title for i in items] == ["Ford signs battery deal"]


def test_news_cache_passes_query_to_fetch() -> None:
    seen: list[str] = []

    def spy_fetch(query: str, limit: int) -> list[NewsItem]:
        seen.append(query)
        return _fake_fetch(query, limit)

    cache = NewsCache(ttl_seconds=60, fetch=spy_fetch)
    items = cache.get("T", "AT&T Inc. stock")
    assert seen == ["AT&T Inc. stock"]
    assert items[0].title.startswith("AT&T Inc. stock")
    # second call is served from cache — no refetch
    cache.get("t", "AT&T Inc. stock")
    assert seen == ["AT&T Inc. stock"]


def test_news_cache_serves_from_cache_without_refetch() -> None:
    calls: list[str] = []

    def counting_fetch(query: str, limit: int) -> list[NewsItem]:
        calls.append(query)
        return _fake_fetch(query, limit)

    cache = NewsCache(ttl_seconds=60, fetch=counting_fetch)
    first = cache.get("AAPL")
    second = cache.get("aapl")  # case-insensitive key
    assert first == second
    assert calls == ["AAPL stock"]  # fetched exactly once, default ticker query


def test_news_cache_serves_stale_on_fetch_failure() -> None:
    state = {"fail": False}

    def flaky_fetch(query: str, limit: int) -> list[NewsItem]:
        if state["fail"]:
            raise RuntimeError("network down")
        return _fake_fetch(query, limit)

    cache = NewsCache(ttl_seconds=0.01, fetch=flaky_fetch)
    good = cache.get("MSFT")
    assert len(good) == 6
    state["fail"] = True
    import time

    time.sleep(0.02)  # let the entry expire
    stale = cache.get("MSFT")
    assert stale == good  # last good data served, nothing raised


def test_get_company_news_never_raises() -> None:
    # even a catastrophic cache failure must return []
    import tickerlens.services.news as news_mod

    class Boom(NewsCache):
        def get(self, ticker: str, query: str | None = None, limit: int = 6):  # type: ignore[override]
            raise RuntimeError("boom")

    original = news_mod._news_cache
    news_mod._news_cache = Boom()
    try:
        assert get_company_news("ZZZZ") == []
    finally:
        news_mod._news_cache = original


def test_news_route_renders_partial() -> None:
    from fastapi.testclient import TestClient

    from tickerlens.main import app

    client = TestClient(app)
    resp = client.get("/company/AAPL/news")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    # partial renders either headlines or the empty-state message
    assert "<ul" in resp.text or "No headlines" in resp.text
