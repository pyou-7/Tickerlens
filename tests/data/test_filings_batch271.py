"""Batch 271 regression tests.

The batch-270 carry-forward, fixed here: the leading-bullet block's
"Other Highlights" wart (Visa Q4 FY2025 served only its 4 figure
bullets) needed both a narrowed heading continuation and a
table-title stop.

- Heading continuation: a short colon-ended standalone sub-heading
  ("Other Highlights:") that introduces a bullet list is a label
  line inside the leading block, not a competing section — the
  block keeps collecting when bullets are already in hand and the
  next content line is a bullet. The gates are the whole point:
  a bare heading ("Recent Highlights" — Air Products, no colon)
  still breaks, and a bullet line carrying a glued heading label
  (Booking's "• Revenue grew ... Full Year 2024 Highlights")
  never reaches the branch as a heading. The batch-270 naive form
  (continue past ANY heading followed by bullets) flipped APD x3
  and BKNG x1 — both are pinned unchanged here.
- Table-title stop: a financial-statement table title ("Income
  Statement Summary", "Condensed Consolidated Statements of
  Operations", "Key Business Drivers") ends the block — the
  flattened statement behind it is table residue, not a bullet
  continuation. The next-is-bullet guard is the batch-195 shape:
  a title that introduces bullets ("KEY DRIVERS" + its bullet
  list, 48 occurrences in the cache) is a sub-heading, not a
  table, so the break fires only when a table follows.

Blast radius of the pair: exactly 1 row moves in the 1,699-exhibit
cache — V_2025-09-30, 420 -> 732 chars (the 3 stranded narrative
bullets join the 4 figure bullets; no table residue).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_financial_table_title,
    _leading_bullet_block,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# --- _is_financial_table_title -------------------------------------------

_TABLE_TITLES = (
    "Income Statement Summary",
    "Condensed Consolidated Statements of Operations",
    "Consolidated Statements of Cash Flows",
    "CONDENSED CONSOLIDATED BALANCE SHEETS",
    "Condensed Consolidated Balance Sheets (Unaudited)",
    "CONDENSED CONSOLIDATING BALANCE SHEETS – ASSETS",
    "Key Business Drivers",
    "KEY DRIVERS",
    "Results Summary",
    "FINANCIAL SUMMARY",
    "Balance Sheet",
    "Consolidated Cash Flow Statement",
    "Supplemental Data for Results of Operations",
    "Income Statement Classification",
    "Free Cash Flow",
    "GAAP Consolidated Statements of Operations and",
)

_NOT_TABLE_TITLES = (
    # Table row labels: lowercase non-connector words / no keyword.
    "Income from operations",
    "Free cash flow",
    "Accumulated other comprehensive loss",
    "Cash provided by operations",
    "Net Revenue",
    "GAAP Net Income",
    "Discontinued operations",
    "Cash flow from operating activities:",
    # Too short / too long / terminated prose.
    "Summary",
    "OPERATIONS",
    "Cash flow from operating activities for the quarter was strong.",
    "Consolidated Statements of Operations for the Three Months Ended",
    # Bullets are never titles.
    "• Income Statement Summary",
    # Figure-carrying lines are never titles.
    "Income Statement Summary $10.7B",
    "Balance Sheet 12%",
)


def test_is_financial_table_title_positives():
    for ln in _TABLE_TITLES:
        assert _is_financial_table_title(ln), ln


def test_is_financial_table_title_negatives():
    for ln in _NOT_TABLE_TITLES:
        assert not _is_financial_table_title(ln), ln


# --- Narrowed heading continuation (synthetic) ---------------------------

def test_heading_continuation_colon_subheading_keeps_bullets():
    lines = [
        "• GAAP net income of $5.1B or $2.62 per share and non-GAAP net income of $5.8B or $2.98 per share",
        "• Net revenue of $10.7B, an increase of 12%, or 11% on a constant-dollar basis",
        "Other Highlights:",
        "• Fiscal fourth quarter growth in payments volume, cross-border volume and processed transactions remained strong",
        "• Share repurchases and dividends of $6.1B and $22.8B for fiscal fourth quarter and full-year, respectively",
        "Income Statement Summary",
        "In billions, except percentages and per share data.",
    ]
    block = _leading_bullet_block(lines)
    assert block is not None
    assert block == [
        "• GAAP net income of $5.1B or $2.62 per share and non-GAAP net income of $5.8B or $2.98 per share",
        "• Net revenue of $10.7B, an increase of 12%, or 11% on a constant-dollar basis",
        "Other Highlights:",
        "• Fiscal fourth quarter growth in payments volume, cross-border volume and processed transactions remained strong",
        "• Share repurchases and dividends of $6.1B and $22.8B for fiscal fourth quarter and full-year, respectively",
    ]


def test_heading_continuation_bare_heading_still_breaks():
    # Air Products: "Recent Highlights" has no colon, so the block
    # ends at the heading and the narrative bullets stay out.
    lines = [
        "• GAAP EPS# of $2.73, up six percent; GAAP net income of $622 million, up six percent; and GAAP net income margin of 20.7 percent",
        "• Adjusted EPS* of $2.82, up seven percent; adjusted EBITDA* of $1.2 billion, up eight percent; and adjusted EBITDA margin* of 39.5 percent",
        "Recent Highlights",
        "• Increased quarterly dividend to $1.77 per share in January, the 42nd consecutive year of increases",
    ]
    block = _leading_bullet_block(lines)
    assert block is not None
    assert len(block) == 2
    assert "Increased quarterly dividend" not in "\n".join(block)


def test_heading_continuation_glued_heading_in_bullet_breaks():
    # Booking: the heading label is glued to the end of a bullet
    # line, so the line is a bullet, not a standalone heading —
    # the block still breaks there (the batch-270 BKNG flip).
    lines = [
        "• Room nights grew 13% compared to 2023, or 14% on a constant-currency basis, with gross bookings up sharply",
        "• Gross bookings grew 17% compared to 2023, or 18% on a constant-currency basis, driven by travel demand",
        "• Revenue grew 14% compared to 2023. Full Year 2024 Highlights",
        "• Room nights grew 9% compared to 2023.",
    ]
    block = _leading_bullet_block(lines)
    assert block is not None
    assert len(block) == 2
    assert "Room nights grew 9%" not in "\n".join(block)


def test_heading_continuation_needs_bullets_first():
    # A colon highlights heading ahead of any bullet is a section
    # heading, not a mid-block label — the block never starts.
    lines = [
        "First Quarter 2024 Highlights:",
        "• GAAP net income of $5.1B or $2.62 per share and non-GAAP net income of $5.8B or $2.98 per share",
        "• Net revenue of $10.7B, an increase of 12%, or 11% on a constant-dollar basis",
    ]
    assert _leading_bullet_block(lines) is None


def test_heading_continuation_needs_bullets_after():
    # A colon sub-heading followed by prose/table (not bullets) is
    # still a break — the continuation only fires for a bullet list.
    # (The single bullet is long so the block clears the 150-char
    # floor on its own.)
    lines = [
        "• GAAP net income of $5.1B or $2.62 per share and non-GAAP net income of $5.8B or $2.98 per share, with net revenue of $10.7B, an increase of 12%, or 11% on a constant-dollar basis",
        "Other Highlights:",
        "In billions, except percentages and per share data.",
        "• Fiscal fourth quarter growth remained strong",
    ]
    block = _leading_bullet_block(lines)
    assert block is not None
    assert len(block) == 1


def test_table_title_stop_ends_block_before_table():
    # Without the stop, the title + units line + table rows ride
    # the block as continuations to the cap (the batch-270 V run).
    lines = [
        "• GAAP net income of $5.1B or $2.62 per share and non-GAAP net income of $5.8B or $2.98 per share",
        "• Net revenue of $10.7B, an increase of 12%, or 11% on a constant-dollar basis",
        "Income Statement Summary",
        "In billions, except percentages and per share data.",
        "Net Revenue",
        "$10.7 12%",
    ]
    block = _leading_bullet_block(lines)
    assert block is not None
    assert len(block) == 2
    assert "Income Statement Summary" not in "\n".join(block)


def test_table_title_followed_by_bullets_is_subheading():
    # The batch-195 guard: a title that introduces bullets
    # ("KEY DRIVERS" + its list) is a sub-heading, not a table.
    lines = [
        "• GAAP net income of $5.1B or $2.62 per share and non-GAAP net income of $5.8B or $2.98 per share",
        "KEY DRIVERS",
        "• Volume growth of 9% drove revenue higher across every segment and region in the quarter",
        "• Pricing actions added 2 points of margin while volumes held steady year over year",
    ]
    block = _leading_bullet_block(lines)
    assert block is not None
    assert len(block) == 4
    assert block[1] == "KEY DRIVERS"


# --- Batch-270 naive-fix regressions, pinned unchanged --------------------

def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        html = fh.read()
    return extract_press_release_highlights(html) or ""


def test_apd_recent_highlights_unchanged():
    # The naive fix grew APD's leading block past "Recent
    # Highlights" and flipped the competition; the narrowed rule
    # leaves the bare heading alone, so the served shape is the
    # pre-batch-271 one: narrative + guidance bullets, no figure
    # bullets from the leading block.
    live = _live("APD_2023-12-31")
    assert "Increased quarterly dividend to $1.77 per share" in live
    assert "Updated fiscal 2024 full-year adjusted EPS guidance" in live
    assert "GAAP EPS# of $2.73" not in live
    assert "Adjusted EPS* of $2.82" not in live


def test_bkng_glued_heading_unchanged():
    # The naive fix let BKNG's block run past the bullet line
    # ending in the glued "Full Year 2024 Highlights" label; the
    # narrowed rule never treats a bullet line as a heading, so
    # the served shape is the pre-batch-271 one: the full-year
    # bullets, not the Q4 bullets.
    live = _live("BKNG_2024-12-31")
    assert "Room nights grew 9% compared to 2023." in live
    assert "Gross bookings grew 10% compared to 2023" in live
    assert "Room nights grew 13% compared to 2023." not in live
    assert "Gross bookings grew 17% compared to 2023" not in live
