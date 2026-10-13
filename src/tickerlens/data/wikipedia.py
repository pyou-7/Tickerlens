from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_SEARCH = "https://en.wikipedia.org/w/api.php"
# Stub-rejection floor, not a quality bar: the summary API's extract length
# varies between fetches (egress caching), and real company summaries land
# well under the old 50-word floor — Broadcom's live summary measured 48
# words, Visa's 32, GE's 20. Anything at/above 15 words on a
# relevance-checked standard-type page is a real description; disambiguation
# pages are rejected by type, not by length.
_MIN_WORDS = 15
_MAX_CHARS = 1800
_STOP_WORDS = {"inc", "corp", "co", "ltd", "llc", "plc", "the", "and", "of", "group"}
# Trailing corporate-suffix tokens stripped for the fallback search query
# (batch 54): Wikipedia's ranking degrades when the full legal name plus
# " company" is queried ("Atlassian Corp company" returns junk while
# "Atlassian company" hits the article). Only ONE trailing token is
# stripped, and only for the fallback query — relevance scoring still uses
# the full legal name.
_CORP_SUFFIXES = frozenset(
    {
        "corp", "corporation", "inc", "incorporated", "co", "company", "ltd",
        "limited", "llc", "plc", "lp", "l.p.", "sa", "ag", "nv", "pty",
        "holdings", "holding", "group", "trust", "bancorp", "bancshares",
    }
)
# Curated DBA/nickname aliases (batch 58): ticker -> the exact Wikipedia
# article title, for companies whose SEC legal name cannot reach the right
# article on its own. Human-verified only — never guess an entry:
# - CART: "Maplebear Inc." does business as Instacart; the legal-name
#   search's top hit IS "Instacart" but word-agreement against "Maplebear"
#   rejects it. The article's first line is "Maplebear Inc., doing business
#   as Instacart..." (verified).
# - SHOO: "STEVEN MADDEN, LTD." — the article is "Steve Madden, Ltd." and
#   "steve" vs "steven" defeats first-word agreement. The ", Ltd." is
#   load-bearing: the bare title "Steve Madden" is the founder's page, so
#   the alias must be the exact company-article title (verified).
# Tickers with no Wikipedia article at all (AGNC, APLD, MPLX) stay
# out — an alias can't fix a missing article, and pointing at a parent or
# subsidiary would be a batch-47-class misattribution.
_DBA_ALIASES = {
    "CART": "Instacart",
    "SHOO": "Steve Madden, Ltd.",
    # Batch 64 (live ORLY case): "O REILLY AUTOMOTIVE INC" — Wikipedia's top
    # hit IS the right article, but the apostrophe-join ("o"+"reilly" vs
    # normalized "oreilly") zeroes the word-overlap relevance score, so every
    # relevance path rejects it. The company does business as O'Reilly Auto
    # Parts (SEC 10-K cover page: "O'Reilly Automotive, Inc." dba O'Reilly
    # Auto Parts; verified 2026-10-13). Exact-match guarded like the rest.
    "ORLY": "O'Reilly Auto Parts",
}


def get_description(company_name: str, ticker: str | None = None) -> str | None:
    """Fetch a company description from Wikipedia.

    Returns a description string, or None if no relevant page exists,
    the relevance check fails, or a transient network error occurs.
    Callers should treat None as "overwrite with None" — a fresh search
    that finds nothing is preferable to keeping stale/wrong text.
    """
    title = _best_title(company_name, ticker)
    if not title:
        return None
    return _fetch_extract(title)


def _relevance_overlap(title: str, company_name: str, ticker: str | None = None) -> int:
    """Shared-word overlap between a candidate title and the company name.

    An exact ticker-title match ("AMD") always wins.
    """
    if ticker and title.strip().lower() == ticker.strip().lower():
        return 100
    return len(set(_normalize_words(title)) & set(_normalize_words(company_name)))


def _name_word_set(company_name: str, ticker: str | None = None) -> set[str]:
    words = set(_normalize_words(company_name))
    if ticker:
        words.add(ticker.strip().lower())
    return words


def _bare_title_words(title: str) -> set[str]:
    """Title words with any parenthetical removed ("Amazon (company)" ->
    {amazon}), for overlap scoring."""
    start, end = title.find("("), title.rfind(")")
    bare = title[:start] + " " + title[end + 1 :] if 0 <= start < end else title
    return set(_normalize_words(bare))


def _squashed(text: str) -> str:
    """Lowercase alphanumeric-only form, stop words retained.

    Used for exact-name comparison, where stop-word removal would be lossy:
    "Domino's Pizza Group plc" must not equal "DOMINOS PIZZA INC".
    """
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _bare_title(title: str) -> str:
    """Title with any parenthetical removed."""
    start, end = title.find("("), title.rfind(")")
    return (title[:start] + " " + title[end + 1 :]) if 0 <= start < end else title


def _best_title(company_name: str, ticker: str | None = None) -> str | None:
    """Best relevant title from the top search results.

    Wikipedia's ranking leads: the top hit wins when relevant. Three narrow
    exceptions, all verified against live data (batch 47):
    - Exact-name match: a relevant hit whose squashed form (lowercase
      alphanumeric, stop words retained, parenthetical stripped) equals the
      squashed company name ("Tesla, Inc." for "TESLA INC") wins
      immediately — it is the canonical article. Stop words are retained
      here so "Domino's Pizza Group plc" can't equal "DOMINOS PIZZA INC".
    - Predecessor override: a lower hit with strictly higher name overlap
      that is name-contained and no more verbose replaces the top hit
      ("Lockheed Martin" over "Lockheed Corporation"). The containment +
      brevity requirements are what keep this from promoting subsidiaries
      ("Domino's Pizza Group plc") or museums ("Wells Fargo History
      Museum") above the company page. (Lawsuit articles never reach this
      point — excluded from relevance.)
    - Top hit irrelevant: take the best name-contained relevant lower hit;
      otherwise None.
    Ties keep Wikipedia's ranking (first max wins).

    Fallback (batch 54): when the primary search yields nothing relevant
    (or nothing at all), retry with the corporate suffix stripped from the
    query ("Atlassian Corp company" poisons Wikipedia's ranking while
    "Atlassian company" hits the article). Acceptance is strict — the
    candidate must be an article *named* the stripped company name — so
    merely similar articles are declined, never misattributed.

    Alias retry (batch 58): when the fallback also yields nothing and the
    ticker has a curated entry in _DBA_ALIASES, search the alias and accept
    only the article whose squashed full title equals the squashed alias
    (exact, parenthetical included). This is the escape hatch for
    DBA/nickname companies ("Maplebear Inc." -> Instacart) and spelling
    drift ("STEVEN MADDEN, LTD." -> the "Steve Madden, Ltd." article). The
    exact-match requirement is what keeps SHOO off the founder's "Steve
    Madden" page — a fuzzy relevance path would accept it on first-word
    agreement. Fires last, so the 130 described companies are untouched.
    """
    results = _search_titles(company_name, limit=5)
    if results:
        allowed = _name_word_set(company_name, ticker)
        squashed_name = _squashed(company_name)
        for cand in results:
            if _title_relevant(cand, company_name, ticker) and _squashed(_bare_title(cand)) == squashed_name:
                return cand
        top = results[0]
        if _title_relevant(top, company_name, ticker):
            top_overlap = _relevance_overlap(top, company_name, ticker)
            top_len = len(set(_normalize_words(top)))
            for cand in results[1:]:
                if not _title_relevant(cand, company_name, ticker):
                    continue
                cand_words = set(_normalize_words(cand))
                if (
                    _relevance_overlap(cand, company_name, ticker) > top_overlap
                    and cand_words <= allowed
                    and len(cand_words) <= top_len
                ):
                    return cand
            return top
        best: str | None = None
        best_score = 0
        for cand in results[1:]:
            if not _title_relevant(cand, company_name, ticker):
                continue
            if not set(_normalize_words(cand)) <= allowed:
                continue
            score = _relevance_overlap(cand, company_name, ticker)
            if score > best_score:
                best, best_score = cand, score
        if best is not None:
            return best
    # Fallback (batch 54): the full legal name can poison Wikipedia's
    # ranking ("Atlassian Corp company" -> junk). Retry with the corporate
    # suffix stripped. Acceptance is strict on purpose — the candidate must
    # be an article *named* the stripped company name (word-set equality,
    # suffix-stripped on both sides), so a merely similar article like
    # "Applied Digital Data Systems" for "Applied Digital Corp." is
    # declined rather than misattributed (batch-47 IBM/Commodore class).
    stripped = _strip_corp_suffix(company_name)
    if stripped and stripped != company_name:
        for cand in _search_titles(stripped, limit=5):
            if _strict_title_match(cand, stripped):
                return cand
    # Alias retry (batch 58): last resort, exact title match only. The map
    # is keyed by ticker so no recursion guard is needed — this is a flat
    # search of the alias, not a re-entry into _best_title.
    if ticker:
        alias = _DBA_ALIASES.get(ticker.strip().upper())
        if alias and alias != company_name:
            squashed_alias = _squashed(alias)
            for cand in _search_titles(alias, limit=5):
                if _never_relevant(cand):
                    continue
                if _squashed(cand) == squashed_alias:
                    return cand
    return None


def _strip_corp_suffix(name: str) -> str:
    """Strip a trailing SEC state tag ("/MA/") and one corporate suffix token.

    "AMERICAN TOWER CORP /MA/" -> "AMERICAN TOWER"; "3M CO" -> "3M".
    Never returns an empty string.
    """
    n = re.sub(r"\s*/[A-Z]{2}/?\s*$", "", name).strip()
    n = re.sub(r"[\s,&]+$", "", n)
    toks = n.split()
    if len(toks) > 1 and toks[-1].rstrip(".,").lower() in _CORP_SUFFIXES:
        n = re.sub(r"[\s,&]+$", "", " ".join(toks[:-1]))
    return n or name


def _word_set(text: str) -> set[str]:
    """Word set for strict title comparison — keeps short words.

    Unlike _normalize_words (which drops <=2-char tokens for relevance
    scoring), "3M" and "D. R." must survive here for exact-name matching.
    """
    words: set[str] = set()
    for chunk in _bare_title(text).replace("-", " ").split():
        w = chunk.lower().replace("'", "").replace("’", "").strip(".,;:!?\"()&")
        if w and w not in _STOP_WORDS:
            words.add(w)
    return words


def _never_relevant(title: str) -> bool:
    """Titles that can never name the company, regardless of overlap."""
    lowered = title.lower()
    if " v. " in lowered or " vs. " in lowered or " vs " in lowered:
        return True
    if lowered.startswith("list of "):
        return True
    paren = _paren_content(title)
    return paren is not None and paren != "company"


def _strict_title_match(title: str, stripped_name: str) -> bool:
    """True when the article is *named* the suffix-stripped company name.

    Word-set equality (order-insensitive, suffix-stripped on both sides)
    with the never-relevant exclusions. "Atlassian" matches "Atlassian";
    "D. R. Horton" matches "HORTON D R"; "Applied Digital Data Systems"
    does NOT match "Applied Digital".
    """
    if _never_relevant(title):
        return False
    return _word_set(_strip_corp_suffix(title)) == _word_set(stripped_name)


def _normalize_words(text: str) -> list[str]:
    """Significant words, normalized for company-name/title comparison.

    Hyphens split into words ("Kimberly-Clark" -> kimberly, clark),
    apostrophes and punctuation are stripped ("Domino's" -> dominos), so
    SEC-style names ("COCA COLA CO", "DOMINOS PIZZA INC") match their
    Wikipedia titles ("The Coca-Cola Company", "Domino's").
    """
    words: list[str] = []
    for chunk in text.replace("-", " ").split():
        # Interior apostrophes ("Domino's" -> dominos) as well as edge punctuation
        w = chunk.lower().replace("'", "").replace("’", "").strip(".,;:!?\"()")
        if w and w not in _STOP_WORDS and len(w) > 2:
            words.append(w)
    return words


def _paren_content(title: str) -> str | None:
    """Text inside the title's parenthetical, if any."""
    start, end = title.find("("), title.rfind(")")
    if 0 <= start < end:
        return title[start + 1 : end].strip().lower()
    return None


def _title_relevant(title: str, company_name: str, ticker: str | None = None) -> bool:
    """Return True if the Wikipedia title plausibly names the company.

    Never relevant:
    - Lawsuit articles ("United States v. Microsoft Corp.") — the " v. "
      citation convention never names the company article.
    - List articles ("List of mergers and acquisitions by Microsoft") —
      the "List of " prefix marks a Wikipedia list, never the company.
    - Parenthetical-disambiguated pages other than "(company)":
      "William Procter (industrialist)" and "Procter & Gamble (P&G)
      Pakistan" are not the company; "Amazon (company)" is (bare "Amazon"
      is the river/mythology).

    Otherwise, three rules in order:
    1. Acronym pages: the article is literally the ticker ("AMD", "BNY").
    2. First-word agreement between the SEC name and the title.
    3. Fallback: the SEC name's lead word appears anywhere in the title —
       covers "John Deere" for "DEERE & CO", "The Coca-Cola Company" for
       "COCA COLA CO", "Domino's" for "DOMINOS PIZZA INC", and
       "Kimberly-Clark" for "KIMBERLY CLARK CORP".
    """
    if _never_relevant(title):
        return False
    if ticker and title.strip().lower() == ticker.strip().lower():
        return True
    title_words = _normalize_words(title)
    name_words = _normalize_words(company_name)
    if not name_words or not title_words:
        return False
    if title_words[0] == name_words[0]:
        return True
    if name_words[0] in title_words:
        return True
    return False


def _search_titles(query: str, limit: int = 5) -> list[str]:
    """Return up to ``limit`` Wikipedia search-result titles, [] on error.

    Callers treat [] identically to no results — no distinction is enforced
    upstream."""
    try:
        resp = httpx.get(
            _SEARCH,
            params={
                "action": "query",
                "list": "search",
                "srsearch": f"{query} company",
                "format": "json",
                "srlimit": limit,
            },
            timeout=10,
            headers={"User-Agent": "Tickerlens/1.0 (personal research tool)"},
        )
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        return [r["title"] for r in results if r.get("title")]
    # NOTE: httpx.InvalidURL is NOT an HTTPError subclass (inherits directly
    # from Exception); it can be raised from broken proxy/env config before
    # any request is made. Treat it as a network failure, per this module's
    # None-on-error contract.
    except (httpx.HTTPError, httpx.InvalidURL, OSError):
        logger.warning("Wikipedia search failed for %r", query, exc_info=True)
        return []


def _search_title(query: str) -> str | None:
    """Return the top Wikipedia search-result title, None when absent/error."""
    titles = _search_titles(query, limit=1)
    return titles[0] if titles else None


def _fetch_extract(title: str) -> str | None:
    try:
        resp = httpx.get(
            _API.format(title=title),
            timeout=10,
            headers={"User-Agent": "Tickerlens/1.0 (personal research tool)"},
        )
        resp.raise_for_status()
        data = resp.json()
        # Disambiguation pages ("O", "T") carry short extracts that would
        # otherwise pass the stub floor — reject by type, not by length.
        if data.get("type") == "disambiguation":
            return None
        extract: str = data.get("extract", "") or ""
        if len(extract.split()) < _MIN_WORDS:
            return None
        return extract[:_MAX_CHARS]
    # NOTE: httpx.InvalidURL is NOT an HTTPError subclass (inherits directly
    # from Exception); it can be raised from broken proxy/env config before
    # any request is made. Treat it as a network failure, per this module's
    # None-on-error contract.
    except (httpx.HTTPError, httpx.InvalidURL, OSError):
        logger.warning("Wikipedia extract failed for %r", title, exc_info=True)
        return None
