from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_SEARCH = "https://en.wikipedia.org/w/api.php"
_MIN_WORDS = 50
_MAX_CHARS = 1800


_STOP_WORDS = {"inc", "corp", "co", "ltd", "llc", "plc", "the", "and", "of", "group"}


def get_description(company_name: str) -> str | None:
    """Fetch a company description from Wikipedia.

    Searches by company name + 'company' for disambiguation, then validates
    that the returned title has at least one meaningful word in common with
    the query before returning the extract.
    """
    query = f"{company_name} company"
    title = _search_title(query)
    if not title or not _title_relevant(title, company_name):
        return None
    return _fetch_extract(title)


def _title_relevant(title: str, company_name: str) -> bool:
    """Return True if the title's first significant word matches the company name's first significant word."""
    def first_significant(text: str) -> str | None:
        for word in text.split():
            w = word.lower().strip(".,")
            if w not in _STOP_WORDS and len(w) > 2:
                return w
        return None

    title_words = {w.lower() for w in title.split()} - _STOP_WORDS
    name_words = {w.lower().strip(".,") for w in company_name.split()} - _STOP_WORDS
    first = first_significant(company_name)
    # Require the first meaningful word AND at least one total overlap
    return first is not None and first in title_words and bool(title_words & name_words)


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
