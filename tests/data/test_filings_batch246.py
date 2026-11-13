"""Batch 246 regression tests.

One extractor decision: the leading-bullet block now serves the
executive quote that immediately follows the dateline. The seed rows
are split on this — ADI/Deckers/DGX carry the quote, Broadcom/Dollar
Tree/Elevance/GD do not — but the quote is the release's own summary
of the quarter, so the uniform rule is to serve it: the block pulls
the quote run (at most 3 consecutive executive-quote lines) that
follows the dateline sentence closing the bullet item, then ends.
Full-cache blast: 85 rows change, every added line a quote line
(verified by scripts/batch246_probe3.py), 0 rows lose content;
13 SKIP-loss rows re-sync under gate S4 and 72 in-sync rows gain
their quote the same way.

The dateline test is deliberately local to the pull-in: the
extractor's own dateline regexes miss the glued-dash ("WILMINGTON,
Mass.--November 26, 2024--"), all-caps-month ("SAN FRANCISCO, MAY
22, 2025--"), parenthesized-date ("Goleta, California (October 24,
2024) --") and two-comma ("SECAUCUS, N.J., October 22, 2024 -")
forms, and widening the shared regexes would be wrong — the block
breaks on a dated dateline mid-block, so a matching dateline would
drop out of the block instead of riding in as a continuation.
"""
from tickerlens.data.filings import (
    _is_executive_quote_line,
    _is_quote_pull_dateline,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

_ADI_HEADLINE = "Analog Devices Reports Fiscal Second Quarter 2025 Financial Results"
_ADI_BULLETS = [
    "• Revenue of $2.64 billion, with double-digit year-over-year growth across all end markets",
    "• Operating cash flow of $3.9 billion and free cash flow of $3.3 billion on a trailing twelve-month basis or 39% and 34% of revenue, respectively",
    "• Returned $0.7 billion to shareholders via dividends and repurchases during the second quarter",
]
_ADI_DATELINE = (
    "WILMINGTON, Mass.--May 22, 2025--Analog Devices, Inc. (Nasdaq: ADI), "
    "a global semiconductor leader, today announced financial results for "
    "its fiscal second quarter 2025, which ended May 3, 2025."
)
_ADI_QUOTES = [
    "“ADI delivered second quarter revenue and earnings per share above the high end of guidance,” said Vincent Roche, CEO and Chair. “Against a backdrop of global trade volatility, our performance reflects the ongoing cyclical recovery.”",
    "CFO Richard Puccio added, “Second quarter bookings accelerated across all end markets and all regions, resulting in continued sequential backlog growth.”",
]
_TABLE_HEAD = "Performance for the Second Quarter of Fiscal 2025"


def test_quote_predicate_shapes() -> None:
    # Quote-first and attribution-first, both seen in the seed rows.
    assert _is_executive_quote_line(_ADI_QUOTES[0])
    assert _is_executive_quote_line(_ADI_QUOTES[1])
    assert _is_executive_quote_line(
        "“We remain confident in the long-term earnings potential of our "
        "diverse businesses as we navigate a dynamic operating environment.”"
    )
    # A bullet, a dateline, and a prose line are not quotes.
    assert not _is_executive_quote_line(_ADI_BULLETS[0])
    assert not _is_executive_quote_line(_ADI_DATELINE)
    assert not _is_executive_quote_line(
        "Worldwide net sales and revenues increased 5 percent, to $12.608 billion."
    )
    # Ford's flattened page-image mega-line carries a quoted term and
    # a quote verb deep inside it, but it never opens with a quote
    # and its first quote mark sits past the bound — not a quote line.
    assert not _is_executive_quote_line(
        "The following applies to the information throughout this release: "
        "• See tables later in this release for the nature and amount of "
        "special items, and reconciliations of the non-GAAP financial "
        "measures designated as “adjusted” to the most comparable "
        "financial measures, and the company continued to invest."
    )
    # A quote that opens but never closes on its own line is not
    # pulled — the pull-in only takes complete quote lines.
    assert not _is_executive_quote_line(
        "“We delivered a strong quarter, with revenue growth across every"
    )


def test_quote_pull_dateline_forms() -> None:
    # Every dateline form the pull-in must recognize (one per filer
    # family in the blast), plus the two the shared regexes already
    # know.
    assert _is_quote_pull_dateline(_ADI_DATELINE)
    assert _is_quote_pull_dateline(
        "SAN FRANCISCO, MAY 22, 2025-- Autodesk, Inc. (NASDAQ: ADSK) "
        "today reported financial results for the first quarter of fiscal 2026."
    )
    assert _is_quote_pull_dateline(
        "Goleta, California (October 24, 2024) -- Deckers Brands "
        "(NYSE: DECK), a global leader in designing, marketing, and "
        "distributing innovative footwear, today announced financial results."
    )
    assert _is_quote_pull_dateline(
        "SECAUCUS, N.J., October 22, 2024 - Quest Diagnostics Incorporated "
        "(NYSE: DGX), a leading provider of diagnostic information services, "
        "today announced financial results."
    )
    assert _is_quote_pull_dateline(
        "Indianapolis, IN - October 17, 2024 - Elevance Health, Inc. "
        "(NYSE: ELV) reported third quarter 2024 results."
    )
    assert _is_quote_pull_dateline(
        "PALO ALTO, Calif. – December 12, 2024 – Broadcom Inc. "
        "(Nasdaq: AVGO), a global technology leader."
    )
    # Prose, bullets, and period subheadings are not datelines.
    assert not _is_quote_pull_dateline(
        "Worldwide net sales and revenues increased 5 percent."
    )
    assert not _is_quote_pull_dateline(_ADI_BULLETS[0])
    assert not _is_quote_pull_dateline("First Quarter Fiscal 2026")


def test_full_pipeline_pulls_quote_after_dateline() -> None:
    # The ADI shape: headline + bullets + dateline + two quotes,
    # then the results-table heading. Both quotes are served.
    hl = extract_press_release_highlights(
        _contact_release_html(
            _ADI_HEADLINE,
            *_ADI_BULLETS,
            _ADI_DATELINE,
            *_ADI_QUOTES,
            _TABLE_HEAD,
            "Results Summary(1)",
            "(in millions, except per-share amounts and percentages)",
            "Revenue $ 2,640 $ 2,159 22 %",
        )
    )
    assert hl is not None
    assert "above the high end of guidance" in hl
    assert "Second quarter bookings accelerated" in hl
    assert "Results Summary" not in hl


def test_full_pipeline_no_quote_no_change() -> None:
    # Same release with no quote after the dateline: the block ends
    # at the dateline exactly as before — the pull-in adds nothing.
    hl = extract_press_release_highlights(
        _contact_release_html(
            _ADI_HEADLINE,
            *_ADI_BULLETS,
            _ADI_DATELINE,
            _TABLE_HEAD,
            "Results Summary(1)",
            "(in millions, except per-share amounts and percentages)",
            "Revenue $ 2,640 $ 2,159 22 %",
        )
    )
    assert hl is not None
    assert "above the high end of guidance" not in hl
    assert _ADI_DATELINE[:60] in hl


def test_full_pipeline_quote_after_prose_not_pulled() -> None:
    # Deere shape: a results-prose line sits between the dateline
    # and the quote. The pull-in only fires on the line immediately
    # after the dateline, so the quote stays out — a single-row shape,
    # not a generalization worth making. (The real Deere bullets use
    # the ● marker, which is not a leading-bullet start, so the
    # synthetic doc uses • bullets to exercise the block path the
    # pull-in lives on.)
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Deere Reports Third Quarter Net Income of $1.379 Billion",
            "• Net income of $1.379 billion for the third quarter, up 4 percent from a year ago",
            "• Net sales and revenues of $12.608 billion, up 5 percent from a year ago",
            "MOLINE, Illinois (August 20, 2026) — Deere & Company reported "
            "net income of $1.379 billion for the third quarter ended August 2, 2026.",
            "Worldwide net sales and revenues increased 5 percent, to $12.608 billion.",
            "“Deere delivered a strong quarter, reflecting disciplined execution "
            "by our teams,” said John C. May, chairman and chief executive officer.",
            "Third Quarter 2026 Financial Results",
        )
    )
    assert hl is not None
    assert "Deere delivered a strong quarter" not in hl
    assert "Worldwide net sales" not in hl


def test_full_pipeline_quote_run_capped_at_three() -> None:
    # Four consecutive quote lines after the dateline: only the first
    # three are pulled — the cap keeps a long quote run from eating
    # the block.
    quotes = [
        "“First quote line, complete on its own,” said Jane Doe, CEO.",
        "“Second quote line, complete on its own,” said Jane Doe, CEO.",
        "“Third quote line, complete on its own,” said Jane Doe, CEO.",
        "“Fourth quote line, complete on its own,” said Jane Doe, CEO.",
    ]
    hl = extract_press_release_highlights(
        _contact_release_html(
            _ADI_HEADLINE,
            *_ADI_BULLETS,
            _ADI_DATELINE,
            *quotes,
            _TABLE_HEAD,
        )
    )
    assert hl is not None
    assert "First quote line" in hl
    assert "Second quote line" in hl
    assert "Third quote line" in hl
    assert "Fourth quote line" not in hl


def test_full_pipeline_two_comma_dateline_pulls_quote() -> None:
    # The DGX shape: a two-comma dateline the shared regexes miss.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Quest Diagnostics Reports Third Quarter 2024 Financial Results",
            "• Third quarter revenues of $2.49 billion, up 8.5% from 2023",
            "• Third quarter reported diluted earnings per share (\"EPS\") of $1.99, up 1.5% from 2023",
            "SECAUCUS, N.J., October 22, 2024 - Quest Diagnostics Incorporated "
            "(NYSE: DGX), a leading provider of diagnostic information services, "
            "today announced financial results for the third quarter ended September 30, 2024.",
            "“We delivered a strong third quarter, with total revenue growth of 8.5%,” "
            "said Jim Davis, Chairman, CEO and President.",
            "Three Months Ended September 30,",
            "2024 2023 Change",
            "(dollars in millions, except per share data)",
        )
    )
    assert hl is not None
    assert "We delivered a strong third quarter" in hl
    assert "Three Months Ended" not in hl
