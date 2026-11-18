"""Batch 272 regression tests.

The DRI same-restaurant-sales table, fixed here: Darden's Q1-Q3
releases head their Highlights section with a trailing comparison
clause ("Second Quarter 2025 Financial Highlights, Comparisons
Versus Same Fiscal Quarter Last Year"), which the old section
anchor never matched — it required "highlights" at end-of-line.
The releases fell to the lede, which drops the mini-table under
a dangling "Same-restaurant sales:" opener. The anchor now
accepts a short, unterminated comparisons-versus tail, so the
section path serves the table rows exactly as the stored rows
have them (including the split label/value pairs and the footnote
lines).

- Anchor positives/negatives: the DRI heading shape anchors;
  Chipotle's "<period> highlights, year over year:" does NOT —
  the first form of this fix included it, but the blast proved
  it a regression (the CMG sections serve long prose and drop
  the all-caps summary sub-headlines the lede served, so 8 of 9
  stored CMG rows would newly refuse the gates as loss), so the
  year-over-year tail is pinned out. Prose that merely mentions
  highlights (AIG's non-GAAP boilerplate, Airbnb's letter prose,
  Salesforce's pointer sentence) never anchors.
- End-to-end on cached exhibits: DRI Q2 FY2025 serves all 5
  table rows plus the footnote lines; DRI Q1 FY2026 serves the
  split pairs; DRI Q4 FY2025 (already section-served) and CMG
  Q4 FY2025 are pinned unchanged.
- norm(): the footnote-key glue now also fires before a comma
  ("Bahama Breeze brand 2," vs live "brand2," — Darden x2), the
  same spacing-only class as batch 242; years and decimals still
  never collapse.

Blast radius: exactly 8 rows move in the 1,699-exhibit cache —
all DRI, no other ticker; the 5 stored DRI rows re-sync via S4,
census B 1108 -> 1113, SKIP-loss 98 -> 93.
"""
import os
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm
from tickerlens.data.filings import (
    _HIGHLIGHTS_SECTION_ANCHOR_RE,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _anchors(ln: str) -> bool:
    return bool(_HIGHLIGHTS_SECTION_ANCHOR_RE.search(ln))


# --- Anchor: comparisons-versus tail --------------------------------------

_ANCHOR_POSITIVES = (
    "Second Quarter 2025 Financial Highlights, Comparisons Versus Same Fiscal Quarter Last Year",
    "First Quarter 2026 Financial Highlights, Comparisons Versus Same Fiscal Quarter Last Year",
    "Third Quarter 2025 Financial Highlights, Comparisons Versus Same Fiscal Quarter Last Year",
    "Second Quarter 2025 Financial Highlights, Comparison Versus Same Fiscal Quarter Last Year",
    "Fourth Quarter 2025 Financial Highlights",
    "Fiscal 2025 Financial Highlights",
    "Highlights",
    "HIGHLIGHTS OF SEGMENT RESULTS",
)


def test_anchor_comparison_tail_positives():
    for ln in _ANCHOR_POSITIVES:
        assert _anchors(ln), ln


_ANCHOR_NEGATIVES = (
    # The narrowed rule: Chipotle's year-over-year tail stays out —
    # the blast proved anchoring it a regression (CMG sections serve
    # long prose and drop the summary sub-headlines).
    "Fourth quarter highlights, year over year:",
    "First quarter highlights, year over year:",
    "Full year 2025 highlights, year over year:",
    # Prose that merely mentions highlights — long or terminated.
    "Throughout this press release, including the financial highlights, AIG presents its financial condition and results of operations in the way it believes will be most meaningful.",
    "driven by a number of positive business highlights: \u2022 Guest demand remains strong.",
    "To learn more about our newest innovations and product release highlights, including our latest Spring 2025 Product Release, visit: www.salesforce.com/releases.",
    "consideration gap and accelerate penetration levels. Regional highlights, including our expansion markets, are as follows:",
    # A terminated comparison tail is prose, not a heading.
    "Second Quarter 2025 Financial Highlights, Comparisons Versus Same Fiscal Quarter Last Year. The company reported strong results.",
)


def test_anchor_comparison_tail_negatives():
    for ln in _ANCHOR_NEGATIVES:
        assert not _anchors(ln), ln


# --- End-to-end on cached exhibits ----------------------------------------

def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        html = fh.read()
    return extract_press_release_highlights(html) or ""


def test_dri_q2_fy2025_serves_table_and_footnotes():
    live = _live("DRI_2024-11-24")
    assert "Consolidated Darden* 2.4%" in live
    assert "Olive Garden 2.0%" in live
    assert "LongHorn Steakhouse 7.5%" in live
    assert "Fine Dining** (5.8)%" in live
    assert "Other Business* 0.7%" in live
    # The dangling opener is gone: the table follows it, and the
    # footnote lines ride the section as the stored row has them.
    assert "\u2022 Same-restaurant sales:\nConsolidated Darden* 2.4%" in live
    assert "* Will not include Chuy's until they have been owned" in live
    assert "Darden includes Ruth's Chris for the month of November only" in live
    # The lede leftovers are gone: no dateline, no section heading.
    assert "ORLANDO, Fla." not in live
    assert "Comparisons Versus Same Fiscal Quarter Last Year" not in live


def test_dri_q1_fy2026_serves_split_table_pairs():
    live = _live("DRI_2025-08-24")
    assert "Consolidated Darden1\n4.7%" in live
    assert "Olive Garden 5.9%" in live
    assert "LongHorn Steakhouse 5.5%" in live
    assert "Fine Dining (0.2)%" in live
    assert "Other Business1\n3.3%" in live
    assert "ORLANDO, Fla." not in live


def test_dri_q4_fy2025_unchanged():
    # Already section-served before this batch; the anchor change
    # must not touch it.
    live = _live("DRI_2025-05-25")
    assert "Consolidated Darden1\n4.6%" in live
    assert "Olive Garden 6.9%" in live
    assert "Other Business1\n1.2%" in live
    assert "Total sales increased 10.6% to $3.3 billion" in live


def test_cmg_q4_fy2025_unchanged():
    # The narrowed rule leaves Chipotle alone: the lede-served
    # sub-headlines stay, the section bullets stay unserved.
    live = _live("CMG_2025-12-31")
    assert "FULL YEAR TOTAL REVENUE INCREASED 5.4% TO $11.9 BILLION" in live
    assert "Operating margin was 16.2%" not in live
    assert "Opened 334 company-owned restaurants" not in live


# --- norm(): footnote-key glue before a comma ------------------------------

def test_norm_glues_footnote_key_before_comma():
    assert norm("Bahama Breeze brand 2, $0.16") == norm(
        "Bahama Breeze brand2, $0.16"
    )
    assert norm("closed restaurant costs 2, adjusted") == norm(
        "closed restaurant costs2, adjusted"
    )
    # The pre-existing shapes still hold.
    assert norm("same-restaurant sales 1 increase") == norm(
        "same-restaurant sales1 increase"
    )
    assert norm("Consolidated Darden 1") == norm("Consolidated Darden1")


def test_norm_year_and_decimal_never_collapse():
    assert norm("Q3 2024") == "Q3 2024"
    assert norm("year 2024") == "year 2024"
    assert norm("up 10 percent") == "up 10 percent"
    assert norm("sales 1") != norm("sales 2")
    # A thousands comma is not a footnote: the digit continues.
    assert norm("revenue of $2,000 million") == "revenue of $2,000 million"
    # A date's day number never glues: "November 6, 2024" must stay
    # spaced, or the dateline predicates the gates run on normed
    # lines stop recognizing it (batch-241 CVS pins).
    assert (
        norm("WOONSOCKET, RHODE ISLAND, November 6, 2024 - CVS Health")
        == "WOONSOCKET, RHODE ISLAND, November 6, 2024 - CVS Health"
    )
    assert norm("February 12, 2025") == "February 12, 2025"
