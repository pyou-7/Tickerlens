"""Batch 202: results-narrative "X and Outlook" headings end the guidance section.

Batch 200/201 carry-forward: Delta's stored guidance ran through the
results narrative ("Revenue Environment and Outlook", "Cost Performance
and Outlook") to the 4000-char cap, because the vocabulary exemption
in _is_guidance_next_section_heading rejects any heading containing
"outlook"/"guidance" — and the $-carrying quote followers defeated the
follower test (now fixed by batch 201's quote rule). A heading whose
final conjunct is "and Outlook" and whose topic word is a results noun
(Environment/Performance/Results) opens the commentary that FOLLOWS
the guidance table, not the guidance section itself, so it may end the
section, subject to the usual title-case + follower + has-signal gates.

Blast (blast202/g_new vs g_old, 1,699 exhibits): 10 diffs, all DAL,
all pure tail cuts at "Revenue Environment and Outlook", 0 added
paragraphs, 0 None-flips. Every forward figure in the cut quotes is
duplicated in the kept table (revenue 3-6% / 5-7% / 2-4% / low-teens /
mid-teens, margins, EPS ranges); the secondary forward details lost
are capacity growth (3-4% / 5-6%), TRASM (flat to down 2%), geographic
unit revenue, and non-fuel unit-cost direction — commentary detail,
not targets. No other ticker changes.
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


DAL_QUOTE = (
    "“Delta generated record September quarter revenue of $15.2 billion, "
    "up 4.1 percent year-over-year, reflecting the strength of our "
    "diverse, high margin revenue streams and improving Domestic "
    "fundamentals. Over the last 6 weeks, sales trends have accelerated "
    "across all geographies and in every advance purchase window, "
    "positioning Delta to finish the year with momentum. For the December "
    "quarter, we expect total revenue growth of 2 percent to 4 percent "
    "over last year’s record performance,” said Glen Hauenstein, Delta's "
    "president."
)
LUV_BULLET = (
    "•Third quarter 2025 passenger revenues were a third quarter record "
    "of $6.3 billion, a 1.0 percent increase, year-over-year."
)


# --- Unit pins ---------------------------------------------------------


def test_revenue_environment_outlook_with_quote_is_a_section_heading():
    # The DAL shape: a results-narrative heading followed by the CEO
    # quote. The quote follower fires (batch 201); the heading gate
    # now lets a narrative "and Outlook" heading through.
    lines = ["Revenue Environment and Outlook", DAL_QUOTE]
    assert _is_guidance_section_end_follower(lines, 0)
    assert _is_guidance_next_section_heading(lines, 0)


def test_cost_performance_outlook_with_quote_is_a_section_heading():
    lines = [
        "Cost Performance and Outlook",
        "“Our teams continue to deliver for our customers, achieving "
        "operational performance that has led the industry. Non-fuel unit "
        "cost growth was approximately flat compared to prior year,” said "
        "Dan Janki, Delta’s chief financial officer.",
    ]
    assert _is_guidance_next_section_heading(lines, 0)


def test_revenue_results_outlook_colon_with_bullet_is_a_section_heading():
    # The LUV shape: colon-ended narrative heading + results bullet.
    lines = ["Revenue Results and Outlook:", LUV_BULLET]
    assert _is_guidance_section_end_follower(lines, 0)
    assert _is_guidance_next_section_heading(lines, 0)


def test_guidance_and_outlook_with_quote_still_exempt():
    # "Guidance and Outlook" is the guidance section's own heading —
    # no results noun, so the carve-out never matches it.
    lines = ["Guidance and Outlook", DAL_QUOTE]
    assert not _is_guidance_next_section_heading(lines, 0)


def test_bare_outlook_headings_still_exempt():
    # Pure outlook headings never match the narrative shape: no
    # "and Outlook" tail, or the topic word is not a results noun.
    for heading in ["2025 Outlook", "Financial Outlook", "Full Year 2026 Outlook"]:
        lines = [heading, DAL_QUOTE]
        assert not _is_guidance_next_section_heading(lines, 0)


def test_dicks_commentary_outlook_still_exempt():
    # DKS's "Foot Locker Business: Q4 2025 Commentary & Outlook" is
    # genuine outlook content (Foot Locker Q4 expectations follow it):
    # colon prefix, period label, "Commentary", "&" — none of the
    # narrative shape matches, so it stays exempt.
    lines = [
        "Foot Locker Business: Q4 2025 Commentary & Outlook",
        "The Company is taking strategic actions to address the "
        "challenges in the Foot Locker business and expects Q4 2025 "
        "operating profit for Foot Locker to be slightly negative.",
    ]
    assert not _is_guidance_next_section_heading(lines, 0)


def test_narrative_outlook_heading_with_table_follower_is_not_a_section_heading():
    # The follower gate still applies: a narrative heading followed by
    # a bare table row label (not a bullet, quote, dateline or long
    # prose line) never ends the section — the table after it is still
    # guidance.
    lines = ["Revenue Environment and Outlook", "Total Revenue"]
    assert not _is_guidance_section_end_follower(lines, 0)
    assert not _is_guidance_next_section_heading(lines, 0)


def test_narrative_outlook_heading_with_short_quote_is_not_a_section_heading():
    # Under 60 chars: a pull-quote fragment, not a section's opening
    # paragraph — the batch-201 quote floor still applies.
    lines = ["Revenue Environment and Outlook", "“We are pleased with our progress.”"]
    assert not _is_guidance_section_end_follower(lines, 0)
    assert not _is_guidance_next_section_heading(lines, 0)


# --- Real-exhibit pins -------------------------------------------------


def test_dal_2025_09_30_narrative_tail_cut():
    g = _guidance("DAL_2025-09-30.html")
    assert "Revenue Environment and Outlook" not in g
    assert "Cost Performance and Outlook" not in g
    assert "record September quarter revenue" not in g
    assert "Total Revenue YoY" in g
    assert "Up 2% - 4%" in g
    assert "$1.60 - $1.90" in g
    # Batch 233: the "2Adjusted debt to EBITDAR" footnote definition
    # is dropped with the rest of Delta's footnotes, so the key is
    # gone rather than present.
    assert "2Adjusted debt to EBITDAR" not in g


def test_dal_2025_12_31_narrative_tail_cut_keeps_cost_prose():
    # The MRO / non-fuel-unit-cost prose sits BEFORE the narrative
    # heading, so it is kept: it is the quarter's cost guidance.
    g = _guidance("DAL_2025-12-31.html")
    assert "Revenue Environment and Outlook" not in g
    assert "Cost Performance and Outlook" not in g
    assert "record revenue of $58.3 billion" not in g
    assert "Total Revenue YoY" in g
    assert "Up 5% - 7%" in g
    assert "non-fuel unit cost growth in line with its long-term financial framework" in g


def test_dal_2026_06_30_narrative_tail_cut():
    g = _guidance("DAL_2026-06-30.html")
    assert "Revenue Environment and Outlook" not in g
    assert "Cost Performance and Outlook" not in g
    assert "Up Mid-Teens" in g
    assert "$2.00 - $2.50" in g
    assert "11% - 13%" in g


def test_dal_2024_12_31_wrapped_heading_unchanged():
    # Regression pin: this quarter's narrative heading wraps across two
    # flattened lines ("Revenue Environment" / "and Outlook"), so the
    # single-line shape never matches and the extraction is unchanged
    # (the 30-line budget already stops it at the wrapped heading).
    g = _guidance("DAL_2024-12-31.html")
    assert "Greater than $7.35 per share" in g or "greater than $7.35 per share" in g
    assert "Up 7% - 9%" in g
