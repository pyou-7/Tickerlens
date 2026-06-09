from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_SEARCH = "https://en.wikipedia.org/w/api.php"
_MIN_WORDS = 50
_MAX_CHARS = 1800
_STOP_WORDS = {"inc", "corp", "co", "ltd", "llc", "plc", "the", "and", "of", "group"}

# Sentinel: fetch succeeded but no relevant article found.
# Distinct from None which means a network/parse error occurred.
NOT_FOUND = object()


def get_description(company_name: str) -> str | None:
    """Fetch a company description from Wikipedia.

    Returns a description string, or None if no relevant page exists or
    a transient error occurred. Callers can check whether None came from
    a confirmed non-match by the `description is None and title is None`
    path — but for most uses, None means "don't overwrite existing data."

    Internal logic:
      - _search_title returns None on network error, empty-string sentinel on
        "no results found" so we can distinguish the two cases.
      - _title_relevant gates on the first significant word matching.
    """
    title = _search_title(company_name)
    if title is None:
        return None  # network error — caller should keep existing DB value
    if title == "" or not _title_relevant(title, company_name):
        return None  # confirmed no relevant match — caller may clear DB value
    return _fetch_extract(title)


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
    """Return the Wikipedia title, empty string if no results, None on error."""
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
            headers={"User-Agent": "Tickerlens/1.0 (personal research tool)"},
        )
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        return results[0]["title"] if results else ""
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
