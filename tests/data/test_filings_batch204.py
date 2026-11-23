"""Batch 204: the guidance line budget is a backstop, not a guillotine —
plus a mid-line sentence boundary in the tagline follower run.

Batch 203 carry-forward: COIN 2024-09-30 through 2025-06-30 guidance is
truncated mid-prose by the 30-line budget (sales-and-marketing commentary
tails and the Deribit exclusion note are lost — budget starvation, needs a
budget rethink; COIN 2025-09-30 also ends mid-sentence). The fix has two
parts. (1) Budget lookahead: when the 30-line budget is hit, the collector
keeps going for up to 20 more kept lines, but only keeps them if a
section-end break fires inside the window; if no break fires — or the
document runs out — the extra lines are discarded and the 30-line cut
stands. A runaway section (no end in sight — CSCO, ELV) therefore still
stops at 30 lines, while a section that ends just past the cut (COIN's
"Webcast Information" 6–8 lines out, ADP's "Investor Webcast Today" ~20
lines out) completes. (2) Mid-line sentence boundary in the tagline
follower run: COIN 2025-09-30's "Product Update" prose wraps so the first
sentence ends mid-line ("... rich app ecosystem. Coinbase is building
..."), and the line-end termination test never fires, so the 6-line run
expires unterminated and the heading is collected as guidance. A mid-line
boundary (lowercase letter + terminal punctuation + space + uppercase)
now terminates the run; abbreviations ("U.S. GAAP", "No. 1") never match,
and the check runs after the run guards, so a figure-dense line is still
killed as a table row instead of terminating.

Blast (blast204/g_new vs blast203/g_new, 1,699 exhibits): 66 diffs, 0
None-flips — all pure extensions. Genuine completions: COIN x5 (the S&M
ranges, the Deribit note, the mid-sentence tails), ADP x12 (the full
outlook table to the "Net Impact from Client Funds Extended Strategy"
row), AMT x5 (the capital-expenditures outlook table), BMY 2024-03-31
(the full guidance table + disclaimer), EL x5 (assumptions bullets and
EPS-bridge rows), CCI x7 (AFFO table + outlook bullets), AKAM, CLX, CPB,
DKS x2, MCO x2, V, ACN x4, EMR. Deepened pre-existing bleeds (NOT
repaired): DELL x7, ECL x4, DASH 2026-09-30 — those sections already run
into results tables inside the 30-line budget, and the lookahead extends
the bleed to the next section end; fixing the bleed needs a
results-boundary detector in the main loop (carried forward).
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


def _synthetic_doc(lines: list[str]) -> str:
    return "<html><body>" + "".join(f"<p>{ln}</p>" for ln in lines) + "</body></html>"


def _prose_line(n: int) -> str:
    # A long, figure-sparse, unterminated wrapped-prose line.
    return (
        f"Wrapped guidance prose line number {n} carrying onward commentary about "
        "the outlook for the coming quarters and the drivers behind it"
    )


# --- Tagline follower: mid-line sentence boundary ----------------------


def test_coin_money_tagline_midline_boundary_is_a_section_heading():
    # COIN 2025-09-30's real shape: the sentence after the tagline ends
    # mid-line ("... rich app ecosystem. Coinbase is building ..."), so
    # the line-end test never fires and the old run expires unterminated.
    lines = [
        "Product Update",
        "Building the future of money, step by step",
        "We see crypto adoption unfolding in 3 phases: people first invest through trading, then use financial services,",
        "and ultimately engage with a rich app ecosystem. Coinbase is building for every step. We provide a trusted",
        "venue for individuals and institutions to trade and custody assets, the first step in bringing people onchain.",
    ]
    assert _is_guidance_section_end_follower(lines, 0)
    assert _is_guidance_next_section_heading(lines, 0)


def test_us_gaap_abbreviation_does_not_end_tagline_run():
    # Guard pin: the only mid-line ". " + uppercase in the run is the
    # "U.S. GAAP" abbreviation, which the mid-line boundary must not
    # match — the run expires unterminated and the heading is not a
    # section end. (Passes on old code too: the line-end test never
    # fires on these lines either.)
    lines = [
        "Product Update",
        "Building the future of money, step by step",
        "We see U.S. GAAP to Non-GAAP figures in the table below and the",
        "reconciliation that follows them in the appendix to this release",
        "with further detail on each adjustment and its treatment in the",
        "notes that accompany the condensed consolidated statements here",
        "and in the prior year presentation for comparison purposes only",
        "as filed with the commission in the annual report on Form 10-K",
    ]
    assert not _is_guidance_section_end_follower(lines, 0)
    assert not _is_guidance_next_section_heading(lines, 0)


def test_coin_2025_09_30_product_update_cut_by_midline_boundary():
    # Real exhibit: the budget cut lands one line short of the sentence
    # end ("as a result of our"), and the old follower never fires on
    # "Product Update" because the prose run expires unterminated.
    g = _guidance("COIN_2025-09-30.html")
    assert "recent acquisitions." in g
    assert "Product Update" not in g
    assert "Building the future of money" not in g
    assert "$70 million of total depreciation and amortization" in g


# --- Budget lookahead: genuine completions -----------------------------


def test_coin_2024_09_30_lookahead_completes_sales_marketing_range():
    g = _guidance("COIN_2024-09-30.html")
    assert "$170-$220 million" in g
    assert "As such, we are continuing to provide a wide range to capture all market conditions." in g
    assert "Webcast Information" not in g


def test_coin_2024_12_31_lookahead_completes_mid_sentence_cut():
    g = _guidance("COIN_2024-12-31.html")
    assert "Since mid-Q4, we have" in g
    assert "seen a significant increase in marketing opportunities" in g
    assert "For reference, this was approximately 35% of sales and marketing expenses in Q4." in g
    assert "Webcast Information" not in g


def test_coin_2025_06_30_lookahead_keeps_deribit_note():
    g = _guidance("COIN_2025-06-30.html")
    assert "$190-$290 million" in g
    assert "This outlook does not include costs related to our acquisition of Deribit." in g
    assert "Webcast Information" not in g


def test_adp_2023_12_31_lookahead_completes_outlook_table():
    g = _guidance("ADP_2023-12-31.html")
    assert "Net Impact from Client Funds Extended Strategy $730M $850 to $870M $835 to $845M" in g
    assert "Adj. Diluted EPS $8.23 10 to 12% 10 to 12%" in g
    assert "Investor Webcast Today" not in g


def test_adp_2024_09_30_lookahead_completes_outlook_table():
    g = _guidance("ADP_2024-09-30.html")
    assert "Net Impact from Client Funds Extended Strategy $879M $1,000 to $1,020M $1,000 to $1,020M" in g
    assert "Investor Webcast Today" not in g


# --- Budget lookahead: the backstop still holds ------------------------


def test_csco_runaway_section_still_stops_at_budget():
    # Batch 212: the old premise (no section end in sight, 80 lines of
    # dividend/repurchase prose, 30-line budget cut) was an artifact of
    # the teaser anchor — the collector anchored on the "guidance range"
    # teaser in the highlights area and ran away through the results.
    # The teaser-anchor fix anchors on the real "Guidance" section,
    # which ends legitimately at the "Reconciliations of GAAP to
    # Non-GAAP Measures" heading: 16 blocks, complete Q2 FY 2025
    # table, no dividend/repurchase/news-summary prose. The budget
    # backstop is still pinned by the SKYD runaway test below and the
    # synthetic lookahead tests. Batch 233: 22 -> 16 blocks as the
    # split table rows fuse to "Label: values".
    g = _guidance("CSCO_2024-10-26.html")
    assert len(g.split("\n\n")) == 16
    assert "Q2 FY 2025" in g
    assert "GAAP to non-GAAP Guidance" in g
    assert "Dividend" not in g
    assert "Repurchase" not in g
    assert "News Summary" not in g


def test_skyd_runaway_section_still_stops_at_budget():
    # SKYD's fragmentary-table section runs 152 lines uncapped.
    # Batch 233: 30 -> 26 blocks as the split rows fuse.
    # Batch 235: 26 -> 22 as the Studios row fuses (5 lines -> 1).
    g = _guidance("SKYD_2026-06-30.html")
    assert len(g.split("\n\n")) == 22


def test_lookahead_keeps_extras_when_section_ends_inside_window():
    # Synthetic: 30-line budget hit, then 5 more prose lines, then a
    # "Webcast Information" section end — the extras survive.
    lines = ["Business Outlook"]
    lines += [f"Guidance line {n} expects revenue growth of 5% to 7% for the year ahead" for n in range(29)]
    lines += [_prose_line(n) for n in range(5)]
    lines += [
        "Webcast Information",
        "We will host a conference call to discuss the results for the quarter today at 2:30 pm PT.",
    ]
    g = extract_management_guidance(_synthetic_doc(lines))
    assert g is not None
    assert "Wrapped guidance prose line number 4" in g
    assert "Webcast Information" not in g


def test_lookahead_discards_extras_when_document_ends():
    # Synthetic: the guidance section is the last thing in the document
    # and runs past the budget with no section end — the while-else
    # path drops the unverified extras and the 30-line cut stands.
    # (Passes on old code too: the budget break stops at 30 lines.)
    lines = ["Business Outlook"]
    lines += [f"Guidance line {n} expects revenue growth of 5% to 7% for the year ahead" for n in range(29)]
    lines += [_prose_line(n) for n in range(6)]
    g = extract_management_guidance(_synthetic_doc(lines))
    assert g is not None
    assert len(g.split("\n\n")) == 30
    assert "Wrapped guidance prose line number 0" not in g
