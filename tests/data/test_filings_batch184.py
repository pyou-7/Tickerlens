"""Batch 184 regression tests: a leading-"Highlights" sub-headline is content.

The old _HIGHLIGHTS_HEADING_RE matched ANY line starting with the word
"highlights" (bare "^highlights?\\b"), so Chipotle's all-caps
sub-headlines — "HIGHLIGHTS RETURN TO POSITIVE COMPARABLE SALES AND
TRANSACTIONS IN JUNE" (Q2 2025) and "HIGHLIGHTS POSITIVE COMPARABLE
SALES" (Q3 2025) — were dropped by the lede loop as section headings.
Both sit between the headline and the dateline and carry real news:
June comps turned positive while the quarter was down 4%. The regex's
leading branch is now narrowed to heading-shaped tails (of/from/for/
include + unterminated rest); the trailing-word branch is unchanged.
"""
from tickerlens.data.filings import (
    _HIGHLIGHTS_HEADING_RE,
    _is_lede_heading_fragment,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def test_highlights_heading_leading_branch_heading_shapes_match() -> None:
    # Every attested real heading that starts with "Highlights"
    # (full-cache survey, 17 distinct lines).
    for ln in (
        "Highlights",
        "HIGHLIGHTS",
        "HIGHLIGHTS OF SEGMENT RESULTS",
        "HIGHLIGHTS FROM THE QUARTER",
        "HIGHLIGHTS FROM THE YEAR",
        "Highlights from the report include:",
        "Highlights for the first quarter of 2025 are listed below:",
        "Highlights for the fourth quarter of 2025 are listed below:",
        "Q1 2025 Financial Highlights (unaudited)",
        "Selected Revenue Highlights",
    ):
        assert _HIGHLIGHTS_HEADING_RE.search(ln), ln


def test_highlights_heading_sub_headlines_do_not_match() -> None:
    # CMG's all-caps sub-headlines: a sentence, not a section heading —
    # the word after "Highlights" is a verb/adjective, not a heading
    # tail (of/from/for/include), and there is no colon.
    for ln in (
        "HIGHLIGHTS RETURN TO POSITIVE COMPARABLE SALES AND TRANSACTIONS IN JUNE",
        "HIGHLIGHTS POSITIVE COMPARABLE SALES",
    ):
        assert not _HIGHLIGHTS_HEADING_RE.search(ln), ln


def test_highlights_heading_prose_and_fragments_do_not_match() -> None:
    # A terminated prose sentence starting "Highlights of ..." is not a
    # heading (the terminator guard), and a flattened-prose fragment
    # starting "highlights based ..." is not one either (the tail-word
    # guard). The batch-97/batch-155 prose negative still holds.
    for ln in (
        "Highlights of the March quarter, including both GAAP and adjusted "
        "metrics, are on page five and incorporated here.",
        "highlights based suggested destinations, recently viewed an "
        "animated tour to explain key Airbnb on guest searches",
        "prepared to highlight and facilitate the discussion (unaudited)",
    ):
        assert not _HIGHLIGHTS_HEADING_RE.search(ln), ln


def test_heading_fragment_carveout_for_highlights_sub_headline() -> None:
    # The ≤4-word all-caps rule drops heading fragments ("QUARTER",
    # "RESULTS FOR THE QUARTER") — but a leading-"Highlights" line
    # that is not a highlights heading is a sub-headline, not a
    # fragment. The real heading shapes still drop.
    assert not _is_lede_heading_fragment("HIGHLIGHTS POSITIVE COMPARABLE SALES")
    assert not _is_lede_heading_fragment(
        "HIGHLIGHTS RETURN TO POSITIVE COMPARABLE SALES AND TRANSACTIONS IN JUNE"
    )
    assert _is_lede_heading_fragment("HIGHLIGHTS OF SEGMENT RESULTS")
    assert _is_lede_heading_fragment("HIGHLIGHTS FROM THE QUARTER")
    assert _is_lede_heading_fragment("HIGHLIGHTS")
    assert _is_lede_heading_fragment("RESULTS FOR THE QUARTER")


def test_cmg_sub_headline_is_served_in_the_lede() -> None:
    # Verbatim CMG Q2 2025 head (contact blocks, headline, sub-headline,
    # dateline, highlights intro, bullets): the sub-headline must be
    # served as the second paragraph, not dropped as a heading.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "2",
            "cmg-20250723xex991.htm",
            "EX-99.1",
            "Exhibit 99.1",
            "EARNINGS RELEASE",
            "PR Contact: Laurie Schalow",
            "(949) 524-4035",
            "MediaRelations@chipotle.com",
            "IR Contact: Cindy Olsen, CFA",
            "(949) 524-4205",
            "Cindy.Olsen@chipotle.com",
            "CHIPOTLE ANNOUNCES SECOND QUARTER 2025 RESULTS",
            "HIGHLIGHTS RETURN TO POSITIVE COMPARABLE SALES AND TRANSACTIONS IN JUNE",
            "NEWPORT BEACH, Calif. – July 23, 2025 – Chipotle Mexican Grill, "
            "Inc. (NYSE: CMG) today reported financial results for its second "
            "quarter ended June 30, 2025.",
            "Second quarter highlights, year over year:",
            "•Total revenue increased 3.0% to $3.1 billion",
            "•Comparable restaurant sales decreased 4.0%",
            "•Operating margin was 18.2%, a decrease from 19.7%",
            "•Restaurant level operating margin was 27.4%, a decrease from 28.9%",
            "•Diluted earnings per share was $0.32, a 3.0% decrease from $0.33",
            "•Opened 61 company-owned restaurants with 47 locations including a Chipotlane",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "CHIPOTLE ANNOUNCES SECOND QUARTER 2025 RESULTS"
    assert (
        "HIGHLIGHTS RETURN TO POSITIVE COMPARABLE SALES AND TRANSACTIONS IN JUNE"
        in hl
    )
    # The sub-headline anchors the Highlights section, so it is served
    # as the section's first line and nothing is truncated by the lede's
    # 6-line budget: all six bullets survive.
    assert hl.split("\n\n")[1].startswith(
        "HIGHLIGHTS RETURN TO POSITIVE COMPARABLE SALES AND TRANSACTIONS IN JUNE"
    )
    assert "Total revenue increased 3.0% to $3.1 billion" in hl
    assert "Opened 61 company-owned restaurants" in hl
    assert "PR Contact" not in hl


def test_cmg_q3_sub_headline_fragment_is_served() -> None:
    # The Q3 2025 fragment ("HIGHLIGHTS POSITIVE COMPARABLE SALES") is
    # the same shape — short, all-caps, no heading tail — and must be
    # served too, not dropped as a heading.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "2",
            "cmg-20251029xex991.htm",
            "EX-99.1",
            "Exhibit 99.1",
            "EARNINGS RELEASE",
            "PR Contact: Laurie Schalow",
            "(949) 524-4035",
            "MediaRelations@chipotle.com",
            "IR Contact: Cindy Olsen, CFA",
            "(949) 524-4205",
            "Cindy.Olsen@chipotle.com",
            "CHIPOTLE ANNOUNCES THIRD QUARTER 2025 RESULTS",
            "HIGHLIGHTS POSITIVE COMPARABLE SALES",
            "NEWPORT BEACH, Calif. – October 29, 2025 – Chipotle Mexican Grill, "
            "Inc. (NYSE: CMG) today reported financial results for its third "
            "quarter ended September 30, 2025.",
            "•Total revenue increased 7.5% to $3.0 billion",
            "•Comparable restaurant sales increased 0.3%",
            "•Operating margin was 15.9%, a decrease from 16.9%",
            "•Restaurant level operating margin was 24.5%, a decrease from 25.5%",
            "•Diluted earnings per share was $0.29, a 3.6% increase from $0.28",
            "•Opened 84 company-owned restaurants, with 64 locations including a Chipotlane",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "CHIPOTLE ANNOUNCES THIRD QUARTER 2025 RESULTS"
    assert "HIGHLIGHTS POSITIVE COMPARABLE SALES" in hl
    assert "Total revenue increased 7.5% to $3.0 billion" in hl
