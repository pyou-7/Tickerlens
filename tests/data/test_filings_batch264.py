"""Batch 264 regression tests.

Batch 263's bullet-run extension stops at the 18-line bound even
mid-sub-list: DIS Q4 FY2025 ends on the first Experiences ◦ child
while its sibling ("Domestic Parks & Experiences operating income
grew 9% to $920 million") sits one line past the cap, and the line
after that is the "Guidance and Outlook" heading — the sub-list is
one bullet short of complete. Batch 264 adds sub-list completion to
_leading_bullet_block: at the bound, on a ◦ child of a colon-ended •
parent, with another ◦ child next, keep collecting — at most 4 lines
past the cap, mirroring the batch-222 allowance, and only while the
next line is a ◦ child. DIS Q4 FY2024 gains the same way: its
"Fiscal 2025:" sub-list completes with the last two ◦ children.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _html(lines):
    return "<html><body>" + "".join(f"<p>{ln}</p>" for ln in lines) + "</body></html>"


_FILLER = (
    "About Acme Corp: Acme Corp is a leading global provider of "
    "household and personal care products, serving consumers in more "
    "than one hundred countries with a portfolio of trusted brands "
    "spanning laundry, cleaning, oral care, skin care and pet care, "
    "and the Company remains committed to sustainable growth, "
    "operational excellence and returning capital to shareholders "
    "through dividends and share repurchases over the long term."
)


def _leading_block_lines(n_bullets, parent="• Entertainment: For Q4:", n_children=4):
    """A leading block of exactly `n_bullets` • bullets, then a colon
    parent, then `n_children` ◦ children — 13 + 1 + 4 = 18 entries by
    default, i.e. the block sits exactly on the 18-line bound on a ◦
    child. Extra ◦ siblings and a heading follow in the caller."""
    lines = ["ACME CORP REPORTS FISCAL 2026 FOURTH QUARTER RESULTS"]
    for i in range(n_bullets):
        lines.append(
            f"• Financial bullet {i + 1} with revenue of ${10 + i}.0 billion, "
            f"up {i + 1}% year over year"
        )
    lines.append(parent)
    for i in range(n_children):
        lines.append(
            f"◦ Segment child {i + 1} operating income grew {i + 1}% "
            f"to ${100 + i} million"
        )
    return lines


def test_sublist_completion_serves_stranded_sibling():
    # 18 entries on a ◦ child, one ◦ sibling past the cap, then the
    # next-section heading: the sibling is served, the heading is not.
    lines = _leading_block_lines(13)
    lines.append("◦ Segment child 5 operating income grew 5% to $104 million")
    lines.append("Guidance and Outlook:")
    out = extract_press_release_highlights(_html([*lines, _FILLER])) or ""
    assert "Segment child 4 operating income grew 4%" in out
    assert "Segment child 5 operating income grew 5%" in out
    assert "Guidance and Outlook" not in out


def test_sublist_completion_bounded_at_four_past_cap():
    # Six ◦ siblings past the cap: at most 4 are collected (entries
    # 19-22); the 5th and 6th strand, and the heading still stays out.
    lines = _leading_block_lines(13)
    for i in range(5, 11):
        lines.append(
            f"◦ Segment child {i} operating income grew {i}% to ${100 + i} million"
        )
    lines.append("Guidance and Outlook:")
    out = extract_press_release_highlights(_html([*lines, _FILLER])) or ""
    assert "Segment child 8 operating income grew 8%" in out
    assert "Segment child 9 operating income grew 9%" not in out
    assert "Segment child 10 operating income grew 10%" not in out
    assert "Guidance and Outlook" not in out


def test_sublist_completion_needs_colon_parent():
    # Same shape, but the nearest • parent ends with a period, not a
    # colon: the ◦ run is not a sub-list finish, so the bound still
    # ends the block at 18 and the sibling strands.
    lines = _leading_block_lines(
        13, parent="• Entertainment segment operating income grew."
    )
    lines.append("◦ Segment child 5 operating income grew 5% to $104 million")
    lines.append("Guidance and Outlook:")
    out = extract_press_release_highlights(_html([*lines, _FILLER])) or ""
    assert "Segment child 4 operating income grew 4%" in out
    assert "Segment child 5 operating income grew 5%" not in out


def test_sublist_completion_needs_same_level_sibling():
    # At the bound on a ◦ child, the next line is a • bullet — a new
    # top-level item, not a sub-list sibling — so the bound still ends
    # the block and the • bullet strands.
    lines = _leading_block_lines(13)
    lines.append("• Next section bullet with revenue of $9.0 billion, up 2%")
    lines.append("Guidance and Outlook:")
    out = extract_press_release_highlights(_html([*lines, _FILLER])) or ""
    assert "Segment child 4 operating income grew 4%" in out
    assert "Next section bullet" not in out


def test_dis_q4_2025_real_exhibit_experiences_sublist_completed():
    out = _live("DIS_2025-09-27")
    assert "International Parks & Experiences operating income grew 25%" in out
    assert "Domestic Parks & Experiences operating income grew 9%" in out
    assert "Guidance and Outlook" not in out
    assert out.count("◦") == 10
    assert out.count("•") == 8


def test_dis_q4_2024_real_exhibit_fiscal_year_sublist_completed():
    out = _live("DIS_2024-09-28")
    assert "Targeting $3 billion in stock repurchases" in out
    assert (
        "Entertainment: Double digit percentage segment operating income "
        "growth compared to fiscal 2024" in out
    )
    assert out.count("◦") == 6
    assert out.count("•") == 12
