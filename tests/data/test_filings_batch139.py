"""Batch 139 regression tests: lede-budget separators (Chubb Q3 2024).

Chubb's Q3 2024 exhibit flattens its bullet list with middle-dot ("·")
markers and white-circle ("○") sub-bullet markers — neither was in
_is_lone_bullet_marker, so both counted as content lines, and even the
recognized markers (●/•/-/*) consumed budget mid-lede. The old 6-line
budget therefore stopped the Q3 2024 lede after bullet 2 although the
lede holds 8 bullets, and the stored row (from an older extraction) held
only bullet 1.

The fix: a lone marker line is a separator, never budget — at the lead
it is skipped (batch 138's rule, now extended to "·"/"○"), mid-lede it is
kept as a separator paragraph. In a marker-delimited lede the current
item is finished rather than cut mid-item (bounded: 4 continuation
lines past the budget, and a marker at the boundary ends collection
without being appended). A marker-less prose lede keeps the old hard
6-line cap — without item delimiters "finish the item" is undefined,
and the ungated version changed 109/232 blast quarters, mostly prose
extensions up to the 4000-char cap, for no defect.
"""

from tickerlens.data.filings import (
    _is_lone_bullet_marker,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def test_middle_dot_and_white_circle_are_lone_markers() -> None:
    assert _is_lone_bullet_marker("·")
    assert _is_lone_bullet_marker("○")
    # Still the batch-138 set.
    assert _is_lone_bullet_marker("●")
    assert _is_lone_bullet_marker("•")
    assert _is_lone_bullet_marker("-")
    assert _is_lone_bullet_marker("*")
    # A marker glued to text is content, not a separator.
    assert not _is_lone_bullet_marker("· Net income was $2.32 billion.")
    assert not _is_lone_bullet_marker("○ Global P&C net premiums written.")
    assert not _is_lone_bullet_marker("Net income was $2.32 billion.")


def _cb_q3_2024_html() -> str:
    # Real Q3 2024 lede shape (exhibit 99.1): middle-dot bullets, a
    # white-circle sub-bullet, bullets wrapping across lines. The
    # masthead block is omitted: the test is about the lede loop, not
    # the masthead skips.
    return _contact_release_html(
        "Chubb Reports Third Quarter Results",
        "·",
        "Net income was $2.32 billion, up 13.8%, and core operating income was $2.33 billion, up 14.3%. For the",
        "nine months, net income and core operating income were a record $6.70 billion and $6.75 billion, up 16.9% and 13.8%, respectively. On a per share basis,",
        "year-to-date net income and core operating income of $16.38 and $16.50 were records and up 18.8% and 15.6%.",
        "·",
        "Consolidated net premiums written were up 5.5%, or 6.6% in constant dollars.",
        "·",
        "P&C net premiums written were up 5.4%, or 6.1% in constant dollars.",
        "○",
        "Global P&C net premiums written, which excludes Agriculture, were up 7.6%, or 8.5% in constant dollars, with",
        "commercial insurance up 8.1% and consumer insurance up 9.4%.",
        "up 4.9%, or 7.5% in constant dollars, with growth of 8.5% in consumer insurance and 6.7% in commercial insurance.",
        "·",
        "Agriculture net premiums written were down 9.3% due to lower commodity prices.",
    )


def test_cb_q3_2024_markers_do_not_consume_budget_and_final_item_completes() -> None:
    hl = extract_press_release_highlights(_cb_q3_2024_html())
    assert hl is not None
    parts = hl.split("\n\n")
    assert parts[0] == "Chubb Reports Third Quarter Results"
    # The lead "·" is skipped; bullets 1-4 complete with separators;
    # bullet 5 (after the boundary marker) is never reached.
    assert parts[1:] == [
        "Net income was $2.32 billion, up 13.8%, and core operating income was $2.33 billion, up 14.3%. For the",
        "nine months, net income and core operating income were a record $6.70 billion and $6.75 billion, up 16.9% and 13.8%, respectively. On a per share basis,",
        "year-to-date net income and core operating income of $16.38 and $16.50 were records and up 18.8% and 15.6%.",
        "·",
        "Consolidated net premiums written were up 5.5%, or 6.6% in constant dollars.",
        "·",
        "P&C net premiums written were up 5.4%, or 6.1% in constant dollars.",
        "○",
        "Global P&C net premiums written, which excludes Agriculture, were up 7.6%, or 8.5% in constant dollars, with",
        "commercial insurance up 8.1% and consumer insurance up 9.4%.",
        "up 4.9%, or 7.5% in constant dollars, with growth of 8.5% in consumer insurance and 6.7% in commercial insurance.",
    ]
    assert "Agriculture net premiums written were down" not in hl


def test_marker_at_budget_boundary_does_not_dangle() -> None:
    # Content reaches exactly 6 at the end of bullet 3; the following
    # marker must end collection, not appear as a trailing paragraph.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Acme Reports Third Quarter Results",
            "•",
            "Bullet one reports net income of $1.21 billion, up 14 percent.",
            "Bullet one continues with core operating income up 9 percent.",
            "•",
            "Bullet two reports net premiums written of $4.8 billion, up 6 percent.",
            "Bullet two continues with a combined ratio of 87.2 percent.",
            "•",
            "Bullet three reports book value per share of $142.18, up 11 percent.",
            "Bullet three continues with tangible book value up 13 percent.",
            "•",
            "Bullet four must not appear in the extracted highlights at all.",
        )
    )
    assert hl is not None
    parts = hl.split("\n\n")
    assert parts[0] == "Acme Reports Third Quarter Results"
    assert parts[1:] == [
        "Bullet one reports net income of $1.21 billion, up 14 percent.",
        "Bullet one continues with core operating income up 9 percent.",
        "•",
        "Bullet two reports net premiums written of $4.8 billion, up 6 percent.",
        "Bullet two continues with a combined ratio of 87.2 percent.",
        "•",
        "Bullet three reports book value per share of $142.18, up 11 percent.",
        "Bullet three continues with tangible book value up 13 percent.",
    ]


def test_finishing_cap_bounds_long_wrapped_item() -> None:
    # The final bullet wraps 7 lines past the budget point; only the
    # first 4 continuation lines are taken.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Acme Reports Third Quarter Results",
            "•",
            "Alpha bullet opens with net income of $1.21 billion, up 14 percent.",
            "Alpha bullet continues with core operating income up 9 percent.",
            "Alpha bullet closes with a combined ratio of 87.2 percent.",
            "•",
            "Beta bullet opens with net premiums written of $4.8 billion.",
            "Beta bullet continues with commercial lines up 8 percent.",
            "•",
            "Gamma bullet opens with book value per share of $142.18.",
            "Gamma bullet second line reports tangible book value up 13 percent.",
            "Gamma bullet third line reports ROE of 14.7 percent annualized.",
            "Gamma bullet fourth line reports ROTE of 21.7 percent annualized.",
            "Gamma bullet fifth line reports core operating ROE of 13.9 percent.",
            "Gamma bullet sixth line must not appear in the highlights.",
            "Gamma bullet seventh line must not appear in the highlights.",
        )
    )
    assert hl is not None
    parts = hl.split("\n\n")
    assert parts[1:] == [
        "Alpha bullet opens with net income of $1.21 billion, up 14 percent.",
        "Alpha bullet continues with core operating income up 9 percent.",
        "Alpha bullet closes with a combined ratio of 87.2 percent.",
        "•",
        "Beta bullet opens with net premiums written of $4.8 billion.",
        "Beta bullet continues with commercial lines up 8 percent.",
        "•",
        "Gamma bullet opens with book value per share of $142.18.",
        "Gamma bullet second line reports tangible book value up 13 percent.",
        "Gamma bullet third line reports ROE of 14.7 percent annualized.",
        "Gamma bullet fourth line reports ROTE of 21.7 percent annualized.",
        "Gamma bullet fifth line reports core operating ROE of 13.9 percent.",
    ]


def test_prose_lede_keeps_hard_six_line_cap() -> None:
    # No markers anywhere: the old behavior is exact — the 7th and 8th
    # prose lines never appear, even though the finish rule exists.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Acme Reports Third Quarter Results",
            "Prose line one reports quarterly net income of $1.21 billion, up 14 percent.",
            "Prose line two reports core operating income of $1.18 billion, up 9 percent.",
            "Prose line three reports net premiums written of $4.8 billion, up 6 percent.",
            "Prose line four reports a combined ratio of 87.2 percent for the quarter.",
            "Prose line five reports book value per share of $142.18, up 11 percent.",
            "Prose line six reports tangible book value per share up 13 percent.",
            "Prose line seven must not appear in the extracted highlights at all.",
            "Prose line eight must not appear in the extracted highlights at all.",
        )
    )
    assert hl is not None
    parts = hl.split("\n\n")
    assert parts[1:] == [
        "Prose line one reports quarterly net income of $1.21 billion, up 14 percent.",
        "Prose line two reports core operating income of $1.18 billion, up 9 percent.",
        "Prose line three reports net premiums written of $4.8 billion, up 6 percent.",
        "Prose line four reports a combined ratio of 87.2 percent for the quarter.",
        "Prose line five reports book value per share of $142.18, up 11 percent.",
        "Prose line six reports tangible book value per share up 13 percent.",
    ]


def test_lead_middle_dot_and_circle_markers_are_skipped() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Acme Reports Third Quarter Results",
            "·",
            "○",
            "Only bullet line.",
        )
    )
    assert hl is not None
    parts = hl.split("\n\n")
    assert parts[0] == "Acme Reports Third Quarter Results"
    assert "Only bullet line." in parts[1:]
    assert "·" not in parts[1:]
    assert "○" not in parts[1:]
