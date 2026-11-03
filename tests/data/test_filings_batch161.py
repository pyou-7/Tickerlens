"""Batch 161 regression tests: Sempra's single-figure reconciliation rows
no longer leak into the lede.

The batch-160 follow-up named SRE's single-figure long-label tail rows:
the GAAP-to-adjusted reconciliation table flattens rows that carry one
trailing figure after dash placeholders ("Equity losses from write-off of
rate base disallowances ... — — — 44", "Net unrealized losses on
contingent interest rate swap ... — — — 17"), rows that end in a dash
placeholder ("Net unrealized losses on interest rate swaps ... 9 —",
"Impact from regulatory disallowances 25 — 25 —", "Tax items related to
assets held for sale 26 — 26 —"), and bare two-figure rows whose long
labels dilute density below every data-row branch ("Impact from foreign
currency and inflation on monetary positions in Mexico (8) 41" at 17%,
"... and associated undesignated derivatives (19) (8)" at 13%, "Net
unrealized losses on interest rate swaps ... 11 9" at 13%). No density
rule catches them and the tail trim can't start on them, so they serve
at the tail of 3 SRE quarters. The fix adds a reconciliation-row
predicate: a dash-cell row (standalone dash token adjacent to a figure,
ending in a figure or a dash) or a bare two-figure row (>=2 figures,
ends in a figure, $-less, no %, >=10% density, >=4-word label, no
comparison phrase, no mid-line sentence boundary).
"""

from tickerlens.data.filings import (
    _is_lede_recon_row,
    _is_lede_table_label,
    _is_lede_table_line,
    extract_press_release_highlights,
)


def _bare_release_html(*lines: str) -> str:
    body = "".join(f"<p>{ln}</p>" for ln in lines)
    return f"<html><body>{body}</body></html>"


def test_dash_placeholder_rows_are_recon_rows() -> None:
    # Batch 161: SRE's single-figure rows end in a figure after dash
    # cells, or end in a dash cell themselves.
    assert _is_lede_recon_row(
        "Equity losses from write-off of rate base disallowances "
        "resulting from Public Utility Commission of Texas' final order "
        "in Oncor Electric Delivery Company LLC's comprehensive base "
        "rate review — — — 44"
    )
    assert _is_lede_recon_row(
        "Net unrealized losses on contingent interest rate swap related "
        "to initial phase of the Port Arthur LNG liquefaction project "
        "— — — 17"
    )
    assert _is_lede_recon_row(
        "Net unrealized losses on interest rate swaps related to Port "
        "Arthur LNG Phase 1 project 9 —"
    )
    assert _is_lede_recon_row(
        "Impact from regulatory disallowances 25 — 25 —"
    )
    assert _is_lede_recon_row(
        "Net unrealized (gains) losses on interest rate swaps related "
        "to Port Arthur LNG Phase 1 project (1) — 8 —"
    )
    assert _is_lede_recon_row(
        "Tax items related to assets held for sale 26 — 26 —"
    )
    assert _is_lede_recon_row(
        "Tax items related to assets held for sale (35) —"
    )
    # Wells Fargo's segment row carries the same shape: a label, a value,
    # and empty dash cells.
    assert _is_lede_recon_row("Consumer Banking and Lending 781.4 — —")
    # The en dash and hyphen-minus are the same empty-cell mark.
    assert _is_lede_recon_row(
        "Tax items related to assets held for sale 26 – 26 –"
    )
    assert _is_lede_recon_row(
        "Tax items related to assets held for sale 26 - 26 -"
    )
    # A recon row is table residue in the lede loop and at the tail.
    assert _is_lede_table_line(
        "Equity losses from write-off of rate base disallowances "
        "resulting from Public Utility Commission of Texas' final order "
        "in Oncor Electric Delivery Company LLC's comprehensive base "
        "rate review — — — 44"
    )
    assert _is_lede_table_line(
        "Net unrealized losses on interest rate swaps related to Port "
        "Arthur LNG Phase 1 project 9 —"
    )


def test_bare_two_figure_rows_are_recon_rows() -> None:
    # Batch 161: two bare figures, a long label, no $ or % anywhere,
    # density 13-17% — below every data-row branch, but a row, not prose.
    assert _is_lede_recon_row(
        "Impact from foreign currency and inflation on monetary "
        "positions in Mexico (8) 41"
    )
    assert _is_lede_recon_row(
        "Impact from foreign currency and inflation on monetary "
        "positions in Mexico and associated undesignated derivatives "
        "(19) (8)"
    )
    assert _is_lede_recon_row(
        "Net unrealized losses on interest rate swaps related to Port "
        "Arthur LNG Phase 1 project 11 9"
    )
    assert _is_lede_table_line(
        "Impact from foreign currency and inflation on monetary "
        "positions in Mexico (8) 41"
    )


def test_recon_row_negatives() -> None:
    # Terminated prose is never a row, even with dash cells and figures.
    assert not _is_lede_recon_row(
        "Sempra's GAAP earnings for the first nine months of 2024 were "
        "$2.152 billion, or $3.38 per diluted share, compared with GAAP "
        "earnings of $2.293 billion in the first nine months of 2023."
    )
    # A bullet is content, never a row.
    assert not _is_lede_recon_row("•Revenue grew 12% year over year")
    # A short label plus a dash plus a value is a metric line, not a
    # reconciliation row: the label must run >= 4 words.
    assert not _is_lede_recon_row("EPS — $0.89")
    assert not _is_lede_recon_row("Net income — 44")
    # A prose em-dash is surrounded by words, not figures: no
    # figure-adjacent dash cell, no bare two-figure ending.
    assert not _is_lede_recon_row(
        "Adjusted EBITDA — up 4% to $1.3 billion in the quarter"
    )
    # A fragment ending in a word is prose, even with dash cells.
    assert not _is_lede_recon_row(
        "Net unrealized losses — 44 in the quarter"
    )
    # A comparison clause is prose, not a row (Kinder Morgan's EPS
    # summary shape, batch 159) — and it carries %.
    assert not _is_lede_recon_row(
        "Earnings per share (EPS) up 23% versus Q2 2024; Adjusted EPS up 12%"
    )
    # A wrapped prose fragment with a completed sentence inside is
    # prose (the COIN guard, batch 160).
    assert not _is_lede_recon_row(
        "majority of which were unrealized. These gains were 44 17"
    )
    # One bare figure is a metric value, not a row.
    assert not _is_lede_recon_row(
        "Revenue grew to 44 in the quarter, up from the prior year"
    )
    # A short label before two bare figures is a fragment, not a row.
    assert not _is_lede_recon_row("earnings of 566 and 685 in the quarter")
    # A $-carrying line ending in a word is prose here, not a recon row.
    assert not _is_lede_recon_row(
        "Net income $1.2 billion, or $0.89 per diluted share"
    )
    # A line ending in a bare year is prose, never a row — headlines,
    # sub-headlines, and wrapped fragments all end in years, while a
    # reconciliation value never is one. These are the DB-wide scan's
    # false positives before the year guard.
    assert not _is_lede_recon_row(
        "Verizon delivered strong financial growth with industry-leading "
        "wireless service revenue in 1Q 2025"
    )
    assert not _is_lede_recon_row(
        "of common stock at the close of business on August 17, 2026"
    )
    assert not _is_lede_recon_row(
        "Shopify's Standout 2025: The Launchpad for a New Era of "
        "Commerce in 2026"
    )
    assert not _is_lede_recon_row(
        "Gas Facilities Commissioned in the Fourth Quarter; Overall "
        "Production Expected to More Than Double from 2024 to 2025"
    )
    assert not _is_lede_recon_row(
        "Simon® Reports Third Quarter 2024 Results, Affirms Full Year 2024"
    )
    # A flattened mega-line is never a recon row (the Tesla guard).
    mega = " ".join(["Revenue 100 200 300 400"] * 100)
    assert len(mega) > 2000
    assert not _is_lede_recon_row(mega)


def test_recon_row_label_above_values() -> None:
    # Batch 161: the batch-160 label rule also accepts a recon row as
    # the values row below a figure-less label line. The (19) (8) shape
    # is 12.5% dense, so it is a recon row but NOT a data row — this
    # case pins the extension rather than the existing data-row path.
    assert _is_lede_table_label(
        "Impact from foreign currency and inflation",
        "on monetary positions in Mexico and associated undesignated "
        "derivatives (19) (8)",
    )
    # The existing data-row label cases still hold.
    assert _is_lede_table_label(
        "Property-Liability combined ratio",
        "Recorded 96.4 103.4 (7.0) 96.9 109.8 (12.9)",
    )
    # A label above prose is still not a label.
    assert not _is_lede_table_label(
        "Impact from foreign currency and inflation",
        "The company continues to manage currency exposure carefully",
    )


_SRE_LINES = (
    "Sempra Reports First-Quarter 2025 Results",
    "SAN DIEGO, May 8, 2025 — Sempra (NYSE: SRE) today reported "
    "first-quarter 2025 earnings, prepared in accordance with Generally "
    "Accepted Accounting Principles (GAAP), of $906 million or $1.39 per "
    "diluted share, compared to first-quarter 2024 GAAP earnings of $801 "
    "million or $1.26 per diluted share. On an adjusted basis, "
    "first-quarter 2025 earnings were $942 million or $1.44 per diluted "
    "share, compared to $854 million or $1.34 per diluted share in 2024.",
    "“We are pleased to report a solid quarter for Sempra, which is the "
    "direct result of continued focus on delivering strong financial "
    "performance while making steady progress on our strategic "
    "initiatives,” said Jeffrey W. Martin, chairman and CEO of Sempra. "
    "“We remain committed to our disciplined growth strategy, which "
    "centers on delivering safer and more reliable energy to the nearly "
    "40 million consumers we serve.”",
    "The reported financial results reflect certain significant items as "
    "described on an after-tax basis in the following table of GAAP "
    "earnings, reconciled to adjusted earnings, for first-quarter 2025 "
    "and 2024.",
    "Impact from foreign currency and inflation on monetary positions "
    "in Mexico (8) 41",
    "Net unrealized losses on interest rate swaps related to Port Arthur "
    "LNG Phase 1 project 9 —",
    "1) See Table A for information regarding non-GAAP financial measures.",
)


def test_sempra_recon_rows_do_not_reach_lede() -> None:
    # Batch 161: the reconciliation rows are skipped and the dateline,
    # quote, and table-intro sentence serve instead. The "1) See Table A"
    # footnote line is out of scope for this batch (2 stored rows
    # DB-wide) and is not asserted either way.
    hl = extract_press_release_highlights(_bare_release_html(*_SRE_LINES))
    assert hl is not None
    assert "first-quarter 2025 earnings were $942 million" in hl
    assert "We are pleased to report a solid quarter for Sempra" in hl
    assert "The reported financial results reflect certain significant" in hl
    assert "(8) 41" not in hl
    assert "Port Arthur LNG Phase 1 project 9" not in hl
    assert "Net unrealized losses on interest rate swaps" not in hl
    assert "Impact from foreign currency and inflation on monetary" not in hl
