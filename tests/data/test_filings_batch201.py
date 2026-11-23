"""Batch 201: generalize the quote-led guidance section-end follower
beyond colon-ended headings.

Batch 200's carry-forward: Carnival's 2024-11-30 live guidance still
carried the "Financing and Capital Activity" section — its quote
follower is a complete 442-char paragraph carrying $ figures, so
neither the terminated-prose test (needs $-less) nor the colon+quote
rule (needs a colon-ended heading) fired. A quotation after a heading
is a speaker statement, not guidance prose: a quote-led follower now
ends the section when it opens with a quote, is >= 60 chars, and its
first cased char is uppercase — regardless of $/% or termination.
The heading gate (title-case, no guidance vocabulary, no period
label) still applies. The batch-200 pinned negative (non-colon
heading + wrapped quote) is superseded by this rule.

Blast (blast201/g_new vs g_old, 1,699 exhibits): 9 diffs, all CCL,
all pure tail cuts, 0 added paragraphs, 0 None-flips. Cut headings:
"Financing and Capital Activity" x3, "Financing" x3, "Capital
Allocation" x2, "Successful Early Completion of Refinancing Plan
Enables Dividend Reinstatement" x1. No guidance content lost.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_guidance_next_section_heading,
    _is_guidance_section_end_follower,
    extract_management_guidance,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _guidance(name: str) -> str:
    g = extract_management_guidance(_load(name))
    assert g is not None
    return g


CCL_QUOTE = (
    "“With the benefit of well managed near term maturity towers and "
    "improved leverage metrics, we expect to opportunistically capitalize "
    "on improved interest rates while proactively managing our maturity "
    "towers for 2027 and beyond. In 2025, interest expense is currently "
    "expected to be over $200 million lower than 2024 and over $500 "
    "million lower compared to 2023,” commented Carnival Corporation & "
    "plc’s Chief Financial Officer David Bernstein."
)
WRAPPED_QUOTE = (
    "“Our performance in Q3 demonstrates the progress we’ve made against "
    "our four strategic priorities across our creative studios, streaming, "
    "sports, and"
)


def test_non_colon_heading_figure_quote_is_a_section_heading():
    # The CCL shape: a complete quote paragraph carrying $ figures
    # after a non-colon heading — the terminated-prose test never
    # fires on it (it needs $-less), and neither did the colon+quote
    # rule (no colon). The quote follower now ends the section.
    lines = ["Financing and Capital Activity", CCL_QUOTE]
    assert _is_guidance_section_end_follower(lines, 0)
    assert _is_guidance_next_section_heading(lines, 0)


def test_non_colon_heading_wrapped_quote_is_a_section_heading():
    # Supersedes the batch-200 pinned negative: a wrapped quote
    # fragment after a non-colon heading is now a follower too.
    lines = ["Message From Our CEO", WRAPPED_QUOTE]
    assert _is_guidance_section_end_follower(lines, 0)
    assert _is_guidance_next_section_heading(lines, 0)


def test_short_quote_follower_is_not_a_section_heading():
    # Under 60 chars: a pull-quote fragment, not a section's opening
    # paragraph.
    lines = ["Financing and Capital Activity", "“We are pleased with our progress.”"]
    assert not _is_guidance_section_end_follower(lines, 0)
    assert not _is_guidance_next_section_heading(lines, 0)


def test_lowercase_quote_follower_is_not_a_section_heading():
    # First cased char lowercase: a mid-sentence quote continuation,
    # not a new section's opening paragraph.
    lines = [
        "Financing and Capital Activity",
        "“looking forward, we expect to continue reducing our debt balances "
        "while investing in our fleet and returning capital to shareholders "
        "through dividends and share repurchases over time.”",
    ]
    assert not _is_guidance_section_end_follower(lines, 0)
    assert not _is_guidance_next_section_heading(lines, 0)


def test_guidance_word_heading_with_quote_still_exempt():
    # A guidance sub-heading followed by a quote is still guidance,
    # never a section end — the heading gate decides, not the follower.
    lines = ["Full Year 2026 Outlook", CCL_QUOTE]
    assert not _is_guidance_next_section_heading(lines, 0)


def test_period_label_heading_with_quote_still_exempt():
    lines = ["Fourth Quarter 2025", CCL_QUOTE]
    assert not _is_guidance_next_section_heading(lines, 0)


# --- Real-exhibit pins -------------------------------------------------


def test_ccl_2024_11_30_financing_tail_cut():
    g = _guidance("CCL_2024-11-30.html")
    assert "Financing and Capital Activity" not in g
    assert "debt prepayments of $3.3 billion" not in g
    assert "Adjusted ROIC of approximately 11.7 percent" in g
    assert "See “Guidance”" in g


def test_ccl_2023_11_30_financing_tail_cut():
    g = _guidance("CCL_2023-11-30.html")
    assert "Financing and Capital Activity" not in g
    assert "debt payments of $6 billion" not in g
    assert "Adjusted cruise costs excluding fuel" in g


def test_ccl_2025_11_30_refinancing_tail_cut():
    g = _guidance("CCL_2025-11-30.html")
    assert "Successful Early Completion of Refinancing Plan" not in g
    assert "convertible notes" not in g
    assert "See “Guidance”" in g


def test_ccl_2026_05_31_capital_allocation_tail_cut():
    g = _guidance("CCL_2026-05-31.html")
    assert "Capital Allocation" not in g
    assert "share buyback" not in g
    assert "See “Guidance”" in g


def test_ccl_2024_02_29_still_clean():
    # Regression pin: this quarter already ended at the pointer line
    # before batch 201; the wider rule must not change it.
    g = _guidance("CCL_2024-02-29.html")
    assert "Financing and Capital Activity" not in g
    assert "Adjusted EBITDA of approximately $5.63 billion" in g
    assert "See “Guidance”" in g
