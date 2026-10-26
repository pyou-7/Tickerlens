"""Batch 130 regression tests: deck-title page as headline.

U.S. Bancorp's exhibits are slide decks headed by a title page,
"<NQ>YY Key Financial Data", with the highlights section heading
("<NQ>YY (Financial) Highlights") immediately after it. The loop
picked the title page, so all 8 USB quarters stored a deck-section
title ("3Q24 Key Financial Data") instead of the highlights heading
the bullets belong to.

The fix is deliberately narrow: the title line is skipped only when
the next line is a highlights heading, and the body starts AT that
heading so the section extractor still finds its content — without
the body_start-at-heading, the section anchor is lost and the body
would fall back to a later business section, losing the financial
bullets. The title shape is also added to the never-headline set as
a backstop for decks where no highlights heading follows it.
"""

from tickerlens.data.filings import (
    _DECK_KEY_FINANCIAL_DATA_RE,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def _usb_q3_html() -> str:
    return _contact_release_html(
        "EX-99.1",
        "2",
        "a3q24earningsrelease.htm",
        "EX-99.1",
        "3Q24 Key Financial Data",
        "3Q24 Highlights",
        "PROFITABILITY METRICS 3Q24 2Q24 3Q23 •Net income of $1,714 million and diluted earnings per common share of $1.03",
        "•Net interest income on a taxable-equivalent basis increased 2.8% on a linked quarter basis",
        "•Net revenue of $6,864 million, including $4,166 million of net interest income on a taxable-equivalent basis",
    )


def test_usb_q3_deck_title_is_not_the_headline() -> None:
    hl = extract_press_release_highlights(_usb_q3_html())
    assert hl is not None
    assert hl.split("\n\n")[0] == "3Q24 Highlights"
    assert "Key Financial Data" not in hl
    assert "Net income of $1,714 million" in hl
    assert "Net revenue of $6,864 million" in hl


def test_usb_q2_2026_financial_highlights_heading_is_the_headline() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "2",
            "a2q26earningsrelease.htm",
            "EX-99.1",
            "2Q26 Key Financial Data",
            "2Q26 Financial Highlights",
            "PROFITABILITY METRICS",
            "2Q26",
            "1Q26",
            "2Q25",
            "•Record net revenue of $7,712 million, including year-over-year increases of 7.5% in net interest income",
            "•Net income of $2,177 million, an increase of 20% year-over-year",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "2Q26 Financial Highlights"
    assert "Key Financial Data" not in hl
    assert "Record net revenue of $7,712 million" in hl


def test_deck_title_without_following_highlights_heading_is_skipped() -> None:
    # Backstop: a deck title with no highlights heading after it is
    # never the headline either; the next line becomes the pick.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "3Q24 Key Financial Data",
            "CEO Commentary",
            "In the third quarter, we reported diluted earnings per share of $1.03 and a return on tangible common equity of 17.9%.",
        )
    )
    assert hl is not None
    assert "Key Financial Data" not in hl.split("\n\n")[0]


def test_deck_key_financial_data_regex_guards() -> None:
    for title in ("3Q24 Key Financial Data", "4Q24 Key Financial Data", "1Q26 Key Financial Data"):
        assert _DECK_KEY_FINANCIAL_DATA_RE.match(title), title
    # Lam Research's prose heading is a different shape and is untouched.
    assert not _DECK_KEY_FINANCIAL_DATA_RE.match(
        "Key Financial Data for the Quarters Ended"
    )
    # Trailing words, spelled-out quarters, and bad quarter digits are out.
    assert not _DECK_KEY_FINANCIAL_DATA_RE.match("3Q24 Key Financial Data and more")
    assert not _DECK_KEY_FINANCIAL_DATA_RE.match("Q2 2026 Key Financial Data")
    assert not _DECK_KEY_FINANCIAL_DATA_RE.match("5Q24 Key Financial Data")
    # The highlights heading itself is not the title shape.
    assert not _DECK_KEY_FINANCIAL_DATA_RE.match("3Q24 Financial Highlights")
