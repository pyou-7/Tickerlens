"""Batch 134 regression tests: subsidiary-list masthead skip.

Cincinnati Financial's exhibits head the release with a flattened
subsidiary table — one line per table row, " n " joining the columns:

    The Cincinnati Insurance Company n The Cincinnati Indemnity Company
    The Cincinnati Casualty Company n The Cincinnati Specialty Underwriters Insurance Company
    The Cincinnati Life Insurance Company n CFC Investment Company n CSU Producer Resources Inc.
    Cincinnati Global Underwriting Ltd. n Cincinnati Global Underwriting Agency Ltd.

ahead of the contact block and the real headline ("Cincinnati Financial
Reports Fourth-Quarter and Full-Year 2024 Results"). The loop picked
the second row as the headline: the first row (71 chars) enters the
company-name masthead branch, but _skip_masthead_block stops at the
second row (not masthead residue), and the second row (90 chars)
escapes that branch's 80-char bound — so it was picked, dragging the
remaining rows, the real headline, and the dateline into the 6-line
lede. All 8 CINF quarters stored a subsidiary line as the headline.

The skip is deliberately narrow: the line must split on " n " into at
least two segments, each ending with a company suffix and within 80
chars — a prose line containing " n " fails the suffix rule, and a real
headline never consists solely of " n "-joined company names.
"""

from tickerlens.data.filings import (
    _is_subsidiary_list,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def _cinf_q4_html() -> str:
    return _contact_release_html(
        "EX-99.1",
        "2",
        "exhibit991q424.htm",
        "EX-99.1",
        "The Cincinnati Insurance Company n The Cincinnati Indemnity Company",
        "The Cincinnati Casualty Company n The Cincinnati Specialty Underwriters Insurance Company",
        "The Cincinnati Life Insurance Company n CFC Investment Company n CSU Producer Resources Inc.",
        "Cincinnati Global Underwriting Ltd. n Cincinnati Global Underwriting Agency Ltd.",
        "Investor Contact: Dennis E. McDaniel, 513-870-2768",
        "CINF-IR@cinfin.com",
        "Media Contact: Betsy E. Ertel, 513-603-5323",
        "Media_Inquiries@cinfin.com",
        "Cincinnati Financial Reports Fourth-Quarter and Full-Year 2024 Results",
        "Cincinnati, February 10, 2025 – Cincinnati Financial Corporation (Nasdaq: CINF) today reported:",
        "•Fourth-quarter 2024 net income of $405 million, or $2.56 per share, compared with $1.183 billion, or $7.50 per share, in the fourth quarter of 2023.",
        "•Full-year 2024 net income of $2.292 billion, or $14.53 per share, compared with $1.843 billion, or $11.66 per share, in 2023.",
    )


def test_cinf_shaped_release_headline_is_real_headline() -> None:
    hl = extract_press_release_highlights(_cinf_q4_html())
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "Cincinnati Financial Reports Fourth-Quarter and Full-Year 2024 Results"
    )
    assert "Cincinnati Casualty Company" not in hl
    assert "Cincinnati Specialty Underwriters" not in hl
    assert "Cincinnati Global Underwriting" not in hl
    assert "Fourth-quarter 2024 net income of $405 million" in hl


def test_is_subsidiary_list_guards() -> None:
    assert _is_subsidiary_list(
        "The Cincinnati Insurance Company n The Cincinnati Indemnity Company"
    )
    assert _is_subsidiary_list(
        "The Cincinnati Life Insurance Company n CFC Investment Company n CSU Producer Resources Inc."
    )
    assert _is_subsidiary_list(
        "Cincinnati Global Underwriting Ltd. n Cincinnati Global Underwriting Agency Ltd."
    )
    # A single company name (no " n ") is a masthead line, not this rule.
    assert not _is_subsidiary_list("The Cincinnati Insurance Company")
    # A prose line containing " n " fails the suffix rule on its segments.
    assert not _is_subsidiary_list(
        "Growth in the n plan for the coming year"
    )
    # One non-company segment breaks the rule.
    assert not _is_subsidiary_list(
        "The Cincinnati Insurance Company n results for the quarter"
    )
    # A real results headline never matches, even with a company mention.
    assert not _is_subsidiary_list(
        "Cincinnati Financial Reports Fourth-Quarter and Full-Year 2024 Results"
    )
    # An over-long segment stays out of the rule.
    assert not _is_subsidiary_list(
        "The Cincinnati Insurance Company n "
        + "A" * 75
        + " Company"
    )
