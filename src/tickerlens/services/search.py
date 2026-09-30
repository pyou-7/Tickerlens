"""Company search for the autocomplete combobox (PRD §4.10).

Data source is SEC ``company_tickers.json`` — ticker, company name, and CIK
for all ~10,000 EDGAR filers — already fetched and cached by
``data/edgar.py``. Ranking is a pure function so it's unit-testable; the
parsed entry list is cached for the process lifetime (the file changes
rarely, and navigation resolves the CIK live anyway).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from tickerlens.data.edgar import normalize_cik

# Max suggestions per PRD §4.10.
MAX_SUGGESTIONS = 8


def sibling_tickers(
    cik: str, exclude_ticker: str | None, entries: list[dict[str, str]]
) -> list[str]:
    """Other SEC-listed tickers sharing ``cik`` (PRD §4.9 — "Also trades as").

    e.g. viewing GOOG shows GOOGL, since both map to Alphabet's CIK.
    Sorted alphabetically; ``exclude_ticker`` is omitted (case-insensitive).
    Pure function so it's unit-testable; callers pass the cached entries
    from :func:`get_search_entries`.
    """
    excl = (exclude_ticker or "").upper()
    return sorted(
        e["ticker"]
        for e in entries
        if e.get("cik") == cik and e["ticker"].upper() != excl
    )


class SearchResult(BaseModel):
    ticker: str
    name: str
    cik: str


def _entries_from_tickers(company_tickers: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for item in company_tickers.values():
        ticker = str(item.get("ticker", "")).strip()
        # SEC company_tickers.json uses "title" for the company name.
        name = str(item.get("title") or item.get("name") or "").strip()
        if not ticker:
            continue
        entries.append(
            {
                "ticker": ticker.upper(),
                "name": name,
                "cik": normalize_cik(item.get("cik_str", "")),
            }
        )
    return entries


_entries_cache: list[dict[str, str]] | None = None


def get_search_entries(edgar_client) -> list[dict[str, str]]:
    """Parse ``company_tickers.json`` into search entries (cached per process)."""
    global _entries_cache
    if _entries_cache is None:
        _entries_cache = _entries_from_tickers(edgar_client.company_tickers())
    return _entries_cache


def search_companies(query: str, entries: list[dict[str, str]]) -> list[SearchResult]:
    """Rank entries against ``query`` per PRD §4.10.

    Rank order: exact ticker match → ticker prefix → company-name prefix →
    ticker/name substring. Ties break alphabetically by ticker (market caps
    aren't in company_tickers.json). Returns at most ``MAX_SUGGESTIONS``.
    """
    q = query.strip().lower()
    if not q:
        return []
    exact: list[dict[str, str]] = []
    ticker_prefix: list[dict[str, str]] = []
    name_prefix: list[dict[str, str]] = []
    contains: list[dict[str, str]] = []
    for entry in entries:
        ticker = entry["ticker"].lower()
        name = entry["name"].lower()
        if ticker == q:
            exact.append(entry)
        elif ticker.startswith(q):
            ticker_prefix.append(entry)
        elif name.startswith(q):
            name_prefix.append(entry)
        elif q in ticker or q in name:
            contains.append(entry)
    ranked: list[dict[str, str]] = []
    for bucket in (exact, ticker_prefix, name_prefix, contains):
        ranked.extend(sorted(bucket, key=lambda e: e["ticker"]))
    return [
        SearchResult(ticker=e["ticker"], name=e["name"], cik=e["cik"])
        for e in ranked[:MAX_SUGGESTIONS]
    ]
