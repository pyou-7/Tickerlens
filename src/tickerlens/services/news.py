"""Latest-news service backed by the Google News RSS feed.

The user asked for the latest news for companies on the overview page.
Yahoo Finance's per-ticker RSS is bot-blocked from our servers (it returns
the "Will be right back" page), so this service queries Google News RSS for
"<TICKER> stock" instead — free, keyless, and reliable from this VM.

Design constraints (matches the quote-cache conventions in data/yahoo.py):
- Thread-safe TTL cache so the overview page never blocks on the network
  and a transient failure never blanks previously-good data.
- Never raises: fetch problems are logged and an empty list is returned.
"""

from __future__ import annotations

import email.utils
import logging
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime, timezone

from pydantic import BaseModel

logger = logging.getLogger(__name__)

NEWS_TTL_SECONDS = 1800  # 30 minutes — news is slow-moving relative to quotes
NEWS_FETCH_TIMEOUT = 10
NEWS_LIMIT = 6

_GNEWS_URL = (
    "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US%3Aen"
)
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) Tickerlens/1.0"


class NewsItem(BaseModel):
    """A single headline about a company."""

    title: str
    url: str
    source: str
    published_at: datetime | None = None

    @property
    def age_label(self) -> str:
        """Human relative age ("2h ago", "3d ago") or empty when unknown."""
        if self.published_at is None:
            return ""
        delta = datetime.now(timezone.utc) - self.published_at
        minutes = int(delta.total_seconds() // 60)
        if minutes < 1:
            return "just now"
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 30:
            return f"{days}d ago"
        months = days // 30
        return f"{months}mo ago"


def _strip_source_suffix(title: str) -> tuple[str, str]:
    """Split Google's "Headline - SourceName" convention into (title, source)."""
    if " - " in title:
        head, _, tail = title.rpartition(" - ")
        if head.strip() and tail.strip() and len(tail) < 60:
            return head.strip(), tail.strip()
    return title.strip(), ""


def _parse_pub_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def parse_news_feed(xml_text: str, limit: int = NEWS_LIMIT) -> list[NewsItem]:
    """Parse a Google News RSS document into NewsItems. Never raises."""
    items: list[NewsItem] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("Could not parse Google News RSS", exc_info=True)
        return items
    channel = root.find("channel")
    if channel is None:
        return items
    for entry in channel.findall("item")[:limit]:
        try:
            raw_title = (entry.findtext("title") or "").strip()
            link = (entry.findtext("link") or "").strip()
            if not raw_title or not link:
                continue
            title, source = _strip_source_suffix(raw_title)
            src_el = entry.find("source")
            if not source and src_el is not None and src_el.text:
                source = src_el.text.strip()
            items.append(
                NewsItem(
                    title=title,
                    url=link,
                    source=source or "News",
                    published_at=_parse_pub_date(entry.findtext("pubDate")),
                )
            )
        except Exception:  # one bad item must not kill the feed
            logger.debug("Skipping malformed news item", exc_info=True)
    return items


def _fetch_feed(ticker: str, limit: int = NEWS_LIMIT) -> list[NewsItem]:
    query = urllib.parse.quote(f"{ticker} stock")
    url = _GNEWS_URL.format(q=query)
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=NEWS_FETCH_TIMEOUT) as resp:
        xml_text = resp.read().decode("utf-8", errors="replace")
    return parse_news_feed(xml_text, limit=limit)


class NewsCache:
    """Thread-safe TTL cache for per-company news. Never raises.

    Mirrors QuoteCache: on fetch failure the last good items are served
    until they expire, then an empty list — a news outage must never
    break the overview page.
    """

    def __init__(
        self,
        ttl_seconds: float = NEWS_TTL_SECONDS,
        *,
        fetch: Callable[[str, int], list[NewsItem]] = _fetch_feed,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._fetch = fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[str, tuple[float, list[NewsItem]]] = {}

    def get(self, ticker: str, limit: int = NEWS_LIMIT) -> list[NewsItem]:
        key = ticker.upper()
        with self._lock:
            hit = self._items.get(key)
            if hit and self._clock() - hit[0] < self.ttl_seconds:
                return hit[1][:limit]
            stale = hit[1] if hit else []
        try:
            fresh = self._fetch(key, limit)
        except Exception:
            logger.warning("Google News fetch failed for %s", key, exc_info=True)
            return stale[:limit]
        with self._lock:
            self._items[key] = (self._clock(), fresh)
        return fresh[:limit]

    def invalidate(self, ticker: str) -> None:
        with self._lock:
            self._items.pop(ticker.upper(), None)


_news_cache = NewsCache()


def get_company_news(ticker: str, limit: int = NEWS_LIMIT) -> list[NewsItem]:
    """Latest headlines for a ticker. Never raises — returns [] on failure."""
    try:
        return _news_cache.get(ticker, limit)
    except Exception:
        logger.warning("News lookup failed for %s", ticker, exc_info=True)
        return []
