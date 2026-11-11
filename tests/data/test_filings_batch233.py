"""Batch 233: the split guidance table — APP x7 + DD x4 NULL-guidance
rows were blocked by batch-231 gate G (table fraction >= 0.2) because
their guidance section is a flattened split table: a bare label line,
then 1-2 figure-only value lines, plus footnote-definition furniture.
The fix is a post-collection clean step (_clean_guidance_result) that
fuses split rows to "Label: v1 / v2" (or "Label: low – high" for a
Low/High table), merges dash-led value lines into the previous unit,
drops footnote-definition blocks and pure rule lines, and splits a
units line carrying its Low/High headers.

Blast-radius method: guidance old-vs-new over 1,699 cached exhibits
(scripts/batch233_guidance_blast.py, hidden_files/blast233_diff.txt):
226 exhibits changed, 0 gained/lost guidance, all verified
line-by-line. The defects the blast caught and the fixes that
followed are pinned here: Cigna's comma-separated footnote keys
read as figures ("Pre-Tax: 1,2"), qualifier labels ("at least:
$7,000"), a bare "+" label, a prose sentence chopped at its year
("The Cigna Group's: 2025"), Centene's dropped "Full Year 2024"
period line and its "EPS >: $5.94" qualifier, Elevance's date
fragments ("December: 31,") and qualifier-tailed labels
("... Approximately: ($0.89)"), Emerson's missing-value dashes
("Step-up ---: $0.38"), and Moody's "Up to: $3.0 billion".

Live pins run the extractor against the real cached exhibits; the
unit pins cover each new predicate and its guards directly.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _clean_guidance_result,
    _guidance_value_figures,
    _is_guidance_header_token_line,
    _is_guidance_table_label,
    _is_guidance_value_line,
    _move_label_qualifier,
    _split_guidance_fused_row,
    extract_management_guidance,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _lines(g: str) -> list[str]:
    return [ln for ln in g.splitlines() if ln.strip()]


def _guidance(name: str) -> list[str]:
    return _lines(extract_management_guidance(_read(name)) or "")


# --- live pins: the split table fuses, the furniture drops ---------


def test_app_2024_12_31_fuses_and_drops_footnotes():
    g = _guidance("APP_2024-12-31.html")
    assert "Advertising Revenue: $1,030 – $1,050" in g
    assert "Apps Revenue: 325 – 335" in g
    assert "Total Revenue: 1,355 – 1,385" in g
    assert "Total Adjusted EBITDA: $855 – $885" in g
    assert "Total Adjusted EBITDA Margin: 63% – 64%" in g
    assert "1Q25" not in g
    assert "Low" not in g
    assert not any(ln.startswith("2Includes") for ln in g)
    assert not any("We have not provided" in ln for ln in g)


def test_app_2025_06_30_fuses_and_drops_footnote():
    g = _guidance("APP_2025-06-30.html")
    assert "Revenue: $1,320 – $1,340" in g
    assert "Adjusted EBITDA: $1,070 – $1,090" in g
    assert "Adjusted EBITDA margin: 81% – 81%" in g
    assert "3Q25" not in g
    assert not any(ln.startswith("1Includes") for ln in g)


def test_dd_2024_12_31_fuses_split_rows():
    g = _guidance("DD_2024-12-31.html")
    assert "Net sales: ~$3,025 / $12,800 - $12,900" in g
    assert "Operating EBITDA(2): ~$760 / $3,325 - $3,375" in g
    assert "Adjusted EPS(2): ~$0.95 / $4.30 - $4.40" in g


def test_csco_fuses_ranges():
    g = _guidance("CSCO_2023-10-28.html")
    assert "Revenue: $12.6 billion - $12.8 billion" in g
    assert "Non-GAAP gross margin rate: 65% – 66%" in g
    assert "Non-GAAP EPS: $0.82 – $0.84" in g
    assert "Revenue: $53.8 billion - $55.0 billion" in g


def test_dal_drops_footnotes_1_to_4():
    g = _guidance("DAL_2024-12-31.html")
    assert "Earnings Per Share: $0.70 - $1.00" in g
    assert not any("Non-GAAP measures; Refer to" in ln for ln in g)
    assert not any("CrowdStrike-caused outage" in ln for ln in g)
    assert not any("Introduced at November 2024 Investor Day" in ln for ln in g)


def test_fico_and_aph_normalize_fused_rows():
    g = _guidance("FICO_2024-03-31.html")
    assert "Non-GAAP Net Income: $566 million $573 million" in g
    assert "Non-GAAP EPS: $22.45 $22.80" in g
    g = _guidance("APH_2024-09-30.html")
    assert "Diluted EPS (GAAP): $0.48 - $0.50 / $1.81 - $1.83" in g
    assert "Adjusted Diluted EPS (non-GAAP) (2): $0.48 - $0.50 / $1.82 - $1.84" in g
    assert not any(set(ln) == {"_"} for ln in g)


def test_akam_low_high_joins_and_header_drops():
    g = _guidance("AKAM_2023-12-31.html")
    assert "Revenue (in millions): $980 – $1,000" in g
    assert "Non-GAAP operating margin*: 29% – 30%" in g
    assert "Low End High End" not in g
    assert "Revenue growth rates year-over-year*(2): 6% – 8%" in g


# --- live pins: the blast-caught defects stay fixed -----------------


def test_ci_footnote_keys_are_not_figures():
    g = _guidance("CI_2023-12-31.html")
    assert "Capital Expenditures 2: ~$1,500" in g
    assert "Shareholder Dividends 2: ~$1,550" in g
    assert "Weighted Average Shares Outstanding (millions) 2: 282 to 286" in g
    assert not any("Pre-Tax: 1,2" in ln for ln in g)
    assert not any("Medical Care Ratio: 2,5" in ln for ln in g)
    assert not any("Total Medical Customers: 2,6" in ln for ln in g)


def test_ci_qualifier_and_prose_do_not_fuse():
    g = _guidance("CI_2023-12-31.html")
    assert "Adjusted Income from Operations, Pre-Tax 1,2" in g
    assert "at least $7,000" in g
    assert not any(ln.startswith("at least:") for ln in g)
    assert not any("The Cigna Group's: 2025" in ln for ln in g)
    assert any("The foregoing statements represent" in ln for ln in g)
    g = _guidance("CI_2024-03-31.html")
    assert "+$25" in g
    assert not any(ln.startswith("+:") for ln in g)


def test_cnc_keeps_period_and_moves_qualifier():
    g = _guidance("CNC_2024-03-31.html")
    assert "Full Year 2024" in g
    assert "GAAP diluted EPS: > $5.94" in g
    assert "Adjusted diluted EPS (1): > $6.80" in g
    assert "Total revenues (in billions): $147.5 – $150.5" in g


def test_elv_date_fragments_stay_put():
    g = _guidance("ELV_2023-12-31.html")
    assert "December 31," in g
    assert "September 30," in g
    assert not any(ln.startswith("December:") for ln in g)
    assert "Individual: 1,025" in g
    assert "Commercial Risk-Based: 4,781 / 4,777" in g


def test_elv_qualifier_moves_to_values():
    g = _guidance("ELV_2024-06-30.html")
    assert "Tax impact of non-GAAP adjustments: Approximately ($0.89)" in g
    assert "Adjusted shareholders' earnings per diluted share: At least $37.20" in g


def test_emr_missing_value_dash_moves_to_values():
    g = _guidance("EMR_2023-12-31.html")
    assert "Amortization of Acquisition-related Inventory Step-up: --- $0.38" in g
    assert "Discrete Tax Benefits: --- ($0.10)" in g


def test_emr_lone_year_header_still_forms():
    # A lone "2024" ahead of Emerson's table is a period header, not
    # a value line — without the guard the pending header never forms
    # and no fused row in the table normalizes.
    g = _guidance("EMR_2024-06-30.html")
    assert "2024" in g
    assert "Net Sales Growth: ~15%" in g
    assert "Earnings Per Share: $2.82 - $2.87" in g
    assert "Adjusted Earnings Per Share: $5.45 - $5.50" in g


def test_mco_up_to_moves_to_values():
    g = _guidance("MCO_2026-06-30.html")
    assert "and other ongoing capital allocation decisions): Up to $3.0 billion" in g


def test_first_fused_row_without_context_stays_unfused():
    # Genuine Parts' "Total sales growth" is the section's first fused
    # row with no pending header and no row seen yet, so it stays
    # as-is; the later fused rows normalize once the split
    # "Diluted earnings per share(1)" row establishes the table.
    g = _guidance("GPC_2024-12-31.html")
    assert "Total sales growth 2% to 4%" in g
    assert "Diluted earnings per share(1): $6.95 to $7.45" in g
    assert "Free cash flow: $800 million to $1.0 billion" in g


# --- unit pins: the predicates --------------------------------------


def test_value_line_shapes():
    assert _is_guidance_value_line("$1,030 $1,050")
    assert _is_guidance_value_line("~$3,025")
    assert _is_guidance_value_line("> $6.80")
    assert _is_guidance_value_line("($0.70) – ($0.10)")
    assert _is_guidance_value_line("2x - 3x")
    assert not _is_guidance_value_line("at least $235,000")
    assert not _is_guidance_value_line("Greater than 10%")
    assert not _is_guidance_value_line("Net sales growth")
    # A lone 1-3 digit line is a page number, not a value.
    assert not _is_guidance_value_line("42")
    assert not _is_guidance_value_line("(2)")
    # A lone 4-digit line is a year, not a value.
    assert not _is_guidance_value_line("2024")


def test_value_figures_filters_keys_and_years():
    assert _guidance_value_figures("(1) $1.91 - $1.97") == ["$1.91", "$1.97"]
    assert _guidance_value_figures("Pre-Tax 1,2") == []
    assert _guidance_value_figures("The Cigna Group's 2025") == []
    assert _guidance_value_figures("$12.6 billion - $12.8 billion") == [
        "$12.6",
        "$12.8",
    ]


def test_table_label_guards():
    assert _is_guidance_table_label("Net sales")
    assert _is_guidance_table_label("Shares used in non-GAAP per diluted share calculations * (in millions)")
    assert not _is_guidance_table_label("December")
    assert not _is_guidance_table_label("at least $235,000")
    assert not _is_guidance_table_label("The foregoing statements represent")
    assert not _is_guidance_table_label("+")
    assert not _is_guidance_table_label("Full Year 2024 Outlook")
    # A qualifier-tailed label IS a label — the qualifier moves to
    # the values at fuse time, it does not void the row.
    assert _is_guidance_table_label("Net sales growth in the range of approximately")


def test_header_token_line_drops_only_column_headers():
    assert _is_guidance_header_token_line("Low")
    assert _is_guidance_header_token_line("Low High")
    assert _is_guidance_header_token_line("Low End High End")
    assert _is_guidance_header_token_line("1Q25")
    assert not _is_guidance_header_token_line("Full Year 2024")
    assert not _is_guidance_header_token_line("Full Year 2025E")
    assert not _is_guidance_header_token_line("2025")


def test_move_label_qualifier():
    assert _move_label_qualifier("GAAP diluted EPS >", "$5.94") == (
        "GAAP diluted EPS",
        "> $5.94",
    )
    assert _move_label_qualifier(
        "Tax impact of non-GAAP adjustments Approximately", "($0.89)"
    ) == (
        "Tax impact of non-GAAP adjustments",
        "Approximately ($0.89)",
    )
    assert _move_label_qualifier(
        "Adjusted shareholders' earnings per diluted share At least", "$37.20"
    ) == (
        "Adjusted shareholders' earnings per diluted share",
        "At least $37.20",
    )
    assert _move_label_qualifier(
        "and other ongoing capital allocation decisions) Up to", "$3.0 billion"
    ) == (
        "and other ongoing capital allocation decisions)",
        "Up to $3.0 billion",
    )
    assert _move_label_qualifier(
        "Amortization of Acquisition-related Inventory Step-up ---", "$0.38"
    ) == (
        "Amortization of Acquisition-related Inventory Step-up",
        "--- $0.38",
    )
    # A trailing em-dash that is part of the metric name stays.
    assert _move_label_qualifier("Net income (loss)", "$28,635") == (
        "Net income (loss)",
        "$28,635",
    )


def test_split_fused_row_guards():
    assert _split_guidance_fused_row("Revenue $12.6 billion - $12.8 billion") == (
        "Revenue",
        "$12.6 billion - $12.8 billion",
    )
    assert _split_guidance_fused_row("December 31,") is None
    assert _split_guidance_fused_row("The Cigna Group's 2025") is None
    assert _split_guidance_fused_row("Adjusted Income from Operations, Pre-Tax 1,2") is None
    # The split returns the raw pair; the qualifier move happens in
    # the caller (_clean_guidance_result), not here.
    assert _split_guidance_fused_row("Net sales growth in the range of approximately 3.7% to 4.2%") == (
        "Net sales growth in the range of approximately",
        "3.7% to 4.2%",
    )


def test_clean_guidance_result_synthetic():
    out = _clean_guidance_result(
        [
            "First Quarter 2025 Financial Guidance Summary",
            "(In millions, except percentages)",
            "Low",
            "High",
            "Advertising Revenue",
            "$1,030 $1,050",
            "Apps Revenue 325 335",
            "Total Adjusted EBITDA Margin",
            "63% 64%",
            "2Includes repurchased shares as well as withholdings",
            "3 We have not provided the forward-looking GAAP equivalents",
            "for forward-looking non-GAAP metrics.",
            "____________________________________",
        ]
    )
    assert "Advertising Revenue: $1,030 – $1,050" in out
    assert "Apps Revenue: 325 – 335" in out
    assert "Total Adjusted EBITDA Margin: 63% – 64%" in out
    assert "Low" not in out
    assert not any("Includes repurchased" in ln for ln in out)
    assert not any("We have not provided" in ln for ln in out)
    assert not any(set(ln) == {"_"} for ln in out)
    # Prose and headings pass through untouched.
    out = _clean_guidance_result(
        ["Outlook", "We expect revenue to grow.", "Net sales: $1,000"]
    )
    assert out == ["Outlook", "We expect revenue to grow.", "Net sales: $1,000"]
