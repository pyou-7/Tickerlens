"""Batch 205: a results-boundary detector in the guidance main loop.

Batch 204 carry-forward: DELL x7, ECL x4 and DASH 2026-09-30 guidance
sections bleed into the reported results table — the bleed starts inside
the 30-line budget, so the batch-204 lookahead only deepens it. The fix
has two parts. (1) Generalize _GUIDANCE_RESULTS_PERIOD_RE: the old shape
only matched the dated lowercase form ("Three months ended January 31"),
so it missed the dateless/combined form ("Three Months Ended Fiscal Year
Ended" — DELL; "Three Months Ended Y/Y % Change Q/Q % Change" — DASH),
the quarter form ("First Quarter Ended March 31" — ECL) and the standalone
fiscal-year form. A forward guidance period says "Ending", never "Ended",
so the past tense is the discriminator — and as a follower it only fires
after a heading candidate, which is how DELL/DASH now break at their
results headings ("Fourth Quarter ... Financial Results", "Q3 2026
Financial Performance"). (2) A direct break in the main loop on the period
header itself: ECL's two outlook bullets run straight into its results
table with no heading line at all. The break needs guidance signal already
delivered (a guidance table's own period header sits before any signal —
AKAM's "Three Months Ended" intro) and a results-table confirmation ahead
(_is_results_table_ahead: a unit line, a "Change"/"Reported"/"Adjusted"
column label, or Y/Y-Q/Q change columns; a "Low End High End" range label
anywhere in the window refuses — AKAM's guidance-range table). Without the
confirmation a guidance table that happens to head its columns with
"Ended" would be cut.

Blast (blast205/g_new vs blast204/g_new, 1,699 exhibits): 22 diffs, 0
None-flips. 21 pure tail cuts — DELL x7, ECL x10, DASH x4 — removing
results-table leakage (DELL 2025-01-31: 44 -> 5 lines, 3996 -> 538 chars;
ECL 2025-03-31: 50 -> 3 lines; DASH 2026-09-30: 38 -> 10 lines). One
genuine completion: GE 2025-06-30 (30 -> 38 lines) — the new break gives
the batch-204 lookahead its section-end signal, so the rest of GE's
guidance table ($6.5-$6.9B, ~$8.5B FCF, footnotes (a)/(b)) is kept instead
of truncating mid-table. AKAM x2 unchanged: its guidance-range tables are
preserved by both guards.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _GUIDANCE_RESULTS_PERIOD_RE,
    extract_management_guidance,
)


def _results_table_ahead(lines: list[str], j: int) -> bool:
    # Local import: the helper is new in batch 205, so a module-level
    # import would break collection on stashed old code during the
    # behavioral pin check.
    from tickerlens.data.filings import _is_results_table_ahead

    return _is_results_table_ahead(lines, j)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _guidance(name: str) -> str:
    g = extract_management_guidance(_load(name))
    assert g is not None
    return g


def _synthetic_doc(lines: list[str]) -> str:
    return "<html><body>" + "".join(f"<p>{ln}</p>" for ln in lines) + "</body></html>"


# --- Real exhibits: the bleed cohort is cut, the guidance kept --------


def test_dell_2025_01_31_ends_at_guidance_bullets():
    g = _guidance("DELL_2025-01-31.html")
    assert "$101.0 billion" in g
    assert "$9.30" in g
    assert "Fourth Quarter and Full-Year Fiscal 2025 Financial Results" not in g
    assert "Three Months Ended" not in g
    assert "Net revenue $ 23,931" not in g
    assert "Revised Consolidated Financial Statements" not in g
    assert len(g.split("\n\n")) == 5


def test_ecl_2025_03_31_ends_at_outlook_bullets():
    g = _guidance("ECL_2025-03-31.html")
    assert "$7.42 to $7.62" in g
    assert "$1.84 to $1.94" in g
    assert "First Quarter Ended March 31" not in g
    assert "Net sales" not in g
    assert "Public Currency Rates" not in g
    assert len(g.split("\n\n")) == 3


def test_dash_2026_09_30_ends_before_financial_performance():
    g = _guidance("DASH_2026-09-30.html")
    assert "$35.4 billion" in g
    assert "Q3 2026 Financial Performance" not in g
    assert "Three Months Ended" not in g
    assert "Revenue $ 3,446" not in g
    assert "Total Orders in Q3 2026" not in g


def test_akam_2024_03_31_guidance_table_unchanged():
    # AKAM's guidance table is itself headed "Three Months Ended" — both
    # guards must hold it: no signal precedes the header, and the range
    # labels refuse the confirmation.
    g = _guidance("AKAM_2024-03-31.html")
    assert "Three Months Ended" in g
    assert "Low End High End" in g
    assert "$ 967" in g
    assert "$ 1.51" in g


def test_ge_2025_06_30_lookahead_completes_guidance_table():
    # The new break fires at GE's results-table header just past the
    # 30-line budget, so the lookahead now verifies and keeps the rest of
    # the guidance table instead of truncating mid-table at ">100%".
    g = _guidance("GE_2025-06-30.html")
    assert "$6.5 - $6.9 billion" in g
    assert "~$8.5 billion" in g
    assert "Non-GAAP Financial Measure" in g
    assert "Three Months Ended" not in g


# --- The period-header regex --------------------------------------------


def test_results_period_regex_matches_bleed_shapes():
    for ln in (
        "Three Months Ended",
        "Three Months Ended Fiscal Year Ended",
        "Three Months Ended Y/Y % Change Q/Q % Change",
        "Three Months Ended January 31, 2025",
        "First Quarter Ended March 31",
        "Fourth Quarter Ended December 31",
        "Nine Months Ended September 30",
        "Fiscal Year Ended December 31",
    ):
        assert _GUIDANCE_RESULTS_PERIOD_RE.match(ln), ln


def test_results_period_regex_rejects_guidance_periods():
    for ln in (
        "Three Months Ending June 30, 2026",
        "First Quarter Ending March 31, 2026",
        "Fiscal Year Ending December 31, 2026",
        "Q3 FY2025",
        "Full Year Fiscal 2026",
    ):
        assert not _GUIDANCE_RESULTS_PERIOD_RE.match(ln), ln


# --- The results-table confirmation -------------------------------------


def test_results_table_ahead_unit_line_confirms():
    lines = [
        "Three Months Ended",
        "January 31, 2025 February 2, 2024 Change",
        "(in millions, except per share amounts and percentages; unaudited)",
        "Net revenue $ 23,931 $ 22,318 7%",
    ]
    assert _results_table_ahead(lines, 0)


def test_results_table_ahead_column_labels_confirm():
    lines = [
        "First Quarter Ended March 31",
        "Reported",
        "Adjusted",
        "(unaudited)",
        "Net sales",
    ]
    assert _results_table_ahead(lines, 0)


def test_results_table_ahead_change_columns_in_header_confirm():
    lines = [
        "Three Months Ended Y/Y % Change Q/Q % Change",
        "(in millions, except percentages) Sept. 30,",
        "Revenue $ 3,446 $ 3,955",
    ]
    assert _results_table_ahead(lines, 0)


def test_results_table_ahead_range_labels_refuse():
    # AKAM's guidance-range table: the range labels sit in the header
    # block ahead of the rows.
    lines = [
        "Three Months Ended",
        "June 30, 2024 Year Ended",
        "Low End High End Low End High End",
        "Revenue (in millions) $ 967 $ 986 $ 3,950 $ 4,020",
    ]
    assert not _results_table_ahead(lines, 0)


def test_results_table_ahead_range_label_after_unit_line_still_refuses():
    # Two passes: a unit line must not outvote a range label later in the
    # window — a guidance table that prints a unit line first is still a
    # guidance table.
    lines = [
        "Three Months Ended",
        "(in millions)",
        "Low End High End",
        "Revenue $ 100 $ 110",
    ]
    assert not _results_table_ahead(lines, 0)


def test_results_table_ahead_no_confirmation_refuses():
    lines = [
        "Three Months Ended",
        "June 30, 2024 Year Ended",
        "Revenue $ 100 $ 110",
    ]
    assert not _results_table_ahead(lines, 0)


# --- Synthetic docs: the direct break and its guards --------------------


def test_synthetic_period_header_breaks_after_signaled_guidance():
    doc = _synthetic_doc(
        [
            "Financial Outlook",
            "• Full-year revenue expected between $101.0 billion and $105.0 billion, up 8% year over year.",
            "Three Months Ended",
            "January 31, 2025 February 2, 2024 Change",
            "(in millions, except per share amounts and percentages; unaudited)",
            "Net revenue $ 23,931 $ 22,318 7%",
        ]
    )
    g = extract_management_guidance(doc)
    assert g is not None
    assert "$101.0 billion" in g
    assert "Three Months Ended" not in g
    assert "Net revenue" not in g


def test_synthetic_results_heading_breaks_via_period_follower():
    # DELL shape: the results heading itself is the break — the follower
    # (the period header) now matches the generalized regex.
    doc = _synthetic_doc(
        [
            "Guidance Summary",
            "• Full-year FY26 revenue expected between $101.0 billion and $105.0 billion, up 8% year over year.",
            "Fourth Quarter and Full-Year Fiscal 2025 Financial Results",
            "Three Months Ended Fiscal Year Ended",
            "January 31, 2025 February 2, 2024 Change",
            "(in millions, except per share amounts and percentages; unaudited)",
            "Net revenue $ 23,931 $ 22,318 7%",
        ]
    )
    g = extract_management_guidance(doc)
    assert g is not None
    assert "$101.0 billion" in g
    assert "Financial Results" not in g
    assert "Three Months Ended" not in g


def test_synthetic_range_table_survives_after_signal():
    # A guidance-range table headed "Three Months Ended" after signaled
    # prose: the range labels refuse the confirmation, so the table is kept.
    doc = _synthetic_doc(
        [
            "Financial Outlook",
            "• We expect full-year revenue of about $4.0 billion, up 8% year over year.",
            "Three Months Ended",
            "June 30, 2024 Year Ended",
            "Low End High End Low End High End",
            "Revenue (in millions) $ 967 $ 986 $ 3,950 $ 4,020",
        ]
    )
    g = extract_management_guidance(doc)
    assert g is not None
    assert "Three Months Ended" in g
    assert "$ 967" in g


def test_synthetic_period_header_before_signal_does_not_break():
    # The has-signal guard: a period header before any guidance signal is
    # not a section end (the section has not delivered yet).
    doc = _synthetic_doc(
        [
            "Financial Outlook",
            "The Company provides the following outlook for the coming year, including revenue and earnings targets for the fourth quarter and the full year ahead.",
            "Three Months Ended",
            "June 30, 2024 Year Ended",
            "(in millions)",
            "Revenue $ 100 $ 110",
        ]
    )
    g = extract_management_guidance(doc)
    assert g is not None
    assert "Three Months Ended" in g
