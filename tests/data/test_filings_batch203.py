"""Batch 203: a section-tagline follower ends the guidance section.

Batch 200 carry-forward: COIN's stored guidance ends on the bare
"Product Update" line. "Product Update" is a real next-section heading,
but its follower is a short tagline ("Building the future of finance,
step by step" — 46 chars, unterminated), and the prose after it is
wrapped, so its first flattened line is a fragment: neither the
long-prose follower test (needs >= 60 chars, terminated, $-less) nor
any other follower shape fires, and the heading is collected as
guidance — the 30-line budget's last slot. The fix adds a tagline
follower to _is_guidance_section_end_follower: a short sentence-case
fragment after a heading, followed by a wrapped prose run that
terminates within 6 lines and totals >= 100 chars, ends the section.
Two run guards keep the join from crossing a guidance table to a
distant disclaimer paragraph: every non-terminating run line must be
>= 50 chars (a wrapped prose line is near column width; a table row
is short) and figure-sparse (at most one $/% character per 25 chars;
a table row is figure-dense). The terminating line is exempt from
both — it is the sentence tail and may be short or carry the
sentence's figures.

Blast (blast203/g_new vs g_old, 1,699 exhibits): 2 diffs, 0
None-flips, 0 added paragraphs — both pure tail cuts. COIN 2025-12-31
drops the bare "Product Update" line (1526 -> 1510); GPC 2023-12-31
cuts the results narrative at "Fourth Quarter 2023 Segment
Highlights" (4007 -> 1786) while keeping the two outlook bullets
(Revenue Growth 3% to 5%, Adjusted Diluted EPS $9.70 to $9.90). The
unguarded version also cut BMY 2024-06-30 (2277 -> 388, losing the
Diluted EPS $0.60-$0.90 row), EL 2026-06-30 (2256 -> 531, losing the
assumptions bullets and the 12.7%-13.5% margin target), BMY
2024-03-31 and V 2023-09-30 (trailing table-row labels); the run
guards kill all four, and all four are pinned unchanged below.
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


COIN_TAGLINE = "Building the future of finance, step by step"
COIN_PROSE = [
    "We delivered record highs across the board for product performance in 2025, including for Coinbase Total",
    "Trading Volume, Coinbase Crypto Trading Volume Market Share, Average USDC Held in Coinbase Products,",
    "and for our growing derivatives business. We now have 12 products generating over $100 million in annualized",
    "revenue.",
]


# --- Unit pins ---------------------------------------------------------


def test_coin_product_update_with_tagline_is_a_section_heading():
    # The COIN shape: title-case heading + short sentence-case tagline
    # + wrapped prose that terminates within 4 lines (carrying $100M).
    lines = ["Product Update", COIN_TAGLINE] + COIN_PROSE
    assert _is_guidance_section_end_follower(lines, 0)
    assert _is_guidance_next_section_heading(lines, 0)


def test_coin_money_tagline_single_line_prose_is_a_section_heading():
    # COIN 2025-09-30's tagline ("Building the future of money, step
    # by step") followed by a single long terminated prose line.
    lines = [
        "Product Update",
        "Building the future of money, step by step",
        "We see crypto adoption unfolding in 3 phases: people first invest through trading, then use financial services, "
        "and ultimately engage with a rich app ecosystem.",
    ]
    assert _is_guidance_section_end_follower(lines, 0)
    assert _is_guidance_next_section_heading(lines, 0)


def test_gpc_segment_highlights_with_tagline_is_a_section_heading():
    # The GPC shape: results-section heading + sub-label tagline +
    # wrapped results prose.
    lines = [
        "Fourth Quarter 2023 Segment Highlights",
        'Automotive Parts Group ("Automotive")',
        "Global Automotive sales were $3.5 billion, up 0.8% from the same period in 2022, with a 2.9% benefit from acqu",
        "isitions, 0.6% favorable impact of foreign currency and other, partially offset by a 2.7% decrease in comparable sales.",
    ]
    assert _is_guidance_section_end_follower(lines, 0)
    assert _is_guidance_next_section_heading(lines, 0)


def test_bmy_table_row_label_with_figure_dense_run_is_not_a_section_heading():
    # The BMY 2024-06-30 false positive (unguarded version): the run
    # after the "Low single-digit increase No Change" tagline starts
    # with a 38-char figure-dense table row, so the join is a table,
    # not prose — the Diluted EPS row must survive.
    lines = [
        "Operating Expenses1",
        "Low single-digit increase No Change",
        "Other income/(expense) ~($250M) ~($50M)",
        "Effective tax rate ~69% ~66%",
        "Diluted EPS $0.40 - $0.70 $0.60 - $0.90",
        "The 2024 financial guidance excludes the impact of any potential future strategic acquisitions, divestitures, "
        "specified items that have not yet been identified and quantified, and the impact of future Acquired IPRD charges.",
    ]
    assert not _is_guidance_section_end_follower(lines, 0)
    assert not _is_guidance_next_section_heading(lines, 0)


def test_el_table_run_with_figure_dense_row_is_not_a_section_heading():
    # The EL 2026-06-30 false positive (unguarded version): the run
    # reaches a 68-char row carrying four $/% tokens, so the join is
    # a table — the assumptions bullets must survive.
    lines = [
        "Non-GAAP",
        "Restructuring and other charges .50 - .58 1.83",
        "Securities class action litigation settlements — .18",
        "Forecasted/Adjusted EPS - Non-GAAP $3.10 - $3.35 $ 2.51 24% - 34%",
        "Impact of foreign currency translation (.04)",
        "Forecasted/Adjusted Constant Currency EPS - Non-GAAP $3.06 - $3.31 $ 2.51 22% - 32%",
        "The Company has reflected the following assumptions in its fiscal 2027 full-year outlook:",
    ]
    assert not _is_guidance_section_end_follower(lines, 0)
    assert not _is_guidance_next_section_heading(lines, 0)


def test_mco_short_colon_pointer_run_is_not_a_section_heading():
    # The run terminates on an 82-char colon-ended pointer, under the
    # 100-char floor — a list pointer, not a prose paragraph.
    lines = [
        "MA Organic Constant Currency Revenue",
        "Increase in the high-single-digit percent range",
        "The following reconciles the drivers of projected MCO Operating Expense growth:",
    ]
    assert not _is_guidance_section_end_follower(lines, 0)
    assert not _is_guidance_next_section_heading(lines, 0)


def test_dow_cash_flow_heading_with_money_tagline_is_not_a_section_heading():
    # A $-carrying immediate follower is a table row, never a tagline.
    lines = [
        "Operating Activities",
        "Net income $ 660 $ 4,640",
        "Adjustments to reconcile net income to net cash provided by operating activities:",
    ]
    assert not _is_guidance_section_end_follower(lines, 0)
    assert not _is_guidance_next_section_heading(lines, 0)


def test_title_case_tagline_is_not_a_section_heading():
    # A title-case follower is a second heading/label, not a tagline.
    lines = [
        "Chief Revenue Officer: Colin M. McLean",
        "Investor Relations",
        "To request more information or to be added to our e-mail distribution list, please visit the Investor Relations "
        "section of our website.",
    ]
    assert not _is_guidance_section_end_follower(lines, 0)
    assert not _is_guidance_next_section_heading(lines, 0)


def test_short_quote_tagline_still_not_a_section_heading():
    # The batch-202 pinned negative still holds: a short quote is not
    # a tagline, and with no prose run after it nothing fires.
    lines = ["Revenue Environment and Outlook", "“We are pleased with our progress.”"]
    assert not _is_guidance_section_end_follower(lines, 0)
    assert not _is_guidance_next_section_heading(lines, 0)


# --- Real-exhibit pins -------------------------------------------------


def test_coin_2025_12_31_product_update_cut():
    g = _guidance("COIN_2025-12-31.html")
    assert "Product Update" not in g
    assert "Building the future of finance" not in g
    assert "USDC rewards." in g
    assert "$550-$630 million" in g
    assert "$925-$975 million" in g
    assert "$420 million of transaction revenue" in g


def test_gpc_2023_12_31_segment_highlights_cut():
    g = _guidance("GPC_2023-12-31.html")
    assert "Segment Highlights" not in g
    assert "Balance Sheet, Cash Flow and Capital Allocation" not in g
    assert "Full-Year 2023 Results" not in g
    assert "Revenue Growth of 3% to 5%" in g
    assert "$9.70 to $9.90" in g


def test_bmy_2024_06_30_guidance_table_unchanged():
    # Regression pin: the unguarded tagline rule cut this quarter's
    # guidance table at "Operating Expenses1" (2277 -> 388). The run
    # guards keep the full table.
    g = _guidance("BMY_2024-06-30.html")
    assert "Operating Expenses1" in g
    assert "$0.60 - $0.90" in g
    assert "Effective tax rate" in g
    assert "The 2024 financial guidance excludes the impact" in g


def test_el_2026_06_30_assumptions_unchanged():
    # Regression pin: the unguarded tagline rule cut this quarter's
    # assumptions section at "Non-GAAP" (2256 -> 531).
    g = _guidance("EL_2026-06-30.html")
    assert "Forecasted/Adjusted EPS - Non-GAAP $3.10 - $3.35" in g
    assert "Adjusted operating margin of 12.7% to 13.5%" in g
    assert "Organic net sales growth of 3% to 5%" in g


def test_bmy_2024_03_31_row_label_unchanged():
    # Regression pin: the unguarded tagline rule dropped this
    # quarter's trailing "Operating Expenses1" row label (1117 -> 1096).
    g = _guidance("BMY_2024-03-31.html")
    assert "Operating Expenses1" in g


def test_v_2023_09_30_row_label_unchanged():
    # Regression pin: the unguarded tagline rule dropped this
    # quarter's trailing "Constant-Dollar Basis(5)" row label.
    g = _guidance("V_2023-09-30.html")
    assert "Constant-Dollar Basis(5)" in g
