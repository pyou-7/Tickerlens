"""Batch 228: the dated-dateline swallow in the leading-bullet block —
a dateline sentence after the leading bullets was collected as a bullet
continuation, dragging the flattened earnings table behind it into the
highlights (Centene: the "ST. LOUIS, October 25, 2024 -- ..." dateline
paragraph plus 7 table rows served in all 8 quarters).

The fix lives in _leading_bullet_block only: a new dated-dateline
predicate (_DATED_DATELINE_LEAD_RE — city + spelled-out month/day/year
+ dash, the form _DATELINE_LEAD_RE never matches because its location
segments allow no digits) breaks the block when a continuation line is
a dated dateline sentence, and the same form joins the pre-bullet
dateline skip so a dated dateline ahead of the bullets no longer breaks
the block either. Data rows and labels still stay out of the break
shapes, so a figure-dense bullet continuation is never cut.

Live pins run the extractor against the real cached exhibits; the unit
pins cover the new predicate and its guards directly.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _DATED_DATELINE_LEAD_RE,
    _leading_bullet_block,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


# --- unit pins: the dated-dateline predicate --------------------------


def test_dated_dateline_full_month_matches() -> None:
    assert _DATED_DATELINE_LEAD_RE.match(
        "ST. LOUIS, October 25, 2024 -- Centene Corporation (NYSE: CNC)"
        ' ("the Company") announced today its financial results'
    )
    assert _DATED_DATELINE_LEAD_RE.match(
        "ST. LOUIS, February 4, 2025 -- Centene Corporation announced"
    )


def test_dated_dateline_abbreviated_month_matches() -> None:
    assert _DATED_DATELINE_LEAD_RE.match(
        "NEW YORK, Oct. 15, 2025 -- Company reported third quarter results"
    )
    assert _DATED_DATELINE_LEAD_RE.match(
        "OMAHA, Sept. 30, 2025 - Company announced results"
    )


def test_dated_dateline_needs_city_and_dash() -> None:
    # No city: a bare date line is not a dateline sentence.
    assert not _DATED_DATELINE_LEAD_RE.match(
        "October 25, 2024 -- Centene Corporation announced results"
    )
    # No dash: a city + date without the dash is a header, not a lead.
    assert not _DATED_DATELINE_LEAD_RE.match(
        "ST. LOUIS, October 25, 2024 Centene Corporation announced"
    )
    # No date: the undated form belongs to _DATELINE_LEAD_RE, not this one.
    assert not _DATED_DATELINE_LEAD_RE.match(
        "ST. LOUIS, Missouri -- Centene Corporation announced results"
    )


def test_dated_dateline_never_matches_prose_or_bullets() -> None:
    assert not _DATED_DATELINE_LEAD_RE.match(
        "• Membership increases of 22% in Marketplace and 49% in Medicare"
    )
    assert not _DATED_DATELINE_LEAD_RE.match(
        "Continued execution on capital deployment with $1.2 billion of"
    )
    assert not _DATED_DATELINE_LEAD_RE.match(
        "Q4 2024 -- strong results across the board"
    )
    assert not _DATED_DATELINE_LEAD_RE.match(
        "In October 2025, the Company repurchased shares"
    )


# --- unit pins: the block breaks at the dateline, keeps the bullets ---


def test_leading_block_breaks_at_dated_dateline() -> None:
    lines = [
        "-- Diluted EPS of $1.36; Adjusted Diluted EPS of $1.62 --",
        "• Adjusted diluted EPS of $1.62 in the third quarter of 2024.",
        "• Premium and service revenues of $36.9 billion.",
        "ST. LOUIS, October 25, 2024 -- Centene Corporation announced"
        " today its financial results for the third quarter.",
        "Total revenues (in millions) $ 42,023",
        "Premium and service revenues (in millions) $ 36,899",
    ]
    block = _leading_bullet_block(lines)
    assert block is not None
    assert len(block) == 3
    assert "Total revenues" not in "\n".join(block)
    assert "ST. LOUIS" not in "\n".join(block)


def test_leading_block_skips_dated_dateline_before_bullets() -> None:
    lines = [
        "ST. LOUIS, July 25, 2025 -- Centene Corporation (NYSE: CNC)"
        " announced today its financial results.",
        "• Adjusted diluted EPS of $0.50 in the third quarter of 2025,"
        " including a $0.10 benefit of a low adjusted effective tax rate.",
        "• Premium and service revenues of $44.9 billion in the quarter,"
        " up 12% from $40.1 billion in the prior year period.",
    ]
    block = _leading_bullet_block(lines)
    assert block is not None
    assert len(block) == 2
    assert "ST. LOUIS" not in "\n".join(block)


def test_leading_block_keeps_figure_dense_bullet_continuation() -> None:
    # The dateline break must not swallow an ordinary figure-dense
    # wrapped bullet: a continuation that is not a dateline still joins.
    lines = [
        "• Net income was $2.32 billion, up 13.8%, and core operating",
        "income was $2.33 billion, up 14.3% for the quarter.",
        "• Adjusted EPS of $1.62 in the third quarter of 2024.",
    ]
    block = _leading_bullet_block(lines)
    assert block is not None
    assert "income was $2.33 billion" in "\n".join(block)


# --- live pins: Centene's table is gone, the content stays ------------


def test_cnc_2024_q3_table_gone() -> None:
    hl = extract_press_release_highlights(_read("CNC_2024-09-30.html"))
    assert hl is not None
    assert "Total revenues (in millions)" not in hl
    assert "Health benefits ratio" not in hl
    assert "GAAP diluted EPS $ 1.36" not in hl
    assert "ST. LOUIS, October 25, 2024" not in hl
    assert "Adjusted diluted EPS of $1.62 in the third quarter of 2024." in hl
    assert "Premium and service revenues of $36.9 billion" in hl


def test_cnc_2024_q4_table_gone() -> None:
    hl = extract_press_release_highlights(_read("CNC_2024-12-31.html"))
    assert hl is not None
    assert "Total revenues (in millions)" not in hl
    assert "SG&A expense ratio" not in hl
    assert "2024 adjusted diluted EPS of $7.17, up 7% from $6.68" in hl


def test_cnc_2025_q1_table_gone() -> None:
    hl = extract_press_release_highlights(_read("CNC_2025-03-31.html"))
    assert hl is not None
    assert "Total revenues (in millions)" not in hl
    assert "Health benefits ratio" not in hl


def test_cnc_2025_q2_lede_serves_prose_not_table() -> None:
    # No bullets before the dateline here: the block is only the
    # sub-headline, so the lede fallback serves — dateline intro, CEO
    # quote and awards bullets, and no table row at all.
    hl = extract_press_release_highlights(_read("CNC_2025-06-30.html"))
    assert hl is not None
    assert "Total revenues (in millions)" not in hl
    assert "Health benefits ratio" not in hl
    assert "GAAP diluted loss per share" not in hl
    assert "We are disappointed by our second quarter results" in hl
    assert "America's Greatest Workplaces" in hl


def test_cnc_2025_q3_table_gone() -> None:
    hl = extract_press_release_highlights(_read("CNC_2025-09-30.html"))
    assert hl is not None
    assert "Total revenues (in millions)" not in hl
    assert "GAAP diluted loss per share $ (13.50)" not in hl
    assert "Adjusted diluted EPS of $0.50 in the third quarter" in hl


def test_cnc_2025_q4_table_gone() -> None:
    hl = extract_press_release_highlights(_read("CNC_2025-12-31.html"))
    assert hl is not None
    assert "Total revenues (in millions)" not in hl
    assert "Health benefits ratio" not in hl


def test_cnc_2026_q1_table_gone() -> None:
    hl = extract_press_release_highlights(_read("CNC_2026-03-31.html"))
    assert hl is not None
    assert "Total revenues (in millions)" not in hl
    assert "Health benefits ratio" not in hl


def test_cnc_2026_q2_table_gone() -> None:
    hl = extract_press_release_highlights(_read("CNC_2026-06-30.html"))
    assert hl is not None
    assert "Total revenues (in millions)" not in hl
    assert "Health benefits ratio" not in hl
