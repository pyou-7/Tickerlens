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
# The separator class covers the heading punctuation filers use between "1A"
# and "Risk Factors": Dell renders "ITEM 1A — RISK FACTORS" (em dash).
_RISK_START_RE = re.compile(
    r"item\s*1a\.?\s*[:.\-–—]*\s*risk\s+factors"
    # Legacy parenthesized numbering, matched as a full heading line only:
    # horizontal whitespace (never newlines), so the TOC's split "Item 1(a)."
    # / "Risk Factors" lines and mid-sentence cross-references ("see Part I,
    # Item 1(a). Risk Factors") cannot match. (Halliburton, ICE.)
    r"|^[ \t]*item[ \t]*1[ \t]*\([ \t]*a[ \t]*\)\.?[ \t]*[:.\-–—]*[ \t]*risk[ \t]+factors[ \t]*\.?[ \t]*$"
    # Dotted numbering, also full-line only for the same reason (Clorox's
    # 10-K heads the section "ITEM 1.A. RISK FACTORS" as a standalone line;
    # an inline match could catch a mid-sentence "see Item 1.A. Risk Factors"
    # cross-reference and steal longest-section-wins).
    r"|^[ \t]*item[ \t]*1[ \t]*\.[ \t]*a[ \t]*\.?[ \t]*[:.\-–—]*[ \t]*risk[ \t]+factors[ \t]*\.?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_RISK_END_RE = re.compile(
    r"item\s*1b\.?\s*[:.\-–]*\s*unresolved"
    r"|item\s*1\s*\.\s*b\.?\s*[:.\-–]*\s*unresolved"
    r"|item\s*1\s*\(\s*b\s*\)\.?\s*[:.\-–]*\s*unresolved"
    r"|item\s*1c\.?\s*[:.\-–]*\s*cybersecurity"
    r"|item\s*1\s*\.\s*c\.?\s*[:.\-–]*\s*cybersecurity"
    r"|item\s*2\.?\s*[:.\-–]*\s*properties"
    r"|item\s*2\s*\.\s*[:.\-–]*\s*properties",
    re.IGNORECASE,
)

# Below this length (roughly a paragraph of real prose) the match is almost
# certainly a table-of-contents entry, not the real section — treat as "not
# found" rather than surface a stub. Real Item 1A sections run many KB.
_MIN_SECTION_CHARS = 500

# Primary "Item 1A ... Risk Factors" matches shorter than this are TOC stubs
# (a page number before the next item marker). When no primary candidate even
# reaches this length, the heading wasn't found in Item-1A form and the bare
# all-caps "RISK FACTORS" fallback may apply; a longer-but-subfloor section
# means the real heading matched and holds only a cross-reference
# (incorporation by reference — honestly None, never second-guessed).
_MIN_TOC_STUB_CHARS = 50

# Bare all-caps section heading used by filers with no "Item 1A" prefix
# (McDonald's, Citi). Matched as a standalone line only.
_RISK_CAPS_LINE_RE = re.compile(r"^RISK FACTORS$", re.MULTILINE)

# Bare title-case standalone heading, same no-prefix situation (Intel,
# Morgan Stanley). Matched as a standalone line only; the prose-follow check
# in extract_risk_factors excludes TOC entries and running page headers.
_RISK_TITLE_LINE_RE = re.compile(r"^Risk Factors$", re.MULTILINE)

# Run-in heading: "RISK FACTORS." directly followed by prose on the same line
# (GE Aerospace: "RISK FACTORS. The following discussion of the material
# factors..."). The uppercase lookahead keeps table fragments out.
_RISK_RUNIN_RE = re.compile(r"^[ \t]*RISK FACTORS[.:][ \t]+(?=[A-Z])", re.MULTILINE)

# A standalone heading-line candidate is only viable when the next non-blank
# line looks like body prose. TOC entries and running page headers are
# followed by page numbers or item labels ("37", "1A 13") — short fragments,
# never prose. A real section heading is followed by its opening paragraph.
_PROSE_FOLLOW_MIN_CHARS = 20


def _followed_by_prose(text: str, pos: int) -> bool:
    for line in text[pos:].splitlines():
        stripped = line.strip()
        if stripped:
            return len(stripped) >= _PROSE_FOLLOW_MIN_CHARS
    return False

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

# Release-admin lines that precede the real headline in many exhibits:
# "For Immediate Release" banners plus the SEC exhibit headers EDGAR renders
# at the top of ex-99 docs (EX-99.1 labels, page numbers, exhibit filenames).
_ADMIN_LINE_RE = re.compile(
    r"^(for immediate release|news release|press release)\b"
    r"|^ex-?99\.1\b"  # EX-99.1
    r"|^exhibit\s+99\b"  # Exhibit 99.1
    r"|^\d{1,3}$"  # page numbers
    r"|^\S+\.html?$"  # exhibit filename lines
    r"|^\(furnished herewith\)$",  # SEC exhibit parenthetical (Deere-style)
    re.IGNORECASE,
)

# An explicit "Highlights" / "Financial Highlights" section heading.
_HIGHLIGHTS_HEADING_RE = re.compile(r"\bhighlights?\b", re.IGNORECASE)

# Contact lines (media/investor contacts + email addresses) that some filers
# (e.g. JNJ, Deere) place *before* the release headline. They are neither headline nor
# lede content: skipping them keeps "Media contact:" / "Media Inquiries:" from
# becoming the headline and keeps a leading "Investor contact:" from terminating
# the lede fallback before any real content is collected.
_CONTACT_LINE_RE = re.compile(
    r"(media|press|investor)[\s\-–]*(contacts?|inquiries?)|[\w.\-+]+@[\w.\-]+\.\w+",
    re.IGNORECASE,
)

# A bare "Contact:" / "Contacts:" header starts a contact *block* whose detail
# lines follow on their own lines (CHD, Oracle style):
#   Contact:
#   Lee McChesney
#   Chief Financial Officer
#   609-806-1200
# Matched separately from _CONTACT_LINE_RE because the block's detail lines are
# not emails / media-labeled lines, and because here we want to *skip* the whole
# block (see _skip_contact_block), whereas the boilerplate regex below uses
# "contacts?(\s|:)" to *terminate* the lede when a contacts section appears at
# the end of a release.
_CONTACT_HEADER_RE = re.compile(r"^contacts?\s*:", re.IGNORECASE)

# Phone numbers inside contact blocks (609-806-1200, 1.650.607.0349, ...).
_PHONE_RE = re.compile(r"\+?\d[\d.\-\s()]{7,}\d")

# Company-name masthead lines some filers (CHD) place before the release
# headline: "Church & Dwight Co., Inc.". Skipping them in the headline pass
# keeps the company name from becoming the headline. Anchored at line end and
# length-guarded at the call site so a real headline that happens to mention a
# company is never swallowed.
_COMPANY_NAME_LINE_RE = re.compile(
    r",?\s*\b(Inc\.?|Incorporated|Corporation|Corp\.?|Co\.?|Company|Ltd\.?|Limited|"
    r"LLC|PLC|Holdings|Group)\s*\.?$",
    re.IGNORECASE,
)


def _skip_contact_block(lines: list[str], i: int) -> int:
    """Return the index of the first line after the contact block whose header
    is at index *i*.

    Contact detail lines are emails, phone numbers, or short fragments (names,
    titles, departments — "Lee McChesney", "Chief Financial Officer", "Oracle
    Investor Relations"). The block ends at the first line that looks like real
    content: 4+ words, 40+ characters, or an all-caps line of 15+ characters
    (the usual shapes of a release headline). Bounded at 8 detail lines so a
    misfired header can never swallow the release body.
    """
    j = i + 1
    while j < len(lines) and j - i <= 8:
        ln = lines[j]
        words = ln.split()
        looks_like_content = (
            len(words) >= 4
            or len(ln) >= 40
            or (len(ln) >= 15 and ln.upper() == ln and any(c.isalpha() for c in ln))
        )
        if looks_like_content and not _PHONE_RE.search(ln):
            break
        j += 1
    return j

# A "TABLE OF CONTENTS" heading opens a combined release+supplement packet
# (SPG): cover lines, then section-title / page-number pairs, then the real
# release narrative. TOCs are skipped so the heading and its entries never
# become the headline or the lede.
_TOC_HEADING_RE = re.compile(r"^table of contents:?$", re.IGNORECASE)

# Page-number lines inside a TOC: "12", "2–11" (en dash), "30-38".
_TOC_PAGE_RE = re.compile(r"^\d{1,3}\s*[–-]\s*\d{1,3}$|^\d{1,3}$")

# TOC titles are section-name fragments; the (title*, page-number) pairing does
# the real discrimination, so this bound only needs to exclude genuine prose.
_TOC_TITLE_MAX_CHARS = 140


def _skip_toc(lines: list[str], i: int) -> int:
    """Return the index of the first narrative line after a table of contents.

    *lines[i]* matches _TOC_HEADING_RE. Consumes (title*, page-number)+ runs —
    SPG's packet lists section titles with page numbers ("Earnings
    Release(1)" / "2–11", "Overview" / "12", ...); multiple titles may share
    one page number. Stops at the first narrative marker (contacts block,
    release banner) or at a line that is neither a title nor a page number.

    After the runs, a trailing run of title-shaped lines is consumed only when
    a narrative marker appears within the next few lines — this handles the
    packet's mini-TOC ("TABLE OF CONTENTS" / "EARNINGS RELEASE" / "Contacts:")
    without swallowing a real headline that directly follows the TOC.

    Requires at least 2 page-number lines: a stray "table of contents" mention
    in a normal release must never trigger the skip. Returns *i* unchanged when
    the lines don't look like a TOC.
    """
    j = i + 1
    pages = 0
    while j < len(lines):
        ln = lines[j]
        if _TOC_PAGE_RE.match(ln):
            pages += 1
            j += 1
            continue
        if (
            _CONTACT_HEADER_RE.match(ln)
            or _CONTACT_LINE_RE.search(ln)
            or _ADMIN_LINE_RE.match(ln)
        ):
            break  # narrative starts here — the headline pass handles it
        if len(ln) <= _TOC_TITLE_MAX_CHARS:
            j += 1
            continue
        break
    if pages < 2:
        return i
    # Trailing mini-TOC: only skip ahead when a narrative marker is close.
    k = j
    while k < len(lines) and k - j <= 4:
        ln = lines[k]
        if (
            _CONTACT_HEADER_RE.match(ln)
            or _CONTACT_LINE_RE.search(ln)
            or _ADMIN_LINE_RE.match(ln)
        ):
            return k
        if _TOC_PAGE_RE.match(ln) or len(ln) <= _TOC_TITLE_MAX_CHARS:
            k += 1
            continue
        break
    return j

# Headline continuations: some filers (SPG) wrap the release headline across
# two lines, breaking after a conjunction or preposition ("...Results and" /
# "Increases Guidance ..."). Joining the next line recovers the full headline.
_HEADLINE_WRAP_TAIL_RE = re.compile(
    r"\b(and|or|of|for|to|with|in|on|at|the|a|an|&|–|—)\s*$", re.IGNORECASE
)

# Lines that can never be a headline continuation: sentence-terminated prose,
# bullets, datelines, quoted or numeric-led lines.
_HEADLINE_CONT_BAD_START_RE = re.compile(r"^[•\-\d\"“]")


def _join_wrapped_headline(lines: list[str], i: int) -> tuple[str, int]:
    """Join a wrapped headline's continuation line; return (headline, next index).

    Only fires when the picked headline ends on a conjunction/preposition and
    the next line is short, fragment-shaped (no terminal sentence punctuation),
    and carries none of the admin/boilerplate/contact markers — so a genuine
    short headline never swallows the lede.
    """
    headline = lines[i]
    j = i + 1
    if (
        _HEADLINE_WRAP_TAIL_RE.search(headline)
        and j < len(lines)
        and len(lines[j]) <= 100
        and not lines[j].rstrip().endswith((".", "!", "?", ":"))
        and not _HEADLINE_CONT_BAD_START_RE.match(lines[j])
        and not _ADMIN_LINE_RE.match(lines[j])
        and not _BOILERPLATE_RE.match(lines[j])
        and not _CONTACT_HEADER_RE.match(lines[j])
        and not _CONTACT_LINE_RE.search(lines[j])
    ):
        return f"{headline} {lines[j]}", j + 1
    return headline, i + 1

# Guidance and Outlook section headings in earnings releases
_GUIDANCE_HEADING_RE = re.compile(
    r"^(business\s+outlook|financial\s+guidance|financial\s+outlook|guidance\s+and\s+outlook|"
    # Quarter-prefixed long forms: "Fourth Quarter Fiscal Year 2026 Business
    # Outlook" (AVGO), "Full Year Fiscal 2027 Guidance" / "First Quarter Fiscal
    # 2027 Guidance" (INTU), "Full-year 2026 guidance:" (JNJ). Up to five
    # intervening words (quarter/fiscal/year/digits, hyphen- or space-separated)
    # are allowed between the prefix and the guidance/outlook tail.
    r"(?:first|second|third|fourth|full|q[1-4]|fiscal|\d{4})"
    r"(?:[\s\-]+(?:quarter|fiscal|year|\d{4})){0,5}[\s\-]+(?:business\s+)?(?:guidance|outlook)|"
    # "Forward-Looking Guidance" section intros (INTU).
    r"forward[- ]looking\s+(?:business\s+)?(?:guidance|outlook)|"
    r"cfo\s+outlook(?: commentary)?|outlook\s+summary|guidance\s+summary|outlook|guidance)\b",
    re.IGNORECASE,
)

# Markers where financial statements tables or webcast details begin in an earnings release
_FINANCIAL_TABLE_START_RE = re.compile(
    r"^(condensed\s+consolidated|consolidated\s+statements|unaudited\s+condensed|"
    r"reconciliation\s+of|gaap\s+to\s+non-gaap|non-gaap\s+financial|conference\s+call|webcast|"
    r"earnings\s+webcast|quarterly\s+highlights|product\s+releases)\b",
    re.IGNORECASE,
)

# Executive quote extraction pattern. Two common earnings-release formats:
#   1. "Quote text…" said Jane Doe, Chief Executive Officer.   (quote first)
#   2. Jane Doe, Chairman and CEO, commented: "Quote text…"   (speaker first)
_QUOTE_RE = re.compile(
    r"(?:"
    r"[“\"][^”\"]{40,800}[”\"][^.\n]*?(?:said|commented|noted)[^.\n]*?\."
    r"|"
    r"[A-Z][A-Za-z .,'-]{1,70}?\b(?:said|commented|noted)\b[^:\n]{0,40}:\s*[“\"][^”\"]{40,800}[”\"]"
    r")",
    re.DOTALL,
)


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
    longest_primary = 0
    for match in _RISK_START_RE.finditer(text):
        start = match.end()
        end_match = _RISK_END_RE.search(text, start)
        end = end_match.start() if end_match else len(text)
        section = text[start:end].strip(" .:-–")
        longest_primary = max(longest_primary, len(section))
        if best_section is None or len(section) > len(best_section):
            best_section = section

    if (best_section is None or len(best_section) < _MIN_SECTION_CHARS) and (
        longest_primary < _MIN_TOC_STUB_CHARS
    ):
        # Fallback: filers that head the section with no "Item 1A" prefix.
        # Candidates are bare all-caps lines (McDonald's, Citi), bare
        # title-case lines (Intel, Morgan Stanley), and run-in "RISK FACTORS."
        # headings (GE Aerospace). A standalone-line candidate must be followed
        # by prose — this excludes TOC entries and running page headers, which
        # are followed by page numbers or item labels. The longest resulting
        # section wins, mirroring the primary path: running headers later in
        # the section yield shorter sections than the real heading (Honeywell).
        # The two guards above keep this from second-guessing documents whose
        # real Item 1A heading matched but holds only a cross-reference
        # (BNY/WFC incorporate Item 1A by reference — honestly None).
        viable: list[Any] = [
            m
            for m in list(_RISK_CAPS_LINE_RE.finditer(text))
            + list(_RISK_TITLE_LINE_RE.finditer(text))
            if _followed_by_prose(text, m.end())
        ]
        viable.extend(_RISK_RUNIN_RE.finditer(text))
        for match in viable:
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
    i = 0
    while i < len(lines):
        ln = lines[i]
        if _ADMIN_LINE_RE.match(ln) or _CONTACT_LINE_RE.search(ln):
            i += 1
            continue
        if _CONTACT_HEADER_RE.match(ln):
            # Bare "Contact:" header (CHD, Oracle): skip the header plus its
            # name/title/phone detail lines so the real headline is found.
            i = _skip_contact_block(lines, i)
            continue
        if _TOC_HEADING_RE.match(ln):
            # Combined release+supplement packet (SPG): skip the table of
            # contents so its heading and entries never become the headline.
            j = _skip_toc(lines, i)
            if j > i:
                i = j
                continue
        if len(ln) <= 80 and _COMPANY_NAME_LINE_RE.search(ln):
            i += 1
            continue  # company masthead (CHD) is not the headline
        if len(ln) <= _MAX_HEADLINE_CHARS:
            headline, next_i = _join_wrapped_headline(lines, i)
            body_start = next_i
        break

    body_lines = lines[body_start:]

    section = _extract_highlights_section(body_lines)
    if section is not None:
        body = "\n".join(section)
    else:
        # Fallback: the lede — opening paragraphs before boilerplate begins.
        lede: list[str] = []
        i = 0
        while i < len(body_lines):
            ln = body_lines[i]
            if _ADMIN_LINE_RE.match(ln):
                i += 1
                continue  # stray exhibit headers / page numbers mid-document
            if _CONTACT_LINE_RE.search(ln):
                i += 1
                continue  # contact blocks some filers put before the headline
            if _CONTACT_HEADER_RE.match(ln):
                # Trailing "Contacts:" section: skip the whole block rather
                # than letting its detail lines pollute the lede; the "About"
                # boilerplate below still terminates collection.
                i = _skip_contact_block(body_lines, i)
                continue
            if _BOILERPLATE_RE.match(ln):
                break
            lede.append(ln)
            if len(lede) >= 6:
                break
            i += 1
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
            if _ADMIN_LINE_RE.match(follow):
                continue  # stray exhibit headers / page numbers mid-document
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


def extract_management_guidance(
    document_html: str, max_chars: int = 4000
) -> str | None:
    """Best-effort extract forward-looking management guidance from an earnings release.

    Locates sections headed by "Business Outlook", "Financial Guidance", "Outlook", etc.
    and collects the targets and commentary before condensed statements or boilerplate begin.
    Returns None if no distinct guidance section is found.
    """
    text = _html_to_text(document_html)
    if len(text) < 200:
        return None

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    for i, ln in enumerate(lines):
        if _GUIDANCE_HEADING_RE.match(ln) and len(ln) <= 90:
            collected = [ln]
            for follow in lines[i + 1 :]:
                if _ADMIN_LINE_RE.match(follow):
                    continue
                if _BOILERPLATE_RE.match(follow) or _FINANCIAL_TABLE_START_RE.match(follow):
                    break
                if follow.isupper() and len(follow) <= 80 and not any(
                    w in follow for w in ["GAAP", "RANGE", "GUIDANCE", "OUTLOOK", "REVENUE", "EPS", "NET SALES"]
                ):
                    break
                collected.append(follow)
                if len(collected) >= 30:
                    break

            res = "\n\n".join(collected)
            if len(res) >= 100:
                if len(res) > max_chars:
                    res = res[:max_chars].rsplit(" ", 1)[0].rstrip() + "…"
                return res
    return None


def extract_transcript_excerpts(
    document_html: str, max_chars: int = 4000
) -> str | None:
    """Best-effort extract executive prepared remarks / earnings call quotes.

    In official 8-K earnings releases, the CEO and CFO's prepared remarks are
    quoted verbatim. This extracts those executive quotes and remarks with
    speaker attribution for the earnings call disclosure.
    """
    text = _html_to_text(document_html)
    if len(text) < 200:
        return None

    quote_matches = _QUOTE_RE.findall(text)
    if not quote_matches:
        return None

    formatted = []
    for q in quote_matches[:3]:
        cleaned = " ".join(q.split())
        formatted.append(f"• {cleaned}")

    result = "\n\n".join(formatted)
    if len(result) < 100:
        return None
    if len(result) > max_chars:
        result = result[:max_chars].rsplit(" ", 1)[0].rstrip() + "…"
    return result


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
    # Inline formatting tags carry no whitespace of their own: adjacent inline
    # elements with no whitespace between them render concatenated in a
    # browser. Replacing them with a space corrupts words that filers split
    # across <span>s — DFIN-prepared 10-Ks render "ITEM 1A. RISK FACTORS" as
    # "RIS</span><span>K FACTORS", which the old space-join turned into
    # "RIS K FACTORS" and hid the real Item 1A heading (TOC-only match, so
    # extract_risk_factors returned None for MSFT/GE/MCD/INTC/BRK.B/...).
    text = re.sub(
        r"(?i)</?(?:span|a|b|i|em|strong|u|font|sup|sub|small|big|label|abbr|"
        r"acronym|cite|code|dfn|kbd|samp|var|mark|q|s|strike|tt|wbr)\b[^>]*>",
        "",
        text,
    )
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _html.unescape(text).replace("\xa0", " ")
    # Zero-width / BOM characters are invisible junk that some filers' exhibits
    # sprinkle between blocks (Deere's release pads sections with \u200b
    # lines). Left in, they count as "content" lines and can fill the lede
    # line-cap with invisible text, starving real highlights.
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = re.sub(r"[ \t]+", " ", text)          # collapse runs of spaces
    text = re.sub(r" *\n *", "\n", text)          # trim spaces around newlines
    text = re.sub(r"\n{3,}", "\n\n", text)        # cap blank-line runs
    return text.strip()
