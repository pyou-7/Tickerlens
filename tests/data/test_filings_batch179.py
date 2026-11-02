"""Batch 179 regression tests: "PR Contact:" / "IR Contact:" role labels.

Chipotle heads every release with a two-block contact head:

    PR Contact: Laurie Schalow
    (949) 524-4035
    MediaRelations@chipotle.com
    IR Contact: Cindy Olsen, CFA
    (949) 524-4205
    Cindy.Olsen@chipotle.com

The old contact regexes only knew the spelled-out roles (media/press/
investor), so neither label matched: the headline loop picked
"PR Contact: Laurie Schalow" as the headline (it is headline-shaped),
and the stored rows open with the contact lines. "PR Contact:" / "IR
Contact:" now match both _CONTACT_LINE_RE and _CONTACT_HEADER_RE, so
the header branch fires, the block skip consumes the phone/email
detail lines, and the real headline is picked.
"""
from tickerlens.data.filings import (
    _CONTACT_HEADER_RE,
    _CONTACT_LINE_RE,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def test_pr_ir_contact_labels_match_contact_regexes() -> None:
    for ln in (
        "PR Contact: Laurie Schalow",
        "IR Contact: Cindy Olsen, CFA",
        "pr contact: Jane Doe",
        "ir contact: John Smith",
    ):
        assert _CONTACT_LINE_RE.search(ln), ln
        assert _CONTACT_HEADER_RE.match(ln), ln


def test_pr_ir_contact_regexes_do_not_match_prose() -> None:
    # "their contact" / "first contact": the "ir" sits mid-word, with
    # no word boundary before it, so the abbreviation branch must not
    # fire. A real headline and a newswire label must not match either.
    for ln in (
        "their contact list",
        "First contact with customers",
        "Please contact our team",
        "PR Newswire",
        "CHIPOTLE ANNOUNCES THIRD QUARTER 2024 RESULTS",
        "Investor day presentation",
    ):
        assert not _CONTACT_LINE_RE.search(ln), ln
        assert not _CONTACT_HEADER_RE.match(ln), ln


def test_cmg_contact_head_is_skipped_and_real_headline_picked() -> None:
    # Verbatim CMG Q3 2024 head: the contact blocks, the real headline,
    # the sub-headline, the dateline, the colon-heading highlights intro
    # (batch 177 drops it) and the first bullets.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "2",
            "cmg-202401029xex991.htm",
            "EX-99.1",
            "Exhibit 99.1",
            "EARNINGS RELEASE",
            "PR Contact: Laurie Schalow",
            "(949) 524-4035",
            "MediaRelations@chipotle.com",
            "IR Contact: Cindy Olsen, CFA",
            "(949) 524-4205",
            "Cindy.Olsen@chipotle.com",
            "CHIPOTLE ANNOUNCES THIRD QUARTER 2024 RESULTS",
            "COMPARABLE SALES INCREASE 6% DRIVEN BY OVER 3% TRANSACTION GROWTH",
            "NEWPORT BEACH, Calif. – October 29, 2024 – Chipotle Mexican Grill, "
            "Inc. (NYSE: CMG) today reported financial results for its third "
            "quarter ended September 30, 2024.",
            "Third quarter highlights, year over year:",
            "•Total revenue increased 13.0% to $2.8 billion",
            "•Comparable restaurant sales increased 6.0%",
            "•Operating margin was 16.9%, an increase from 16.0%",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "CHIPOTLE ANNOUNCES THIRD QUARTER 2024 RESULTS"
    assert "Contact" not in hl
    assert "Schalow" not in hl
    assert "Olsen" not in hl
    assert "chipotle.com" not in hl
    assert "524-4035" not in hl
    assert "524-4205" not in hl
    assert "Total revenue increased 13.0% to $2.8 billion" in hl
    assert "Comparable restaurant sales increased 6.0%" in hl
