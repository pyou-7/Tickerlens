from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_SEARCH = "https://en.wikipedia.org/w/api.php"
_MIN_WORDS = 50
_MAX_CHARS = 1800
_STOP_WORDS = {"inc", "corp", "co", "ltd", "llc", "plc", "the", "and", "of", "group"}


import hashlib
from pathlib import Path

_WIKI_CACHE_DIR = Path(".edgar_cache/wikipedia")
_USER_AGENT = "Tickerlens/1.0 (https://github.com/tickerlens; investment-research-app@example.com)"


def get_description(company_name: str) -> str | None:
    """Fetch a company description from Wikipedia.

    Returns a description string, or None if no relevant page exists,
    the relevance check fails, or a transient network error occurs.
    """
    _WIKI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.md5(company_name.lower().encode("utf-8")).hexdigest()
    cache_file = _WIKI_CACHE_DIR / f"{cache_key}.txt"

    if cache_file.exists():
        text = cache_file.read_text(encoding="utf-8").strip()
        return text if text else None

    title = _search_title(company_name)
    if not title or not _title_relevant(title, company_name):
        try:
            cache_file.write_text("", encoding="utf-8")
        except Exception:
            pass
        return None

    extract = _fetch_extract(title)
    try:
        cache_file.write_text(extract or "", encoding="utf-8")
    except Exception:
        pass
    return extract


def _title_relevant(title: str, company_name: str) -> bool:
    """Return True if the title's first significant word matches the company name's."""
    def significant_words(text: str) -> list[str]:
        return [
            w.lower().strip(".,")
            for w in text.split()
            if w.lower().strip(".,") not in _STOP_WORDS and len(w.strip(".,")) > 2
        ]

    title_words = set(significant_words(title))
    name_words = significant_words(company_name)
    if not name_words:
        return False
    return name_words[0] in title_words


def _search_title(query: str) -> str | None:
    """Return the Wikipedia title, empty string if no results, None on network error."""
    try:
        resp = httpx.get(
            _SEARCH,
            params={
                "action": "query",
                "list": "search",
                "srsearch": f"{query} company",
                "format": "json",
                "srlimit": 1,
            },
            timeout=10,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        return results[0]["title"] if results else ""
    except (httpx.HTTPError, httpx.TimeoutException, OSError):
        logger.warning("Wikipedia search failed for %r", query, exc_info=True)
        return None


def _fetch_extract(title: str) -> str | None:
    try:
        resp = httpx.get(
            _API.format(title=title),
            timeout=10,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
        extract: str = resp.json().get("extract", "")
        if len(extract.split()) < _MIN_WORDS:
            return None
        return extract[:_MAX_CHARS]
    except (httpx.HTTPError, httpx.TimeoutException, OSError):
        logger.warning("Wikipedia extract failed for %r", title, exc_info=True)
        return None
