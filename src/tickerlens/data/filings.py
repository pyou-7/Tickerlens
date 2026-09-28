"""
Filing-text extraction.

The SEC `companyfacts` API gives us structured XBRL numbers but no narrative
text. Item 1A "Risk Factors" lives only in the primary 10-K/10-Q HTML document,
so this module locates the latest annual filing and best-effort extracts that
section as plain text.

Parsing raw filing HTML is inherently fragile (formatting varies widely across
filers), so every function degrades gracefully: on any doubt it returns None and
the caller shows "Not available for this period".
"""

from __future__ import annotations

import html as _html
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from tickerlens.data.edgar import normalize_cik

logger = logging.getLogger(__name__)


@dataclass
class AnnualFiling:
    accession: str        # "0000320193-24-000123"
    primary_doc: str      # "aapl-20240928.htm"
    filing_date: date


# The real Item 1A section is bounded below by the next item heading. Different
# filers jump to 1B (Unresolved Staff Comments) or straight to 2 (Properties);
# some recent filings also use "1C" (Cybersecurity).
_RISK_START_RE = re.compile(r"item\s*1a\.?\s*[:.\-–]*\s*risk\s+factors", re.IGNORECASE)
_RISK_END_RE = re.compile(
    r"item\s*1b\.?\s*[:.\-–]*\s*unresolved"
    r"|item\s*1c\.?\s*[:.\-–]*\s*cybersecurity"
    r"|item\s*2\.?\s*[:.\-–]*\s*properties",
    re.IGNORECASE,
)

# Below this length (roughly a paragraph of real prose) the match is almost
# certainly a table-of-contents entry, not the real section — treat as "not
# found" rather than surface a stub. Real Item 1A sections run many KB.
_MIN_SECTION_CHARS = 500

# Below this length the document is almost certainly not a real press release
# (an error page, a bare 8-K shell, or a stub) — treat as "not found".
_MIN_RELEASE_CHARS = 800

# Headline candidates longer than this are usually run-on body text, not a title.
_MAX_HEADLINE_CHARS = 220

# Lines that mark the start of boilerplate we never want in highlights.
_BOILERPLATE_RE = re.compile(
    r"^(about\s|forward-looking|safe harbor|contacts?(\s|:)|press\s+contacts?|"
    r"investor\s+contacts?|note to editors|###)",
    re.IGNORECASE,
)

# Release-admin lines that precede the real headline in many exhibits.
_ADMIN_LINE_RE = re.compile(
    r"^(for immediate release|news release|press release)\b", re.IGNORECASE
)

# An explicit "Highlights" / "Financial Highlights" section heading.
_HIGHLIGHTS_HEADING_RE = re.compile(r"\bhighlights?\b", re.IGNORECASE)


def latest_annual_filing(submissions: dict[str, Any]) -> AnnualFiling | None:
    """Return the most recently filed 10-K from an SEC submissions payload."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    filing_dates = recent.get("filingDate", [])

    best: AnnualFiling | None = None
    for i, form in enumerate(forms):
        if form != "10-K":
            continue
        doc = primary_docs[i] if i < len(primary_docs) else ""
        if not doc:
            continue
        try:
            filed = date.fromisoformat(filing_dates[i])
        except (ValueError, IndexError):
            continue
        if best is None or filed > best.filing_date:
            best = AnnualFiling(accession=accessions[i], primary_doc=doc, filing_date=filed)
    return best


def filing_doc_url(cik: str | int, filing: AnnualFiling) -> str:
    """Full EDGAR URL for a filing's primary HTML document."""
    cik_num = str(int(normalize_cik(cik)))
    acc_clean = filing.accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/{filing.primary_doc}"


def extract_risk_factors(document_html: str, max_chars: int = 8000) -> str | None:
    """Best-effort extract the Item 1A Risk Factors section as plain text.

    Returns None when the section can't be confidently located. When multiple
    "Item 1A ... Risk Factors" markers exist (a table-of-contents link plus the
    real heading), the longest resulting section wins — the TOC entry yields only
    a few words before the next item marker, the real section yields pages.
    """
    text = _html_to_text(document_html)

    best_section: str | None = None
    for match in _RISK_START_RE.finditer(text):
        start = match.end()
        end_match = _RISK_END_RE.search(text, start)
        end = end_match.start() if end_match else len(text)
        section = text[start:end].strip(" .:-–")
        if best_section is None or len(section) > len(best_section):
            best_section = section

    if best_section is None or len(best_section) < _MIN_SECTION_CHARS:
        logger.info("Risk Factors section not confidently located in filing")
        return None

    if len(best_section) > max_chars:
        best_section = best_section[:max_chars].rsplit(" ", 1)[0].rstrip() + "…"
    return best_section


def extract_press_release_highlights(
    document_html: str, max_chars: int = 4000
) -> str | None:
    """Best-effort extract headline + key highlights from an earnings-release exhibit.

    Strategy: the release headline (first substantial line) plus an explicit
    "Highlights" section when one exists; otherwise the opening paragraphs (the
    lede, which in earnings releases summarizes the quarter's results).
    Boilerplate — "About …", forward-looking statements, contacts — is excluded.

    Returns None when the document doesn't look like a usable release. Like
    extract_risk_factors, this degrades gracefully: on any doubt it returns None
    and the caller shows "Not available for this period".
    """
    text = _html_to_text(document_html)
    if len(text) < _MIN_RELEASE_CHARS:
        logger.info("Press release too short to be usable (%d chars)", len(text))
        return None

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not lines:
        return None

    headline: str | None = None
    body_start = 0
    for i, ln in enumerate(lines):
        if _ADMIN_LINE_RE.match(ln):
            continue
        if len(ln) <= _MAX_HEADLINE_CHARS:
            headline = ln
            body_start = i + 1
        break

    body_lines = lines[body_start:]

    section = _extract_highlights_section(body_lines)
    if section is not None:
        body = "\n".join(section)
    else:
        # Fallback: the lede — opening paragraphs before boilerplate begins.
        lede: list[str] = []
        for ln in body_lines:
            if _BOILERPLATE_RE.match(ln):
                break
            lede.append(ln)
            if len(lede) >= 6:
                break
        body = "\n\n".join(lede)

    result = f"{headline}\n\n{body}".strip() if headline else body.strip()
    if len(result) < 200:
        logger.info("Press-release highlights too short after extraction")
        return None
    if len(result) > max_chars:
        result = result[:max_chars].rsplit(" ", 1)[0].rstrip() + "…"
    return result


def _extract_highlights_section(lines: list[str]) -> list[str] | None:
    """Return the content lines of an explicit "Highlights" section, or None.

    Collects lines after a highlights heading until boilerplate or what looks
    like the next section heading (a short ALL-CAPS line). Requires a minimum
    amount of content — a heading with nothing under it falls back to the lede.
    """
    for i, ln in enumerate(lines):
        if not _HIGHLIGHTS_HEADING_RE.search(ln) or len(ln) > 120:
            continue
        collected: list[str] = []
        for follow in lines[i + 1:]:
            if _BOILERPLATE_RE.match(follow):
                break
            if follow.isupper() and len(follow) <= 80:
                break
            collected.append(follow)
            if len(collected) >= 12:
                break
        if len("\n".join(collected)) >= 150:
            return collected
        return None  # heading found but section too thin — don't try later headings
    return None


def _html_to_text(document_html: str) -> str:
    """Strip HTML to plain text, preserving block boundaries as line breaks.

    Script/style content is dropped; `<br>` and common block-close tags become
    newlines so risk-factor paragraphs stay readable instead of collapsing into
    one wall of text.
    """
    text = re.sub(r"(?is)<head\b.*?</head>", " ", document_html)
    text = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)          # collapse runs of spaces
    text = re.sub(r" *\n *", "\n", text)          # trim spaces around newlines
    text = re.sub(r"\n{3,}", "\n\n", text)        # cap blank-line runs
    return text.strip()
