"""Batch 155 regression tests: mixed-case dateline before the leading
bullets.

Alphabet's dateline is "MOUNTAIN VIEW, Calif. – February 4, 2025 – ..." —
the mixed-case state ("Calif.") never matched _DATELINE_LEAD_RE, which
required all-caps location segments, so _leading_bullet_block broke at the
dateline and returned None. Q1–Q3 still served (the lede fallback collects
dateline + bullets), but Q4's "Q4 2024 Financial Highlights" table section
was the only section candidate and won by the earliest-candidate rule,
serving table scaffolding ("The following table summarizes..." + the period
header) instead of the five real bullets.
"""

from tickerlens.data.filings import (
    _HIGHLIGHTS_HEADING_RE,
    _leading_bullet_block,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

_GOOGL_Q4_DATELINE = (
    "MOUNTAIN VIEW, Calif. – February 4, 2025 – Alphabet Inc. (NASDAQ: GOOG, "
    "GOOGL) today announced financial results for the quarter and fiscal year "
    "ended December 31, 2024."
)
_GOOGL_Q4_BULLETS = [
    "•Consolidated Alphabet revenues in Q4 2024 increased 12% year over year "
    "to $96.5 billion reflecting robust momentum across the business.",
    "•Google Services revenues increased 10% to $84.1 billion, reflecting the "
    "strong momentum across Google Search & other and YouTube ads.",
    "•Google Cloud revenues increased 30% to $12.0 billion led by growth in "
    "Google Cloud Platform (GCP) across core GCP products, AI Infrastructure, "
    "and Generative AI Solutions.",
    "•Total operating income increased 31% and operating margin expanded by 5% "
    "percentage points to 32%.",
    "•Net income increased 28% and EPS increased 31% to $2.15.",
]
_GOOGL_Q4_QUOTE = (
    "Sundar Pichai, CEO, said: “Q4 was a strong quarter driven by our "
    "leadership in AI and momentum across the business. We expect to invest "
    "approximately $75 billion in capital expenditures in 2025.”"
)


def test_mixed_case_dateline_before_bullets_still_leading_block() -> None:
    # Batch 155: "MOUNTAIN VIEW, Calif. – ..." must skip like the all-caps
    # "NEWARK, N.J. – ..." dateline in batch 118.
    block = _leading_bullet_block(
        [_GOOGL_Q4_DATELINE, *_GOOGL_Q4_BULLETS, _GOOGL_Q4_QUOTE]
    )
    assert block is not None
    assert len(block) == 6  # 5 bullets + the CEO quote as the last item's tail
    assert block[0].startswith("•Consolidated Alphabet revenues")
    assert "MOUNTAIN VIEW" not in "\n".join(block)


def test_lowercase_state_dateline_is_not_a_dateline_lead() -> None:
    # Boundary: the state segment must still start with a capital — a
    # lowercase-led second segment is not a dateline, so the block is None.
    lines = [
        "MOUNTAIN VIEW, calif. – February 4, 2025 – Alphabet Inc. today "
        "announced results.",
        "•Consolidated Alphabet revenues increased 12% to $96.5 billion.",
    ]
    assert _leading_bullet_block(lines) is None


def test_digit_led_second_segment_is_not_a_dateline_lead() -> None:
    # Boundary: no digits in the location class — "Results, Q4 – ..." is
    # prose, not a dateline, so the block is None.
    lines = [
        "Results, Q4 – the quarter was strong across the business.",
        "•Consolidated Alphabet revenues increased 12% to $96.5 billion.",
    ]
    assert _leading_bullet_block(lines) is None


def test_googl_q4_shaped_release_bullets_beat_table_section() -> None:
    # Batch 155: headline + mixed-case dateline + bullets + quote, then a
    # "Q4 2024 Financial Highlights" table. The bullets must win; the table
    # intro and period header must not become the body.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "Exhibit 99.1",
            "February 4, 2025",
            "Alphabet Announces Fourth Quarter and Fiscal Year 2024 Results",
            _GOOGL_Q4_DATELINE,
            *_GOOGL_Q4_BULLETS,
            _GOOGL_Q4_QUOTE,
            "Q4 2024 Financial Highlights",
            "The following table summarizes our consolidated financial results "
            "for the quarter and fiscal year ended December 31, 2023 and 2024 "
            "(in millions, except for per share information and percentages).",
            "Quarter Ended December 31, Year Ended December 31,",
            "2023 2024 2023 2024",
            "Revenues $ 86,310 $ 96,469 $ 307,394 $ 350,018",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "Alphabet Announces Fourth Quarter and Fiscal Year 2024 Results"
    )
    assert "• Consolidated Alphabet revenues in Q4 2024 increased 12%" in hl
    assert "• Net income increased 28% and EPS increased 31% to $2.15." in hl
    assert "Sundar Pichai" in hl
    assert "The following table summarizes" not in hl
    assert "Quarter Ended December 31" not in hl
    assert "Revenues $ 86,310" not in hl


def test_googl_q3_shaped_release_keeps_bullets_without_dateline() -> None:
    # The same shape in a Q3 release (no fiscal-year table): the leading
    # block serves the bullets + quote, and the boilerplate dateline drops
    # out instead of consuming a lede line.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "Exhibit 99.1",
            "October 29, 2025",
            "Alphabet Announces Third Quarter 2025 Results",
            "MOUNTAIN VIEW, Calif. – October 29, 2025 – Alphabet Inc. (NASDAQ: "
            "GOOG, GOOGL) today announced financial results for the quarter "
            "ended September 30, 2025.",
            "•Consolidated Alphabet revenues in Q3 2025 increased 16%, or 15% "
            "in constant currency, year over year to $102.3 billion.",
            "•Google Services revenues increased 14% to $87.1 billion.",
            "Sundar Pichai, CEO, said: “Q3 was a strong quarter.”",
            "Q3 2025 Financial Highlights",
            "The following table summarizes our consolidated financial results "
            "for the quarters ended September 30, 2024 and 2025.",
            "Quarter Ended September 30,",
            "2024 2025",
            "Revenues $ 88,268 $ 102,346",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Alphabet Announces Third Quarter 2025 Results"
    assert "• Consolidated Alphabet revenues in Q3 2025 increased 16%" in hl
    assert "Sundar Pichai" in hl
    assert "MOUNTAIN VIEW" not in hl
    assert "The following table summarizes" not in hl


def test_highlights_heading_with_unaudited_suffix_matches() -> None:
    # Batch 155: "Q1 2025 Financial Highlights (unaudited)" is a heading —
    # the trailing parenthetical must not defeat the closing-word rule.
    assert _HIGHLIGHTS_HEADING_RE.search(
        "Q1 2025 Financial Highlights (unaudited)"
    )
    assert _HIGHLIGHTS_HEADING_RE.search("Selected Revenue Highlights")
    # The batch-97 guard still holds: a mid-sentence "highlight" verb is
    # not a heading, parenthetical or not.
    assert not _HIGHLIGHTS_HEADING_RE.search(
        "prepared to highlight and facilitate the discussion (unaudited)"
    )


def test_googl_q1_shaped_release_unaudited_heading_ends_block() -> None:
    # Batch 155: Alphabet suffixes Q1/Q2 2025's headings with "(unaudited)".
    # The leading block must end there — the heading and the table-intro
    # sentence must not ride along as a bullet continuation.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "Exhibit 99.1",
            "April 24, 2025",
            "Alphabet Announces First Quarter 2025 Results",
            "MOUNTAIN VIEW, Calif. – April 24, 2025 – Alphabet Inc. (NASDAQ: "
            "GOOG, GOOGL) today announced financial results for the quarter "
            "ended March 31, 2025.",
            "•Consolidated Alphabet revenues in Q1 2025 increased 12% year over "
            "year to $90.2 billion.",
            "•Google Services revenues increased 10% to $77.3 billion.",
            "•The company announced a 5% increase to the dividend, resulting "
            "in a quarterly cash dividend of $0.21.",
            "Sundar Pichai, CEO, said: “We’re pleased with our strong Q1 "
            "results, which reflect healthy growth and momentum.”",
            "Q1 2025 Financial Highlights (unaudited)",
            "The following table summarizes our consolidated financial results "
            "for the quarters ended March 31, 2024 and 2025.",
            "Quarter Ended March 31,",
            "2024 2025",
            "Revenues $ 74,535 $ 90,234",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Alphabet Announces First Quarter 2025 Results"
    assert "• Consolidated Alphabet revenues in Q1 2025 increased 12%" in hl
    assert "• The company announced a 5% increase to the dividend" in hl
    assert "Sundar Pichai" in hl
    assert "Financial Highlights (unaudited)" not in hl
    assert "The following table summarizes" not in hl
    assert "Quarter Ended March 31" not in hl
