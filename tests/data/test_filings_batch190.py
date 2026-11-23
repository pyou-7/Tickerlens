"""Batch 190: compact period fragments are not data rows.

AJG flattens its summary-table column headers one cell per line —
"4th Q 25", "9 Mths 25" — and the density rule reads a fragment's
quarter ordinal + 2-digit year as two figures (2 of 3 tokens), so
_is_lede_data_row qualifies it. _is_lede_table_label's next-line
check then misreads a heading directly above one ("Summary of
Financial Results - Fourth Quarter") as a table label. The full-cache
survey finds 109 such misfires, all AJG, all table chrome the other
rules drop anyway — latent today (the batch-188 summary-title branch
drops the heading first) — but the predicate is wrong on its face:
a period fragment carries period labels, not values. The fragment
stays table residue via the _is_lede_table_line branch added in this
batch, which is the only branch that caught it before (period_header
and table-cell both read False on it).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_lede_compact_period_fragment,
    _is_lede_data_row,
    _is_lede_recon_row,
    _is_lede_table_label,
    _is_lede_table_line,
    extract_press_release_highlights,
)

FRAGMENTS = ["4th Q 25", "3rd Q 24", "9 Mths 25", "1st Q 2026", "2nd Q 2025"]


def test_compact_period_fragments_are_not_data_rows():
    for ln in FRAGMENTS:
        assert _is_lede_compact_period_fragment(ln), ln
        assert not _is_lede_data_row(ln), ln
        # Neither a recon row either — the predicates stay disjoint and
        # the fragment is neither kind of row.
        assert not _is_lede_recon_row(ln), ln
    # Real data rows are untouched by the exemption.
    assert _is_lede_data_row(
        "Net income (loss) per share\u2014diluted $0.65 $(3,903) N/A $0.55 $0.10"
    )
    assert _is_lede_data_row("Net Sales Growth (0.5%) - 0.5% 1.5% - 3.5%")
    assert _is_lede_data_row("Restructuring / Related Costs ~$0.06 ~$0.20")
    assert _is_lede_data_row("\u2013 \u2013 65 33 87 44 0.25 0.13")  # batch 187 pin
    # A bare year is not a fragment, and a prose line with two figures
    # keeps the old verdict (terminated prose never qualifies).
    assert not _is_lede_compact_period_fragment("4th Q")
    assert not _is_lede_data_row("Revenue grew 20% in 2025.")


def test_compact_period_fragments_are_table_lines():
    # The fragment is still table residue — without this branch the
    # data-row exemption would let it leak into the lede as content.
    for ln in FRAGMENTS:
        assert _is_lede_table_line(ln), ln
    assert not _is_lede_table_line(
        "Our two-pronged growth strategy drove double-digit growth."
    )


def test_table_label_check_ignores_compact_fragment_next_line():
    # The AJG Q4 FY2025 heading misclassification (batch 189's carried
    # item): the heading above a period fragment is not a table label.
    assert not _is_lede_table_label(
        "Summary of Financial Results - Fourth Quarter", "4th Q 25"
    )
    assert not _is_lede_table_label("Revenues Before", "3rd Q 23")
    assert not _is_lede_table_label("Compensation Expense and Ratios", "2nd Q 2025")
    # Genuine labels above real values rows still qualify (batch 160 pins).
    assert _is_lede_table_label(
        "Property-Liability combined ratio",
        "Recorded 96.4 103.4 (7.0) 96.9 109.8 (12.9)",
    )
    assert _is_lede_table_label(
        "Total policies in force (in thousands)", "205,483 190,089 8.1 %"
    )


def test_ajg_q4_extraction_unchanged():
    # No-regression pin on the real exhibit (0-diff blast): the title
    # is still dropped by the summary-title branch, the fragment is
    # still dropped as a table line, and the quote body is served.
    cache = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
    html = open(os.path.join(cache, "AJG_2025-12-31.html"), encoding="utf-8").read()
    out = extract_press_release_highlights(html)
    assert out is not None
    assert "4th Q 25" not in out
    assert "Summary of Financial Results" not in out
    assert "We had an excellent fourth quarter and a terrific 2025!" in out
    assert "double-digit top line growth for the 20th straight quarter" in out
