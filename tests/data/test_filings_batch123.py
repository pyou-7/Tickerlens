"""Batch 123 regression tests: flattened two-column contact table as headline.

Akamai's Q4 releases (full-year) put the contact table BEFORE the title,
while Q1-Q3 put the title first — so both Q4 quarters stored contact names
as their headline ("Christine Simeone Mark Stoutenberg",
"Johanna Schmitt Mark Stoutenberg"), with the role row, the doubled company
row, and the real (wrapped) headline polluting the body. The names row is
4 words and headline-shaped, so no existing skip caught it.
"""

from tickerlens.data.filings import (
    _CONTACT_HEADER_RE,
    _is_repeated_phrase,
    _skip_contact_table,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def test_akam_q4_shaped_release_headline_is_real_title() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Christine Simeone Mark Stoutenberg",
            "Media Relations Investor Relations",
            "Akamai Technologies Akamai Technologies",
            "AKAMAI REPORTS FOURTH QUARTER 2024 AND",
            "FULL-YEAR 2024 FINANCIAL RESULTS",
            "Fourth quarter highlights",
            "•Revenue of $1.020 billion, up 3% year-over-year and when adjusted for foreign exchange.",
            "•Diluted EPS of $0.91, up 12% year-over-year on a reported basis.",
            "•Cash flow from operations of $400 million for the quarter.",
        )
    )
    assert hl is not None
    assert (
        hl.split("\n\n")[0]
        == "AKAMAI REPORTS FOURTH QUARTER 2024 AND FULL-YEAR 2024 FINANCIAL RESULTS"
    )
    assert "Christine Simeone" not in hl
    assert "Media Relations Investor Relations" not in hl
    assert "Akamai Technologies Akamai Technologies" not in hl


def test_doubled_role_row_is_contact_header() -> None:
    assert _CONTACT_HEADER_RE.match("Media Relations Investor Relations")
    assert _CONTACT_HEADER_RE.match("Investor Relations Media Relations")


def test_is_repeated_phrase() -> None:
    assert _is_repeated_phrase("Akamai Technologies Akamai Technologies")
    assert _is_repeated_phrase("Acme Acme")
    assert not _is_repeated_phrase("Akamai Technologies Inc.")
    assert not _is_repeated_phrase("Akamai Reports Fourth Quarter Results")
    assert not _is_repeated_phrase("Acme")


def test_skip_contact_table_returns_headline_index() -> None:
    lines = [
        "Christine Simeone Mark Stoutenberg",
        "Media Relations Investor Relations",
        "Akamai Technologies Akamai Technologies",
        "AKAMAI REPORTS FOURTH QUARTER 2024 AND",
        "FULL-YEAR 2024 FINANCIAL RESULTS",
    ]
    assert _skip_contact_table(lines, 0) == 3


def test_skip_contact_table_ignores_verb_headline() -> None:
    # A genuine headline contains a headline word, so it is never treated
    # as a names row even when a role-label line follows it.
    lines = [
        "Acme Reports Third Quarter Results",
        "Media Relations Investor Relations",
        "Acme Corporation Acme Corporation",
        "Something else entirely here.",
    ]
    assert _skip_contact_table(lines, 0) is None


def test_skip_contact_table_requires_headline_ahead() -> None:
    # Names row + role row but no headline-shaped line within the table
    # window: body sentences end with periods, so nothing is skipped and
    # the original behavior holds.
    lines = [
        "Christine Simeone Mark Stoutenberg",
        "Media Relations Investor Relations",
        "Akamai Technologies Akamai Technologies",
        "Net income was strong this quarter.",
        "Revenue grew year over year.",
    ]
    assert _skip_contact_table(lines, 0) is None


def test_skip_contact_table_requires_role_row() -> None:
    lines = [
        "Christine Simeone Mark Stoutenberg",
        "Some other line here today",
        "AKAMAI REPORTS FOURTH QUARTER 2024 AND",
        "FULL-YEAR 2024 FINANCIAL RESULTS",
    ]
    assert _skip_contact_table(lines, 0) is None
