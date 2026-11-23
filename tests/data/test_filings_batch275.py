"""Batch 275 regression tests.

The `norm()` footnote-key rule in scripts/batch231_repair.py claimed
to be per-line ("literal spaces, never \\s, so a rule can never join
two lines") but ran on the whole string: `([,.])\\s+(\\d)` with `\\s`
matching a newline glued a line ending in "." or "," to a
digit-starting next line. Batch 274 diagnosed it on Ford — the lede
(2910 chars) + segment line (2256 chars) became one 5162-char normed
line, defeating the gates' exact line-match even when every figure
was present, which is why the gate chain refused the 9 F override
rows. The probe (scripts/batch275_probe.py) found the defect in 31
stored rows and 7 live extractions across the corpus.

The fix moves that one rule into the per-line loop (literal
spaces/tabs only). The intra-line cases the batch-241 pins cover
("$1.64, 1 up" -> "$1.64,1 up", "basis. 1" -> "basis.1") are
unchanged, and the batch-272 date guard ("November 6, 2024" never
glues its day to the month) still holds.

Census impact (scripts/batch274_census.py, full 2,543-row DB):
baseline before the fix was B 1125 / SKIP-loss 81; the fixed census
is recorded in the batch-275 docs entry.
"""
import os
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


# --- the defect: no cross-line glue --------------------------------------

def test_norm_never_glues_period_line_to_digit_line():
    assert norm("on an adjusted basis.\n1 footnote defines the term") == (
        "on an adjusted basis.\n1 footnote defines the term"
    )


def test_norm_never_glues_comma_line_to_digit_line():
    assert norm("Fellow Affirm shareholders,\n2 Affirm Holdings, Inc.") == (
        "Fellow Affirm shareholders,\n2 Affirm Holdings, Inc."
    )


def test_norm_ford_lede_and_segment_stay_two_lines():
    lede = "• Ford reports second-quarter revenue of $47.8 billion."
    segment = "2 Total Company Highlights Fourth Quarter Full Year"
    assert norm(lede + "\n" + segment).split("\n") == [lede, segment]


def test_norm_mega_lines_stay_separate():
    # The batch-274 shape: a 2910-char lede line ending in "." and a
    # 2256-char segment line starting with a digit must not fuse into
    # one 5162-char normed line.
    lede = ("Revenue was $48.2 billion, an increase from a year ago. " * 60).strip()
    segment = ("2 Total Company Highlights 2023 2024 Change " * 55).strip()
    assert len(lede) > 2000 and len(segment) > 1000
    lines = norm(lede + "\n" + segment).split("\n")
    assert len(lines) == 2
    assert lines[0] == lede
    # The segment line's "Highlights 2023" is glued by the batch-242
    # letter rule (intended); the point is the two lines never fuse.
    assert lines[1].startswith("2 Total Company Highlights")


# --- the rule's intra-line job is unchanged -------------------------------

def test_norm_footnote_key_intra_line_still_glues():
    assert norm("Diluted earnings per share was $1.64, 1 up 12 percent") == norm(
        "Diluted earnings per share was $1.64,1 up 12 percent"
    )
    assert norm("on an adjusted basis. 1") == norm("on an adjusted basis.1")
    assert norm("word , 1 up") == norm("word,1 up")


def test_norm_date_day_never_glues_to_month():
    # Batch-272 guard: a date's day number keeps its space; the comma
    # is followed by a 4-digit year, which never glues.
    assert norm("November 6, 2024") == "November 6, 2024"
    assert norm("ended Sept. 1, 2025") != norm("ended Sept. 2, 2025")


def test_norm_content_differences_still_differ():
    assert norm("on an adjusted basis. 1") != norm("on an adjusted basis. 2")
    assert norm("Net revenue $6.2 billion") != norm("Net revenue $6.3 billion")


# --- end-to-end on the cached Ford exhibits -------------------------------

def _live_normed_lines(ticker_period: str) -> list[str]:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        live = extract_press_release_highlights(fh.read()) or ""
    return [ln for ln in norm(live).split("\n") if ln.strip()]


def test_ford_live_normed_lines_keep_lede_and_segment_separate():
    # Before the fix the F 2024-06-30 normed live text fused the lede
    # bullet and the segment-table page into a single line; the gates
    # then could never match the stored segment line. The lede page
    # (2910 chars) and the segment page (2252 chars) must stay two
    # lines, and no normed line may exceed 4000 chars.
    for period in ("F_2024-06-30", "F_2024-09-30", "F_2024-12-31"):
        lines = _live_normed_lines(period)
        assert not any(len(ln) > 4000 for ln in lines), period
        assert any("Business Segment Highlights" in ln for ln in lines), period
    # Note: F_2024-09-30's raw live line itself embeds the segment
    # heading 1703 chars in (one flattened exhibit page carries the
    # narrative tail and the segment heading) — that is the
    # extractor's line, not norm's doing, so no position assertion
    # here; the fused-5162-char normed line the fix removes is pinned
    # by test_norm_mega_lines_stay_separate above.
    # Only the Q4 FY2024 exhibit carries the Total Company table page
    # in the leading block; Q2/Q3 serve the narrative page instead.
    assert any(
        "Total Company Highlights" in ln
        for ln in _live_normed_lines("F_2024-12-31")
    )
