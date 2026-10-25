"""Batch 124 regression tests: compound earnings-release document title.

lululemon's Q3 releases combine the earnings release with a stock-repurchase
announcement in one 8-K, so the exhibit's document title ("EARNINGS RELEASE
& STOCK REPURCHASE PROGRAM") sits before "Exhibit 99.1" while the real
release headline follows it. The bare "EARNINGS RELEASE" title was already
skipped (which is why Q4 was fine), but the compound form was picked as the
headline — so both Q3 quarters stored the document title instead of
"LULULEMON ATHLETICA INC. ANNOUNCES THIRD QUARTER FISCAL ... RESULTS".

The skip is deliberately narrow: the title must carry "earnings release"
followed by "&"/"and", an exhibit marker must appear within 2 lines, and
the line after the marker must be a verb-led headline. That keeps
JPMorgan's stored headline safe (its title is also followed by a marker,
but the line after the marker is the company name/address block, not a
verb headline) and XOM's ("3Q 2025 Earnings Release", preceded by its
marker) untouched.
"""

from tickerlens.data.filings import (
    _is_compound_earnings_title,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def _lulu_q3_html(title: str) -> str:
    return _contact_release_html(
        "EX-99.1",
        "2",
        "lulu-20241027xex991.htm",
        title,
        "Exhibit 99.1",
        "LULULEMON ATHLETICA INC. ANNOUNCES THIRD QUARTER FISCAL 2024 RESULTS",
        "BOARD OF DIRECTORS AUTHORIZES $1.0 BILLION INCREASE IN ITS STOCK REPURCHASE PROGRAM",
        "Revenue increased 9% to $2.4 billion",
        "Comparable sales increased 4%, or 3% on a constant dollar basis",
        "Diluted EPS of $2.87",
        "Balance Sheet Highlights",
        "The Company ended the third quarter of 2024 with $1.2 billion in cash and cash equivalents.",
    )


def test_lulu_q3_shaped_release_headline_is_real_title() -> None:
    hl = extract_press_release_highlights(
        _lulu_q3_html("EARNINGS RELEASE & STOCK REPURCHASE PROGRAM")
    )
    assert hl is not None
    assert (
        hl.split("\n\n")[0]
        == "LULULEMON ATHLETICA INC. ANNOUNCES THIRD QUARTER FISCAL 2024 RESULTS"
    )
    assert "EARNINGS RELEASE & STOCK REPURCHASE PROGRAM" not in hl


def test_compound_title_and_form_is_skipped() -> None:
    hl = extract_press_release_highlights(
        _lulu_q3_html("EARNINGS RELEASE AND STOCK REPURCHASE PROGRAM")
    )
    assert hl is not None
    assert (
        hl.split("\n\n")[0]
        == "LULULEMON ATHLETICA INC. ANNOUNCES THIRD QUARTER FISCAL 2024 RESULTS"
    )


def test_is_compound_earnings_title_guards() -> None:
    lines = [
        "EARNINGS RELEASE & STOCK REPURCHASE PROGRAM",
        "Exhibit 99.1",
        "LULULEMON ATHLETICA INC. ANNOUNCES THIRD QUARTER FISCAL 2024 RESULTS",
    ]
    assert _is_compound_earnings_title(lines, 0)
    # No exhibit marker after the title: old behavior (title is picked).
    assert not _is_compound_earnings_title(
        [
            "EARNINGS RELEASE & STOCK REPURCHASE PROGRAM",
            "LULULEMON ATHLETICA INC. ANNOUNCES THIRD QUARTER FISCAL 2024 RESULTS",
        ],
        0,
    )
    # Marker after the title but prose (not a verb headline) after the
    # marker: old behavior.
    assert not _is_compound_earnings_title(
        [
            "EARNINGS RELEASE & STOCK REPURCHASE PROGRAM",
            "Exhibit 99.1",
            "Vancouver, British Columbia, December 5, 2024, lululemon athletica inc. today announced results",
        ],
        0,
    )
    # Bare label is not a compound title (handled by the label branch).
    assert not _is_compound_earnings_title(
        ["EARNINGS RELEASE", "Exhibit 99.1", "ACME ANNOUNCES RESULTS"], 0
    )
    # Dash-joined results title (JPMorgan shape) is not a compound title.
    assert not _is_compound_earnings_title(
        [
            "JPMORGAN CHASE & CO. EARNINGS RELEASE - THIRD QUARTER 2025 RESULTS",
            "Exhibit 99.1",
            "JPMorgan Chase & Co.",
        ],
        0,
    )


def test_jpm_shaped_title_keeps_its_headline() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "2",
            "a3q25erfexhibit991narrative.htm",
            "JPMORGAN CHASE & CO. EARNINGS RELEASE - THIRD QUARTER 2025 RESULTS",
            "Exhibit 99.1",
            "JPMorgan Chase & Co.",
            "383 Madison Avenue, New York, NY 10179-0001",
            "JPMORGANCHASE REPORTS THIRD-QUARTER 2025 NET INCOME OF $14.4 BILLION",
            "ROE 17%",
            "ROTCE 20%",
        )
    )
    assert hl is not None
    assert (
        hl.split("\n\n")[0]
        == "JPMORGAN CHASE & CO. EARNINGS RELEASE - THIRD QUARTER 2025 RESULTS"
    )
