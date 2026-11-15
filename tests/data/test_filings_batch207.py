"""Batch 207: page-footer furniture in the highlights collectors; flattened
range rows and footnote-marker labels in the lede table predicates.

Batch 206 carry-forward: CCI highlights keep the tagline "The pathway to
possible." as a standalone para in 2 stored rows (2024-12-31, 2026-03-31)
— the highlights collector drops the domain line already (a no-space
line reads as table residue) but not the tagline. The blast shows the
pair in 7 cached exhibits, in three shapes: a standalone lede para
(2024-12-31, 2026-03-31), embedded mid-quote in the lede (2023-12-31,
2024-03-31, 2024-06-30), and embedded mid-bullet in a Highlights
section (2023-09-30, 2024-09-30).

Fix (extract_press_release_highlights, in-loop skips in the lede loop,
the Highlights-section collector, and the leading-bullet block, so no
budget is consumed): the shared _is_page_footer_furniture predicate —
a bare-domain line, or a short terminated sentence-case line
immediately before one — with the batch-206 conditions byte-identical
so the two collectors agree on what furniture is.

The lede skip frees a budget slot in CCI 2026-03-31, which exposed two
lede table-predicate gaps (the freed slot filled with outlook-table
rows instead of the bullet below): a flattened range row ("Straight-
lined revenues (75) to (45) —", "Site rental revenues 3,828 to 3,873
—") was not a data row — the density rule misses it and the 25%
branch needs a figure ending — and a table label carrying a footnote
marker ("Interest expense ... net(f)") was not a label — the marker
matches _LEDE_FIGURE_RE. Both are fixed here: _is_lede_data_row gains
a flattened-range-row branch (bare-number range + trailing dash, no $
or %, at least one word), and _is_lede_table_label /
_is_lede_flat_table_label_shape ignore single-char parenthesized
footnote markers in the figure test. The freed slot then serves the
genuine reconciliation bullet below the table, not table residue.

Blast (blast207/h_new vs h_old, 1,699 exhibits): 8 diffs, 0 None-flips
— the 7 CCI (6 pure furniture drops; 2026-03-31 drops the tagline and
gains the genuine "$200 million" reconciliation bullet) and GOOGL
2023-12-31 (a "(1)"-marked table label drops, a real subsection
heading enters at the tail). Repair: 3 stored CCI rows repaired
(2024-09-30, 2024-12-31, 2026-03-31); the 4 pre-seeding CCI quarters
have no stored rows and serve on refresh; GOOGL 2023-12-31 has a
stored row and is repaired too.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_lede_data_row,
    _is_lede_table_label,
    _is_page_footer_furniture,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _highlights(name: str) -> str:
    h = extract_press_release_highlights(_load(name))
    assert h is not None
    return h


def _synthetic_doc(lines: list[str]) -> str:
    return "<html><body>" + "".join(f"<p>{ln}</p>" for ln in lines) + "</body></html>"


# --- Real exhibits: the CCI furniture cohort ---------------------------


def test_cci_2024_12_31_highlights_tagline_dropped():
    h = _highlights("CCI_2024-12-31.html")
    assert "The pathway to possible." not in h
    assert "CrownCastle.com" not in h
    assert "Successfully Concludes Strategic Review" in h
    assert "tower business will be uniquely well positioned" in h
    assert len(h) == 2529


def test_cci_2026_03_31_highlights_tagline_dropped_bullet_gained():
    # The freed lede slot serves the genuine reconciliation bullet below
    # the outlook table, not table residue.
    h = _highlights("CCI_2026-03-31.html")
    assert "The pathway to possible." not in h
    assert "CrownCastle.com" not in h
    assert "Straight-lined revenues (75) to (45)" not in h
    assert "Site rental revenues 3,828 to 3,873" not in h
    assert "approximately $200 million" in h
    # Batch 259: the bullet-run extension serves two more genuine
    # bullets (the AFFO-reconciliation bullet and the $160M interest
    # decrease bullet), so the pinned length moves 2526 -> 2965.
    assert len(h) == 2965


def test_cci_2024_09_30_highlights_footer_pair_dropped_mid_bullet():
    h = _highlights("CCI_2024-09-30.html")
    assert "The pathway to possible." not in h
    assert "CrownCastle.com" not in h
    assert "Site rental revenues grew 1%, or $16 million" in h
    assert "AFFO was $801 million, or $1.84 per share" in h
    assert len(h) == 3797


def test_cci_2023_12_31_highlights_footer_pair_dropped_mid_quote():
    h = _highlights("CCI_2023-12-31.html")
    assert "The pathway to possible." not in h
    assert "CrownCastle.com" not in h
    assert "more than 90% fixed rate debt" in h


def test_cci_2024_03_31_highlights_footer_pair_dropped_mid_quote():
    h = _highlights("CCI_2024-03-31.html")
    assert "The pathway to possible." not in h
    assert "CrownCastle.com" not in h
    assert "5.0% consolidated core organic growth" in h


def test_cci_2024_06_30_highlights_footer_pair_dropped_mid_quote():
    h = _highlights("CCI_2024-06-30.html")
    assert "The pathway to possible." not in h
    assert "CrownCastle.com" not in h
    assert "89% fixed rate debt" in h


def test_cci_2023_09_30_highlights_footer_pair_dropped():
    h = _highlights("CCI_2023-09-30.html")
    assert "The pathway to possible." not in h
    assert "CrownCastle.com" not in h


def test_googl_2023_12_31_footnote_label_dropped():
    # The "(1)"-marked table label drops; the real subsection heading
    # enters at the tail; both CEO/CFO quotes stay.
    h = _highlights("GOOGL_2023-12-31.html")
    assert "Change in constant currency revenues year over year(1)" not in h
    assert "Reductions in Our Workforce and Office Space" in h
    assert "We are pleased with the ongoing strength in Search" in h
    assert "Q4 consolidated revenues of $86 billion" in h


# --- The shared footer predicate: guards ------------------------------


def test_footer_predicate_bare_domain_and_tagline():
    lines = ["Prose line here.", "The pathway to possible.", "CrownCastle.com"]
    assert _is_page_footer_furniture(lines, 2)
    assert _is_page_footer_furniture(lines, 1)
    assert not _is_page_footer_furniture(lines, 0)


def test_footer_predicate_guards():
    # A short sentence without a domain after it is kept.
    assert not _is_page_footer_furniture(["Short sentence here.", "Next line."], 0)
    # A figure sentence before a domain is kept.
    assert not _is_page_footer_furniture(
        ["Revenue grew 5% this quarter.", "CrownCastle.com"], 0
    )
    # A title-case line before a domain is kept.
    assert not _is_page_footer_furniture(
        ["Full Year 2025 Outlook", "CrownCastle.com"], 0
    )
    # A bullet before a domain is kept.
    assert not _is_page_footer_furniture(
        ["•Revenue grew 5% this quarter.", "CrownCastle.com"], 0
    )
    # Prose that merely mentions a domain is kept (no bare-domain line).
    assert not _is_page_footer_furniture(
        ["More detail is available at www.crowncastle.com.", "Next line."], 0
    )
    # A long terminated line before a domain is kept.
    assert not _is_page_footer_furniture(
        [
            "This is a much longer sentence that runs past sixty characters.",
            "CrownCastle.com",
        ],
        0,
    )


# --- Flattened range rows are data rows --------------------------------


def test_flattened_range_row_is_data_row():
    assert _is_lede_data_row("Straight-lined revenues (75) to (45) —")
    assert _is_lede_data_row("Site rental revenues 3,828 to 3,873 —")
    assert _is_lede_data_row("978 to 1,023 —")


def test_range_row_guards():
    # A $ range is a guidance statement, never a table row (batch 183).
    assert not _is_lede_data_row(
        "Reaffirms 2026 Outlook for Adjusted EPS of $7.50 to $8.00"
    )
    # A range without the trailing dash is prose, not a flattened row.
    assert not _is_lede_data_row("Headcount grew 100 to 120 in the quarter")
    # A terminated line is prose even with a range and a dash inside.
    assert not _is_lede_data_row("Revenue was $3,828 to $3,873 million.")
    # A bare range fragment with no label words is a values line, not a
    # label-plus-range row — the density rule already catches it.
    assert _is_lede_data_row("2,665 to 2,715 —")
    # A spaced dash is a column separator, not a range connector: SRE's
    # recon rows ("25 — 25 —") stay recon rows, not data rows (batch 161).
    assert not _is_lede_data_row("Impact from regulatory disallowances 25 — 25 —")
    assert not _is_lede_data_row("Tax items related to assets held for sale 26 — 26 —")
    assert not _is_lede_data_row(
        "Net unrealized losses on interest rate swaps related to Port "
        "Arthur LNG Phase 1 project 9 —"
    )
    # An unspaced dash range is a range row, like the "to" form.
    assert _is_lede_data_row("Site rental revenues 3,828–3,873 —")


# --- Footnote-marker labels --------------------------------------------


def test_footnote_marker_label_is_label():
    assert _is_lede_table_label(
        "Interest expense and amortization of deferred financing costs, net(f)",
        "792 to 837 (40)",
    )
    assert _is_lede_table_label(
        "Income (loss) from discontinued operations, net of tax(g)",
        "(360) to (80) —",
    )
    assert _is_lede_table_label(
        "Change in constant currency revenues year over year(1)",
        "13% 14% 15%",
    )


def test_label_figure_guard_still_refuses_real_figures():
    # A label carrying a real figure is a data row, not a label — the
    # marker strip must not let figures through.
    assert not _is_lede_table_label("Net income $5 (a)", "10 20")
    assert not _is_lede_table_label("Revenue 100 (a)", "200 300")
    # A label above a non-row line is not a label either.
    assert not _is_lede_table_label(
        "Interest expense and amortization of deferred financing costs, net(f)",
        "Some prose continuation here.",
    )


# --- Synthetic docs: the three collection paths ------------------------


def test_lede_path_footer_pair_dropped_quote_kept():
    html = _synthetic_doc(
        [
            "NEWS RELEASE",
            "October 16, 2024",
            "ACME CORP REPORTS THIRD QUARTER 2024 RESULTS",
            "October 16, 2024 - HOUSTON, TEXAS - Acme Corp. (NYSE: ACME) today reported results for the third quarter ended September 30, 2024.",
            '"We delivered solid results this quarter across all of our businesses," stated Jane Smith, Chief Executive Officer of Acme Corp. "Revenue grew 5% year over year and our margins expanded as we executed on our plan."',
            "The pathway to possible.",
            "CrownCastle.com",
            "News Release continued: Page 2",
            '"Our outlook for the full year remains strong and we are well positioned for continued growth," said John Doe, Chief Financial Officer of Acme Corp.',
            "Third quarter revenue was $100 million, an increase of 5% compared to $95 million in the third quarter of 2023, driven by growth in every region and continued demand for our products.",
        ]
    )
    h = extract_press_release_highlights(html)
    assert h is not None
    assert "The pathway to possible." not in h
    assert "CrownCastle.com" not in h
    assert "We delivered solid results this quarter" in h
    assert "Our outlook for the full year remains strong" in h


def test_section_path_footer_pair_dropped_mid_bullet():
    html = _synthetic_doc(
        [
            "NEWS RELEASE",
            "October 16, 2024",
            "ACME CORP REPORTS THIRD QUARTER 2024 RESULTS",
            "October 16, 2024 - HOUSTON, TEXAS - Acme Corp. (NYSE: ACME) today reported results for the third quarter ended September 30, 2024.",
            "HIGHLIGHTS FROM THE QUARTER",
            "•Revenue grew. Revenue grew 5% to $100 million in the quarter, driven by strong demand across all segments and continued momentum in our core business lines, with growth in every region.",
            "The pathway to possible.",
            "CrownCastle.com",
            "•Net income rose. Net income was $20 million, up 10% from the prior year, reflecting improved margins and disciplined cost management throughout the quarter.",
            "•Cash flow strengthened. Operating cash flow was $35 million in the quarter, up from $28 million a year ago, as working capital improved and collections accelerated.",
            "•Margins expanded. Gross margin rose to 42% from 39% a year ago as pricing actions and a richer product mix more than offset higher input costs.",
        ]
    )
    h = extract_press_release_highlights(html)
    assert h is not None
    assert "The pathway to possible." not in h
    assert "CrownCastle.com" not in h
    assert "Revenue grew 5% to $100 million" in h
    assert "Net income was $20 million, up 10%" in h


def test_leading_bullet_block_footer_pair_does_not_break_block():
    html = _synthetic_doc(
        [
            "NEWS RELEASE",
            "October 16, 2024",
            "ACME CORP REPORTS THIRD QUARTER 2024 RESULTS",
            "•Net income of $0.64 per diluted share, up 10% from the prior year, driven by strong performance across all business segments and continued cost discipline.",
            "The pathway to possible.",
            "CrownCastle.com",
            "•Revenue grew 5% to $100 million, with growth in every region and strong demand for our products throughout the quarter.",
            "•Operating cash flow was $35 million in the quarter, up from $28 million a year ago, as working capital improved and collections accelerated.",
            "•Adjusted EBITDA was $40 million, up 12% from the prior year, reflecting improved margins and disciplined cost management throughout the quarter.",
            "•Gross margin rose to 42% from 39% a year ago as pricing actions and a richer product mix more than offset higher input costs.",
        ]
    )
    h = extract_press_release_highlights(html)
    assert h is not None
    assert "The pathway to possible." not in h
    assert "CrownCastle.com" not in h
    assert "Net income of $0.64 per diluted share" in h
    assert "Revenue grew 5% to $100 million" in h
