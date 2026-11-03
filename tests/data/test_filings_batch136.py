"""Batch 136 regression tests: "for"-led headline continuations (Moody's,
FICO, Kroger, Ross).

Some filers wrap the release headline mid-phrase with the period phrase
leading the second line: "MOODY'S CORPORATION REPORTS RESULTS" / "FOR
THIRD QUARTER 2025", "FICO Announces Earnings of $7.40 per Share" / "for
Third Quarter Fiscal 2025", "... Announces Guidance" / "for 2026". The old
joiner only recognized conjunction-led continuations (batch 107's and/or/
but), so the period phrase was stored as the first body line and the
headline read as if it had no period at all.

The rule is narrow on purpose: a bare "for" lead is not a trigger, because
lede "For ..." lines are common — but they always start "For the ..."
("For the three months ended ...:", "For the full year:") or are admin
lines ("For 6:00 a.m. ET Release"), and a bare-year continuation must
stand alone ("for 2026", not "For 2026, the company expects ...").
"""

from tickerlens.data.filings import (
    _join_wrapped_headline,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def _mco_q3_2025_html() -> str:
    # Real Q3 2025 headline lines (exhibit 99.1), then the lede bullets.
    # The masthead block is omitted: the test is about the wrap joiner,
    # not the masthead skips.
    return _contact_release_html(
        "EX-99.1",
        "Exhibit 99.1",
        "News Release",
        "MOODY'S CORPORATION REPORTS RESULTS",
        "FOR THIRD QUARTER 2025",
        "NEW YORK, NY - October 22, 2025 - Moody's Corporation (NYSE: MCO) today announced results for the third quarter 2025.",
        "●",
        "Moody's Corporation revenue was $2.0 billion, up 12% from the prior year.",
    )


def test_mco_for_quarter_continuation_joins_end_to_end() -> None:
    hl = extract_press_release_highlights(_mco_q3_2025_html())
    assert hl is not None
    assert (
        hl.split("\n\n")[0]
        == "MOODY'S CORPORATION REPORTS RESULTS FOR THIRD QUARTER 2025"
    )
    # No period phrase leaks into the body.
    assert "FOR THIRD QUARTER 2025" not in hl.split("\n\n", 1)[1]


def test_fico_for_quarter_fiscal_continuation_joins() -> None:
    headline, next_i = _join_wrapped_headline(
        [
            "FICO Announces Earnings of $7.40 per Share",
            "for Third Quarter Fiscal 2025",
            "Revenue of $536 million vs. $448 million in prior year",
        ],
        0,
    )
    assert headline == (
        "FICO Announces Earnings of $7.40 per Share "
        "for Third Quarter Fiscal 2025"
    )
    assert next_i == 2


def test_rost_for_quarter_and_fiscal_continuation_joins() -> None:
    headline, next_i = _join_wrapped_headline(
        [
            "ROSS STORES REPORTS RESULTS",
            "FOR FOURTH QUARTER AND FISCAL 2024",
            "DUBLIN, Calif., March 4, 2025 -- Ross Stores, Inc. today reported earnings.",
        ],
        0,
    )
    assert headline == (
        "ROSS STORES REPORTS RESULTS FOR FOURTH QUARTER AND FISCAL 2024"
    )
    assert next_i == 2


def test_kr_for_bare_year_continuation_joins() -> None:
    headline, next_i = _join_wrapped_headline(
        [
            "Kroger Reports Fourth Quarter and Full-Year 2025 Results and Announces Guidance",
            "for 2026",
            "●",
            "Fourth quarter identical sales grew 2.1%.",
        ],
        0,
    )
    assert headline == (
        "Kroger Reports Fourth Quarter and Full-Year 2025 Results "
        "and Announces Guidance for 2026"
    )
    assert next_i == 2


def test_for_lead_guards() -> None:
    # Every line below must NOT join: each is a real stored body-first line
    # shape (Realty Income / Intuit colon-terminated labels, Lowe's admin
    # line, a "For the ..." lede sentence, a "For 2026, ..." outlook
    # sentence) that a bare "for" trigger would have swallowed.
    cases = [
        (
            "REALTY INCOME ANNOUNCES OPERATING RESULTS FOR THE THREE AND NINE MONTHS ENDED SEPTEMBER 30, 2024",
            "For the three months ended September 30, 2024:",
        ),
        (
            "Intuit Reports Strong First Quarter Results and Reiterates Full Year Guidance",
            "For the first quarter, Intuit:",
        ),
        (
            "November 19, 2025",
            "For 6:00 a.m. ET Release",
        ),
        (
            "ACME REPORTS FOURTH QUARTER RESULTS",
            "For the first quarter, revenue grew 10% year over year.",
        ),
        (
            "ACME ANNOUNCES FULL YEAR GUIDANCE",
            "For 2026, the company expects revenue growth of 5%.",
        ),
    ]
    for headline, cont in cases:
        joined, next_i = _join_wrapped_headline(
            [headline, cont, "●", "A bullet lede line."],
            0,
        )
        assert joined == headline, (headline, cont)
        assert next_i == 1, (headline, cont)
