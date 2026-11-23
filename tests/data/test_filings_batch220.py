"""Batch 220: a single-value key-metric line is not a table data row.

Citi's "2024 PAYOUT RATIO OF 58% (3)" was dropped from every quarter's
highlights by two independent misclassifications: _is_lede_data_row
counted the leading year ("2024") and the trailing footnote key ("(3)")
as values, so 1 real value read as 3 figures in 6 tokens (50% density);
and _is_lede_table_line's footnote-tail branch caught any <=6-word line
ending in "(N)". A data row is a label plus values — a year in the label
and a footnote key on the value are not values. The fix counts value
figures (excluding a leading bare year and a trailing single-char paren
key) in _is_lede_data_row, and _is_lede_caps_metric_line exempts the
all-caps key-metric shape from the footnote-tail branch. The corpus
attests exactly 11 such lines, all Citi payout ratios, plus 3 CET1
ratio lines rescued by the data-row fix alone.

The rescue displaces 1-3 tail lede paragraphs per quarter through the
fixed 11-line lede budget; the displaced paragraphs are the last ones
and their headline numbers survive in the dateline paragraph and the
CEO quote.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_lede_caps_metric_line,
    _is_lede_data_row,
    _is_lede_table_line,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


# A single-value metric line is not a data row, with or without a
# leading year label.
def test_data_row_single_value_metric_not_a_row():
    assert not _is_lede_data_row("2024 PAYOUT RATIO OF 58% (3)")
    assert not _is_lede_data_row("PAYOUT RATIO OF 49% (3)")
    assert not _is_lede_data_row("COMMON EQUITY TIER 1 CAPITAL RATIO OF 13.2% (6)")
    assert not _is_lede_data_row("2024 PAYOUT RATIO OF 58%")


# Genuine multi-value rows still classify as rows, including one whose
# label opens with a year.
def test_data_row_multi_value_rows_still_rows():
    assert _is_lede_data_row("Operating margin 23.1% 41.5% (1)")
    assert _is_lede_data_row("Earnings per share $0.91 $1.70 (3)")
    assert _is_lede_data_row("Organic revenue growth (Non-GAAP) 6% 6%")
    assert _is_lede_data_row(
        "Net income (loss) per share—diluted $0.65 $(3,903) N/A $0.55 $0.10"
    )
    assert _is_lede_data_row("2024 Revenue $5.0 $6.0")
    assert _is_lede_data_row("Net Sales Growth (0.5%) - 0.5% 1.5% - 3.5%")


# A repeated parenthesized value is a column value, not a footnote
# key — the batch-159 shape stays a row.
def test_data_row_repeated_paren_value_still_a_row():
    assert _is_lede_data_row("Acquisition and Disposition Impacts — (2) — (2)")
    assert _is_lede_data_row("Tax Impact — 1 — 1")


# The batch-183 $-range exemption is untouched by the recount.
def test_data_row_dollar_range_still_exempt():
    assert not _is_lede_data_row(
        "Reaffirms 2026 Outlook for Adjusted EPS of $7.50 to $8.00"
    )


# The caps-metric shape is exactly the attested one: all-caps label of
# >=3 words, one digit-% value, single-char footnote key.
def test_caps_metric_line_shape():
    assert _is_lede_caps_metric_line("2024 PAYOUT RATIO OF 58% (3)")
    assert _is_lede_caps_metric_line("PAYOUT RATIO OF 49% (3)")
    assert _is_lede_caps_metric_line("PAYOUT RATIO OF 176% (5)")
    assert not _is_lede_caps_metric_line("Less than 60% (5)")  # mixed case
    assert not _is_lede_caps_metric_line("20.9% (a)")  # <3 label words
    assert not _is_lede_caps_metric_line("Nuclear Capacity Factor (%)(f)")  # no value
    assert not _is_lede_caps_metric_line(
        "Series J 8.375% Cumulative Redeemable (4)"
    )  # mixed case
    assert not _is_lede_caps_metric_line(
        "BOOK VALUE PER SHARE OF $101.62"
    )  # no footnote key
    assert not _is_lede_caps_metric_line(
        "TANGIBLE BOOK VALUE PER SHARE OF $89.34 (4)"
    )  # >6 words


# End to end through _is_lede_table_line: the metric is kept, the
# residue shapes still drop.
def test_table_line_metric_kept_residue_dropped():
    assert not _is_lede_table_line("2024 PAYOUT RATIO OF 58% (3)")
    assert not _is_lede_table_line("PAYOUT RATIO OF 49% (3)")
    assert not _is_lede_table_line("COMMON EQUITY TIER 1 CAPITAL RATIO OF 13.2% (6)")
    assert not _is_lede_table_line("BOOK VALUE PER SHARE OF $101.62")
    assert _is_lede_table_line("Less than 60% (5)")
    assert _is_lede_table_line("20.9% (a)")
    assert _is_lede_table_line("$ 6.38 (a)")
    assert _is_lede_table_line("% Change (1)")
    assert _is_lede_table_line("Operating margin 23.1% 41.5% (1)")


# Live pins on real exhibits: the payout ratio (and CET1 where the
# exhibit carries one) is served, inside the 11-line lede budget.
def test_citi_payout_ratio_served_q4_2024():
    out = extract_press_release_highlights(_read("C_2024-12-31.html"))
    assert out is not None
    assert "2024 PAYOUT RATIO OF 58% (3)" in out
    assert "TANGIBLE BOOK VALUE PER SHARE OF $89.34 (4)" in out
    assert "CEO COMMENTARY" not in out
    assert len([ln for ln in out.splitlines() if ln.strip()]) == 11


def test_citi_payout_and_cet1_served_q4_2025():
    out = extract_press_release_highlights(_read("C_2025-12-31.html"))
    assert out is not None
    assert "2025 PAYOUT RATIO OF 133% (5)" in out
    assert "COMMON EQUITY TIER 1 CAPITAL RATIO OF 13.2% (6)" in out
    assert len([ln for ln in out.splitlines() if ln.strip()]) == 11
