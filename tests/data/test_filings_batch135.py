"""Batch 135 regression tests: fragment-tail headline wraps (Chubb/CB).

Chubb's release headline is a whole paragraph wrapped at arbitrary points,
and the wrap lands mid-phrase on a word that cannot end a complete headline
— a modifier awaiting its head noun ("Net Income and Core" / "Operating
Income", "P&C Up 10.6% and Life" / "Insurance", "Respectively;
Consolidated" / "Net Premiums Written", "P&C Combined" / "Ratio") or the
preposition "Up" awaiting its figure ("Net Income of $7.35, Up" / "34.6%").
The old joiner only recognized conjunction/preposition, verb, ordinal,
and year tails, so it stored the first line ("Chubb Reports Second
Quarter Per Share Net Income and Core") as the headline and left the
rest of the headline paragraph as body lines. The Q2 2024 paragraph wraps
8 times, so the join cap rises from 3 to 12 — every join still requires
a trigger plus all continuation guards.

Guard negatives hold the line: a fragment tail followed by a
sentence-terminated lede never joins; a digit-led line after a verb or
ordinal tail is still refused (metric-table rows, not completions); a
bullet after a fragment tail still stops the chain.
"""

from tickerlens.data.filings import (
    _join_wrapped_headline,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def _cb_q2_2024_html() -> str:
    # Real Q2 2024 headline paragraph lines (exhibit 99.1), then the
    # bullet lede. The masthead/address block is omitted: the test is
    # about the wrap joiner, not the masthead skips.
    return _contact_release_html(
        "EX-99.1",
        "Exhibit 99.1",
        "News Release",
        "Chubb Reports Second Quarter Per Share Net Income and Core",
        "Operating Income of $5.46 and $5.38, Up 26.4% and 9.3%,",
        "Respectively; Consolidated Net Premiums Written of $13.4 Billion,",
        "Up 11.8%, or 12.3% in Constant Dollars, with P&C Up 10.6% and Life",
        "Insurance Up 27.6%; P&C Combined Ratio of 86.8%;",
        "Record Year-to-Date Per Share Net Income and Core",
        "Operating",
        "Income of $10.68 and $10.78, Up 20.8% and 15.7%, Respectively",
        "●",
        "Net income was $2.23 billion, up 24.3%, and core operating income was $2.20 billion, up 7.5%.",
    )


def test_cb_q2_2024_headline_paragraph_joins_fully() -> None:
    hl = extract_press_release_highlights(_cb_q2_2024_html())
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "Chubb Reports Second Quarter Per Share Net Income and Core "
        "Operating Income of $5.46 and $5.38, Up 26.4% and 9.3%, "
        "Respectively; Consolidated Net Premiums Written of $13.4 Billion, "
        "Up 11.8%, or 12.3% in Constant Dollars, with P&C Up 10.6% and Life "
        "Insurance Up 27.6%; P&C Combined Ratio of 86.8%; "
        "Record Year-to-Date Per Share Net Income and Core "
        "Operating Income of $10.68 and $10.78, Up 20.8% and 15.7%, Respectively"
    )
    # No headline-continuation line leaks into the body.
    assert "Operating Income of $5.46" not in hl.split("\n\n", 1)[1]


def test_fragment_tail_joins_up_percentage_continuation() -> None:
    # "Up" fragment + digit-led percentage line: the figure completing
    # the fragment, which the digit-led bad-start guard used to refuse.
    headline, next_i = _join_wrapped_headline(
        [
            "Chubb Reports Second Quarter Per Share Net Income of $7.35, Up",
            "34.6%, and Record Per Share Core Operating Income of $6.14, Up",
            "14.1%; Consolidated Net Premiums Written of $14.2 Billion, Up",
            "6.3%, or 7.1% in Constant Dollars, with P&C and Life Insurance Up",
            "5.8% and 17.3%, Respectively; P&C Combined Ratio of 85.6%",
            "●",
        ],
        0,
    )
    assert headline == (
        "Chubb Reports Second Quarter Per Share Net Income of $7.35, Up "
        "34.6%, and Record Per Share Core Operating Income of $6.14, Up "
        "14.1%; Consolidated Net Premiums Written of $14.2 Billion, Up "
        "6.3%, or 7.1% in Constant Dollars, with P&C and Life Insurance Up "
        "5.8% and 17.3%, Respectively; P&C Combined Ratio of 85.6%"
    )
    assert next_i == 5


def test_fragment_tail_guards() -> None:
    # Sentence-terminated lede after a fragment tail: no join.
    headline, next_i = _join_wrapped_headline(
        [
            "Acme Reports Record",
            "Net income was 5.2 billion dollars, up 8 percent year over year.",
        ],
        0,
    )
    assert headline == "Acme Reports Record"
    assert next_i == 1
    # Digit-led line after a verb tail: still refused (metric-table row).
    headline, next_i = _join_wrapped_headline(
        ["Acme Reports", "20% growth in the quarter"],
        0,
    )
    assert headline == "Acme Reports"
    assert next_i == 1
    # Bullet after a fragment tail: the chain stops.
    headline, next_i = _join_wrapped_headline(
        [
            "Chubb Reports Second Quarter Per Share Net Income and Core",
            "• Operating income rose sharply",
        ],
        0,
    )
    assert headline == "Chubb Reports Second Quarter Per Share Net Income and Core"
    assert next_i == 1
    # A complete headline ending on a fragment-adjacent word that is a
    # real noun ("Growth") is untouched.
    headline, next_i = _join_wrapped_headline(
        [
            "Acme Reports Record Growth",
            "CUPERTINO, California — the lede starts here with a period.",
        ],
        0,
    )
    assert headline == "Acme Reports Record Growth"
    assert next_i == 1


def test_fragment_tail_does_not_swallow_fresh_headline() -> None:
    # Danaher: the cover slogan ends on a fragment word ("life"), but the
    # next line is the real headline — joining would build a
    # Franken-headline, so the slogan stays exactly as stored today.
    headline, next_i = _join_wrapped_headline(
        [
            "Innovation at the speed of life",
            "Danaher Reports Third Quarter 2024 Results",
            "WASHINGTON -- the lede starts here with a period.",
        ],
        0,
    )
    assert headline == "Innovation at the speed of life"
    assert next_i == 1
    # The block applies to fragment tails only: a wrap-comma join into a
    # verb-led continuation (Merck's company-name wrap) still joins.
    headline, next_i = _join_wrapped_headline(
        [
            "Merck & Co., Inc., Rahway, N.J.,",
            "USA Announces Second-Quarter 2025 Financial Results",
            "RAHWAY, N.J. -- the lede starts here with a period.",
        ],
        0,
    )
    assert headline == (
        "Merck & Co., Inc., Rahway, N.J., USA Announces "
        "Second-Quarter 2025 Financial Results"
    )
    assert next_i == 2
