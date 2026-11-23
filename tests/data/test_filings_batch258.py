"""Batch 258 regression tests.

DLR's "Table of Contents" headline wart: all 8 stored DLR rows
carried the literal headline "Table of Contents". Three defects,
all in the headline pass of extract_press_release_highlights:

1. _skip_toc's admin-break fired on the "Exhibit 99.1" line DLR
   repeats inside its table of contents, so the skip never ran and
   the TOC heading became the headline. The exhibit marker is
   packet front-matter, not a narrative marker — it is now consumed
   as TOC material (the release-banner / contact breaks are
   untouched).

2. After the TOC skip, the headline loop broke on the first long
   line (DLR's corporate-profile paragraph) with headline=None.
   Inside a release+supplement packet the supplement's front matter
   precedes the release section, so the loop now keeps scanning:
   long lines and non-headline-shaped lines are skipped, and only a
   headline-verb + results-topic line is picked. The decoys it
   passes are pinned below: the stock-listing lines ("DLR" /
   "Series J Preferred Stock:"), the "Key Quarterly Financial Data"
   title, and the "Unaudited, Dollars ..." units line.

3. The single-word-fragment join ("DLR" + "Series J Preferred
   Stock:") bypassed the shape check — it now needs the verb+topic
   shape in the after-TOC state too.

EOG pin: the same scan must NOT wander a supplement-only packet
into serving a table section as highlights. EOG's exhibits are
tables all the way down (image-only, honestly None); the scan now
skips the dateline-shaped table row ("Acquisition Costs of Other
Property, Plant and Equipment (134) —" trips the city-dateline
shape) instead of breaking there with the "Net Debt-to-Total
Capitalization Ratio" section as the lede. A faithful synthetic
EOG packet needs ~200 lines of table rows before the lede stays
empty, so the guard is pinned with the same row inside the DLR
packet instead; the real-EOG protection is proven by the
full-cache blast (EOG byte-identical before/after).
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _TOC_EXHIBIT_MARKER_RE,
    _skip_toc,
    extract_press_release_highlights,
)

_LONG_PROSE = (
    "Digital Realty Trust, Inc. (\"Digital Realty\" or the \"company\") owns, "
    "acquires, develops, and operates data centers through its operating "
    "partnership subsidiary, Digital Realty Trust, L.P. (the \"operating "
    "partnership\"). The company is focused on providing data center, "
    "colocation, and interconnection solutions for domestic and "
    "international customers."
)

# --- Synthetic DLR-shaped packet (miniature of DLR 2025-06-30) ---
_DLR_LINES = [
    "EX-99.1",
    "2",
    "dlr-20250724xex99d1.htm",
    "EX-99.1",
    "Table of Contents",
    "Exhibit 99.1",
    "Table of Contents",
    "Financial Supplement",
    "Table of Contents",
    "Second Quarter 2025",
    "Overview",
    "PAGE",
    "Corporate Information",
    "3",
    "Key Quarterly Financial Data",
    "5",
    "Consolidated Statements of Operations",
    "Earnings Release",
    "7",
    "2025 Outlook",
    "10",
    "Corporate Profile",
    _LONG_PROSE,
    "Corporate Headquarters",
    "2323 Bryan Street, Suite 1800",
    "Dallas, TX 75201",
    "Telephone: (214) 231-1350",
    "Senior Management",
    "President & Chief Executive Officer: Andrew P. Power",
    "The stock of Digital Realty Trust, Inc. is traded primarily on the "
    "New York Stock Exchange under the following symbols:",
    "Common Stock:",
    "DLR",
    "Series J Preferred Stock:",
    "DLRPRJ",
    "Table of Contents",
    "Key Quarterly Financial Data",
    "Financial Supplement",
    "Unaudited, Dollars (except per share data) and Square Feet in Thousands",
    "Second Quarter 2025",
    "(1) The market value of common equity is based on the closing stock "
    "price at the end of the quarter and assumes 100% redemption of the "
    "limited partnership units in our operating partnership.",
    "6",
    "Table of Contents",
    "Digital Realty Trust",
    "Financial Supplement",
    "Earnings Release",
    "Second Quarter 2025",
    "Digital Realty Reports Second Quarter 2025 Results",
    "Dallas, TX \u2014 July 24, 2025 \u2014 Digital Realty (NYSE: DLR), the "
    "largest global provider of cloud- and carrier-neutral data center, "
    "colocation, and interconnection solutions, announced today financial "
    "results for the second quarter of 2025.",
    "Highlights",
    "\u25fe Reported net income available to common stockholders of $2.94 "
    "per share in 2Q25, compared to $0.20 in 2Q24",
    "\u25fe Reported FFO per share of $1.75 in 2Q25, compared to $1.57 "
    "in 2Q24",
]


def _html(lines):
    return "<html><body>" + "".join(f"<p>{ln}</p>" for ln in lines) + "</body></html>"


# --- Dateline-shaped table row, inserted mid-supplement (batch 258) ---
# EOG's supplement is tables all the way down; its "Acquisition Costs
# of Other Property, Plant and Equipment (134) —" row trips the
# city-dateline shape, and without the after-TOC dateline guard the
# scan breaks there and serves the Net Debt table section as the
# lede. A faithful synthetic EOG packet needs ~200 lines of table
# rows before the lede stays empty, so the guard is pinned here
# instead: the same row inside the DLR packet, ahead of the real
# headline — the guard must skip it and still serve the headline.
# The real-EOG protection is proven by the full-cache blast (EOG
# byte-identical before/after).
_DLR_DATELINE_ROW_LINES = [
    *_DLR_LINES[:36],
    "Acquisition Costs of Other Property, Plant and Equipment (134) \u2014",
    "Exploration Costs (181) (159)",
    "Total Capital Expenditures (Non-GAAP) 6,041 4,607",
    *_DLR_LINES[36:],
]


def test_skip_toc_consumes_exhibit_marker():
    lines = [
        "Table of Contents",
        "Exhibit 99.1",
        "Financial Supplement",
        "Overview",
        "3",
        "Key Data",
        "5",
        "Balance Sheets",
        "7",
        _LONG_PROSE,
    ]
    assert _skip_toc(lines, 0) == 9


def test_skip_toc_marker_variants():
    assert _TOC_EXHIBIT_MARKER_RE.match("EXHIBIT-99.1")
    assert _TOC_EXHIBIT_MARKER_RE.match("ECHIBIT 99.1")
    assert _TOC_EXHIBIT_MARKER_RE.match("TMUS EXHIBIT 99.1")
    # "Exhibit 99.2" matches too: the family follows _ADMIN_LINE_RE's
    # own breadth (its ^exhibit[\s\-]+99(\.1)?\b branch also matches
    # 99.2), and inside a TOC any exhibit marker is front-matter.
    assert _TOC_EXHIBIT_MARKER_RE.match("Exhibit 99.2")
    assert not _TOC_EXHIBIT_MARKER_RE.match("Exhibit A")
    assert not _TOC_EXHIBIT_MARKER_RE.match("FOR IMMEDIATE RELEASE")


def test_skip_toc_still_breaks_on_release_banner():
    # The marker is consumed, but a release banner right after it is
    # still a narrative marker: with no page numbers the skip refuses.
    lines = [
        "Table of Contents",
        "Exhibit 99.1",
        "FOR IMMEDIATE RELEASE",
        "Acme Reports Second Quarter 2025 Results",
    ]
    assert _skip_toc(lines, 0) == 0


def test_skip_toc_plain_toc_unchanged():
    lines = [
        "Table of Contents",
        "Overview",
        "3",
        "Key Data",
        "5",
        "Balance Sheets",
        "7",
        _LONG_PROSE,
    ]
    assert _skip_toc(lines, 0) == 7


def test_dlr_packet_serves_real_headline():
    live = extract_press_release_highlights(_html(_DLR_LINES))
    assert live is not None
    first, _, body = live.partition("\n\n")
    assert first == "Digital Realty Reports Second Quarter 2025 Results"
    assert "Table of Contents" not in first
    assert "Reported net income available to common stockholders of $2.94" in body
    assert "Reported FFO per share of $1.75" in body


def test_dateline_shaped_table_row_skipped_after_toc():
    # The EOG row trips _DATELINE_RE; without the after-TOC guard the
    # scan breaks here with body_start past the row and the table
    # section becomes the lede instead of the real headline.
    live = extract_press_release_highlights(_html(_DLR_DATELINE_ROW_LINES))
    assert live is not None
    first, _, body = live.partition("\n\n")
    assert first == "Digital Realty Reports Second Quarter 2025 Results"
    assert "Reported net income available to common stockholders of $2.94" in body
