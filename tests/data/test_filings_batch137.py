"""Batch 137 regression tests: "Income"/"Insurance" headline wrap tails (Chubb).

Chubb's paragraph headlines wrap at arbitrary points, and two more wrap
points stranded tail clauses in stored rows. Q3 2024 wraps after "Net
Investment Income" onto "Both Up Double-Digit; ...", so the tail clause
sat in the body as two orphan paragraphs; Q4 2024 wraps after "Life
Insurance" onto "Up 15.7%; P&C Combined Ratio of 86.6%", and that tail
clause dropped out of the stored text entirely (the old headline stopped
at "Insurance" and the section extractor skipped the orphan line, so the
stored body never contained it).

The fix adds "Insurance" to _HEADLINE_FRAGMENT_TAIL_RE, under the usual
fragment-tail guards. "Income" is narrower: it joins only onto a
"Both"-led continuation, because the old-vs-new blast showed a bare
"Income" tail over-joins genuine headlines — Carnival's "NET INCOME"
headlines are followed by subhead lines ("Accelerates shareholder
returns ...") and PSEG's "$3.54 PER SHARE NET INCOME" by a sibling
metric line ("$3.68 PER SHARE NON-GAAP OPERATING EARNINGS"). The
conjunctive rule (income tail AND both lead) is the whole trigger.
"""

from tickerlens.data.filings import (
    _join_wrapped_headline,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def _cb_q3_2024_html() -> str:
    # Real Q3 2024 headline lines (exhibit 99.1), then the bullet lede.
    # The masthead block is omitted: the test is about the wrap joiner,
    # not the masthead skips.
    return _contact_release_html(
        "Chubb",
        "Reports Third Quarter Per Share Net Income and Core",
        "Operating Income of $5.70 and $5.72, Up 15.2% and 15.6%,",
        "Respectively, with P&C Underwriting and Net Investment Income",
        "Both Up Double-Digit; Global P&C and Life Insurance Net",
        "Premiums Written were Up 8.5% and 10.6%, in Constant Dollars",
        "·",
        "Net income was $2.32 billion, up 13.8%, and core operating income was $2.33 billion, up 14.3%.",
    )


def test_cb_q3_2024_income_wrap_joins_end_to_end() -> None:
    hl = extract_press_release_highlights(_cb_q3_2024_html())
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "Chubb Reports Third Quarter Per Share Net Income and Core "
        "Operating Income of $5.70 and $5.72, Up 15.2% and 15.6%, "
        "Respectively, with P&C Underwriting and Net Investment Income "
        "Both Up Double-Digit; Global P&C and Life Insurance Net "
        "Premiums Written were Up 8.5% and 10.6%, in Constant Dollars"
    )
    # Neither stranded tail paragraph leaks into the body.
    assert "Both Up Double-Digit" not in hl.split("\n\n", 1)[1]
    assert "Premiums Written were Up" not in hl.split("\n\n", 1)[1]


def _cb_q4_2024_html() -> str:
    # Real Q4 2024 headline lines (exhibit 99.1), then the bullet lede.
    return _contact_release_html(
        "Chubb Reports",
        "Fourth Quarter Per Share Net Income and Core",
        "Operating Income of $6.33 and $6.02, Respectively; Consolidated",
        "Net Premiums Written of $12.1 Billion, with Global P&C and Life",
        "Insurance Up 6.7% and 7.6%; P&C Combined Ratio of 85.7%;",
        "Record Full-Year Per Share Net Income of $22.70 and Core",
        "Operating Income of $22.51; Consolidated Net Premiums Written of",
        "$51.5 Billion, Up 8.7%, with Global P&C Up 9.6% and Life Insurance",
        "Up 15.7%; P&C Combined Ratio of 86.6%",
        "QUARTER",
        "●",
        "Net income and core operating income were $2.58 billion and $2.45 billion.",
    )


def test_cb_q4_2024_insurance_wrap_joins_end_to_end() -> None:
    hl = extract_press_release_highlights(_cb_q4_2024_html())
    assert hl is not None
    assert hl.split("\n\n")[0].endswith(
        "with Global P&C Up 9.6% and Life Insurance "
        "Up 15.7%; P&C Combined Ratio of 86.6%"
    )
    # The recovered tail clause is in the headline, not lost.
    assert "Up 15.7%; P&C Combined Ratio of 86.6%" in hl.split("\n\n")[0]


def test_income_tail_joins_both_led_continuation() -> None:
    headline, next_i = _join_wrapped_headline(
        [
            "Chubb Reports Third Quarter Net Investment Income",
            "Both Up Double-Digit; Global P&C and Life Insurance Net",
            "Premiums Written were Up 8.5% and 10.6%, in Constant Dollars",
            "Net income was $2.32 billion, up 13.8%.",
        ],
        0,
    )
    assert headline == (
        "Chubb Reports Third Quarter Net Investment Income "
        "Both Up Double-Digit; Global P&C and Life Insurance Net "
        "Premiums Written were Up 8.5% and 10.6%, in Constant Dollars"
    )
    assert next_i == 3


def test_insurance_tail_joins_up_figure_continuation() -> None:
    headline, next_i = _join_wrapped_headline(
        [
            "Chubb Reports Fourth Quarter Results, with Life Insurance",
            "Up 15.7%; P&C Combined Ratio of 86.6%",
            "Net income and core operating income were $2.58 billion.",
        ],
        0,
    )
    assert headline == (
        "Chubb Reports Fourth Quarter Results, with Life Insurance "
        "Up 15.7%; P&C Combined Ratio of 86.6%"
    )
    assert next_i == 2


def test_income_tail_does_not_join_sentence_terminated_lede() -> None:
    headline, next_i = _join_wrapped_headline(
        [
            "Acme Reports Third Quarter Net Income",
            "Net income rose 10% year over year.",
        ],
        0,
    )
    assert headline == "Acme Reports Third Quarter Net Income"
    assert next_i == 1


def test_income_tail_does_not_join_bullet_lede() -> None:
    # Carnival/PACCAR shape: the headline genuinely ends on "Income"
    # and the bullets below are the body, not a continuation.
    headline, next_i = _join_wrapped_headline(
        [
            "Carnival Reports Second Quarter Revenues, Net Yields and Adjusted Net Income",
            "•Completed the unification of the company's dual-listed structure.",
        ],
        0,
    )
    assert headline.startswith("Carnival Reports")
    assert next_i == 1


def test_insurance_tail_does_not_join_fresh_headline() -> None:
    headline, next_i = _join_wrapped_headline(
        [
            "Acme Reports Growth in Life Insurance",
            "Acme Reports Fourth Quarter Results",
        ],
        0,
    )
    assert headline == "Acme Reports Growth in Life Insurance"
    assert next_i == 1


def test_income_tail_does_not_join_subhead_line() -> None:
    # Carnival shape (blast evidence): the "NET INCOME" headline is
    # complete; the next line is a subhead, not a wrap continuation.
    headline, next_i = _join_wrapped_headline(
        [
            "Carnival Corporation Delivers Record Second Quarter Revenues, Net Yields and Adjusted Net Income",
            "Accelerates shareholder returns, surpassing $450 million in stock repurchases",
            "•Completed the unification of the company's dual-listed structure.",
        ],
        0,
    )
    assert headline == (
        "Carnival Corporation Delivers Record Second Quarter Revenues, "
        "Net Yields and Adjusted Net Income"
    )
    assert next_i == 1


def test_income_tail_does_not_join_sibling_metric_line() -> None:
    # PSEG shape (blast evidence): "$3.54 PER SHARE NET INCOME" is a
    # complete metric headline; the next metric line is its sibling.
    headline, next_i = _join_wrapped_headline(
        [
            "$3.54 PER SHARE NET INCOME",
            "$3.68 PER SHARE NON-GAAP OPERATING EARNINGS",
            "•Settled PSE&G's first electric and gas distribution base rate case.",
        ],
        0,
    )
    assert headline == "$3.54 PER SHARE NET INCOME"
    assert next_i == 1


def test_both_lead_does_not_join_without_income_tail() -> None:
    # The "Both" lead alone is not a trigger: after any other tail it is
    # a lede/subhead line, not a wrap continuation.
    headline, next_i = _join_wrapped_headline(
        [
            "Acme Reports Third Quarter Results",
            "Both segments grew year over year",
            "Net income was $1.0 billion, up 10%.",
        ],
        0,
    )
    assert headline == "Acme Reports Third Quarter Results"
    assert next_i == 1
