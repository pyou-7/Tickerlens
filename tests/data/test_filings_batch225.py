"""Batch 225: the heading-tail class — the trailing-heading drop now
covers the full heading family.

Batch 224 left the heading-tail class open: stored highlights ending
on a table/section heading with nothing after it (Accenture's
"Revenues by Type of Work", Boeing's "Table 1. Summary Financial
Results ...", AEP's "Preliminary, unaudited results"). The batch-157
trailing-heading test missed them on end-word/small-word gaps
("Work", "Year", "Operations", "Liquidity", "Area", "Metrics",
"Share", "by", "per"), on the "Table N." prefix, on a trailing
parenthetical ("(GAAP)", "(In millions ...)", '("EPS")', a segment
list), and on lowercase-led results captions.

The fix lives in the final cleanup only (_clean_highlights_result,
via _is_trailing_heading_tail): the shared _HEADING_END_WORDS /
_HEADING_SMALL_WORDS sets are deliberately NOT widened — _is_lede_title_line
reads them, and widening them turned "Fourth Quarter Full Year" into a
mid-lede title line that changed what the lede collects (caught by the
first blast: DASH/FDX/SPG diffs that were not tail removals). The
batch-225 extended sets are local to the final trim.

Live pins run the extractor against the real cached exhibits; the unit
pins cover each new shape and its guards directly.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _clean_highlights_result,
    _is_trailing_caption_results,
    _is_trailing_heading,
    _is_trailing_heading_tail,
    _is_trailing_table_heading,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _last(hl: str) -> str:
    lines = [ln for ln in hl.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


# --- live pins: the heading tails are gone, the content stays ----------


def test_acn_revenues_by_type_of_work_dropped() -> None:
    hl = extract_press_release_highlights(_read("ACN_2025-11-30.html"))
    assert hl is not None
    assert "Revenues by Type of Work" not in hl
    assert "Revenues for the first quarter of fiscal 2026 were $18.74 billion" in hl


def test_ba_table_1_caption_dropped() -> None:
    hl = extract_press_release_highlights(_read("BA_2024-09-30.html"))
    assert hl is not None
    assert "Table 1. Summary Financial Results" not in hl
    assert "Total company backlog of $511 billion" in hl


def test_aep_preliminary_unaudited_results_dropped() -> None:
    # Batch 226 update: the "AMERICAN ELECTRIC POWER" caps footer is
    # now dropped too (batch 226's _is_trailing_caps_line — the footer
    # is page furniture, and it became the tail once the caption was
    # popped). The pin's intent — the caption is gone, the bullets
    # stay — is unchanged; the footer assertion flips to the intended
    # new behavior.
    hl = extract_press_release_highlights(_read("AEP_2024-09-30.html"))
    assert hl is not None
    assert "Preliminary, unaudited results" not in hl
    assert "AMERICAN ELECTRIC POWER" not in hl
    assert "Expands five-year capital plan to $54 billion" in hl


def test_cat_fourth_quarter_full_year_dropped() -> None:
    # The heading is dropped by the final trim only — the lede still
    # collects it (shared sets untouched), so the bullets stay and the
    # dateline prose is NOT pulled in (the first-cut leak).
    hl = extract_press_release_highlights(_read("CAT_2023-12-31.html"))
    assert hl is not None
    assert "Fourth Quarter Full Year" not in hl
    assert "IRVING, Texas" not in hl
    assert hl.endswith("Returned $7.5 billion to shareholders through share repurchases and dividends in 2023")


def test_cl_gaap_header_dropped() -> None:
    hl = extract_press_release_highlights(_read("CL_2024-03-31.html"))
    assert hl is not None
    assert "First Quarter Total Company Results (GAAP)" not in hl
    assert "updated its financial guidance for full year 2024" in hl


def test_clx_household_segment_label_dropped() -> None:
    hl = extract_press_release_highlights(_read("CLX_2024-09-30.html"))
    assert hl is not None
    assert "Household (Bags and Wraps; Cat Litter; Grilling)" not in hl
    assert "Segment adjusted EBIT2 increased 126%" in hl


def test_dd_consolidated_results_footnote_key_dropped() -> None:
    hl = extract_press_release_highlights(_read("DD_2025-09-30.html"))
    assert hl is not None
    assert "Third Quarter 2025 Consolidated Results(1)" not in hl
    assert "well-positioned to drive continued value creation" in hl


def test_duol_financial_metrics_heading_dropped() -> None:
    hl = extract_press_release_highlights(_read("DUOL_2023-09-30.html"))
    assert hl is not None
    assert "Financial and Key Operating Metrics" not in hl
    assert "Adjusted EBITDA was $22.5 million" in hl


def test_expe_metrics_heading_and_units_note_dropped() -> None:
    hl = extract_press_release_highlights(_read("EXPE_2025-09-30.html"))
    assert hl is not None
    assert "Financial Summary & Operating Metrics" not in hl
    assert "17th consecutive quarter of double-digit growth in B2B" in hl


def test_well_capital_activity_heading_dropped() -> None:
    hl = extract_press_release_highlights(_read("WELL_2024-06-30.html"))
    assert hl is not None
    assert "Capital Activity and Liquidity" not in hl
    assert "appointment of Andrew Gundlach" in hl


def test_dlr_toc_only_result_unchanged_by_floor() -> None:
    # Batch 253: this test pinned the DLR wart — live extraction was a
    # 220-char table-of-contents result whose whole body is headings,
    # kept by the batch-153 floor. The batch-253 ◾ fix removes the
    # wart at its root: the "Highlights" section is no longer rejected
    # as a financial table, so live serves the real bullets and the
    # TOC entries are gone. The "Table of Contents" first line stays
    # — it is the picked headline, a separate wart the stored rows
    # already carry (see the batch-253 DECISIONS entry).
    hl = extract_press_release_highlights(_read("DLR_2026-03-31.html"))
    assert hl is not None
    assert hl.split("\n\n")[0] == "Table of Contents"
    assert "Reported net income available to common stockholders of $0.46" in hl
    assert "Signed total bookings during 1Q26" in hl
    assert "Raised 2026 Core FFO per share outlook to $8.00 - $8.10" in hl
    assert "total revenues of $1.6 billion" in hl
    assert "Adjusted Funds From Operations" not in hl
    assert "Key Quarterly Financial Data" not in hl


# --- unit pins: each new shape ------------------------------------------


def test_trailing_table_heading_predicate() -> None:
    assert _is_trailing_table_heading("Table 1. Summary Financial Results Third Quarter Nine Months")
    assert _is_trailing_table_heading("Table 1. Summary Financial Results First Quarter")
    assert _is_trailing_table_heading("Table 2. Consolidated Statements of Operations")
    # A table caption carrying figures is a data line, not a heading.
    assert not _is_trailing_table_heading("Table 1. Revenue $17.1 billion")
    # A prose sentence that merely mentions a table is not a caption.
    assert not _is_trailing_table_heading("Table 1 shows revenue grew 12% in the quarter.")
    # Terminated, so not a dangling heading.
    assert not _is_trailing_table_heading("Table 1. Summary Financial Results.")


def test_trailing_caption_results_predicate() -> None:
    assert _is_trailing_caption_results("Preliminary, unaudited results")
    assert _is_trailing_caption_results("Overall financial results")
    assert _is_trailing_caption_results("Unaudited results")
    assert _is_trailing_caption_results("Financial results")
    # A wrapped prose fragment ending in "results" carries other words.
    assert not _is_trailing_caption_results("delivered strong quarterly results")
    assert not _is_trailing_caption_results("and other items")
    # Figures or terminal punctuation disqualify.
    assert not _is_trailing_caption_results("Preliminary 2025 results")
    assert not _is_trailing_caption_results("Preliminary, unaudited results.")


def test_trailing_heading_tail_extended_words() -> None:
    assert _is_trailing_heading_tail("Revenues by Type of Work")
    assert _is_trailing_heading_tail("Q4 Revenues by Type of Work")
    assert _is_trailing_heading_tail("Fourth Quarter Full Year")
    assert _is_trailing_heading_tail("Adjusted Funds From Operations")
    assert _is_trailing_heading_tail("Capital Activity and Liquidity")
    assert _is_trailing_heading_tail("Net Revenue by Geographic Area")
    assert _is_trailing_heading_tail("Financial Summary & Operating Metrics")
    assert _is_trailing_heading_tail("Diluted Earnings per Share")
    # The plain batch-157 shapes still qualify.
    assert _is_trailing_heading_tail("CFO Outlook Commentary")
    assert _is_trailing_heading_tail("First Quarter 2026 Financial Results")


def test_trailing_heading_tail_parenthetical() -> None:
    assert _is_trailing_heading_tail("Third Quarter Total Company Results (GAAP)")
    assert _is_trailing_heading_tail("Financial Summary & Operating Metrics (In millions except per share amounts)")
    assert _is_trailing_heading_tail('Diluted Earnings per Share ("EPS")')
    assert _is_trailing_heading_tail("Household (Bags and Wraps; Cat Litter; Grilling)")
    assert _is_trailing_heading_tail("First Quarter 2026 Consolidated Results(1)")
    # A prose line with parens is not a heading: the base must itself
    # be heading-shaped.
    assert not _is_trailing_heading_tail("Net income (GAAP) was $2.1 billion")
    assert not _is_trailing_heading_tail("Revenue (in millions)")
    # A quote attribution with parens never qualifies.
    assert not _is_trailing_heading_tail("— Jane Smith, CEO (retired)")


def test_trailing_heading_tail_guards() -> None:
    # The shared-set guards still hold: the extended sets are local to
    # the final trim, so _is_trailing_heading itself is unchanged.
    assert not _is_trailing_heading("Fourth Quarter Full Year")
    assert not _is_trailing_heading(
        "Goldman Sachs Reports Second Quarter Earnings Per Common"
    )
    assert not _is_trailing_heading("and other items")
    assert not _is_trailing_heading("Revenue $ 51,242 $ 40,589")
    # ... and the tail test inherits them.
    assert not _is_trailing_heading_tail(
        "Goldman Sachs Reports Second Quarter Earnings Per Common"
    )
    assert not _is_trailing_heading_tail("and other items")
    assert not _is_trailing_heading_tail("Revenue $ 51,242 $ 40,589")
    assert not _is_trailing_heading_tail(
        "We look forward to updating you next quarter."
    )


def test_clean_result_drops_heading_tail_only() -> None:
    # A trailing heading is dropped; a mid-body heading and the
    # headline are untouched. (The body is long enough that the
    # batch-153 200-char floor does not veto the trim.)
    result = _clean_highlights_result(
        "Acme Reports Record Third Quarter 2025 Results\n\n"
        "•Revenue grew 12% to $5.2 billion in the quarter, with strong demand across all segments and continued momentum in the core business.\n\n"
        "•Adjusted earnings per share of $1.84 beat expectations, driven by margin expansion and disciplined cost management across the company.\n\n"
        "Fourth Quarter Full Year"
    )
    assert "Fourth Quarter Full Year" not in result
    assert "Revenue grew 12%" in result
    assert "Adjusted earnings per share" in result
    assert result.startswith("Acme Reports Record Third Quarter 2025 Results")
    result2 = _clean_highlights_result(
        "Acme Reports Record Third Quarter 2025 Results\n\n"
        "Financial Summary & Operating Metrics\n\n"
        "•Revenue grew 12% to $5.2 billion in the quarter, with strong demand across all segments and continued momentum in the core business."
    )
    assert "Financial Summary & Operating Metrics" in result2
