"""Batch 245 regression tests.

One extractor fix: a bare "Fiscal YYYY" Highlights heading is the
full-year section. Autodesk heads its annual section "Fiscal 2025
Financial Highlights" — no "year" word, no "FY" prefix — so the
batch-244 scope regex missed it, scope read "other", and the
full-year section (denser: 12 figure lines vs the quarter's 7) won
over the quarter section on all 7 ADSK rows, serving annual figures
($6.13B revenue, $5.12 EPS) on quarterly rows. The scope rule still
only fires when a quarter-scoped candidate financially qualifies,
and the quarter check still runs first, so a "Fiscal YYYY ...
Quarter" heading still reads quarter.
"""
from tickerlens.data.filings import (
    _extract_highlights_section,
    _highlights_section_scope,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

_Q4 = [
    "Fourth Quarter Fiscal 2025 Financial Highlights",
    "• Total revenue increased 12 percent to $1.64 billion;",
    "• GAAP operating margin was 22 percent, compared to 21 percent;",
    "• Non-GAAP operating margin was 37 percent, compared to 36 percent;",
    "• GAAP income from operations was $366 million, compared to $315 million;",
    "• Non-GAAP income from operations was $608 million, compared to $522 million;",
    "• GAAP diluted EPS was $1.40; Non-GAAP diluted EPS was $2.29;",
    "• Cash flow from operating activities was $692 million; free cash flow was $678 million.",
    # The real ADSK section runs on past the bullets: the CEO/CFO
    # quotes, the restructuring prose, the "Additional Financial
    # Details" sub-head and its billings bullet fill the section's
    # 12-follow-line budget, so the full-year heading that follows
    # is outside the section (mirrors the real doc, where a results
    # table sits between the sections). The stored ADSK rows are
    # byte-identical to this 12-line section body.
    "“Autodesk is focused on the convergence of design and make in the cloud, enabled by platform, industry clouds, and AI.”",
    "“The fourth quarter and full year fiscal 25 results are strong,” said Janesh Moorjani, Autodesk CFO.",
    "Following a review of our business, Autodesk has announced today a worldwide restructuring plan.",
    "Fourth Quarter Fiscal 2025 Additional Financial Details",
    "• Total billings increased 23 percent to $2.11 billion.",
]
_FY = [
    "Fiscal 2025 Financial Highlights",
    "• Total billings increased 16 percent to $6.00 billion.",
    "• Total revenue was $6.13 billion, an increase of 12 percent as reported, and 13 percent on a constant currency basis. Recurring revenue represents 97 percent of total.",
    "• Design revenue was $5.10 billion, an increase of 10 percent as reported, and 11 percent on a constant currency basis.",
    "• Make revenue was $654 million, an increase of 25 percent as reported, and 26 percent on a constant currency basis.",
    "• Subscription plan revenue was $5.72 billion, an increase of 12 percent as reported, and 13 percent on a constant currency basis.",
    "• Total subscriptions increased approximately 516 thousand to 7.79 million. Total subscriptions adjusted for the multi-user trade-in increased approximately 471 thousand to 7.18 million.",
    "• GAAP income from operations was $1.35 billion, compared to $1.13 billion. GAAP operating margin was 22 percent, up 1 percentage point.",
    "• Total non-GAAP income from operations was $2.23 billion, compared to $1.96 billion. Non-GAAP operating margin was 36 percent, flat compared to the prior period.",
    "• GAAP diluted net income per share was $5.12, compared to $4.19.",
    "• Non-GAAP diluted net income per share was $8.47, compared to $7.60.",
    "• Cash flow from operating activities increased to $1.61 billion, compared to $1.31 billion. Free cash flow increased to $1.57 billion, compared to $1.28 billion.",
]


def test_section_scope_bare_fiscal_year() -> None:
    assert _highlights_section_scope("Fiscal 2025 Financial Highlights") == "fullyear"
    assert _highlights_section_scope("FISCAL 2026 HIGHLIGHTS") == "fullyear"
    # The quarter word still wins when both are present, either order.
    assert (
        _highlights_section_scope("Fourth Quarter Fiscal 2025 Financial Highlights")
        == "quarter"
    )
    assert (
        _highlights_section_scope("Fiscal 2025 Fourth Quarter Financial Highlights")
        == "quarter"
    )
    # The pre-existing forms are unchanged.
    assert _highlights_section_scope("2024 FULL YEAR HIGHLIGHTS") == "fullyear"
    assert _highlights_section_scope("Fiscal Year 2025 Highlights") == "fullyear"
    assert _highlights_section_scope("FY 2025 Highlights") == "fullyear"
    assert _highlights_section_scope("Company Highlights") == "other"
    # A bare year alone is NOT a scope word — only the "Fiscal YYYY"
    # form counts; a "2025 Financial Highlights" heading on a
    # quarterly release must not be demoted on the year alone.
    assert _highlights_section_scope("2025 Financial Highlights") == "other"


def test_quarter_section_beats_bare_fiscal_year_section() -> None:
    # ADSK shape: the FY section has MORE figure lines (11 vs 7),
    # so density alone picks it — the scope rule must pick the Q4 one.
    best = _extract_highlights_section(_Q4 + _FY)
    assert best is not None
    joined = "\n".join(best)
    assert "Total revenue increased 12 percent to $1.64 billion" in joined
    assert "Total revenue was $6.13 billion" not in joined


def test_bare_fiscal_year_section_wins_when_alone() -> None:
    best = _extract_highlights_section(_FY)
    assert best is not None
    assert "Total revenue was $6.13 billion" in "\n".join(best)


def test_full_pipeline_picks_quarter_figures_over_bare_fiscal_year() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "AUTODESK, INC. ANNOUNCES FISCAL 2025 FOURTH QUARTER AND FULL-YEAR RESULTS",
            *_Q4,
            *_FY,
        )
    )
    assert hl is not None
    assert "$1.64 billion" in hl
    assert "$6.13 billion" not in hl
    assert "$1.40" in hl
    assert "$5.12" not in hl
