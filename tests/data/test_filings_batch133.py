"""Batch 133 regression tests: address dateline skip.

M&T Bank's exhibits head the release with an address dateline on one
line — "One M&T Plaza, Buffalo, NY 14203 July 15, 2026" — ahead of the
real headline ("M&T Bank Corporation (NYSE:MTB) announces second
quarter 2026 results"). The loop picked the dateline because no skip
matched it: 49 chars (over the 48-char masthead-residue bound, 9 words
over the 4-word guard), ending with a date rather than a dash (so
_DATELINE_RE misses it), and not starting with a date (so _DATE_LINE_RE
misses it). All 8 MTB quarters stored the dateline as the headline.

The skip is deliberately narrow: the line must end with "<ZIP> <full
month date>" — a genuine headline never does — and stay within 120
chars, so a prose sentence that happens to end with a ZIP+date is not
swallowed.
"""

from tickerlens.data.filings import (
    _is_address_dateline,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def _mtb_q2_html(dateline: str = "One M&T Plaza, Buffalo, NY 14203 July 15, 2026") -> str:
    return _contact_release_html(
        "EX-99.1",
        "2",
        "ex991release2q26.htm",
        "Exhibit 99.1",
        "News Release",
        dateline,
        "M&T Bank Corporation (NYSE:MTB) announces second quarter 2026 results",
        'M&T Bank Corporation ("M&T" or "the Company") reports quarterly net income of $818 million or $5.32 of diluted earnings per common share.',
        "Financial Highlights",
        "•Taxable-equivalent net interest income increased $41 million in the recent quarter.",
        "•Average loans in the recent quarter reflect higher average balances.",
    )


def test_mtb_q2_shaped_release_headline_is_real_headline() -> None:
    hl = extract_press_release_highlights(_mtb_q2_html())
    assert hl is not None
    assert hl.split("\n\n")[0].startswith(
        "M&T Bank Corporation (NYSE:MTB) announces second quarter 2026 results"
    )
    assert "One M&T Plaza" not in hl
    assert "Buffalo, NY 14203" not in hl
    assert "Taxable-equivalent net interest income increased $41 million" in hl


def test_mtb_abbreviated_month_dateline_is_skipped() -> None:
    hl = extract_press_release_highlights(
        _mtb_q2_html("One M&T Plaza, Buffalo, NY 14203 Jul. 15, 2026")
    )
    assert hl is not None
    assert hl.split("\n\n")[0].startswith(
        "M&T Bank Corporation (NYSE:MTB) announces second quarter 2026 results"
    )
    assert "One M&T Plaza" not in hl


def test_is_address_dateline_guards() -> None:
    assert _is_address_dateline("One M&T Plaza, Buffalo, NY 14203 July 15, 2026")
    assert _is_address_dateline("One M&T Plaza, Buffalo, NY 14203 Jul. 15, 2026")
    # ZIP+4 is still an address dateline.
    assert _is_address_dateline("One M&T Plaza, Buffalo, NY 14203-1234 July 15, 2026")
    # No ZIP: a city+date line is a different shape, not this rule.
    assert not _is_address_dateline("Buffalo, NY July 15, 2026")
    # No date: a bare address line is a different shape, not this rule.
    assert not _is_address_dateline("One M&T Plaza, Buffalo, NY 14203")
    # A genuine results headline never ends with a ZIP+date.
    assert not _is_address_dateline(
        "M&T Bank Corporation (NYSE:MTB) announces second quarter 2026 results"
    )
    # Date mid-line (not ending the line) is untouched.
    assert not _is_address_dateline(
        "One M&T Plaza, Buffalo, NY 14203 July 15, 2026 - M&T reports results"
    )
    # A prose sentence that happens to end with a ZIP+date but runs long
    # stays out of the rule.
    assert not _is_address_dateline(
        "The Company's headquarters at One M&T Plaza, Buffalo, NY 14203 were "
        "opened on a sunny morning in the city of Buffalo, NY 14203 July 15, 2026"
    )
