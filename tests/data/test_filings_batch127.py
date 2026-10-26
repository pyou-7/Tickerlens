"""Batch 127 regression tests: abbreviated quarter earnings-release
document title.

ExxonMobil's exhibits put the document title after the exhibit marker:
"EXHIBIT 99.1" / "3Q 2024 Earnings Release" / "FOR IMMEDIATE RELEASE
November 1, 2024" / "ExxonMobil Announces Third-Quarter 2024 Results".
The title is short and headline-shaped, so the loop picked it and all 8
XOM quarters stored the document title instead of the real headline.

The skip is deliberately narrow: the line must be exactly "<digit>Q
<year> Earnings Release" (full-line anchored, so JPMorgan's genuine
"JPMORGAN CHASE & CO. EARNINGS RELEASE - THIRD QUARTER 2024 RESULTS"
headlines never match); an exhibit marker must appear within the
previous 3 lines; and the next non-admin line after the title must be
a headline-shaped line carrying a headline verb (announces/reports).
A quarter label with no verb headline after it keeps old behavior.
"""

from tickerlens.data.filings import (
    _is_quarter_earnings_title,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def _xom_q3_html(title: str = "3Q 2024 Earnings Release") -> str:
    return _contact_release_html(
        "EX-99.1",
        "2",
        "f8k3q24991.htm",
        "NEWS RELEASE",
        "EXHIBIT 99.1",
        title,
        "FOR IMMEDIATE RELEASE November 1, 2024",
        "ExxonMobil Announces Third-Quarter 2024 Results",
        "•Improved earnings power from enterprise-wide transformation drove industry-leading third-quarter earnings of $8.6 billion",
        "•Achieved highest liquids production in over 40 years with 3.2 million barrels per day",
        "Results Summary",
        "Financial Highlights",
        "•Year-to-date earnings were $26.1 billion versus $28.4 billion in the same period last year",
        "•Achieved $11.3 billion of cumulative Structural Cost Savings versus 2019",
    )


def test_xom_q3_shaped_release_headline_is_real_title() -> None:
    hl = extract_press_release_highlights(_xom_q3_html())
    assert hl is not None
    assert hl.split("\n\n")[0] == "ExxonMobil Announces Third-Quarter 2024 Results"
    assert "3Q 2024 Earnings Release" not in hl


def test_is_quarter_earnings_title_guards() -> None:
    lines = [
        "EXHIBIT 99.1",
        "3Q 2024 Earnings Release",
        "FOR IMMEDIATE RELEASE November 1, 2024",
        "ExxonMobil Announces Third-Quarter 2024 Results",
    ]
    assert _is_quarter_earnings_title(lines, 1)
    # No exhibit marker before the title: old behavior (title is picked).
    assert not _is_quarter_earnings_title(
        [
            "NEWS RELEASE",
            "3Q 2024 Earnings Release",
            "FOR IMMEDIATE RELEASE November 1, 2024",
            "ExxonMobil Announces Third-Quarter 2024 Results",
        ],
        1,
    )
    # Prose (not a verb headline) after the admin line: old behavior.
    assert not _is_quarter_earnings_title(
        [
            "EXHIBIT 99.1",
            "3Q 2024 Earnings Release",
            "FOR IMMEDIATE RELEASE November 1, 2024",
            "SPRING, Texas – November 1, 2024 – Exxon Mobil Corporation today announced results.",
        ],
        1,
    )
    # Bullets after the title (no verb headline at all): old behavior.
    assert not _is_quarter_earnings_title(
        [
            "EXHIBIT 99.1",
            "3Q 2024 Earnings Release",
            "•Year-to-date earnings were $26.1 billion",
        ],
        1,
    )
    # JPMorgan's genuine headline is not a quarter title at all.
    assert not _is_quarter_earnings_title(
        [
            "EXHIBIT 99.1",
            "JPMORGAN CHASE & CO. EARNINGS RELEASE - THIRD QUARTER 2024 RESULTS",
            "•Reported net income of $12.9 billion",
        ],
        1,
    )
    # A quarter label with no marker and no following headline is kept.
    assert not _is_quarter_earnings_title(["3Q 2024 Earnings Release"], 0)


def test_jpm_shaped_release_keeps_its_headline() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "EXHIBIT 99.1",
            "JPMORGAN CHASE & CO. EARNINGS RELEASE - THIRD QUARTER 2024 RESULTS",
            "•Reported net income of $12.9 billion",
            "•Managed revenue of $43.3 billion",
        )
    )
    assert hl is not None
    assert (
        hl.split("\n\n")[0]
        == "JPMORGAN CHASE & CO. EARNINGS RELEASE - THIRD QUARTER 2024 RESULTS"
    )
