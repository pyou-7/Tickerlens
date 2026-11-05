"""Batch 192: "#" and spaced-"*" footnote definitions are never highlights.

Air Products keys its per-share footnote "#" and its non-GAAP legend "*":
its Q2 FY2026 release serves both definitions as section content — "# Per
share amounts are calculated and presented on a diluted basis from
continuing operations attributable to Air Products." and "* Certain
results in this release include references to non-GAAP financial measures
..." — because no footnote predicate covers them: _FOOTNOTE_DEF_RE matches
only attached "*"/"†"/"‡" glyphs, and _ASTERISK_NOTE_LEAD_RE never listed
the "Certain results" opener. The fix adds a "#" shape (attached or
spaced — "#" never opens a bullet or prose in these exhibits) to
_FOOTNOTE_DEF_RE and "Certain results" to _ASTERISK_NOTE_LEAD_RE, so the
shared _footnote_def_block_len / _asterisk_note_block_len machinery drops
them on every collection path. The same change drops American Express's
"# - Denotes a variance of 100 percent or more." legend (FY2023) and the
attached APD forms ("#Earnings ...", "*Certain results ...").
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _asterisk_note_block_len,
    _footnote_def_block_len,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _live(ticker_period: str) -> str:
    html = open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ).read()
    out = extract_press_release_highlights(html)
    assert out is not None, f"{ticker_period} extracted None"
    return out


# --- unit: the "#" footnote-definition shapes ---------------------------

HASH_LINES = [
    # APD Q2 FY2026, spaced form (the carried item's stored line).
    "# Per share amounts are calculated and presented on a diluted basis "
    "from continuing operations attributable to Air Products.",
    # APD Q1 FY2025, attached form.
    "#Earnings per share is calculated and presented on a diluted basis "
    "from continuing operations attributable to Air Products.",
    # APD Q3 FY2025, attached form.
    "#Per share amounts are calculated and presented on a diluted basis "
    "from continuing operations attributable to Air Products.",
    # AXP FY2023, spaced legend form.
    "# - Denotes a variance of 100 percent or more.",
]


def test_hash_footnote_def_block_len():
    for ln in HASH_LINES:
        assert _footnote_def_block_len([ln], 0) == 1, ln


def test_hash_separator_opens_a_block_of_one():
    # A bare "###" page separator opens a footnote-def block (the "#"
    # shape matches it) but consumes nothing after it: the following
    # headline is not a plausible wrap continuation.
    lines = ["###", "Air Products Reports Fiscal 2026 Second Quarter Results"]
    assert _footnote_def_block_len(lines, 0) == 1


# --- unit: the "Certain results" asterisk-note opener -------------------

CERTAIN_LINES = [
    # APD Q2 FY2026, spaced form.
    "* Certain results in this release include references to non-GAAP "
    "financial measures on a consolidated, continuing operations basis.",
    # APD Q1 FY2025, attached form.
    "*Certain results in this release, including in the highlights above, "
    "include references to non-GAAP financial measures.",
]


def test_certain_results_asterisk_note_block_len():
    for ln in CERTAIN_LINES:
        assert _asterisk_note_block_len([ln], 0) == 1, ln


def test_revenue_bullet_stays_a_bullet():
    # Batch 165's pin, still: a "*" bullet that opens with a result verb
    # is content, not a note — the lead list stays note-shaped.
    assert _asterisk_note_block_len(["* Revenue grew 12 percent."], 0) == 0


# --- real exhibits: the footnote lines are gone, the content stays -----

def test_apd_q2_fy2026_no_footnote_defs():
    out = _live("APD_2026-03-31")
    assert "# Per share amounts" not in out
    assert "* Certain results in this release" not in out
    assert "non-GAAP financial measures on a consolidated" not in out
    # The section's real content survives: bullets, heading, lede, quote.
    assert "Selected by Samsung" in out
    assert "Fiscal 2026 Second Quarter Consolidated Results" in out
    assert "LEHIGH VALLEY, Pa. (April 30, 2026)" in out
    assert "Despite macroeconomic volatility" in out


def test_apd_q3_fy2025_no_hash_footnote_def():
    out = _live("APD_2025-06-30")
    assert "#Per share amounts" not in out
    assert "GAAP earnings per share" in out
    assert "Adjusted EPS* of $3.09" in out


def test_axp_fy2023_no_hash_legend():
    # The "# - Denotes a variance of 100 percent or more." legend sits
    # between AXP's sub-headlines and its dateline paragraph in the lede.
    out = _live("AXP_2023-12-31")
    assert "# - Denotes a variance" not in out
    assert "FULL-YEAR EARNINGS PER SHARE INCREASED 14% TO $11.21" in out
    assert "New York – January 26, 2024" in out
