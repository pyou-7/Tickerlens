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
    r"investor\s+contacts?|note to editors|###|"
    # Batch 188: the safe-harbor intro itself — "This press release
    # contains forward-looking statements that are intended to qualify
    # for the safe-harbor provisions ..." (ED, AAPL, ADI, ADSK and
    # 277 other distinct intros in the cache survey). The bare
    # "forward-looking" alternative only matches when the line STARTS
    # with it; the intro starts with "This press release contains",
    # so ED's lede ran on into the safe-harbor paragraph.
    r"this\s+(press\s+release|release|announcement)\s+contains\s+forward-looking)",
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
    r"|^\d{1,6}\s+\S.*\b\d{5}(?:-\d{4})?\s*$"
    # All-caps title + page marker ("CON EDISON REPORTS 2026 FIRST QUARTER
    # EARNINGS page 2" — Con Edison repeats the release title at the top of
    # each page). The (?-i:...) scope matters: the regex is IGNORECASE, so
    # the prefix class must be case-sensitive — a line with any lowercase
    # letter in the prefix is prose, not a title (AJG's "…ratios using
    # reported revenues on page 1" table labels, AAL's "Oct. 22, 2026 |
    # Page 10" footers). A real headline never ends with a page marker.
    # Batch 188. Survey: 14 distinct lines, all ED.
    r"|^(?-i:[^a-z]+)\s+page\s+\d+$",
    re.IGNORECASE,
)

# Release dateline ("Omaha, NE (BRK.A; BRK.B) –" / "NEW YORK, May 1, 2025 –"):
# city + state/country (optionally with a date and parenthetical tickers)
# ending in an em/en dash or hyphen. A dateline is never a headline — when
# the scan reaches one with no headline found, the release has no headline
# (Berkshire's releases have none), so the honest result is headline=None
# with the lede starting after the dateline. Batch 112.
_DATELINE_RE = re.compile(
    r"^[A-Z][A-Za-z .'\-]*?,\s+[A-Za-z0-9][A-Za-z0-9 .'\-(),;]*?[–—-]\s*$"
)

# Leading page marker glued to headline text ("Page 1 of 16 UnitedHealth
# Group Reports ..." — UnitedHealth's page-image exhibits flatten page 1
# into one bullet-run line, and _split_bullet_runs leaves the marker on the
# first piece). The bare-page admin guard is $-anchored, so it never fires
# when headline text follows the marker, and the headline loop picks the
# marker + headline verbatim. Stripped only in the headline loop, and only
# when the remainder is headline-shaped (see the pick branch) — a
# page-prefixed prose line is not this defect and falls through unchanged.
# Batch 141.
_PAGE_PREFIX_RE = re.compile(r"^page\s+\d+(?:\s+of\s+\d+)?\s+", re.IGNORECASE)

# A "Page N of M" marker glued to a body line ("Page 2 of 16 business,
# with ..." — UnitedHealth's page-image exhibits flatten each page into
# one line, so page 2+ markers land mid-paragraph, ahead of a bullet, or
# ahead of prose). Stripped from body lines only, and only in the full
# "of M" form: the headline loop keeps its own batch-141 guard (a bare
# fragment remainder must not become the headline), and a bare "Page N"
# without "of M" is left alone — a prose sentence like "Page 2 of the
# report ..." must never be beheaded into "of the report ...". Batch 142.
_BODY_PAGE_PREFIX_RE = re.compile(
    r"^page\s+\d+\s+of\s+\d+\s+", re.IGNORECASE
)

# A "view online" trailer glued onto a bullet (UnitedHealth: the outlook
# bullet carries "To view this information in a different format,
# including graphics, published on our website, click here: <url>" plus
# flattened following prose). The www. in the URL tripped _CONTACT_LINE_RE
# and dropped the whole bullet — the earnings outlook — from the
# leading-bullet block, the section, and the lede. Cut at the trailer
# start; the prefix is the bullet. The glued prose after the URL is
# dropped with the trailer: it was dropped with the whole line before,
# and keeping it would bloat the bullet item and push metric bullets
# past the 14-line block cap. Batch 142.
_VIEW_ONLINE_TRAILER_RE = re.compile(
    r"\s*To view this information in a different format\b.*$",
    re.IGNORECASE,
)


def _clean_body_line(ln: str) -> str:
    """Strip a page marker / view-online trailer glued onto a body line."""
    m = _BODY_PAGE_PREFIX_RE.match(ln)
    if m:
        rest = ln[m.end():].strip()
        if rest:
            ln = rest
    m = _VIEW_ONLINE_TRAILER_RE.search(ln)
    if m:
        prefix = ln[: m.start()].rstrip()
        if prefix:
            ln = prefix
    return ln


# A dateline that opens a full sentence ("NEWARK, N.J. – Prudential ...
# today reported ..."), as opposed to _DATELINE_RE's bare dateline-only
# line. Batch 118: Prudential puts the dateline sentence between the
# headline and the bullets, which made _leading_bullet_block return None
# (first body line isn't a bullet) and let a "Financial Highlights" table
# header become the whole body. The lead is a location + dash, so a prose
# line rarely matches it. Batch 155: the location segments were all-caps
# only, so Alphabet's "MOUNTAIN VIEW, Calif. – ..." dateline never
# matched — the mixed-case state ("Calif.") broke the skip, the leading
# block returned None, and Q4's "Financial Highlights" table section (the
# only candidate) served table scaffolding instead of the bullets. Both
# segments now allow mixed case; the comma + capital-led state + spaced
# dash shape still keeps prose out (no digits in the class, so a "Q4"-led
# line never matches, and a lowercase-led second segment never matches).
# Batch 172: Business Wire datelines need no "CITY, ST" comma at all —
# "SEATTLE—(BUSINESS WIRE) October 31, 2024—..." (Amazon),
# "BOZEMAN, Mont.--(BUSINESS WIRE)--October 30, 2024--..." (FICO),
# "GOODLETTSVILLE, Tenn.--(BUSINESS WIRE)--..." (Dollar General),
# "DENVER— (BUSINESS WIRE) — ..." (Palantir),
# "SAN FRANCISCO—(BUSINESS WIRE)—..." (DoorDash). The wire branch is a
# caps city with an optional mixed-case state abbreviation, one or two
# dashes (or a spaced dash) around the literal "(BUSINESS WIRE)" tag, an
# optional "Month DD, YYYY" date, and the lead sentence. The tag itself
# is the anchor — prose never opens with a caps city + dash + wire tag —
# and a bare tag with nothing after it is a credit line, not a dateline
# (the separator after the tag is required).
_DATELINE_LEAD_RE = re.compile(
    r"^[A-Z][A-Za-z .'\-]*,\s*[A-Z][A-Za-z .'\-]*?\s[–—-]\s"
    r"|^[A-Z][A-Z .'\-]*?(?:,\s*[A-Za-z.]+)?\s*[–—-]{1,2}\s*\(BUSINESS WIRE\)"
    r"(?:\s*[–—-]{1,2}\s*|\s+)(?:[A-Z][a-z]+\.? \d{1,2}, \d{4}\s*[–—-]{1,2}\s*)?"
)

# Quarter-prefixed earnings-release document label ("FIRST QUARTER 2026
# EARNINGS RELEASE" — Berkshire heads Q1 releases with it; the real
# headline follows "FOR IMMEDIATE RELEASE" / the date line). Narrow: quarter
# word + year + the label words, so a genuine headline like "X Schedules
# First Quarter Earnings Release" (verb + company subject) never matches.
# Batch 112.
_QUARTER_EARNINGS_LABEL_RE = re.compile(
    r"^(first|second|third|fourth)\s+quarter\s+\d{4}\s+earnings\s+release$",
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
# ...", batch 97), hijacking the section with footnote prose. Batch 155: a
# trailing parenthetical is allowed after the closing word ("Q1 2025
# Financial Highlights (unaudited)") — Alphabet suffixes two quarters'
# headings that way, and without it the leading-bullet block swallows the
# heading plus the table-intro sentence as a bullet continuation.
_HIGHLIGHTS_HEADING_RE = re.compile(
    # Batch 184: the leading-"Highlights" branch is narrowed to
    # heading-shaped tails (of/from/for/include + unterminated rest).
    # The old bare "^highlights?\b" matched ANY line starting with the
    # word — including Chipotle's all-caps sub-headlines ("HIGHLIGHTS
    # RETURN TO POSITIVE COMPARABLE SALES AND TRANSACTIONS IN JUNE",
    # "HIGHLIGHTS POSITIVE COMPARABLE SALES"), which sit between the
    # headline and the dateline and carry real news (June comps turned
    # positive while the quarter was down 4%). The lede loop, the
    # trailing trim, the block boundary and the section collector all
    # treat a match as a heading, so the sub-headline was dropped
    # everywhere. Attested heading shapes after a leading "Highlights"
    # (full-cache survey, 17 distinct lines): bare, "OF SEGMENT
    # RESULTS", "FROM THE QUARTER/YEAR", "from the report include:",
    # "for the ... are listed below:". A prose sentence starting
    # "Highlights of the March quarter, ... are on page five ..." is
    # excluded by the terminator guard, and a flattened-prose fragment
    # ("highlights based suggested destinations ...") by the tail-word
    # guard. The trailing-word branch is unchanged ("Selected Revenue
    # Highlights", "Q1 2025 Financial Highlights (unaudited)").
    r"^highlights?\b[\s:–—-]+(?:of|from|for|include)\b[^.!?]*$"
    r"|\bhighlights?\b[\s:–—-]*(\([^)]*\))?\s*$",
    re.IGNORECASE,
)

# Batch 184: the section collector keeps the BROAD anchor — a line
# starting with "Highlights" anchors a Highlights section even when
# it is content, not a heading. Chipotle's all-caps sub-headlines
# ("HIGHLIGHTS RETURN TO POSITIVE COMPARABLE SALES AND TRANSACTIONS
# IN JUNE") anchor the section that serves the dateline, the bullets,
# the CEO quote and the prose after them; Delta's pointer sentence
# ("Highlights of the March quarter, ... are on page five ...")
# anchors the section that serves the CEO quotes after it. The
# narrowed _HIGHLIGHTS_HEADING_RE above is the definition of a real
# heading (used where a match means drop/break); this regex is only
# the "a section starts here" signal, and _extract_highlights_sections
# decides per anchor whether the line itself is content.
_HIGHLIGHTS_SECTION_ANCHOR_RE = re.compile(
    r"^highlights?\b|\bhighlights?\b[\s:–—-]*(\([^)]*\))?\s*$", re.IGNORECASE
)
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
# Batch 175: the bare-dollar units form — Trane's summary tables head
# with "$, millions except EPS Q3 2024 Q3 2023 ..." (no parens), which
# the parenthesized branch never matches, so the Highlights section
# collector sailed past the units line and served the table's data rows
# as highlights (5 TT quarters). A line starting "$," followed by a
# scale word is a units header, never prose.
# Batch 178: the singular "dollar" — Ares Capital's tables head with
# "(dollar amounts in millions, except per share data)", which the
# "dollars" branch never matches, so the units line plus its column
# headers rode the lede in all 8 ARCC quarters. The lookahead keeps a
# hyphenated prose parenthetical ("(dollar-cost averaging ...)") out:
# only a space, comma, or close-paren may follow the word.
_TABLE_UNITS_RE = re.compile(
    r"\(\s*(dollars?(?=[\s),])|usd|\$)|^\$\s*,\s*(millions|thousands|billions)\b",
    re.IGNORECASE,
)

# A bullet-led line. Batch 154: the glyph bullets (•/●/–/—) need no
# following space — flattened exhibits emit "•Site rental revenues."
# with the text glued to the glyph, and the old "\s" requirement meant
# those bullets missed every bullet guard. Crown Castle Q3 2024 proved
# it: 3 space-less $+%-carrying bullets plus a $+%-carrying quote
# tripped the data_rows >= 4 threshold, so the genuine 7-bullet
# "HIGHLIGHTS FROM THE QUARTER" section was rejected as a financial
# table and the lede fallback served the outlook table instead. The
# hyphen stays strict (space required): a "-$1,234" line is a negative
# table value, not a bullet, and must keep counting as a data row.
# Batch 175: the Wingdings "l" bullet — Trane's releases render their
# highlight bullets as <font face="Wingdings">l</font> (a small square),
# which flattens to a lone "l" ("l Reported revenues of $5.4 billion
# ..."). A line starting with a lone "l" plus a space is never prose
# (no English word is a lone "l"), so "l " is a bullet lead. The space
# stays required: a line starting with the letter "l" glued to a word
# ("lower revenue ...") is prose, not a bullet.
_BULLET_LEAD_RE = re.compile(r"^(?:[•●–—]\s?|-\s|l\s)")


def _is_inline_bullet_start(ln: str) -> bool:
    """True for a line that opens a bullet item with its marker attached
    to the text: "•Q2 was our best quarter ...".

    The _BULLET_LEAD_RE glyphs (•/●/–/—, "- " with the space) plus the
    flattened-list glyphs the lede already treats as bullets ("·"/"○"/
    "▪"/"■" — batch 138/139/140) and "*" (a bullet start in
    _leading_bullet_block). A lone marker line is NOT one — it is a
    separator, handled by _is_lone_bullet_marker — so text must follow
    the marker. Batch 165.
    """
    m = _BULLET_LEAD_RE.match(ln)
    if m:
        return bool(ln[m.end():].strip())
    if ln[:1] in "▪■·○*":
        return bool(ln[1:].strip())
    return False

# A units parenthetical in words, anchored at line start (batch 143):
# "(In millions, except earnings per share)" (FedEx), "(in thousands,
# except per share data)" (AutoZone), "(In billions)" (Elevance). The
# batch-97 _TABLE_UNITS_RE only matches "(Dollars|USD|$", so these
# tables slipped through. Anchored so a mid-sentence "(in millions)"
# in narrative prose never fires.
_TABLE_WORD_UNITS_RE = re.compile(
    r"^\(\s*in\s+(millions|thousands|billions)\b", re.IGNORECASE
)

# A bare units declaration, no parens (batch 178): Visa's tables head
# with the sentence "In billions, except percentages and per share
# data." — no parens, terminated, so neither units regex matches it
# and the termination gate in _is_lede_table_line returns False before
# the units checks. The freed lede budget (a dropped title line) lets
# the loop reach it in 7 Visa quarters. The shape is the whole line: a
# scale word, "except", and an ending in "data"/"information" — a prose
# sentence that merely mentions units ("In billions, except percentages
# and per share data, revenue grew ...") never ends there. DuPont's
# tables head with the same shape in "Dollars in" form ("Dollars in
# millions, except EPS") — the "Dollars in" opening is itself the
# units-declaration signature, so its tail is free.
_LEDE_BARE_UNITS_RE = re.compile(
    r"^(?:In (millions|billions|thousands), except .* (data|information)\.?$"
    r"|Dollars? in (millions|billions|thousands), except)",
    re.IGNORECASE,
)

# The lowercase form of the same declaration (batch 178, post-blast
# scan): eBay's and Emerson's units lines split from their parenthesised
# header and flatten without the capital ("in millions, except per share
# data and percentages", "in millions, except per share)"). A real
# sentence never opens lowercase, so the free tail is safe here — the
# capital form keeps the (data|information) tail so a prose sentence
# that merely mentions units ("In billions, ... revenue grew 8%.")
# still survives.
_LEDE_BARE_UNITS_LOWER_RE = re.compile(
    r"^in (millions|billions|thousands), except",
)

# A bare units declaration with no "except" tail (batch 182): CSX's
# reconciliation table heads with "Dollars in millions," on its own
# line and the "except per share amounts" continuation plus the column
# labels on the next — the "Dollars in" form of _LEDE_BARE_UNITS_RE
# requires ", except", so the split form escaped both it and the
# paren-form units regexes. A line that IS just the declaration is
# never prose: a sentence never consists solely of "Dollars in
# millions,".
_LEDE_BARE_UNITS_DOLLARS_RE = re.compile(
    r"^dollars? in (millions|billions|thousands),?$", re.IGNORECASE
)

# A "% change" table footnote glued onto a quote attribution (batch 180):
# Visa flattens its summary-table footnote ("% change is calculated over
# the comparable prior-year period."), the table's period header ("Q3
# 2024") and the CEO-quote attribution ("Ryan McInerney, Chief Executive
# Officer, Visa, commented on the results:") onto one line. The footnote
# fragment is the table's own text and the attribution without its quote
# is a dangling fragment, so the glued line is table residue — dropping
# it frees the lede budget for the quote itself, which follows the table.
# Both halves are required: a bare "% change is calculated ..." line is
# a footnote-definition block (caught elsewhere), and a bare attribution
# ("... commented on the results:") is a legitimate quote intro the
# colon-heading veto protects.
_LEDE_PCT_CHANGE_FOOTNOTE_RE = re.compile(r"% change is calculated", re.IGNORECASE)
_LEDE_QUOTE_ATTRIBUTION_TAIL_RE = re.compile(
    r",\s*(?:commented|said|noted|added)(?:\s+on\s+the\s+results)?\s*:\s*$",
    re.IGNORECASE,
)

# A quote attribution split across wrapped lines (Emerson Q4 FY2024):
# the budget line ends "...said Emerson President and Chief Executive
# Officer" and the speaker's name plus the quote's second half sit on
# the next line ("Lal Karsanbhai. "We have done an exceptional job
# ..."). The finish rule reads the budget line as a complete item —
# it ends in a role noun, so neither the wrap-tail test (a function
# word) nor the batch-180 attribution-tail test (a colon-ended
# attribution) fires — and breaks, orphaning the quote continuation.
# The shape: a quote verb followed by a role title at the line end,
# with no comma between verb and role — a complete attribution names
# the speaker on the same line ("said Jane Smith, President and CEO",
# comma after the name), so the comma is the guard that keeps a
# finished attribution finished. Batch 181.
_LEDE_QUOTE_VERB_RE = re.compile(
    r"\b(said|says|commented|noted|added|stated)\b", re.IGNORECASE
)
_LEDE_SPLIT_ATTRIBUTION_ROLE_RE = re.compile(
    r"\b(?:(?:President|Chairman|Chair|Chair-Elect)\s+and\s+)?"
    r"(?:Chief Executive Officer|Chief Financial Officer|"
    r"Chief Operating Officer|CEO|CFO|COO|President|Chairman|Chair|"
    r"Chief Executive|Chief Financial|Chief Operating)\.?$",
    re.IGNORECASE,
)


def _is_lede_split_quote_attribution(ln: str) -> bool:
    """True for a quote attribution whose speaker name sits on the
    next line: a quote verb plus a role title at the line end, no comma
    between verb and role. The quote it introduces continues past the
    budget line, so the finish rule must treat the item as unfinished.
    A complete attribution ("said Jane Smith, President and CEO") has
    the comma and never qualifies; a bare role line has no verb and
    never qualifies."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    verb = _LEDE_QUOTE_VERB_RE.search(s)
    if not verb:
        return False
    if "," in s[verb.start() :]:
        return False
    return bool(_LEDE_SPLIT_ATTRIBUTION_ROLE_RE.search(s))


def _lede_quote_is_open(lines: list[str]) -> bool:
    """True when the lede's quotes are unbalanced — an opening quote
    mark with no closing mark yet. A multi-sentence CEO quote closes
    after its last sentence, not after its first: the finish rule's
    sentence-terminated break must not fire while the quote that the
    budget line opened is still open (Emerson Q4 FY2024: the second
    quote sentence ends "…Emerson Management System." and the third
    sentence "Emerson's leading technology … fiscal 2025." still
    belongs to the same quote). The marks pair on a stack: a curly
    open pushes, a curly close pops, and a straight quote pops when
    one is open and pushes when none is — so a curly open closed by
    a straight mark (Bristol Myers' "…to patients."" and Cintas'
    "…professional manner."") counts as closed, not open. Without
    the stack, the mixed style reads as an open quote and the finish
    rule pulls the table chrome below it (BMY's "$ in millions,
    except per share amounts" header, CTAS's guidance-table
    fragments). The overrun cap (4 lines) still bounds the pull-in,
    so a stray mark can cost at most a few lines. Batch 181;
    stack pairing batch 188."""
    depth = 0
    for ln in lines:
        for ch in ln:
            if ch == "“":
                depth += 1
            elif ch == "”":
                depth = max(0, depth - 1)
            elif ch == '"':
                depth = depth + 1 if depth == 0 else depth - 1
    return depth > 0

# A "Percent Change" column header in words (batch 143): FedEx's tables
# spell the header out, so the batch-97 "% change" check never fires.
# Full-line (possibly repeated for multi-period headers) so a prose
# "percent change" inside a sentence never fires.
_PERCENT_CHANGE_WORDS_RE = re.compile(r"^(percent change\s*)+$", re.IGNORECASE)

# One flattened table cell on its own line (batch 143): a lone "$", a
# bare number ("1,757,093", "(1,371,420 )", "2024"), a lone $ amount
# ("$ 0.44" — a flattened table cell, not a metric value: a metric
# value carries a scale word or suffix, "$50.2 billion" / "$1.2B",
# which the number-only class never matches; batch 181, CSX's
# recon-table EPS cell), or a period header ("Three Months Ended",
# "12 Weeks Ended 12 Weeks Ended"). Simon's "Financial Highlights"
# table splits every cell across lines, so no line carries both $ and
# % and no units line exists at all.
_BARE_CELL_RE = re.compile(r"^(\$|\(?[\d,\s]+\)?|\$\s?[\d,().]+)$")
_PERIOD_HEADER_RE = re.compile(
    r"^(((three|six|nine|twelve)\s+months\s+ended\s*)+"
    r"|(\d+\s+weeks\s+ended\s*)+"
    r"|(\d+\s+months\s+ended\s*)+)$",
    re.IGNORECASE,
)

# Header-only table stubs (batch 143, second pass): FedEx FY2026 Q2/Q3
# flatten their multi-period headers onto single lines ("Three Months
# Ended Six Months Ended", "November 30, 2025 November 30, 2024
# Percent" / "Change ..."), so the section that survives the first
# pass is six header lines and no data rows. Its lines are all header
# fragments: a standalone "(Unaudited)" annotation, a doubled period
# header, date lines ending in "Percent", and a lone "Change" line.
_STANDALONE_PAREN_RE = re.compile(r"^\(.{1,30}\)$")
# A lone "Change"/"Percent" header word (batch 143): the trailing
# " Percent" branch is case-sensitive on purpose — a wrapped narrative
# line ending in lowercase "percent" is prose, while the capitalized
# "Percent" at a line end is a split column header.
_HEADER_WORD_RE = re.compile(r"^(change|percent)$", re.IGNORECASE)

# A count row: a short label ending in two or more bare numbers
# ("Beginning stores 6,627 6,432", "Stores opened 39 23") — AutoZone's
# "Store Count" table has no $ or % anywhere. Month-name lines are
# excluded: a doubled date header ("November 22, 2025 November 23,
# 2024") also ends in two numbers but is a header, not a row, and a
# prose dateline inside a section would false-fire the same way.
_MONTH_NAME_RE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\b",
    re.IGNORECASE,
)
_COUNT_ROW_RE = re.compile(r"(?:^|\s)[\d,]+\s+[\d,]+$")


def _looks_like_table_cell(ln: str) -> bool:
    """True for one flattened cell line: lone $, bare number, period header."""
    if _BULLET_LEAD_RE.match(ln):
        return False
    if _BARE_CELL_RE.match(ln):
        return True
    if _PERIOD_HEADER_RE.match(ln):
        return True
    if _STANDALONE_PAREN_RE.match(ln):
        return True
    if _HEADER_WORD_RE.match(ln) or ln.endswith(" Percent"):
        return True
    if (
        len(ln) <= 60
        and not ln.rstrip().endswith((".", "!", "?", ":"))
        and "$" not in ln
        and "%" not in ln
        and not _MONTH_NAME_RE.search(ln)
        and _COUNT_ROW_RE.search(ln)
    ):
        return True
    return False


def _looks_like_financial_table(lines: list[str]) -> bool:
    """True when a collected "Highlights" section is a data table, not prose."""
    strong = False
    data_rows = 0
    cells = 0
    for ln in lines:
        if _TABLE_UNITS_RE.search(ln) or re.search(r"% change", ln, re.IGNORECASE):
            strong = True
        elif not _BULLET_LEAD_RE.match(ln) and "$" in ln and "%" in ln:
            data_rows += 1
        # Batch 143: flattened-cell tables. The new strong signals and
        # the cell count apply to non-bullet lines only, keeping the
        # batch-107 bullet guard: narrative bullets never count.
        if not _BULLET_LEAD_RE.match(ln):
            if _TABLE_WORD_UNITS_RE.match(ln) or _PERCENT_CHANGE_WORDS_RE.match(ln):
                strong = True
            if _looks_like_table_cell(ln):
                cells += 1
    return strong or data_rows >= 4 or cells >= 3


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


# Headline verbs: a longer all-caps line carrying one is the release's
# sub-headline, not a section heading ("Q2 ORGANIC SALES AND ADJUSTED
# EPS EXCEED OUTLOOK", "COMPANY MAINTAINS FULL-YEAR REVENUE AND EPS
# GUIDANCE", "RESETTING DIVIDEND TO ACCELERATE DEBT REDUCTION").
# Batch 177. Batch 178 adds the missing members of families the list
# already covers — AFFIRMS (American Water's "AFFIRMS 2024 EPS GUIDANCE
# AND LONG-TERM GROWTH TARGETS"), PROVIDES (Campbell's "PROVIDES
# FULL-YEAR FISCAL 2027 GUIDANCE"), CONFIRMS / REVISES / INITIATES
# (FedEx's "... Earnings Outlook" headings), REITERATES / REITERATING
# (Church & Dwight's "REITERATING FULL YEAR 2026 OUTLOOK") — each is a
# sub-headline the title-line skip would otherwise drop.
_LEDE_HEADLINE_VERB_RE = re.compile(
    r"\b(REPORTS?|ANNOUNCES?|EXCEEDS?|RAISES?|MAINTAINS?|LEADS?|"
    r"NAMES?|APPOINTS?|ELECTS?|DECLARES?|POSTS?|DELIVERS?|"
    r"ACHIEVES?|SETS?|UPDATES?|REAFFIRMS?|AFFIRMS?|PROVIDES?|"
    r"CONFIRMS?|REVISES?|INITIATES?|REITERATES?|REITERATING|"
    r"GUIDES?|RESETTING|"
    r"RESETS?|GROWS?|INCREASES?|DECREASES?|BEATS?|TOPS?|MISSES?|"
    r"LIFTS?|CUTS?|EXPANDS?|LAUNCHES?|INTRODUCES?|UNVEILS?|"
    r"RETIRE|ASSUME|COMPLETES?)\b",
    re.IGNORECASE,
)


def _is_lede_heading_fragment(ln: str) -> bool:
    """True for an all-caps section-heading fragment in the lede — a lone
    all-caps word ("QUARTER" from a "Fourth Quarter" heading, "YEAR" from
    "Full Year") or a short all-caps heading ("RESULTS FOR THE QUARTER").
    An all-caps line is never narrative prose, so it never belongs in the
    lede; left in, it consumes one of the 6 lede lines and truncates a real
    bullet (Chubb Q4 2024: the "QUARTER" line plus the leading "●" left
    bullet 2 cut mid-item). Batch 138; batch 153 extends the single word
    to short headings (<=4 words). Batch 177 extends the bound to 8
    words for table titles ("FOURTH QUARTER AND FULL YEAR SUMMARY
    FINANCIALS" — Moody's Q4 2025, 6 words), guarded by a headline-verb
    list and a no-figures rule: a longer all-caps line is usually the
    release's sub-headline ("Q2 ORGANIC SALES AND ADJUSTED EPS EXCEED
    OUTLOOK", "AMERICAN WATER REPORTS SOLID SECOND QUARTER RESULTS"),
    and the verb is what tells a sub-headline from a table title.
    """
    words = ln.split()
    if not words:
        return False
    if not ln.isupper() or not any(c.isalpha() for c in ln):
        return False
    # Batch 184: an all-caps line leading with "Highlights" that is NOT
    # a highlights heading (per _HIGHLIGHTS_HEADING_RE) is a sub-headline
    # — Chipotle Q3 2025's "HIGHLIGHTS POSITIVE COMPARABLE SALES" sits
    # between the headline and the dateline and carries the quarter's
    # news — not a section-heading fragment. The regex is the single
    # definition of a highlights heading, so its heading shapes
    # ("HIGHLIGHTS", "HIGHLIGHTS OF SEGMENT RESULTS", "HIGHLIGHTS FROM
    # THE QUARTER") still return True here; only the content shapes
    # escape. Placed before the word-count branches so it covers the
    # 5–8-word band too, where the verb veto would otherwise drop a
    # verb-less sub-headline ("RETURN" is not a headline verb — and
    # must not become one, or "Return on Equity" table labels escape
    # the table-header predicate).
    if re.match(r"highlights?\b", ln, re.IGNORECASE) and not (
        _HIGHLIGHTS_HEADING_RE.search(ln)
    ):
        return False
    if len(words) <= 4:
        return True
    if len(words) > 8:
        return False
    if "$" in ln or "%" in ln:
        return False
    if any(c.isdigit() for c in ln):
        return False
    return not _LEDE_HEADLINE_VERB_RE.search(ln)


# A colon-ended list-intro / section heading in the lede ("Financial
# Results for the Quarter:", "Fiscal 2026 outlook:", "Fourth Quarter
# 2024:", "Business highlights included the following:"). It carries no
# figures and no news — the list or table below it is the content — so
# it only consumes one of the 6 lede lines and starves a real bullet
# (Disney Q3 2026: "Fiscal 2026 outlook:" sits above the outlook
# bullets; Capital One: "The quarter included the following adjusting
# items:" sits above the adjusting-items table). The "the following:" /
# "as follows:" idiom fires regardless of verbs ("included" is part of
# the idiom); otherwise the line must be a bare noun phrase — no verb
# at all. A quote attribution ("Sundar Pichai, CEO of Google and
# Alphabet, said:") is never a heading: dropping it would orphan the
# quote, so "said"/"says" vetoes. Batch 180: "commented"/"comments"
# joins the veto — the same attribution shape ("Ryan McInerney, Chief
# Executive Officer, Visa, commented on the results:") was classified
# as a colon heading and dropped, orphaning the quote it introduces;
# "noted"/"added" were already vetoed via _LEDE_COLON_VERB_RE.
# Batch 177. Batch 178: the bare-phrase
# bound moves 8 -> 12 words — a table's label line is the same shape
# one word longer ("Weighted average yields on debt and other income
# producing securities(7):" — Ares Capital, 10 words, no verb), and a
# 9-12-word verb-less colon line is a label or a heading either way,
# never a prose lead-in (a lead-in carries a verb).
_LEDE_COLON_VERB_RE = re.compile(
    r"\b(is|are|was|were|be|been|being|has|have|had|expected|expects|"
    r"expect|continued|continues|continue|announced|announces|"
    r"reported|reports|said|says|noted|added|delivered|delivers|"
    r"provides|provided|reflects|reflected|includes|included|"
    r"include|drives|drove|shows|showed|remains|remained|grew|"
    r"grows|increased|decreased|rose|fell|will|would|can|could|"
    r"should)\b",
    re.IGNORECASE,
)


def _is_lede_colon_heading(ln: str) -> bool:
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if not s.endswith(":"):
        return False
    if "$" in s or "%" in s:
        return False
    body = s[:-1].strip()
    if re.search(r"\b(said|says|commented|comments)\b", body, re.IGNORECASE):
        return False  # quote attribution — never a heading
    words = body.split()
    if not words:
        return False
    low = body.lower()
    m = re.search(r"\bthe following\b((?:\s+\w+){0,3})\s*$", low)
    if m and not _LEDE_COLON_VERB_RE.search(m.group(1)):
        return len(words) <= 14  # list-intro idiom, verb or not — the
    # tail after "the following" is a bare noun phrase ("adjusting
    # items"); a verb there ("metrics will improve") makes it a prose
    # lead-in, not an intro, and it falls through to the verb veto.
    if low.endswith("as follows"):
        return len(words) <= 14
    if len(words) > 12:
        return False
    return not _LEDE_COLON_VERB_RE.search(body)


# A summary-table column-header line in the lede ("MCO Diluted EPS MCO
# Adjusted Diluted EPS2" — Moody's, 6 stored rows; "Impact After-Tax
# Diluted EPS" — Capital One's adjusting-items table header, 5 rows).
# It is two column labels flattened onto one line: figure-less,
# unterminated, every word capital-led, carrying a metric token, with
# either a repeated label word or a table qualifier (Adjusted /
# After-Tax / Pre-Tax / Non-GAAP / GAAP). A sub-headline looks similar
# but carries a headline verb ("Q2 ORGANIC SALES AND ADJUSTED EPS
# EXCEED OUTLOOK", "RESETTING DIVIDEND TO ACCELERATE DEBT REDUCTION",
# "Investment Income Leads Second-Quarter Profits") — the verb vetoes.
# Batch 177. Batch 178: footnote digits ride the qualifier ("Organic
# Net Sales, Non-GAAP1", "Adjusted Diluted Net Earnings Per Common
# Share, Non-GAAP1,2" — Estée Lauder's summary-table headers), so the
# qualifier/repeat comparison strips trailing digits and commas first
# ("Non-GAAP1,2" -> "non-gaap", "EPS2" -> "eps"); "Earnings" joins the
# metric list for the same pair of lines.
_LEDE_TABLE_HEADER_METRIC_RE = re.compile(
    r"\b(EPS|Revenue|Income|Margin|EBITDA|EBITA|EBIT|Sales|Cash|Profit|Dividend|Earnings)\d?\b",
    re.IGNORECASE,
)
_LEDE_TABLE_HEADER_QUALIFIERS = frozenset(
    {"adjusted", "after-tax", "pre-tax", "non-gaap", "gaap"}
)


def _is_lede_table_header(ln: str) -> bool:
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if "$" in s or "%" in s:
        return False
    if _is_sentence_terminated(s):
        return False
    words = s.split()
    # Batch 181: the floor moves 4 -> 3 — Emerson's "Adjusted Segment
    # EBITA4" is a 3-word column label (metric + qualifier), and the
    # capital-led + metric + qualifier guards already keep prose out.
    # A bare year token is transparent in the capital-led check (FICO's
    # "Fourth Quarter Fiscal 2024 GAAP Revenue" is a period phrase plus
    # a metric label, not prose) — the year is already excluded from
    # the repeated-word/qualifier list below, so only this loop needed
    # the skip.
    if not 3 <= len(words) <= 8:
        return False
    if not _LEDE_TABLE_HEADER_METRIC_RE.search(s):
        return False
    if _LEDE_HEADLINE_VERB_RE.search(s):
        return False  # sub-headline, not a column header
    for w in words:
        if _LEDE_YEAR_RE.fullmatch(w.strip(",")):
            continue  # a bare year is a period token, not a word
        if w.strip(",") in ("-", "–", "—"):
            continue  # Batch 182: a bare dash token is a separator,
            # not a word — Brown & Brown's "Diluted Net Income Per
            # Share - Adjusted" is a column label, and the dash was
            # the only thing keeping the capital-led check out.
        # Batch 188: a parenthesized capital word ("(Loss)" — AJG's
        # "Net Earnings (Loss) EBITDAC Diluted Net Earnings" column
        # header) is capital-led: strip the parens before the check.
        # A parenthesized lowercase word ("(in", "(loss") still fails,
        # and a bare "(" is empty after the strip.
        w2 = re.sub(r"\d+$", "", w).lstrip("(").rstrip(")")
        if not w2 or not w2[0].isupper():
            return False
    lowered = [
        re.sub(r"[\d,]+$", "", w.lower().strip(",")) for w in words
    ]
    lowered = [w for w in lowered if w]
    if len(set(lowered)) < len(lowered):
        return True  # a label word repeats: two labels, one line
    return any(q in lowered for q in _LEDE_TABLE_HEADER_QUALIFIERS)


# Table residue in the lede (batch 153): Crown Castle's releases open with
# the outlook table directly after the dateline paragraph ("...as reflected
# in the table below."), so the old lede loop filled its 6-line budget with
# the table itself — unit line, outlook-table headings, header lines, data
# rows — and the real highlights bullets after the table starved. Table
# lines are now skipped in the lede loop: they neither consume budget nor
# get stored, so the prose after the table is collected instead.
#
# The predicates are deliberately strict about wrapped prose: _html_to_text
# keeps literal newlines inside block elements, so a long paragraph arrives
# as unterminated mid-sentence fragments — "fiscal 2026 second quarter
# results with total revenue of $16.0 billion, up 8% in" looks exactly
# like an unterminated $-carrying line. A wrapped fragment is therefore
# never skipped on $/%/unterminated alone: figure-carrying lines must be
# figure-dense (at most 3 non-figure words), header lines must be pure
# header vocabulary, and label lines must be short. Terminated lines and
# bullets are never table lines.
_LEDE_HEADING_WORDS = frozenset(
    [
        "current", "previous", "full", "year", "quarter", "outlook",
        "midpoint", "guidance", "summary", "financial", "compared",
        "growth", "rate", "actual", "estimate", "change", "percent",
        "first", "second", "third", "fourth", "half", "to", "vs",
        "fiscal", "annual", "q1", "q2", "q3", "q4",
    ]
)
_LEDE_PERIOD_TOKEN_RE = re.compile(
    r"^(q[1-4]|full|year|quarter|half|first|second|third|fourth|actual|"
    r"estimate|outlook|change|percent|growth|rate|compared|to|midpoint|vs|"
    r"%|\(\w\)|\d{4})$",
    re.IGNORECASE,
)
# Batch 156: the $ may be space-separated from its figure in flattened
# tables ("Revenues $ 86,310 $ 96,469"). Batch 157: a $ before a figure
# is no longer required for short data rows, but it still distinguishes
# the pre-existing behavior for long lines (a flattened table mega-line
# with bare-number figures is never a lede data row). Batch 178: the $
# may also be separated from a DECIMAL figure by a space and a period
# ("Diluted Net Earnings Per Common Share $ .44 $ .91 (52) %" — Estée
# Lauder's summary table flattens "$0.44" as "$ .44"), so the optional
# dot is part of the $ figure too.
_LEDE_DATA_ROW_RE = re.compile(r"\$\s?\.?[\d(]")
# Batch 183: a $-to-$ range ("$7.50 to $8.00") is a guidance statement,
# never a table row — a row's values are separate columns. Batch 178
# guarded only the 81-120 band with this; the <=80 branch and the
# >=40% density branch still classified short ranges as rows (GPC's
# 55-char "Reaffirms 2026 Outlook for Adjusted EPS of $7.50 to $8.00"
# sub-headline; the dense "EPS $7.50 to $8.00"). Shared here so every
# $-carrying branch uses the same exemption.
_LEDE_DOLLAR_RANGE_RE = re.compile(r"\$\s?\.?[\d,().]+\s+to\s+\$", re.IGNORECASE)
_LEDE_FOOTNOTE_TAIL_RE = re.compile(r"\(\w\)$")
# A table's symbol legend ("NM = not meaningful" — Allstate defines the
# NM cell value below its Consolidated Highlights table). A short
# all-caps symbol plus " = " plus a definition is legend, never prose:
# narrative never opens with an abbreviation-equals definition. Batch 160.
# Batch 173: the quoted-symbol dash form ("“cc” - constant currency" —
# Walmart's legend after its footnote run) is the same class with a dash
# instead of "=".
_LEDE_SYMBOL_LEGEND_RE = re.compile(
    r"^[A-Z]{1,5}\s*=\s+\S"
    r'|^["“”\'][A-Za-z]{1,5}["“”\']\s*[-\u2013\u2014]\s+\S'
)
# A spaced footnote-glyph legend line ("* Measures used in this release
# ..." — Allstate's non-GAAP legend below its table). _FOOTNOTE_DEF_RE
# deliberately matches only ATTACHED glyphs ("*Non-GAAP ...") for headline
# purposes — a spaced "* Foo" is pinned as not-a-footnote-def there — but
# in the lede a line leading with a footnote glyph is the table's legend,
# never narrative: "*" is not a bullet lead in this extractor
# (_BULLET_LEAD_RE is •●–—/-/l only), so no bullet is ever shaped this way.
# Batch 160.
_LEDE_FOOTNOTE_GLYPH_RE = re.compile(r"^[*†‡]\s+\S")
# A table-intro sentence (batch 156): "The following table summarizes ..."
# or "The table below summarizes ...". Only "summarizes" is attested in
# real exhibits (Alphabet, Adobe) — "sets forth" is genuine prose in the
# wild (Crown Castle Q1 2026: "The following table sets forth Crown
# Castle's current full year 2026 Outlook, which includes a $40 million
# decrease ..."), so the verb list stays at one word rather than guessing
# synonyms that would eat real sentences.
_TABLE_INTRO_RE = re.compile(
    r"\b(?:following table|table below)\s+summarizes\b",
    re.IGNORECASE,
)
# Figure tokens for the data-row density rule. The bare-number branch
# must start with a digit (a bare "[\d,]+" also matches a lone comma, and
# "13.8%" must match as one token, not "13" + "8%") — otherwise wrapped
# prose fragments score as figure-dense and get skipped as table rows.
# A standalone "%" counts too: spaced-out tables write "67 %" as two
# tokens, and without it a 3-figure row scores under the density bar.
_LEDE_FIGURE_RE = re.compile(r"\$[\d,().]+|\d[\d,.]*%|\(\w\)|\bN/A\b|\d[\d,.]*|%")


def _is_sentence_terminated(ln: str) -> bool:
    """True when a line ends with sentence punctuation, modulo trailing
    closing quotes/parens (a CEO quote ends '...value."' — punctuated
    prose, not an unterminated fragment)."""
    s = ln.rstrip().rstrip("”\"'’)]}")
    return s.endswith((".", "!", "?", ":", "…"))


def _is_lede_table_heading(ln: str) -> bool:
    """True for an outlook/guidance table title: every word is header
    vocabulary (footnote markers and trailing footnote digits stripped)
    and the line names an outlook or guidance table. A prose clause that
    merely mentions the outlook ("we raised the full year 2025 outlook
    midpoint") fails on its verbs and pronouns."""
    low = ln.lower()
    if "outlook" not in low and "guidance" not in low:
        return False
    norm = re.sub(r"\(\w\)", " ", ln)
    words: list[str] = []
    for w in norm.split():
        if re.fullmatch(r"\d", w):
            continue  # standalone footnote digit ("Summary 2")
        if re.fullmatch(r"[Qq][1-4]", w):
            words.append(w.lower())
        elif re.fullmatch(r"\d{4}", w):
            words.append(w)
        elif re.fullmatch(r"[A-Za-z]+[^A-Za-z]*", w):
            # Trailing footnote digits and punctuation ("Summary2",
            # "Summary:2") are stripped; the word itself must be vocab.
            words.append(re.sub(r"[^A-Za-z]+$", "", w).lower())
        else:
            words.append(w.lower())
    if not words or len(words) > 12:
        return False
    return all(
        w in _LEDE_HEADING_WORDS or (w.isdigit() and len(w) == 4)
        for w in words
    )


def _is_lede_period_header(ln: str) -> bool:
    """True for a flattened period header: every word is a period token
    and a year is present ("Full Year 2025 Actual", "Q2 2026 Q2 2025 (c)",
    "Full Year 2024 Actual % Change"). Any real prose word breaks it."""
    words = ln.split()
    return (
        len(words) <= 10
        and any(re.fullmatch(r"\d{4}", w) for w in words)
        and all(_LEDE_PERIOD_TOKEN_RE.match(w) for w in words)
    )


# A bare period-fragment line ("Three Months", "Six Months", "Ended",
# "Year Ended", "Full Year", "Three Months Ended"): a table's period
# header flattened onto one line, with no month or year to anchor it.
# Every word must be a period token — a prose sentence ("Three months
# ended September 30, 2025 ...") carries a month name and digits, so it
# never qualifies, and a bullet ("• Three months ...") never qualifies
# either. The lede loop already drops these via _is_lede_table_line
# (every fragment is a table line), but the leading-bullet block and the
# Highlights section collector break only on the strong heading shapes
# (period header needs a year; date header needs "ended" or a month —
# "Three Months" has neither), so a fragment rides along as a bullet
# continuation (BlackRock: the "SUMMARY OF NONOPERATING INCOME" table's
# header follows the expense bullets, and the fragments tail the stored
# rows). Batch 174.
_PERIOD_FRAGMENT_WORDS = frozenset(
    "three six nine twelve month months ended year years full quarter quarters".split()
)


def _is_bare_period_fragment(ln: str) -> bool:
    """True for a standalone period-header fragment line."""
    if _BULLET_LEAD_RE.match(ln):
        return False
    words = [w.strip(",.").lower() for w in ln.split()]
    if not 1 <= len(words) <= 4:
        return False
    return all(w in _PERIOD_FRAGMENT_WORDS for w in words)


# One token of a flattened date header ("Quarter Ended September 30, Nine
# Months Ended September 30,"): period words, month names, and day/year
# numbers, with trailing commas stripped. The all-words-must-match rule
# is the guard — a prose fragment ("for the quarter ended September 30")
# carries "for"/"the" and never qualifies. Batch 156 adds full/year/years:
# a doubled period header ("Quarter Ended December 31, Year Ended
# December 31,") is a date header too, and without them it rode the lede
# budget after a rejected table section.
_LEDE_DATE_TOKEN_RE = re.compile(
    r"^(quarter|quarters|month|months|ended|three|six|nine|twelve|full|year|years|"
    r"january|february|march|april|may|june|july|august|september|"
    r"october|november|december|\d{1,4})$",
    re.IGNORECASE,
)


def _is_lede_date_header(ln: str) -> bool:
    """True for a flattened table date header: every word is a date
    token and a month name or "ended" is present. AppLovin's tables
    flatten their period headers onto one line, and the line otherwise
    survives every table predicate (no $/%, no year-word, too long to
    be a label)."""
    words = [w.rstrip(",") for w in ln.split()]
    if not words or len(words) > 12:
        return False
    low = ln.lower()
    if "ended" not in low and not _MONTH_NAME_RE.search(ln):
        return False
    return all(_LEDE_DATE_TOKEN_RE.match(w) for w in words)


# A bare as-of date fragment ("As of December 31," — Ares Capital's
# balance-sheet date line, served as a lede line in Q4 FY2025 above
# the Fair-value recon row). The date-header predicate never fires on
# it ("As"/"of" are not date tokens), and it carries no year — a table's
# as-of line never does, the year lives in the column header — so the
# shape is the whole month-day fragment with an optional trailing
# comma. A prose fragment ("As of December 31, revenue grew ...")
# always continues on the same line, so a standalone year-less as-of
# line is table residue, never narrative. Batch 178.
_LEDE_ASOF_DATE_RE = re.compile(
    r"^As of (January|February|March|April|May|June|July|August|"
    r"September|October|November|December) \d{1,2},?$"
)


def _is_lede_asof_date(ln: str) -> bool:
    """True for a standalone year-less as-of date fragment line."""
    return bool(_LEDE_ASOF_DATE_RE.match(ln.strip()))


_LEDE_SUMMARY_RESULTS_ANCHOR_RE = re.compile(
    r"^Summary of Financial Results(?:\s*-\s*(.*))?$", re.IGNORECASE
)


def _is_lede_summary_results_title(ln: str) -> bool:
    """True for AJG's summary-table title: "Summary of Financial
    Results" plus an optional " - <period>" tail of period/date
    tokens only ("First Quarter", "Six-Months ended June 30",
    "Year Ended December 31", the wrapped "Fourth"). The anchor is
    the guard — no narrative line starts with it, and the tail-token
    gate keeps a prose continuation ("... for the first quarter")
    out — so the dated forms are titles even though they carry
    figures ("June 30", "December 31"). Batch 188."""
    s = ln.strip()
    m = _LEDE_SUMMARY_RESULTS_ANCHOR_RE.match(s)
    if not m:
        return False
    tail = (m.group(1) or "").strip()
    if not tail:
        return True
    words = [w.strip(",") for w in tail.split()]
    if not words or len(words) > 8:
        return False
    return all(
        _LEDE_DATE_TOKEN_RE.match(w)
        or w.lower() in ("first", "second", "third", "fourth")
        or re.fullmatch(r"(six|nine|twelve)-months?", w, re.IGNORECASE)
        for w in words
    )


def _is_lede_table_title(ln: str) -> bool:
    """True for a table's title line: an unterminated, figure-less line
    that pairs a period phrase with table vocabulary ("Non-GAAP Financial
    Measures Three Months Ended September" — Southern Company's table
    title, which otherwise consumes a lede line and lets the table's
    rows fill the 6-line budget). Guards: terminated lines are prose;
    any figure (a year, a day, a value) means a header row or a prose
    fragment, not a title — so "Three Months Ended December 31," and
    "Fourth Quarter 2024" never qualify; the vocabulary is table-specific
    ("financial measures", "non-gaap", "financial summary"), so a prose
    fragment like "a summary of results for the three months ended"
    fails; bullet-led lines never qualify, so a bullet carrying a period
    phrase is never mistaken for a title. Batch 159. Batch 188: AJG's
    "Summary of Financial Results - First Quarter" title carries no
    "ended" period phrase, so the anchored shape above is checked
    first, before the figure guard (its dated forms carry a day)."""
    if _BULLET_LEAD_RE.match(ln) or ln[:1] in "▪■·○":
        return False
    if _is_lede_summary_results_title(ln):
        return True
    if _is_sentence_terminated(ln):
        return False
    if _LEDE_FIGURE_RE.search(ln):
        return False
    words = ln.split()
    if not words or len(words) > 12:
        return False
    low = ln.lower()
    if not re.search(
        r"\b(three|six|nine|twelve)\s+months\s+ended\b"
        r"|\b(year|quarter)\s+ended\b"
        r"|\bmonths\s+ended\b",
        low,
    ):
        return False
    return any(
        vocab in low
        for vocab in (
            "financial measures",
            "non-gaap",
            "financial summary",
            "financial highlights",
            "consolidated",
        )
    )


def _is_lede_dollar_range_statement(ln: str) -> bool:
    """True for a guidance-range STATEMENT: a $-to-$ range carried by a
    label or subject (at least 4 alphabetic words besides "to"). Batch
    183: GPC's "Reaffirms 2026 Outlook for Adjusted EPS of $7.50 to
    $8.00" (6 words), AXP's FY2025 guidance line, BBY's "Expects FY25
    Non-GAAP Diluted EPS of $5.75 to $6.20", Cencora's raised-guidance
    line. A bare range fragment ("$10.40 to $11.00" — Moody's
    outlook-table cell flattened onto its own line) has no words and
    stays a data row: served, it would dangle in the lede as a bare
    pair of numbers with no subject.
    """
    if not _LEDE_DOLLAR_RANGE_RE.search(ln):
        return False
    words = [
        tok
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)?", ln)
        if tok.lower() != "to"
    ]
    return len(words) >= 4


_LEDE_DASH_TOKENS = frozenset({"—", "–", "-"})


def _is_lede_dash_value_row(ln: str) -> bool:
    """True for a flattened table value row whose cells are dash
    placeholders and figures: "– – 65 33 87 44 0.25 0.13" (AJG 2026).
    Batch 187: AJG's 2026 summary tables flatten each adjustment row
    as a label line plus a values line, and the values line starts
    with dash cells for the empty revenue columns — so _BULLET_LEAD_RE
    matches it ("– " / "— " lead) and the batch-175 bullet guard in
    _is_lede_data_row exempted the whole row, which in turn kept its
    label from _is_lede_table_label (the next line was not a data
    row). Both the label and the values then filled the 6-line lede
    budget as fake bullets, starving the CEO quote. The shape is
    wordless by construction — every token is a dash placeholder or a
    figure token, the first token is a dash, at least one figure is
    present — so it can never be a bullet: a bullet always carries
    words. A dashes-only line (no figure) is a lone bullet marker,
    not a value row; a terminated line is prose, not a row.
    """
    if _is_sentence_terminated(ln):
        return False
    tokens = ln.split()
    if len(tokens) < 2 or tokens[0] not in _LEDE_DASH_TOKENS:
        return False
    figures = 0
    for tok in tokens:
        if tok in _LEDE_DASH_TOKENS:
            continue
        if _is_lede_figure_token(tok):
            figures += 1
            continue
        return False
    return figures >= 1


def _is_lede_data_row(ln: str) -> bool:
    """True for a table data row: carries at least 2 figures and figures
    are at least 40% of its tokens ("Net income (loss) per share—diluted
    $0.65 $(3,903) N/A $0.55 $0.10" -> 5 of 10 tokens). A wrapped prose
    fragment with a $ figure is figure-sparse, so it never qualifies; a
    lone value line ("$50.2 billion", one figure) is a metric value, not
    a row, so it is kept. Batch 157: $-less guidance/margin rows ("Net
    Sales Growth (0.5%) - 0.5% 1.5% - 3.5%", "Margin 14.7% 16.4% 170
    bps ...", "FY 2024 FY 2024 FY 2024") are table rows too, and the
    density rule is the guard — but only for short lines. A flattened
    table mega-line (Tesla's whole FINANCIAL SUMMARY as one 4000-char
    line) is figure-dense without a $ before its figures, and skipping
    it just swaps one table mega-line for the next (OPERATIONAL SUMMARY);
    the length cap keeps that pre-existing behavior. A second shape
    qualifies on $ figures alone: a label + 2 $ figures in a short line
    ("Restructuring / Related Costs ~$0.06 ~$0.20" is 2 figures in 6
    tokens, 33%) is a guidance-table row even under the density bar.
    Terminated prose never qualifies — the caller checks termination
    first, and the guard here protects direct callers.
    Batch 160: the $-less caps move 80 -> 120 chars. Allstate's rows run
    82-86 chars ("Net income (loss) applicable to common shareholders
    1,161 (41) NM 2,651 (1,776) NM" is 82; "Property-Liability insurance
    premiums earned 13,694 12,270 11.6 % 39,933 35,826 11.5 %" is 86),
    so the 80 cap let them ride the lede. Tesla's flattened mega-line is
    ~4000 chars, so 120 keeps that guard with wide margin. The 25%
    branch also accepts a trailing "NM" ("not meaningful" — Allstate's
    cell value where a change is meaningless) as a figure-like ending,
    since a row ending in NM is a row, not prose.
    Batch 178: the $-carrying branch's cap moves 80 -> 120 too — the
    batch-160 raise left it behind, and Ares Capital's reconciliation
    rows run 86 chars ("Fair value of accruing debt and other income
    producing securities(5) $ 24,831 $ 23,643"), so they rode the lede
    in 5 quarters. But the 81-120 band is bare-number table values
    ONLY: a wrapped prose fragment ends mid-clause on a word and its $
    figures carry scale words ("We delivered strong financial results
    in Q1, generating $2.0 billion in total revenue, $66 million in net
    income," — Coinbase Q1 FY2025; Chubb's "Net income was $2.32
    billion, up 13.8%, and core operating income was $2.33 billion, up
    14.3%. For the" — both 81-120 chars with 2 $ figures, both prose).
    A table row ends in a value and its $ figures are bare amounts, so
    the extended band requires all four: the line ends in a figure
    token that is not a bare year (Eaton's "... up 24% over 2022"),
    no $ figure is followed by a scale word, no $-to-$ range (Amex's
    "EPS OF $12.65 TO $13.15"; Cencora's "$17.45 to $17.75" — a range
    is a guidance statement, never a table row), and the line is not a
    flattened-list bullet ("■"/"◦" are not in _BULLET_LEAD_RE, so the
    top guard misses them — AIG's "■Net income per diluted share was
    $0.12 ..." and AWK's "◦2023 weather-normalized earnings of $4.77
    ..." are bullets). The plain 80-char branch is unchanged — short
    rows keep the old behavior, and the repair script's $-row guard
    already uses 120. The $-figure count also accepts the spaced-decimal
    form ("$ .44" — Estée Lauder's "$ .44 $ .91" row), via the optional
    dot in _LEDE_DATA_ROW_RE and in the count below.
    Batch 175: a bullet-led line never qualifies — a highlight bullet
    is narrative, never a table row, and _is_lede_table_line already
    exempts bullets, so the predicate itself must too: direct callers
    (repair residue scans) otherwise misflag figure-dense bullets.
    Trane's Wingdings "l" EPS bullet ("l GAAP continuing EPS of $3.43;
    adjusted continuing EPS* of $3.37, up 21 percent") trips the
    $-figures branch (2 $ figures in 78 chars) without it.
    Batch 183: the $-to-$ range exemption is hoisted out of the 81-120
    band to the top of this predicate — a range is a guidance statement
    at any length, so the <=80 branch and the >=40% density branch
    (which both returned True for any 2-$ line) no longer eat short
    guidance sub-headlines. GPC's 55-char "Reaffirms 2026 Outlook for
    Adjusted EPS of $7.50 to $8.00" and the dense "EPS $7.50 to $8.00"
    both classified as data rows before this fix. The exemption is a
    STATEMENT, not any range: _is_lede_dollar_range_statement requires
    >=4 alphabetic words, so a bare range fragment ("$10.40 to $11.00"
    — Moody's outlook-table cell on its own line) stays a data row.
    Batch 187: a dash-led WORDLESS line of dash placeholders and
    figures ("– – 65 33 87 44 0.25 0.13" — AJG 2026) is a value row,
    not a bullet, so it is exempt from the batch-175 bullet guard
    below: _is_lede_dash_value_row runs first and returns True before
    the guard can refuse it. A bullet always carries words, so the
    exemption cannot catch a real bullet.
    Batch 190: a compact period fragment ("4th Q 25", "9 Mths 25" —
    AJG's flattened summary-table column headers) is not a data row:
    its two "figures" are a quarter ordinal and a 2-digit year, period
    labels, not values — but the density rule reads them as figures
    (2 of 3 tokens) and the line qualifies, so a heading directly
    above one ("Summary of Financial Results - Fourth Quarter") is
    misread as a table label by _is_lede_table_label's next-line
    check. The full-cache survey finds 109 such misfires, all AJG,
    all table chrome the other rules drop anyway — the misfire is
    latent today (the batch-188 summary-title branch drops the
    heading first) — but the predicate is wrong on its face, and the
    exemption keeps it wrong nowhere else: a fragment is still table
    residue via the _is_lede_table_line branch added in this batch.
    """
    if _is_lede_dash_value_row(ln):
        return True
    if _is_lede_compact_period_fragment(ln):
        return False
    if _BULLET_LEAD_RE.match(ln):
        return False
    if _is_sentence_terminated(ln):
        return False
    if _is_lede_dollar_range_statement(ln):
        return False
    figures = _LEDE_FIGURE_RE.findall(ln)
    if len(figures) < 2:
        return False
    tokens = ln.split()
    if len(figures) / max(len(tokens), 1) >= 0.4:
        if _LEDE_DATA_ROW_RE.search(ln):
            return True  # $-carrying: the pre-batch-157 behavior
        return len(ln) <= 120  # $-less: short rows only, never mega-lines
    # Batch 159: $-less rows whose label runs 3-4 words dilute figure
    # density below the 40% bar ("Organic revenue growth (Non-GAAP) 6%
    # 6%", "Net Income – Excluding Items (in millions) 2024 2023 2024
    # 2023", "Acquisition and Disposition Impacts — (2) — (2)"). A short
    # line ending in a figure, with >=2 figures at >=25% density and no
    # $ at all, is a row: a wrapped prose fragment ends mid-clause on a
    # word, not a figure, and $-carrying rows are handled by the branch
    # below, so a $-carrying prose fragment can never qualify here. A
    # comparison clause is prose, not a row: "Earnings per share (EPS)
    # up 23% versus Q2 2024; Adjusted EPS up 12%" and "2025 Earnings per
    # share (EPS) 17% greater than 2024" are Kinder Morgan's EPS summary
    # lines — the full-year figures in the second one appear nowhere
    # else — and a data row is a label plus values, never a "versus" /
    # "greater than" narration, so comparison phrases exempt the line.
    # Batch 160: the ending may be "NM" (see above) and the cap is 120.
    if (
        "$" not in ln
        and len(ln) <= 120
        and len(figures) / max(len(tokens), 1) >= 0.25
        and (
            _LEDE_FIGURE_RE.search(tokens[-1])
            or re.fullmatch(r"\(?NM\)?", tokens[-1], re.IGNORECASE)
        )
        and not re.search(
            r"\b(versus|greater than|less than|higher than|lower than|"
            r"compared (?:with|to))\b",
            ln,
            re.IGNORECASE,
        )
    ):
        return True
    dollar_figs = len(re.findall(r"\$\s?\.?[\d(]", ln))
    if dollar_figs >= 2:
        if len(ln) <= 80:
            return True
        # Batch 178, extended band (see docstring): bare-number table
        # values only — ends in a figure (never a bare year), no scaled
        # $ figure, no $-to-$ range, and never a flattened-list bullet
        # ("■"/"◦" bullets are not in _BULLET_LEAD_RE, so the top guard
        # misses them — AIG's "■Net income per diluted share was $0.12
        # ..." and AWK's "◦2023 weather-normalized earnings of $4.77
        # ..." are bullets, not rows). A bare-year ending is prose
        # (Eaton's "Fourth quarter earnings per share of $2.35 and
        # record adjusted earnings per share of $2.55, up 24% over
        # 2022"), and a $-to-$ range is a guidance statement (Amex's
        # "FULL-YEAR 2024 GUIDANCE FOR REVENUE GROWTH OF 9% TO 11% AND
        # EPS OF $12.65 TO $13.15"; Cencora's "$17.45 to $17.75" range),
        # never a table row — a row's values are separate columns.
        if (
            len(ln) <= 120
            and ln[:1] not in "▪■·○◦"
            and _is_lede_figure_token(tokens[-1])
            and not _LEDE_YEAR_RE.fullmatch(tokens[-1].rstrip(","))
            and not _LEDE_DOLLAR_RANGE_RE.search(ln)
            and not re.search(
                r"\$\s?\.?[\d,().]+\s+"
                r"(?:billions?|millions?|thousands?|trillions?)\b",
                ln,
                re.IGNORECASE,
            )
        ):
            return True
    return False


def _is_lede_figure_token(tok: str) -> bool:
    """True for a token that is a single figure: a bare or parenthesized
    number ("44", "(35)", "13.8%"), a $ figure ("$1.2"), or a standalone
    "%" (spaced-out tables write "11.6 %" as two tokens). A footnote
    marker ("(a)") or a symbol ("NM") is not a figure."""
    return bool(re.fullmatch(r"\(?\$?[\d,.]+\)?%?", tok)) or tok == "%"


# A bare 4-digit year (1900-2099, optionally parenthesized). A line
# ending in a year is prose, never a reconciliation row: headlines
# ("Simon® Reports Third Quarter 2024 Results, Affirms Full Year
# 2024"), sub-headlines ("Verizon delivered strong financial growth
# ... in 1Q 2025"), and wrapped fragments ("of common stock at the
# close of business on August 17, 2026") all end in years, while a
# reconciliation value is a small bare number ("41", "(8)", "9") —
# never a year. Batch 161.
_LEDE_YEAR_RE = re.compile(r"\(?(?:19|20)\d{2}\)?")


def _is_lede_recon_row(ln: str) -> bool:
    """True for a reconciliation-table row: a long wordy label plus
    sparse values that no data-row density rule catches. Sempra's
    GAAP-to-adjusted reconciliation table flattens this way: rows carry
    one trailing figure after dash placeholders for empty cells
    ("Equity losses from write-off of rate base disallowances ...
    — — — 44"), rows that end in a dash cell ("Net unrealized losses
    on interest rate swaps ... 9 —", "Tax items related to assets held
    for sale 26 — 26 —"), and bare two-figure rows whose labels dilute
    density to 13-17% ("Impact from foreign currency ... (8) 41").
    Two branches, both guarded by a >=4-word label (the tokens before
    the first figure or dash token): a short label plus a value is a
    metric line ("EPS — $0.89"), not a reconciliation row. The dash
    branch requires a standalone dash token adjacent to a figure token
    (a prose em-dash sits between words) and an ending in a figure or
    a dash, capped at 300 chars. The bare branch requires >=2 figures,
    an ending in a figure, no $ or % anywhere, >=10% density, <=150
    chars, no mid-line sentence boundary (the COIN guard, batch 160),
    and no comparison phrase (the KMI guard, batch 159). Terminated
    prose and bullets never qualify, and a line that is already a lede
    data row is not a recon row — the predicates stay disjoint. A line
    ending in a bare year is prose, never a row (headlines and wrapped
    fragments end in years; a reconciliation value never is one).
    Batch 161."""
    if _BULLET_LEAD_RE.match(ln) or _is_sentence_terminated(ln):
        return False
    if _is_lede_data_row(ln):
        return False
    figures = _LEDE_FIGURE_RE.findall(ln)
    if not figures:
        return False
    tokens = ln.split()
    if not tokens:
        return False
    # The label is the run before the values zone (first figure or dash
    # token); a reconciliation label is a wordy phrase, never 1-3 words.
    first_value = next(
        (
            i
            for i, tok in enumerate(tokens)
            if tok in ("—", "–", "-") or _is_lede_figure_token(tok)
        ),
        len(tokens),
    )
    if first_value < 4:
        return False
    # Dash-cell branch: an empty-cell dash adjacent to a figure, with
    # the line ending in a figure or a dash cell — never in a year.
    dash_idx = [i for i, tok in enumerate(tokens) if tok in ("—", "–", "-")]
    if dash_idx and len(ln) <= 300:
        last = tokens[-1]
        ends_fig_or_dash = (
            _is_lede_figure_token(last)
            and not _LEDE_YEAR_RE.fullmatch(last)
        ) or last in ("—", "–", "-")
        adjacent = any(
            (i > 0 and _is_lede_figure_token(tokens[i - 1]))
            or (i + 1 < len(tokens) and _is_lede_figure_token(tokens[i + 1]))
            for i in dash_idx
        )
        if ends_fig_or_dash and adjacent:
            return True
    # Bare two-figure branch: sparse values, no $ or % anywhere, ending
    # in a figure — never in a year. A wrapped prose fragment ends
    # mid-clause on a word, not a figure; a comparison clause is prose,
    # not a row.
    if (
        len(figures) >= 2
        and "$" not in ln
        and "%" not in ln
        and len(ln) <= 150
        and len(figures) / max(len(tokens), 1) >= 0.10
        and _is_lede_figure_token(tokens[-1])
        and not _LEDE_YEAR_RE.fullmatch(tokens[-1])
        and not re.search(r"[.!?]\s", ln)
        and not re.search(
            r"\b(versus|greater than|less than|higher than|lower than|"
            r"compared (?:with|to))\b",
            ln,
            re.IGNORECASE,
        )
    ):
        return True
    return False


def _is_table_intro_only(ln: str) -> bool:
    """True when a line IS a table-intro sentence, not a paragraph that
    merely opens with one. Batch 181: Emerson's Q3 FY2025 guidance
    paragraph opens "The following table summarizes the fiscal year
    2025 guidance framework." and continues in the same flattened
    line with real guidance prose ("Net and underlying sales guidance
    of ~3.5% ... GAAP EPS is now expected to be ~$4.08 ...") — the
    batch-156 branch dropped the whole paragraph as table residue,
    and the guidance-table rows leaked into the freed budget instead.
    The batch-157 trailing rule already knew this ("Emerson's guidance
    paragraph ... must never be dropped") but only applied at the
    tail; the lede-loop branch had no such guard. The guard is the
    remainder after the intro sentence's first terminator: empty
    (a standalone intro, terminated or not — Cigna's unterminated
    "The following table summarizes The Cigna Group's medical
    customers") means table-only; a remainder carrying a $ figure is
    substantive prose. Measured over the cache: 219 of 220 intro
    lines are single-sentence, exactly 1 (Emerson Q3 FY2025) carries
    $ prose after the intro, 0 are multi-sentence without $. The
    remainder test errs toward prose: a decimal inside the intro
    sentence only lengthens the remainder, so a $ there still saves
    the line."""
    m = _TABLE_INTRO_RE.search(ln)
    if not m:
        return False
    end = len(ln)
    for punct in (".", "!", "?"):
        idx = ln.find(punct, m.end())
        if idx != -1:
            end = min(end, idx)
    rest = ln[end + 1 :].strip() if end < len(ln) else ""
    return not rest or "$" not in rest


_LEDE_SINGLE_VALUE_RE = re.compile(r"~?\(?\$\s?\.?[\d,().]+[BMK]?\)?$")
_LEDE_SINGLE_VALUE_VERB_RE = re.compile(
    r"\b(was|were|is|are|has|have|had|increased|decreased|rose|fell|"
    r"grew|represents|represent|included|includes|generated|totaled|"
    r"reached|amounted|delivered|came|declined|improved|reflects|"
    r"reflected|remains|remained)\b",
    re.IGNORECASE,
)


def _is_lede_single_value_row(ln: str) -> bool:
    """True for a guidance/balance-sheet table row carrying exactly one
    $ value: a metric label plus a single bare amount ("Operating Cash
    Flow ~$3.6B", "Free Cash Flow ~$3.2B", "Discrete taxes related to
    AspenTech transaction $0.09", "IEEPA tariff refunds - ~($0.11)").
    The data-row predicate needs 2 figures, so these single-column rows
    leaked into the lede once the batch-178 budget freeing reached
    Emerson's guidance table (and American's cash-flow table the same
    way). Guards: unterminated and bullet-free (a bullet is narrative);
    the line must END in the bare $ value (a prose $ figure carries a
    scale word — "$135.7 million" — or "per share" after it); the label
    is 2-12 words with no mid-line sentence boundary; and the label
    carries no finite verb and does not end in a preposition ("to",
    "of") — the shapes that separate a table row from a wrapped
    summary line ("FULL-YEAR EARNINGS PER SHARE INCREASED 14% TO
    $11.21", "GAAP Diluted EPS Increased 2% to $1.13", "BOOK VALUE
    PER SHARE OF $99.08", "Adjusted* Diluted EPS of $2.58",
    "reported net income of $374.2", "Board of Directors Declares
    Quarterly Cash Dividend of $0.59"). A table-row label ends in a
    noun, never a preposition. Measured over the cache: 140
    single-value candidates end in "of", every one sampled a prose
    summary line; "at" and "for" have zero attested candidates, so
    they are not in the guard. Participles common in
    table labels ("provided", "reported", "related", "adjusted") are
    deliberately NOT in the verb list, so "Net cash provided by
    operating activities $ 3,803" and "Gross profit, as reported
    $ 2,917" still drop. A lone value ("$50.2 billion", no label) is
    not a row — the label floor keeps the batch-157 lone-value rule.
    Batch 181."""
    if _BULLET_LEAD_RE.match(ln) or _is_sentence_terminated(ln):
        return False
    if len(ln) > 120:
        return False
    if len(re.findall(r"\$\s?\.?[\d(]", ln)) != 1:
        return False
    m = _LEDE_SINGLE_VALUE_RE.search(ln)
    if not m:
        return False
    label = ln[: m.start()].strip()
    words = label.split()
    if not 2 <= len(words) <= 12:
        return False
    if re.search(r"[.!?]\s", label):
        return False
    if _LEDE_SINGLE_VALUE_VERB_RE.search(label):
        return False
    if words[-1].lower() in {"to", "of"}:
        return False
    return True


def _is_lede_table_line(ln: str) -> bool:
    """True for a lede line that is table residue, not narrative."""
    # Batch 187: a dash-led wordless value row ("– – 65 33 87 44
    # 0.25 0.13" — AJG 2026) is a table row, not a bullet, so it is
    # exempt from this guard exactly as it is from the batch-175
    # guard in _is_lede_data_row. A real bullet always carries words.
    if _BULLET_LEAD_RE.match(ln) and not _is_lede_dash_value_row(ln):
        return False
    # ...") is table residue even though it is a terminated sentence — it
    # is the table's own preamble, and without this it consumes a lede
    # line after a rejected table section. Only "summarizes" is matched:
    # "sets forth" is genuine prose in the wild (Crown Castle Q1 2026),
    # so the verb is not generalized. Batch 181: only when the intro
    # sentence IS the line — a paragraph that opens with the intro and
    # continues with real prose (Emerson's guidance paragraph) is
    # content, not residue; _is_table_intro_only is the guard.
    if _is_table_intro_only(ln):
        return True
    # Batch 162: a bare numbered footnote ("1) See Table A ...") is
    # table residue even though it is a terminated sentence — checked
    # before the termination gate, like the table-intro sentence
    # (batch 156), so the tail trim can start on it.
    if _LEDE_FOOTNOTE_NUM_RE.match(ln):
        return True
    if _LEDE_FOOTNOTE_GLYPH_RE.match(ln):
        return True
    # Batch 178: a bare units declaration ("In billions, except
    # percentages and per share data.") is table residue even though it
    # is a terminated sentence — checked before the termination gate,
    # like the table-intro sentence (batch 156).
    if _LEDE_BARE_UNITS_RE.match(ln):
        return True
    if _LEDE_BARE_UNITS_LOWER_RE.match(ln):
        return True
    # Batch 182: a bare "Dollars in millions," units line (CSX's split
    # declaration) and its "except per share amounts ..." continuation
    # glued to the column labels — both are the table's own header,
    # never narrative.
    if _LEDE_BARE_UNITS_DOLLARS_RE.match(ln):
        return True
    if _is_lede_split_units_continuation(ln):
        return True
    # Batch 180: a "% change" table footnote glued onto a quote
    # attribution (Visa) — the footnote and the period header are the
    # table's own text, and the attribution without its quote is a
    # dangling fragment.
    if _is_lede_footnote_attribution(ln):
        return True
    if _is_sentence_terminated(ln):
        return False
    # Anchored unit lines (a mid-sentence "(dollars ...)" parenthetical
    # is prose, not a unit line) and vocabulary-gated headings/headers
    # carry their own strictness, so they have no length gate.
    if _TABLE_UNITS_RE.match(ln) or _TABLE_WORD_UNITS_RE.match(ln):
        return True
    if _is_lede_table_heading(ln) or _is_lede_period_header(ln):
        return True
    # Batch 190: a compact period fragment ("4th Q 25" — AJG's
    # flattened summary-table column header) is table residue even
    # though it is no longer a data row (batch 190 exempts fragments
    # from _is_lede_data_row, which was the only branch catching it
    # here: period_header and table-cell both read False on it). A
    # whole line that is only the fragment is never prose.
    if _is_lede_compact_period_fragment(ln):
        return True
    if _is_lede_date_header(ln):
        return True
    if _is_lede_asof_date(ln):
        return True
    # A data row's wordy label plus 4-5 figures can run past 60 chars, so
    # it is exempt from the length gate below — its density rule (2+
    # figures, >=40% of tokens) is the guard that keeps wrapped prose out.
    if _is_lede_data_row(ln):
        return True
    # Batch 161: a reconciliation row is table residue too — its label
    # runs long and its values are sparse, so it reads as prose to the
    # density rules but is still a table row.
    if _is_lede_recon_row(ln):
        return True
    # Batch 181: a single-value table row (one $ figure — Emerson's
    # guidance table, American's cash-flow table) is residue too; the
    # data-row predicate needs 2 figures, so these leaked.
    if _is_lede_single_value_row(ln):
        return True
    if len(ln) > 60:
        return False
    words = ln.split()
    # A symbol legend line ("NM = not meaningful") is the table's own
    # footnote, not narrative — it sits below the table after the
    # numbered footnotes. Batch 160.
    if _LEDE_SYMBOL_LEGEND_RE.match(ln):
        return True
    # Short label lines — but never a $-carrying value line: "$50.2
    # billion" is a metric value the batch-100 rule keeps, not a label.
    if "$" not in ln:
        if len(words) <= 2:
            return True
        if len(words) <= 4 and "(" in ln:
            return True
    if _looks_like_table_cell(ln):
        return True
    if len(words) <= 6 and _LEDE_FOOTNOTE_TAIL_RE.search(ln):
        return True
    return False


def _is_lede_table_label(ln: str, next_ln: str) -> bool:
    """True for a table row's label line: figure-less and unterminated,
    directly above its values row. Some filers flatten a row as label
    on one line and values on the next (Allstate: "Property-Liability
    combined ratio" / "Recorded 96.4 103.4 (7.0) 96.9 109.8 (12.9)";
    "Return on Allstate common shareholders' equity (trailing twelve
    months)" / its 26.1 % row; "Total policies in force (in thousands)"
    / "205,483 190,089 8.1 %"), and the label alone matches no table
    predicate — it is too long for the short-label rule, or paren-less.
    Guards: terminated lines are prose; any figure means a data row or a
    prose fragment, not a label; bullets are content; and the next line
    must itself be a lede data row or a reconciliation row — a label with
    no values row below it is not a label, so a sub-headline above a
    prose paragraph never qualifies. A completed sentence inside the line
    is prose too:
    Coinbase wraps one sentence across lines ("majority of which were
    unrealized. These gains were" above the "$357 million and $514
    million after reflecting the tax" continuation), and without this
    guard the fragment reads as a label above a data row. Batch 160.
    Batch 161: a reconciliation row below the label counts as the values
    row (Sempra flattens some reconciliation labels onto their own line).
    """
    if _BULLET_LEAD_RE.match(ln) or _is_sentence_terminated(ln):
        return False
    if re.search(r"[.!?]\s", ln):
        return False
    if _LEDE_FIGURE_RE.search(ln):
        return False
    words = ln.split()
    if not words or len(words) > 12 or len(ln) > 120:
        return False
    return bool(next_ln) and (
        _is_lede_data_row(next_ln) or _is_lede_recon_row(next_ln)
    )


def _is_lede_flat_table_label_shape(ln: str) -> bool:
    """Shape-only half of _is_lede_flat_table_label: a flattened table
    row's label line — figure-less and unterminated, 2-12 words. The
    guards mirror _is_lede_table_label (terminated lines are prose; any
    figure means a data row or a prose fragment; bullets are content; a
    mid-line sentence boundary is prose), plus a quote-verb veto (a
    wrapped quote attribution — \"X, Chief Executive Officer, said,\" —
    is figure-less and unterminated too), a headline-verb veto (a
    sub-headline, never a row label) and an all-caps veto (same). A
    colon-ended line is a heading, not a label — the colon-heading skip
    upstream already handles it, and _is_sentence_terminated counts
    \":\" as a terminator. Batch 185.
    """
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if _is_sentence_terminated(s):
        return False
    if re.search(r"[.!?]\s", s):
        return False
    if _LEDE_FIGURE_RE.search(s):
        return False
    words = s.split()
    if not 2 <= len(words) <= 12 or len(s) > 120:
        return False
    if s.isupper():
        return False
    if _is_lede_table_header(s):
        return False  # a capital-led metric header is a header, not a
        # label — the loop's table-header skip handles it upstream.
    if _LEDE_HEADLINE_VERB_RE.search(s) or _LEDE_QUOTE_VERB_RE.search(s):
        return False
    return True


_LEDE_COMPACT_PERIOD_FRAGMENT_RE = re.compile(
    r"^(?:\d+(?:st|nd|rd|th)\s+Q|\d+\s+Mths?)\s+\d{2}(?:\d{2})?$",
    re.IGNORECASE,
)


def _is_lede_compact_period_fragment(ln: str) -> bool:
    """True for a compact flattened period fragment: AJG flattens its
    summary-table column headers one cell per line — "3rd Q 25",
    "9 Mths 25", "1st Q 26" (ordinal quarter or N months + a 2-digit
    year; 4-digit years in the later tables). The bare-period and
    period-header predicates never fire on these — "3rd"/"Q"/"25" are
    not period words and the year is 2 digits — so a label directly
    below one was not a flat table label (batch 185) and AJG's orphaned
    labels ("Net (gains) losses on divestitures", "Effective income
    tax rate impact") filled the lede budget in 10 quarters. A whole
    line that is only the fragment is never prose: the full-line match
    is the guard, and the cache survey attests the shape only in AJG
    (370 occurrences, all AJG). Batch 186.
    """
    return bool(_LEDE_COMPACT_PERIOD_FRAGMENT_RE.match(ln.strip()))


def _is_lede_flat_table_label(ln: str, prev_ln: str) -> bool:
    """True for a flattened table row's label line directly below a table
    header block. Brown & Brown flattens its reconciliation tables one
    cell per line, so a label (\"Diluted net income per share\",
    \"Change in estimated acquisition earn-out payables\") survives
    _drop_table_fragment_runs — its $-value rows drop as a fragment run,
    but the 5-6-word label is too long for the heading fold (4 words)
    and too lowercase-led for the table-header predicate — and the lede
    loop then collects it as its last budget lines (7 quarters). The
    label sits directly below the table's header block (date/period
    header, table header/title/heading, units line, recon heading,
    bare period fragment, or compact period fragment — batch 186:
    AJG's "3rd Q 25" / "9 Mths 25" column headers), which is what
    separates it from a wrapped
    prose fragment: prose follows prose, never a period header. The
    previous line must be a header-block line, not another label — a
    wrapped sub-headline (Apple's "Services revenue reaches new
    all-time high" below "June quarter records for Revenue and EPS",
    Estée Lauder's wrapped sub-headlines) looks exactly like a run of
    labels, so a label-shaped previous line never qualifies. The
    _is_lede_table_label next-line check cannot see these labels —
    their values rows were already dropped by the fragment-run dropper,
    so in lede_lines the next line is the next label, not a data row.
    Batch 185.
    """
    if not _is_lede_flat_table_label_shape(ln):
        return False
    prev = prev_ln.strip()
    if not prev:
        return False
    return (
        _is_lede_date_header(prev)
        or _is_lede_period_header(prev)
        or _is_lede_table_heading(prev)
        or _is_lede_table_header(prev)
        or _is_lede_table_title(prev)
        or bool(_TABLE_UNITS_RE.match(prev))
        or bool(_TABLE_WORD_UNITS_RE.match(prev))
        or _is_lede_recon_heading(prev)
        or _is_bare_period_fragment(prev)
        or _is_lede_compact_period_fragment(prev)
    )


def _is_lede_table_mode_residue(ln: str) -> bool:
    """True for a line inside a table region the lede loop is skipping
    past: anything that is not narrative prose. Once the loop has seen
    a flattened table label (batch 185), the lines that follow are
    table rows until real prose resumes — a terminated sentence, a
    bullet, or the boilerplate break — so an unterminated or
    colon-ended line is residue, however long (a wrapped balance-sheet
    row, a cash-flow label); a "Note:" line is a footnote even when
    terminated. Bullets and terminated prose are never residue: a
    quote or paragraph after the table (CSX) is still collected, which
    is why this is a skip-and-continue mode and not a break. Batch 185.
    """
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if re.match(r"note\s*:", s, re.IGNORECASE):
        return True
    stripped = s.rstrip().rstrip("”\"'’)]}")
    if stripped.endswith(":"):
        return True  # a colon-ended line is a heading, not prose
    if _is_sentence_terminated(s):
        # A company-name line ("Brown & Brown, Inc.") ends in a period
        # that is an abbreviation, not a sentence terminator — it is
        # residue, not the prose that ends table mode.
        last = stripped.rsplit(None, 1)[-1].lower().rstrip(".") if stripped else ""
        if last in {"inc", "corp", "ltd", "co", "llc", "plc", "lp", "llp"}:
            return True
        # A flattened multi-column table row joined with "respectively"
        # ("Treasury stock, at cost 20 shares at 2024, 20 shares at
        # 2023, respectively.") is terminated but is not prose — the
        # per-column values are the row, and collecting it leaks a
        # balance-sheet row into the highlights (BRO 2024-03-31, blast
        # 185). The year requirement keeps a plain narrative
        # "..., respectively." sentence (no year) collectible.
        if stripped.lower().endswith("respectively.") and re.search(
            r"\b(?:19|20)\d{2}\b", s
        ):
            return True
        return False
    return True


def _lede_wrapped_paragraph_head(run: list[str], ln: str) -> list[str]:
    """Return the wrapped head lines of the paragraph whose tail is ln,
    taken from the table-mode residue run — or [] when ln is not the
    tail of such a paragraph (batch 191).

    Arthur J. Gallagher's pretax paragraph sits inside the summary-table
    region: its wrapped head lines are unterminated, so the lede loop
    skips them as table-mode residue, and only the terminated tail is
    served — a dangling fragment ("income taxes is shown on pages 14
    and 15.") with no subject. The tail is a lowercase-led continuation
    of the skipped paragraph, so the whole paragraph can be served by
    prepending its head — budget-neutral, only the tail counts, so the
    CEO quote after the paragraph keeps exactly the budget it had.

    The naive alternative (treat lowercase-led terminated lines as
    residue in table mode) is NOT what this does: that would eat the
    CEO quote's own wrapped lines once the mode stays on past the
    paragraph (batch 186 note). This only ever ADDS lines, never
    removes, and only a coherent paragraph: the run is scanned back
    from its end — continuations are lowercase-led (a year wrap,
    "2024, the pretax impact ...", is the one digit-led continuation
    allowed) — and the first capital-led line is the head. The run
    usually opens with orphaned table labels ("Total Brokerage & Risk
    Management, as adjusted *", the batch-185/186 label chains), which
    the scan passes over because they sit before the head; a label can
    never BE the head, because the head must end mid-sentence (a wrap
    tail: trailing comma/dash or conjunction/preposition/article, per
    _LEDE_WRAP_TAIL_RE) while a label ends in "*" or ")" or a noun.
    A run with no capital-led head is a paragraph whose true head was
    consumed by another branch — no join. A colon-ended line, a "Note:"
    line, a company-name line or a "respectively." row anywhere in the
    scanned suffix blocks the join, because _is_sentence_terminated
    counts ":" as terminal and those lines are headings or table rows,
    not paragraph wraps.
    """
    tail = ln.strip()
    if len(tail) < 20 or not tail[0].islower():
        return []  # a capital-led tail starts a new paragraph
    if not _is_sentence_terminated(tail):
        return []
    if "“" in tail or "”" in tail or '"' in tail:
        return []  # a quote tail belongs to a quote, not this paragraph
    i = len(run) - 1
    while i >= 0:
        w = run[i].strip()
        if len(w) < 40 or _is_sentence_terminated(w):
            return []
        if "“" in w or "”" in w or '"' in w:
            return []
        if w[0].islower() or re.match(r"\d{4},", w):
            i -= 1
            continue
        break  # first capital-led line is the head candidate
    if i < 0:
        return []
    head = run[i].strip()
    if not head[0].isupper():
        return []
    if not _LEDE_WRAP_TAIL_RE.search(head):
        return []  # a label ends in "*" or ")" or a noun, never mid-sentence
    return run[i:]


def _is_lede_nongaap_section_heading(ln: str) -> bool:
    """True for a bare "Non-GAAP Financial Measures" section heading.
    The definitions prose under it is boilerplate, never highlights —
    a supplement packet (EOG) whose TOC and tables fill the lede would
    otherwise serve the definitions once table mode skips the tables.
    Only the bare heading qualifies (optional trailing colon): a
    sentence that merely mentions non-GAAP measures is prose. Batch 185.
    """
    return ln.strip().rstrip(":").strip().lower() == "non-gaap financial measures"


def _is_lede_table_tail_continuation(ln: str) -> bool:
    """True for a line inside a trailing table run: short, unterminated,
    and figure/marked/label-shaped. A wrapped prose fragment is longer
    than 2 words and carries no figure or marker, so it stops the walk."""
    if _BULLET_LEAD_RE.match(ln) or _is_sentence_terminated(ln):
        return False
    if len(ln) > 60:
        return False
    return (
        any(c.isdigit() for c in ln)
        or "$" in ln
        or "%" in ln
        or "(" in ln
        or len(ln.split()) <= 2
    )


def _is_bare_highlights_heading(ln: str) -> bool:
    """True for a dangling section heading at the lede tail ("Additional
    Financial Highlights:") — the heading whose bullets the budget never
    reached. A prose sentence that merely contains "highlights" is
    terminated with a period and never qualifies; a colon is a heading
    terminator, not a sentence one, so it does not disqualify."""
    if len(ln) > 120:
        return False
    s = ln.rstrip().rstrip("”\"'’)]}")
    if s.endswith((".", "!", "?", "…")):
        return False
    return bool(_HIGHLIGHTS_HEADING_RE.search(ln))


# A horizontal-rule line: a flattened <hr> or a row of underscores/dashes
# in the exhibit (Meta's releases carry a 36-underscore rule between the
# Highlights bullets and the footnote). It is never content. Batch 157.
_RULE_LINE_RE = re.compile(r"^(?:([_\-*=])\1{7,}|#+(\s+#+)*)$")
# Batch 182: the second alternative is a hash separator — Amex
# flattens its "###" end-of-release marker as the line "# # #",
# which was the tail of every Amex highlights block (5 quarters).
# A line of nothing but "#" (spaced or not) is a separator, never
# content; the final-assembly filter strips it for both paths.

# A table-intro sentence standing alone as a line ("The following table
# summarizes the key financial performance measures for the third quarter
# of 2026."): the table itself never follows in highlights, so as a
# trailing line it is a stub, not content. The ending may be a colon —
# Adobe's targets intro ends "targets:" and is still just the table's
# preamble. Must be a single sentence — Emerson's guidance paragraph
# opens with the same phrase and continues with real guidance prose in
# the same flattened line, and that line must never be dropped. Batch 157.
_TRAILING_TABLE_INTRO_RE = re.compile(
    r"^(?:the following table|the table below)\s+summarizes\b[^.!?]*[.:]$",
    re.IGNORECASE,
)

# Small words that may appear lowercase inside a heading ("First Quarter
# 2026 Financial Results" is all-capitals-led; "Recent Investment
# Activity" likewise). A trailing line is only a heading when every word
# is capitalized, all-caps, a number, or one of these — a lowercase-led
# wrapped prose fragment ("and other items") never qualifies. Batch 157.
_HEADING_SMALL_WORDS = frozenset(
    {"and", "or", "of", "the", "for", "to", "in", "on", "at", "a", "an", "&"}
)

# Section words a heading ends with ("CFO Outlook Commentary",
# "First Quarter 2026 Financial Results", "Financial Targets"). The
# end-word is the guard that keeps a truncated headline fragment out:
# "Goldman Sachs Reports Second Quarter Earnings Per Common" is
# heading-shaped (7 capitalized words, unterminated) but ends with
# "Common", so it is content, not a section label. Batch 157.
_HEADING_END_WORDS = frozenset(
    {
        "highlights",
        "results",
        "commentary",
        "targets",
        "summary",
        "overview",
        "update",
        "guidance",
        "outlook",
        "performance",
        "review",
        "measures",
        "financials",
        "earnings",
        "activity",
        "discussion",
    }
)


def _is_trailing_heading(ln: str) -> bool:
    """True for a heading-shaped line: short, unterminated, every word
    capitalized (or a number / small word), no figures or currency,
    ending with a section word, and never bullet- or dash-led (a quote
    attribution is not a heading)."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if s.endswith((".", "!", "?", "…")):
        return False
    if "$" in s or "%" in s:
        return False
    words = s.split()
    if not words or len(words) > 8:
        return False
    if words[-1].strip(",;:").lower() not in _HEADING_END_WORDS:
        return False
    for w in words:
        clean = w.strip(",;:")
        if not clean:
            return False
        if clean[0].isdigit():
            continue
        if clean in _HEADING_SMALL_WORDS:
            continue
        if clean[0].isupper():
            continue
        return False
    return True


_TRAILING_COMPANY_SUFFIXES = frozenset(
    {
        "inc.",
        "corp.",
        "corporation",
        "company",
        "ltd.",
        "co.",
        "llc",
        "group",
        "holdings",
        "n.v.",
        "s.a.",
    }
)


def _is_trailing_company_signature(ln: str) -> bool:
    """True for a bare company-name signature at the tail of a highlights
    body (batch 194): a short line of capitalized words ending in a
    corporate suffix ("CarMax, Inc." — the page-2 header of CarMax's
    release, pulled in when the "-more-" skip freed a section slot).
    A prose sentence ending in a suffix ("... approved by Apple Inc.")
    fails on its lowercase words; a quote attribution fails on length
    and on its lowercase words too. The trim only ever pops the last
    line, so a mid-text company name is untouched."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if "$" in s or "%" in s:
        return False
    words = s.split()
    if not words or len(words) > 6:
        return False
    if words[-1].strip(",;:").lower() not in _TRAILING_COMPANY_SUFFIXES:
        return False
    for w in words:
        clean = w.strip(",;:")
        if not clean:
            return False
        if clean[0].isdigit():
            continue
        if clean.lower() in _HEADING_SMALL_WORDS:
            continue
        if clean[0].isupper():
            continue
        return False
    return True


def _is_lede_title_line(ln: str) -> bool:
    """True for an exhibit title line served mid-lede ("Capital One
    Third Quarter 2024 Earnings" — Capital One, 7 stored rows: the
    freed lede budget reaches the exhibit's own title below the CEO
    quote). It is heading-shaped (short, capital-led, ending in a
    section word), so _is_trailing_heading matches it — but a
    sub-headline is heading-shaped too ("Q2 ORGANIC SALES AND ADJUSTED
    EPS EXCEED OUTLOOK", "COMPANY MAINTAINS FULL-YEAR REVENUE AND EPS
    GUIDANCE", "AMERICAN WATER REPORTS SOLID SECOND QUARTER RESULTS"),
    and the headline verb is what tells them apart: a title line never
    carries one, a sub-headline always does. The verb veto is
    load-bearing — without it the batch-177 keeps all drop. Batch 178.
    """
    return _is_trailing_heading(ln) and not _LEDE_HEADLINE_VERB_RE.search(ln)


def _is_lede_conf_call_heading(ln: str) -> bool:
    """True for a conference-call section heading in the lede
    ("Conference Call and Upcoming Events" — Emerson; "Webcast and
    Conference Calls" — AppLovin). It heads the boilerplate section
    (call notice, investor-conference notice, About, forward-looking
    statements), so it is never highlights — but the batch-178 budget
    freeing lets the lede loop reach it once the rows above it are
    skipped, and it consumes a budget line. Guards: short (2-8
    words), capital-led (small connector words allowed), unterminated,
    figure-free, no headline verb, and it must name the section
    ("conference call" / "upcoming events"). An announcement names
    the quarter or the results ("Company to Host Conference Call to
    Discuss Q3 Results") and is kept — a bare section heading never
    does. Batch 181."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if _is_sentence_terminated(s):
        return False
    if "$" in s or "%" in s:
        return False
    words = s.split()
    if not 2 <= len(words) <= 8:
        return False
    low = s.lower()
    if "conference call" not in low and "upcoming events" not in low:
        return False
    if re.search(r"\bq[1-4]\b", low) or "results" in low or "earnings" in low:
        return False
    if _LEDE_HEADLINE_VERB_RE.search(s):
        return False
    for w in words:
        clean = w.strip(",;:")
        if not clean:
            return False
        if clean[0].isdigit():
            continue
        if clean.lower() in _HEADING_SMALL_WORDS:
            continue
        if clean[0].isupper():
            continue
        return False
    return True


def _is_lede_recon_heading(ln: str) -> bool:
    """True for a reconciliation-table section heading in the lede
    ("GAAP/Adjusted (non-GAAP) Operating Earnings Reconciliation" —
    Constellation, 5 cache quarters; "Reconciliation of Commissions
    and Fees" — Brown & Brown, 7; "Reconciliation of GAAP to Non-GAAP
    Measures1" — CSX). It heads the reconciliation table, so it is
    never highlights — but the batch-178 budget freeing lets the loop
    reach it, and it consumes a budget line (and in the Highlights
    section path it is collected as content, with its boilerplate
    intro paragraph behind it). Guards: short (1-10 words),
    capital-led (small connector words allowed; a parenthesized
    qualifier like "(non-GAAP)" is transparent), unterminated,
    figure-free, no headline verb, and it must carry "reconcil".
    A sub-headline naming a reconciliation ("Company Provides
    Reconciliation of ...") is kept by the verb veto; a prose
    mention is terminated ("Please see a reconciliation ...") or
    lowercase-led, so neither qualifies. Batch 182. Batch 188:
    AJG's segment recon headings end with a units parenthetical
    and a colon ("Brokerage Segment Reported GAAP to Adjusted
    Non-GAAP Reconciliations (dollars in millions):",
    "Reconciliations (continued) (dollars in millions):") — the
    trailing parenthetical groups and colon are stripped before
    the guards, so the heading shape is judged on the heading
    itself; a bare "Reconciliations" is a heading too, so the
    floor is 1 word."""
    s = ln.strip()
    # Batch 188: strip trailing parenthetical groups and a colon —
    # a colon-ended recon heading is still a heading, and the units
    # parenthetical is not part of the heading shape.
    s = re.sub(r"(\s*\([^)]*\))+\s*:?$", "", s).strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if _is_sentence_terminated(s):
        return False
    if "$" in s or "%" in s:
        return False
    words = s.split()
    if not 1 <= len(words) <= 10:
        return False
    if "reconcil" not in s.lower():
        return False
    if _LEDE_HEADLINE_VERB_RE.search(s):
        return False
    for w in words:
        if w.startswith("("):
            continue  # parenthesized qualifier, e.g. "(non-GAAP)"
        clean = w.strip(",;:()\"'")
        if not clean:
            return False
        if clean[0].isdigit():
            continue
        if clean.lower() in _HEADING_SMALL_WORDS:
            continue
        if clean[0].isupper():
            continue
        return False
    return True


def _is_recon_heading_wrap(ln: str) -> bool:
    """True for the wrapped continuation of a reconciliation heading
    (Brown & Brown: "Reconciliation of Commissions and Fees" / "to
    Organic Revenue" — one heading split across two lines). Only
    consulted immediately after a skipped recon heading, so the
    position is the evidence: a short lowercase-led fragment there is
    the heading's wrap tail, never prose. Guards: short (1-6 words),
    unterminated, figure-free, no $/%, first word lowercase.
    Batch 182."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if _is_sentence_terminated(s):
        return False
    if "$" in s or "%" in s:
        return False
    if _LEDE_FIGURE_RE.search(s):
        return False
    words = s.split()
    if not 1 <= len(words) <= 6:
        return False
    return words[0][0].islower()


def _is_lede_segment_heading(ln: str) -> bool:
    """True for a business-segment section heading in the lede
    ("North America Automotive Parts Group (\"North America
    Automotive\")" — Genuine Parts, 2 cache quarters; the 4-word
    form "Automotive Parts Group (\"Automotive\")" is already caught
    by the table-line short-label rule, the 8-word form escapes it).
    The heading introduces the segment paragraph below it, which is
    real content — so the heading itself is skipped and the paragraph
    is kept, freeing the budget line the dangling heading consumed.
    Guards: ends with Group ("<alias>"), short (3-10 words),
    capital-led (small connector words allowed; the parenthesized
    alias words are heading words too), unterminated, figure-free.
    A prose line ending in a group name is terminated or
    lowercase-led, so it never qualifies. Batch 182."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if _is_sentence_terminated(s):
        return False
    if "$" in s or "%" in s:
        return False
    if not re.search(r"\bGroup\s*\(\"[^\"]+\"\)$", s):
        return False
    words = s.split()
    if not 3 <= len(words) <= 10:
        return False
    for w in words:
        if w.startswith("("):
            continue  # alias opener, e.g. '("North'
        clean = w.strip(",;:()\"'")
        if not clean:
            return False
        if clean[0].isdigit():
            continue
        if clean.lower() in _HEADING_SMALL_WORDS:
            continue
        if clean[0].isupper():
            continue
        return False
    return True


def _is_lede_call_announcement(ln: str) -> bool:
    """True for a conference-call announcement line that the batch-166
    notice regex misses (CSX, 6 quarters: "CSX executives will conduct
    a conference call with the investment community this afternoon,
    October 16, at 4:30 p.m. Eastern Time. Investors, media and the
    public may listen to the conference call by dialing 1-888-510-2008.
    ..."). The batch-166 regex needs "conference call" AND "webcast" /
    "replay" on one line; CSX splits the notice — the announcement
    line carries the call + time + dial-in but no webcast, and the
    webcast lives on the next line. Guards: a future-tense scheduling
    verb ("will conduct/host/hold") before "conference call", plus a
    time or dial-in detail — a prose mention ("on the conference call,
    management said ...") has neither, and a bare heading-shaped
    announcement ("Company to Host Conference Call to Discuss Q3
    Results") has no time/dial-in, so the conf-call-heading guard's
    kept announcements stay kept. Batch 182."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if not re.search(
        r"will (?:conduct|host|hold)\b[^.]*\bconference call\b",
        s,
        re.IGNORECASE,
    ):
        return False
    return bool(
        re.search(r"\d{1,2}:\d{2}\s*[ap]\.?m\.?|dial", s, re.IGNORECASE)
    )


def _is_lede_webcast_continuation(ln: str) -> bool:
    """True for the webcast second half of a split conference-call
    notice (CSX: "In conjunction with the call, a live webcast will
    be accessible and presentation materials will be posted ... .
    Following the earnings call, a webcast replay ... will be
    archived ..."). Only consulted immediately after a skipped call
    notice, so the position is the evidence: the line opens "In
    conjunction with the call" and carries "webcast" — a real prose
    sentence never opens that way right after a call announcement.
    Batch 182."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    return bool(
        re.match(
            r"in conjunction with the call\b.*\bwebcast\b",
            s,
            re.IGNORECASE,
        )
    )


def _is_lede_report_pointer(ln: str) -> bool:
    """True for a pointer sentence to where the full announcement
    lives (CSX, 12 cache quarters: "This earnings announcement, as
    well as additional detailed financial information, is contained
    in the CSX Quarterly Financial Report available through the
    company's website ... and on Form 8-K ..."; American Express, 12
    quarters: "This earnings release should be read in conjunction
    with the company's statistical tables ..."). It is a document-tail
    pointer, never highlights — but the freed lede budget reaches it
    once the notice above it drops, and it consumes a budget line.
    Guards: opens "This earnings announcement / press release /
    earnings release" and contains "is contained in" or "should be
    read in conjunction with", or opens "See information regarding"
    and contains "presented later in this press release" (Brown &
    Brown, 12 quarters: "See information regarding non-GAAP measures
    presented later in this press release."). A highlights sentence
    never opens either way. The opener is load-bearing: Charter's
    "The information in this press release should be read in
    conjunction with ..." is mid-paragraph boilerplate, not a
    line-opener, so it never qualifies. Batch 182."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    low = s.lower()
    if re.match(
        r"this (?:earnings announcement|press release|earnings release)\b",
        s,
        re.IGNORECASE,
    ):
        return (
            "is contained in" in low
            or "should be read in conjunction with" in low
        )
    if re.match(r"see information regarding\b", s, re.IGNORECASE):
        return "presented later in this press release" in low
    if re.match(r"see\b", s, re.IGNORECASE) and "beginning on page" in low:
        # Batch 188: AJG's recon-table pointer ("See "Information
        # Regarding Non-GAAP Measures" beginning on page 8 of 17.")
        # — a document-tail pointer, never highlights. The "See"
        # opener plus a page reference is load-bearing: a highlights
        # sentence never opens with "See" and points at a page.
        # Survey: 7 distinct lines, all AJG.
        return True
    if re.match(r"see attachment\b", s, re.IGNORECASE):
        # Batch 188: Con Edison's attachment pointer ("See Attachment
        # A to this press release for a reconciliation of ...") — the
        # same document-tail pointer class. Survey: 10 distinct
        # lines, all ED.
        return "to this press release for" in low
    if low.startswith(
        "percentage comparisons throughout this press release "
        "are calculated for"
    ):
        # Batch 188: Citigroup's methodology note ("Percentage
        # comparisons throughout this press release are calculated
        # for the first quarter 2026 versus the first quarter 2025,
        # unless otherwise specified.") — boilerplate, never
        # highlights. Survey: 11 distinct lines, all C.
        return True
    return False


def _is_lede_split_units_continuation(ln: str) -> bool:
    """True for the continuation of a split units declaration glued to
    table column labels (CSX: "except per share amounts Operating
    Income Operating Margin Net" — the second half of the "Dollars in
    millions," units line, flattened with the recon table's column
    headers). Guards: opens with "except per share (amounts|data)",
    unterminated, and carries a table metric word after the units
    phrase — a wrapped prose fragment starting "except ..." carries
    no metric word. Batch 182."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if _is_sentence_terminated(s):
        return False
    m = re.match(r"except per share (?:amounts|data)\b", s, re.IGNORECASE)
    if not m:
        return False
    return bool(_LEDE_TABLE_HEADER_METRIC_RE.search(s[m.end():]))


def _is_lede_footnote_attribution(ln: str) -> bool:
    """True for a table footnote glued onto a quote attribution (Visa,
    7 quarters: "% change is calculated over the comparable prior-year
    period. Q3 2024 Ryan McInerney, Chief Executive Officer, Visa,
    commented on the results:"). The footnote fragment is the summary
    table's own note, the period header is the table's column header,
    and the attribution without its quote is a dangling fragment — the
    glued line is table residue, not narrative. Both halves are required:
    a bare "% change is calculated ..." line is a footnote-definition
    block, and a bare attribution is a legitimate quote intro (the
    colon-heading veto protects "... said:" lines). Batch 180.
    """
    return bool(
        _LEDE_PCT_CHANGE_FOOTNOTE_RE.search(ln)
        and _LEDE_QUOTE_ATTRIBUTION_TAIL_RE.search(ln)
    )


def _clean_highlights_result(result: str) -> str:
    """Final cleanup of an assembled highlights body (batch 157).

    Drops horizontal-rule lines anywhere, and trims a trailing table
    stub — a lone table-intro sentence and/or a heading-shaped line at
    the very end (Meta's "CFO Outlook Commentary" with nothing after
    it; Moody's "First Quarter 2026 Financial Results" + intro
    sentence after the bullets). The headline is never trimmed: only
    lines after the first paragraph break are candidates. The trim is
    kept only when the result stays >=200 chars — below that the
    extractor would return None, and a wart is better than dropping
    the row (the batch-153 floor rule).
    """
    lines = [ln for ln in result.split("\n") if not _RULE_LINE_RE.match(ln.strip())]
    head_end = 0
    for i, ln in enumerate(lines):
        if not ln.strip():
            head_end = i
            break
    else:
        return "\n".join(lines).strip()
    body = lines[head_end:]
    trimmed = list(body)
    while trimmed:
        last = trimmed[-1].strip()
        if not last:
            trimmed.pop()
            continue
        if _TRAILING_TABLE_INTRO_RE.match(last):
            trimmed.pop()
            continue
        if _is_trailing_heading(last):
            trimmed.pop()
            continue
        if last == "-more-":
            # Batch 194: a page-continuation marker at the very tail
            # (a path that bypasses the lede/section loops, e.g. the
            # shareholder-letter or flat-table modes) is never content.
            trimmed.pop()
            continue
        if _is_trailing_company_signature(last):
            # Batch 194: a bare company-name signature at the very tail
            # (CarMax's "CarMax, Inc." page-2 header, pulled in when the
            # "-more-" skip freed a section slot) is page furniture.
            trimmed.pop()
            continue
        # Batch 178: a trailing bare units declaration (eBay's "in
        # millions, except per share data and percentages" — the next
        # section's table header, flattened without its parens) is
        # table residue, not a highlight. The lede loop's table-line
        # skip never sees it: a Highlights section serves its lines
        # directly, so the units fragment lands at the very end of the
        # assembled body and only this final trim can catch it.
        if _LEDE_BARE_UNITS_RE.match(last) or _LEDE_BARE_UNITS_LOWER_RE.match(last):
            trimmed.pop()
            continue
        break
    candidate = "\n".join(lines[:head_end] + trimmed).strip()
    if len(candidate) < 200:
        return "\n".join(lines).strip()
    return candidate


def _trim_lede_table_tail(lede: list[str]) -> list[str]:
    """Drop a trailing run of table residue from a collected lede.

    The lede-loop skip above catches table lines before collection, but a
    shape it misses still lands at the tail (a period-header orphan whose
    data rows were skipped, leaving the header behind). The run starts
    only at a strong table signal — the last line itself must be a lede
    table line — then walks backward through continuation lines and stops
    at the first bullet, terminated, or long line, so real prose is never
    eaten. A trailing bare highlights heading ("Additional Financial
    Highlights:") is dropped the same way: its bullets never arrived, so
    the heading dangles. The trim applies only when the remaining lede
    still holds >=200 chars; otherwise the original is kept, since a wart
    is better than dropping the row to None. Batch 153.
    """
    end = len(lede)
    if end == 0:
        return lede
    if _is_lede_table_line(lede[-1]):
        end -= 1
        while end > 0 and _is_lede_table_tail_continuation(lede[end - 1]):
            end -= 1
    trimmed = lede[:end]
    while (
        trimmed
        and _is_bare_highlights_heading(trimmed[-1])
        and len("\n\n".join(trimmed[:-1])) >= 200
    ):
        trimmed = trimmed[:-1]
    if trimmed and len("\n\n".join(trimmed)) >= 200:
        return trimmed
    return lede


def _is_lone_bullet_marker(ln: str) -> bool:
    """True for a line that is only a bullet glyph ("●", "•", "-", "*").

    Chubb's bullet lists flatten each marker onto its own line; a marker
    before any collected lede line carries no content — the bullet's text
    follows on the next lines — so it must not consume a lede slot. Mid-
    lede markers were kept as separators through batch 139, on the theory
    that they separate bullets in the rendered paragraphs. Batch 140
    drops that: paragraphs are already separated by blank lines, so a
    lone marker paragraph renders as a junk glyph line and adds no
    separation. Markers are now never stored — in either path — but they
    still delimit items for the lede finish rule (marker_seen), so the
    budget behavior is unchanged. Batch 138; batch 139 adds Chubb's other
    two flattened markers, the middle dot ("·", Q3 2024) and the white
    circle ("○", Q3 2024 sub-bullets) — both were counted as content
    lines, which is what starved the Q3 2024 lede. Batch 140 adds the
    last two glyphs the DB audit found standing alone: the black small
    square ("▪", PNC's lists) and the en dash ("–", Simon's lists) —
    the hyphen-minus was already covered, the en dash was not.
    Batch 185 adds the em dash ("—"): Brown & Brown's flattened
    tables leave lone "—" empty cells standing on their own lines,
    and _BULLET_LEAD_RE already treats "—" as a bullet marker — but
    without this entry the lone dash was collected as a content line
    (and cleared table mode), letting the next table's labels in.
    """
    return ln in ("●", "•", "·", "○", "▪", "-", "–", "—", "*")


# Table footnotes in the lede ("(a) Represents ...", "(1) During the year ...")
# are never narrative highlights. Distinct from _FOOTNOTE_LINE_RE (digits-only,
# used by the shareholder-letter table parser) — exhibits also letter their
# footnotes. Batch 97. Batch 101: no separator is required after the marker —
# EOG's supplement packet letters its endnotes "(B)Production volumes ..."
# with the marker running straight into the text, and the old [\s.] tail let
# that endnote boilerplate fill the lede and get stored as highlights.
_LEDE_FOOTNOTE_RE = re.compile(r"^\([a-z0-9]+\)", re.IGNORECASE)


def _is_paren_prose_continuation(ln: str) -> bool:
    """True when a paren-led line is a wrapped prose continuation, not a
    footnote definition. Batch 176: the paren shape is the loosest
    footnote marker — it also matches a parenthesized abbreviation
    that a wrapped sentence breaks on ("(MRC) protocol, and segment
    routing over IPv6 (SRv6) ..." — the tail of an Arista bullet;
    "(QoQ) and 46% year-over-year (YoY), driven by ..." — the tail
    of a Plug bullet; "(IV) KEYTRUDA. Merck also announced ..." — the
    tail of a Merck sentence, "(IV)" completing "intravenous (IV)").
    The section collector was dropping all three as footnote
    definitions, losing real prose. Two guards, both on the text after
    the marker — the previous line is deliberately NOT consulted:
    a genuine definition can follow an unterminated table row
    (Lilly's "(1) Tirzepatide is marketed ..." follows the revenue
    table's last row), so a prev-line test would keep real footnotes.
      - Lowercase lead: a definition is a sentence and starts
        capitalized; a continuation resumes mid-sentence, so its first
        word after the marker is lowercase ("protocol", "and").
      - Single-word first sentence with more text after it: "(IV)
        KEYTRUDA." is a bare term, not a definition — a definition
        needs a predicate — and the line then starts a new sentence
        ("Merck also announced ..."). The "more text" requirement is
        load-bearing: a bare figure fragment ("(210) (0.67)") has no
        sentence terminator at all, and a bare marker ("(1)") has no
        text after it, so neither fires — both stay footnote/table
        residue, as the CEG/CNC rows require.
    """
    m = _LEDE_FOOTNOTE_RE.match(ln)
    if not m:
        return False
    rest = ln[m.end():].strip()
    if not rest:
        return False
    if rest[0].islower():
        return True
    # A single alphabetic word (2+ letters) as the whole first
    # sentence, with a new sentence after it: "(IV) KEYTRUDA. Merck
    # also announced ..." — the marker's "definition" is a bare term,
    # not a definition, and the line is the tail of the previous
    # sentence ("... compared to intravenous (IV) KEYTRUDA."). The
    # 2+ letter, all-alpha bound is load-bearing: a decimal figure
    # ("(210) (0.67)") splits on its decimal point, and an
    # abbreviation ("U.S. ...") splits after one letter — neither
    # fires, so CEG's table fragments and real definitions stay
    # footnote residue. A bare marker ("(1)") has no text after it
    # and never reaches this test.
    if re.match(r"[A-Za-z]{2,}[.!?]\s+\S", rest):
        return True
    return False

# An investor-conference-call notice ("Today, beginning at 3:30 p.m.
# Central Time ... Emerson management will discuss the second quarter
# results during an investor conference call. Participants can access a
# live webcast ... A replay of the call will be available for 90 days.")
# is never highlights — it sits at the end of the release and backfills
# the lede once the footnotes below it are dropped (Emerson's quarters,
# batch 166). Both markers are required, and "call" is singular with a
# word boundary: a bare "conference call" mention inside real prose
# ("we discussed the quarter on the call") is not a notice, a
# "webcast"/"replay" mention without the call is not either, and a
# heading like AppLovin's "Webcast and Conference Calls" (plural) is
# not a notice either.
_CONFERENCE_CALL_NOTICE_RE = re.compile(
    r"conference call\b.*(webcast|replay)|(webcast|replay).*conference call\b",
    re.IGNORECASE,
)

# An investor-conference notice (Emerson: "Emerson will hold an
# in-person and virtual investor conference on Thursday, Nov. 20 in
# New York City. A live webcast of the investor conference will begin
# at 8:00 a.m. ..." and "Emerson also announces it will host an
# investor conference on Nov. 20, 2025 in New York City. Event
# details will be distributed closer to this date.") is the same
# class as the conference-call notice — an event announcement, never
# highlights — but it says "conference", not "conference call", so
# the batch-166 regex never fires on it and the freed lede budget
# serves it. Two shapes: "will hold/host an investor conference"
# (both attested lines), or an investor conference tied to a webcast
# in the same sentence. The "(?! call)" guard keeps a conference
# CALL notice on the batch-166 regex (it already skips those) and
# keeps "investor conference call" from matching this one. Batch 181.
_INVESTOR_CONFERENCE_NOTICE_RE = re.compile(
    r"\bwill\s+(?:hold|host)\b[^.]*?\binvestor conference\b(?! call)"
    r"|\binvestor conference\b(?! call)[^.]*?\bwebcast\b"
    r"|\bwebcast\b[^.]*?\binvestor conference\b(?! call)",
    re.IGNORECASE,
)

# A bare numbered footnote ("1) See Table A for information regarding
# non-GAAP financial measures.", "1) The three months ended June 30,
# 2025 are adjusted for M&A transaction costs of $1.4 million ...") —
# the table's footnote definitions without parentheses. Sempra numbers
# its reconciliation-table footnote "1)" and Datadog its M&A-costs
# footnote the same way; neither is narrative, and both sit inside the
# lede budget where the parenthesized rule never sees them. Batch 162.
_LEDE_FOOTNOTE_NUM_RE = re.compile(r"^\d{1,3}\)\s")

# A footnote-definition legend line is never a headline (batch 126): the
# marker is a single letter/digit in parentheses ("(B)Crude oil ..."). The
# single-character bound is load-bearing: "(NYSE: ACME)" and "(2026)"
# parentheticals are not footnote markers (the character after the first is
# not ")"), so exchange-prefixed and year-prefixed headlines are untouched.
_FOOTNOTE_HEADLINE_RE = re.compile(r"^\([A-Za-z0-9]\)")

# A table-of-contents entry: section title + trailing page number
# ("Income Statements 13"). Batch 126.
_TOC_ENTRY_RE = re.compile(r"^.+ \d{1,3}$")


# Footnote-definition legend lines (GEV's Workiva ex-99 opens with
# "1 Defined as remaining performance obligation (RPO)" /
# "*Non-GAAP Financial Measure" / "Page 1" before the real headline, and the
# numeric one was picked as the headline in batch 103's aftermath). Three
# shapes, all never headline or lede material. Batch 104.
#   - numeric key + definition verb: "1 Defined as ...", "2 Represents ...",
#     "1 Includes ...", "3 Excludes ..." — the verb is the guard that keeps a
#     numeric-opening headline from being swallowed ("2025 outlook raised"
#     can't match: 4-digit year; "1Q26 record quarter" can't match: no space
#     and no verb; "1 billion in buybacks" can't match: no verb).
#   - numeric key + defined term + copula + definition pointer: "1
#     Non-GAAP measures are detailed in the Supplemental Disclosures at
#     the end of this letter." (Skydance Q2 FY2026 — picked as the
#     headline, batch 164), "1 Adjusted EBITDA is defined as ...", "2
#     Free cash flow is calculated as ...". The participle list is
#     deliberately definition-pointer only: "are included / provided /
#     presented / discussed" stay OUT, because a wrapped bullet
#     continuation can legitimately read "1 million shares are included
#     in ..." — those verbs are prose, not footnote pointers. The
#     300-char line bound is load-bearing: the copula may sit anywhere
#     in the line, so an unbounded match would swallow a Workiva
#     page-flattened mega-line whole — SHOP Q3 2024's page 1 opens
#     "1 Internet, Everywhere ..." and contains "are reconciled ..." a
#     thousand chars in, and the unbounded form dropped the entire page
#     from the lede (killing the batch-163 salvage and serving the
#     outlook + balance sheet instead). A footnote definition is one
#     sentence, always far under 300 chars; a mega-line never is.
#   - glyph footnote markers attached to the text: "*Non-GAAP Financial
#     Measure", "†Excludes ...". The marker must sit at line start with the
#     text attached — a spaced "* Foo" or mid-line asterisk is prose
#     punctuation, not a legend (bullet "•" is a different char and is
#     unaffected).
#   - Batch 192: the hash marker "#", attached or spaced — Air Products
#     keys its per-share footnote "#" ("#Earnings per share is calculated
#     ...", "#Per share amounts are calculated ...", "# Per share amounts
#     are calculated ...") and Coinbase its variance legend ("# - Denotes
#     a variance of 100 percent or more."). Unlike "*", "#" never opens
#     a bullet or prose in these exhibits (the cache survey finds only
#     footnote definitions, legends, table fragments like DLR's "# of"
#     and decorations "###" / "# # #"), so the spaced form is safe here
#     where it is not for "*". A bare "###" separator opens a block of
#     length 1 in practice — the next line is a heading, never a
#     plausible wrap continuation.
_FOOTNOTE_DEF_RE = re.compile(
    r"^\d{1,3}\s+(defined as|represents|includes|excludes|reflects)\b"
    r"|^(?=.{0,300}$)\d{1,3}\s+\S.*\b(are|is)\s+(detailed|defined|described|calculated|reconciled|set forth)\b"
    r"|^[*†‡]\S"
    r"|^#\s*\S",
    re.IGNORECASE,
)

# A bracketed footnote marker ("[1] Adjusted EBITDA is a non-GAAP
# financial measure." — Coinbase's Q2 FY2025 letter serves its [1]/[2]
# footnotes as the lede). The paren form "(1) ..." is already a footnote
# by _LEDE_FOOTNOTE_RE; the bracket form is the same class. Batch 166.
_FOOTNOTE_BRACKET_RE = re.compile(r"^\[\d{1,3}\](?:\s|$)")

# A footnote-definition BLOCK (batch 166): the single-line shapes above
# only drop the key line, but a definition wraps ("3 Trading Volume
# represents the / total US dollar equivalent value of / ... / period of
# measurement.") and the wrapped continuation lines are served as lede /
# section / bullet-block content whenever a path reaches them. Coinbase's
# letters also carry a fourth shape the single-line regexes never match
# at all: a numeric key + bare capitalized term, the definition verb on
# the NEXT line ("1 Coinbase Total Trading Volume / comprises Spot Trading
# Volume / and Derivatives Trading Volume."), followed by chained
# bare-term definitions ("Spot Trading Volume is the total / U.S. dollar
# equivalent value of spot ..."). A sixth variant puts the verb on the
# key line after the term ("3 Trading Volume represents the", "4 Crypto
# Asset Volatility represents", "1 Spot Trading Volume is" — the last
# one is why shape 2 misses it: its participle is "presented", outside
# shape 2's list). _footnote_def_block_len returns how many lines the
# block starting at lines[i] occupies, or 0 when lines[i] opens no
# footnote definition; callers skip that many lines at every collection
# path (headline, lede, leading-bullet block, Highlights sections), so a
# footnote definition is never served, whole or in part.
#
# Consumption rules, each load-bearing:
#   - Only sentence termination ends a definition. There is deliberately
#     NO completeness gate: a wrapped line can look complete ("[3] $USD
#     resources is defined as cash and cash" carries a 5-word object,
#     yet the definition wraps onto "equivalents and USDC ..."). The
#     guard that matters is the next line's shape, not this line's.
#   - An unterminated line consumes its next line only when that line is
#     a plausible wrap continuation: lowercase-led, definition-verb-led,
#     conjunction-led, a "U.S."-style abbreviation lead, or a bare-term
#     definition opener. A headline-shaped next line ("Third Quarter
#     2025 Results") is never plausible, so GEV's single-line legend
#     never eats the headline that follows it. A figure-dense
#     continuation ("million and $687 million in pre-tax gains ...") is
#     lowercase-led, so it consumes — it must NOT be treated as a table
#     line, which is why the boundary below excludes table predicates.
#   - After a definition terminates, the block chains only onto another
#     definition opener (any key shape, or a bare capitalized term +
#     copula/definition verb, no digits). Real prose after the block
#     ("2025 was a strong year ...") ends the chain.
#   - Hard boundaries (bullets, boilerplate, admin/contact lines,
#     headings, datelines) never continue a definition, even an
#     unfinished one.
# Known limitations (attested in Coinbase's Q4 FY2024 / Q4 FY2025
# letters, no path serves these lines today): a definition whose TERM
# wraps ("4 Coinbase Crypto Trading Volume / Market Share is defined as
# / Coinbase Total Crypto Trading / Volume divided by Total Crypto ...")
# never opens a block — its verb sits on the second line, not leading
# it, so the chain stops at the previous definition's termination and
# the whole wrapped-term definition is left; a definition's second
# sentence is consumed only when it is anaphoric with an exact noun
# match ("These losses were ..." — batch 168), so a second sentence
# whose noun differs in number ("Both measurements represent ..." vs
# the definition's "period of measurement") is still left — and no path
# serves that line today; and a mixed-case term ("2 Total transaction
# revenue / generated from trading on our / platform.") never opens a
# block, because the term test needs Title-Case words. A wrapped-term
# chain rule and a plural-tolerant anaphora test are separate designs.
_FOOTNOTE_TERM_KEY_RE = re.compile(
    r"^\d{1,3}\s+(?:[A-Z][a-z]+|[A-Z]{2,})"
    r"(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,})){1,5}$"
)
# Same-line term+verb variant (batch 166): "3 Trading Volume
# represents the", "4 Crypto Asset Volatility represents", "1 Spot
# Trading Volume is". A bare "is"/"are" counts only at line end or
# before a definition participle (including "presented", the attested
# one shape 2 excludes) — "1 Total Revenue is expected to grow" never
# opens a block, because "expected" is prose, not a definition pointer.
# The anchored term (1-5 Title-Case words right after the key) is what
# keeps shape 2's "1 million shares are included in ..." hazard out:
# "million" is lowercase, so the term never matches. The term's first
# word must be Title-Case, but later words may be lowercase (Emerson's
# "2 Underlying orders do not include AspenTech.", "2 Underlying sales
# excludes the impact ...") — the verb right after the term is the
# guard, and an optional "do not / does not" precedes it. A digit in
# the term still blocks ("1 Fourth Quarter 2025 Results are presented"
# never opens: "2025" breaks the term).
_FOOTNOTE_TERM_VERB_RE = re.compile(
    r"^\d{1,3}\s+(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+[A-Za-z]+){0,4}\s+"
    r"(?:(?:do not|does not)\s+)?"
    r"(?:(?:defined as|represents?|includes?|excludes?|reflects|comprises"
    r"|consists of|means|refers to)\b"
    r"|(?:is|are)(?:\s+(?:defined|described|calculated|reconciled"
    r"|set forth|detailed|presented)\b|\s*$))",
    re.IGNORECASE,
)
_FOOTNOTE_DEF_VERB_LEAD_RE = re.compile(
    r"^(comprises|represents|includes|excludes|reflects|consists of"
    r"|means|refers to|is defined as|are defined as|defined as)\b",
    re.IGNORECASE,
)
_FOOTNOTE_BARE_TERM_RE = re.compile(
    r"^(?:[A-Z][a-z]+|[A-Z]{2,})(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,})){1,4}"
    r"\s+(is|are|represents|comprises|includes|excludes|means|refers to"
    r"|defined as)\b"
)
# The fourth shape collapsed onto one sentence (page-flattened decks):
# "1 Coinbase Total Trading Volume comprises Spot Trading Volume and
# Derivatives Trading Volume." Used by the salvage path, which sees
# sentences, not lines. Batch 166.
_FOOTNOTE_DEF_SENTENCE_RE = re.compile(
    r"^\d{1,3}\s+(?:[A-Z][a-z]+|[A-Z]{2,})"
    r"(?:\s+(?:[A-Z][a-z]+|[A-Z]{2,})){1,5}\s+"
    r"(comprises|represents|includes|excludes|reflects|is|are|defined as"
    r"|means|refers to)\b",
    re.IGNORECASE,
)


# A footnote-pointer opener (batch 173): a bare-numbered cross-reference
# ("1 See additional information at the end of the release ...",
# "1 Refer to the tables at the end of this press release ...",
# "2 See the Non-GAAP Measures section ...") — Walmart, CSX, Carnival
# and PACCAR serve these as lede content today (13 stored rows). The
# See/Refer-to verb is the anchor: prose never opens with a bare number
# + See/Refer to. The optional period covers "1. See ...". The
# parenthesized alternative covers Carnival's tail pointer ("(See
# \u201cNon-GAAP Financial Measures\u201d and \u201cReconciliation of
# Forecasted Data\u201d)") — a cross-reference wrapped in parens, never
# narrative. Batch 173.
_FOOTNOTE_POINTER_RE = re.compile(
    # Batch 182: the number may be GLUED to its word ("1See the
    # Non-GAAP Measures section ..." — CSX's recon-table footnote,
    # flattened without the space; Aflac's "1Refer to previously
    # defined ..." is the same shape, terminated). The batch-178
    # glued-number precedent: a digit glued to "See"/"Refer to" is a
    # pointer by construction — no prose opens that way — so the space
    # is optional. The verb is the guard, as before.
    r"^(?:\d{1,3}[.)]?\s*|\(+)(See|Refer to)\b",
    re.IGNORECASE,
)


def _is_bare_numbered_footnote(ln: str) -> bool:
    """True for a bare-numbered footnote sentence ("2 Comp sales for the
    13-week period ...", "3 Source: Rystad Energy ...", "1 Net debt is
    total debt of $39.0 billion ...", "1 As used in this release ...").

    Guards, each load-bearing:
      - Terminated sentence: a wrapped bullet continuation ("12 of them
        in Texas") is unterminated, so it never opens — the termination
        test is what keeps wrapped prose out.
      - 1000-char cap: a footnote definition is one or two short
        sentences — attested bare-numbered footnotes run to 984 chars
        (Comcast's pro-forma footnote; Emerson's 699-char Copeland
        discontinued-operations footnote, Moody's 556-char
        medium-term-EPS disclaimer, Amex's 671-char FX-adjusted
        footnote). Batch 181 raised the cap from 500: the 500–1000
        band is footnotes throughout (~190 attested lines, every one
        sampled a definition), and the one non-footnote sampled is
        Affirm's 913-char page-flattened chart title, which is
        harmless to skip. Above 1000 the population is dominated by
        page/table mega-lines (Affirm's shareholder-letter lines,
        Ford's 3000-char flattened highlights table, BofA's
        balance-sheet table) with only a few real footnotes
        interspersed (Nike's 1071-char segment footnote, Ford's
        1179-char guidance footnote), so the cap stays at 1000 and
        those longer ones survive as tails. Page/table mega-lines
        start with a bare number too and are far longer — the cap
        keeps them out, and the Affirm lines are unterminated besides,
        so the termination test excludes them.
      - Capital after the number: a footnote sentence starts capitalized
        ("1 Net debt is ...", "2 Comp sales ...", "3 Source: ..."). A
        wrapped bullet continuation starts with a lowercase quantity
        word ("1 million shares are included in the diluted count." —
        batch 164's mirror negative), and a bullet with a footnote key
        ("2 • Strategic acquisition ...") starts with a marker, not a
        capital — both stay continuations, not footnotes.
      - Batch 199: the number may carry a period ("1. Adjustment item
        resides in the Corporate & Other reportable segment." — the
        batch-198 carry-forward shape; "1.Assumes $2.10 billion ..." —
        First Solar's 2026 footnote defs, flattened without the space).
        The period is optional and the capital-after-number guard is
        unchanged, so a decimal-led figure ("1.5 million shares ...",
        "1.25 billion ...") still never opens — the char after the
        period is a digit, not a capital.
    """
    if len(ln) > 1000 or not _is_sentence_terminated(ln):
        return False
    return bool(re.match(r"^\d{1,3}\.?(?:\s+[A-Z]|(?=[A-Z][a-z]))", ln))


def _is_bare_term_def_opener(ln: str) -> bool:
    """True for a bare capitalized-term definition opener ("Spot Trading
    Volume is the total", "Derivatives Trading Volume is the").

    No digits: a figure line ("Total Revenue is expected to grow 10%")
    is prose, not a definition. The 80-char bound keeps a wrapped prose
    sentence that happens to start "Term is ..." out — a definition
    opener is one short term + verb, never a full clause.
    """
    if len(ln) > 80 or any(ch.isdigit() for ch in ln):
        return False
    return bool(_FOOTNOTE_BARE_TERM_RE.match(ln))


def _opens_footnote_def(ln: str, nxt: str = "", include_paren: bool = True) -> bool:
    """True when ln opens a footnote-definition block.

    Any single-line shape (_FOOTNOTE_DEF_RE, bare numbered, paren,
    bracketed), a footnote pointer ("1 See ...", "1 Refer to ..." —
    batch 173), a bare-numbered footnote sentence (batch 173), or the
    fourth shape: a numeric key + bare capitalized term whose NEXT line
    starts with a definition verb ("1 Coinbase Total Trading Volume" /
    "comprises Spot Trading Volume"). The verb-on-next-line requirement
    is the guard that keeps a numbered heading ("1 Fourth Quarter
    Highlights") from opening a block.
    include_paren=False for the headline loop: a paren line ("(B)Crude
    oil ...", "(2026) ACME CORP REPORTS ...") stays headline-eligible
    there — batch 126 returns None for a supplement packet whose best
    headline is a footnote definition, and preserves year-prefixed
    headlines — so the headline loop must not skip paren lines.
    Batch 176: a paren line that is a wrapped prose continuation
    ("(MRC) protocol ...", "(QoQ) and ...", "(IV) KEYTRUDA. Merck
    ...") is not a footnote definition — see
    _is_paren_prose_continuation.
    """
    if (
        _FOOTNOTE_DEF_RE.match(ln)
        or _LEDE_FOOTNOTE_NUM_RE.match(ln)
        or (
            include_paren
            and _LEDE_FOOTNOTE_RE.match(ln)
            and not _is_paren_prose_continuation(ln)
        )
        or _FOOTNOTE_BRACKET_RE.match(ln)
        or _FOOTNOTE_TERM_VERB_RE.match(ln)
        or _FOOTNOTE_POINTER_RE.match(ln)
        or _is_bare_numbered_footnote(ln)
    ):
        return True
    return bool(
        _FOOTNOTE_TERM_KEY_RE.match(ln)
        and nxt
        and _FOOTNOTE_DEF_VERB_LEAD_RE.match(nxt)
    )


def _is_block_boundary(ln: str) -> bool:
    """True for a line that never continues a footnote definition, even
    an unfinished one: bullets, boilerplate, admin/contact lines,
    headings, datelines. Deliberately NOT table predicates: a wrapped
    footnote continuation routinely carries figures ("million and $687
    million in pre-tax gains ...", "$1.5 billion in pre-tax gains on")
    and scores as a table line — treating it as a boundary stops the
    block at the key line and serves the continuations. Table lines
    are already excluded by the plausibility test (they do not start
    lowercase, with a definition verb, or with a conjunction), and a
    lowercase-led table fragment consumed here is residue the lede
    would skip anyway."""
    return bool(
        _is_inline_bullet_start(ln)
        or _is_lone_bullet_marker(ln)
        or _BOILERPLATE_RE.match(ln)
        or _ADMIN_LINE_RE.match(ln)
        or _CONTACT_HEADER_RE.match(ln)
        or _CONTACT_LINE_RE.search(ln)
        or (_HIGHLIGHTS_HEADING_RE.search(ln) and len(ln) <= 120)
        or (ln.isupper() and len(ln) <= 80)
        or _DATELINE_LEAD_RE.match(ln)
    )


def _is_plausible_continuation(ln: str) -> bool:
    """True when ln could be the wrapped continuation of an unterminated
    footnote definition: lowercase-led (wrapped prose), definition-verb
    led, conjunction-led, a "U.S."-style abbreviation lead, a "$"-led
    or digit-led figure line, or a bare-term definition opener.
    Anything else — in particular a headline-shaped line — ends the
    definition. A digit-led line is implausible when it opens a
    year-led sentence ("2025 was a strong year ..."): a new sentence
    never continues a definition. A "$"-led line is always a figure
    continuation ("$357 million and $514 million after reflecting the
    tax") — a new sentence starting with "$" does not follow an
    unterminated definition line."""
    if not ln:
        return False
    if ln[0].islower():
        return True
    if _FOOTNOTE_DEF_VERB_LEAD_RE.match(ln):
        return True
    if re.match(r"^(and|or|but)\b", ln, re.IGNORECASE):
        return True
    if re.match(r"^[A-Z]{1,2}\.", ln):
        return True
    if (
        re.match(r"^[A-Z]{2,3}\s+[a-z]", ln)
        and not _is_sentence_terminated(ln)
        and not any(ch.isdigit() for ch in ln)
    ):
        # All-caps abbreviation lead without the periods ("US dollar
        # equivalent value of ...", the Q1 FY2025 [4] AUC definition):
        # a wrapped definition's first words, not a new sentence — a
        # year-led or figure-led prose sentence either terminates or
        # carries digits, so the two guards keep those out.
        return True
    if (
        re.match(r"^[A-Z]{2,}\s*\([a-z]", ln)
        and not any(ch.isdigit() for ch in ln)
    ):
        # All-caps abbreviation lead opening a lowercase parenthetical
        # ("USDC (net of USDC lent or", the Q3 FY2024 [3] definition's
        # wrap tail — batch 168): the 4-cap lead fails the 2-3-cap
        # branch above, but a lowercase parenthetical after an
        # abbreviation is a definition tail, never new prose. Unlike
        # that branch the termination guard is dropped: a tail that
        # happens to terminate on its own line ("USDC (net of USDC lent
        # or pledged as collateral).") is still the same definition's
        # tail. The no-digits guard keeps figure-led prose out, and the
        # line is only ever reached as the wrap of an unterminated
        # definition.
        return True
    if ln[0] == "$":
        return True
    if ln[0].isdigit() and not re.match(r"^\d{4}\s+[a-z]", ln):
        return True
    return _is_bare_term_def_opener(ln)


# A definition's second sentence (batch 168): Coinbase's Q3 FY2024 [1]
# footnote is two sentences, and the flattening puts the break on a line
# boundary — "majority of which were unrealized." / "These losses were
# $92 million / after reflecting the tax impact." The block stops at the
# first sentence's termination and the second sentence is served as lede.
# (Q4 FY2024's identical shape escapes only because its second sentence
# starts mid-line, "These gains were" sharing the termination line.) A
# capital-led sentence after a terminated definition is otherwise
# indistinguishable from new prose, so the guard is anaphora: the line
# must open with an anaphoric determiner (These/This/Those/That/Both/
# Such) whose noun appears in the definition just consumed — "These
# losses" (losses in the [1] definition). Real prose after the legend
# ("2025 was a strong year ...", "We delivered ...") never opens that
# way, and the noun test is exact, not stemmed ("measures" != "measure"),
# so the Q4 FY2025 "Both measurements represent ..." shape stays
# uncovered (its definition says "period of measurement").
_ANAPHORA_LEAD_RE = re.compile(r"^(These|This|Those|That|Both|Such)\s+([A-Za-z]+)")


def _def_words(ln: str) -> set[str]:
    """Lowercase alpha words of a definition line, for the anaphora test."""
    return set(re.findall(r"[A-Za-z]+", ln.lower()))


def _is_def_second_sentence(ln: str, def_words: set[str]) -> bool:
    """True when ln is the second sentence of the just-terminated
    footnote definition (see _ANAPHORA_LEAD_RE)."""
    if _is_block_boundary(ln):
        return False
    m = _ANAPHORA_LEAD_RE.match(ln)
    if not m:
        return False
    return m.group(2).lower() in def_words


def _footnote_def_block_len(
    lines: list[str], i: int, include_paren: bool = True
) -> int:
    """Length of the footnote-definition block starting at lines[i], or 0.

    Consumes the key line, its wrapped continuations (while the
    definition is unfinished and the next line is a plausible wrap),
    and any chained definitions that follow a terminated/complete one.
    Capped at 60 lines: a real footnote block is far shorter, and the
    cap bounds any misfire to one block instead of the document.
    include_paren=False for the headline loop (see _opens_footnote_def).
    """
    if i >= len(lines) or not _opens_footnote_def(
        lines[i], lines[i + 1] if i + 1 < len(lines) else "", include_paren
    ):
        return 0
    n = 1
    cur = lines[i]
    def_words = _def_words(cur)
    while n < 60:
        nxt = lines[i + n] if i + n < len(lines) else None
        if nxt is None:
            break
        if _is_sentence_terminated(cur):
            # Definition finished — chain only onto another definition,
            # or onto its own anaphoric second sentence ("These losses
            # were $92 million ..." — batch 168).
            if _opens_footnote_def(
                nxt,
                lines[i + n + 1] if i + n + 1 < len(lines) else "",
                include_paren,
            ) or _is_bare_term_def_opener(nxt):
                n += 1
                cur = nxt
                def_words = _def_words(nxt)
                continue
            if _is_def_second_sentence(nxt, def_words):
                n += 1
                cur = nxt
                def_words |= _def_words(nxt)
                continue
            break
        # Unfinished — the next line continues unless it is a hard
        # boundary or an implausible wrap. No completeness gate: a
        # wrapped line can look complete ("[3] $USD resources is
        # defined as cash and cash" has a 5-word object, yet the
        # definition wraps onto "equivalents and USDC ..."), and the
        # plausibility test is the guard that matters — a headline-
        # shaped next line ("Third Quarter 2025 Results") is never a
        # plausible wrap, so GEV's single-line legend never eats the
        # headline that follows it. Batch 178: a blank line or a bare
        # page number inside a wrapped definition is a flattening
        # artifact (Ares Capital's (7) yields footnote wraps across a
        # page break: "... plus the net annual" / "2" / "" / "securities
        # at amortized cost ..." — the "2" is a page number, an admin
        # line and therefore a boundary by _is_block_boundary, which
        # orphans the continuation as lede content) — consume it and
        # keep looking for the continuation. The plausibility test on
        # the line after the artifact still guards the boundary: a new
        # prose paragraph after the blank is capital-led and
        # implausible, so the block still ends there. A lone bare
        # number is never a footnote key (a key always carries its term
        # on the same line), so skipping it loses no definition.
        if not nxt.strip() or re.fullmatch(r"\d{1,3}", nxt.strip()):
            n += 1
            continue
        if _is_block_boundary(nxt) or not _is_plausible_continuation(nxt):
            break
        n += 1
        cur = nxt
        def_words |= _def_words(nxt)
    return n


# Batch 188: the adjustment-item glossary that follows the recon tables
# in some releases — a run of "Term - definition" lines, e.g. AJG's
# "Interest, banking costs and debt - At March 31, 2026, Gallagher had
# $9,550 million of borrowings ..." / "Clean energy-related - For 2026,
# this consists of ..." / "Acquisition costs - Consists mostly of ..."
# (8 consecutive lines in AJG 2026 Q1/Q2), EFX's "Legal settlement - ... /
# Antitrust litigation costs - ... / Adjusted EBITDA and EBITDA margin -
# Management defines ...". Cache survey (1,699 exhibits): only 4 runs of
# >=3 such lines exist, and all 4 are glossaries. A lone "Term -
# sentence" line is never a glossary — datelines ("COLUMBUS, Ohio, July
# 30, 2025 - American Electric Power ... today reported ...") share the
# shape, so the term must carry no digits and no month name, and only a
# run of 3+ counts. Bulleted definitions ("•Net gains (losses) on
# divestitures, which are ...") are excluded: they live under the
# "Information Regarding Non-GAAP Measures" heading, past the "About"
# break, and never reach the lede loop.
_GLOSSARY_TERM_RE = re.compile(r"^([A-Z][A-Za-z, '&()/-]{0,60}) - ([A-Z].*)$")
_GLOSSARY_TERM_MONTH_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\b"
)


def _is_glossary_def_line(ln: str) -> bool:
    """One line of a definition glossary: "Term - definition sentence."

    Term is a short (<=6 words) digit-free phrase; the definition is a
    terminated sentence starting with a capital letter.
    """
    if ln[:1] in "•▪■·○◦◾":
        return False
    m = _GLOSSARY_TERM_RE.match(ln)
    if not m:
        return False
    term = m.group(1)
    if not 1 <= len(term.split()) <= 6:
        return False
    if re.search(r"\d", term) or _GLOSSARY_TERM_MONTH_RE.search(term):
        return False
    # A definition never opens with a bare month name — that is a
    # dateline whose location split off as the term ("Bethesda, MD -
    # April 20, 2026 - AGNC ... today announced ...").
    if _GLOSSARY_TERM_MONTH_RE.match(m.group(2)):
        return False
    return _is_sentence_terminated(ln)


def _glossary_def_block_len(lines: list[str], i: int) -> int:
    """Length of a glossary-definition block starting at lines[i], or 0.

    Counts consecutive glossary lines; returns 0 unless the run is >=3.
    """
    n = 0
    while i + n < len(lines) and _is_glossary_def_line(lines[i + n]):
        n += 1
    return n if n >= 3 else 0


# A rounding note (batch 167): Coinbase's shareholder letters carry a
# rounding boilerplate paragraph ahead of the letter prose — the long form
# ("Figures have been rounded for presentation purposes only. For
# additional financial information and a reconciliation between GAAP and
# non-GAAP results, please refer to the reconciliation of GAAP to
# Non-GAAP results table(s) in this shareholder letter and our Form
# 10-K/10-Q filed with the SEC on <date>.") and the short form ("Note:
# Figures presented [above] may not sum precisely due to rounding.").
# Either form fills the lede when nothing else precedes the prose (Q4
# FY2024's whole stored body is the long form), and the long form's first
# line becomes the headline when the quarter title is skipped (Q1/Q2
# FY2025). A rounding note is boilerplate, never highlights. The short
# form's "may not" alternative covers the wrapped shape ("Note: Figures
# presented may not / sum precisely due to rounding."). The "For
# additional financial information" alternative covers the long form's
# second sentence standing alone: Q3 FY2024 carries the short note plus
# the referral sentence, with no long-form first sentence — without it
# the referral paragraph is served as lede content.
_ROUNDING_NOTE_RE = re.compile(
    r"^Figures have been rounded for presentation purposes\b"
    r"|^Note:\s*Figures presented (above\s+)?may not\b"
    r"|^For additional financial information\b",
    re.IGNORECASE,
)

# The rounding note's second sentence (batch 167): the long form is two
# sentences, and the flattening may put the break on a line boundary
# ("Figures have been rounded for presentation purposes only." / "For
# additional financial information and a ..."). A following line with
# this lead is the same note's continuation, never new prose.
_ROUNDING_NOTE_CHAIN_RE = re.compile(
    r"^For additional financial information\b", re.IGNORECASE
)

# A spaced-glyph asterisk note (batch 167): Coinbase's letters annotate
# charts with "*"-led notes — "* Based on the closing price of Coinbase's
# Class A common stock on May 7, 2025 on the Nasdaq Global Stock Market.",
# "*Below reporting threshold of 10%.", "*Net of USDC loaned or pledged as
# collateral.", "*As of December 31, 2024, USDC excludes ...", "* Measures
# used in this release ...". The lede's table-line rule already drops the
# opener, but its wrapped continuations are served ("Coinbase's Class A
# common stock" opens Q1 FY2025's lede once the rounding note is skipped),
# and in the leading-bullet block the opener starts a bullet item. The
# lead list is deliberately note-shaped: a highlights bullet never opens
# with "Based on" / "As of" / "Net of" / "Below" / "Measures used" — and
# the batch-165 "* Revenue grew 12 percent." bullet stays a bullet.
# Batch 192 adds "Certain results": Air Products' non-GAAP legend —
# "* Certain results in this release include references to non-GAAP
# financial measures ..." (spaced form, Q2 FY2026) and "*Certain results
# in this release, including in the highlights above, include references
# ..." (attached form, Q1 FY2025) — served as section content in Q2
# FY2026 because the asterisk-note block is the one path that drops
# spaced-"*" notes and its lead list never covered this opener. The
# "\s*" already covers both forms.
# Known limitation: the "During" form ("*During the first quarter of 2024,
# we revised our definition of ...") and the quoted-term form ("*‘Major’
# stablecoins include ...") are not covered — neither is served by any
# path today.
_ASTERISK_NOTE_LEAD_RE = re.compile(
    r"^\*\s*(Based on|As of|Net of|Below|Measures used|Certain results)\b",
    re.IGNORECASE,
)


def _wrapped_note_block_len(
    lines: list[str], i: int, opener_re, chain_re=None, cap: int = 10
) -> int:
    """Length of the boilerplate-note block starting at lines[i], or 0.

    A note is one paragraph, possibly wrapped: consume lines until the
    current sentence terminates, taking any non-boundary line as a
    continuation — unlike the footnote block, a note's wraps are ordinary
    sentence fragments ("GAAP results table in this shareholder letter
    and our", "Coinbase's Class A common stock", "Form 10-Q filed with
    the SEC on May 8, 2025."), so the footnote block's plausibility test
    (lowercase-led / verb-led / bare-term) would stop the block mid-note
    and serve the rest. The opener is the guard instead: both regexes
    match boilerplate only, never narrative prose. After termination the
    block chains only onto chain_re (the rounding note's second sentence);
    a following note is its own opener, handled by the caller's per-line
    check. Capped at 10 lines: the attested long form is 6, the asterisk
    note 4, the Allstate legend 3 — a misfire can never eat the letter.
    """
    if i >= len(lines) or not opener_re.match(lines[i]):
        return 0
    n = 1
    cur = lines[i]
    while n < cap:
        nxt = lines[i + n] if i + n < len(lines) else None
        if nxt is None:
            break
        if _is_sentence_terminated(cur):
            # Sentence finished — chain only onto the note's second
            # sentence (rounding note); anything else ends the block.
            if chain_re is not None and chain_re.match(nxt):
                n += 1
                cur = nxt
                continue
            break
        if _is_block_boundary(nxt):
            break
        n += 1
        cur = nxt
    return n


def _rounding_note_block_len(lines: list[str], i: int) -> int:
    """Length of the rounding-note block starting at lines[i], or 0.

    The long form ("Figures have been rounded for presentation purposes
    only. For additional financial information ... Form 10-Q filed with
    the SEC on May 8, 2025.") is 6 wrapped lines; the short form ("Note:
    Figures presented may not / sum precisely due to rounding.") is 2,
    or 1 unwrapped. The chain rule covers the sentence break falling on
    a line boundary.
    """
    return _wrapped_note_block_len(
        lines, i, _ROUNDING_NOTE_RE, chain_re=_ROUNDING_NOTE_CHAIN_RE
    )


def _asterisk_note_block_len(lines: list[str], i: int) -> int:
    """Length of the asterisk-note block starting at lines[i], or 0.

    One sentence, possibly wrapped ("* Based on the closing price of /
    Coinbase's Class A common stock / on May 7, 2025 on the Nasdaq /
    Global Stock Market." is 4 lines); the single-line forms ("*Below
    reporting threshold of 10%.") are 1. No chaining: each note stands
    alone.
    """
    return _wrapped_note_block_len(lines, i, _ASTERISK_NOTE_LEAD_RE)


# A shareholder-letter salutation (batch 169): letters open "Fellow
# shareholders," / "Dear Shareholders," after the date — a greeting,
# never highlights. It is served three ways today: as the HEADLINE
# (NFLX — the headline loop picks the first short line it reaches, so
# the salutation becomes the headline); as lede content (COIN's Q3
# FY2025 letter, SKYD); and as a leading-bullet continuation (AXON —
# the salutation follows the last bullet and the block appends it as a
# wrap). NFLX's letters carry it as a standalone line (one quarter
# drops the comma in flattening); COIN's Q3 FY2025 letter splits it
# across two lines ("Fellow" / "Shareholders,"). _salutation_block_len
# returns how many lines the salutation starting at lines[i] occupies
# (1, or 2 for the split form), or 0. The pattern is deliberately
# salutation-shaped: an optional single capitalized word between the
# opener and "shareholders" ("Fellow Affirm Shareholders,") and an
# optional trailing comma or period — and the line must END at the
# salutation. A prose sentence that happens to mention shareholders
# ("Shareholders approved the merger") never matches, and an inline
# salutation ("Dear Shareholders, This is my first letter ...",
# Instacart/Affirm's flattened form) never matches either: dropping
# that line would eat the prose with it, so those stay served.
_SALUTATION_RE = re.compile(
    r"^(Fellow|Dear)(\s+[A-Z][a-z]+)?\s+shareholders[,.]?$",
    re.IGNORECASE,
)
_SALUTATION_SPLIT_RE = re.compile(r"^shareholders[,.]?$", re.IGNORECASE)


def _salutation_block_len(lines: list[str], i: int) -> int:
    """Length of the salutation block starting at lines[i], or 0."""
    if i >= len(lines):
        return 0
    if _SALUTATION_RE.match(lines[i]):
        return 1
    if (
        lines[i].strip().lower() in ("fellow", "dear")
        and i + 1 < len(lines)
        and _SALUTATION_SPLIT_RE.match(lines[i + 1])
    ):
        return 2
    return 0


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
# Batch 179: role-abbreviation labels ("PR Contact:" / "IR Contact:" —
# Chipotle heads every release with them, and the old regexes only knew
# the spelled-out roles, so "PR Contact: Laurie Schalow" became the
# headline). Word-boundaried so "their contact" / "first contact" never
# match — the "ir" sits mid-word there, with no boundary before it.
_CONTACT_LINE_RE = re.compile(
    r"(media|press|investor)[\s\-–]*(contacts?|inquiries?)"
    r"|\b(pr|ir)[\s\-–]*(contacts?|inquiries?)\b"
    r"|[\w.\-+]+@[\w.\-]+\.\w+"
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
    # Batch 179: role-abbreviation prefixes ("PR Contact:" / "IR Contact:"
    # — Chipotle) join the prefix list, so the header branch fires and
    # the block skip consumes the phone/email detail lines with it.
    r"^((for more information|investor(\s+relations)?|financial|media|press|editorial|pr|ir)\s+)?"
    r"contacts?\b"
    # Company-prefixed header: "The Progressive Corporation Company Contact:"
    # (batch 105). A real headline never ends with "Company Contact:".
    r"|^.*\bcompany\s+contacts?\b"
    # Bare role labels with no "contact" word (American Airlines: "Corporate
    # Communications" / "Investor Relations"; BlackRock: "INVESTOR RELATIONS:"
    # / "MEDIA RELATIONS:" with a trailing colon). Full-line anchored so a
    # real headline mentioning investor relations is never swallowed.
    # Batch 111: the colon variant made every BlackRock quarter's headline
    # the contact header.
    r"|^(investor relations|corporate communications|media relations):?$"
    # Doubled role labels from a flattened two-column contact table
    # (Akamai Q4: "Media Relations Investor Relations" — media contact in
    # one column, investor contact in the other). A doubled label row is a
    # contact header, never a headline or lede. Batch 123.
    r"|^(?:(?:investor relations|corporate communications|media relations|press relations|public relations)\s+){1,}(?:investor relations|corporate communications|media relations|press relations|public relations):?$"
    # Company-name-prefixed header without the word "Company" (Qualcomm:
    # "Qualcomm Contact:"). Full-line anchored and length-capped; a real
    # headline never ends with "Contact(s):". Batch 111.
    r"|^[\w&.,'\-\s]{1,80}\s+contacts?:\s*$"
    # Date-prefixed header (American Water: "July 29, 2026 Investor Contact:").
    # The date prefix keeps the standard branch from matching.
    r"|^(january|february|march|april|may|june|july|august|september|october|"
    r"november|december)\s+\d{1,2},\s+\d{4}\s+"
    r"((for more information|investor(\s+relations)?|financial|media|press|editorial)\s+)?"
    r"contacts?\b",
    re.IGNORECASE,
)

# A bare job-title line ("Chief Financial Officer", "President and Chief
# Executive Officer" — Moody's quote attributions, 6 stored rows): the
# name is missing (dropped elsewhere), so the role alone is a dangling
# fragment, never highlights. Every word must be role vocabulary (2-6
# words) and at least one must be an anchor (Officer/President/...), so
# a prose line that merely mentions a role ("Our Chief Financial Officer
# said ...") never matches — it carries verbs and other words.
# Batch 189: the abbreviations CEO/CFO/COO are role vocabulary too —
# a wrapped attribution tail ("Chairman and CEO.", "President and
# CEO.") is the same dangling fragment as the spelled-out form, and
# without them the tail consumes a lede budget line and the finish
# rule reads it as a complete item, orphaning the quote body that
# follows (AJG Q4 FY2025). Full-cache survey: only 4 distinct lines
# newly match ("CEO and Co-Founder" x9, "President and CEO." x3,
# "CHAIR AND CEO" x2, "Chairman and CEO." x1) — all bare role lines.
# The abbreviations join the anchor set as well, so a "Group CEO"
# shape matches; the 2-word floor still keeps a lone "CEO" out.
_ROLE_TITLE_WORDS = frozenset(
    "president and chief executive financial operating commercial legal "
    "technology information marketing strategy people risk accounting "
    "senior vice officer director chairman chairwoman chair founder "
    "co-founder cofounder group global managing head investor relations "
    "general counsel secretary treasurer principal corporate development "
    "business human resources administrative ceo cfo coo".split()
)
_ROLE_ANCHOR_WORDS = frozenset(
    "officer president chairman chairwoman chair director founder "
    "co-founder cofounder head counsel secretary treasurer principal "
    "ceo cfo coo".split()
)


def _is_bare_role_line(ln: str) -> bool:
    """True when ln is only a job title, no name or other content."""
    words = [w.strip(",.").lower() for w in ln.split()]
    if not 2 <= len(words) <= 6:
        return False
    if not all(w in _ROLE_TITLE_WORDS for w in words):
        return False
    return any(w in _ROLE_ANCHOR_WORDS for w in words)


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


def _is_subsidiary_list(ln: str) -> bool:
    """True for a flattened subsidiary-list masthead line (Cincinnati
    Financial: its exhibit header flattens the subsidiary table into one
    line per table row, " n " joining the columns — "The Cincinnati
    Insurance Company n The Cincinnati Indemnity Company").

    Narrow by construction: the line must split on " n " into at least two
    segments, and every segment must end with a company suffix (via
    _COMPANY_NAME_LINE_RE) and stay within 80 chars. A prose line that
    happens to contain " n " fails the suffix rule on at least one segment,
    and a real headline never consists solely of " n "-joined company
    names. Batch 134.
    """
    parts = ln.split(" n ")
    if len(parts) < 2:
        return False
    return all(
        0 < len(p) <= 80 and _COMPANY_NAME_LINE_RE.search(p) for p in parts
    )


# A quarter cover title (batch 167): "First Quarter 2025", "Second
# Quarter 2025", "Fourth Quarter and Full Year 2024". It is a document
# title, never an address line — but the digit rule below would swallow
# the 3-word form as a street / city-postal line, and the headline loop's
# masthead branch then skips it when a date line follows (Coinbase's Q1/Q2
# 2025 letters lost their title that way and the rounding note became the
# headline). The 6-word "and Full Year" form already escapes the digit
# rule on word count and is picked as the headline today; the exclusion
# makes the 3-word form behave the same.
_QUARTER_TITLE_RE = re.compile(
    r"^(First|Second|Third|Fourth) Quarter( and Full Year)? \d{4}$"
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
    if _QUARTER_TITLE_RE.match(ln):
        return False  # cover title, not an address line (batch 167)
    if len(ln) > 48:
        return False
    if _CONTACT_LINE_RE.search(ln):
        return True
    if _SUITE_ADDRESS_RE.search(ln):
        return True
    words = ln.split()
    if len(words) == 1:
        return True  # country line ("Switzerland")
    if re.match(r"^(NYSE|Nasdaq|AMEX)\s*:\s*[A-Z][A-Z.\-]{0,6}$", ln, re.IGNORECASE):
        return True  # exchange:ticker masthead line ("NYSE: TRV" — Travelers).
        # Batch 115: never a headline; lets _skip_masthead_block consume it
        # instead of stranding it as a headline candidate.
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


def _looks_like_wrapped_headline_start(ln: str, nxt: str) -> bool:
    """True when *ln* looks like the first line of a wrapped release headline.

    Sempra heads its release "Sempra Reports Third-Quarter" / "2025 Results":
    the fragment is short (3 words / 28 chars), so _skip_contact_block eats it
    as a contact detail line and "2025 Results" becomes the headline. A
    contact detail line never ends on a headline wrap/verb/ordinal tail with a
    plausible continuation on the next line — a real headline fragment does.
    Batch 115.
    """
    if not (
        _HEADLINE_WRAP_TAIL_RE.search(ln)
        or _HEADLINE_VERB_TAIL_RE.search(ln)
        or _HEADLINE_ORDINAL_TAIL_RE.search(ln)
    ):
        return False
    if not nxt or len(nxt) > 140 or not any(c.isalpha() for c in nxt):
        return False
    if nxt.rstrip().endswith((".", "!", "?", ":")):
        return False
    if (
        _ADMIN_LINE_RE.match(nxt)
        or _BOILERPLATE_RE.match(nxt)
        or _CONTACT_HEADER_RE.match(nxt)
        or _CONTACT_LINE_RE.search(nxt)
        or _PHONE_RE.search(nxt)
    ):
        return False
    return True


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
        nxt = lines[j + 1] if j + 1 < len(lines) else ""
        if _looks_like_wrapped_headline_start(ln, nxt):
            # Wrapped-headline fragment, not contact detail (Sempra's "Sempra
            # Reports Third-Quarter" / "2025 Results"). Stop so the headline
            # pass picks it up and joins the continuation. Batch 115.
            break
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
            # Batch 151: admin lines do not consume a lookahead slot.
            # Crown Castle's block runs "Contacts: Sunit Patel, CFO" /
            # "Kris Hinson, VP Corp Finance & Treasurer" / "FOR IMMEDIATE
            # RELEASE" / "Crown Castle Inc." / "713-570-3050" — the phone
            # is three raw lines after the name line, so the old lookahead
            # stopped at the name line and the headline loop then picked
            # it as the headline. Skipping admin lines when gathering the
            # following lines finds the phone within two non-admin lines.
            following: list[str] = []
            k = j + 1
            while k < len(lines) and len(following) < 2:
                if not _ADMIN_LINE_RE.match(lines[k]):
                    following.append(lines[k])
                k += 1
            if not any(
                _CONTACT_LINE_RE.search(f) or _PHONE_RE.search(f) for f in following
            ):
                break
        j += 1
    return j


def _is_repeated_phrase(ln: str) -> bool:
    """True when a line repeats one phrase twice ("Akamai Technologies Akamai
    Technologies") — the flattened two-column form of a single table cell.
    A real headline never repeats its whole phrase. Batch 123."""
    words = ln.split()
    if len(words) < 2 or len(words) % 2:
        return False
    half = len(words) // 2
    return words[:half] == words[half:]


# Words a contact-name row never contains but a real headline almost always
# does; keeps the contact-table skip from ever firing on a genuine headline
# that happens to precede a role-label line. Batch 123.
_CONTACT_TABLE_NON_NAME_WORDS = frozenset(
    {
        "reports",
        "report",
        "announces",
        "announce",
        "announced",
        "results",
        "quarter",
        "fiscal",
        "earnings",
        "revenue",
        "revenues",
    }
)


def _skip_contact_table(lines: list[str], i: int) -> int | None:
    """Return the index of the real headline after a flattened two-column
    contact table, or None when the lines at *i* are not one.

    Shape (Akamai Q4 releases, which put the contact table before the title
    while Q1-Q3 put the title first): a names row ("Christine Simeone Mark
    Stoutenberg" — two contacts side by side), a role-label row ("Media
    Relations Investor Relations"), a company row ("Akamai Technologies
    Akamai Technologies"), then the real headline, wrapped ("AKAMAI REPORTS
    FOURTH QUARTER 2024 AND" / "FULL-YEAR 2024 FINANCIAL RESULTS"). The
    names row is 4 words and headline-shaped, so no existing skip catches
    it: there is no contact-header line for the header branch (the roles row
    is a doubled label, not a header), and _skip_bare_masthead_name requires
    <=3 words and a non-headline-shaped line.

    Guards, all required: the next line is a role-label row (single or
    doubled — a real headline is never followed by one); the names row is
    short (<=6 words), has no terminal punctuation, and contains no
    headline word; the table rows after the roles row are consumed only
    while they look like table continuation (repeated phrase, company-name
    line, admin/contact line, or a short label line); and a headline-shaped
    line must appear within 8 lines, otherwise nothing is skipped — so a
    genuine headline followed by a stray role line keeps its headline, and
    a table whose headline never arrives never swallows body text.
    """
    ln = lines[i]
    if i + 1 >= len(lines):
        return None
    if not (
        _CONTACT_HEADER_RE.match(lines[i + 1])
        or _CONTACT_TABLE_ROLE_RE.match(lines[i + 1])
    ):
        return None
    words = ln.split()
    if len(words) > 6 or re.search(r"[.!?;:]\\s*$", ln):
        return None
    if any(
        w.strip(".,;:").lower() in _CONTACT_TABLE_NON_NAME_WORDS for w in words
    ):
        return None
    j = i + 2
    while j < len(lines) and j - i <= 8:
        cand = lines[j]
        if (
            _is_repeated_phrase(cand)
            or _COMPANY_NAME_LINE_RE.search(cand)
            or _ADMIN_LINE_RE.match(cand)
            or _CONTACT_LINE_RE.search(cand)
            or _CONTACT_HEADER_RE.match(cand)
        ):
            j += 1
            continue
        if _looks_like_headline(cand):
            return j
        if len(cand.split()) <= 4 and not re.search(r"[.!?]\\s*$", cand):
            j += 1  # short label line inside the table block
            continue
        return None
    return None




# A "Exhibit 99.1" / "EXHIBIT 99.1" marker line inside the document, as
# its own pattern for the compound-title lookahead below (the admin regex
# also matches it, but it matches page numbers and filenames too, which
# would make the lookahead fire on the wrong lines).
_EXHIBIT_MARKER_RE = re.compile(
    r"^exhibit[\s\-]*99(\.1)?\b|^ex-?99(\.1)?\b",
    re.IGNORECASE,
)


def _is_compound_earnings_title(lines: list[str], i: int) -> bool:
    """True when the line at *i* is a compound earnings-release document
    title, not the release headline.

    Shape (lululemon Q3 releases, which combine the earnings release with
    a stock-repurchase announcement in one 8-K): the exhibit document
    title (EARNINGS RELEASE & STOCK REPURCHASE PROGRAM) sits before
    Exhibit 99.1, and the real release headline follows the marker
    (LULULEMON ATHLETICA INC. ANNOUNCES THIRD QUARTER FISCAL 2024
    RESULTS). The bare EARNINGS RELEASE title is already skipped by
    the label branch below, but the compound form was picked as the
    headline instead, so both Q3 quarters stored the document title.

    Guards, all required: the line carries earnings release followed
    by & or and (a compound title, not a bare label and not a
    results headline); an exhibit-marker line appears within the next 2
    lines; and the line immediately after that marker is a headline-shaped
    line carrying a headline verb (announces/reports). The verb guard is
    what keeps JPMorgan stored headline safe: its EARNINGS RELEASE -
    THIRD QUARTER 2025 RESULTS title is also followed by an exhibit
    marker, but the line after the marker is the company name/address
    block, not a verb headline, and XOM 3Q 2025 Earnings Release
    title is preceded by (not followed by) its marker, so it never fires
    either. A compound title with no marker after it, or with prose
    (not a verb headline) after the marker, keeps the old behavior.
    """
    ln = lines[i]
    if not re.search(r"earnings\s+release\s+(&|and\b)", ln, re.IGNORECASE):
        return False
    for k in (i + 1, i + 2):
        if k >= len(lines):
            return False
        if _EXHIBIT_MARKER_RE.match(lines[k]):
            nxt = lines[k + 1] if k + 1 < len(lines) else ""
            return bool(
                _looks_like_headline(nxt)
                and re.search(r"\b(announces?|reports?)\b", nxt, re.IGNORECASE)
            )
    return False


# An abbreviated quarter earnings-release document title (ExxonMobil:
# "3Q 2024 Earnings Release"), as its own pattern for the lookbehind
# below — the spelled-out label regex above covers "FIRST QUARTER 2026
# EARNINGS RELEASE" but not the abbreviated form.
_QUARTER_ABBR_EARNINGS_TITLE_RE = re.compile(
    r"^[1234]q \d{4} earnings release$",
    re.IGNORECASE,
)


def _is_quarter_earnings_title(lines: list[str], i: int) -> bool:
    """True when the line at *i* is an abbreviated quarter earnings-release
    document title, not the release headline.

    Shape (ExxonMobil, all 8 stored quarters): the exhibit header ends
    with "EXHIBIT 99.1", then the document title ("3Q 2024 Earnings
    Release"), then a "FOR IMMEDIATE RELEASE <date>" admin line, then
    the real headline ("ExxonMobil Announces Third-Quarter 2024
    Results"). The title is short and headline-shaped, so the loop
    picked it and all 8 XOM quarters stored the document title.

    Guards, all required: the line is exactly "<digit>Q <year> Earnings
    Release" (full-line anchored, so JPMorgan's genuine "JPMORGAN CHASE
    & CO. EARNINGS RELEASE - THIRD QUARTER 2024 RESULTS" headlines never
    match); an exhibit-marker line appears within the previous 3 lines
    (the mirror of the compound-title rule, where the marker follows
    the title — here it precedes it); and the next non-admin line after
    the title is a headline-shaped line carrying a headline verb
    (announces/reports). The verb guard is what keeps a release whose
    only title is the quarter label on old behavior: with no verb
    headline after it, the title is kept rather than skipped into
    bullets or a table row.
    """
    if not _QUARTER_ABBR_EARNINGS_TITLE_RE.match(lines[i]):
        return False
    if not any(
        _EXHIBIT_MARKER_RE.match(lines[k]) for k in range(max(0, i - 3), i)
    ):
        return False
    j = i + 1
    while j < len(lines) and _ADMIN_LINE_RE.match(lines[j]):
        j += 1
    if j >= len(lines):
        return False
    nxt = lines[j]
    return bool(
        _looks_like_headline(nxt)
        and re.search(r"\b(announces?|reports?)\b", nxt, re.IGNORECASE)
    )


# A dated press-release document label (Altria/MO, all 8 stored quarters):
# "<COMPANY NAME> (EARNINGS) PRESS RELEASE, DATED <Month DD, YYYY>".
# The label sits between the exhibit header and the "Exhibit 99.1"
# marker, ahead of the real headline ("ALTRIA REPORTS 2024
# THIRD-QUARTER ..."), and the loop picked it because it is short and
# headline-shaped. A genuine headline never ends with "DATED <full
# date>", so the date anchor is the whole discriminator — no marker
# lookbehind/lookahead is needed (unlike batches 124/127, the label
# here precedes its marker, and the marker follows it in both MO
# variants). The 140-char bound keeps a prose sentence that happens
# to end "... press release, dated <date>" out of the rule.
_DATED_PRESS_RELEASE_LABEL_RE = re.compile(
    r"^.+?\b(earnings\s+)?press\s+release,?\s+dated\s+"
    r"(january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|"
    r"oct|nov|dec)\.?\s+\d{1,2},?\s+\d{4}$",
    re.IGNORECASE,
)


def _is_dated_press_release_label(ln: str) -> bool:
    """True when *ln* is a dated press-release document label, not a headline."""
    return len(ln) <= 140 and bool(_DATED_PRESS_RELEASE_LABEL_RE.match(ln))


# An address dateline (M&T Bank/MTB, all 8 stored quarters): "One M&T
# Plaza, Buffalo, NY 14203 July 15, 2026" — the head-office address plus
# the release date on one line, ahead of the real headline ("M&T Bank
# Corporation (NYSE:MTB) announces second quarter 2026 results"). The
# loop picked it because no skip matched it: it is 49 chars (over the
# 48-char masthead-residue bound, 9 words over the 4-word guard), it
# ends with a date rather than a dash (so _DATELINE_RE misses it), and
# it does not start with a date (so _DATE_LINE_RE misses it). A genuine
# headline never ends "<ZIP> <full month date>" — the ZIP+date ending
# is the whole discriminator, so no lookahead is needed. The 120-char
# bound keeps a prose sentence that happens to end with a ZIP+date out
# of the rule. Batch 133.
_ADDRESS_DATELINE_RE = re.compile(
    r"^.+?\b\d{5}(-\d{4})?\s+"
    r"(january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|"
    r"oct|nov|dec)\.?\s+\d{1,2},\s+\d{4}$",
    re.IGNORECASE,
)


def _is_address_dateline(ln: str) -> bool:
    """True when *ln* is an address+date dateline, not a headline."""
    return len(ln) <= 120 and bool(_ADDRESS_DATELINE_RE.match(ln))


# A slide-deck title page (U.S. Bancorp/USB, all 8 stored quarters):
# "<NQ>YY Key Financial Data" heads the deck, and the highlights
# section heading ("<NQ>YY (Financial) Highlights") follows
# immediately. The title page is never the headline — the section
# heading is — and the body starts AT the heading so the section
# extractor still finds its content (batch 130). Without the
# body_start-at-heading, the section anchor is lost: the body would
# fall back to a later business section and the financial bullets
# would be lost. Full-line anchored: a genuine headline is never
# exactly a quarter token plus "Key Financial Data" (Lam Research's
# "Key Financial Data for the Quarters Ended ..." prose heading is a
# different shape and is untouched).
_DECK_KEY_FINANCIAL_DATA_RE = re.compile(r"^[1234]Q\d{2}\s+Key Financial Data$")


# A role-label row of a flattened two-column contact table, as its own
# pattern (the _CONTACT_HEADER_RE alternative above covers the same shape
# for the header branch; this one is the lookahead the table skip uses).
# Full-line anchored: one or more role labels run together, optional colon.
_CONTACT_TABLE_ROLE_RE = re.compile(
    r"^(?:(?:investor relations|corporate communications|media relations|"
    r"press relations|public relations)\s+)*"
    r"(?:investor relations|corporate communications|media relations|"
    r"press relations|public relations):?$",
    re.IGNORECASE,
)

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

# A narrative line inside a TOC's unanchored tail: a headline verb plus a
# results topic, with no terminal sentence punctuation (batch 148). TOC tails
# are section labels ("Overview", "EARNINGS RELEASE") and footnote markers
# ("(1)"), never verb+topic lines; a footnote sentence ("Includes
# reconciliation of consolidated net income to FFO ...") carries no headline
# verb, and a prose lede ("Acme reports fourth quarter results today.") is
# excluded by its terminal period — so the signal is headline-shaped, not
# merely prose-shaped.
_NARRATIVE_TAIL_RE = re.compile(
    r"\b(reports?|announces?|delivers?|posts?|declares?|names?|elects?)\b"
    r".*\b(results?|quarter|earnings|year|revenue|guidance|outlook)\b",
    re.IGNORECASE,
)


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

    The tail after the last page number is bounded (batch 148): a tail line
    that is headline-shaped (headline verb + results topic, no terminal
    sentence punctuation) means the narrative already started, so the skip
    rolls back to that line instead of swallowing the headline and ledes.
    A tail with no headline-shaped line keeps the old return.

    Requires at least 2 page-number lines: a stray "table of contents" mention
    in a normal release must never trigger the skip. Returns *i* unchanged when
    the lines don't look like a TOC.
    """
    j = i + 1
    pages = 0
    last_page_end = i + 1
    while j < len(lines):
        ln = lines[j]
        if _TOC_PAGE_RE.match(ln):
            pages += 1
            j += 1
            last_page_end = j
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
    # Bounded tail (batch 148): lines after the last page number are
    # unanchored — no page number vouches for them — and the loop above
    # consumes them as titles without limit, so a packet whose narrative
    # follows the TOC directly (short headline + short ledes, no Contacts:
    # block, no >140-char line) loses its headline and ledes and the whole
    # release extracts as None. When the tail's first headline-shaped line
    # appears, the narrative already started: roll back to it so the
    # headline pass sees the real headline (a leading footnote marker is
    # skipped with the tail, never landed on — it would trip the
    # footnote-headline guard and lose the release). A tail with no such
    # line is TOC material (SPG's "(1)" + footnote + mini-TOC tail) and
    # keeps the old return, so SPG is byte-identical.
    for k in range(last_page_end, j):
        ln = lines[k]
        if _NARRATIVE_TAIL_RE.search(ln) and not re.search(r"[.!?]\s*$", ln):
            return k
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

# A lede line that ends grammatically unfinished — a wrap tail. Batch 165:
# the lede finish rule (batch 139) fires for lone-marker ledes via
# marker_seen, but an inline-marked bullet list (Skydance's "Summary
# Points") never sets it, so a bullet cut mid-sentence ("...building our
# pipeline across") stayed cut. The wrap tail is the second trigger: a
# trailing comma/dash, or a trailing conjunction / preposition / article /
# copula — the sentence continues on the next line. A semicolon is NOT a
# wrap tail: it separates independent clauses, and Coinbase's letter ends
# a paragraph with one right before its footnote block ("...than any other
# company;" / "1 Coinbase Total Trading Volume ...") — treating it as a
# wrap pulled the footnote definition in as "continuation". A complete statement does NOT match, even without terminal punctuation:
# a figure bullet ("•Share repurchases and dividends of $5.1B", "•Diluted
# EPS was $0.78") and a complete clause ("...up 181% and 148% year over
# year, respectively") end the item, so the prose and tables that follow
# are never pulled in as "continuation". Deliberately wider than the
# headline wrap tail (which lacks "across" — the attested Skydance tail)
# and narrower than a bare "no terminal punctuation" test (which would
# fire on every period-less figure bullet).
_LEDE_WRAP_TAIL_RE = re.compile(
    r"(\b(and|or|of|for|to|with|in|on|at|the|a|an|across|including|through|"
    r"under|over|between|among|per|via|from|by|as|into|upon|toward|towards|"
    r"against|within|without|before|after|during|while|than|but|so|yet|nor|"
    r"versus|vs|is|are|was|were|has|have|had|will|would|be|been)\b"
    r"|[&–—-]|[,]\s*)\s*$",
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

# A continuation line that opens with "for" + a period designator ("FOR
# THIRD QUARTER 2024" after "MOODY'S CORPORATION REPORTS RESULTS", "for
# Fourth Quarter Fiscal 2025" after "FICO Announces Earnings of $7.40 per
# Share", "for 2026" after "... Announces Guidance"): the headline was
# wrapped mid-phrase with the period phrase leading the second line. Batch
# 136. Narrow on purpose — a bare "for" lead is NOT a trigger, because a
# lede "For ..." line is common, and it always starts "For the ..." ("For
# the three months ended ...:", "For the full year:") or is an admin line
# ("For 6:00 a.m. ET Release", caught by _ADMIN_LINE_RE). So the rule
# requires an ordinal quarter ("Third Quarter", "Fourth Quarter and Fiscal
# 2024") or a bare year standing alone ("for 2026" — the $-anchor means
# "For 2026, the company expects ..." never matches), and the (?!the\b)
# guard is belt-and-braces for a "For the ..." line that somehow lost its
# colon. A genuine period phrase never starts a lede sentence.
_HEADLINE_FOR_LEAD_RE = re.compile(
    r"^for\s+(?!the\b)"
    r"(?:(?:first|second|third|fourth)[-\s]+quarter|20\d{2}\s*$)",
    re.IGNORECASE,
)

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
#
# Batch 115: the hyphenated ordinal-quarter form is the same fragment shape
# (Sempra's "Sempra Reports Third-Quarter" / "2025 Results"). Without it the
# fragment is eaten as a contact detail line and "2025 Results" becomes the
# headline.
_HEADLINE_ORDINAL_TAIL_RE = re.compile(
    r"\b(first|second|third|fourth|full)([-\s]+(quarter|year))?\s*$", re.IGNORECASE
)

# A headline ending on "{ordinal} Quarter" / "Full Year" with a bare 4-digit
# year on the next line ("Intercontinental Exchange Reports Second Quarter" /
# "2026"): the year completes the headline. The year is never a lede start,
# so the digit-lead continuation guard is bypassed for this exact shape only.
# Batch 108.
#
# Batch 115: the quarter tail may be hyphenated ("Sempra Reports
# Third-Quarter"), and the continuation may be year-led rather than a bare
# year ("2025 Results") — the period label still completes the fragment, and
# a complete headline never ends on "{ordinal} Quarter".
_HEADLINE_QUARTER_TAIL_RE = re.compile(
    r"\b((first|second|third|fourth)[-\s]+quarter|full[-\s]+year)\s*$", re.IGNORECASE
)
_HEADLINE_BARE_YEAR_RE = re.compile(r"^20\d{2}$")
_HEADLINE_YEAR_LEAD_RE = re.compile(r"^20\d{2}\b")
# A year-led results fragment ("2024 Results") — the tail of a wrapped
# headline ("Prudential Financial, Inc. Announces" / "2024 Results"), never
# a lede start. Batch 118: the digit-led bad-start guard below refused it,
# stranding the fragment as the first body line (which also killed the
# leading-bullet-block detection and let a "Financial Highlights" table
# header become the whole body, under 200 chars -> highlights None).
_HEADLINE_YEAR_RESULTS_RE = re.compile(r"^20\d{2}\s+Results\b", re.IGNORECASE)

# A headline ending on a fragment word (Chubb/CB, batch 135): the release
# headline is a whole paragraph wrapped at arbitrary points, and the wrap
# lands mid-phrase on a word that cannot end a complete headline — a
# modifier awaiting its head noun ("Net Income and Core" / "Operating
# Income", "P&C Up 10.6% and Life" / "Insurance", "Respectively;
# Consolidated" / "Net Premiums Written", "P&C Combined" / "Ratio",
# "Excluding Catastrophe Losses and Prior" / "Period Development") or
# the preposition "Up" awaiting its figure ("Net Income of $7.35, Up" /
# "34.6%"). Each word is load-bearing: a complete headline never ends on
# one of them ("Reports Record" is a fragment of "Record ... Income";
# "Reports P&C" is a fragment of "P&C Combined Ratio"). The continuation
# guards still apply, so a genuine short headline ending on one of these
# words followed by a sentence-terminated lede never joins.
#
# Batch 137: two more Chubb wrap points. "Insurance" — the Q4 2024 headline
# wraps after "Life Insurance" onto "Up 15.7%; P&C Combined Ratio of
# 86.6%", and that tail clause drops out of the stored text entirely (the
# old headline stopped at "Insurance" and the section extractor skipped
# the orphan line, so the stored body never contained it). "Income" is
# NOT a bare fragment word, despite the Q3 2024 wrap after "Net
# Investment Income" onto "Both Up Double-Digit; ...": the old-vs-new
# blast showed a bare "Income" tail over-joins genuine headlines —
# Carnival's "NET INCOME" headlines are followed by subhead lines
# ("Accelerates shareholder returns ...", "Record bookings provide ...")
# and PSEG's "$3.54 PER SHARE NET INCOME" by a sibling metric line
# ("$3.68 PER SHARE NON-GAAP OPERATING EARNINGS"). So "Income" joins
# only conjunctively, with a "Both"-led continuation (see
# _HEADLINE_INCOME_TAIL_RE / _HEADLINE_BOTH_LEAD_RE below): "Both" is a
# pronoun referring back to the two income figures, never a subhead or a
# sibling metric line, and a sentence-terminated "Both ..." lede is still
# refused by the continuation guards.
_HEADLINE_FRAGMENT_TAIL_RE = re.compile(
    r"\b(core|record|consolidated|life|net|operating|combined|prior|p&c|up|insurance)\s*$",
    re.IGNORECASE,
)

# Batch 137 conjunctive wrap rule (see comment above): a headline ending
# on "Income" continues only onto a "Both"-led line ("Net Investment
# Income" / "Both Up Double-Digit; ..."). Either half alone is not a
# trigger — Carnival/PSEG prove "Income" alone over-joins, and a "Both"
# lead after any other tail is a lede/subhead, not a wrap.
_HEADLINE_INCOME_TAIL_RE = re.compile(r"\bincome\s*$", re.IGNORECASE)
_HEADLINE_BOTH_LEAD_RE = re.compile(r"^both\b", re.IGNORECASE)

# A percentage-led continuation ("34.6%, and Record ...", "21.7%;") — the
# figure completing an "Up" fragment, or the second figure of an "and"
# wrap ("Up 78.8% and" / "85.2%;"). The digit-led bad-start guard below
# refused these, stranding the figure as the first body line and leaving
# the headline ending on "Up"/"and". Allowed only when the headline ends
# on a fragment tail or a wrap tail (a headline never ends with a comma,
# semicolon, or conjunction either) — never for verb/ordinal tails, where
# a digit-led line is a metric-table row, not a headline completion.
_HEADLINE_PCT_LEAD_RE = re.compile(r"^\d[\d,]*(\.\d+)?\s*%")

# A continuation line that is itself a complete headline ("Danaher
# Reports Third Quarter 2024 Results" after Danaher's cover slogan
# "Innovation at the speed of life"): the slogan line ends on a fragment
# word ("life"), but the next line is a fresh headline, not a wrap
# continuation — joining them would build a Franken-headline. Blocks
# fragment-tail joins only: stronger triggers (a wrap comma, a verb
# tail) keep their existing behavior — Merck's "Merck & Co., Inc.,
# Rahway, N.J.," / "USA Announces ..." wrap must still join, and there
# the continuation is the verb half of the same headline, not a new one.
_HEADLINE_FRESH_HEADLINE_RE = re.compile(
    r"^\S+\s+(reports?|announces?|delivers?|posts?|declares?|names?|"
    r"elects?|approves?|raises?|beats?|tops?|reaffirms?|launches?|"
    r"completes?|acquires?)\b",
    re.IGNORECASE,
)


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


# Lines that are never a release headline (batch 115). Each shape was found
# as a stored headline or as a bare-masthead-name misfire that jumped the
# pick onto a contact-detail line:
# - no alphanumeric characters at all: Truist's lone backtick, Welltower's
#   lone quote, Ross's underscore rule, Chevron's lone backslash;
# - a single alphanumeric token carrying a digit, 5+ chars: Verizon's
#   'VZQTR20FIN' image filename (a bare masthead name is a word, not a
#   token; short tickers like '3M' still pass);
# - a page number glued to a single junk token: Airbnb's '1 §:)airbnb'
#   page-header logo artifact (the token must carry a non-word character,
#   so a real '2026 Outlook'-shaped line never matches);
# - an exchange:ticker masthead line: Travelers' 'NYSE: TRV';
# - a 1-4 word section label ending in a colon: Skydance's 'Summary Points:'.
# - a lone country-name masthead line: Rockwell's releases put 'USA' under
#   the street address ('1201 S. Second Street' / 'Milwaukee, WI 53204') and
#   above the contact block, and it became the headline for all 8 quarters.
#   Full-line anchored; a real headline is never one word, let alone a bare
#   country name (the U.S./U.K. forms matter — the address block above the
#   contact line is a common Donnelley masthead shape). Batch 116.
# - a slide-deck title line: Bank of America's deck releases open with a
#   "1 2Q26 Financial Highlights ... Business Segment Highlights ... Consumer
#   Banking" title (page number + quarter token + "Financial Highlights").
#   It is a slide title, never a headline — without this the split
#   bullet-run's first piece became the headline. Batch 125.
_NEVER_HEADLINE_RE = re.compile(
    r"^[^A-Za-z0-9]*$"
    r"|^(?=[A-Za-z0-9]{5,}$)[A-Za-z0-9]*\d[A-Za-z0-9]*$"
    r"|^\d{1,3}\s+\S*[^\w\s]\S*$"
    r"|^(NYSE|Nasdaq|AMEX)\s*:\s*[A-Z][A-Z.\-]{0,6}$"
    r"|^\S+(?:\s+\S+){0,3}:\s*$"
    r"|^u\.?s\.?(?:a\.?)?\.?$|^united\s+states$|^u\.?k\.?$|^united\s+kingdom$"
    r"|^canada$|^mexico$|^germany$|^france$|^japan$|^ireland$|^netherlands$"
    r"|^switzerland$|^australia$|^singapore$|^india$|^brazil$"
    r"|^\d+\s+\S+\s+Financial Highlights"
    r"|^[1234]Q\d{2}\s+Key Financial Data$",
    re.IGNORECASE,
)


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
       (Batch 115) The quarter tail may be hyphenated ("Sempra Reports
       Third-Quarter") and the continuation year-led ("2025 Results") — same
       fragment shape, same bypass.
    6. (Batch 118) The picked headline ends on a headline verb and the next
       line is a year-led results fragment ("Prudential Financial, Inc.
       Announces" / "2024 Results"). A "YYYY Results" line is never a lede
       start, so the digit-lead guard is bypassed for this exact shape only
       — a bare year after a verb tail still does NOT join (batch 108's
       "Acme Reports Results" / "2026" negative still holds: no "Results"
       word after the year).

    7. (Batch 135) The picked headline ends on a fragment word (see
       _HEADLINE_FRAGMENT_TAIL_RE): a mid-phrase wrap on a modifier or on
       "Up" ("... and Core" / "Operating Income ...", "... and Life" /
       "Insurance ..."). Chubb's paragraph headlines wrap 5-11 times, so
       the join cap rises from 3 to 12 — every join still requires a
       trigger plus all continuation guards, so the higher cap cannot run
       away into the lede: a runaway would need 12 consecutive
       fragment-shaped lines. One exception: a fragment-tail join is
       blocked when the continuation is itself a fresh headline (Danaher's
       cover slogan "Innovation at the speed of life" / "Danaher Reports
       ..." — the slogan is the stored headline today, and joining would
       build a Franken-headline, not a repair).
    8. (Batch 135) The next line is percentage-led ("34.6%, ...", "21.7%;")
       and the headline ends on a fragment tail or a wrap tail: the figure
       completing an "Up" fragment or an "and" wrap. The digit-lead guard
       is bypassed for this exact shape only — a digit-led line after a
       verb or ordinal tail is still refused (metric-table rows).

    9. (Batch 136) The next line is "for"-led with a period designator
       ("FOR THIRD QUARTER 2024", "for Fourth Quarter Fiscal 2025", "for
       2026"): the period phrase completing a wrapped headline. A bare
       "for" lead is not a trigger — lede "For the ..." lines and admin
       "For 6:00 a.m. ET Release" lines never match the period-designator
       shape (see _HEADLINE_FOR_LEAD_RE).

    10. (Batch 137) The picked headline ends on "Insurance" (new
       _HEADLINE_FRAGMENT_TAIL_RE word): Chubb's paragraph headline
       wraps after "Life Insurance" ("Up 15.7%; P&C Combined Ratio of
       86.6%"). Same fragment-tail guards as batch 135. "Income" is
       narrower: it joins only onto a "Both"-led continuation
       ("Net Investment Income" / "Both Up Double-Digit; ...") — a bare
       "Income" tail over-joins Carnival subheads and PSEG sibling metric
       lines, so the conjunctive rule (income tail AND both lead) is the
       whole trigger; a "Both" lead after any other tail never joins.
    """
    headline = lines[i]
    j = i + 1
    joins = 0
    while joins < 12 and j < len(lines):
        year_join = bool(
            _HEADLINE_QUARTER_TAIL_RE.search(headline)
            and _HEADLINE_YEAR_LEAD_RE.match(lines[j])
        )
        verb_year_results_join = bool(
            _HEADLINE_VERB_TAIL_RE.search(headline)
            and _HEADLINE_YEAR_RESULTS_RE.match(lines[j])
        )
        fragment_join = bool(_HEADLINE_FRAGMENT_TAIL_RE.search(headline))
        income_both_join = bool(
            _HEADLINE_INCOME_TAIL_RE.search(headline)
            and _HEADLINE_BOTH_LEAD_RE.match(lines[j])
        )
        pct_join = bool(
            _HEADLINE_PCT_LEAD_RE.match(lines[j])
            and (
                fragment_join or _HEADLINE_WRAP_TAIL_RE.search(headline)
            )
        )
        fresh_headline_block = bool(
            (fragment_join or income_both_join)
            and _HEADLINE_FRESH_HEADLINE_RE.match(lines[j])
        )
        if not (
            _HEADLINE_WRAP_TAIL_RE.search(headline)
            or _HEADLINE_VERB_TAIL_RE.search(headline)
            or _HEADLINE_ORDINAL_TAIL_RE.search(headline)
            or _HEADLINE_CONT_LEAD_RE.match(lines[j])
            or _HEADLINE_FOR_LEAD_RE.match(lines[j])
            or year_join
            or verb_year_results_join
            or fragment_join
            or income_both_join
        ):
            break
        if not (
            len(lines[j]) <= 140
            and not lines[j].rstrip().endswith((".", "!", "?", ":"))
            and (
                year_join
                or verb_year_results_join
                or pct_join
                or not _HEADLINE_CONT_BAD_START_RE.match(lines[j])
            )
            and not _ADMIN_LINE_RE.match(lines[j])
            and not _BOILERPLATE_RE.match(lines[j])
            and not _CONTACT_HEADER_RE.match(lines[j])
            and not _CONTACT_LINE_RE.search(lines[j])
            and not fresh_headline_block
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
    if _QUARTER_TITLE_RE.match(ln):
        return None  # cover title ("First Quarter 2025"), not a company
        # name: the lookahead below would read the date line + page number
        # as masthead residue and the first footnote line ("[1] Adjusted
        # EBITDA is a non-GAAP financial" — unterminated, so
        # headline-shaped) as the real headline, skipping the title.
        # Coinbase's Q2 2025 letter lost its title exactly that way
        # (Q1's "[1] This is a non-GAAP financial measure." ends with a
        # period, so the skip returned None there and the title survived).
        # A quarter title is a document title, never a masthead name.
        # Batch 167.
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
    # Batch 193: Axon's "Quarterly conference call and webcast" section
    # heading (its call notice was collected as guidance once the
    # footnote skip freed the line budget) — the bare "conference call"
    # alternative never matches it because of the "Quarterly" prefix.
    r"quarterly\s+conference\s+call|"
    r"earnings\s+webcast|quarterly\s+highlights|product\s+releases|"
    # Batch 193 (repair spot-check): Applied Materials' guidance
    # section is followed by its results segment table headed "First
    # Quarter Reportable Segment Information" (and "Fourth Quarter and
    # Fiscal 2025 Reportable Segment Information") — the period-label
    # exemption let collection past the guidance table and into the
    # segment actuals ("Net revenue $ 5,356 $ 4,909"). A
    # reportable-segment-information heading is always the
    # reported-quarter results table, never guidance, so it ends the
    # section. Up to five words may precede it.
    r"(?:[a-z0-9]+[\s\-]+){0,5}reportable\s+segment\s+information)\b",
    re.IGNORECASE,
)

# Batch 193 (repair spot-check): General Mills' guidance section is
# followed by its earnings-call notice in a shape none of the
# conference-call tests match — "General Mills will issue pre-recorded
# management remarks today, December 17, 2025, at approximately 6:30
# a.m. Central time ... and will hold a live, webcasted question and
# answer session beginning at 8:00 a.m. ..." — no "conference call"
# phrase ("will hold" + "question and answer session", not "will host"
# + "conference call"), so _is_lede_call_announcement, the "will host
# ... webcast" test and _CONFERENCE_CALL_NOTICE_RE all miss it, and
# the notice (11 GIS quarters) was collected as guidance. The two
# phrases are distinctive enough to search for, with the same
# 120-char start guard as _CONFERENCE_CALL_NOTICE_RE: a guidance
# sentence may point at the call in its tail, and the guard keeps that
# shape (Biogen's FX line) from breaking. "pre-recorded remarks"
# without "management" covers the notice's continuation line ("The
# pre-recorded remarks and the webcast will be made available at ...").
_CALL_QA_SESSION_RE = re.compile(
    r"pre-recorded (?:management )?remarks|webcasted question and answer session",
    re.IGNORECASE,
)

# Batch 193: a next-section heading inside a guidance collection — a
# short unterminated title-case line that is not itself a guidance
# heading and heads a prose or bullet block. Air Products' "Guidance"
# section is two bullets followed by "News and Highlights", "Fiscal
# ... Consolidated Results", "Fiscal ... Results by Business Segment"
# and "Earnings Teleconference" — without this break the collector
# runs 30 lines through the whole results narrative and the 4000-char
# cap truncates it mid-segment-table, so the served "guidance" is
# mostly results prose. The follower test is the precision guard: a
# table header ("U.S. & Canada Property International Property(2)",
# AMT's outlook table) is followed by figure-dense rows, not prose or
# bullets, so it never breaks; a guidance sub-heading that carries
# "Outlook"/"Guidance" is exempt by the vocabulary test. The
# exemptions below are the blast-193 failure modes, each attested:
#   - guidance vocabulary ("Consolidated Fiscal 2024 Outlook",
#     "Long-Term Outlook", "AbbVie Raises 2024 EPS Guidance Floor" —
#     ADP/ABBV's outlook sub-sections end in, or carry, the words);
#   - period labels ("Second Quarter Fiscal 2024" — ACN's outlook
#     period sub-heading);
#   - datelines ("GOODLETTSVILLE, Tenn.--(BUSINESS WIRE)--" — DG's
#     guidance heading precedes the dateline);
#   - a line after a lone bullet marker ("Full year comparable
#     restaurant sales growth ..." — CMG's flattened bullet list puts
#     the "·" on its own line, so the item text follows a marker);
#   - non-title-case metric sub-headings ("Bookings and revenue",
#     "Gross margin", "Share count" — DUOL's outlook metric labels
#     are sentence-case, not headings).
# The follower must be a bullet, a dateline (the next section opens
# with one), or a long terminated prose sentence without $ or %
# (guidance prose almost always carries $ or % in its first line, so
# a $-less terminated sentence after a heading is next-section prose,
# not a wrapped guidance line — DUOL's "Bookings and revenue" is
# followed by an unterminated wrap, so it never breaks).
_GUIDANCE_SMALL_WORDS = frozenset(
    ["a", "an", "the", "and", "or", "of", "for", "by", "in", "on", "to", "with", "vs", "at", "from", "per", "&"]
)
_GUIDANCE_PERIOD_TOKENS = frozenset(
    ["first", "second", "third", "fourth", "full", "q1", "q2", "q3", "q4", "fiscal", "quarter", "year", "fy"]
)


def _is_guidance_period_label(ln: str) -> bool:
    """True for a pure period label ("Second Quarter Fiscal 2024",
    "Q3 FY2025", "Full Year Fiscal 2026") — an outlook period
    sub-heading, never a next-section heading."""
    toks = re.split(r"[\s\-]+", ln.strip())
    if not toks:
        return False
    for tok in toks:
        t = tok.lower()
        if t in _GUIDANCE_PERIOD_TOKENS:
            continue
        if re.fullmatch(r"\d{4}", t) or re.fullmatch(r"fy\d{2,4}", t):
            continue
        return False
    return True


def _is_guidance_title_case(ln: str) -> bool:
    """True when every content word is capitalized (small words excepted)
    — the shape of a section heading. Sentence-case metric labels
    ("Bookings and revenue", "Gross margin") fail it."""
    for w in ln.split():
        w = w.strip("(),:;")
        if not w:
            continue
        if w.lower() in _GUIDANCE_SMALL_WORDS:
            continue
        if w[0].isupper() or w[0].isdigit():
            continue
        return False
    return True


# A dateline with a parenthesized date ("LEHIGH VALLEY, Pa. (November 6,
# 2025) - ..." — APD's results sections open with one): _DATELINE_LEAD_RE
# never matches it (its character class has no parens), so without this
# shape "Fiscal ... Consolidated Results" never breaks and the whole
# results narrative is collected as guidance (APD 2025-09-30 ran to the
# 4000-char cap through full-year and Q4 results plus the CEO quote).
_GUIDANCE_PAREN_DATELINE_RE = re.compile(
    r"^[A-Z][A-Z .'\-]*,\s*[A-Z][A-Za-z.]*\s*\([A-Za-z]+ \d{1,2}, \d{4}\)"
)


# Batch 199: a horizontal rule never opens a section. First Solar's
# guidance table ends with a rule line ("——————————") directly after
# its last row ("Volume Sold 15.6GW to 16.3GW"); the follower test
# treated the rule as a dash-led bullet, so the last table row read as
# a next-section heading and the break dropped it (and the safe-harbor
# paragraph after the footnote block). Rule lines are skipped when
# advancing to the real follower, like admin lines.
_GUIDANCE_RULE_LINE_RE = re.compile(r"^[-–—_=*]{3,}$")


# Batch 200: a results-table period header ("Three months ended
# September 30", doubled "Three months ended ... Nine months ended
# ...") after a heading opens the condensed results table, never
# guidance — GE Vernova's outlook section runs past "Total Company
# Results" into its results table because the follower is a period
# header, not a bullet, dateline or long prose line.
_GUIDANCE_RESULTS_PERIOD_RE = re.compile(
    r"^(Three|Six|Nine|Twelve) months ended "
    r"(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}"
)


# Batch 202: a results-narrative heading ("Revenue Environment and
# Outlook", "Cost Performance and Outlook" — DAL; "Revenue Results
# and Outlook:" — LUV) names a results topic and appends "Outlook",
# but it opens the results commentary that FOLLOWS the guidance
# table, not the guidance section itself. The vocabulary exemption in
# _is_guidance_next_section_heading ("outlook"/"guidance" anywhere in
# the line) kept these from ever qualifying as section-end headings,
# so the stored guidance ran through the narrative to the 4000-char
# cap. A heading whose final conjunct is "and Outlook" and whose
# topic word is a results noun (Environment/Performance/Results) is
# a narrative heading: it may end the section, subject to the usual
# title-case + follower + has-signal gates. Pure outlook headings
# never match — "Guidance and Outlook" (no results noun), "2025
# Outlook" / "Financial Outlook" (no "and Outlook" tail), "DICK'S
# Business: Full Year 2025 Outlook" (colon prefix, period label) —
# and neither does DKS's "Foot Locker Business: Q4 2025 Commentary
# & Outlook" (colon prefix, "Commentary", "&"), whose section is
# genuine outlook content.
_GUIDANCE_NARRATIVE_OUTLOOK_RE = re.compile(
    r"^(?:[A-Z][A-Za-z]* )+(Environment|Performance|Results) and Outlook:?$"
)


def _is_guidance_section_end_follower(lines: list[str], j: int) -> bool:
    """True when the line after a heading candidate opens a new section:
    a bullet, a dateline, or a long terminated prose sentence with no $
    or % (see _is_guidance_next_section_heading)."""
    k = j + 1
    while k < len(lines) and (
        _ADMIN_LINE_RE.match(lines[k])
        or lines[k] == "-more-"
        or _GUIDANCE_RULE_LINE_RE.match(lines[k])
    ):
        k += 1
    if k >= len(lines):
        return False
    nxt = lines[k]
    if _BULLET_LEAD_RE.match(nxt) or nxt.startswith("·"):
        # An em/en-dash or hyphen lead carrying figures is a table row,
        # not a bullet item ("— $(0.57)" — BMY's EPS-bridge figure line
        # after the "BioNTech Acquired IPRD Charge" row label, not the
        # next section's first bullet).
        if nxt[0] in ("—", "–", "-") and ("$" in nxt or "%" in nxt):
            pass
        else:
            return True
    if _DATELINE_LEAD_RE.match(nxt) or _GUIDANCE_PAREN_DATELINE_RE.match(nxt):
        return True
    if _GUIDANCE_RESULTS_PERIOD_RE.match(nxt):
        return True
    # Batch 200: a colon-ended label followed by a quotation is a
    # speaker/section label ("Message From Our CEO:" + the CEO quote)
    # — the quote's first flattened line is a wrapped fragment, so
    # the terminated-prose test below never fires on it. The heading
    # still has to be title-case and colon-ended, so a prose clause
    # that happens to precede a quote never qualifies.
    if (
        lines[j].rstrip().rstrip("”\"'’)]}").endswith(":")
        and nxt.lstrip().startswith(("“", '"', "‘", "'"))
    ):
        return True
    # Batch 201: a quote-led follower ends the section even without a
    # colon-ended heading — Carnival's "Financing and Capital Activity"
    # is followed by the CFO quote, a complete 442-char paragraph
    # carrying $ figures, so neither the terminated-prose test (needs
    # $-less) nor the colon+quote rule fires. A quotation after a
    # heading is a speaker statement, not guidance prose: the opening
    # quote + uppercase first cased char + length >= 60 is the shape.
    # The heading gate (title-case, no guidance vocabulary, no period
    # label) still applies, so a guidance sub-heading followed by a
    # quote never qualifies. Supersedes the batch-200 pinned negative
    # (non-colon heading + wrapped quote).
    if nxt.lstrip().startswith(("“", '"', "‘", "'")):
        first_q = nxt.lstrip("“\"'‘’()[]")
        if len(nxt) >= 60 and first_q[:1].isupper():
            return True
    # Batch 203: a section-tagline follower — a heading followed by a
    # short sentence-case fragment ("Building the future of finance,
    # step by step" — COIN's "Product Update" tagline) and then wrapped
    # prose that terminates within a few lines. The immediate follower
    # is too short and unterminated for the prose test below, and the
    # prose's first flattened line is a wrapped fragment, so neither
    # test fires today and the heading is collected as guidance (COIN
    # 2025-12-31 ends on the bare "Product Update" line — the 30-line
    # budget's last slot). A tagline is short (< 60), unterminated,
    # carries no $/% (a figure line is a table row, not a tagline), is
    # not a bullet/dateline/period header/quote (those are handled
    # above), and is sentence-case, not title-case — a second
    # heading/label is title-case ("Investor Relations", "CEO
    # Comment", "BB+", "Diluted 360.5 361.4"), and a bare page number
    # is title-case by the digit rule. The prose run joins up to 6
    # following lines (admin lines skipped) until sentence
    # termination; it must terminate and total >= 100 chars with an
    # uppercase first cased char. The run may carry $ ("... over $100
    # million in annualized revenue.") — a 100+ char terminated
    # sentence is prose, not a table row. The 100-char floor keeps
    # short colon-terminated pointers ("The following reconciles the
    # drivers of projected MCO Operating Expense growth:", 82 chars)
    # from firing. Two run guards keep the join from crossing a
    # guidance table to a distant disclaimer paragraph: every
    # NON-terminating run line must be >= 50 chars (a wrapped prose
    # line is near column width; a table row is short — BMY's
    # "Other income/(expense) ~($250M) ~($50M)" is 38) and figure-
    # sparse — at most one $/% character per 25 chars (ordinary prose
    # runs about one figure per 50+ chars — GPC's "Global Automotive
    # sales were $3.5 billion, up 0.8% ... with a 2.9% benefit ..." is
    # 3 tokens in 110 chars; a table row is figure-dense — EL's
    # "Forecasted/Adjusted EPS - Non-GAAP $3.10 - $3.35 $ 2.51 24% -
    # 34%" is 4 tokens in 68 chars). A line failing either guard kills
    # the run: the join is not prose, it is a table. The terminating
    # line is exempt from both guards — it is the sentence tail
    # ("revenue.") and may be short or carry the sentence's figures.
    if (
        len(nxt) < 60
        and not _is_sentence_terminated(nxt)
        and "$" not in nxt
        and "%" not in nxt
        and not _BULLET_LEAD_RE.match(nxt)
        and not nxt.startswith("·")
        and not nxt.lstrip().startswith(("“", '"', "‘", "'"))
        and not _DATELINE_LEAD_RE.match(nxt)
        and not _GUIDANCE_PAREN_DATELINE_RE.match(nxt)
        and not _GUIDANCE_RESULTS_PERIOD_RE.match(nxt)
        and not _is_guidance_title_case(nxt)
    ):
        run: list[str] = []
        m = k + 1
        terminated = False
        while m < len(lines) and len(run) < 6:
            if (
                _ADMIN_LINE_RE.match(lines[m])
                or lines[m] == "-more-"
                or _GUIDANCE_RULE_LINE_RE.match(lines[m])
            ):
                m += 1
                continue
            run.append(lines[m])
            if _is_sentence_terminated(lines[m]):
                terminated = True
                break
            if len(lines[m]) < 50 or (
                lines[m].count("$") + lines[m].count("%")
            ) * 25 > len(lines[m]):
                # Not wrapped prose: a short or figure-dense line is a
                # table row, and the run has crossed into a table.
                terminated = False
                run = []
                break
            m += 1
        if terminated:
            joined = " ".join(run)
            first_run = joined.lstrip("“\"'‘’()[]")
            if len(joined) >= 100 and first_run[:1].isupper():
                return True
    # Batch 200: a quote-led paragraph ("“This was another year ..." —
    # Disney's CEO quote after "Message From Our CEO:") opens with a
    # curly quote, so the uppercase test reads the first cased char.
    first = nxt.lstrip("“\"'‘’()[]")
    return (
        len(nxt) >= 60
        and first[:1].isupper()
        and "$" not in nxt
        and "%" not in nxt
        and _is_sentence_terminated(nxt)
    )


def _is_guidance_next_section_heading(lines: list[str], j: int) -> bool:
    ln = lines[j]
    if len(ln) > 90 or _GUIDANCE_HEADING_RE.match(ln):
        return False
    if re.search(r"\b(outlook|guidance)\b", ln, re.IGNORECASE):
        # Batch 202: a results-narrative heading ("Revenue Environment
        # and Outlook" — DAL) is exempted from the exemption: the
        # "Outlook" tail names the commentary section after the
        # guidance table, not the guidance section itself.
        if not _GUIDANCE_NARRATIVE_OUTLOOK_RE.match(ln):
            return False
    # Batch 200: a trailing colon is a heading label, not sentence
    # termination — "Editor's Notes:", "Message From Our CEO:",
    # "Caution Concerning Forward Looking Statements:" all introduce
    # the content that follows them, and the colon is what kept the
    # section-end test from firing on them. A colon-ended line still
    # has to pass the title-case + follower tests below, so a
    # sentence fragment ("We expect the following:") never qualifies.
    _stripped = ln.rstrip().rstrip("”\"'’)]}")
    if _is_sentence_terminated(ln) and not _stripped.endswith(":"):
        return False
    if not ln or not ln[0].isupper() or ln.isupper():
        return False
    if "$" in ln or "%" in ln:
        return False
    if re.search(r"\.(com|net|org|io|co|biz|info)$", ln, re.IGNORECASE):
        # A bare domain ("CrownCastle.com" — CCI's page footer between
        # its outlook tagline and the outlook table's change notes) is
        # page furniture, never a section heading.
        return False
    if _DATELINE_LEAD_RE.match(ln) or _is_guidance_period_label(ln):
        return False
    # A dateline wrapped across lines ("GOODLETTSVILLE, Tenn.--(BUSINESS"
    # / "WIRE)-- ..." — DG's 2026-05-01 release): the candidate alone
    # never matches the dateline regex, so test it joined with its next
    # line, which is how the flattened dateline reads.
    if j + 1 < len(lines) and _DATELINE_LEAD_RE.match(ln + " " + lines[j + 1]):
        return False
    if j > 0 and _is_lone_bullet_marker(lines[j - 1]):
        return False
    if not _is_guidance_title_case(ln):
        return False
    if re.search(
        r"dividend\s+(declaration|payment)|^quarterly\s+dividend$",
        ln,
        re.IGNORECASE,
    ):
        # Batch 199: a dividend declaration ("Quarterly Dividend",
        # "Dividend Declaration" — COR, EXPE) is always the next
        # section, never guidance; its follower paragraph carries
        # "$0.48 per share", so the $-less follower test never fires
        # on it. A "Dividend Policy" sub-heading is not matched.
        return True
    return _is_guidance_section_end_follower(lines, j)


# Batch 193: whether the collected guidance lines (excluding the heading)
# already carry guidance content — a bullet, a $ or % figure, or an
# expectation verb. The safe-harbor intro that opens some outlook
# sections ("This Outlook section contains forward-looking statements
# ...") carries none of these, so a next-section heading before any
# signal does not end the section: Crown Castle's OUTLOOK section
# opens with the intro and a "Restructuring Plan Update" subsection
# BEFORE its outlook table, and breaking there would keep the intro
# and lose the table.
_GUIDANCE_SIGNAL_RE = re.compile(r"expect\w*|anticipat\w*|forecast\w*", re.IGNORECASE)


def _guidance_has_signal(collected: list[str]) -> bool:
    for ln in collected[1:]:
        if _BULLET_LEAD_RE.match(ln) or ln.startswith(("·", "●", "o ")):
            return True
        if "$" in ln or "%" in ln:
            return True
        if _GUIDANCE_SIGNAL_RE.search(ln):
            return True
    return False

# Batch 193: the guidance-heading anchor test. Two attested gaps in
# the bare _GUIDANCE_HEADING_RE match: (1) a quote fragment that
# happens to start with "outlook" ("outlook at the start of the
# year.”" — DAL's CEO-quote tail) is never a heading, so an anchor
# line ending in sentence punctuation + a closing quote is rejected
# — but a plain terminated line stays an anchor, because GEV's
# wrapped "guidance of similar segment EBITDA losses to 2025." is the
# (accidental but working) entry to its segment-outlook section;
# (2) a footnote marker attached to the heading ("Financial
# Guidance1" — DAL's real guidance heading) breaks the regex's \b,
# so the match is also tried with trailing digits stripped. A trailing
# ":" stays a heading (JNJ's "Full-year 2026 guidance:").
# Batch 196: the digit-strip path no longer requires a compound heading.
# Batch 193 required a space in the stripped line (\"Financial Guidance1\"
# — DAL's real heading — vs \"Guidance5\" — CRM's guidance-table column
# header, a table cell not a heading). But Cigna's outlook section is
# headed by the BARE word with a superscript footnote digit (\"OUTLOOK2\"
# in text — the HTML is OUTLOOK<sup>2</sup>), so CI's 2024-12-31,
# 2025-03-31 and 2025-09-30 quarters extracted None while every other
# CI quarter (\"2025 OUTLOOK2\", compound, already accepted) served
# guidance. A census of the 1,699-exhibit cache finds exactly six
# bare-word+digit guidance headings: CI's three OUTLOOK2 (all real
# section headings, followed by outlook prose + metrics table),
# CRM_2024-10-31's two Guidance5 (table column headers INSIDE the
# guidance section — the extractor already anchors on the earlier
# \"Guidance\" heading, so they can never become the anchor), and
# EMR_2025-09-30's \"Guidance 2026\" (also after the earlier \"2026
# Outlook\" anchor). A bare-word+digit line can only anchor when no
# earlier guidance heading exists — i.e. when it IS the section
# heading, as in CI — so accepting the stripped match is safe; the
# full blast (batch 196) verifies only CI's three quarters change.
# Batch 199: a guidance-intro sentence anchors the section when there
# is no heading. First Solar's interim releases introduce the table
# with prose — "Our 2024 guidance has been updated as follows:",
# "Our 2024 guidance remains unchanged. The complete 2024 guidance is
# as follows:", "Our 2026 guidance remains unchanged and is summarized
# below:", "Our updated 2026 guidance is summarized below:" — and no
# bare "2024 Guidance" heading, so 9 of 11 cached FSLR quarters
# extracted None despite carrying a full guidance table. A census of
# the 1,699-exhibit cache finds this shape only in FSLR, and no
# serving exhibit has one before its real anchor, so accepting it is
# safe. The year must follow "Our" (optionally "updated"/"revised")
# and the sentence must close with "as follows" / "summarized below"
# — a bare "Our 2024 guidance was strong." never anchors.
_GUIDANCE_INTRO_RE = re.compile(
    r"^our (?:updated |revised )?\d{4} guidance\b.*\b(as follows|summarized below)\s*:?\s*$",
    re.IGNORECASE,
)


def _is_guidance_heading(ln: str) -> bool:
    if len(ln) > 90:
        return False
    if re.search(r"[.!?…][”\"]\s*$", ln):
        return False
    if _GUIDANCE_HEADING_RE.match(ln):
        return True
    stripped = ln.rstrip("0123456789").rstrip()
    if _GUIDANCE_HEADING_RE.match(stripped):
        return True
    return bool(_GUIDANCE_INTRO_RE.match(ln))


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


_BULLET_RUN_SPLIT_RE = re.compile(r"\s+[•●○]\s+")


def _split_bullet_runs(lines: list[str]) -> list[str]:
    """Split bullet-run mega-lines into one pseudo-line per bullet.

    Slide-deck releases (Bank of America) flatten a whole highlights slide
    into a single line — the bullets are joined by " • " with no line
    breaks, so the headline loop, section extraction, and lede all see one
    giant line and the batch-105 page-line guard discards the release
    entirely (BAC: 8/8 quarters blank). Only lines longer than the headline
    cap with at least two bullet separators are split, so ordinary prose
    and single-bullet lines are untouched. Continuation pieces keep a "• "
    prefix so downstream bullet logic (the lede, the batch-115
    bullet-headline strip) treats them as bullets. Batch 125.

    Batch 197: the separator is any of •/●/○, not just •. Instacart's
    shareholder letter, Booking's release, and Affirm's letter join
    their bullet runs with " ● " (Instacart also " ○ " for sub-bullets),
    so the •-only split never fired and all 10 cached CART quarters, 7
    BKNG quarters, and AFRM 2024-12-31 extracted None — the "Financial
    Highlights" bullets sit mid-line in a mega-line no anchor ever sees.
    The downstream glyph set already treats ●/○ as bullets
    (_BULLET_LEAD_RE, the lone-marker test), so the split only extends
    the batch-125 mechanism to the glyphs the documents actually use.
    """
    out: list[str] = []
    for ln in lines:
        if len(ln) > _MAX_HEADLINE_CHARS and len(_BULLET_RUN_SPLIT_RE.findall(ln)) >= 2:
            pieces = [p.strip() for p in _BULLET_RUN_SPLIT_RE.split(ln)]
            pieces = [p for p in pieces if p]
            if len(pieces) > 1:
                out.append(pieces[0])
                out.extend(f"• {p}" for p in pieces[1:])
                continue
        out.append(ln)
    return out


# Workiva page-flattened releases (batch 163): a whole release page collapses
# into a single mega-line — the dateline lede, the CEO/CFO quotes, the
# headline, and the metric table all run together with no line breaks, so no
# headline line ever exists and the batch-105 page-line guard discards the
# release entirely (Shopify Q3 2024: its only blank quarter, the other 7
# fine). Unlike a slide deck, the page line carries real narrative: it opens
# with a dateline ("Internet, Everywhere - November 12, 2024 - ..."), so the
# salvage below splits ONLY such a line, at sentence boundaries, and keeps
# the narrative sentences. It runs strictly inside the batch-105 guard — a
# document that currently extracts anything never reaches it — so the blast
# radius is exactly the set of documents that currently return None there.
_PAGE_DATELINE_RE = re.compile(
    r"^(?:\d{1,2}\s+)?"  # optional Workiva page number ("1 Internet, ...")
    r"[A-Z][^,]{0,60}?,\s+(?:[^,]{0,60}?\s+-\s+)?"  # city, [tagline -]
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}\s+-\s+"
)
_SENTENCE_END_RE = re.compile(
    r"(?:(?<=[.!?][\"”')\]])|(?<=[.!?]))\s+(?=[A-Z\"“\(\[])"
)
_SENTENCE_ABBREV = frozenset(
    {
        "inc", "corp", "ltd", "co", "llc", "llp", "mr", "mrs", "ms", "dr",
        "jr", "sr", "st", "no", "vs", "e.g", "i.e", "etc", "u.s", "u.k",
        "a.m", "p.m", "jan", "feb", "mar", "apr", "jun", "jul", "aug",
        "sep", "sept", "oct", "nov", "dec", "ave", "blvd", "dept", "fig",
        "eq", "approx", "al", "sen", "rep", "gov",
    }
)
_PAGE_NUMBER_PREFIX_RE = re.compile(r"^\d{1,2}\s+")
_NUMBER_TOKEN_RE = re.compile(r"\b\d[\d,]*\.?\d*%?\b")
_TABLE_HEAD_MARKER_RE = re.compile(
    r"(?:three|nine)\s+months\s+ended|year\s+ended|\(in\s+(?:us\s+)?\$\s|"
    r"selected\s+business\s+performance|condensed\s+consolidated",
    re.IGNORECASE,
)


def _split_page_line_sentences(text: str) -> list[str]:
    """Split a page-flattened mega-line at sentence boundaries.

    A sentence ends on . ! ? (modulo a closing quote/paren) followed by
    whitespace and a capital, opening quote, or opening paren. A terminal
    abbreviation ("Inc.", "U.S.", "Nov.") never splits — the next token is
    a continuation, not a new sentence ("Shopify Inc. (NYSE, TSX: SHOP)"
    stays one sentence).
    """
    pieces: list[str] = []
    start = 0
    for m in _SENTENCE_END_RE.finditer(text):
        before = text[start : m.start()].rstrip()
        word = before.split()[-1] if before else ""
        if word.rstrip(".!?\"”')]").lower() in _SENTENCE_ABBREV:
            continue
        pieces.append(text[start : m.start()].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    return [p for p in pieces if p]


def _salvage_page_line_lede(paragraph: str) -> str | None:
    """Salvage highlights from a page-flattened mega-line paragraph.

    Only a paragraph opening with a dateline qualifies — a slide-deck page
    (Bank of America, batch 105) has none, so it still returns None. The
    dateline sentence plus up to 5 following narrative sentences become the
    lede (the 6-line budget, mirroring the lede); footnote-definition and
    table-residue sentences are dropped, and a release title sitting at the
    head of a table-residue sentence ("... Expands to 19%   Three months
    ended ... GMV 69,715 ...") is rescued as the headline when it is
    headline-shaped. Returns the full result string, or None when the
    paragraph holds no real narrative (single dateline sentence, table-only
    sentences, or under 200 chars of prose).
    """
    if not _PAGE_DATELINE_RE.match(paragraph):
        return None
    # Drop the Workiva page number ("1 Internet, Everywhere ...") so the
    # dateline sentence reads as a dateline, not a page marker.
    paragraph = _PAGE_NUMBER_PREFIX_RE.sub("", paragraph, count=1)
    sentences = _split_page_line_sentences(paragraph)
    if len(sentences) < 2:
        return None
    headline: str | None = None
    body: list[str] = []
    for s in sentences:
        if _BOILERPLATE_RE.match(s):
            break
        if (
            _LEDE_FOOTNOTE_RE.match(s)
            or _FOOTNOTE_DEF_RE.match(s)
            or _LEDE_FOOTNOTE_NUM_RE.match(s)
            or _FOOTNOTE_BRACKET_RE.match(s)
            or _FOOTNOTE_DEF_SENTENCE_RE.match(s)
            or _FOOTNOTE_POINTER_RE.match(s)
            or _is_bare_numbered_footnote(s)
            or _ROUNDING_NOTE_RE.match(s)
        ):
            continue  # footnote-definition sentence, including the
            # bracketed form ("[1] Adjusted EBITDA is ...") and the
            # fourth shape collapsed onto one sentence ("1 Coinbase
            # Total Trading Volume comprises ..."). Batch 166. A
            # rounding-note sentence ("Figures have been rounded for
            # presentation purposes only.", "Note: Figures presented may
            # not sum precisely due to rounding.") is the same
            # boilerplate class. Batch 167. Batch 173: a footnote
            # pointer ("1 See ...") or bare-numbered footnote sentence
            # ("1 Information about Affirm's use of non-GAAP ...") is
            # the same class on a page-flattened line.
        if _is_lede_table_line(s) or len(_NUMBER_TOKEN_RE.findall(s)) >= 6:
            # Table residue — but the release title may sit at its head,
            # ahead of the table. Rescue it as the headline when it is
            # headline-shaped; the table itself is never kept.
            if headline is None:
                head = _TABLE_HEAD_MARKER_RE.split(s, maxsplit=1)[0].strip()
                if head and _looks_like_headline(head):
                    headline = head
            continue
        # The 6-sentence budget caps the body, but scanning continues: a
        # table-residue sentence past the cap may still carry the headline.
        if len(body) < 6:
            body.append(s)
    text = "\n\n".join(body)
    if len(body) < 2 or len(text) < 200:
        return None
    return f"{headline}\n\n{text}".strip() if headline else text


def _is_more_page_section_heading(ln: str) -> bool:
    """True when a line right after a "-more-" page marker opens a new
    section instead of continuing the lede (batch 194).

    The shape mirrors the guidance collector's next-section heading
    (batch 193) but without its follower check: the follower here is
    usually a table, which that check does not accept. A paragraph
    wrapped across the page break is never heading-shaped (its head is
    sentence-case, or its previous line is unterminated — the caller
    also requires the previously collected line to be terminated), and
    a quote-attribution tail ends with a comma or colon, so both stay
    collectable. All-caps lines are excluded the same way: a table
    title after the break is caught by the loop's own table breaks.
    """
    s = ln.strip()
    if not s or len(s) > 90:
        return False
    if _is_sentence_terminated(s) or s.endswith(","):
        return False
    if s.isupper() or _BULLET_LEAD_RE.match(s) or s.startswith("·"):
        return False
    if "$" in s or "%" in s:
        return False
    if _DATELINE_LEAD_RE.match(s) or _GUIDANCE_PAREN_DATELINE_RE.match(s):
        return False
    if _is_lone_bullet_marker(s):
        return False
    return _is_guidance_title_case(s)


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

    # Slide-deck bullet runs collapse into mega-lines (batch 125): split
    # them before any headline/section/lede logic sees them.
    lines = _split_bullet_runs(lines)

    if _is_shareholder_letter(lines):
        # Shareholder-letter mode (batch 94): metric-table "Highlights"
        # sections (Duolingo/Affirm/Coinbase style) parse as bullets.
        # Falls back to the standard path when no metric table parses, so
        # letters without one keep the pre-existing behavior exactly.
        metric = _extract_shareholder_letter_highlights(lines, max_chars)
        if metric is not None:
            return metric
        # Batch 146: flattened summary-table mode (Airbnb style) — a
        # "Key Financial/Business Measures" table with no Highlights
        # heading. Also falls back on any parse failure.
        flat = _extract_flat_summary_table_highlights(lines, max_chars)
        if flat is not None:
            return flat

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
        if _DECK_KEY_FINANCIAL_DATA_RE.match(ln):
            # Deck-title page (U.S. Bancorp): the title is never the
            # headline; the highlights section heading that follows it
            # is, and the body starts AT the heading so the section
            # extractor still finds its content. Batch 130. When no
            # highlights heading follows, fall through to the
            # never-headline skip below instead.
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if nxt and len(nxt) <= 120 and _HIGHLIGHTS_HEADING_RE.search(nxt):
                headline, body_start = nxt, i + 1
                break
        if _NEVER_HEADLINE_RE.match(ln):
            # Never a headline (batch 115): lone punctuation, image-filename
            # tokens, page-header junk, exchange:ticker lines, section
            # labels. Checked before the masthead-name skip — such lines were
            # misread as bare masthead names, jumping the pick onto a
            # contact-detail line (Ross, Welltower, Verizon).
            i += 1
            continue
        wrapped_label = _wrapped_spaced_label_skip(lines, i)
        if wrapped_label:
            # Wrapped spaced-letter document label (Elevance Health Q3 2025:
            # "E A R" / "N I N G S R E L E A S E"); the real headline follows.
            # Batch 110.
            i += wrapped_label
            continue
        block = _footnote_def_block_len(lines, i, include_paren=False)
        if block:
            # Footnote-definition block (GEV's Workiva exhibit opens
            # with "1 Defined as remaining performance obligation (RPO)" /
            # "*Non-GAAP Financial Measure" before the real headline):
            # never headline material — and the block skip takes the
            # wrapped continuations with it, so a wrapped definition
            # never becomes the headline either. Batch 104; batch 162:
            # the bare numbered form ("1) See Table A ...") is the same
            # hazard; batch 166: the whole block, not just the key line.
            # include_paren=False: a paren line stays headline-eligible
            # (batch 126: "(B)Crude oil ..." headlines a supplement
            # packet that must return None; "(2026) ACME CORP ..."
            # headlines are preserved).
            i += block
            continue
        note = _rounding_note_block_len(lines, i) or _asterisk_note_block_len(
            lines, i
        )
        if note:
            # Rounding boilerplate ("Figures have been rounded for
            # presentation purposes ...") and chart asterisk notes ("*
            # Based on the closing price of ...") are never headline
            # material — and a wrapped note's continuations are never
            # the headline either. Batch 167.
            i += note
            continue
        sal = _salutation_block_len(lines, i)
        if sal:
            # Shareholder-letter salutation ("Fellow shareholders,"):
            # never a headline — and a letter that opens with one has
            # no headline at all (NFLX: date / salutation / bullets),
            # so the lede starts after it, like the dateline branch
            # below. Without this the loop picks the salutation as the
            # headline. Batch 169.
            body_start = i + sal
            break
        if _TOC_HEADING_RE.match(ln):
            # Combined release+supplement packet (SPG): skip the table of
            # contents so its heading and entries never become the headline.
            j = _skip_toc(lines, i)
            if j > i:
                i = j
                continue
        if _is_subsidiary_list(ln):
            # Flattened subsidiary-list masthead (Cincinnati Financial):
            # the exhibit header flattens its subsidiary table into
            # " n "-joined company names, one line per table row, ahead of
            # the contact block and the real headline. The second row
            # (90 chars) escapes the company-name masthead branch's 80-char
            # bound and was picked as the headline, dragging the remaining
            # rows, the real headline, and the dateline into the lede.
            # Skip the line; the loop finds the real headline. Batch 134.
            i += 1
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
        if _is_compound_earnings_title(lines, i):
            # Compound earnings-release document title (lululemon Q3:
            # "EARNINGS RELEASE & STOCK REPURCHASE PROGRAM") before the
            # "Exhibit 99.1" marker; the real headline follows the marker.
            # Batch 124.
            i += 1
            continue
        if _is_quarter_earnings_title(lines, i):
            # Abbreviated quarter earnings-release document title
            # (ExxonMobil: "3Q 2024 Earnings Release") after the
            # "EXHIBIT 99.1" marker; the real headline follows a
            # "FOR IMMEDIATE RELEASE" admin line. Batch 127.
            i += 1
            continue
        if _is_dated_press_release_label(ln):
            # Dated press-release document label (Altria/MO: "ALTRIA
            # GROUP, INC. EARNINGS PRESS RELEASE, DATED OCTOBER 31,
            # 2024") ahead of the real headline; the label is never the
            # headline. Batch 129.
            i += 1
            continue
        if _is_address_dateline(ln):
            # Address dateline (M&T Bank/MTB: "One M&T Plaza, Buffalo,
            # NY 14203 July 15, 2026") ahead of the real headline; the
            # dateline is never the headline. Batch 133.
            i += 1
            continue
        if ln.lower() == "earnings release" or _QUARTER_EARNINGS_LABEL_RE.match(ln):
            # "Earnings Release" document label (Mastercard, Amgen, Northrop
            # Grumman) and quarter-prefixed variants ("FIRST QUARTER 2026
            # EARNINGS RELEASE" — Berkshire heads Q1 releases with it): the
            # real headline follows, but not necessarily on the next line —
            # Amgen/Northrop put "Exhibit 99.1" / "News Release" / an address
            # block between the label and the headline. Skip the label and let
            # the loop find the headline; don't require the next line to be
            # headline-shaped (batch 105 did, which left the label as the
            # headline for Amgen/Northrop). Skipped here (not in
            # _ADMIN_LINE_RE) because the same words are a TOC entry title
            # elsewhere. A real headline is never the bare words
            # "Earnings Release" or a quarter-prefixed earnings-release
            # label. Batch 105; generalized batch 110; quarter-prefixed
            # variant batch 112.
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
        table_headline = _skip_contact_table(lines, i)
        if table_headline is not None:
            # Flattened two-column contact table (Akamai Q4): the names row
            # precedes the role row, so no header branch fires on it — skip
            # the table and let the loop pick the real headline. Batch 123.
            i = table_headline
            continue
        page_prefix = _PAGE_PREFIX_RE.match(ln)
        if page_prefix:
            # Page-image exhibit (UnitedHealth, batch 141): the page marker
            # is glued to the headline — "Page 1 of 16 UnitedHealth Group
            # Reports First Quarter 2026 Results" — because the bare-page
            # admin guard is $-anchored and never fires when headline text
            # follows. Strip the marker and run the remainder through the
            # wrap joiner, as the single-word-fragment branch does, so a
            # wrapped remainder ("Page 1 of 16 UnitedHealth Group Reports"
            # / "2025 Results and Issues 2026 Outlook") still joins. The
            # JOINED result must be headline-shaped and must not itself be
            # a dateline — a bare fragment remainder with no continuation
            # ("UnitedHealth Group Reports" alone, 3 words) fails the shape
            # test, so it falls through to the existing pick unchanged and
            # the wrap join happens on the unstripped line instead.
            rest = ln[page_prefix.end():].strip()
            if rest:
                joined, rel_next = _join_wrapped_headline(
                    [rest] + lines[i + 1:], 0
                )
                if _looks_like_headline(joined) and not _DATELINE_RE.match(
                    joined
                ):
                    headline = joined
                    body_start = i + rel_next
                    break
        if len(ln) <= _MAX_HEADLINE_CHARS:
            if _DATELINE_RE.match(ln):
                # Dateline reached with no headline found (Berkshire's
                # releases have no headline at all). A dateline is never a
                # headline — stop here with headline=None; the lede starts
                # after the dateline. Batch 112.
                body_start = i + 1
                break
            headline, next_i = _join_wrapped_headline(lines, i)
            body_start = next_i
        break

    body_lines = lines[body_start:]

    # Batch 142: page markers glued to body lines and view-online
    # trailers glued to bullets are cleaned here — after headline
    # selection, so the headline loop's batch-141 page-prefix guard is
    # untouched. Every body consumer (leading-bullet block, sections,
    # lede) reads body_lines, so one cleaning covers all three paths.
    body_lines = [_clean_body_line(ln) for ln in body_lines]

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
        # Batch 139: the 6-line budget counts content lines only. A lone
        # bullet marker is a separator, not content — counting it (as the
        # old code did for every marker, and for "·"/"○" which were not
        # even recognized) starved Chubb Q3 2024 after bullet 2, although
        # the lede holds 8 bullets. The finish-the-item rule below applies
        # ONLY to marker-delimited ledes: once the budget is reached in a
        # lede that has separators, the current item is finished rather
        # than cut mid-item (up to 4 continuation lines, and a marker at
        # the boundary ends collection without being appended — no
        # dangling marker). A marker-less prose lede keeps the old hard
        # 6-line cap: without item delimiters "finish the item" is
        # undefined, and the ungated version changed 109/232 blast
        # quarters — mostly prose extensions up to the 4000-char cap —
        # for no defect. The gate is what keeps this fix narrow.
        content_lines = 0
        overrun = 0
        marker_seen = False
        # Batch 194: set when a "-more-" page marker is skipped — the
        # next line is judged as a possible new-section heading (below).
        after_more = False
        # Batch 185: set when a flattened table label is skipped — the
        # lines that follow are table rows until real prose (a terminated
        # sentence or a bullet) resumes and clears it.
        in_table = False
        # Batch 191: consecutive lines skipped as table-mode residue
        # since the last non-residue line, with a flag for whether the
        # previous iteration ended in the residue branch. When a
        # terminated line is collected in table mode, the run is the
        # wrapped paragraph's head (batch 186's pretax-paragraph wart):
        # the tail alone is a dangling fragment, so the head is
        # prepended — budget-neutral, only the tail counts.
        table_residue_run: list[str] = []
        prev_was_residue = False
        # Batch 185: set when a real table row (a _is_lede_table_line
        # skip — a data row, unit line or period header) is seen while
        # in table mode. Mode residue (labels, TOC entries) does not
        # count: a TOC-only packet enters mode on its supplement title
        # and skips nothing but residue, so prose reached with no
        # table row seen is filler after a TOC, not narrative after a
        # table (batch 126 guard — see the normal-append break below).
        table_seen = False
        # Batch 165: decided once, at the first line past the budget —
        # whether the item at the budget is unfinished. finish_sentence
        # is the wrap-tail trigger: the unfinished item is a sentence,
        # so collection stops once a continuation line terminates it.
        finish_item: bool | None = None
        finish_sentence = False
        i = 0
        while i < len(lede_lines):
            ln = lede_lines[i]
            # Batch 191: the residue run only spans consecutive
            # residue-skipped lines — any other branch (a table row, a
            # header skip, a collected line) breaks it.
            if not prev_was_residue:
                table_residue_run = []
            prev_was_residue = False
            if _ADMIN_LINE_RE.match(ln):
                i += 1
                continue  # stray exhibit headers / page numbers mid-document
            if ln == "-more-":
                # Batch 194: a page-continuation marker, never content
                # (the guidance collector skips it since batch 193; the
                # lede loop never did — APD Q2 FY2026 served it plus
                # the next section's heading as highlights). It never
                # consumes budget, and the line after it is judged as a
                # possible new-section heading below.
                after_more = True
                i += 1
                continue
            if after_more:
                # Consumed by the very next line, whatever branch takes
                # it — except a bare company-name page header, which is
                # skipped transparently so the line after IT is judged
                # (CarMax: "CarMax, Inc." + "Page 2 of 13" head page 2).
                if _is_trailing_company_signature(ln):
                    i += 1
                    continue
                # A heading-shaped line after a page break ends the lede:
                # the previous section is over and the heading's content
                # belongs to the next section
                # (APD: "Fiscal 2026 Second Quarter Results by Business
                # Segment" after the CEO quote). Not in table mode — a
                # table label after the break is residue, not a heading
                # (batch 185: prose after a table is still collected).
                after_more = False
                if (
                    not in_table
                    and lede
                    and _is_sentence_terminated(lede[-1])
                    and _is_more_page_section_heading(ln)
                ):
                    break
            if in_table and _is_lede_nongaap_section_heading(ln):
                # Batch 185: the non-GAAP definitions section is
                # boilerplate — nothing after it is highlights (EOG's
                # supplement packet: the TOC + tables fill the lede, and
                # the definitions prose would otherwise be served once
                # table mode skips the tables). Only in table mode: a
                # definitions heading ahead of the narrative is not a
                # reason to stop. This sits at the top of the loop body
                # because _is_lede_title_line (batch 178) also matches
                # the bare heading and would skip it before the break
                # below could run.
                break
            block = _footnote_def_block_len(lede_lines, i)
            if block:
                i += block
                continue  # footnote-definition block ("1 Defined as ...",
                # "*Non-GAAP Financial Measure", "1) See Table A ...",
                # "[1] Adjusted EBITDA is ...", "1 Coinbase Total Trading
                # Volume / comprises ..." plus wrapped continuations and
                # chained term definitions) is never lede content. The
                # block skip is what keeps the batch-165 finish rule from
                # pulling a footnote block in as a "continuation" of the
                # item at the budget: the key line and its continuations
                # are skipped before the budget logic ever sees them.
                # Batch 162 (bare numbered form); batch 166 (the block).
            block = _glossary_def_block_len(lede_lines, i)
            if block:
                i += block
                continue  # Batch 188: a run of >=3 "Term - definition"
                # glossary lines (AJG's adjustment-item definitions after
                # the recon tables) is never lede content — without the
                # skip, the freed budget from the batch-188 header fixes
                # let the loop fill itself with glossary paragraphs.
            note = _rounding_note_block_len(lede_lines, i) or (
                _asterisk_note_block_len(lede_lines, i)
            )
            if note:
                i += note
                continue  # rounding note ("Figures have been rounded ...",
                # "Note: Figures presented may not sum precisely due to
                # rounding.") or chart asterisk note ("* Based on the
                # closing price of ...") — boilerplate, never lede
                # content. The lede's table-line rule already drops the
                # asterisk opener, but its wrapped continuations were
                # served; the block skip takes them with it. Batch 167.
            sal = _salutation_block_len(lede_lines, i)
            if sal:
                i += sal
                continue  # shareholder-letter salutation ("Fellow
                # shareholders,", "Dear Shareholders," — or the split
                # "Fellow" / "Shareholders," form) is a greeting, never
                # lede content. Batch 169.
            if _CONFERENCE_CALL_NOTICE_RE.search(ln) or _is_lede_call_announcement(ln):
                i += 1
                # Batch 182: a split notice's webcast second half
                # ("In conjunction with the call, a live webcast ...")
                # is the same notice — consume it with the announcement
                # so it never dangles as a lede line.
                if i < len(lede_lines) and _is_lede_webcast_continuation(
                    lede_lines[i]
                ):
                    i += 1
                continue  # investor-conference-call notice (Emerson: the
                # "Today, beginning at 3:30 p.m. ... will discuss the ...
                # results during an investor conference call ... live
                # webcast ... replay ..." line) is never highlights; it
                # backfills the lede once the footnotes are dropped.
                # Batch 166.
            if _INVESTOR_CONFERENCE_NOTICE_RE.search(ln):
                i += 1
                continue  # investor-conference notice (Emerson: "will
                # hold an in-person and virtual investor conference on
                # Thursday, Nov. 20 ..." / "will host an investor
                # conference on Nov. 20, 2025 ...") — an event
                # announcement, never highlights; the batch-166 regex
                # needs "conference call", so this shape slipped
                # through. Batch 181.
            if _is_lede_report_pointer(ln):
                i += 1
                continue  # Batch 182: a pointer sentence to the full
                # report ("This earnings announcement ... is contained
                # in the CSX Quarterly Financial Report ...") is
                # document-tail boilerplate, never highlights.
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
            if _is_bare_role_line(ln):
                i += 1
                continue  # bare quote-attribution role line ("Chief
                # Financial Officer", "President and Chief Executive
                # Officer" — Moody's, 6 stored rows): the name is
                # missing, so the role alone is a dangling fragment,
                # never highlights. Batch 173.
            if _is_lede_heading_fragment(ln):
                i += 1
                continue  # section-heading tail ("QUARTER", "YEAR") — never prose
            if _HIGHLIGHTS_HEADING_RE.search(ln) and len(ln) <= 120:
                i += 1
                continue  # Batch 156: a "Highlights" section heading is
                # never lede prose — after a table-headed section is
                # rejected, its heading would otherwise consume a lede
                # line and starve the real bullets below the table.
            if re.fullmatch(r"Key Points:?", ln.strip(), re.IGNORECASE):
                i += 1
                continue  # Batch 173: a "Key Points:" section heading is
                # the same class — Disney's Q4 FY2024 lede ends on the
                # dangling heading while its bullets starve below it.
                # Skipping it lets the bullets in.
            if _is_lede_colon_heading(ln):
                i += 1
                continue  # Batch 177: a colon-ended list-intro /
                # section heading ("Financial Results for the
                # Quarter:", "Fiscal 2026 outlook:", "Business
                # highlights included the following:") carries no
                # figures and no news — the list below it is the
                # content. Skipping it frees a lede line for a real
                # bullet. A quote attribution ("... said:") never
                # qualifies — the veto is in the predicate.
            if _is_lede_table_header(ln):
                i += 1
                continue  # Batch 177: a summary-table column-header
                # line ("MCO Diluted EPS MCO Adjusted Diluted EPS2",
                # "Impact After-Tax Diluted EPS") is two column
                # labels flattened onto one line, not narrative.
            if _is_lede_title_line(ln):
                i += 1
                continue  # Batch 178: an exhibit title line ("Capital
                # One Third Quarter 2024 Earnings") is the document's
                # own title served mid-lede once the budget frees up —
                # never highlights. The verb veto in the predicate keeps
                # sub-headlines ("Q2 ORGANIC SALES AND ADJUSTED EPS
                # EXCEED OUTLOOK") in the lede.
            if _is_lede_conf_call_heading(ln):
                i += 1
                continue  # Batch 181: a conference-call section
                # heading ("Conference Call and Upcoming Events") heads
                # the boilerplate tail (call notice, investor-conference
                # notice, About, forward-looking statements) — never
                # highlights. The quarter/results guard in the
                # predicate keeps call announcements in the lede.
            if _is_lede_recon_heading(ln):
                # Batch 182: a reconciliation-table section heading
                # ("GAAP/Adjusted (non-GAAP) Operating Earnings
                # Reconciliation", "Reconciliation of Commissions and
                # Fees") — the table's own title, never highlights.
                # SKIPPED, not a break: the table's rows are skipped
                # below and real prose after the table is still
                # collected (CSX's CEO quote and volume paragraph
                # follow its recon table — a break would lose them).
                # A wrapped heading's continuation ("to Organic
                # Revenue") goes with it — at most two lines, only
                # while the wrap shape holds.
                # Batch 188: entering table mode — the recon table's
                # row labels follow the heading, and a label whose
                # next line is another label (AJG's nested "Base
                # Commissions and Fees" / "Less supplemental
                # revenues ..." chain) matches no table predicate, so
                # without the mode it is served as content once the
                # budget frees up. In table mode the unterminated
                # labels are residue; terminated prose after the table
                # still clears the mode and is collected.
                in_table = True
                table_seen = False
                i += 1
                wraps = 0
                while (
                    wraps < 2
                    and i < len(lede_lines)
                    and _is_recon_heading_wrap(lede_lines[i])
                ):
                    i += 1
                    wraps += 1
                continue
            if _is_lede_segment_heading(ln):
                i += 1
                continue  # Batch 182: a business-segment section
                # heading ("North America Automotive Parts Group
                # (\"North America Automotive\")" — Genuine Parts) heads
                # the segment paragraph below it, which is real content
                # — so only the heading is skipped, freeing the budget
                # line the dangling heading consumed.
            if _is_lede_table_title(ln):
                # Batch 159: a table's title line means the narrative
                # lede is over and a table begins (Southern Company:
                # the title plus the table's rows filled the 6-line
                # budget after two good prose paragraphs). Break once
                # content exists; before any content, skip the title
                # and keep looking — the table's rows are skipped below
                # and real bullets after the table are still collected.
                # Batch 188: AJG's "Summary of Financial Results"
                # title is skipped, never a break — it heads the
                # summary table at the top of the release (or the
                # six-months table mid-release), and the narrative
                # lede (pretax paragraphs, CEO quote) follows the
                # table. The dateline paragraph's tail lines are
                # collected as content ahead of the title in the older
                # quarters, so the break-on-content rule would fire on
                # boilerplate, not narrative, and lose the quote
                # (blast 188: 10 quarters). The generic table-title
                # break stays for titles that follow real prose.
                if lede and not _is_lede_summary_results_title(ln):
                    break
                i += 1
                continue
            if _is_lone_bullet_marker(ln):
                if not lede:
                    i += 1
                    continue  # leading marker with no item yet — carries no content
                if content_lines >= 6:
                    break  # budget reached at an item boundary — stop clean
                # Batch 140: a mid-lede marker is a separator, never stored.
                # Paragraphs are already blank-line separated, so appending
                # it produced a junk glyph paragraph in 42 stored rows
                # (SPG/NUE/CB/CI/SNPS/...). marker_seen is still set: the
                # marker still delimits items for the finish rule below.
                marker_seen = True
                i += 1
                continue  # separator between bullets — never consumes budget
            if _BOILERPLATE_RE.match(ln):
                break
            if _is_lede_table_label(
                ln, lede_lines[i + 1] if i + 1 < len(lede_lines) else ""
            ):
                i += 1
                continue  # a table row's label line (its values are the
                # next line, itself a data row) — batch 160
            if _is_lede_flat_table_label(
                ln, lede_lines[i - 1] if i > 0 else ""
            ):
                # Batch 185: a flattened table row's label directly below
                # a table header block (Brown & Brown: the label's
                # $-values were already dropped as a fragment run, so the
                # label is the only table line the loop can still see —
                # skipping it alone just lets the next table's labels
                # fill the budget instead). Skip it and enter table mode:
                # the lines that follow are table rows until real prose
                # resumes. NOT a break — a quote or paragraph after the
                # table (CSX) is still collected; the batch-159
                # table-title break would lose it, and the v1 break did
                # (AAPL/AXP/CCI/COF/CSX/EL/FDX, blast 185).
                in_table = True
                table_seen = False
                i += 1
                continue
            if _is_lede_table_line(ln):
                if in_table:
                    table_seen = True
                i += 1
                continue  # table residue (unit lines, outlook-table
                # headings/headers, data rows) never consumes lede budget
                # and never gets stored — batch 153
            if in_table and _is_lede_table_mode_residue(ln):
                # Batch 185: inside a table region, an unterminated or
                # colon-ended line is another table row, not narrative —
                # skip it and stay in table mode. Terminated prose and
                # bullets fall through below, are collected, and clear
                # the mode.
                # Batch 191: remember the skipped line — it may be the
                # wrapped head of the paragraph whose terminated tail
                # is collected below.
                table_residue_run.append(ln)
                prev_was_residue = True
                i += 1
                continue
            if _is_lede_dollar_range_statement(ln) and not any(
                _is_sentence_terminated(x) for x in lede
            ):
                # Batch 183: a guidance-range sub-headline ("Reaffirms
                # 2026 Outlook for Adjusted EPS of $7.50 to $8.00") is
                # served but never consumes lede budget — it sits with
                # the headline, and counting it starved the results
                # paragraph (AXP's dateline), the CEO quote (BBY) or
                # the final bullet (GPC). Bounded to the pre-body zone
                # (no terminated line collected yet): a range statement
                # past the dateline is body prose, not a sub-headline.
                lede.append(ln)
                in_table = False  # Batch 185: narrative resumes.
                table_seen = False
                i += 1
                continue
            if content_lines >= 6:
                if finish_item is None:
                    # First line past the budget: decide once whether the
                    # item at the budget is unfinished. A lone-marker lede
                    # (batch 139) always finishes; otherwise only a line
                    # that ends grammatically unfinished (wrap tail) does
                    # — a complete figure bullet ("•Share repurchases and
                    # dividends of $5.1B") or a complete clause (ending in
                    # "respectively") ends the item, so the prose or tables
                    # that follow are never pulled in as "continuation".
                    # The decision is snapshotted: a continuation line's own
                    # ending is an arbitrary wrap point, not evidence the
                    # item finished. Batch 165. Batch 180: a quote
                    # attribution ("... commented on the results:") is an
                    # unfinished item too — its colon introduces the quote
                    # — even though neither the wrap tail nor the sentence
                    # rules see it that way.
                    finish_item = (
                        marker_seen
                        or bool(_LEDE_WRAP_TAIL_RE.search(lede[-1]))
                        or bool(_LEDE_QUOTE_ATTRIBUTION_TAIL_RE.search(lede[-1]))
                        or _is_lede_split_quote_attribution(lede[-1])
                        # Batch 188: an open quote is unfinished by
                        # definition — the budget line opened a quote
                        # that hasn't closed (AJG 2024: the budget
                        # lands mid-quote once the title drops, and
                        # without this the quote is cut at "bedrock
                        # culture"). Batch 181 already suppresses the
                        # sentence-terminated break while a quote is
                        # open; this extends the same insight to the
                        # finish decision. The 4-line overrun cap
                        # still bounds the pull-in.
                        or _lede_quote_is_open(lede)
                    )
                    finish_sentence = not marker_seen and finish_item
                if not finish_item:
                    break  # the item at the budget is complete — a prose
                    # lede keeps the hard 6-line cap. Batch 165.
                if _is_inline_bullet_start(ln):
                    break  # a new bullet starts past the budget — stop at
                    # the item boundary rather than starting a bullet we
                    # cannot finish. Batch 165.
                if finish_sentence and _is_sentence_terminated(lede[-1]) and not _LEDE_QUOTE_ATTRIBUTION_TAIL_RE.search(lede[-1]) and not _lede_quote_is_open(lede):
                    break  # the unfinished sentence just terminated — the
                    # next line starts a new item, not a continuation.
                    # Batch 180: a quote attribution ("... commented on
                    # the results:") is not terminated here — the colon
                    # introduces the quote, so an attribution landing on
                    # the budget line still pulls its quote in. Any other
                    # colon-ended item (a table intro like Berkshire's
                    # "Net earnings includes:") keeps the old stop: its
                    # continuation is the table's label lines, not prose.
                    # (The _is_sentence_terminated ":" branch stays: for
                    # the table-line gate a colon-ended line is a complete
                    # heading unit.)
                    # Batch 181: an open quote suppresses the stop too —
                    # a multi-sentence quote's first sentence terminating
                    # does not end the quote ("…Emerson Management
                    # System." is followed by "Emerson's leading
                    # technology … fiscal 2025." in the same quote), so
                    # the next line still belongs to the item. The
                    # overrun cap (4 lines) still bounds the pull-in.
                    # Batch 165.
                if overrun >= 4:
                    break  # finishing cap: at most 4 lines past the budget
                lede.append(ln)
                in_table = False  # Batch 185: narrative resumes.
                table_seen = False
                overrun += 1
                i += 1
                continue
            if (
                in_table
                and content_lines == 0
                and not table_seen
                and not _is_inline_bullet_start(ln)
            ):
                # Batch 185: prose reached in table mode with no content
                # collected and no real table row seen since the mode
                # started is filler after a TOC, not narrative after a
                # table. A supplement packet enters mode on its
                # supplement title ("Supplemental Financial and Operating
                # Data Page"), skips its TOC entries as residue, and
                # would otherwise serve the boilerplate/filler that
                # follows (batch 126: a TOC-only packet must stay None).
                # A real table leaves table rows behind (data rows, unit
                # lines, period headers set table_seen), so a quote or
                # paragraph after it is still collected (CSX); bullets
                # are exempt — a bullet is a narrative item, never
                # filler. Once any content exists the mode is a table
                # inside a real lede, and prose after it is collected
                # as before (BRO's pointer sentence).
                break
            if in_table:
                # Batch 191: the line being collected may be the tail of
                # a paragraph whose wrapped head lines were skipped as
                # table-mode residue — serve the whole paragraph, not
                # the dangling tail alone. Budget-neutral: only the
                # tail counts against the 6-line budget, so the CEO
                # quote after the paragraph keeps exactly the budget
                # it had. (The TOC-filler break above already ran, so
                # this only fires once real content exists.)
                head_lines = _lede_wrapped_paragraph_head(table_residue_run, ln)
                if head_lines:
                    lede.extend(head_lines)
            lede.append(ln)
            in_table = False  # Batch 185: narrative resumes.
            table_seen = False
            content_lines += 1
            i += 1
        lede = _trim_lede_table_tail(lede)
        body = "\n\n".join(lede)

    # A trailing comma means the headline's continuation was too long to join
    # (URI Q4 2025: 166-char sub-headline). Strip it — a headline never ends
    # with a comma. Batch 106.
    if headline:
        headline = headline.rstrip().removesuffix(",").rstrip()
        # A picked headline that is really a lead bullet (Palantir's
        # "• U.S. revenue grew ...", Skydance's summary points): strip the
        # bullet marker — it reads as the headline, not as a list item.
        # Batch 115.
        headline = re.sub(r"^[•\-*]\s*", "", headline).strip()
    result = f"{headline}\n\n{body}".strip() if headline else body.strip()
    # Batch 157: drop horizontal-rule lines and trim a trailing table
    # stub (lone table-intro sentence / dangling heading) from the
    # assembled body — the headline itself is never trimmed.
    result = _clean_highlights_result(result)
    if len(result) < 200:
        logger.info("Press-release highlights too short after extraction")
        return None
    first_para = result.split("\n\n")[0]
    if (
        not headline
        and first_para
        and max(len(ln) for ln in first_para.split("\n")) > 1000
        and not any(
            _BULLET_LEAD_RE.match(ln) for ln in first_para.split("\n")
        )
    ):
        # Page-image exhibit (Bank of America slide deck): the "lines" are
        # whole pages with no usable headline. A page-LINE is not a highlight;
        # return None so the UI shows "Not available" instead of garbage.
        # Batch 105. Batch 169: the bound is on the longest LINE, not the
        # paragraph — the section path joins a bullet list with "\n", so a
        # 1385-char bullet list reads as one paragraph although no line
        # exceeds 350 chars (NFLX Q3 FY2024: headline-less once the
        # salutation fix stops the greeting becoming the headline, its
        # bullets were discarded as a "page-line"). A single line over
        # 1000 chars still trips the guard exactly as before.
        # Batch 197: a bullet-led line exempts the paragraph — a real
        # section's narrative paragraphs are flattened mega-lines too
        # (Instacart's "Financial Update" prose runs 1200–2500 chars a
        # line), so the guard discarded all 6 remaining CART quarters
        # although their sections open with 8 genuine financial bullets.
        # A page-line dump has no bullet lines (BAC's deck bullets became
        # the headline via batch 125, so the guard never sees them; a
        # risk-factor bullet run like Ford's early releases still returns
        # None through the other gates, not this one).
        # Batch 163: a Workiva page-flattened release is the same shape but
        # carries real narrative behind a dateline — salvage its lede (and
        # an embedded title) instead of discarding it; a dateline-less page
        # line still returns None below.
        salvaged = _salvage_page_line_lede(first_para)
        if salvaged is not None:
            return salvaged
        logger.info("Press-release highlights are page-lines without a headline")
        return None
    if headline and _FOOTNOTE_HEADLINE_RE.match(headline):
        # Supplement-only packet (EOG): the headline loop's best pick is a
        # table footnote definition ("(B)Crude oil ..."), which means the
        # document has no narrative headline — its release text lives in
        # image pages and only the supplement tables are text. A footnote
        # definition is never a headline; returning it as one presents
        # table notes as highlights. Batch 126.
        logger.info("Press-release headline is a footnote definition")
        return None
    if headline:
        # Same packet, other shape (EOG Q3 FY2024): the TOC subtitle became
        # the headline and the lede is just the TOC entries. A table of
        # contents is not highlights. The all-lines bound is load-bearing:
        # a real lede never consists entirely of title + page-number lines.
        # Batch 126.
        _body_parts = [p.strip() for p in result.split("\n\n")[1:] if p.strip()]
        if len(_body_parts) >= 2 and all(
            _TOC_ENTRY_RE.match(p) for p in _body_parts
        ):
            logger.info("Press-release body is only a table of contents")
            return None
    if len(result) > max_chars:
        result = result[:max_chars].rsplit(" ", 1)[0].rstrip() + "…"
    return result


def _financial_line_count(lines: list[str]) -> int:
    """Count lines carrying reported financial figures (see _FINANCIAL_LINE_RE)."""
    return sum(1 for ln in lines if _FINANCIAL_LINE_RE.search(ln))


def _item_has_open_quote(item_text: str) -> bool:
    """True when item_text leaves a quotation open.

    Curly quotes nest by depth ("\u201c opens, \u201d closes); a straight
    double quote toggles the depth, so a lone " is an opener and a pair is
    balanced. Mixed forms compose: a curly opener closed by a straight
    quote still balances. Batch 158.
    """
    depth = 0
    for ch in item_text:
        if ch == "\u201c":
            depth += 1
        elif ch == "\u201d":
            depth = max(0, depth - 1)
        elif ch == '"':
            depth = 0 if depth else 1
    return depth > 0


# Bullet starts for the leading-bullet block (batch 170): "◦" (white
# bullet, U+25E6) joins "•"/"-"/"*". Netflix nests "◦" sub-bullets
# under "•" items, and the item-close rule treated a terminated "◦"
# line followed by another "◦" line as the end of the block — the
# block truncated at the first sub-bullet and the rest of the list
# was lost (6 NFLX rows refused by the batch-169 preservation gate).
# Distinct from "○" (white circle, U+25CB), which the lone-marker
# rule already covers. The "·"/"▪"/"●" glyphs are NOT added: they are
# top-level bullets served fine by the lede path, with no attested
# leading-block truncation — a separate design if one is ever found.
_LEADING_BULLET_STARTS = ("•", "-", "*", "◦")


def _current_leading_item_text(bullets: list[str]) -> str:
    """The current item of a leading-bullet block: from the last bullet
    start line to the end. The item-close rule judges the quote state of
    the item, not the whole block — an earlier item's closed quote must
    not keep a later item open. Batch 158.
    """
    start = 0
    for i, ln in enumerate(bullets):
        if ln.startswith(_LEADING_BULLET_STARTS):
            start = i
    return "\n".join(bullets[start:])


def _leading_bullet_block(lines: list[str]) -> list[str] | None:
    """Consecutive bullet lines immediately after the headline.

    Some filers (Halliburton) open the release with the financial bullets
    ("Net income of $0.64 per diluted share ...") before any "Highlights"
    heading, which may later introduce a purely business section. Bullet
    items may wrap across lines ("... free cash flow1 of / approximately
    $582 million."): a non-bullet line following a bullet start is a
    continuation unless it closes the item (terminal punctuation) and the
    next line isn't a new bullet — that's the dateline paragraph starting.
    A dateline *sentence* before the bullets (Prudential: "NEWARK, N.J. –
    ... today reported ...") is skipped so the bullets still count as the
    leading block. Returns the block only when substantial — otherwise None.
    """
    bullets: list[str] = []
    in_item = False  # previous line was a bullet start or continuation
    n = len(lines)
    skip_until = 0  # footnote-definition block span (batch 166)
    for idx, ln in enumerate(lines):
        if idx < skip_until:
            continue  # inside a skipped footnote-definition block
        if _ADMIN_LINE_RE.match(ln) or _CONTACT_LINE_RE.search(ln):
            continue
        if _BOILERPLATE_RE.match(ln):
            break
        if _HIGHLIGHTS_HEADING_RE.search(ln) and len(ln) <= 120:
            break  # a headed section follows; it competes on its own
        if not bullets and _DATELINE_LEAD_RE.match(ln):
            continue  # dateline sentence before the bullets (Prudential):
            # the bullets are still the leading block, not the dateline
            # prose. Only before any bullet is collected; mid-block lines
            # keep the existing continuation behavior. Batch 118.
        if not bullets and _is_lede_period_header(ln):
            continue  # bare period label between the dateline and the
            # bullets (Amazon Q4: "Fourth Quarter 2024" sits on its own
            # line after the dateline; the lede loop already drops it via
            # _is_lede_table_line). Only before any bullet is collected;
            # mid-block lines keep the existing continuation behavior.
            # Batch 172.
        if not bullets and _is_lede_colon_heading(ln):
            continue  # Batch 195: a colon-ended list-intro heading
            # ahead of the bullets ("Q1 FY25 (comparisons versus prior
            # year):" — Air Products) carries no figures and no news;
            # the list below it is the content. The lede loop already
            # skips such headings (batch 177); the leading-bullet block
            # never did, so the intro line broke the block at its first
            # line and the financial bullets under it never competed.
            # Only before any bullet is collected — a mid-block colon
            # line is a continuation and is dropped post-selection by
            # the batch-177 rule. When the line after the intro is not
            # a bullet, the else branch below breaks the block exactly
            # as before, so the skip alone can never create a block.
        block = _footnote_def_block_len(lines, idx)
        if block:
            # Footnote definition after a bullet ("1) See Table A ...",
            # "1 Non-GAAP measures are detailed ...", "1 Coinbase Total
            # Trading Volume / comprises ...") is table residue, not a
            # bullet continuation — skip the whole block (key line plus
            # wrapped continuations) and keep collecting the block. The
            # item stays open across the skip. Batch 164 (single-line
            # form); batch 166 (the block).
            skip_until = idx + block
            continue
        note = _rounding_note_block_len(lines, idx) or _asterisk_note_block_len(
            lines, idx
        )
        if note:
            # Same hazard as a footnote block, one path earlier: a
            # rounding note ahead of the bullets would break the block
            # (prose first line, no bullet yet), and an asterisk note
            # ("* Based on the closing price of ...") would start a
            # bullet item. Skip the whole block and keep collecting.
            # Batch 167.
            skip_until = idx + note
            continue
        sal = _salutation_block_len(lines, idx)
        if sal:
            # Shareholder-letter salutation after the bullets (AXON:
            # "Fellow shareholders," follows the last bullet and the
            # block would append it as a wrap continuation). Skip the
            # whole block and keep collecting — the prose paragraph
            # after it still closes the last item. Batch 169.
            skip_until = idx + sal
            continue
        if _LEDE_SYMBOL_LEGEND_RE.match(ln):
            continue  # symbol legend ("NM = not meaningful",
            # "“cc” - constant currency" — Walmart's legend after its
            # footnote run): the table's own footnote, never a bullet
            # continuation. Batch 173.
        if _is_bare_role_line(ln):
            continue  # bare quote-attribution role line — the same
            # dangling fragment as in the lede loop (Moody's).
            # Batch 173.
        if ln.startswith(_LEADING_BULLET_STARTS):
            bullets.append(ln)
            in_item = True
        elif in_item:
            nxt = lines[idx + 1] if idx + 1 < n else ""
            if (
                _TABLE_UNITS_RE.match(ln)
                or _TABLE_WORD_UNITS_RE.match(ln)
                or (
                    _is_lede_table_heading(ln)
                    and not _next_content_line_is_bullet(lines, idx)
                )
                or _is_lede_period_header(ln)
                or _is_bare_period_fragment(ln)
            ):
                break  # a table starts where the bullets end (AppLovin's
                # "First Quarter 2026 Financial Guidance Summary" heading
                # after the bullets): the block ends here, the heading is
                # not a bullet continuation. Only the strong heading shapes
                # break — data rows and labels stay out, so a figure-dense
                # bullet continuation is never cut. Batch 153. Batch 174:
                # a bare period fragment ("Three Months") is the same
                # signal — BlackRock's nonoperating-income table header
                # follows the expense bullets, and the fragments tail the
                # block as continuations. Batch 195: the table-heading
                # break fires only when the next content line is NOT a
                # bullet — a bare "Guidance" heading that introduces
                # bullets (Air Products) is a sub-heading, not a table
                # title, so the heading is kept as a label line and the
                # bullets below it stay in the block.
            bullets.append(ln)
            if (
                # Batch 158: the terminal-punctuation check sees through a
                # closing quote ("." / ".”) — without it a quote that opens
                # and closes on one line never closes the item itself, and
                # the next prose line leaks in before the rule fires.
                re.search(r"[.!?;][\u201d\"']?\s*$", ln)
                and not nxt.startswith(_LEADING_BULLET_STARTS)
                # Batch 158: don't close the item while its quote is still
                # open — a multi-line CEO quote (GOOGL Q2 FY2026: the
                # opener ends "... across every part of our business." and
                # the quote runs three more lines) would otherwise truncate
                # at its first terminated line. The 14-line cap and the
                # heading/boilerplate breaks above still bound the block,
                # so an unclosed quote cannot run away.
                and not _item_has_open_quote(_current_leading_item_text(bullets))
            ):
                break  # item closed and prose follows (dateline)
        else:
            break  # first line isn't a bullet — no leading block
        if len(bullets) >= 14:
            break
    if len("\n".join(bullets)) >= 150:
        # Batch 140: drop lone-marker lines AFTER qualification, so the
        # 150-char floor and the item-close logic above see the same
        # lines as before — only the junk glyph lines disappear. A
        # flattened bullet list ("•" alone, then the item text) otherwise
        # stores a glyph line per item.
        return [ln for ln in bullets if not _is_lone_bullet_marker(ln)]
    return None


def _is_section_footnote_line(ln: str) -> bool:
    """True for a table-footnote definition inside a Highlights section:
    parenthesized ("(1) During the year ..."), definition-verb ("1
    Defined as ...", "*Non-GAAP Financial Measure"), bare numbered
    ("1) See Table A ..."), or copula-pointer ("1 Non-GAAP measures are
    detailed ...", batch 164). A footnote definition is never a highlight —
    Datadog's M&A-costs footnote sits between its section bullets — so
    it is dropped after qualification, like the lone-marker lines
    (batch 140). Batch 162."""
    return bool(
        _LEDE_FOOTNOTE_RE.match(ln)
        or _FOOTNOTE_DEF_RE.match(ln)
        or _LEDE_FOOTNOTE_NUM_RE.match(ln)
    )


def _next_content_line_is_bullet(lines: list[str], idx: int) -> bool:
    """True when the first non-admin line after lines[idx] starts a bullet.

    A guidance/outlook table heading ("First Quarter 2026 Financial
    Guidance Summary") and a bare sub-heading ("Guidance") share the
    _is_lede_table_heading shape, but only the first heads a table: the
    second heads bullets. The look-ahead tells them apart — page-number
    admin lines between the heading and its bullets are skipped, so a
    page break between them does not hide the bullets. Batch 195.
    """
    for ln in lines[idx + 1 :]:
        if _ADMIN_LINE_RE.match(ln):
            continue
        return bool(_BULLET_LEAD_RE.match(ln) or ln.startswith("·"))
    return False


def _extract_highlights_sections(lines: list[str]) -> list[list[str]]:
    """Return the content lines of every explicit "Highlights" section.

    Previously only the first match was returned; Halliburton's releases
    pair leading financial bullets with a later business "Highlights"
    section, so all candidates are collected and ranked by financial
    density by the caller (batch 102).
    """
    sections: list[list[str]] = []
    for i, ln in enumerate(lines):
        if not _HIGHLIGHTS_SECTION_ANCHOR_RE.search(ln) or len(ln) > 120:
            continue
        collected: list[str] = []
        # Batch 184: a section anchored by a leading-"Highlights"
        # sub-headline serves the anchor as its first content line — the
        # anchor is the release's own sub-headline, not a title. The
        # shape is all-caps and unterminated (Chipotle's "HIGHLIGHTS
        # RETURN TO POSITIVE ..." / "HIGHLIGHTS POSITIVE COMPARABLE
        # SALES"); a real heading never qualifies (the narrowed regex
        # says so), and a terminated prose pointer (Delta's "Highlights
        # of the March quarter, ... are on page five ...") stays a
        # heading-only anchor, so the quotes after it are still served
        # without the pointer sentence itself.
        if (
            re.match(r"highlights?\b", ln, re.IGNORECASE)
            and not _HIGHLIGHTS_HEADING_RE.search(ln)
            and ln.isupper()
            and not ln.rstrip().endswith((".", "!", "?", "…"))
        ):
            collected.append(ln)
        hit_table = False
        # Batch 194: a "-more-" page marker inside a Highlights
        # section is never content, and a heading-shaped line right
        # after it ends the section (same rule as the lede loop).
        after_more = False
        n_follow = 0  # Batch 184: the cap counts FOLLOW lines only — a
        # prepended sub-headline anchor (above) is headline-adjacent
        # content, not part of the section's 12-line budget. Counting
        # it would shift every line by one and drop the section's last
        # line (Chipotle's revenue prose) for no reason; for sections
        # without a prepended anchor n_follow == len(collected), so
        # behavior is byte-identical.
        for j, follow in enumerate(lines[i + 1 :], start=i + 1):
            if _ADMIN_LINE_RE.match(follow):
                continue  # stray exhibit headers / page numbers mid-document
            if follow == "-more-":
                # Batch 194: page-continuation marker, never content.
                after_more = True
                continue
            if after_more:
                # Consumed by the next line: a bare company-name page
                # header is skipped transparently (CarMax: "CarMax,
                # Inc." + "Page 2 of 13" head page 2), so the line after
                # IT is judged as the section boundary.
                if _is_trailing_company_signature(follow):
                    continue
                # A heading-shaped line ends the section (its content
                # belongs to the next section), anything else continues it.
                after_more = False
                if (
                    collected
                    and _is_sentence_terminated(collected[-1])
                    and _is_more_page_section_heading(follow)
                ):
                    break
            if _BOILERPLATE_RE.match(follow):
                break
            if follow.isupper() and len(follow) <= 80:
                break
            if (
                _TABLE_UNITS_RE.match(follow)
                or _TABLE_WORD_UNITS_RE.match(follow)
                or _LEDE_BARE_UNITS_DOLLARS_RE.match(follow)
                or _is_lede_recon_heading(follow)
                or _CONFERENCE_CALL_NOTICE_RE.search(follow)
                or _is_lede_call_announcement(follow)
                or (
                    _is_lede_table_heading(follow)
                    and not _next_content_line_is_bullet(lines, j)
                )
                or _is_lede_period_header(follow)
                or _is_lede_date_header(follow)
                or _is_bare_period_fragment(follow)
            ):
                hit_table = True
                break  # a table starts where the highlights end (AppLovin's
                # guidance-summary heading after the bullets): the section
                # ends here, the heading is not highlights. Only the strong
                # heading shapes break — data rows stay out, so a section
                # whose bullets are figure-dense is never cut. Batch 153.
                # Batch 195: the table-heading break does not fire when
                # the next content line is a bullet — a bare "Guidance"
                # heading that introduces bullets (Air Products) is a
                # sub-heading, not a table title, so it is collected as
                # a label line and the bullets below it stay in the
                # section.
                # Batch 182: a conference-call notice breaks collection
                # the same way (CSX: the notice + webcast + pointer
                # lines were collected as section content in 3 quarters
                # because the collector has no notice handling — the
                # lede loop's notice skip never runs on the section
                # path).
                # Batch 154: a date header ("Three Months Ended June 30,")
                # breaks too — it is the table's period header, and without
                # it Instacart's financial section ends on the orphan line.
                # Batch 174: a bare period fragment ("Three Months") is the
                # same signal — the period header needs a year and the date
                # header needs "ended" or a month, so the fragment alone
                # matches neither and would be collected as content.
            collected.append(follow)
            n_follow += 1
            if n_follow >= 12:
                break
        if hit_table and (
            len("\n".join(collected)) < 150
            or not any(
                _BULLET_LEAD_RE.match(ln) or ln.startswith("·")
                for ln in collected
            )
        ):
            continue  # table-headed section too thin — try later headings,
            # as the financial-table rejection below does; without this a
            # thin table-led section would block every later heading.
            # Batch 156: the no-bullet half is the GOOGL-Q4 hazard from
            # batch 155, closed generically — a table-headed section with
            # no bullets is a table, not highlights, even when its intro
            # prose runs past 150 chars ("The following table summarizes
            # ..." + a period header, which _looks_like_financial_table
            # never flags); left in, it wins as the only candidate and
            # pre-empts the lede's real bullets. The "·" lead counts as
            # a bullet (batch 138/139: Plug/Chubb flatten bullets onto
            # that marker), so a "·"-bulleted section is never rejected
            # for lacking a "•"-style lead.
        if len("\n".join(collected)) >= 150:
            if _looks_like_financial_table(collected):
                continue  # table, not narrative highlights — try later headings
            # Batch 140: drop lone-marker lines AFTER qualification, so the
            # 12-line cap and the 150-char floor see the same lines as
            # before — only the junk glyph lines disappear. Flattened
            # bullet lists (Nucor: "•" on its own line before each item)
            # otherwise store a glyph line per item.
            # Batch 162: footnote-definition lines drop the same way —
            # Datadog's M&A-costs footnote sits between its section
            # bullets, and the section collector is the one collection
            # path with no footnote handling at all. Batch 166: the
            # whole block drops, not just the key line — a wrapped
            # definition's continuation lines are footnote material
            # too ("3 Trading Volume represents the / total US dollar
            # equivalent value of / ..."). The filter is index-aware
            # because a block spans lines.
            kept: list[str] = []
            j = 0
            while j < len(collected):
                block = _footnote_def_block_len(collected, j)
                if block:
                    j += block
                    continue
                note = _rounding_note_block_len(
                    collected, j
                ) or _asterisk_note_block_len(collected, j)
                if note:
                    # Rounding note / asterisk note inside a Highlights
                    # section: same boilerplate class as a footnote
                    # definition — drop the whole block. Batch 167.
                    j += note
                    continue
                sal = _salutation_block_len(collected, j)
                if sal:
                    # Shareholder-letter salutation inside a Highlights
                    # section: a greeting, never a highlight — drop the
                    # whole block. Batch 169.
                    j += sal
                    continue
                if _LEDE_SYMBOL_LEGEND_RE.match(collected[j]):
                    # Symbol legend inside a Highlights section (Walmart:
                    # "“cc” - constant currency" sits after its footnote
                    # run in the Third-Quarter Highlights section): the
                    # table's own footnote, never a highlight. The lede
                    # loop and the leading-bullet block already skip it;
                    # the section collector is the path that actually
                    # serves Walmart, so it needs the skip too. Batch 173.
                    j += 1
                    continue
                if _is_bare_role_line(collected[j]):
                    # Bare quote-attribution role line inside a Highlights
                    # section — the same dangling fragment as in the lede
                    # loop (Moody's). Batch 173.
                    j += 1
                    continue
                if collected[j].rstrip().lower() in (
                    "key points:",
                    "key points",
                ):
                    # "Key Points:" sub-heading inside a Highlights
                    # section — the same dangling heading as in the lede
                    # loop (Disney); the bullets after it are the
                    # content. Batch 173.
                    j += 1
                    continue
                if _is_lede_report_pointer(collected[j]):
                    # Report-pointer sentence inside a Highlights
                    # section (American Express: "This earnings release
                    # should be read in conjunction with the company's
                    # statistical tables ...") — the same document-tail
                    # pointer as in the lede loop; the section collector
                    # is the path that actually serves Amex, so it needs
                    # the skip too. Batch 182.
                    j += 1
                    continue
                if not _is_lone_bullet_marker(collected[j]):
                    kept.append(collected[j])
                j += 1
            collected = kept
            if collected:
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
    if _score(best)[0] <= 0:
        best = candidates[0]
    # Batch 177: drop colon-ended list-intro / section headings and
    # summary-table column-header lines from the WINNING section only.
    # The drop must happen after selection, not in the per-section
    # cleanup: dropping a heading line pre-selection changes a
    # candidate's financial density and flips which candidate wins
    # (Akamai: the "Revenue by solution:" / "Revenue by geography:"
    # sub-headings drop, the Full-year section wins over the lede's
    # Revenue section, and the real Security/Delivery/Compute bullets
    # are lost). Post-selection the competition is untouched and only
    # the served text loses the dangling heading (Datadog: "Third
    # Quarter & Recent Business Highlights:" between the financial
    # bullets and the business bullets).
    return [
        ln
        for ln in best
        if not _is_lede_colon_heading(ln) and not _is_lede_table_header(ln)
    ]


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


# --- Batch 146: flattened summary-table mode for shareholder letters ---------
#
# Airbnb's shareholder letter opens with a summary table ("Key Financial
# Measures" / "Key Business Metrics") that text extraction flattens into
# run-on lines: group-header words split around the first metric's value
# ("Revenue Key Financial $3.6B Measures"), wrapped labels split around
# their value ("Free Cash $1.3B Flow ("FCF")*"), and Q4 letters carry two
# value columns (quarter + full year). The batch-94 metric mode needs a
# "Highlights" heading line, which this table never has, so the standard
# path served the flattened table as headline + prose — gibberish.
#
# The flat-table mode parses the token stream between value tokens:
#   label value [change ...] label value [change ...]
# where a change phrase is "%" + ("Y/Y" ["(ex-FX)"] | words ending in
# "margin"). A piece between two values splits into a label continuation
# (before the first % — or, with no %, up to the first parenthetical),
# change phrases, and the next label. Anything that does not fit that
# grammar fails the whole parse (returns None) so the old behavior is
# preserved — in particular the Q3/Q4 2024 letters, whose table cells
# interleave with narrative sentences ("Q3 revenue of $3.7 billion
# increased 10% compared to..."), fail on the first prose change phrase
# instead of emitting junk labels.

# A summary-table value: "$3.6B", "$816M", "148.3M". The B/M suffix keeps
# years ("2025") and bare counts out of the value stream.
_FLAT_VALUE_RE = re.compile(r"\$?[\d,]+(?:\.\d+)?[BM]\b")

_FLAT_PCT_RE = re.compile(r"\d[\d.,]*%")

_FLAT_MARGIN_RE = re.compile(r"\s*((?:\S+\s+){0,5}?[Mm]argin)\b")

_FLAT_GROUP_RE = re.compile(
    r"Key Financial Measures|Key Business Metrics|Key Financial|Key Business",
    re.IGNORECASE,
)


def _split_flat_piece(
    piece: str, is_tail: bool
) -> tuple[str, list[str], str | None] | None:
    """Split one between-values piece into (continuation, changes, next-label).

    The continuation is the previous metric's wrapped-label tail: the text
    before the first % token, or — when the piece has no % at all (a metric
    with no change phrases, e.g. Q1 2025 FCF) — the text up to and
    including the first parenthetical. Change phrases are then consumed
    strictly: "%" + "Y/Y" [ "(ex-FX)" ], or "%" + words ending in "margin".
    A % token the grammar cannot consume, a % left in the remainder, or a
    missing/extra label fails the piece — and with it the whole parse.
    """
    pct = _FLAT_PCT_RE.search(piece)
    if pct is None:
        paren = re.search(r"\([^)]*\)", piece)
        if paren is None:
            return None
        end = paren.end()
        if piece[end : end + 1] == "*":
            end += 1  # footnote star belongs to the continuation, not the label
        continuation = piece[:end].strip()
        rest = piece[end:].strip()
        changes: list[str] = []
    else:
        continuation = piece[: pct.start()].strip()
        rest = piece[pct.start() :].strip()
        changes = []
        while rest:
            m = _FLAT_PCT_RE.match(rest)
            if m is None:
                break
            after = rest[m.end() :]
            ym = re.match(r"\s*Y/Y(?:\s*\(ex-FX\))?", after)
            if ym:
                changes.append(rest[: m.end() + ym.end()].strip())
                rest = after[ym.end() :].strip()
                continue
            mm = _FLAT_MARGIN_RE.match(after)
            if mm:
                changes.append(rest[: m.end() + mm.end()].strip())
                rest = after[mm.end() :].strip()
                continue
            return None
    if "%" in rest or "$" in rest or _FLAT_VALUE_RE.search(rest):
        return None
    if len(continuation) > 40 or any(c.isdigit() for c in continuation):
        return None
    if is_tail:
        if rest:
            return None
        return continuation, changes, None
    if not rest or len(rest) > 60 or any(c.isdigit() for c in rest):
        return None
    return continuation, changes, rest


def _parse_flat_summary_table(lines: list[str]) -> list[str] | None:
    """Parse a flattened "Key Financial/Business Measures" summary table.

    Returns rendered lines (optional dual-column header + bullets), or
    None when the shape is absent or any piece fails the grammar.
    """
    # The header fragment alone starts the table: in most quarters it is
    # split around the first metric's value ("Revenue Key Financial $3.6B
    # Measures"), so the full phrase never appears on one line.
    start: int | None = None
    for i, ln in enumerate(lines[:30]):
        low = ln.lower()
        if "key financial" in low or "key business" in low:
            start = i
            break
    if start is None:
        return None
    run: list[str] = []
    for ln in lines[start : start + 9]:
        if "reconciliation of non-gaap" in ln.lower():
            idx = ln.lower().find("reconciliation of non-gaap")
            head = re.sub(r"\*?\s*A\s*$", "", ln[:idx])
            run.append(head)
            break
        run.append(ln)
    else:
        return None  # no reconciliation trailer within the window
    stream = re.sub(r"\s+", " ", " ".join(run)).strip()
    stream = _FLAT_GROUP_RE.sub("", stream)
    stream = re.sub(r"\bMeasures\b|\bMetrics\b", "", stream)
    stream = re.sub(r"\s+", " ", stream).strip()
    # Leading quarter labels are the table's column headers ("Q4 2025
    # FY 2025"); the section title repeats the quarter label, so dedupe.
    columns: list[str] = []
    while True:
        m = re.match(r"(Q[1-4]|FY)\s+(\d{4})\s+", stream)
        if not m:
            break
        label = f"{m.group(1)} {m.group(2)}"
        if label not in columns:
            columns.append(label)
        stream = stream[m.end() :]
    stream = re.sub(r"^Highlights\s+", "", stream)
    if "shareholder letter" in stream.lower():
        return None
    vals = list(_FLAT_VALUE_RE.finditer(stream))
    if len(vals) < 2:
        return None
    # Group consecutive values (whitespace only between them) into one
    # metric's multi-column values: Q4 letters carry quarter + full year.
    groups: list[tuple[list[str], int, int]] = []
    for m in vals:
        if groups and stream[groups[-1][2] : m.start()].strip() == "":
            groups[-1][0].append(m.group(0))
            groups[-1] = (groups[-1][0], groups[-1][1], m.end())
        else:
            groups.append(([m.group(0)], m.start(), m.end()))
    if len(columns) == 2:
        if any(len(g[0]) != 2 for g in groups):
            return None
    elif any(len(g[0]) != 1 for g in groups):
        return None
    first_label = stream[: groups[0][1]].strip()
    if (
        not first_label
        or len(first_label) > 60
        or any(c.isdigit() or c in "%$" for c in first_label)
    ):
        return None
    bullets: list[str] = []
    label = first_label
    for k, (values, _gs, ge) in enumerate(groups):
        piece = (
            stream[ge : groups[k + 1][1]]
            if k + 1 < len(groups)
            else stream[ge:]
        ).strip()
        split = _split_flat_piece(piece, is_tail=(k + 1 == len(groups)))
        if split is None:
            return None
        continuation, changes, next_label = split
        if continuation:
            label = f"{label} {continuation}".strip()
        clean_label = label.rstrip("*").strip()
        if not clean_label or len(clean_label) > 90:
            return None
        detail = "; ".join(values)
        if changes:
            detail += f" ({'; '.join(changes)})"
        bullets.append(f"- {clean_label}: {detail}")
        if next_label is None:
            break
        label = next_label
    if len(bullets) < 3:
        return None
    out: list[str] = []
    if len(columns) == 2:
        out.append("; ".join(columns))
    out.extend(bullets)
    return out


def _extract_flat_summary_table_highlights(
    lines: list[str], max_chars: int
) -> str | None:
    """Shareholder-letter mode: flattened summary-table highlights.

    Returns None when no flat summary table parses, so the caller can
    fall back to the standard press-release path.
    """
    entries = _parse_flat_summary_table(lines)
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
        if _is_guidance_heading(ln):
            collected = [ln]
            # Index loop (batch 193): footnote/note blocks are skipped
            # whole, so the loop can jump past them instead of
            # appending them one line at a time.
            j = i + 1
            while j < len(lines):
                follow = lines[j]
                if _ADMIN_LINE_RE.match(follow) or follow == "-more-":
                    # Batch 193: "-more-" is a page-continuation
                    # marker, never content — skip it like the admin
                    # lines (8 collected guidance texts carry one).
                    j += 1
                    continue
                if (
                    len(follow) <= 90
                    and not _is_sentence_terminated(follow)
                    and re.search(r"\breports\b", follow, re.IGNORECASE)
                    and re.search(r"\b(results|earnings)\b$", follow, re.IGNORECASE)
                ):
                    # Batch 193: a repeated release-title line inside
                    # the guidance section ("American Airlines Reports
                    # Second-Quarter 2026 Financial Results" — AAL's
                    # page-header repeat) is page furniture, never
                    # guidance content — skip it like an admin line.
                    j += 1
                    continue
                if (
                    _BOILERPLATE_RE.match(follow)
                    or _FINANCIAL_TABLE_START_RE.match(follow)
                    or _is_lede_call_announcement(follow)
                    or (
                        (m := _CONFERENCE_CALL_NOTICE_RE.search(follow)) is not None
                        and m.start() <= 120
                    )
                    or (
                        (m := _CALL_QA_SESSION_RE.search(follow)) is not None
                        and m.start() <= 120
                    )
                    or re.search(r"\bwill host\b[^.]*\bwebcast\b", follow, re.IGNORECASE)
                ):
                    # Batch 193: a conference-call / webcast notice ends
                    # the guidance section — the notice line itself
                    # ("Church & Dwight ... will host a webcast to
                    # discuss second quarter 2025 results ...") was
                    # collected as guidance once the footnote skip
                    # freed the line budget, and the dial-in / URL
                    # lines after it are event logistics, never
                    # guidance. The _is_lede_call_announcement shape
                    # (CSX's split notice) and the bare "will host a
                    # webcast" shape are the two the ^-anchored
                    # table-start regex never matches. The
                    # _CONFERENCE_CALL_NOTICE_RE match must start in
                    # the line's first 120 chars: Biogen's FX-assumption
                    # line ends "... will be provided on the conference
                    # call and webcast." — a guidance sentence with a
                    # call pointer in its tail, not a notice — and an
                    # unguarded .search breaks on it, dropping the FX
                    # line and the two disclaimer lines after it. The
                    # _CALL_QA_SESSION_RE test carries the same guard
                    # for the same reason (GIS's notice shape).
                    break
                if (
                    follow.isupper()
                    and len(follow) <= 80
                    and re.search(r"[A-Za-z]{2,}", follow)
                    and not _is_guidance_period_label(follow)
                    and not any(
                        w in follow for w in ["GAAP", "RANGE", "GUIDANCE", "OUTLOOK", "REVENUE", "EPS", "NET SALES"]
                    )
                ):
                    # Batch 193: an all-caps period label ("Q4 FY25",
                    # "FY25" — CRM's guidance-table period headers) is
                    # a table header, not a section heading, so it
                    # never breaks collection.
                    # Batch 199: a wrapped table value on its own line
                    # ("$520M" — FSLR's split "Operating Expenses"
                    # row) is all-caps by construction ($/digits carry
                    # no case, "M" is the only cased char) but never a
                    # heading, so a line with no two-letter word never
                    # breaks. A real heading ("CONFERENCE CALL
                    # DETAILS") always carries one.
                    break
                # Batch 193: footnote-definition, rounding-note and
                # asterisk-note blocks are never guidance — skip the
                # whole block in-loop, with the same block machinery
                # the Highlights section collector uses post-collection
                # (batch 162/166). In-loop (not post-collection: batch
                # 192 showed a post-collection filter frees char
                # budget that the cap then refills with next-section
                # content) so the 30-line budget is spent only on kept
                # lines. APD's "#" per-share definition and "* Certain
                # results" legend, AFL's "*See Non-U.S. GAAP ..."
                # pointer, AKAM's "** Cloud Infrastructure ..." note,
                # AMT's "(1)For additional discussion ..." table
                # footnote and the "*Management is unable to
                # reconcile" disclaimer all drop here. Two guards:
                # (a) a parenthesized WORD is a table column header,
                # not a footnote key — "(Prior) July" / "(Updated)"
                # (BMY's guidance-table headers) match
                # _LEDE_FOOTNOTE_RE's paren shape, so the block
                # machinery would drop them (and chain onto the next
                # table row, "2026 WW Revenue Growth* ..."). A real
                # paren footnote carries a digit key or a sentence
                # after the marker; a bare label word (or nothing) is
                # a header, so those lines collect normally.
                # (b) a block never swallows a guidance (sub-)heading
                # — CARR's "1 Excludes NORESCO" block chains through
                # "2 The closure ..." and the bare "5" onto the "2026
                # Guidance" table header. Truncate the block at the
                # first guidance-vocabulary line after the opener.
                block = 0
                if not re.match(r"^\([A-Za-z]+\)\d?(?:\s+[A-Z][a-z]*)?$", follow):
                    block = (
                        _footnote_def_block_len(lines, j)
                        or _rounding_note_block_len(lines, j)
                        or _asterisk_note_block_len(lines, j)
                    )
                if block:
                    for k in range(j + 1, j + block):
                        if re.search(r"\b(outlook|guidance)\b", lines[k], re.IGNORECASE):
                            block = k - j
                            break
                    j += block
                    continue
                # Batch 193: a next-section heading ends the guidance
                # section — but only once the section has delivered
                # guidance (see _guidance_has_signal).
                if _is_guidance_next_section_heading(lines, j) and _guidance_has_signal(collected):
                    break
                collected.append(follow)
                if len(collected) >= 30:
                    break
                j += 1

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
    # Batch 198: a bullet glyph in its own inline element glues to its
    # item text when the tags are stripped (\"&#8226;</font><font>Net
    # sales...\" -> \"•Net sales...\") — the no-space inline join above is
    # deliberate (DFIN span-splitting), but a line-leading bullet is never
    # part of a split word, so restore the space after it. Stored rows
    # from the older extractor already carry the spaced form (\"• Net
    # sales...\"), and the served guidance/highlights cards render the
    # glued form on ~1,400 of the 1,699 cached exhibits. Dashes are
    # gated on a following letter: a dash before a digit or \"$\" is a
    # table negative, not a bullet. Strip first: a leading space from a
    # stripped opening tag would otherwise hide the first line's bullet
    # from the ^ anchor (the final .strip() runs after these regexes).
    text = text.strip()
    text = re.sub(r"(?m)^([•●○◦▪■·])(\S)", r"\1 \2", text)
    text = re.sub(r"(?m)^([–—])([A-Za-z])", r"\1 \2", text)
    return text
