"""Batch 118 regression tests: verb-tail headline + year-led results fragment.

Prudential's 4Q24 release wraps its headline as "Prudential Financial, Inc.
Announces" / "2024 Results". The digit-led bad-start guard refused the join,
stranding "2024 Results" as the first body line — which killed the leading
bullet-block detection, let a "Financial Highlights" table header become the
whole body (<200 chars), and returned highlights None for PRU 2024 Q4.
"""

from tickerlens.data.filings import (
    _join_wrapped_headline,
    _leading_bullet_block,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def test_verb_tail_year_results_joins() -> None:
    lines = [
        "Prudential Financial, Inc. Announces",
        "2024 Results",
        "NEWARK, N.J. -- the lede starts here with a period.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "Prudential Financial, Inc. Announces 2024 Results"
    assert next_i == 2


def test_verb_tail_year_results_ignores_complete_headline() -> None:
    # No verb tail: a complete headline is never glued to a year-Results line.
    lines = [
        "Acme Reports Third Quarter Results",
        "2024 Results",
        "Net income was strong this quarter.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "Acme Reports Third Quarter Results"
    assert next_i == 1


def test_verb_tail_bare_year_still_not_joined() -> None:
    # The bypass is for "YYYY Results" only — a bare year after a verb tail
    # still does not join.
    lines = [
        "Acme Corp Announces",
        "2026",
        "Net income was strong this quarter.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "Acme Corp Announces"
    assert next_i == 1


def test_dateline_sentence_before_bullets_still_leading_block() -> None:
    # Batch 118: Prudential puts the dateline sentence between the headline
    # and the bullets; the block must still be found.
    lines = [
        "NEWARK, N.J. – Prudential Financial, Inc. (NYSE: PRU) today reported "
        "second quarter 2026 results.",
        "•Net income of $985 million or $2.80 per Common share versus $533 million.",
        "•After-tax adjusted operating income of $1.438 billion or $4.08 per share.",
        "•Book value per Common share of $90.50 versus $85.98 for the year-ago quarter.",
    ]
    block = _leading_bullet_block(lines)
    assert block is not None
    assert len(block) == 3
    assert block[0].startswith("•Net income")


def test_dateline_sentence_without_bullets_is_not_a_block() -> None:
    # Guard: a dateline sentence followed by prose (no bullets) still yields
    # no leading block — the skip must not invent one.
    lines = [
        "NEWARK, N.J. – Prudential Financial, Inc. today reported results.",
        "Net income was $985 million for the quarter.",
    ]
    assert _leading_bullet_block(lines) is None


def test_pru_2q26_shaped_release_bullets_beat_table_header() -> None:
    # Batch 118: headline + dateline sentence + bullets + a "Financial
    # Highlights" table later in the document. The bullets must win; the
    # table header must not become the body.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "Exhibit 99.1",
            "August 4, 2026",
            "Prudential Financial, Inc. Announces",
            "Second Quarter 2026 Results",
            "NEWARK, N.J. – Prudential Financial, Inc. (NYSE: PRU) today "
            "reported second quarter 2026 results.",
            "•Net income attributable to Prudential Financial, Inc. of $985 "
            "million or $2.80 per Common share versus net income of $533 million.",
            "•After-tax adjusted operating income of $1.438 billion or $4.08 "
            "per Common share versus $1.284 billion for the year-ago quarter.",
            "•Book value per Common share of $90.50 versus $85.98 per share "
            "for the year-ago quarter.",
            "Financial Highlights",
            "(in millions, unaudited)",
            "Three Months Ended Six Months Ended",
            "June 30, June 30,",
            "2026 2025 2026 2025",
            "Adjusted operating income (loss) before income taxes (1):",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "Prudential Financial, Inc. Announces Second Quarter 2026 Results"
    )
    assert "$985 million" in hl
    assert "(in millions, unaudited)" not in hl


def test_pru_shaped_release_extracts_headline_and_bullets() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "Exhibit 99.1",
            "February 4, 2025",
            "Prudential Financial, Inc. Announces",
            "2024 Results",
            "•2024 net income attributable to Prudential Financial, Inc. of $2.727 "
            "billion or $7.50 per Common share versus $2.488 billion for 2023.",
            "•2024 after-tax adjusted operating income of $4.588 billion or $12.62 "
            "per Common share versus $4.380 billion for 2023.",
            "•Fourth quarter 2024 net loss of $57 million or $0.17 per Common share "
            "versus net income of $1.317 billion for the year-ago quarter.",
            "NEWARK, N.J. -- Prudential Financial, Inc. today reported year-end "
            "and fourth quarter 2024 results.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Prudential Financial, Inc. Announces 2024 Results"
    assert "$2.727 billion" in hl
    assert "Financial Highlights" not in hl.split("\n\n")[0]
