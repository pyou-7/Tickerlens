"""Batch 256 regression tests.

Extractor: bullet-list completion in the Highlights-section
collector (src/tickerlens/data/filings.py,
_extract_highlights_sections_anchored). The 12-follow-line cap
could strand a bullet list mid-list: a "Full-year highlights"
sub-heading is collected as a label line inside the quarter
section, so BKR's Q4 section (6 Q4 bullets + the heading + 7 FY
bullets = 14 follow lines) served only 5 of the 7 FY bullets —
the last two (cash flows $3,332M, returns to shareholders
$1,320M) were cut by the cap, while the stored seed-era row
carries all 7. The completion allowance (batch 222/224) already
pulled unfinished sentences past the cap; a bullet next line is
the same wart in list form — a new item of the same list, not a
new section — so the winner's sub-list is now completed
post-selection (batch 256): the collector records the tail
(_collect_sublist_tail, at most 4 lines) but the ranking judges
the capped section exactly as before, and _extract_highlights_
section appends the tail to the winner only, bounded at 16
total lines. The bound is absolute for bullets:
_lede_termination_ahead returns False at a bullet, so a list
longer than 4 past the cap still stops at 16. Narrowed: the
tail is collected ONLY while the section is serving a
sub-section's list — the tail of the collected lines after the
last Highlights sub-heading must be all bullets. The broad
in-collector form regressed the blast (in-sync 1054 -> 970): a
plain 12-bullet section pulled its 13th bullet — AMD's "AMD
expanded its embedded portfolio ... including:" opener,
stranded without its sub-bullets — and growing a candidate
pre-selection flipped the density ranking (AGNC x7; Welltower's
Q4 section grew past its Annual section). The in-collector form
also violated the batch-177 principle that nothing about a
candidate changes before selection. Both shapes are pinned below
as refusals.
"""
import sys

sys.path.insert(0, "scripts")

from tickerlens.data.filings import extract_press_release_highlights
from tests.data.test_filings import _contact_release_html

_HEADLINE_BKR = "Baker Hughes Announces Fourth-Quarter and Full-Year 2024 Results"
_DATELINE_BKR = (
    "HOUSTON & LONDON (January 30, 2025) – Baker Hughes Company "
    "(Nasdaq: BKR) (\"Baker Hughes\" or the \"Company\") announced "
    "results today for the fourth-quarter and full-year 2024."
)
_QUOTE_BKR = (
    "\"2024 proved to be a momentous year for Baker Hughes. We closed "
    "out the year with exceptional fourth-quarter results, setting new "
    "quarterly and annual records for revenue, free cash flow and our "
    "adjusted measures of EPS, EBITDA, and EBITDA margin.\""
)
_Q4_BULLETS = [
    "• Orders of $7.5 billion, including $3.8 billion of IET orders.",
    "• RPO of $33.1 billion, including IET RPO of $30.1 billion.",
    "• Revenue of $7.4 billion, up 8% year-over-year.",
    "• GAAP diluted EPS of $1.18 and adjusted diluted EPS* of $0.70.",
    "• Adjusted EBITDA* of $1,310 million, up 20% year-over-year.",
    "• Cash flows from operating activities of $1,189 million and free cash flow* of $894 million.",
]
_FY_BULLETS = [
    "• Orders of $28.2 billion, including $13.0 billion of IET orders.",
    "• Revenue of $27.8 billion, up 9% year-over-year.",
    "• Attributable net income of $2,979 million.",
    "• GAAP diluted EPS of $2.98 and adjusted diluted EPS* of $2.35.",
    "• Adjusted EBITDA* of $4,591 million, up 22% year-over-year.",
    "• Cash flows from operating activities of $3,332 million and free cash flow* of $2,257 million.",
    "• Returns to shareholders of $1,320 million, including $484 million of share repurchases.",
]


def _bkr_html() -> str:
    # Real BKR Q4 FY2024 shape: headline, Q4 section (6 bullets),
    # "Full-year highlights" sub-heading, FY section (7 bullets),
    # then the dateline, the CEO quote and the news-release line —
    # the tail the old cap never reached, and which must stay out.
    return _contact_release_html(
        "EX-99.1",
        _HEADLINE_BKR,
        "Fourth-quarter highlights",
        *_Q4_BULLETS,
        "Full-year highlights",
        *_FY_BULLETS,
        _DATELINE_BKR,
        _QUOTE_BKR,
        "Baker Hughes Company News Release",
    )


def test_bkr_full_year_bullets_are_not_cut_by_the_cap() -> None:
    # Before the fix the Q4 section stopped at 12 follow lines: 6 Q4
    # bullets + the "Full-year highlights" label + 5 FY bullets, and
    # the last two FY bullets never reached the page.
    result = extract_press_release_highlights(_bkr_html())
    assert result is not None
    assert result.split("\n\n")[0] == _HEADLINE_BKR
    for b in _Q4_BULLETS:
        assert b in result
    for b in _FY_BULLETS:
        assert b in result
    assert "Full-year highlights" in result
    # The dateline, the quote and the news-release line sit after the
    # FY list: the list completes, the section still ends there.
    assert "HOUSTON & LONDON (January 30, 2025)" not in result
    assert "2024 proved to be a momentous year" not in result
    assert "Baker Hughes Company News Release" not in result


def test_bullet_completion_stops_at_the_16_line_bound() -> None:
    # 6 Q4 bullets + the sub-heading + 10 FY bullets = 17 follow
    # lines: the allowance pulls 4 past the 12-line cap (items 1-9)
    # and the 16-line bound is absolute for bullets — item 10 stays
    # out, because _lede_termination_ahead returns False at a bullet.
    fy = [
        f"• Full-year item {n}: orders of ${n}.0 billion."
        for n in range(1, 11)
    ]
    result = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            _HEADLINE_BKR,
            "Fourth-quarter highlights",
            *_Q4_BULLETS,
            "Full-year highlights",
            *fy,
        )
    )
    assert result is not None
    for n in range(1, 10):
        assert f"Full-year item {n}: orders of ${n}.0 billion." in result
    assert "Full-year item 10: orders of $10.0 billion." not in result


def test_section_still_ends_on_non_bullet_after_the_cap() -> None:
    # 12 bullets hit the cap and the next line is prose, not a bullet:
    # the section ends exactly as before — the bullet rule fires only
    # on a bullet next line, never on prose.
    bullets = [
        f"• Quarter item {n}: revenue of ${n}.0 billion, up {n}% year-over-year."
        for n in range(1, 13)
    ]
    result = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            _HEADLINE_BKR,
            "Fourth-quarter highlights",
            *bullets,
            "The chief executive officer commented on the quarter.",
        )
    )
    assert result is not None
    for b in bullets:
        assert b in result
    assert "The chief executive officer commented" not in result


def test_dot_bullet_continues_past_the_cap() -> None:
    # The "·" lead is the same bullet shape as "•" (batch 138/139):
    # a "·" item in the sub-section's list past the cap is pulled
    # in, not stranded. The sub-heading is what licenses the pull —
    # a bare 12-bullet list with no sub-heading stops at the cap
    # (the AMD shape), so the "·" item here sits under the
    # "Full-year highlights" sub-heading, as BKR's FY bullets do.
    bullets = [
        f"• Quarter item {n}: revenue of ${n}.0 billion, up {n}% year-over-year."
        for n in range(1, 7)
    ]
    fy = [
        f"• Full-year item {n}: revenue of ${n}.0 billion, up {n}% year-over-year."
        for n in range(1, 6)
    ]
    dot = "· Full-year item 6: revenue of $6.0 billion, up 6% year-over-year."
    result = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            _HEADLINE_BKR,
            "Fourth-quarter highlights",
            *bullets,
            "Full-year highlights",
            *fy,
            dot,
        )
    )
    assert result is not None
    assert dot in result


def test_plain_list_past_the_cap_is_not_pulled() -> None:
    # The AMD shape, pinned as a refusal: a plain 12-bullet
    # Highlights section with NO sub-heading stops at the cap — the
    # 13th bullet is the section's own list continuing, and pulling
    # it strands its opener ("... including:") without its
    # sub-bullets. Only a sub-section's list completes past the cap.
    bullets = [
        f"• Quarter item {n}: revenue of ${n}.0 billion, up {n}% year-over-year."
        for n in range(1, 13)
    ]
    opener = "• Quarter item 13: expanded its portfolio for a range of applications, including:"
    result = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            _HEADLINE_BKR,
            "Fourth-quarter highlights",
            *bullets,
            opener,
            "◦ Sub-item one for the new portfolio.",
            "◦ Sub-item two for the new portfolio.",
        )
    )
    assert result is not None
    for b in bullets:
        assert b in result
    assert "Quarter item 13" not in result
