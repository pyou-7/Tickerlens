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
# Batch 110: raised 220 -> 300 — TJX's genuine Q4 FY25 headline runs 243 chars
# ("THE TJX COMPANIES, INC. REPORTS Q4 AND FY25 RESULTS; Q4 COMP STORE SALES
# UP 5%, PRETAX PROFIT MARGIN OF 11.6%,"); at 220 it was unpickable, the
# headline came back None, and the lede fallback (after _drop_table_fragment_runs
# removed the CONTACT: header) filled with contact detail lines. Page-line junk
# runs 1000+ chars, so 300 still excludes it.
_MAX_HEADLINE_CHARS = 300

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
    r"^(for\s+(immediate\s+)?release|news release|press release)\b"
    r"|^ex-?99(\.1)?\b"  # EX-99.1 / bare EX-99 (NextEra renders the exhibit
    # header without ".1" — without this the "EX-99" line became the headline
    # and the real headline was never reached, batch 97)
    r"|^exhibit$"  # bare "EXHIBIT" when the label wraps across lines (WM:
    # "EXHIBIT" / "99.1" on separate lines). Batch 105.
    r"|^\d+\.\d+$"  # bare version fragment from a wrapped exhibit label
    # ("99.1" after "EXHIBIT"). Never headline material. Batch 105.
    r"|^page\s+\d+\s+of\s+\d+$"  # "Page 1 of 24" exhibit headers (MetLife)
    r"|^page\s+\d+$"  # bare "Page 1" headers (GEV's Workiva exhibits, batch 104)
    r"|^-\s*\d+\s*-$"  # dash-wrapped page numbers ("- 1 -", Merck's Donnelley
    # exhibits; batch 106). A real headline is never a page number.
    r"|^-\s*$"  # bare dash (Merck's page footer; batch 106)
    r"|^\d+\s*-$"  # page-number fragment ("1 -" from a "- 1 -" split across
    # lines; Merck's Donnelley exhibits, batch 106)
    r"|^-\s*\d+$"  # page-number fragment ("- 1" from a "- 1 -" split;
    # batch 106)
    r"|^\d{1,3}$"  # page numbers
    r"|^\S+\.html?$"  # exhibit filename lines
    r"|^\(furnished herewith\)$"  # SEC exhibit parenthetical (Deere-style)
    # Release date lines some filers put before the headline ("August 7,
    # 2025" — Lilly): never headline or lede material.
    r"|^(january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"\.?\s+\d{1,2},?\s+\d{4}$"
    # Date + city + ST + ZIP ("July 30, 2026 Minneapolis, MN 55401" or
    # "10/31/2024 Minneapolis, MN 55401" — Xcel Energy heads releases with a
    # street address, then the date/city/ZIP, then the company name). Never
    # headline or lede material. Batch 108.
    r"|^(?:(january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})"
    r"\s+[A-Za-z][A-Za-z\s.,'-]*,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?$"
    r"|^n\s*e\s*w\s*s\s*r\s*e\s*l\s*e\s*a\s*s\s*e\s*$"  # spaced-letter kicker (Humana)
    r"|^p\s*r\s*e\s*s\s*s\s*r\s*e\s*l\s*e\s*a\s*s\s*e\s*$"  # spaced-letter "press release"
    r"|^e\s+a\s+r\s+n\s+i\s+n\s+g\s+s\s+r\s+e\s+l\s+e\s+a\s+s\s+e\s*$"  # spaced-letter
    # "earnings release" document label (Elevance Health heads releases with
    # it; the real headline follows). \s+ (not \s*) so the unspaced
    # "Earnings Release" — a table-of-contents entry title — is not swallowed
    # here. Batch 110.
    r"|^\S+\s+earnings\s+release$"  # ticker/date-prefixed "EARNINGS RELEASE"
    # document label (Amgen: "AMGN-2024.9.30 EARNINGS RELEASE"). A real
    # headline is never "<single-token> Earnings Release". Batch 110.
    r"|^.*\bfor\s+immediate\s+release$"  # name-prefixed "FOR IMMEDIATE RELEASE"
    # (TJX: "Debra McConnell FOR IMMEDIATE RELEASE"). The ^.* prefix lets the
    # end-anchored marker match after a contact name; a real headline never
    # ends with the release marker. Batch 110.
    r"|^exhibit[\s\-]+99(\.1)?\b"  # Exhibit 99.1 / EXHIBIT-99.1 (Air Products
    # uses the dash form; the real headline follows "News Release"). Batch 110.
    r"|^[A-Z][\w.\-]*\s+exhibit[\s\-]+99(\.1)?\s*$"  # ticker-prefixed exhibit
    # marker (T-Mobile: "TMUS EXHIBIT 99.1"). Batch 110.
    r"|^echibit\s+99(\.1)?\b"  # "ECHIBIT 99.1" — the filer's typo for
    # "EXHIBIT 99.1" (Citi Q1 2025 release). Batch 110.
    # Pre-headline company address block (Amgen: street / city,ST ZIP /
    # "Telephone ..." / www.amgen.com between "News Release" and the real
    # headline). Each shape is full-line anchored; a real headline never
    # looks like an address, a phone line, or a bare city+ZIP. Batch 110.
    r"|^[A-Za-z][A-Za-z\s.'-]*,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?$"
    r"|^(telephone|tel\.?|phone)\s*[:\-]?\s*\+?[\d.\-() ]+$"
    r"|^(?:\d{1,6}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"\s+[A-Za-z0-9][A-Za-z0-9\s.'-]{1,39}?\b(drive|dr|street|st|avenue|ave|road|rd|"
    r"boulevard|blvd|lane|ln|way|plaza|parkway|pkwy|court|ct|circle|cir|trail|"
    r"place)\.?$"
    # Lone "News" section kicker: Southern Company's releases put it before
    # the contact block, and once bare "Page 1" is skipped the kicker would
    # become the headline (batch 104). A real headline is never one word.
    r"|^news$"
    # Bare "Release" / "Press" from a "News Release" / "Press Release" kicker
    # split across lines (Merck's Donnelley exhibits: "News" / "Release" on
    # separate lines; batch 106). A real headline is never one word.
    r"|^release$|^press$"
    # Lone comma (Deere's exhibit: a stray "," line before the real headline;
    # batch 106). Never headline material.
    r"|^,\s*$"
    # "News from <Company>" kicker (AEP: "News from AEP" before the real
    # headline). Single-token company name only — a real headline never has
    # this exact shape. Batch 105.
    r"|^news\s+from\s+\S+$"
    # "THE PRESS RELEASE" exhibit label (Bank of America). Batch 105.
    r"|^the\s+press\s+release$"
    # Full street address on one line ("1550 Peachtree Street, N.W. Atlanta,
    # Georgia 30309" — Equifax heads releases with it; at 50 chars it clears
    # the 48-char bound in _looks_like_masthead_residue and became the
    # headline). A headline never starts with a house number and ends with
    # a ZIP. Batch 107.
    r"|^\d{1,6}\s+\S.*\b\d{5}(?:-\d{4})?\s*$",
    re.IGNORECASE,
)

# A highlights line that carries reported financial figures rather than
# business narrative: a dollar amount, a percent, or a financial keyword
# ("revenue", "net income", "per share", "margin", "cash flow", ...).
# Used to rank candidate highlights sections so the financial one wins for
# this financials app (Halliburton's Q2 2026 release puts "Net income of
# $0.64 per diluted share" bullets right after the headline and buries them
# under a later "Selective Technology & Highlights" business section).
_FINANCIAL_LINE_RE = re.compile(
    r"\$[\d,]|\d\s*%|%|\b(?:revenue|net income|net loss|earnings? per share|"
    r"per diluted share|per basic share|per share|operating margin|"
    r"gross margin|adjusted margin|ebitda|cash flow|operating income|"
    r"operating loss|diluted share|dividend|repurchas|buyback)\b",
    re.IGNORECASE,
)

# An explicit "Highlights" / "Financial Highlights" section heading.
# "Highlights" must head the line ("HIGHLIGHTS FOR ...") or close it
# ("Selected Revenue Highlights") — a bare \bhighlights?\b also matched the
# *verb* mid-sentence in footnotes ("...prepared to highlight and facilitate
# ...", batch 97), hijacking the section with footnote prose.
_HIGHLIGHTS_HEADING_RE = re.compile(
    r"^highlights?\b|\bhighlights?\b[\s:–—-]*$", re.IGNORECASE
)

# A "Highlights" section that is really a financial data table (Lilly's
# "Selected Revenue Highlights" product table, Waste Management's "HIGHLIGHTS
# FOR the fourth quarter" EBITDA table): units parentheticals ("(Dollars in
# millions)"), "% Change" column headers, or data rows dense with $ and %.
# Such a section is not narrative highlights — rejecting it lets the lede
# fallback (the real opening bullets) serve instead. Batch 97.
#
# Batch 107: bullet-led lines (•/●/-) are narrative prose, never table rows.
# Amphenol's "Third Quarter 2024 Highlights:" bullets ("Record sales of $4.04
# billion, up 26%...") each carry $ and % — without the bullet guard, four
# such bullets trip the data_rows >= 4 threshold and a genuine narrative
# section is discarded as a table. Real tables (Lilly/WM) have no bullets.
_TABLE_UNITS_RE = re.compile(r"\(\s*(dollars|usd|\$)", re.IGNORECASE)

_BULLET_LEAD_RE = re.compile(r"^[•●\-–—]\s")


def _looks_like_financial_table(lines: list[str]) -> bool:
    """True when a collected "Highlights" section is a data table, not prose."""
    strong = False
    data_rows = 0
    for ln in lines:
        if _TABLE_UNITS_RE.search(ln) or re.search(r"% change", ln, re.IGNORECASE):
            strong = True
        elif not _BULLET_LEAD_RE.match(ln) and "$" in ln and "%" in ln:
            data_rows += 1
    return strong or data_rows >= 4


def _looks_like_table_fragment(ln: str) -> bool:
    """True for financial-table cell fragments MetLife-style exhibits put
    before the narrative bullets ("Earnings", "Per Share", "Net",
    "Income $1.22", "on Equity (ROE)", "3Q 2025").

    Bullets (•) are always content, and substantial lines (>=40 chars) are
    never fragments — only short, cell-shaped lines qualify. Batch 97.
    """
    if len(ln) >= 40 or ln.startswith("•"):
        return False
    if _TABLE_UNITS_RE.match(ln):
        return True
    if "$" in ln or "%" in ln:
        return True
    words = ln.split()
    if len(words) <= 2:
        return True
    if len(words) <= 4 and "(" in ln:
        return True
    return False


# Table footnotes in the lede ("(a) Represents ...", "(1) During the year ...")
# are never narrative highlights. Distinct from _FOOTNOTE_LINE_RE (digits-only,
# used by the shareholder-letter table parser) — exhibits also letter their
# footnotes. Batch 97. Batch 101: no separator is required after the marker —
# EOG's supplement packet letters its endnotes "(B)Production volumes ..."
# with the marker running straight into the text, and the old [\s.] tail let
# that endnote boilerplate fill the lede and get stored as highlights.
_LEDE_FOOTNOTE_RE = re.compile(r"^\([a-z0-9]+\)", re.IGNORECASE)


# Footnote-definition legend lines (GEV's Workiva ex-99 opens with
# "1 Defined as remaining performance obligation (RPO)" /
# "*Non-GAAP Financial Measure" / "Page 1" before the real headline, and the
# numeric one was picked as the headline in batch 103's aftermath). Two
# shapes, both never headline or lede material. Batch 104.
#   - numeric key + definition verb: "1 Defined as ...", "2 Represents ...",
#     "1 Includes ...", "3 Excludes ..." — the verb is the guard that keeps a
#     numeric-opening headline from being swallowed ("2025 outlook raised"
#     can't match: 4-digit year; "1Q26 record quarter" can't match: no space
#     and no verb; "1 billion in buybacks" can't match: no verb).
#   - glyph footnote markers attached to the text: "*Non-GAAP Financial
#     Measure", "†Excludes ...". The marker must sit at line start with the
#     text attached — a spaced "* Foo" or mid-line asterisk is prose
#     punctuation, not a legend (bullet "•" is a different char and is
#     unaffected).
_FOOTNOTE_DEF_RE = re.compile(
    r"^\d{1,3}\s+(defined as|represents|includes|excludes|reflects)\b"
    r"|^[*†‡]\S",
    re.IGNORECASE,
)


def _drop_table_fragment_runs(lines: list[str]) -> list[str]:
    """Drop runs of 3+ consecutive table fragments (see above).

    Used by the lede fallback: a metric table sitting between the headline
    and the narrative bullets (MetLife's "Earnings / Per Share / 3Q 2025 /
    Net / Income $1.22 / ..." block) would otherwise fill the 6-line lede
    budget with cell fragments and starve the real bullets. Shorter runs
    (1-2 lines) are kept — they may be legit mini-headings. Batch 97.

    A short table heading ("Book Value Per Share") directly above 2+
    fragment rows is residue too — it joins the run for the 3+ count, so a
    heading + its last row ("Book Value Per Share" / "1Q26" / "$361.19")
    drops as one run. Batch 100.
    """
    out: list[str] = []
    i = 0
    while i < len(lines):
        j = i
        if (
            _looks_like_table_heading(lines[j])
            and j + 2 < len(lines)
            and _looks_like_table_fragment(lines[j + 1])
            and _looks_like_table_fragment(lines[j + 2])
        ):
            j += 1  # fold the heading into the fragment run
        while j < len(lines) and _looks_like_table_fragment(lines[j]):
            j += 1
        if j - i >= 3:
            i = j
            continue
        out.append(lines[i])
        i += 1
    return out


def _looks_like_table_heading(ln: str) -> bool:
    """True for a short metric-table heading ("Book Value Per Share").

    Longer than a cell fragment but still table residue when it directly
    heads fragment rows. Bullets are always content; sentence-terminated
    lines are narrative; admin/boilerplate/contact markers are never table
    headings. Batch 100.
    """
    if len(ln) >= 40 or ln.startswith("•"):
        return False
    if ln.rstrip().endswith((".", "!", "?", ":")):
        return False
    if (
        _ADMIN_LINE_RE.match(ln)
        or _BOILERPLATE_RE.match(ln)
        or _CONTACT_HEADER_RE.match(ln)
        or _CONTACT_LINE_RE.search(ln)
    ):
        return False
    return len(ln.split()) <= 4
    out: list[str] = []
    i = 0
    while i < len(lines):
        j = i
        while j < len(lines) and _looks_like_table_fragment(lines[j]):
            j += 1
        if j - i >= 3:
            i = j
            continue
        out.append(lines[i])
        i += 1
    return out

# Contact lines (media/investor contacts + email addresses) that some filers
# (e.g. JNJ, Deere) place *before* the release headline. They are neither headline nor
# lede content: skipping them keeps "Media contact:" / "Media Inquiries:" from
# becoming the headline and keeps a leading "Investor contact:" from terminating
# the lede fallback before any real content is collected. Corporate URLs and
# social handles (Chubb's "www.chubb.com" / "@Chubb" masthead lines) are contact
# info too — never headline or lede material.
_CONTACT_LINE_RE = re.compile(
    r"(media|press|investor)[\s\-–]*(contacts?|inquiries?)|[\w.\-+]+@[\w.\-]+\.\w+"
    r"|www\.|@\w",
    re.IGNORECASE,
)

# A bare "Contact:" / "Contacts:" header starts a contact *block* whose detail
# lines follow on their own lines (CHD, Oracle style):
#   Contact:
#   Lee McChesney
#   Chief Financial Officer
#   609-806-1200
# Role-prefixed variants head the same shape of block (Humana's "FOR MORE
# INFORMATION CONTACT:", GCE's "Investor Relations Contact:", Synopsys'
# "INVESTOR CONTACT:" / "EDITORIAL CONTACT:", Hershey's "FINANCIAL CONTACT:",
# RTX's bare "Media Contact" / "Investor Contact" with no colon) — without the
# prefix only the header line was skipped and the name/title/phone detail lines
# polluted the headline and lede.
# Company-prefixed variant (Progressive: "The Progressive Corporation Company
# Contact:") — the company name stands where a role prefix would.
# Matched separately from _CONTACT_LINE_RE because the block's detail lines are
# not emails / media-labeled lines, and because here we want to *skip* the whole
# block (see _skip_contact_block), whereas the boilerplate regex below uses
# "contacts?(\s|:)" to *terminate* the lede when a contacts section appears at
# the end of a release.
_CONTACT_HEADER_RE = re.compile(
    r"^((for more information|investor(\s+relations)?|financial|media|press|editorial)\s+)?"
    r"contacts?\b"
    # Company-prefixed header: "The Progressive Corporation Company Contact:"
    # (batch 105). A real headline never ends with "Company Contact:".
    r"|^.*\bcompany\s+contacts?\b"
    # Bare role labels with no "contact" word (American Airlines: "Corporate
    # Communications" / "Investor Relations"). Full-line anchored so a real
    # headline mentioning investor relations is never swallowed.
    r"|^(investor relations|corporate communications|media relations)$"
    # Date-prefixed header (American Water: "July 29, 2026 Investor Contact:").
    # The date prefix keeps the standard branch from matching.
    r"|^(january|february|march|april|may|june|july|august|september|october|"
    r"november|december)\s+\d{1,2},\s+\d{4}\s+"
    r"((for more information|investor(\s+relations)?|financial|media|press|editorial)\s+)?"
    r"contacts?\b",
    re.IGNORECASE,
)

# Phone numbers inside contact blocks (609-806-1200, 1.650.607.0349, ...).
_PHONE_RE = re.compile(r"\+?\d[\d.\-\s()]{7,}\d")

# Company-name masthead lines some filers (CHD) place before the release
# headline: "Church & Dwight Co., Inc.". Skipping them in the headline pass
# keeps the company name from becoming the headline. Anchored at line end and
# length-guarded at the call site so a real headline that happens to mention a
# company is never swallowed.
#
# Batch 109: an optional ticker parenthetical may follow the suffix
# ("Citigroup Inc. (NYSE: C)" — Citi heads every release with it). It is still
# a masthead name line, not a headline.
_COMPANY_NAME_LINE_RE = re.compile(
    r",?\s*\b(Inc\.?|Incorporated|Corporation|Corp\.?|Co\.?|Company|Ltd\.?|Limited|"
    r"LLC|PLC|Holdings|Group)\s*\.?(\s*\([A-Za-z]+:\s*[A-Za-z.]+\))?\s*$",
    re.IGNORECASE,
)


def _looks_like_masthead_residue(ln: str) -> bool:
    """True for head-office address-block lines that follow a company-name
    masthead (Chubb: "Bärengasse 32", "CH-8001 Zurich", "Switzerland",
    "www.chubb.com", "@Chubb"; Humana: "101 East Main Street",
    "Louisville, KY 40202", "http://www.humana.com").

    A real headline is never shaped like this: residue lines are short
    (<=48 chars) and are a corporate URL/handle, a single word (country), or
    a short digit-bearing line (street / city-postal). The digit rule is
    word-count-guarded (<=4 words) so a digit-bearing headline is never
    swallowed.

    Batch 106: US street addresses with suite designators ("100 First Stamford
    Place, Suite 700" — United Rentals) run to 6 words, so a suite-address
    pattern covers them without relaxing the word-count guard for all
    digit-bearing lines. A real headline never contains a suite designator.
    """
    if len(ln) > 48:
        return False
    if _CONTACT_LINE_RE.search(ln):
        return True
    if _SUITE_ADDRESS_RE.search(ln):
        return True
    words = ln.split()
    if len(words) == 1:
        return True  # country line ("Switzerland")
    if len(words) <= 4 and re.search(
        r"\b(department|dept\.?)\s*$", ln, re.IGNORECASE
    ):
        return True  # department line ("Public Affairs Department" — PACCAR).
        # Batch 109: a department line in the masthead address block is never
        # a headline. End-anchored and word-count-guarded so a real headline
        # mentioning a department is never swallowed; this helper only runs
        # in masthead-skip contexts.
    if len(words) <= 4 and any(c.isdigit() for c in ln):
        return True  # street / city-postal line ("Bärengasse 32")
    return False


# A US street address with a suite/floor designator ("100 First Stamford
# Place, Suite 700"). Never a headline. Batch 106.
_SUITE_ADDRESS_RE = re.compile(
    r"^\d+\s+[\w\s.,'-]{2,30}?\b(suite|ste\.?|apt\.?|apartment|unit|fl\.?|floor)\b",
    re.IGNORECASE,
)


def _skip_masthead_block(lines: list[str], i: int) -> int:
    """Return the index of the first line after a company-masthead address
    block starting at *i*.

    Bounded at 6 residue lines so a misfire can never swallow the release
    body; stops at the first non-residue line, which the headline pass then
    evaluates normally.

    Batch 109: stops at a contact-header line instead of consuming it (PACCAR:
    "PACCAR Inc" / "Public Affairs Department" / address / "Contact:" / name
    / phone / email before the real headline). The contact block is handled by
    the headline pass's contact-header branch, which knows how to skip its
    detail lines; the masthead skip consuming the header stranded the detail
    lines as headline candidates.
    """
    j = i
    while (
        j < len(lines)
        and j - i < 6
        and not _CONTACT_HEADER_RE.match(lines[j])
        and _looks_like_masthead_residue(lines[j])
    ):
        j += 1
    return j


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
            # A contact name/title line can itself look like content ("Paul
            # Trussell Sandra Carreon-John" — two names, four words; Nike,
            # Hershey, Cisco all head their releases this way). It is still
            # contact detail when an unambiguous contact line (email or phone)
            # follows within the next two lines — a real headline is never
            # followed by an email address. Batch 105.
            following = lines[j + 1 : j + 3]
            if not any(
                _CONTACT_LINE_RE.search(f) or _PHONE_RE.search(f) for f in following
            ):
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
    # Batch 109: a trailing semicolon joins too (RSG: "Republic Services,
    # Inc. Reports Fourth Quarter and Full-Year 2024 Results;" / "Provides
    # 2025 Full-Year Financial Guidance"). A complete headline never ends
    # with a semicolon.
    r"(\b(and|or|of|for|to|with|in|on|at|the|a|an)\b|[&–—]|[,;]\s*)\s*$",
    re.IGNORECASE,
)

# A headline that ends with a headline verb ("Freeport Reports",
# "Merck ... Announces") is a company+verb fragment, not a complete headline —
# the real headline continues on the next line ("Second-Quarter 2026 Results").
# Batch 106: without this, the verb-fragment is stored as the headline and the
# period ("Second-Quarter 2026 Results") is lost.
_HEADLINE_VERB_TAIL_RE = re.compile(
    r"\b(reports?|announces?|delivers?|posts?|declares?|names?|elects?)\s*$",
    re.IGNORECASE,
)

# Lines that can never be a headline continuation: sentence-terminated prose,
# bullets, datelines, quoted or numeric-led lines.
_HEADLINE_CONT_BAD_START_RE = re.compile(r"^[•\-\d\"“]")

# A continuation line that opens with a conjunction ("AND FULL YEAR 2024
# RESULTS" after "AMPHENOL REPORTS RECORD FOURTH QUARTER"): the headline was
# wrapped mid-phrase with the conjunction leading the second line, the mirror
# of the wrap-tail case above. Batch 107.
_HEADLINE_CONT_LEAD_RE = re.compile(r"^(and|or|but)\b", re.IGNORECASE)

# A release-date line ("July 30, 2026", "July 30, 2026 Minneapolis, MN
# 55401", or "10/31/2024 Minneapolis, MN 55401"): never headline material.
# Used by the masthead-residue skip to recognize address+date+name masthead
# blocks (Xcel). Batch 108.
_DATE_LINE_RE = re.compile(
    r"^((january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\b",
    re.IGNORECASE,
)

# A headline that ends on a period/ordinal word ("Plug Power Third",
# "Intercontinental Exchange Reports Strong Full", "Kroger Reports Fourth")
# is a wrapped-headline fragment, not a complete headline — the real headline
# continues on the next line ("Quarter 2025 Highlights", "Year 2025 Results").
# A complete release headline never ends on a bare ordinal. Batch 108.
_HEADLINE_ORDINAL_TAIL_RE = re.compile(
    r"\b(first|second|third|fourth|full)\s*$", re.IGNORECASE
)

# A headline ending on "{ordinal} Quarter" / "Full Year" with a bare 4-digit
# year on the next line ("Intercontinental Exchange Reports Second Quarter" /
# "2026"): the year completes the headline. The year is never a lede start,
# so the digit-lead continuation guard is bypassed for this exact shape only.
# Batch 108.
_HEADLINE_QUARTER_TAIL_RE = re.compile(
    r"\b((first|second|third|fourth)\s+quarter|full\s+year)\s*$", re.IGNORECASE
)
_HEADLINE_BARE_YEAR_RE = re.compile(r"^20\d{2}$")


# A page-image exhibit "line" that is really a whole page starting with a run
# of social-media URLs (Ford: "1 https://ford.to/facebook https://x.com/ford
# https://ford.to/linkedin Ford Reports ..."). The URLs are never headline
# material; the headline follows them. Batch 105.
_LEADING_URL_RUN_RE = re.compile(r"^(\d+\s+)?(https?://\S+\s*)+")


# A headline verb opening the line after a company-name line: the name is the
# first half of a wrapped headline ("Genuine Parts Company" / "Reports Fourth
# Quarter ..."), not a masthead. Batch 105.
_HEADLINE_VERB_LEAD_RE = re.compile(
    r"^(reports?|announces?|delivers?|posts?|declares?|names?|elects?|approves?|"
    r"raises?|beats?|tops?|reaffirms?|launches?|completes?|acquires?)\b",
    re.IGNORECASE,
)


def _wrapped_spaced_label_skip(lines: list[str], i: int) -> int:
    """Return how many lines a spaced-letter document label occupies at *i*.

    Elevance Health's Q3 2025 exhibit wraps the kicker across two lines
    ("E A R" / "N I N G S R E L E A S E", with thin spaces). The joined
    no-space form must be a document label and the first fragment short, so
    wrapped prose is never swallowed. Single-line spaced labels are covered
    by _ADMIN_LINE_RE. Batch 110.
    """
    if i + 1 < len(lines) and len(lines[i]) <= 12:
        joined = re.sub(r"\s+", "", lines[i] + lines[i + 1]).lower()
        if joined in ("earningsrelease", "newsrelease", "pressrelease"):
            return 2
    return 0


def _looks_like_headline(ln: str) -> bool:
    """True for a plausible release-headline line (batch 105).

    Used to detect an orphaned logo/name fragment: a 1-2 word line is never
    the headline when the next line is headline-shaped (Dollar General's
    "Dollar" before "General Corporation Reports First Quarter 2026
    Results"). Deliberately narrow: 4+ words, no terminal sentence
    punctuation, none of the admin/contact/boilerplate markers, not a bullet.
    """
    words = ln.split()
    if len(words) < 4 or len(ln) > _MAX_HEADLINE_CHARS:
        return False
    if ln.startswith(("•", "-", "*")):
        return False
    if re.search(r"[.!?]\s*$", ln):
        return False
    if (
        _ADMIN_LINE_RE.match(ln)
        or _BOILERPLATE_RE.match(ln)
        or _CONTACT_HEADER_RE.match(ln)
        or _CONTACT_LINE_RE.search(ln)
    ):
        return False
    return True


def _join_wrapped_headline(lines: list[str], i: int) -> tuple[str, int]:
    """Join a wrapped headline's continuation lines; return (headline, next index).

    Fires in two cases:
    1. The picked headline ends on a conjunction/preposition and the next line
       is short (≤140 chars), fragment-shaped (no terminal sentence
       punctuation), and carries none of the admin/boilerplate/contact
       markers — so a genuine short headline never swallows the lede.
    2. (Batch 106) The picked headline ends with a headline verb ("Freeport
       Reports", "Merck ... Announces"): a company+verb fragment whose
       continuation ("Second-Quarter 2026 Results") sits on the next line.
       The verb tail is a strong fragment signal — a complete headline never
       ends with a bare verb — and the continuation guards (≤140 chars, no
       terminal punctuation, no admin/contact/boilerplate markers) still
       apply, so a genuine "[Company] Reports" short headline followed by a
       lede sentence (which ends with a period) never joins.

    Iterates (max 3 joins) for multi-line headlines: after a verb-fragment
    join, the continuation may itself end on a wrap word ("WM Announces" /
    "Fourth Quarter and" / "Full Year 2025 Results"). Each join re-checks all
    guards, so the iteration cannot run away into the lede.

    3. (Batch 107) The next line opens with a conjunction ("AMPHENOL REPORTS
       RECORD FOURTH QUARTER" / "AND FULL YEAR 2024 RESULTS"): a mid-phrase
       wrap with the conjunction leading the continuation. The conjunction
       lead is as strong a fragment signal as the wrap tail — a complete
       headline is never followed by a conjunction-led fragment — and the
       same continuation guards apply.

    4. (Batch 108) The picked headline ends on a period/ordinal word ("Plug
       Power Third", "Kroger Reports Fourth", "Intercontinental Exchange
       Reports Strong Full"): a wrapped-headline fragment whose continuation
       ("Quarter 2025 Highlights", "Year 2025 Results") sits on the next
       line. A complete headline never ends on a bare ordinal, and the
       continuation guards still apply.

    5. (Batch 108) The picked headline ends on "{ordinal} Quarter" / "Full
       Year" and the next line is a bare 4-digit year ("Intercontinental
       Exchange Reports Second Quarter" / "2026"). The year is never a lede
       start, so the digit-lead guard is bypassed for this exact shape only.
    """
    headline = lines[i]
    j = i + 1
    joins = 0
    while joins < 3 and j < len(lines):
        year_join = bool(
            _HEADLINE_QUARTER_TAIL_RE.search(headline)
            and _HEADLINE_BARE_YEAR_RE.match(lines[j])
        )
        if not (
            _HEADLINE_WRAP_TAIL_RE.search(headline)
            or _HEADLINE_VERB_TAIL_RE.search(headline)
            or _HEADLINE_ORDINAL_TAIL_RE.search(headline)
            or _HEADLINE_CONT_LEAD_RE.match(lines[j])
            or year_join
        ):
            break
        if not (
            len(lines[j]) <= 140
            and not lines[j].rstrip().endswith((".", "!", "?", ":"))
            and (year_join or not _HEADLINE_CONT_BAD_START_RE.match(lines[j]))
            and not _ADMIN_LINE_RE.match(lines[j])
            and not _BOILERPLATE_RE.match(lines[j])
            and not _CONTACT_HEADER_RE.match(lines[j])
            and not _CONTACT_LINE_RE.search(lines[j])
        ):
            break
        headline = f"{headline} {lines[j]}"
        j += 1
        joins += 1
    return headline, j


def _skip_bare_masthead_name(lines: list[str], i: int) -> int | None:
    """Return the index of the real headline after a bare masthead-name block.

    Batch 107: some filers head the release with a bare company name (no
    corporate suffix — Amphenol's "Amphenol") followed by a kicker/address
    block ("News Release" / "World Headquarters" / "358 Hall Avenue" /
    "Wallingford, CT 06492" / "Telephone (203) 265-8900") and only then the
    real headline ("AMPHENOL REPORTS RECORD THIRD QUARTER 2024 RESULTS").
    The name is not the headline when a headline-shaped line follows within
    6 lines past only admin, residue/contact, or short label lines — and at
    least one residue/contact line is seen, so a genuine short headline is
    never skipped.

    Narrowness guards: the candidate must be short (<=3 words), not already
    headline-shaped, free of terminal punctuation, and must not end on a
    wrap tail, headline verb, or period/ordinal word — those are
    _join_wrapped_headline's wrapped-fragment cases ("WM Announces" /
    "Fourth Quarter and" / "Full Year 2025 Results" / "Plug Power Third"),
    not a masthead. Without the ordinal guard, "Plug Power Third" was read
    as a bare masthead name, its continuation "Quarter 2025 Highlights" as
    digit-bearing residue, and "$177 Million in Quarterly Revenue" was
    picked as the headline. Batch 108.
    """
    ln = lines[i]
    words = ln.split()
    if len(words) > 3 or _looks_like_headline(ln):
        return None
    if (
        _HEADLINE_VERB_TAIL_RE.search(ln)
        or _HEADLINE_WRAP_TAIL_RE.search(ln)
        or _HEADLINE_ORDINAL_TAIL_RE.search(ln)
    ):
        return None
    if re.search(r"[.!?;:]\s*$", ln):
        return None
    j = i + 1
    saw_residue = False
    while j < len(lines) and j - i <= 6:
        cand = lines[j]
        if _looks_like_headline(cand):
            return j if saw_residue else None
        if (
            _CONTACT_HEADER_RE.match(cand)
            or _CONTACT_LINE_RE.search(cand)
            or _looks_like_masthead_residue(cand)
        ):
            # Checked before the admin branch: address-block lines that are
            # also admin-skippable (street / city,ST ZIP / telephone — batch
            # 110) must still count as residue, otherwise the saw_residue
            # guard below fails and a bare masthead name is kept as the
            # headline (Amphenol).
            saw_residue = True
            j += 1
            continue
        if _ADMIN_LINE_RE.match(cand):
            j += 1
            continue
        if len(cand.split()) <= 4 and not re.search(r"[.!?]\s*$", cand):
            j += 1  # kicker/label line ("News Release", "World Headquarters")
            continue
        return None
    return None


# --- Cover title-block skip (batch 100) --------------------------------------
#
# Some filers (Goldman Sachs, in both Workiva and Donnelley vintages) open the
# earnings-release exhibit with a cover page: a quarter-period title
# ("Second Quarter 2026", or the wrapped "Full Year and" / "Fourth Quarter
# 2025"), a generic kind line ("Earnings Results"), inline media/investor
# contact lines, the company masthead + address, and a repeated banner line
# ("SECOND QUARTER 2026 EARNINGS RESULTS"). The naive headline pick takes the
# cover title ("Second Quarter 2026") and the lede fills with the contact /
# masthead lines — while the real headline sits after the banner.
#
# The trigger is deliberately narrow: period title + kind line, then a
# "Media/Investor Relations:" contact line carrying a phone number and a
# banner repeating the period words with "earnings results", all within a
# bounded window. Anything else returns None and the caller falls through to
# the standard headline pick with behavior unchanged.

_COVER_PERIOD_RE = re.compile(
    r"^(?:full\s+year(?:\s+and)?\s+)?(?:first|second|third|fourth)\s+quarter\s+\d{4}$",
    re.IGNORECASE,
)
# Wrapped period title: "Full Year and" on its own line, quarter on the next.
_COVER_PERIOD_WRAP_RE = re.compile(r"^full\s+year(?:\s+and)?$", re.IGNORECASE)
_COVER_AND_RE = re.compile(r"^and$", re.IGNORECASE)
_COVER_YEAR_RE = re.compile(r"^20\d{2}$")
_COVER_BARE_QUARTER_RE = re.compile(
    r"^(?:first|second|third|fourth)\s+quarter$", re.IGNORECASE
)


def _match_cover_title(lines: list[str], i: int) -> int | None:
    """Match a cover period title at lines[i]; return its end index, or None.

    Shapes (Goldman Sachs, Workiva and Donnelley vintages):
      "Second Quarter 2026"
      "Full Year and" / "Fourth Quarter 2025"
      "Full Year" / "and" / "Fourth Quarter 2024"
      "Third Quarter" / "2024"
    """
    j = i
    if j < len(lines) and _COVER_PERIOD_WRAP_RE.match(lines[j]):
        j += 1
        # "Full Year" / "and" / "Fourth Quarter 2024" three-line form.
        if j < len(lines) and _COVER_AND_RE.match(lines[j]):
            j += 1
    if j < len(lines) and _COVER_PERIOD_RE.match(lines[j]):
        return j + 1
    if (
        j < len(lines)
        and _COVER_BARE_QUARTER_RE.match(lines[j])
        and j + 1 < len(lines)
        and _COVER_YEAR_RE.match(lines[j + 1])
    ):
        return j + 2
    return None
_COVER_KIND_RE = re.compile(r"^earnings\s+results?$", re.IGNORECASE)
_COVER_CONTACT_RE = re.compile(r"^(media|investor)\s+relations\s*:", re.IGNORECASE)
_COVER_BANNER_RE = re.compile(
    r"(first|second|third|fourth).*quarter.*earnings\s+results", re.IGNORECASE
)
_COVER_SCAN_LINES = 12
_COVER_HEADLINE_MAX_LINES = 4


def _cover_block_headline(lines: list[str], i: int) -> tuple[str, int] | None:
    """Skip a cover title block; return (headline, body_start), or None.

    Returns None when the cover shape is not present at lines[i]. The real
    headline after a cover often wraps mid-phrase ("...Per Common" /
    "Share of $20.98 ..."), which _join_wrapped_headline deliberately does
    not join, so continuation lines are joined here with a section-heading
    stop: a candidate that is itself a table fragment ("Financial Summary")
    is the metric-table heading, not headline. $-/%-bearing fragments are
    never a stop — real headline continuations carry figures ("...$20.98").
    """
    k = _match_cover_title(lines, i)
    if k is None:
        return None
    if k >= len(lines) or not _COVER_KIND_RE.match(lines[k]):
        return None
    contact_at = banner_at = -1
    for j in range(k + 1, min(k + 1 + _COVER_SCAN_LINES, len(lines))):
        if (
            contact_at < 0
            and _COVER_CONTACT_RE.match(lines[j])
            and _PHONE_RE.search(lines[j])
        ):
            contact_at = j
        if contact_at >= 0 and _COVER_BANNER_RE.search(lines[j]):
            banner_at = j
            break
    if contact_at < 0 or banner_at < 0:
        return None
    h = banner_at + 1
    if h >= len(lines):
        return None
    parts = [lines[h]]
    j = h + 1
    while j < len(lines) and len(parts) < _COVER_HEADLINE_MAX_LINES:
        cand = lines[j]
        if (
            len(cand) > 100
            or cand.rstrip().endswith((".", "!", "?", ":"))
            or _HEADLINE_CONT_BAD_START_RE.match(cand)
            or _ADMIN_LINE_RE.match(cand)
            or _BOILERPLATE_RE.match(cand)
            or _CONTACT_HEADER_RE.match(cand)
            or _CONTACT_LINE_RE.search(cand)
        ):
            break
        if (
            _looks_like_table_fragment(cand)
            and "$" not in cand
            and "%" not in cand
        ):
            break
        parts.append(cand)
        j += 1
    return " ".join(parts), j

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

    if _is_shareholder_letter(lines):
        # Shareholder-letter mode (batch 94): metric-table "Highlights"
        # sections (Duolingo/Affirm/Coinbase style) parse as bullets.
        # Falls back to the standard path when no metric table parses, so
        # letters without one keep the pre-existing behavior exactly.
        metric = _extract_shareholder_letter_highlights(lines, max_chars)
        if metric is not None:
            return metric

    headline: str | None = None
    body_start = 0
    i = 0
    while i < len(lines):
        ln = lines[i]
        url_run = _LEADING_URL_RUN_RE.match(ln)
        if url_run:
            # Page-image exhibit (Ford): the "line" is a whole page starting
            # with social links. Strip the URL run; the headline is the text
            # up to the first bullet. Without this the URL run became the
            # headline (batch 105).
            rest = ln[url_run.end():].strip()
            bullet = rest.find("•")
            cand = rest[:bullet].strip() if bullet != -1 else rest
            if cand and len(cand) <= _MAX_HEADLINE_CHARS and _looks_like_headline(cand):
                headline, body_start = cand, i + 1
                break
            i += 1
            continue
        if _CONTACT_HEADER_RE.match(ln):
            # Contact block header (bare "Contact:" as well as role-prefixed
            # "Investor Relations Contact:" / "INVESTOR CONTACT:" / "FOR MORE
            # INFORMATION CONTACT:"): skip the header plus its name/title/phone
            # detail lines so the real headline is found. Checked before the
            # single-line contact skip — a prefixed header matches both, and
            # the block skip is the one that consumes the detail lines.
            i = _skip_contact_block(lines, i)
            continue
        if _ADMIN_LINE_RE.match(ln) or _CONTACT_LINE_RE.search(ln):
            i += 1
            continue
        wrapped_label = _wrapped_spaced_label_skip(lines, i)
        if wrapped_label:
            # Wrapped spaced-letter document label (Elevance Health Q3 2025:
            # "E A R" / "N I N G S R E L E A S E"); the real headline follows.
            # Batch 110.
            i += wrapped_label
            continue
        if _FOOTNOTE_DEF_RE.match(ln):
            # Footnote-definition legend lines (GEV's Workiva exhibit opens
            # with "1 Defined as remaining performance obligation (RPO)" /
            # "*Non-GAAP Financial Measure" before the real headline): never
            # headline material. Batch 104.
            i += 1
            continue
        if _TOC_HEADING_RE.match(ln):
            # Combined release+supplement packet (SPG): skip the table of
            # contents so its heading and entries never become the headline.
            j = _skip_toc(lines, i)
            if j > i:
                i = j
                continue
        if len(ln) <= 80 and _COMPANY_NAME_LINE_RE.search(ln):
            # Company masthead (CHD): skip the name plus a following
            # head-office address block (Chubb, Humana) so a street or
            # city line never becomes the headline. But when the next line
            # opens with a headline verb, the name is the first half of a
            # wrapped headline (Genuine Parts Company: "Genuine Parts Company"
            # / "Reports Fourth Quarter and Full-Year 2025 Results") — join
            # them instead of skipping. Batch 105.
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if _HEADLINE_VERB_LEAD_RE.match(nxt) and len(ln) + 1 + len(nxt) <= _MAX_HEADLINE_CHARS:
                # The joined fragment may itself be wrapped further ("Genuine
                # Parts Company" / "Reports Fourth Quarter and" / "Full-Year
                # 2025 Results"): run it through the wrap joiner instead of
                # stopping, so a dangling wrap tail is never stored. Batch 108.
                joined = f"{ln} {nxt}"
                headline, rel_next = _join_wrapped_headline([joined] + lines[i + 2 :], 0)
                body_start = i + 1 + rel_next
                break
            i = _skip_masthead_block(lines, i + 1)
            continue
        if _looks_like_masthead_residue(ln):
            # Address-block masthead with no company-name line (General
            # Dynamics: "11011 Sunset Hills Road" / "Reston, Virginia 20190
            # News" / "www.gd.com" before the contact block). Skip the
            # residue run only when a contact header/line follows it —
            # otherwise a stray residue-shaped line is left for the normal
            # headline pick. Batch 105.
            # Batch 108: also skip when a release-date line follows (Xcel:
            # "414 Nicollet Mall" / "July 30, 2026 Minneapolis, MN 55401" /
            # "XCEL ENERGY" before the headline) — the address+date+name is
            # a masthead block, not headline material.
            j = i
            while (
                j < len(lines)
                and j - i < 4
                and _looks_like_masthead_residue(lines[j])
                and not _DATE_LINE_RE.match(lines[j])
            ):
                j += 1
            if (
                j > i
                and j < len(lines)
                and (
                    _CONTACT_HEADER_RE.match(lines[j])
                    or _CONTACT_LINE_RE.search(lines[j])
                    or _DATE_LINE_RE.match(lines[j])
                )
            ):
                i = j
                continue
        cover = _cover_block_headline(lines, i)
        if cover is not None:
            # Cover title block (GS): the real headline follows the banner.
            headline, body_start = cover
            break
        if ln.lower() == "earnings release":
            # "Earnings Release" document label (Mastercard, Amgen, Northrop
            # Grumman): the real headline follows, but not necessarily on the
            # next line — Amgen/Northrop put "Exhibit 99.1" / "News Release" /
            # an address block between the label and the headline. Skip the
            # label and let the loop find the headline; don't require the
            # next line to be headline-shaped (batch 105 did, which left the
            # label as the headline for Amgen/Northrop). Skipped here (not in
            # _ADMIN_LINE_RE) because the same words are a TOC entry title
            # elsewhere. A real headline is never the bare words
            # "Earnings Release". Batch 105; generalized batch 110.
            i += 1
            continue
        if (
            i + 1 < len(lines)
            and len(ln.split()) <= 3
            and ln.upper() == ln
            and any(c.isalpha() for c in ln)
            and _looks_like_headline(lines[i + 1])
            and lines[i + 1].upper() == lines[i + 1]
        ):
            # All-caps company-name masthead before an all-caps headline
            # ("XCEL ENERGY" / "SECOND QUARTER 2026 EARNINGS REPORT"): the
            # name is not the headline. Narrow: both lines all-caps, the name
            # is short, the next line is headline-shaped. Batch 108.
            i += 1
            continue
        if len(ln.split()) == 1 and i + 1 < len(lines) and _looks_like_headline(lines[i + 1]):
            # Orphaned logo/name fragment on its own line before the headline
            # (Dollar General's "Dollar" / Plug Power's "Plug" / WM's "WM"):
            # a single-word line is never the headline when a headline-shaped
            # line follows. Join them — the fragment is the start of the
            # headline, not a separate element. Single-word only: a 2-word
            # line may be a contact name (American Water's "Aaron Musgrave"),
            # which the contact-block skip handles. Batch 105.
            nxt = lines[i + 1]
            if len(ln) + 1 + len(nxt) <= _MAX_HEADLINE_CHARS:
                # The joined fragment may itself be wrapped further ("Kroger"
                # / "Reports Third Quarter 2025 Results and" / "Updates" /
                # "Guidance for 2025"): run it through the wrap joiner instead
                # of stopping, so a dangling wrap tail ("...Results and") is
                # never stored. Batch 108.
                joined = f"{ln} {nxt}"
                headline, rel_next = _join_wrapped_headline([joined] + lines[i + 2 :], 0)
                body_start = i + 1 + rel_next
                break
            i += 1
            continue
        masthead_skip = _skip_bare_masthead_name(lines, i)
        if masthead_skip is not None:
            # Bare company-name masthead (Amphenol's "Amphenol") with the
            # real headline a few lines down past the address block.
            # Batch 107.
            i = masthead_skip
            continue
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
        # Table-fragment runs (MetLife's metric table between the headline and
        # the bullets) are dropped first so they can't fill the 6-line lede
        # budget with cell fragments and starve the real bullets (batch 97).
        lede_lines = _drop_table_fragment_runs(body_lines)
        lede: list[str] = []
        i = 0
        while i < len(lede_lines):
            ln = lede_lines[i]
            if _ADMIN_LINE_RE.match(ln):
                i += 1
                continue  # stray exhibit headers / page numbers mid-document
            if _LEDE_FOOTNOTE_RE.match(ln) or _FOOTNOTE_DEF_RE.match(ln):
                i += 1
                continue  # table footnotes ("(a) ...", "(1) ...") and
                # footnote-definition legends ("1 Defined as ...",
                # "*Non-GAAP Financial Measure") are never lede
            if _CONTACT_HEADER_RE.match(ln):
                # Trailing "Contacts:" section (bare or role-prefixed): skip
                # the whole block rather than letting its detail lines pollute
                # the lede; the "About" boilerplate below still terminates
                # collection. Checked before the single-line contact skip —
                # a prefixed header matches both.
                i = _skip_contact_block(lede_lines, i)
                continue
            if _CONTACT_LINE_RE.search(ln):
                i += 1
                continue  # contact blocks some filers put before the headline
            if _BOILERPLATE_RE.match(ln):
                break
            lede.append(ln)
            if len(lede) >= 6:
                break
            i += 1
        body = "\n\n".join(lede)

    # A trailing comma means the headline's continuation was too long to join
    # (URI Q4 2025: 166-char sub-headline). Strip it — a headline never ends
    # with a comma. Batch 106.
    if headline:
        headline = headline.rstrip().removesuffix(",").rstrip()
    result = f"{headline}\n\n{body}".strip() if headline else body.strip()
    if len(result) < 200:
        logger.info("Press-release highlights too short after extraction")
        return None
    if not headline and len(result.split("\n\n")[0]) > 1000:
        # Page-image exhibit (Bank of America slide deck): the "lines" are
        # whole pages with no usable headline. A page-line is not a highlight;
        # return None so the UI shows "Not available" instead of garbage.
        # Batch 105.
        logger.info("Press-release highlights are page-lines without a headline")
        return None
    if len(result) > max_chars:
        result = result[:max_chars].rsplit(" ", 1)[0].rstrip() + "…"
    return result


def _financial_line_count(lines: list[str]) -> int:
    """Count lines carrying reported financial figures (see _FINANCIAL_LINE_RE)."""
    return sum(1 for ln in lines if _FINANCIAL_LINE_RE.search(ln))


def _leading_bullet_block(lines: list[str]) -> list[str] | None:
    """Consecutive bullet lines immediately after the headline.

    Some filers (Halliburton) open the release with the financial bullets
    ("Net income of $0.64 per diluted share ...") before any "Highlights"
    heading, which may later introduce a purely business section. Bullet
    items may wrap across lines ("... free cash flow1 of / approximately
    $582 million."): a non-bullet line following a bullet start is a
    continuation unless it closes the item (terminal punctuation) and the
    next line isn't a new bullet — that's the dateline paragraph starting.
    Returns the block only when substantial — otherwise None.
    """
    bullets: list[str] = []
    in_item = False  # previous line was a bullet start or continuation
    n = len(lines)
    for idx, ln in enumerate(lines):
        if _ADMIN_LINE_RE.match(ln) or _CONTACT_LINE_RE.search(ln):
            continue
        if _BOILERPLATE_RE.match(ln):
            break
        if _HIGHLIGHTS_HEADING_RE.search(ln) and len(ln) <= 120:
            break  # a headed section follows; it competes on its own
        if ln.startswith(("•", "-", "*")):
            bullets.append(ln)
            in_item = True
        elif in_item:
            nxt = lines[idx + 1] if idx + 1 < n else ""
            bullets.append(ln)
            if re.search(r"[.!?;]\s*$", ln) and not nxt.startswith(("•", "-", "*")):
                break  # item closed and prose follows (dateline)
        else:
            break  # first line isn't a bullet — no leading block
        if len(bullets) >= 14:
            break
    if len("\n".join(bullets)) >= 150:
        return bullets
    return None


def _extract_highlights_sections(lines: list[str]) -> list[list[str]]:
    """Return the content lines of every explicit "Highlights" section.

    Previously only the first match was returned; Halliburton's releases
    pair leading financial bullets with a later business "Highlights"
    section, so all candidates are collected and ranked by financial
    density by the caller (batch 102).
    """
    sections: list[list[str]] = []
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
            if _looks_like_financial_table(collected):
                continue  # table, not narrative highlights — try later headings
            sections.append(collected)
            continue
        break  # heading found but section too thin — don't try later headings
    return sections


def _extract_highlights_section(lines: list[str]) -> list[str] | None:
    """Return the content lines of an explicit "Highlights" section, or None.

    Financial priority (batch 102): the leading bullet block right after
    the headline and every "Highlights" section compete; the one densest
    with reported financial figures wins (earlier wins ties). When nothing
    is financial, the earliest candidate is kept — the pre-batch-102
    behavior.
    """
    candidates: list[list[str]] = []
    leading = _leading_bullet_block(lines)
    if leading is not None:
        candidates.append(leading)
    candidates.extend(_extract_highlights_sections(lines))
    if not candidates:
        return None

    def _score(lines: list[str]) -> tuple[int, int]:
        count = _financial_line_count(lines)
        density = count / max(len(lines), 1)
        # A "financial" candidate needs a real signal: at least 2 figure
        # lines and at least 40% of lines financial. Pure narrative gets
        # score 0 and only wins when nothing financial exists.
        return (1, count) if (count >= 2 and density >= 0.4) else (0, 0)

    best = max(candidates, key=_score)
    return best if _score(best)[0] > 0 else candidates[0]


# --- Shareholder-letter extraction mode (batch 94) ---------------------------
#
# Some filers (Duolingo, Affirm, Coinbase) publish quarterly results as a
# shareholder letter rather than a press release. Their "Q# Highlights"
# section is a metric table, not narrative prose: text extraction flattens
# each metric into a label line ("Daily Active Users 47.7M"), a current-
# value line ("58.7M"), and change lines ("23% YoY"). The standard path
# above terminates section collection at the first value line — "58.7M" is
# all-caps, so `follow.isupper()` fires — and the lede fallback then starves
# on the mission-statement cover, yielding None for every quarter.
#
# The metric-table mode renders the table as honest bullet lines:
#   User Metrics
#   - Daily Active Users: 47.7M → 58.7M (23% YoY)
# Gated on shareholder-letter detection so press-release behavior is
# untouched; falls back to the standard path when no metric table parses.

# Only the document head is checked — "dear shareholders" prose later in
# the document must not trigger this.
_SHAREHOLDER_TITLE_LINES = 30

# "Q2 2026"-style quarter labels on the letter's cover, including Duolingo's
# slash form "Q4 / FY 2025". Groups: (quarter number, year).
_QUARTER_LABEL_RE = re.compile(r"\bQ([1-4])\s*(?:/\s*(?:FY\s*)?)?(\d{4})\b")

# Table group headers with two or more quarter columns:
# "User Metrics Q2 2025 Q2 2026", "Financial Metrics Q4 2025 FY 2025".
# Groups: (name, columns string). A single-quarter line
# ("Financial Metrics Q4 2025") is handled by _METRIC_GROUP_SINGLE_RE plus
# the wrapped-header join below — never as a metric label.
_METRIC_GROUP_RE = re.compile(r"^([A-Za-z].*?)\s+((?:(?:Q[1-4]|FY)\s*\d{4}\s*){2,})$")
_METRIC_GROUP_SINGLE_RE = re.compile(r"^([A-Za-z].*?)\s+(Q[1-4]\s+\d{4})$")
_METRIC_BARE_COL_RE = re.compile(r"^(?:Q[1-4]|FY)\s+\d{4}$")

# A metric value line: "58.7M", "$298.5M". Bare page numbers match too, but
# _ADMIN_LINE_RE skips those before this check runs inside the table.
_METRIC_VALUE_RE = re.compile(r"^\$?[\d,]+(\.\d+)? ?[MBK]?$")

# A metric change line: "23% YoY", "at period end 17% YoY", "(26)%",
# "17.8% margin", "20 bps", "(530) bps". Anchored on a leading digit so a
# prose label can never match.
_METRIC_CHANGE_RE = re.compile(r"^(?:at period end )?\(?\d[\d.,]*\)?\s*(?:%|bps)(?=\s|$).*$", re.IGNORECASE)

# Table footnotes ("(1) During the year ended ...") terminate the table.
_FOOTNOTE_LINE_RE = re.compile(r"^\(\d+\)[\s.]")

# All-caps running headers with a quarter + page number ("DUOLINGO Q2 2026 3",
# "DUOLINGO Q4 / FY 2025 3") terminate the metric table.
_RUNNING_HEADER_RE = re.compile(r"^[A-Z][A-Z .,&'/\-]*\s+Q[1-4]\s*(?:/\s*(?:FY\s*)?)?\d{4}\s+\d{1,3}$")


def _is_shareholder_letter(lines: list[str]) -> bool:
    """True when the document head reads as a shareholder-letter cover.

    Duolingo renders its cover title word-per-line ("shareholder" /
    "letter" / "Q2 2026"); other filers use a single "Shareholder Letter"
    line. The exact-line guard on "shareholder" keeps prose mentions like
    "shareholder value" from triggering this.
    """
    for i, ln in enumerate(lines[:_SHAREHOLDER_TITLE_LINES]):
        low = ln.strip().lower()
        if "shareholder letter" in low:
            return True
        if low == "shareholder" and i + 1 < len(lines):
            if lines[i + 1].strip().lower().startswith("letter"):
                return True
    return False


def _shareholder_letter_headline(lines: list[str]) -> str:
    """Synthesize a document-derived headline for a shareholder letter.

    From the cover title lines near the "shareholder"/"letter" title —
    "Shareholder Letter Q2 2026", "Shareholder Letter Q4 2025" (from Duolingo's
    "Q4 / FY 2025" slash form). The proximity window keeps a quarter label
    from the metric table (e.g. the table's prior-year column) from becoming
    the headline; running headers are skipped. Never invents a company name.
    """
    title_idx: int | None = None
    for i, ln in enumerate(lines[:_SHAREHOLDER_TITLE_LINES]):
        low = ln.strip().lower()
        if "shareholder letter" in low or low == "shareholder":
            title_idx = i
            break
    if title_idx is None:
        return "Shareholder Letter"
    for ln in lines[max(0, title_idx - 2) : title_idx + 7]:
        if _RUNNING_HEADER_RE.match(ln):
            continue
        m = _QUARTER_LABEL_RE.search(ln)
        if m:
            return f"Shareholder Letter Q{m.group(1)} {m.group(2)}"
    return "Shareholder Letter"


def _split_label_prior(ln: str) -> tuple[str, str | None]:
    """Split a metric label line into (label, prior-quarter value).

    "Daily Active Users 47.7M" -> ("Daily Active Users", "47.7M");
    "Net Income $44.8M" -> ("Net Income", "$44.8M");
    "Free Cash Flow" -> ("Free Cash Flow", None).
    """
    head, _, tail = ln.rpartition(" ")
    if tail and _METRIC_VALUE_RE.match(tail) and any(c.isalpha() for c in head):
        return head, tail
    return ln, None


def _is_metric_label(ln: str) -> bool:
    """True for a metric-label line inside the highlights table.

    Mixed-case lines (never all-caps running headers) carrying letters that
    are not value, change, group-header, or boilerplate lines. A trailing
    single quarter ("Revenue Q4 2025") is never a label — that shape is a
    (possibly wrapped) group header, handled by the caller.
    """
    return (
        len(ln) <= 90
        and any(c.isalpha() for c in ln)
        and not ln.isupper()
        and not _METRIC_VALUE_RE.match(ln)
        and not _METRIC_CHANGE_RE.match(ln)
        and not _METRIC_GROUP_RE.match(ln)
        and not _METRIC_GROUP_SINGLE_RE.match(ln)
        and not _BOILERPLATE_RE.match(ln)
    )


def _render_metric(
    label: str, prior: str | None, vals: list[str], changes: list[str], yoy: bool
) -> str | None:
    """Render one parsed metric as a bullet line, or None when valueless.

    A label with no values at all (e.g. a stray prose line after the table)
    renders nothing rather than a junk bullet.

    ``yoy`` is True when the group's two columns are the same quarter a year
    apart ("Q2 2025" vs "Q2 2026"): values read as prior → current. Otherwise
    the columns are different periods ("Q4 2025" vs "FY 2025") and values are
    joined with "; " — a "→" would falsely imply a same-period comparison.
    """
    seq = ([prior] if prior else []) + vals
    if not seq and not changes:
        return None
    parts: list[str] = []
    if yoy:
        if seq:
            parts.append(" → ".join(seq) if len(seq) > 1 else seq[0])
        if changes:
            if (
                len(changes) == 2
                and changes[0].rsplit(" ", 1)[-1].lower()
                == changes[1].rsplit(" ", 1)[-1].lower()
            ):
                # "35.9% margin" / "29.6% margin" read as prior → current.
                parts.append(f"{changes[0]} → {changes[1]}")
            else:
                parts.append("; ".join(changes))
    else:
        if seq:
            parts.append("; ".join(seq))
        if changes:
            parts.append("; ".join(changes))
    detail = f"({' '.join(parts)})" if parts else ""
    if detail:
        return f"- {label}: {detail}"
    return f"- {label}"


def _parse_metric_highlights(lines: list[str]) -> list[str] | None:
    """Parse the "Highlights" metric table of a shareholder letter.

    Returns rendered lines (group headers + bullets), or None when fewer
    than two metric entries parse — too thin to trust.

    Group headers carry the column layout ("User Metrics Q4 2024 Q4 2025"):
    when the two columns are the same quarter a year apart the metrics read
    as prior → current; otherwise (Duolingo's "Financial Metrics Q4 2025 /
    FY 2025", sometimes wrapped across two lines) values are joined without
    implying a same-period comparison. Table footnotes ("(1) ...") and
    running headers terminate the table.
    """
    start: int | None = None
    for i, ln in enumerate(lines):
        if _HIGHLIGHTS_HEADING_RE.search(ln) and len(ln) <= 120:
            start = i + 1
            break
    if start is None:
        return None
    out: list[str] = []
    yoy = True  # per-group; each group header sets it before its metrics
    i = start
    while i < len(lines):
        ln = lines[i]
        if _ADMIN_LINE_RE.match(ln):
            i += 1
            continue
        if (
            _BOILERPLATE_RE.match(ln)
            or _RUNNING_HEADER_RE.match(ln)
            or _FOOTNOTE_LINE_RE.match(ln)
        ):
            break
        gm = _METRIC_GROUP_RE.match(ln)
        if gm is None and _METRIC_GROUP_SINGLE_RE.match(ln):
            # Wrapped group header: "Financial Metrics Q4 2025" / "FY 2025".
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if _METRIC_BARE_COL_RE.match(nxt):
                ln = f"{ln} {nxt}"
                gm = _METRIC_GROUP_RE.match(ln)
                i += 1
            else:
                break  # not a group header we understand — table shape ended
        if gm:
            cols = re.findall(r"(Q[1-4]|FY)\s*(\d{4})", gm.group(2))
            yoy = (
                len(cols) == 2
                and cols[0][0] == cols[1][0]
                and int(cols[1][1]) == int(cols[0][1]) + 1
            )
            out.append(gm.group(1).strip())
            i += 1
            continue
        if _is_metric_label(ln):
            label, prior = _split_label_prior(ln)
            vals: list[str] = []
            changes: list[str] = []
            j = i + 1
            while j < len(lines):
                f2 = lines[j]
                if _ADMIN_LINE_RE.match(f2):
                    j += 1
                    continue
                if _METRIC_VALUE_RE.match(f2):
                    vals.append(f2)
                elif _METRIC_CHANGE_RE.match(f2):
                    changes.append(f2)
                else:
                    break
                j += 1
            bullet = _render_metric(label, prior, vals, changes, yoy)
            if bullet is not None:
                out.append(bullet)
            i = j
            continue
        break  # table shape ended
    entries = [ln for ln in out if ln.startswith("- ")]
    return out if len(entries) >= 2 else None


def _extract_shareholder_letter_highlights(lines: list[str], max_chars: int) -> str | None:
    """Shareholder-letter extraction mode: metric-table highlights.

    Returns None when no metric table parses, so the caller can fall back
    to the standard press-release path.
    """
    entries = _parse_metric_highlights(lines)
    if entries is None:
        return None
    headline = _shareholder_letter_headline(lines)
    body = "\n".join(entries)
    result = f"{headline}\n\n{body}".strip()
    if len(result) > max_chars:
        result = result[:max_chars].rsplit(" ", 1)[0].rstrip() + "…"
    return result


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
