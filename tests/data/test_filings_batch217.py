"""Batch 217: a results-narrative heading wrapped across two flattened
lines is recognized as a section-end heading, so the guidance
collector stops at it instead of serving it as guidance content.

DAL 2024-12-31 serves its heading as "Revenue Environment" /
"and Outlook" (DAL 2025-06-30 wraps the other way, "Revenue
Environment and" / "Outlook"), so batch 202's single-line carve-out
never fired and the stored guidance ends on the two heading
fragments. The fix joins the candidate with its next non-admin line
and tests the joined form against the two narrative patterns
(_GUIDANCE_NARRATIVE_OUTLOOK_RE / _GUIDANCE_RESULTS_LED_RE); the
follower is then tested after the second fragment, and the collector
breaks without appending either fragment.

Blast (guidance old-vs-new over all 1,699 cached exhibits,
scripts/batch217_guidance_blast.py, hidden_files/blast217/g_old ->
g_new): 1 diff — DAL 2024-12-31 guidance loses only the two heading
fragments; 1,698 byte-identical. Highlights old-vs-new over the same
cache (scripts/batch217_cache_blast.py, blast217/h_old -> h_new):
byte-identical (the changed function is guidance-only).
"""

import os

from tickerlens.data.filings import (
    _is_guidance_next_section_heading,
    _wrapped_guidance_narrative_end,
    extract_management_guidance,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


# --- unit: the wrapped join ---


def test_wrapped_narrative_before_conjunction():
    # DAL 2024-12-31: "Revenue Environment" / "and Outlook".
    lines = ["Revenue Environment", "and Outlook", "x"]
    assert _wrapped_guidance_narrative_end(lines, 0) == 1


def test_wrapped_narrative_after_conjunction():
    # DAL 2025-06-30: "Revenue Environment and" / "Outlook".
    lines = ["Revenue Environment and", "Outlook", "x"]
    assert _wrapped_guidance_narrative_end(lines, 0) == 1


def test_wrapped_narrative_colon_tail():
    # LUV's single-line shape wrapped: "Revenue Results and" / "Outlook:".
    lines = ["Revenue Results and", "Outlook:", "x"]
    assert _wrapped_guidance_narrative_end(lines, 0) == 1


def test_wrapped_results_led_by_segment_tail():
    # GE's results-led shape wrapped: "Results and Guidance" /
    # "by Reporting Segment".
    lines = ["Results and Guidance", "by Reporting Segment", "x"]
    assert _wrapped_guidance_narrative_end(lines, 0) == 1


def test_wrapped_bare_results_led():
    lines = ["Results and", "Outlook", "x"]
    assert _wrapped_guidance_narrative_end(lines, 0) == 1


def test_wrapped_rejects_prose_continuation():
    # The joined line must end on the tail word: a prose clause that
    # mentions the outlook is not a heading.
    lines = ["Revenue Environment", "and Outlook for 2026 is strong", "x"]
    assert _wrapped_guidance_narrative_end(lines, 0) is None


def test_wrapped_rejects_table_label_plus_prose():
    # A bare table label ("Revenue") followed by a prose line starting
    # "and Outlook ..." join-matches the end-open results-led regex —
    # the heading-tail guard must refuse it.
    lines = ["Revenue", "and Outlook for the quarter", "x"]
    assert _wrapped_guidance_narrative_end(lines, 0) is None


def test_wrapped_rejects_terminated_second_fragment():
    lines = ["Revenue Environment", "and Outlook is strong.", "x"]
    assert _wrapped_guidance_narrative_end(lines, 0) is None


def test_wrapped_rejects_long_second_fragment():
    # A second fragment over the 40-char cap is not a heading
    # continuation even when the joined line would otherwise match:
    # "by Reporting Segment Results And Outlook" passes the
    # results-led heading-tail guard, so only the length cap refuses it.
    lines = [
        "Results and Guidance",
        "by Reporting Segment Results And Outlook Now",
        "x",
    ]
    assert _wrapped_guidance_narrative_end(lines, 0) is None


def test_wrapped_rejects_uppercase_prose_start():
    # A second fragment starting with a capitalised prose word is a
    # new sentence, not a heading continuation.
    lines = ["Revenue Environment", "Outlook for 2026 is strong", "x"]
    assert _wrapped_guidance_narrative_end(lines, 0) is None


def test_wrapped_single_line_heading_is_not_wrapped():
    # A complete single-line heading followed by prose is not a wrap.
    lines = [
        "Revenue Environment and Outlook",
        '"Delta built momentum as we closed out 2024."',
    ]
    assert _wrapped_guidance_narrative_end(lines, 0) is None


def test_wrapped_skips_admin_lines_between_fragments():
    lines = ["Revenue Environment", "-more-", "and Outlook", "x"]
    assert _wrapped_guidance_narrative_end(lines, 0) == 2


# --- function level: the section-end test on a wrapped heading ---


_QUOTE = (
    '"Delta built momentum as we closed out 2024, with December quarter '
    "total revenue growth of 5.7 percent coming in ahead of guidance.\""
)


def test_wrapped_heading_ends_section_before_quote():
    lines = ["Financial Guidance", "Revenue Environment", "and Outlook", _QUOTE]
    assert _is_guidance_next_section_heading(lines, 1) is True


def test_wrapped_heading_ends_section_before_bullet():
    lines = [
        "Financial Guidance",
        "Revenue Environment",
        "and Outlook",
        "• Demand accelerated through the quarter.",
    ]
    assert _is_guidance_next_section_heading(lines, 1) is True


def test_wrapped_heading_at_end_of_lines_does_not_end_section():
    # No follower after the second fragment: the follower test fails,
    # so the heading is collected like any other line (same as the
    # single-line rule — a heading with nothing after it cannot prove
    # a new section starts).
    lines = ["Financial Guidance", "Revenue Environment", "and Outlook"]
    assert _is_guidance_next_section_heading(lines, 1) is False


# --- real exhibits ---


def test_dal_q4_2024_guidance_drops_wrapped_heading():
    g = extract_management_guidance(_load("DAL_2024-12-31.html"))
    assert g is not None
    assert "Revenue Environment" not in g
    assert "and Outlook" not in g
    # Live footnote spacing is glued ("4Introduced ...") — the stored
    # row's spaced rendering is an older extractor's, see the repair
    # script's normalization gate; the wart removal is the only
    # content change (956 -> 922 = the two heading fragments plus
    # their joins).
    assert len(g) == 922
    assert g.endswith("4Introduced at November 2024 Investor Day")


def test_dal_q2_2025_guidance_unchanged():
    # DAL 2025-06-30 also wraps the heading ("Revenue Environment
    # and" / "Outlook") but it is not in the guidance collection
    # path — the live extraction must be byte-identical to stored.
    g = extract_management_guidance(_load("DAL_2025-06-30.html"))
    assert g is not None
    assert "Revenue Environment" not in g
    assert len(g) == 1527
