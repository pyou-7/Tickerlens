"""Batch 235: the fuser-extender — the 31 new-residue guidance rows
carried forward from batch 234 (stored rows whose live extraction still
carried an unfused split row or a footnote-definition opener).

Root causes, all in _clean_guidance_result / _clean_guidance_footnotes:
- The wrapped-label guard refused fusion whenever the previous line was
  label-shaped — including column headers ("Guidance5", "GAAP
  Non-GAAP(1)"), section sub-headings ("Top-Line and Cost Structure"),
  list headers ("Add / (Subtract):") and bare value words ("Unchanged").
  It now only refuses/j joins on a true wrapped fragment, and a marked
  prev line (GE's "Operating Profit*") refuses outright.
- The value-unit cap was 2 — three/four-column tables (DuPont
  prior/current/Q4, Digital Realty's As-of dates, GE 2025+2028) refused
  every row. The cap is now 4.
- Bristol Myers' "(Prior) <Month>" / "(Updated)" column headers and the
  "(Reported & Ex-FX)" sub-label line were never handled; "(Updated)"
  even opened a footnote block that ate the "2026 WW Revenue Growth*"
  row. They drop (with the bare month heading the group) and the
  sub-label joins the label.
- Delta's footnotes end on an unterminated line with prose resuming
  after them, so the drop condition never fired; Elevance's footnote
  keys sit on their own line ("1." / definition). The drop now fires
  when the prose after the block terminates within a few lines, and
  bare-number keys merge with their definition line first.
- A bare value word ("N/A") counted as a label and fused as one
  ("N/A: ~$0.43"); a parenthesized value line counted as a sub-label
  and joined the label. Both are now excluded.
- A lone closing-paren continuation (")%") merges onto its value
  ("(5.8" + ")%" — Elevance's wrapped "(5.8%)").

Blast-radius method: guidance old-vs-new over 1,699 cached exhibits
(scripts/batch235_guidance_blast.py, hidden_files/blast235_diff.txt):
103 exhibits changed, 0 gained/lost guidance, all verified line-by-line.
Figure multisets: 0 figures added anywhere; the only removals are
footnote keys (BMY "(Updated)4", Delta's 1/2/3, Elevance's 1/2/3).

Live pins run the extractor against the real cached exhibits; the unit
pins cover each new predicate and guard directly.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _carries_footnote_marker,
    _clean_guidance_footnotes,
    _clean_guidance_result,
    _is_guidance_header_line,
    _is_guidance_prior_updated_header,
    _is_guidance_sub_label_line,
    _is_guidance_table_label,
    _is_wrapped_label_fragment,
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


# --- live pins: the residue rows fuse, the furniture drops --------


def test_crm_two_range_value_line_fuses():
    g = _guidance("CRM_2024-10-31.html")
    assert "Total Revenue: $9.90 - $10.10 Billion $37.8 - $38.0 Billion" in g
    assert "GAAP operating margin(1): ~14.5%" in _guidance("CRM_2023-10-31.html")


def test_crm_single_range_value_line_fuses():
    assert "Revenue: $11.13 - $11.23 billion" in _guidance("CRM_2025-10-31.html")
    assert "Revenue: $11.03 - $11.08 billion" in _guidance("CRM_2026-01-31.html")


def test_dlr_three_column_rows_fuse():
    g = _guidance("DLR_2024-06-30.html")
    assert (
        "Total revenue: $5.550 - $5.650 billion / $5.550 - $5.650 billion / "
        "$5.550 - $5.650 billion" in g
    )
    assert (
        "Net non-cash rent adjustments (1): ($35 - $40 million) / "
        "($35 - $40 million) / ($35 - $40 million)" in g
    )
    assert (
        "G&A: $450 - $460 million / $450 - $460 million / $450 - $460 million"
        in g
    )
    assert "Cash basis: 4.0% - 6.0% / 5.0% - 7.0% / 5.0% - 7.0%" in g
    # A parenthesized value line never joins the label (batch-235 bug).
    assert not any(
        "Net non-cash rent adjustments (1) ($35" in ln for ln in g
    )


def test_dlr_fx_row_fuses_alone():
    g = _guidance("DLR_2024-12-31.html")
    assert "U.S. Dollar / Pound Sterling: $1.20 - $1.25" in g


def test_cci_site_rental_billings_fuses():
    g = _guidance("CCI_2024-09-30.html")
    assert "Site rental billings(c): $5,740 to $5,780 $0" in g
    assert "Amortization of prepaid rent: $392 to $417 $0" in g


def test_bmy_sub_label_and_headers():
    g = _guidance("BMY_2025-03-31.html")
    assert (
        "Total Revenues (Reported & Ex-FX): ~$45.5 billion ~$45.8 - $46.8 billion"
        in g
    )
    assert "(Prior) April" not in g
    assert "(Updated)" not in g
    assert "February" not in g


def test_bmy_ww_revenue_row_survives():
    # The "(Updated)" header opened a footnote block that ate this row.
    g = _guidance("BMY_2026-06-30.html")
    assert "Total Revenues (Reported & Ex-FX): ~$46.0 - $47.5 billion / ~$49.0 - $50.0 billion" in g
    assert "2026 WW Revenue Growth* 10% - 15% 20% - 25%" in g
    g2 = _guidance("BMY_2026-09-30.html")
    assert "2026 WW Revenue Growth* 20% - 25% No change" in g2


def test_bmy_reaffirmed_group_drops():
    # BMY 2026-03-31 pairs each bare month with its own marker line
    # ("February" / "(Prior)" / "April" / "(Reaffirmed)") — the whole
    # group drops, not just the "(Prior) <month>" form.
    g = _guidance("BMY_2026-03-31.html")
    assert "Total Revenues (Reported & Ex-FX): ~$46.0 - $47.5 billion" in g
    assert not any(
        ln.strip() in ("February", "April", "(Prior)", "(Reaffirmed)")
        for ln in g
    )
    assert "Diluted EPS: $6.05 - $6.35" in g


def test_dd_three_value_lines_fuse_and_na_stays_a_value():
    g = _guidance("DD_2025-09-30.html")
    assert "Net sales: ~$6,840 / ~$6,865 / ~$1,685" in g
    assert "Operating EBITDA(2): ~$1,600 / ~$1,575 / ~$385" in g
    assert "N/A: ~$0.43" not in g
    assert "N/A" in g


def test_fslr_unchange_prev_row_fuses():
    g = _guidance("FSLR_2025-03-31.html")
    assert "Operating Income (4): $1.95B to $2.30B / $1.45B to $2.00B" in g


def test_ge_four_column_row_fuses_and_fcf_rows_stay_separate():
    g = _guidance("GE_2025-06-30.html")
    assert (
        "Operating profit*: $7.8 - $8.2 billion / $8.2 - $8.5 billion / "
        "~$10 billion / ~$11.5 billion" in g
    )
    assert "Free cash flow*" in g
    assert "FCF* Conversion-b)" in g
    assert not any("Free cash flow* FCF*" in ln for ln in g)
    assert not any("Operating Profit* Operating profit margin*" in ln for ln in g)


def test_emr_wrapped_labels_join():
    g = _guidance("EMR_2024-09-30.html")
    assert "Underlying Sales Growth: 2% - 3% / 3% - 5%" in g
    assert "Restructuring / Related Costs: ~$0.04 / ~$0.16" in g
    assert "Adjusted Earnings Per Share: $1.25 - $1.30 / $5.85 - $6.05" in g
    # Batch 240: the four-word tail ("Fees and Related Costs") now
    # joins — the wrapped-label cap went from two words to four, so
    # the row fuses instead of staying split.
    assert (
        "Acquisition / Divestiture Fees and Related Costs: ~$0.01 / ~$0.04"
        in g
    )


def test_dal_footnotes_drop_before_prose():
    g = _guidance("DAL_2025-03-31.html")
    assert not any("1 Non-GAAP measures" in ln for ln in g)
    assert "Given current uncertainty, Delta is not reaffirming full year" in g
    g2 = _guidance("DAL_2025-12-31.html")
    assert not any("1Non-GAAP measures" in ln for ln in g2)
    assert not any("2Adjusted debt to EBITDAR" in ln for ln in g2)
    assert not any("3Introduced at November 2024 Investor Day" in ln for ln in g2)


def test_elv_bare_number_footnotes_drop():
    g = _guidance("ELV_2025-09-30.html")
    assert "assets 3: $2.98" in g
    assert "1." not in g
    assert not any("Adjustment item resides" in ln for ln in g)
    assert not any("Adjustment item represents" in ln for ln in g)


def test_elv_wrapped_percent_merges():
    g = _guidance("ELV_2023-12-31.html")
    assert "Employer Group Risk-Based: 3,756 / 3,988 / 3,754 / (5.8)%" in g
    assert ")%" not in g


def test_amt_sub_heading_stays_and_row_fuses_alone():
    g = _guidance("AMT_2024-03-31.html")
    assert "International pass-through revenue(5): N/A $ 1,617 N/A $ 1,617" in g
    assert "Total Property" in g
    assert not any("Total Property International" in ln for ln in g)


def test_visa_fx_row_fuses_and_low_teens_stays_put():
    g = _guidance("V_2023-09-30.html")
    assert "Foreign Currency Impact(3): ~1% / ~1.5% / ~0.5%" in g
    assert not any("Low-teens Foreign Currency" in ln for ln in g)
    assert "N/A: ~9%" not in g


def test_carr_current_guidance_header_stays_and_sales_fuses():
    g = _guidance("CARR_2024-09-30.html")
    assert "Sales: ~$22.5B" in g
    assert "Current Guidance**" in g
    assert not any("Current Guidance** Sales" in ln for ln in g)


def test_skyd_studios_row_fuses():
    g = _guidance("SKYD_2026-06-30.html")
    assert "Studios: 1,135 / 2,060 / 1,283 / 1,314" in g


# --- unit pins: the new predicates and guards ----------------------


def test_na_is_a_value_not_a_label():
    assert _is_guidance_table_label("N/A") is False
    assert _is_guidance_table_label("G&A") is True
    assert _is_guidance_table_label("Add / (Subtract):") is False


def test_header_tokens_with_glued_keys():
    assert _is_guidance_header_line("Guidance5") is True
    assert _is_guidance_header_line("GAAP Non-GAAP(1)") is True
    assert _is_guidance_header_line("Current Guidance**") is True
    assert _is_guidance_header_line("Revenue") is False


def test_prior_updated_header_shapes():
    assert _is_guidance_prior_updated_header("(Prior) April") is True
    assert _is_guidance_prior_updated_header("(Updated)") is True
    assert _is_guidance_prior_updated_header("(Updated)4") is True
    assert _is_guidance_prior_updated_header("(Reported & Ex-FX)") is False


def test_sub_label_line_shapes():
    assert _is_guidance_sub_label_line("(Reported & Ex-FX)") is True
    assert _is_guidance_sub_label_line("($35 - $40 million)") is False
    assert _is_guidance_sub_label_line("(2)") is False
    assert _is_guidance_sub_label_line("(Prior)") is False


def test_footnote_marker_shapes():
    assert _carries_footnote_marker("Operating Profit*") is True
    assert _carries_footnote_marker("Underlying Sales") is False
    assert _carries_footnote_marker("assets 3") is True
    assert _carries_footnote_marker("Litigation and settlement expenses1") is True
    assert _carries_footnote_marker("Total Property") is False


def test_wrapped_fragment_narrowness():
    assert _is_wrapped_label_fragment("Underlying Sales", "Growth") is True
    assert _is_wrapped_label_fragment("Adjusted Earnings", "Per Share") is True
    assert (
        _is_wrapped_label_fragment(
            "Total Property", "International pass-through revenue(5)"
        )
        is False
    )
    assert (
        _is_wrapped_label_fragment("Free cash flow*", "FCF* Conversion-b)")
        is False
    )
    # Batch 240: the four-word continuation now joins — the cap went
    # from two words to four (a wrap point is arbitrary).
    assert (
        _is_wrapped_label_fragment(
            "Acquisition / Divestiture", "Fees and Related Costs"
        )
        is True
    )
    assert (
        _is_wrapped_label_fragment(
            "Top-Line and Cost Structure", "Total revenue"
        )
        is False
    )
    assert _is_wrapped_label_fragment("Current Guidance**", "Sales") is False
    assert (
        _is_wrapped_label_fragment("Unchanged", "Operating Income (4)")
        is False
    )
    assert (
        _is_wrapped_label_fragment(
            "Foreign Exchange Rates", "U.S. Dollar / Pound Sterling"
        )
        is False
    )


def test_three_and_four_value_units_fuse_five_refuses():
    assert _clean_guidance_result(
        ["H", "Net sales", "~$6,840", "~$6,865", "~$1,685"]
    ) == ["H", "Net sales: ~$6,840 / ~$6,865 / ~$1,685"]
    assert _clean_guidance_result(
        ["H", "Operating profit*", "$7.8", "$8.2", "~$10", "~$11.5"]
    ) == ["H", "Operating profit*: $7.8 / $8.2 / ~$10 / ~$11.5"]
    out = _clean_guidance_result(
        ["H", "Net sales", "$1", "$2", "$3", "$4", "$5"]
    )
    assert out[1] == "Net sales"
    assert out[2] == "$1"


def test_wrapped_label_joins_in_clean():
    assert _clean_guidance_result(
        ["H", "Underlying Sales", "Growth", "2%", "- 3%", "3%", "- 5%"]
    ) == ["H", "Underlying Sales Growth: 2% - 3% / 3% - 5%"]


def test_sub_label_and_prior_updated_drop_in_clean():
    assert _clean_guidance_result(
        [
            "H",
            "Non-GAAP2,3",
            "February",
            "(Prior) April",
            "(Updated)",
            "Total Revenues",
            "(Reported & Ex-FX)",
            "~$45.5 billion",
        ]
    ) == [
        "H",
        "Non-GAAP2,3",
        "Total Revenues (Reported & Ex-FX): ~$45.5 billion",
    ]


def test_paren_continuation_merges_onto_value():
    assert _clean_guidance_result(
        ["H", "Employer Group Risk-Based", "3,756", "(5.8", ")%"]
    ) == ["H", "Employer Group Risk-Based: 3,756 / (5.8)%"]


def test_marked_prev_row_label_refuses_fusion():
    out = _clean_guidance_result(
        ["H", "Free cash flow*", "FCF* Conversion-b)", "$6.3 - $6.8 billion", ">100%"]
    )
    assert "Free cash flow*" in out
    assert "FCF* Conversion-b)" in out
    assert "$6.3 - $6.8 billion" in out
    assert not any("FCF* Conversion-b):" in ln for ln in out)


def test_na_value_line_stays_put_in_clean():
    out = _clean_guidance_result(
        ["H", "Adjusted EPS(2): ~$1.66", "N/A", "~$0.43"]
    )
    assert "N/A: ~$0.43" not in out
    assert "N/A" in out


def test_sub_heading_plus_complete_row_does_not_join():
    out = _clean_guidance_result(
        ["H", "Total Property", "International pass-through revenue(5)", "N/A $ 1,610 N/A $ 1,610"]
    )
    assert "International pass-through revenue(5): N/A $ 1,610 N/A $ 1,610" in out
    assert "Total Property" in out
    assert not any("Total Property International" in ln for ln in out)


def test_footnote_drops_before_wrapped_prose():
    out = _clean_guidance_footnotes(
        [
            "Total Revenue YoY: Down 2% - up 2%",
            "1 Non-GAAP measures; Refer to Non-GAAP reconciliations for historical comparison figures",
            "Given current uncertainty, Delta is not reaffirming full year",
            "2025 financial guidance and will provide an update later in the year as visibility improves.",
        ]
    )
    assert out == [
        "Total Revenue YoY: Down 2% - up 2%",
        "Given current uncertainty, Delta is not reaffirming full year",
        "2025 financial guidance and will provide an update later in the year as visibility improves.",
    ]


def test_bare_number_footnote_keys_merge_and_drop():
    out = _clean_guidance_footnotes(
        [
            "$5.30",
            "1.",
            "Adjustment item resides in the Corporate & Other reportable segment.",
            "2.",
            "Adjustment item resides in the Health Benefits and Carelon Services reportable segments.",
        ]
    )
    assert out == ["$5.30"]


def test_prior_updated_header_never_opens_footnote_block():
    lines = [
        "2026 Eliquis Revenue Guidance",
        "April",
        "(Prior) July",
        "(Updated)",
        "2026 WW Revenue Growth* 10% - 15% 20% - 25%",
        "* Compared to 2025 Worldwide Eliquis revenues.",
    ]
    out = _clean_guidance_footnotes(lines)
    assert "2026 WW Revenue Growth* 10% - 15% 20% - 25%" in out
