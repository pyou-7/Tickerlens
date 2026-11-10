"""Batch 226: the table-residue tail class — stored/live highlights
ending on a flattened table row or label with no heading shape
(BlackRock/Berkshire row labels, Aon's units+period header, AEP's
all-caps page footer, Expedia's metric rows, dangling period/table
headers, the whole AEP flattened earnings table once its rows are
trimmed).

The fix lives in the final cleanup only (_clean_highlights_result):
five new trailing-trim predicates plus a colon-dangling rule and a
period-suffix strip on the heading test. _is_lede_table_line is
deliberately NOT consulted — its 262 stored-tail matches include
genuine content (Cencora's "5% to 7% growth $285.0B" guidance
fragment, Centene's "GAAP diluted EPS $ 1.36" single-value row,
JPMorgan's truncated prose, Palantir's ◦ customer-count bullet),
because the lede loop skips a line to free budget for later lines
while the final trim drops it for good. The first blast caught the
Palantir false positive (the 25%-density branch read the ◦ bullet
as a row) and the dangling headers the first cut left behind
("EPS ($):", "First Nine Months 2026", "Net earnings includes:",
the " - Fourth Quarter 2023" table title); the data-row predicate
now refuses flattened-list bullets and requires 40% figure density,
and the trim completes the cascade (colon rule, trailing period
header, period-suffix strip) instead of stopping mid-table.

Live pins run the extractor against the real cached exhibits; the
unit pins cover each new shape and its guards directly.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _clean_highlights_result,
    _is_trailing_caps_line,
    _is_trailing_heading_tail,
    _is_trailing_row_label,
    _is_trailing_table_data_row,
    _is_trailing_table_header_orphan,
    _is_trailing_units_period_header,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _last(hl: str) -> str:
    lines = [ln for ln in hl.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


# --- live pins: the table residue is gone, the content stays ---------


def test_acn_revenues_orphan_dropped() -> None:
    hl = extract_press_release_highlights(_read("ACN_2025-05-31.html"))
    assert hl is not None
    assert _last(hl) == "• Managed Services new bookings were $10.62 billion."
    assert "Revenues" not in _last(hl)


def test_aep_earnings_table_stripped_to_prose() -> None:
    hl = extract_press_release_highlights(_read("AEP_2023-12-31.html"))
    assert hl is not None
    assert "EPS ($):" not in hl
    assert "AMERICAN ELECTRIC POWER" not in hl
    assert "Preliminary, unaudited results" not in hl
    assert "GAAP 0.64 0.75" not in hl
    assert "Year-end 2023 GAAP earnings of $4.26 per share" in hl


def test_aep_q1_table_stripped_to_prose() -> None:
    hl = extract_press_release_highlights(_read("AEP_2024-03-31.html"))
    assert hl is not None
    assert "2024 2023 Variance" not in hl
    assert "First-quarter 2024 GAAP earnings of $1.91 per share" in hl


def test_aep_caps_footer_dropped() -> None:
    hl = extract_press_release_highlights(_read("AEP_2024-09-30.html"))
    assert hl is not None
    assert "AMERICAN ELECTRIC POWER" not in hl
    assert "Expands five-year capital plan to $54 billion" in hl


def test_aon_units_period_header_dropped() -> None:
    hl = extract_press_release_highlights(_read("AON_2026-09-30.html"))
    assert hl is not None
    assert "(millions, except percentages and per share data)" not in hl
    assert "First Nine Months 2026" not in hl
    assert "significant momentum" in hl


def test_bby_row_label_dropped() -> None:
    hl = extract_press_release_highlights(_read("BBY_2025-02-01.html"))
    assert hl is not None
    assert "Adjusted1 operating income as a % of revenue" not in hl
    assert "FY25 had 52 weeks compared to 53 weeks in FY24" in hl


def test_blk_row_label_dropped() -> None:
    hl = extract_press_release_highlights(_read("BLK_2024-12-31.html"))
    assert hl is not None
    assert "attributable TO noncontrolling interests" not in hl
    assert "restructuring charge(1) of $61 million" in hl


def test_brkb_label_and_colon_intro_dropped() -> None:
    hl = extract_press_release_highlights(_read("BRK.B_2024-12-31.html"))
    assert hl is not None
    assert "Net earnings attributable to Berkshire shareholders" not in hl
    assert "Net earnings includes:" not in hl
    assert "after-tax basis" in hl


def test_csco_operating_income_label_dropped() -> None:
    hl = extract_press_release_highlights(_read("CSCO_2024-10-26.html"))
    assert hl is not None
    assert _last(hl).startswith("Operating Expenses")
    assert "Operating Income" not in _last(hl)


def test_expe_summary_table_stripped_to_prose() -> None:
    hl = extract_press_release_highlights(_read("EXPE_2023-09-30.html"))
    assert hl is not None
    assert "Booked room nights" not in hl
    assert "Expedia Group, Inc." not in hl
    assert "Financial Summary" not in hl
    assert "Repurchased approximately 17 million shares" in hl


def test_expe_period_suffixed_title_dropped() -> None:
    hl = extract_press_release_highlights(_read("EXPE_2023-12-31.html"))
    assert hl is not None
    assert "Fourth Quarter 2023" not in hl
    assert "Repurchased over 19 million shares" in hl


def test_cmcsa_junk_and_period_header_dropped() -> None:
    hl = extract_press_release_highlights(_read("CMCSA_2024-09-30.html"))
    assert hl is not None
    assert "\\\\" not in hl
    assert "3rd Quarter Consolidated Financial Results" not in hl
    assert "Paris Olympics" in hl


def test_gis_footnote_glyph_dropped() -> None:
    hl = extract_press_release_highlights(_read("GIS_2024-11-24.html"))
    assert hl is not None
    assert _last(hl) == "market share trends"


# --- live guard pins: genuine content tails survive -------------------


def test_pltr_flat_bullet_kept() -> None:
    # The first cut dropped this ◦ bullet as a data row (the 25%
    # branch read it as a row); the flattened-bullet guard + 40%
    # density floor keep it.
    hl = extract_press_release_highlights(_read("PLTR_2023-09-30.html"))
    assert hl is not None
    assert "US commercial customer count grew 37% year-over-year" in hl


def test_cor_guidance_range_kept() -> None:
    hl = extract_press_release_highlights(_read("COR_2025-09-30.html"))
    assert hl is not None
    assert _last(hl) == "5% to 7% growth $285.0B"


def test_cnc_single_value_row_kept() -> None:
    hl = extract_press_release_highlights(_read("CNC_2024-09-30.html"))
    assert hl is not None
    assert _last(hl) == "GAAP diluted EPS $ 1.36"


# --- unit pins: row labels --------------------------------------------


def test_row_label_shapes() -> None:
    assert _is_trailing_row_label("Net earnings attributable to Berkshire shareholders")
    assert _is_trailing_row_label("Net earnings (losses) attributable to Berkshire shareholders")
    assert _is_trailing_row_label(
        "RY OF NONOPERATING INCOME (expense), less net income (loss) attributable TO noncontrolling interests"
    )
    assert _is_trailing_row_label("Adjusted1 operating income as a % of revenue")
    assert _is_trailing_row_label("Non-GAAP operating income as a % of revenue")
    assert _is_trailing_row_label("Operating Income")
    assert _is_trailing_row_label("Net earnings per average equivalent Class A Share")
    assert _is_trailing_row_label("Earnings per share")


def test_row_label_guards() -> None:
    assert not _is_trailing_row_label("Return of capital to shareholders was $2.1 billion")
    assert not _is_trailing_row_label(
        "of $0.36 dividends per common share and $0.42 increase in tangible net book value per common share"
    )
    assert not _is_trailing_row_label("shareholders through both dividends and")
    assert not _is_trailing_row_label("Operating cash flow of $326 million")
    assert not _is_trailing_row_label("• Net earnings attributable to Berkshire shareholders")
    assert not _is_trailing_row_label("Net earnings attributable to Berkshire shareholders.")
    assert not _is_trailing_row_label("driven by favorable underwriting and volume")


# --- unit pins: units + period headers ---------------------------------


def test_units_period_header_shapes() -> None:
    assert _is_trailing_units_period_header(
        "(millions, except percentages and per share data) 2026 2025 Change 2026 2025 Change"
    )
    assert _is_trailing_units_period_header("In millions, except per share amounts 2024 2023 Change")
    assert _is_trailing_units_period_header(
        "In thousands, except per share data (unaudited) 2025 2024 % Change"
    )
    assert _is_trailing_units_period_header("In millions")
    assert _is_trailing_units_period_header("(Amounts in thousands, except per share data)")
    assert _is_trailing_units_period_header("In millions, except per share data (unaudited)")


def test_units_period_header_guards() -> None:
    assert not _is_trailing_units_period_header(
        "In billions, except percentages and per share data, revenue grew 8%."
    )
    assert not _is_trailing_units_period_header("In millions of shares outstanding")
    assert not _is_trailing_units_period_header("• In millions, except per share amounts 2024 2023 Change")


# --- unit pins: all-caps lines -----------------------------------------


def test_caps_line_shapes() -> None:
    assert _is_trailing_caps_line("AMERICAN ELECTRIC POWER")
    assert _is_trailing_caps_line("FINANCIAL HIGHLIGHTS")


def test_caps_line_guards() -> None:
    assert not _is_trailing_caps_line(
        "MAINTAINS FISCAL YEAR SALES, EPS GROWTH AND CASH RETURN GUIDANCE"
    )
    assert not _is_trailing_caps_line("#1 Global Financial Ecosystem")
    assert not _is_trailing_caps_line("AMERICAN ELECTRIC POWER COMPANY INCORPORATED EXTRA WORDS HERE")
    assert not _is_trailing_caps_line("American Electric Power")


# --- unit pins: table data rows ----------------------------------------


def test_table_data_row_shapes() -> None:
    assert _is_trailing_table_data_row("Booked room nights 97.4 89.3 9%")
    assert _is_trailing_table_data_row("Organic Sales Growth +1.4 %")
    assert _is_trailing_table_data_row("Enterprise $ 13,814 $ 13,948 $ 41,691 $ 41,528")
    assert _is_trailing_table_data_row("GAAP 0.64 1.01 (0.37) 2.55 1.78 0.77")
    assert _is_trailing_table_data_row("Revenue $3,929 $3,619 9%")
    assert _is_trailing_table_data_row("Gross bookings $25,685 $23,987 7%")
    # Expedia's "Metric Q… Δ Y/Y" column header reads as a data row
    # by density (its quarter/year tokens count as figures); the
    # header-orphan predicate does not catch it, the data row does.
    assert _is_trailing_table_data_row("Metric Q1 2025 Q1 2024 Δ Y/Y")


def test_table_data_row_guards() -> None:
    assert not _is_trailing_table_data_row("5% to 7% growth $285.0B")
    assert not _is_trailing_table_data_row("$7.35 billion to $7.40 billion")
    assert not _is_trailing_table_data_row("Non-GAAP diluted EPS $15.75 to $16.25")
    assert not _is_trailing_table_data_row(
        "◦ US commercial customer count grew 37% year-over-year, from 132 customers in Q3 2022 to 181 customers in Q3 2023"
    )
    assert not _is_trailing_table_data_row("8.9 % 8.5 %")
    assert not _is_trailing_table_data_row("$2.65 17% $9.73 17%")
    assert not _is_trailing_table_data_row("GAAP diluted EPS $ 1.36")
    assert not _is_trailing_table_data_row("7.6 %")
    assert not _is_trailing_table_data_row("• Booked room nights 97.4 89.3 9%")


# --- unit pins: table header orphans ------------------------------------


def test_table_header_orphan_shapes() -> None:
    assert _is_trailing_table_header_orphan("Full Year 2024")
    assert _is_trailing_table_header_orphan("First Nine Months 2026")
    assert _is_trailing_table_header_orphan("2024 2023 Variance")
    assert _is_trailing_table_header_orphan("Fourth Quarter ended December 31 Year-to-date ended December 31")
    assert _is_trailing_table_header_orphan("Revenues")
    assert _is_trailing_table_header_orphan("Stock Split")
    assert _is_trailing_table_header_orphan("GAAP Non-GAAP")
    assert _is_trailing_table_header_orphan("\\\\")
    assert _is_trailing_table_header_orphan("¹")
    assert _is_trailing_table_header_orphan("Six Months")
    assert _is_trailing_table_header_orphan("Ended")
    assert _is_trailing_table_header_orphan("Third Quarter")
    assert _is_trailing_table_header_orphan("First Quarter")


def test_table_header_orphan_guards() -> None:
    assert not _is_trailing_table_header_orphan("7.6 %")
    assert not _is_trailing_table_header_orphan("Zepbound")
    assert not _is_trailing_table_header_orphan("Record quarter")
    assert not _is_trailing_table_header_orphan("• Revenues")
    assert not _is_trailing_table_header_orphan("Third Quarter ended September 30, 2025.")


# --- unit pins: period-suffixed heading + colon cascade ------------------


def test_heading_tail_period_suffix() -> None:
    assert _is_trailing_heading_tail(
        "Financial Summary & Operating Metrics (In millions, except per share amounts) - Fourth Quarter 2023"
    )
    assert not _is_trailing_heading_tail("Revenue grew 10% - Fourth Quarter 2023")


def test_clean_highlights_colon_cascade() -> None:
    body = (
        "Headline Goes Here And It Is Long Enough To Pass The Floor Check For This Test Body\n\n"
        "• First bullet with real content about the quarter and its results for investors.\n"
        "• Second bullet with more content about guidance and the outlook for next year.\n"
        "EPS ($):\n"
        "GAAP 0.64 1.01 (0.37) 2.55 1.78 0.77\n"
    )
    out = _clean_highlights_result(body)
    assert "EPS ($):" not in out
    assert "GAAP 0.64" not in out
    assert "Second bullet with more content" in out


def test_clean_highlights_colon_without_residue_kept() -> None:
    # The colon rule only fires inside a residue cascade: a bare
    # list intro with no residue popped above it stays put.
    body = (
        "Headline Goes Here And It Is Long Enough To Pass The Floor Check For This Test Body\n\n"
        "• First bullet with real content about the quarter and its results for investors.\n"
        "• Second bullet with more content about guidance and the outlook for next year.\n"
        "Net earnings includes:\n"
    )
    out = _clean_highlights_result(body)
    assert out.endswith("Net earnings includes:")


def test_clean_highlights_floor_kept() -> None:
    # Below the 200-char floor the trim is refused entirely: a wart
    # is better than dropping the row (the batch-153 floor rule).
    body = "Short Headline\n\n• One short bullet.\nRevenues\n"
    assert _clean_highlights_result(body) == body.strip()
