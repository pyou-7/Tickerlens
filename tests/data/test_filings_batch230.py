"""Batch 230: fragmented bullet openers — Dollar General's 2026 releases
typeset each highlights bullet as a table row whose text cell wraps
after the first word ("· Net" / "Sales Increased 3.4% to $10.8
Billion"), and the flattener preserves the break, so the served
highlights read as a one-word bullet plus a stray line. The two
stored DG rows (2026 Q1, 2026 Q2) both show the fragment; the older
DG quarters serve the prose section instead, so their bullets never
reach the output.

The fix: _join_fragmented_bullet_starts joins a marker + 1-2 bare
alphabetic words with its plain continuation line, post-collection
(winning section, lede list, guidance section) so qualification and
the density competition are untouched. The predicate is narrow by
construction:
a label line always carries punctuation ("• Same-restaurant sales:",
"• Fiscal 2025:", "• Media: media@danaher.com") and never matches,
and a sub-bullet or next bullet after the fragment blocks the join
(Equifax's "• Revenues" heads a "◦" sub-bullet list; Carnival's
"• Pricing" is followed by another "•" bullet). A bullet that wraps
after a full clause is untouched — only the orphaned opener joins.

The blast over 1,699 exhibits found exactly 2 highlights diffs
(DG 2026-05-01, DG 2026-07-31 — all 6 bullets joined in each) and
7 guidance diffs (DG 2024-08-02, 2024-11-01, 2025-01-31, 2025-05-02,
2025-08-01, 2026-05-01, 2026-07-31 — the guidance sections carry the
same wrapped bullets, including "○ The"/"○ Diluted" sub-bullets).

Live pins run the extractors against the real cached exhibits; the
unit pins cover the predicate and the continuation guards directly.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _FRAGMENTED_BULLET_RE,
    _join_fragmented_bullet_starts,
    extract_management_guidance,
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


def _live_guidance(ticker_period: str) -> str | None:
    html = open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ).read()
    return extract_management_guidance(html)


# --- Live pins: the two DG quarters whose stored rows are fragmented ---


def test_dg_2026_q1_bullets_joined():
    out = _live("DG_2026-05-01")
    assert "· Net Sales Increased 3.4% to $10.8 Billion" in out
    assert "· Same-Store Sales Increased 2.0%" in out
    assert "· Operating Profit Increased 10.8% to $638.5 Million" in out
    assert "· Diluted Earnings Per Share (“EPS”) Increased 12.4% to $2.00" in out
    assert "· Cash Flow From Operations of $716.2 Million" in out
    assert (
        "· Board of Directors Declares Quarterly Cash Dividend of $0.59 per share"
        in out
    )
    assert "· Net\nSales" not in out
    assert "· Board\nof Directors" not in out


def test_dg_2026_q2_bullets_joined():
    out = _live("DG_2026-07-31")
    assert "· Net Sales Increased 5.2% to $11.3 Billion" in out
    assert "· Same-Store Sales Increased 3.5%" in out
    assert "· Operating Profit Increased 29.2% to $769.2 Million" in out
    assert "· Diluted Earnings Per Share (“EPS”) Increased 33.3% to $2.48" in out
    assert "· Year-to-Date Cash Flow From Operations of $1.5 Billion" in out
    assert (
        "· Board of Directors Declares Quarterly Cash Dividend of $0.59 per share"
        in out
    )
    assert "· Year-to-Date\nCash" not in out


def test_dg_older_quarters_unchanged():
    # DG 2024-2025 quarters serve the prose Highlights section, not
    # the leading bullets — the join must not change what they serve
    # (the prose itself wraps "Net\nsales ...", which is the pre-existing
    # line-break preservation, not a bullet fragment).
    out = _live("DG_2025-10-31")
    assert "Net\nsales increased 4.6% to $10.6 billion" in out
    assert "· Net\nSales" not in out


# --- Live pins: the guidance sections carry the same wrapped bullets ---


def test_dg_guidance_bullets_joined_2026_q1():
    out = _live_guidance("DG_2026-05-01")
    assert out is not None
    assert "· Net Sales Increased 3.4% to $10.8 Billion" in out
    assert "· Board of Directors Declares Quarterly Cash Dividend of $0.59 per share" in out
    assert "· Net\n\nSales" not in out


def test_dg_guidance_bullets_joined_2024_q2():
    # The older guidance sections carry the same wrap, including "○"
    # sub-bullets ("○ The" / "○ Diluted").
    out = _live_guidance("DG_2024-08-02")
    assert out is not None
    assert (
        "· Net sales growth in the range of approximately 4.7% to 5.3%"
        in out
    )
    assert "○ The Company now expects an immaterial impact to EPS" in out
    assert "○ Diluted EPS guidance assumes an effective tax rate" in out
    assert "· Net\n\nsales growth" not in out
    assert "○ The\n\nCompany" not in out


def test_dg_guidance_share_repurchases_joined():
    out = _live_guidance("DG_2026-07-31")
    assert out is not None
    assert "· Share repurchases of up to $700 million" in out
    assert "· Diluted EPS in the range of approximately $7.80 to $8.00" in out


# --- Unit pins: the predicate ---


def test_fragment_predicate_matches_one_and_two_word_openers():
    assert _FRAGMENTED_BULLET_RE.match("· Net")
    assert _FRAGMENTED_BULLET_RE.match("· Same-Store")
    assert _FRAGMENTED_BULLET_RE.match("· Year-to-Date")
    assert _FRAGMENTED_BULLET_RE.match("· Fourth")
    assert _FRAGMENTED_BULLET_RE.match("• Using")
    assert _FRAGMENTED_BULLET_RE.match("· The")


def test_fragment_predicate_rejects_labels_and_complete_bullets():
    assert not _FRAGMENTED_BULLET_RE.match("• Same-restaurant sales:")
    assert not _FRAGMENTED_BULLET_RE.match("• Fiscal 2025:")
    assert not _FRAGMENTED_BULLET_RE.match("• Media: media@danaher.com")
    # ("• Revenues" DOES match the predicate — it is a one-word
    # opener — but its continuation is a "◦" sub-bullet, so the join
    # guard blocks it; see test_join_skips_next_bullet_and_sub_bullet.)
    # A complete bullet (three words, figures, punctuation) is never
    # a fragment — the wrap after a full clause stays as-is.
    assert not _FRAGMENTED_BULLET_RE.match(
        "· Net Sales Increased 3.4% to $10.8 Billion"
    )
    assert not _FRAGMENTED_BULLET_RE.match("· Fourth Quarter Net Sales Decreased")
    assert not _FRAGMENTED_BULLET_RE.match("• Q1 revenue grew 5%")
    assert not _FRAGMENTED_BULLET_RE.match("· Net Sales;")


# --- Unit pins: the join and its continuation guards ---


def test_join_merges_fragment_with_continuation():
    lines = [
        "· Net",
        "Sales Increased 3.4% to $10.8 Billion",
        "· Same-Store",
        "Sales Increased 2.0%",
        "· Board",
        "of Directors Declares Quarterly Cash Dividend of $0.59 per share",
    ]
    assert _join_fragmented_bullet_starts(lines) == [
        "· Net Sales Increased 3.4% to $10.8 Billion",
        "· Same-Store Sales Increased 2.0%",
        "· Board of Directors Declares Quarterly Cash Dividend of $0.59 per share",
    ]


def test_join_skips_next_bullet_and_sub_bullet():
    # Carnival: "• Pricing" is followed by another bullet — no join.
    # Equifax: "• Revenues" heads a "◦" sub-bullet list — no join.
    lines = [
        "• Pricing",
        "• Adjusted net income (loss)",
        "• Revenues",
        "◦ $2.13 billion, a 1% increase over the previous quarter",
    ]
    assert _join_fragmented_bullet_starts(lines) == lines


def test_join_skips_blank_and_heading_continuations():
    lines = ["· Net", "", "Sales Increased 3.4% to $10.8 Billion"]
    assert _join_fragmented_bullet_starts(lines) == lines
    lines = ["· Net", "THIRD QUARTER 2026 HIGHLIGHTS"]
    assert _join_fragmented_bullet_starts(lines) == lines


def test_join_skips_dateline_continuation():
    lines = ["· Net", "GOODLETTSVILLE, Tenn.--(BUSINESS WIRE)--May 28, 2026--"]
    assert _join_fragmented_bullet_starts(lines) == lines


def test_join_leaves_complete_bullets_alone():
    lines = [
        "· Fourth Quarter Net Sales Decreased 3.4% to $9.9 Billion;",
        "Fiscal Year Net Sales Increased 2.2% to $38.7 Billion",
        "· Cash Flows From Operations Increased 247.3% to $663.8 Million",
    ]
    assert _join_fragmented_bullet_starts(lines) == lines


def test_join_fragment_at_end_of_list_is_kept():
    lines = ["· Net Sales Increased 3.4% to $10.8 Billion", "· Cash"]
    assert _join_fragmented_bullet_starts(lines) == lines
