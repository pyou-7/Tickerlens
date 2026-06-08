from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_SEARCH = "https://en.wikipedia.org/w/api.php"
_MIN_WORDS = 50
_MAX_CHARS = 1800


def get_description(company_name: str) -> str | None:
    """Fetch a company description from Wikipedia.

    Searches by company name, returns the extract if it's long enough,
    or None if nothing usable is found.
    """
    title = _search_title(company_name)
    if not title:
        return None
    return _fetch_extract(title)


def _search_title(query: str) -> str | None:
    try:
        resp = httpx.get(
            _SEARCH,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": 1,
            },
            timeout=10,
            headers={"User-Agent": "Tickerlens/1.0 (personal research tool)"},
        )
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        return results[0]["title"] if results else None
    except Exception:
        logger.warning("Wikipedia search failed for %r", query, exc_info=True)
        return None


def _fetch_extract(title: str) -> str | None:
    try:
        resp = httpx.get(
            _API.format(title=title),
            timeout=10,
            headers={"User-Agent": "Tickerlens/1.0 (personal research tool)"},
        )
        resp.raise_for_status()
        extract: str = resp.json().get("extract", "")
        if len(extract.split()) < _MIN_WORDS:
            return None
        return extract[:_MAX_CHARS]
    except Exception:
        logger.warning("Wikipedia extract failed for %r", title, exc_info=True)
        return None
