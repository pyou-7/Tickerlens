"""Batch 252 regression tests.

The extractor drops genuine all-caps sub-headlines (Church & Dwight
x3, the last S9-blocked rows):

  * the <=4-word _is_lede_heading_fragment rule eats verb- or
    figure-carrying short sub-headlines ("ANNOUNCES 4% DIVIDEND
    INCREASE", "TOUCHLAND ACQUISITION COMPLETED");
  * _is_lede_data_row's 25% density branch eats a %-range guidance
    sub-headline ("2026 OUTLOOK OF ORGANIC SALES GROWTH OF 3-4% and
    ADJUSTED EPS GROWTH OF 5-8%" — _LEDE_FIGURE_RE counts each
    hyphenated range as two figures).

The fix: the <=4-word fragment rule spares a line carrying a $/%
figure, or — at <=3 words — a completed-event statement
(COMPLETED); a new _is_lede_percent_range_statement exempts %-range
guidance statements from the data-row rule (the %-range mirror of
the batch-183 $-range exemption), and the lede loop serves one
budget-free like the $-range statement. The full-cache blast moves
exactly the three CHD rows (loss -> S9) plus four pure-addition
rows (BBY/DKS/DUK/EL, in-sync -> S4, each gaining a guidance line
and losing nothing) and moves no row to loss.
"""
import sys

sys.path.insert(0, "scripts")

from batch251_repair import sweep_gate_s9
from tickerlens.data.filings import (
    _is_lede_data_row,
    _is_lede_heading_fragment,
    _is_lede_percent_range_statement,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

_BULLETS = [
    "• Net Sales Growth +3.9%: Domestic +3.7% | Int’l +5.2% | SPD +2.8%",
    "• Organic Sales +0.7%: Domestic -0.1% | Int’l +3.6% | SPD +2.8%¹",
    "• Adjusted Gross Margin of 45.5%¹ (+90 Bps)",
    "• Reported EPS $0.60, Adjusted EPS $0.86¹ (+11.7%)",
    "• Cash from Operations of $363.4 million (+24.3%)",
    "• Net Sales Growth +1.6%",
    "• Organic Sales +0.7%¹",
    "• Adjusted Gross Margin Flat",
    "• Reported EPS $3.02, Adjusted EPS $3.53¹ (+2.6%)",
    "• Cash from operations $1.215 billion (+5.1%)",
]
_DATELINE = (
    "EWING, NJ, January 30, 2026 – Church & Dwight Co., Inc. (NYSE: CHD) "
    "today announced that the Company exceeded its outlook with stronger "
    "than expected results."
)


def _chd_html(headline, subheads, headings, *doc_lines):
    return _contact_release_html(
        "Church & Dwight Co., Inc.",
        "News Release",
        "Contact:",
        "Rick Dierker",
        headline,
        *subheads,
        *headings,
        *doc_lines,
        _DATELINE,
    )


def _chd_2025_12_31_html():
    return _chd_html(
        "CHURCH & DWIGHT REPORTS Q4 2025 AND 2025 RESULTS AND PROVIDES 2026 OUTLOOK",
        [
            "Q4 2025 NET SALES, ADJUSTED GROSS MARGIN, ADJUSTED EPS AND CASH FLOW EXCEED OUTLOOK",
            "2026 OUTLOOK OF ORGANIC SALES GROWTH OF 3-4% and ADJUSTED EPS GROWTH OF 5-8%",
            "ANNOUNCES 4% DIVIDEND INCREASE",
        ],
        ["2025 Fourth Quarter Results", "2025 Full Year Results"],
        *_BULLETS,
    )


def test_extractor_serves_all_three_chd_sub_headlines() -> None:
    # The real extractor, end to end, on the CHD Q4 2025 shape: the
    # %-range outlook line, the 4%-carrying dividend line and the
    # longer sub-headline all reach the served text, the two
    # summary-table headings never do, and the bullets follow.
    live = extract_press_release_highlights(_chd_2025_12_31_html())
    assert live is not None
    assert (
        "2026 OUTLOOK OF ORGANIC SALES GROWTH OF 3-4% and ADJUSTED EPS GROWTH OF 5-8%"
        in live
    )
    assert "ANNOUNCES 4% DIVIDEND INCREASE" in live
    assert (
        "Q4 2025 NET SALES, ADJUSTED GROSS MARGIN, ADJUSTED EPS AND CASH FLOW EXCEED OUTLOOK"
        in live
    )
    assert "2025 Fourth Quarter Results" not in live
    assert "2025 Full Year Results" not in live
    assert "Net Sales Growth +3.9%" in live
    assert "Organic Sales +0.7%" in live


def test_extractor_keeps_completed_event_sub_headline() -> None:
    # CHD Q2 2025: "TOUCHLAND ACQUISITION COMPLETED" is the release's
    # own sub-headline — a completed corporate event, not a heading.
    live = extract_press_release_highlights(
        _chd_html(
            "CHURCH & DWIGHT REPORTS Q2 2025 RESULTS",
            [
                "Q2 ORGANIC SALES AND ADJUSTED EPS EXCEED OUTLOOK",
                "TOUCHLAND ACQUISITION COMPLETED",
            ],
            ["2025 Second Quarter Results", "2025 Full Year Outlook"],
            *_BULLETS,
        )
    )
    assert live is not None
    assert "TOUCHLAND ACQUISITION COMPLETED" in live
    assert "2025 Second Quarter Results" not in live


def test_extractor_still_drops_short_heading_fragments() -> None:
    # The guards are narrow on purpose: a 4-word verb line reads as a
    # heading ("AFFIRMS LONG-TERM TARGETS", "Q1 EPS EXCEEDS OUTLOOK",
    # "UPDATES FULL YEAR OUTLOOK" — sparing them starves a real bullet
    # under the 6-line budget), and a bare period label never carries
    # a figure. All of these stay out of the served text.
    live = extract_press_release_highlights(
        _chd_html(
            "AMERICAN WATER REPORTS SOLID THIRD QUARTER 2026 RESULTS",
            [
                "NARROWS 2026 EPS GUIDANCE TO TOP HALF OF RANGE",
                "AFFIRMS LONG-TERM TARGETS",
                "Q1 EPS EXCEEDS OUTLOOK",
                "UPDATES FULL YEAR OUTLOOK",
            ],
            ["QUARTER", "RESULTS FOR THE QUARTER", "Q4 2025 RESULTS"],
            *_BULLETS,
        )
    )
    assert live is not None
    assert "AFFIRMS LONG-TERM TARGETS" not in live
    assert "Q1 EPS EXCEEDS OUTLOOK" not in live
    assert "UPDATES FULL YEAR OUTLOOK" not in live
    assert "RESULTS FOR THE QUARTER" not in live
    assert "Q4 2025 RESULTS" not in live
    assert "NARROWS 2026 EPS GUIDANCE TO TOP HALF OF RANGE" in live


def test_percent_range_guidance_line_does_not_consume_budget() -> None:
    # Best Buy: "Raises FY27 Comparable Sales Guidance to 1.9% to
    # 3.0%" was eaten by the data-row rule (the "FY27" token counts as
    # a figure, pushing density to 3/9). Served budget-free like the
    # $-range statement, it must not starve a bullet.
    bullets = [
        "• GAAP diluted EPS of $1.32, compared to $1.45 in Q2 FY26",
        "• Non-GAAP diluted EPS of $1.47, compared to $1.45 in Q2 FY26",
        "• Enterprise revenue of $10.2 billion, up 3.1%",
        "• Domestic revenue of $9.3 billion, up 2.8%",
        "• International revenue of $0.9 billion, up 6.4%",
        "• Cash from operations of $412 million in the quarter",
    ]
    live = extract_press_release_highlights(
        _contact_release_html(
            "Best Buy Co., Inc.",
            "News Release",
            "Contact:",
            "Investor Relations",
            "BEST BUY REPORTS SECOND QUARTER RESULTS",
            "Raises FY27 Comparable Sales Guidance to 1.9% to 3.0%",
            *bullets,
            "MINNEAPOLIS, August 26, 2026 – Best Buy Co., Inc. (NYSE: BBY) "
            "today announced results for its second quarter ended August 1, 2026.",
        )
    )
    assert live is not None
    assert "Raises FY27 Comparable Sales Guidance to 1.9% to 3.0%" in live
    for b in bullets:
        assert b.split("• ")[1][:40] in live


def test_is_lede_percent_range_statement() -> None:
    assert _is_lede_percent_range_statement(
        "2026 OUTLOOK OF ORGANIC SALES GROWTH OF 3-4% and ADJUSTED EPS GROWTH OF 5-8%"
    )
    assert _is_lede_percent_range_statement(
        "2025 OUTLOOK: 3 to 4% NET SALES GROWTH, 7 to 8% ADJUSTED EPS GROWTH"
    )
    assert _is_lede_percent_range_statement(
        "Full year adjusted EBITDA margin 15% to 17%"
    )
    # A bare range fragment has no subject — still a data row.
    assert not _is_lede_percent_range_statement("3% to 4%")
    # A short %-range table row has only a 3-word label.
    assert not _is_lede_percent_range_statement(
        "Net Sales Growth (0.5%) - 0.5% 1.5% - 3.5%"
    )
    # A bullet is never a range statement, even with a %-range in it.
    assert not _is_lede_percent_range_statement(
        "● Reiterates long-term core EPS growth rate targets of 5%-7% "
        "for 2021-2025 and 5%-7% for 2025-2028"
    )
    # A $-range statement is the dollar predicate's job, not this one.
    assert not _is_lede_percent_range_statement(
        "Reaffirms 2026 Outlook for Adjusted EPS of $7.50 to $8.00"
    )


def test_is_lede_data_row_still_catches_table_rows() -> None:
    # Fastenal: a negative value's minus is a sign, not a range
    # connector — the row stays a data row.
    assert _is_lede_data_row(
        "Income before income taxes $ 1,508.1 1,522.0 -0.9 % $ 344.3 354.2 -2.8 %"
    )
    assert _is_lede_data_row(
        "Diluted net income per share $ 2.00 2.02 -0.6 % $ 0.46 0.46 -1.9 %"
    )
    assert _is_lede_data_row(
        "Net Sales Growth (0.5%) - 0.5% 1.5% - 3.5%"
    )
    assert _is_lede_data_row("Margin 14.7% 16.4% 170 bps")
    # ...while the guidance statements that were misread as rows are not.
    assert not _is_lede_data_row(
        "2026 OUTLOOK OF ORGANIC SALES GROWTH OF 3-4% and ADJUSTED EPS GROWTH OF 5-8%"
    )
    assert not _is_lede_data_row(
        "Raises FY27 Comparable Sales Guidance to 1.9% to 3.0%"
    )


def test_is_lede_heading_fragment_cases() -> None:
    assert not _is_lede_heading_fragment("ANNOUNCES 4% DIVIDEND INCREASE")
    assert not _is_lede_heading_fragment("TOUCHLAND ACQUISITION COMPLETED")
    assert not _is_lede_heading_fragment("ACQUISITION COMPLETED")
    # A present-tense verb at <=3 words is still a fragment by design
    # ("DECLARES QUARTERLY DIVIDEND" reads as a heading — only a
    # completed-event statement or a $/% figure spares a short line).
    assert _is_lede_heading_fragment("DECLARES QUARTERLY DIVIDEND")
    assert _is_lede_heading_fragment("AFFIRMS LONG-TERM TARGETS")
    assert _is_lede_heading_fragment("Q1 EPS EXCEEDS OUTLOOK")
    assert _is_lede_heading_fragment("UPDATES FULL YEAR OUTLOOK")
    assert _is_lede_heading_fragment("QUARTER")
    assert _is_lede_heading_fragment("RESULTS FOR THE QUARTER")
    assert _is_lede_heading_fragment("Q4 2025 RESULTS")


def test_s9_passes_on_the_three_fixed_chd_rows() -> None:
    # The fix unblocks gate S9 on all three rows: stored loses only
    # the two summary-table headings, live adds only tail bullets.
    cases = [
        (
            "CHURCH & DWIGHT REPORTS Q4 2025 AND 2025 RESULTS AND PROVIDES 2026 OUTLOOK",
            [
                "Q4 2025 NET SALES, ADJUSTED GROSS MARGIN, ADJUSTED EPS AND CASH FLOW EXCEED OUTLOOK",
                "2026 OUTLOOK OF ORGANIC SALES GROWTH OF 3-4% and ADJUSTED EPS GROWTH OF 5-8%",
                "ANNOUNCES 4% DIVIDEND INCREASE",
            ],
            ["2025 Fourth Quarter Results", "2025 Full Year Results"],
            1,
        ),
        (
            "CHURCH & DWIGHT REPORTS Q2 2025 RESULTS",
            [
                "Q2 ORGANIC SALES AND ADJUSTED EPS EXCEED OUTLOOK",
                "TOUCHLAND ACQUISITION COMPLETED",
            ],
            ["2025 Second Quarter Results", "2025 Full Year Outlook"],
            2,
        ),
        (
            "CHURCH & DWIGHT REPORTS FOURTH QUARTER AND FULL YEAR 2024 RESULTS",
            [
                "Q4 NET SALES, EPS AND CASH FROM OPERATIONS EXCEED OUTLOOK",
                "2025 OUTLOOK: 3 to 4% NET SALES GROWTH, 7 to 8% ADJUSTED EPS GROWTH",
                "ANNOUNCES 4% DIVIDEND INCREASE",
            ],
            ["2024 Fourth Quarter Results", "2024 Full Year Results"],
            1,
        ),
    ]
    for headline, subheads, headings, n_stored_bullets in cases:
        html = _chd_html(headline, subheads, headings, *_BULLETS)
        live = extract_press_release_highlights(html)
        assert live is not None
        stored = "\n\n".join(
            [headline, *subheads, *headings, *_BULLETS[:n_stored_bullets]]
        )
        assert sweep_gate_s9(stored, live, html) is None, headline


def test_s9_still_refuses_when_a_sub_headline_is_lost() -> None:
    # Control: a stored sub-headline live still drops (the 4-word
    # verb line) blocks the swap — the gate must not re-sync a row
    # that would lose real news.
    html = _chd_html(
        "AMERICAN WATER REPORTS SOLID THIRD QUARTER 2026 RESULTS",
        [
            "NARROWS 2026 EPS GUIDANCE TO TOP HALF OF RANGE",
            "AFFIRMS LONG-TERM TARGETS",
        ],
        ["2026 Third Quarter Results", "2026 Full Year Results"],
        *_BULLETS,
    )
    live = extract_press_release_highlights(html)
    assert live is not None
    assert "AFFIRMS LONG-TERM TARGETS" not in live
    stored = "\n\n".join(
        [
            "AMERICAN WATER REPORTS SOLID THIRD QUARTER 2026 RESULTS",
            "NARROWS 2026 EPS GUIDANCE TO TOP HALF OF RANGE",
            "AFFIRMS LONG-TERM TARGETS",
            "2026 Third Quarter Results",
            "2026 Full Year Results",
            *_BULLETS[:2],
        ]
    )
    assert sweep_gate_s9(stored, live, html) == "loss"
