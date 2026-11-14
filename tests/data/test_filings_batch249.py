"""Batch 249 regression tests.

One extractor decision: a Highlights section now serves the
executive quote that sits immediately before its heading, when
the quote run is anchored by a dateline. Palantir's releases put
the CEO's quote between the dateline and the "Q# YYYY Highlights"
heading, so the section path wins and the quote is never collected
— the batch-246 pull-in only fires inside the leading-bullet
block, which these releases never open. The seed rows carry the
quote, so the section serves it too.

Full-cache blast: 24 rows change, 0 rows lose content. 21 rows
gain only quote lines (ADBE x6, ANET x2, CRWD x4, CSX, EBAY x3,
PLTR x5 — verified quote-only by scripts/batch249_probe3.py);
the 3 PLTR SKIP-loss rows gain the quote plus the section's
remaining bullets, because their stored rows are truncated
seed-era extractions carrying only the first 2 of 12 bullets.
SKIP-loss 168 -> 165; the 24 rows re-sync under gate S4.

The dateline anchor is what keeps this narrow, exactly as in
batch 246: the line before the quote run must be a dateline
sentence. A quote preceded by a bullet (Amazon's Jassy quote
inside a bullet), a footnote line (Chevron's reconciliation
pointer), an attribution line (Equinix's "Charles Meyers, CEO
and President, Equinix:"), or an undated "today reported" line
(Biogen, Datadog) is a different shape and stays out.
"""
from tickerlens.data.filings import (
    _extract_highlights_section,
    _prepend_pre_section_quote,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

_PLTR_HEADLINE = (
    "Palantir Reports Revenue Growth of 30% Y/Y, U.S. Revenue Growth "
    "of 44% Y/Y, GAAP EPS of $0.06; Raises Full Year Guidance"
)
_PLTR_DATELINE = (
    "DENVER — (BUSINESS WIRE) — Palantir Technologies Inc. "
    "(NYSE:PLTR) today announced financial results for the third "
    "quarter ended September 30, 2024."
)
_PLTR_QUOTE = (
    "“We absolutely eviscerated this quarter, driven by unrelenting "
    "AI demand that won’t slow down. This is a U.S.-driven AI "
    "revolution that has taken full hold,” said Alex Karp, CEO."
)
_PLTR_BULLETS = [
    "• U.S. revenue grew 44% year-over-year and 14% quarter-over-quarter to $499 million",
    "• U.S. commercial revenue grew 54% year-over-year and 13% quarter-over-quarter to $179 million",
    "• Revenue grew 30% year-over-year and 7% quarter-over-quarter to $726 million",
    "• GAAP net income of $144 million, representing a 20% margin",
]


def _pltr_lines(quote=_PLTR_QUOTE, dateline=_PLTR_DATELINE):
    return [
        _PLTR_HEADLINE,
        dateline,
        quote,
        "Q3 2024 Highlights",
        *_PLTR_BULLETS,
    ]


def test_pre_section_quote_prepended() -> None:
    # The Palantir shape: dateline, quote, section heading, bullets.
    # The quote is served ahead of the bullets, in document order.
    hl = extract_press_release_highlights(
        _contact_release_html(*_pltr_lines())
    )
    assert hl is not None
    assert "We absolutely eviscerated this quarter" in hl
    assert hl.index("We absolutely eviscerated") < hl.index(
        "U.S. revenue grew 44%"
    )
    assert "GAAP net income of $144 million" in hl


def test_prepend_helper_dateline_anchored() -> None:
    # Unit level: the helper prepends the quote run only when the
    # line before it is a dateline.
    lines = [
        "Some headline",
        _PLTR_DATELINE,
        _PLTR_QUOTE,
        "Q3 2024 Highlights",
        *_PLTR_BULLETS,
    ]
    out = _prepend_pre_section_quote(lines, 3, list(_PLTR_BULLETS))
    assert out[0] == _PLTR_QUOTE
    assert out[1:] == _PLTR_BULLETS
    # No dateline before the quote: no prepend (Equinix attribution
    # line / Chevron footnote line shape).
    lines[1] = "Charles Meyers, CEO and President, Equinix:"
    out = _prepend_pre_section_quote(lines, 3, list(_PLTR_BULLETS))
    assert out == _PLTR_BULLETS
    # No quote before the heading: no prepend.
    lines[1] = _PLTR_DATELINE
    lines[2] = "Worldwide net sales increased 5 percent."
    out = _prepend_pre_section_quote(lines, 3, list(_PLTR_BULLETS))
    assert out == _PLTR_BULLETS


def test_quote_run_capped_at_three() -> None:
    # Four consecutive quote lines before the heading: only the
    # first three are prepended — the batch-246 cap.
    quotes = [
        "“First quote line, complete on its own,” said Jane Doe, CEO.",
        "“Second quote line, complete on its own,” said Jane Doe, CEO.",
        "“Third quote line, complete on its own,” said Jane Doe, CEO.",
        "“Fourth quote line, complete on its own,” said Jane Doe, CEO.",
    ]
    hl = extract_press_release_highlights(
        _contact_release_html(
            _PLTR_HEADLINE, _PLTR_DATELINE, *quotes,
            "Q3 2024 Highlights", *_PLTR_BULLETS,
        )
    )
    assert hl is not None
    assert "First quote line" in hl
    assert "Second quote line" in hl
    assert "Third quote line" in hl
    assert "Fourth quote line" not in hl


def test_quote_before_heading_after_bullet_not_prepended() -> None:
    # Amazon shape: a bullet sits between the dateline and the quote,
    # so the line before the quote run is not a dateline — the quote
    # stays out. The section still serves its bullets.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Amazon.com Announces Third Quarter Results",
            "SEATTLE — October 31, 2024 — Amazon.com, Inc. (NASDAQ: AMZN) "
            "today announced financial results for its third quarter ended "
            "September 30, 2024.",
            "• Free cash flow less equipment finance leases was $47.7 billion "
            "for the trailing twelve months.",
            "“We delivered strong results across the business,” said Andy "
            "Jassy, President and CEO.",
            "Third Quarter 2024 Highlights",
            "• Net sales increased 11% to $158.9 billion in the third quarter.",
            "• Operating income increased to $18.4 billion in the third quarter.",
        )
    )
    assert hl is not None
    assert "We delivered strong results across the business" not in hl
    assert "Net sales increased 11%" in hl


def test_quote_before_heading_after_undated_line_not_prepended() -> None:
    # Biogen/Datadog shape: the line before the quote is an undated
    # "today reported" line, not a dateline the pull-in recognizes —
    # the quote stays out.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Biogen Reports Fourth Quarter 2023 Results",
            "Biogen Inc. (NASDAQ: BIIB) today reported fourth quarter and "
            "full year 2023 financial results.",
            "“We delivered a strong fourth quarter,” said Christopher A. "
            "Viehbacher, President and Chief Executive Officer.",
            "Fourth Quarter 2023 Highlights",
            "• Total revenue was $2.4 billion, down 6% year-over-year.",
            "• GAAP diluted EPS was $2.41, up 18% year-over-year.",
        )
    )
    assert hl is not None
    assert "We delivered a strong fourth quarter" not in hl
    assert "Total revenue was $2.4 billion" in hl


def test_leading_block_winner_serves_quote_once() -> None:
    # When the leading-bullet block wins the density competition,
    # the batch-246 pull-in already serves the quote — the section
    # prepend must not duplicate it (the prepend only applies to a
    # headed section winner, never to the block).
    hl = extract_press_release_highlights(
        _contact_release_html(
            _PLTR_HEADLINE,
            "• U.S. revenue grew 44% year-over-year to $499 million",
            "• Revenue grew 30% year-over-year to $726 million",
            _PLTR_DATELINE,
            _PLTR_QUOTE,
            "Q3 2024 Highlights",
            "• Customer count grew 39% year-over-year",
        )
    )
    assert hl is not None
    assert hl.count("We absolutely eviscerated this quarter") == 1


def test_section_without_preceding_quote_unchanged() -> None:
    # A section whose heading follows the dateline directly serves
    # exactly its bullets — the prepend adds nothing.
    hl = extract_press_release_highlights(
        _contact_release_html(
            _PLTR_HEADLINE,
            _PLTR_DATELINE,
            "Q3 2024 Highlights",
            *_PLTR_BULLETS,
        )
    )
    assert hl is not None
    assert "We absolutely eviscerated this quarter" not in hl
    assert "GAAP net income of $144 million" in hl


def test_pre_section_quote_does_not_change_selection() -> None:
    # The prepend runs after selection: a quarter-scoped section
    # still beats a full-year one (batch 244), with its quote.
    # Headings are all-caps as in real releases — the section
    # collector breaks at an all-caps heading, so the quarter
    # section's content never swallows the full-year one.
    q4 = [
        "FOURTH QUARTER 2024 HIGHLIGHTS",
        "• Fourth-quarter revenue grew 30% year-over-year to $726 million",
        "• Fourth-quarter GAAP net income was $144 million",
        "• Fourth-quarter adjusted EPS grew 43% year-over-year to $0.10",
    ]
    fy = [
        "FULL YEAR 2024 HIGHLIGHTS",
        "• Full-year revenue grew 29% year-over-year to $2.87 billion",
        "• Full-year GAAP net income was $462 million",
        "• Full-year adjusted EPS grew 38% year-over-year to $0.38",
    ]
    lines = [
        _PLTR_HEADLINE,
        _PLTR_DATELINE,
        _PLTR_QUOTE,
        *q4,
        *fy,
    ]
    best = _extract_highlights_section(lines[1:])
    assert best is not None
    assert best[0] == _PLTR_QUOTE
    assert "Fourth-quarter revenue grew 30%" in "\n".join(best)
    assert "Full-year revenue grew 29%" not in "\n".join(best)
