"""Batch 244 regression tests.

Two parts, one cohort: the highlights sweep's first-diff cohort
(15 rows after batch 243) closes.

1. Extractor — quarter-scoped Highlights sections beat full-year
   ones (AGNC). A Q4 release carries both "FOURTH QUARTER 2024
   FINANCIAL HIGHLIGHTS" (10 figure lines) and "2024 FULL YEAR
   HIGHLIGHTS" (12 figure lines); density alone picks the full-year
   section, but the row is a quarter, so the quarter's figures are
   the right ones. The scope rule only fires when a quarter-scoped
   candidate financially qualifies, so a release whose only financial
   section is the full-year one is untouched.

2. Gate S5 — the wrong-section gate (APO table / CSCO narrative /
   COIN disclaimer / NFLX wrong-section / CART+ANET+EBAY+FTNT
   FY-stored). Each class needs a positive stored shape AND a clean
   live capture; a real highlights block never matches a shape.
"""
import sys

sys.path.insert(0, "scripts")

from batch244_repair import classify_s5, verify_fy_stored
from tickerlens.data.filings import (
    _extract_highlights_section,
    _highlights_section_scope,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

_Q4 = [
    "FOURTH QUARTER 2024 FINANCIAL HIGHLIGHTS",
    "• $(0.11) comprehensive loss per common share, comprised of:",
    "◦ $0.10 net income per common share",
    "◦ $(0.20) other comprehensive loss per common share",
    "• $0.37 net spread and dollar roll income per common share",
    "◦ Excludes $0.06 per common share of catch-up premium amortization",
    "• $8.41 tangible net book value per common share as of December 31, 2024",
    "◦ Decreased $(0.41) per common share, or -4.6%, from September 30, 2024",
    "• $0.36 dividends declared per common share for the fourth quarter",
    "• -0.6% economic return on tangible common equity for the quarter",
    "◦ Comprised of $0.36 dividends and $(0.41) decrease in book value",
]
_FY = [
    "2024 FULL YEAR HIGHLIGHTS",
    "• $0.84 comprehensive income per common share, comprised of:",
    "◦ $0.93 net income per common share",
    "◦ $(0.09) OCI per common share",
    "• $1.88 net spread and dollar roll income per common share",
    "◦ Includes $0.03 per common share of dollar roll income",
    "◦ Excludes $0.06 per common share of catch-up premium amortization",
    "• $1.44 in dividends declared per common share",
    "• 13.2% economic return on tangible common equity for the year, comprised of:",
    "◦ $1.44 dividends per common share",
    "◦ $(0.29) decrease in tangible net book value, or -3.3%, from December 31, 2023",
    "• 8.9% total stock return",
    "• Issued 202.1 million shares of common equity through ATM Offerings",
]


def test_section_scope_words() -> None:
    assert _highlights_section_scope("FOURTH QUARTER 2024 FINANCIAL HIGHLIGHTS") == "quarter"
    assert _highlights_section_scope("Third Quarter Highlights:") == "quarter"
    assert _highlights_section_scope("Q4 2024 Highlights") == "quarter"
    assert _highlights_section_scope("2024 FULL YEAR HIGHLIGHTS") == "fullyear"
    assert _highlights_section_scope("Fiscal Year 2025 Highlights") == "fullyear"
    assert _highlights_section_scope("FY 2025 Highlights") == "fullyear"
    # A combined heading names a quarter, so the quarter word wins.
    assert (
        _highlights_section_scope("FOURTH QUARTER AND FULL YEAR 2024 HIGHLIGHTS")
        == "quarter"
    )
    assert _highlights_section_scope("Company Highlights") == "other"
    assert _highlights_section_scope("OTHER FOURTH QUARTER HIGHLIGHTS") == "quarter"


def test_quarter_section_beats_full_year_section() -> None:
    # AGNC shape: the FY section has MORE figure lines (12 vs 10),
    # so density alone picks it — the scope rule must pick the Q4 one.
    best = _extract_highlights_section(_Q4 + _FY)
    assert best is not None
    assert "$(0.11) comprehensive loss" in "\n".join(best)
    assert "$0.84 comprehensive income" not in "\n".join(best)


def test_full_year_section_wins_when_alone() -> None:
    best = _extract_highlights_section(_FY)
    assert best is not None
    assert "$0.84 comprehensive income" in "\n".join(best)


def test_full_year_wins_when_quarter_section_is_not_financial() -> None:
    # The scope rule only fires when a quarter-scoped candidate
    # financially qualifies; a narrative quarter section must not
    # displace the financial full-year one. (The narrative section
    # needs enough content to clear the collector's 150-char floor,
    # or the collector stops at it and never reaches the FY section.)
    thin_q4 = [
        "FOURTH QUARTER 2024 HIGHLIGHTS",
        "• We welcomed new customers across every region and deepened relationships with our largest partners.",
        "• Our team delivered an outstanding quarter of execution across all of our business lines.",
        "• We enter the new year with strong momentum and a clear plan for continued growth.",
    ]
    best = _extract_highlights_section(thin_q4 + _FY)
    assert best is not None
    assert "$0.84 comprehensive income" in "\n".join(best)


def test_combined_quarter_and_full_year_heading_is_kept() -> None:
    lines = [
        "FOURTH QUARTER AND FULL YEAR 2024 HIGHLIGHTS",
        "• Revenue of $15.3 billion, up 10% year over year, with product revenue up 14% and services revenue down 1%.",
        "• GAAP EPS of $0.80, up 31% year over year, and non-GAAP EPS of $1.04, up 11% year over year.",
        "• GAAP gross margin of 65.0% and non-GAAP gross margin of 67.5%, both above the high end of our guidance range.",
    ]
    best = _extract_highlights_section(lines)
    assert best is not None
    assert "Revenue of $15.3 billion" in "\n".join(best)


def test_full_pipeline_picks_quarter_figures() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "ACME INVESTMENT CORP. ANNOUNCES FOURTH QUARTER 2024 FINANCIAL RESULTS",
            *_Q4,
            *_FY,
        )
    )
    assert hl is not None
    assert "$(0.11) comprehensive loss" in hl
    assert "$0.84 comprehensive income" not in hl


# --- Gate S5 ---------------------------------------------------------------

_APO_LIVE = (
    "Apollo Reports Third Quarter 2024 Results\n"
    "New York, November 5, 2024 — Apollo Global Management, Inc. (NYSE: APO) "
    "today reported results for the third quarter ended September 30, 2024.\n"
    "Marc Rowan, Chief Executive Officer at Apollo said, “Our strong third "
    "quarter results reflect broad-based momentum across the platform.”\n"
    "Apollo issued a full detailed presentation of its third quarter ended "
    "September 30, 2024 results.\n"
    "Apollo Global Management, Inc. has declared a cash dividend of $0.4625 "
    "per share of its Common Stock for the third quarter ended September 30, 2024."
)
_APO_STORED = (
    "Apollo Global Management, Inc. Third Quarter 2024 Earnings\n"
    "3Q'24 Per Share YTD'24 Per Share GAAP Financial Measures "
    "($ in millions, except per share amounts) Net Income Attributable to "
    "Apollo Global Management, Inc. Common Stockholders $787 $1.30 $3,018 $4.96 "
    "Segment Income Attributable to Apollo Global Management, Inc. $1,012 $1.67 "
    "$3,405 $5.61 Fee Related Earnings $442 $0.73 $1,298 $2.14 Spread Related "
    "Earnings $825 $1.36 $2,410 $3.97 Principal Investing Income $198 $0.33 "
    "$612 $1.01 Assets Under Management $733,000 $733,000 Fee Earning Assets "
    "Under Management $588,000 $588,000 Dry Powder $62,000 $62,000\n"
    "(In millions, except per share amounts) 3Q'23 2Q'24 3Q'24 YTD'23 YTD'24 "
    "Revenues Asset Management Management fees $462 $462 $476 $1,328 $1,376 "
    "Advisory and transaction fees, net 157 267 181 482 617 Investment income "
    "402 395 303 1,204 1,098 Incentive fees 89 112 145 301 388 Total revenues "
    "1,110 1,236 1,105 3,315 3,859 Retirement Services Premiums $2,104 $2,310 "
    "$2,456 $6,802 $7,114 Product charges 298 312 341 902 1,005 Net investment "
    "income 2,410 2,512 2,689 7,204 7,802 Total revenues 5,102 5,401 5,790 15,408 "
    "16,501 Expenses Compensation and benefits 512 534 561 1,502 1,621 Interest "
    "expense 1,890 1,940 2,012 5,602 5,890 Policyholder benefits 2,204 2,310 "
    "2,456 6,802 7,114 Amortization of deferred acquisition costs 189 201 214 "
    "568 602 Other operating expenses 401 423 447 1,204 1,298 Total expenses "
    "5,196 5,408 5,690 15,478 16,525 Income before income taxes 1,016 1,229 "
    "1,205 3,245 3,835 Income tax expense 229 276 271 731 862 Net income 787 "
    "953 934 2,514 2,973 Less: Net income attributable to noncontrolling "
    "interests 0 0 0 0 0 Net income attributable to Apollo Global Management, "
    "Inc. Common Stockholders $787 $953 $934 $2,514 $2,973 "
    "Diluted weighted average common shares outstanding 605 608 611 606 609 "
    "Basic weighted average common shares outstanding 598 601 604 599 602 "
    "Fee Related Earnings per share $0.73 $0.74 $0.75 $2.14 $2.19 Spread Related "
    "Earnings per share $1.36 $1.38 $1.41 $3.97 $4.02 Principal Investing Income "
    "per share $0.33 $0.34 $0.36 $1.01 $1.04 Total Segment Income per share "
    "$2.42 $2.46 $2.52 $7.12 $7.25 Book value per common share $18.42 $19.05 "
    "$19.88 $19.88 $21.04 Cash and cash equivalents $1,204 $1,310 $1,428 $1,428 "
    "$1,562 Total assets $48,204 $49,310 $50,428 $50,428 $52,104 Total liabilities "
    "$41,204 $42,310 $43,428 $43,428 $44,562 Total equity $7,000 $7,000 $7,000 "
    "$7,000 $7,542"
)


def test_s5_table_apo_shape() -> None:
    assert classify_s5(_APO_STORED, _APO_LIVE) == "s5-table"


def test_s5_table_needs_a_clean_live_lede() -> None:
    # Live is itself a table: no S5 repair.
    assert classify_s5(_APO_STORED, _APO_STORED) is None


_CSCO_STORED = "\n".join(
    [
        "Revenue -- Total revenue was $15.3 billion, up 10%, with product revenue up 14% and services revenue down 1%.",
        "Revenue by geographic segment was: Americas up 8%, EMEA up 15%, and APJC up 8%.",
        "Gross Margin -- On a GAAP basis, total gross margin was 65.0%, product gross margin 63.9%, and services gross margin 68.4%.",
        "On a non-GAAP basis, total gross margin was 67.5%, product gross margin 66.4%, and services gross margin 70.9%.",
        "Operating Expenses -- On a GAAP basis, operating expenses were $6.2 billion, up 3% year over year.",
        "Operating Income -- GAAP operating income was $3.8 billion, up 21%, with GAAP operating margin of 24.6%.",
        "Provision for Income Taxes -- The GAAP tax provision rate was 12.9%. The non-GAAP tax provision rate was 19.0%.",
        "Net Income and EPS -- On a GAAP basis, net income was $3.2 billion, an increase of 31%, and EPS was $0.80.",
        "Cash Flow from Operating Activities -- $1.8 billion for the second quarter of fiscal 2026, a decrease of 19%.",
        "Balance Sheet and Other Financial Highlights",
        "Cash and Cash Equivalents and Investments -- $15.8 billion at the end of the second quarter of fiscal 2026.",
    ]
)
_CSCO_LIVE = "\n".join(
    [
        "CISCO REPORTS SECOND QUARTER EARNINGS",
        "• Double-digit top and bottom-line growth exceeding our guidance, with EPS growing faster than revenue",
        "◦ Record revenue of $15.3 billion, up 10% year over year; GAAP EPS of $0.80, up 31% year over year",
        "◦ GAAP gross margin of 65.0% and Non-GAAP gross margin of 67.5%",
        "• Accelerating, double-digit growth in product orders across all geographies",
        "◦ Product orders up 18% year over year with networking product orders accelerating to more than 20%",
        "• AI Infrastructure orders taken from hyperscalers totaled $2.1 billion",
        "• Dividend increased by 2% to $0.42 per share",
        "• Q2 FY 2026 Results:",
        "◦ Revenue: $15.3 billion",
        "▪ Increase of 10% year over year",
        "◦ Earnings per Share: GAAP: $0.80; Non-GAAP: $1.04",
        "▪ GAAP EPS increased 31% year over year",
        "▪ Non-GAAP EPS increased 11% year over year",
    ]
)


def test_s5_narrative_csco_shape() -> None:
    assert classify_s5(_CSCO_STORED, _CSCO_LIVE) == "s5-narrative"


def test_s5_narrative_bullet_figure_lines_are_not_table_rows() -> None:
    # The live "◦ Earnings per Share: GAAP: $0.80; Non-GAAP: $1.04"
    # line trips _is_lede_data_row (label + figures), but it is a
    # bullet, never a table row — the added-table check must not block
    # on it. Without the batch-244 exemption this returns None.
    assert "Earnings per Share: GAAP: $0.80" in _CSCO_LIVE
    assert classify_s5(_CSCO_STORED, _CSCO_LIVE) == "s5-narrative"


def test_s5_narrative_needs_live_bullets() -> None:
    prose_live = (
        "CISCO REPORTS SECOND QUARTER EARNINGS\n"
        "Revenue was $15.3 billion, up 10% year over year, with GAAP EPS of $0.80."
    )
    assert classify_s5(_CSCO_STORED, prose_live) is None


_COIN_STORED = (
    "Disclaimers Cautionary Note Regarding Forward-Looking Statements "
    "This presentation contains forward-looking statements within the meaning "
    "of the Private Securities Litigation Reform Act of 1995. All statements "
    "other than statements of historical fact could be deemed forward-looking. "
    "These statements are inherently uncertain and actual results may differ."
)
_COIN_LIVE = "\n".join(
    [
        "Slide 1 Our mission is to increase economic freedom in the world",
        "Crypto is updating all financial services, AI is an accelerant",
        "• Global",
        "• Efficient",
        "• Programmable",
        "• Always on (24/7)",
        "Coinbase is uniquely positioned to capitalize on this transformation",
    ]
)


def test_s5_disclaimer_coin_shape() -> None:
    assert classify_s5(_COIN_STORED, _COIN_LIVE) == "s5-disclaimer"


def test_s5_disclaimer_needs_real_live_content() -> None:
    assert classify_s5(_COIN_STORED, _COIN_STORED) is None


_NFLX_STORED = "\n".join(
    [
        "July 17, 2025",
        "• A number of hit series including Sirens (56M views), Ginny & Georgia S3 (53M views), Mad Unicorn from Thailand (7M views).",
        "• New series out of the US, like The Four Seasons starring Tina Fey and Steve Carell (40M views) delighted members.",
        "• Film releases including Exterritorial from Germany, which became our fourth most popular non-English language film ever (89M views).",
        "• Our new film KPop Demon Hunters (80M views) is one of our biggest animated films ever.",
        "• Finally, our Q2 slate wrapped up on a high note with Squid Game S3 (122M views).",
        "We lead the industry in viewing transparency. In addition to the quarterly data we provide, we also publish weekly Top 10 lists.",
        "• Even with our 2025 slate being unusually second-half weighted, our members watched over 95 billion hours in the first half.",
        "• Non-English language series and films represented more than one-third of all Netflix viewing in the first half of the year.",
        "__________________________________",
        "3 A view is defined as hours viewed divided by runtime for each title.",
        "4 https://www.netflix.com/tudum/top10",
        "5 https://www.bbc.com/culture/article/20250715-the-animated-k-pop-film-that-swept-the-world",
    ]
)
_NFLX_LIVE = "\n".join(
    [
        "• Our business continues to perform well. In Q2, we grew revenue 16% and our operating margin of 34% expanded seven points year over year.",
        "• We now forecast 2025 revenue of $44.8-$45.2B, up from $43.5-$44.5B, and a F/X neutral operating margin of 29.5%.",
        "• We continue to make progress on our key business objectives:",
        "◦ In Q2, we had a wide variety of hit series like Squid Game S3, Sirens, Ginny & Georgia S3, The Eternaut and Secrets We Keep.",
        "◦ We have completed the rollout of the Netflix Ads Suite across all our ads markets.",
        "◦ We have also launched our redesigned TV homepage, which we expect will enhance the member experience.",
        "• We’re optimistic heading into the second half of the year, with a standout slate that includes Wednesday S2 and the Stranger Things finale.",
        "Our summary results, and forecast for Q3, are below.",
    ]
)


def test_s5_wrong_section_nflx_shape() -> None:
    assert classify_s5(_NFLX_STORED, _NFLX_LIVE) == "s5-wrong-section"


def test_s5_wrong_section_needs_furniture_free_live() -> None:
    live_with_furniture = _NFLX_LIVE + "\n__________________________________\n4 https://www.netflix.com/tudum/top10"
    assert classify_s5(_NFLX_STORED, live_with_furniture) is None


def test_s5_never_fires_on_a_real_highlights_block() -> None:
    # A genuine highlights block with no wrong-section shape stays
    # out of S5 even when live differs (e.g. a dropped bullet) — the
    # loss check in S4 is what guards it, and S5 must not bypass it.
    stored = "\n".join(
        [
            "ACME REPORTS THIRD QUARTER RESULTS",
            "• Revenue of $1.21 billion, up 14 percent.",
            "• Net income of $310 million, up 9 percent.",
            "• Book value per share of $142.18, up 11 percent.",
        ]
    )
    live = "\n".join(
        [
            "ACME REPORTS THIRD QUARTER RESULTS",
            "• Revenue of $1.25 billion, up 16 percent.",
            "• Net income of $322 million, up 12 percent.",
        ]
    )
    assert classify_s5(stored, live) is None


# --- s5-fy-stored (doc-level verification) -------------------------------

def _fy_q4_doc_html() -> str:
    return _contact_release_html(
        "ACME REPORTS FOURTH QUARTER AND FULL YEAR 2024 RESULTS",
        "FULL YEAR 2024 FINANCIAL HIGHLIGHTS",
        "• Revenue of $7.00 billion, an increase of 19% compared to fiscal year 2023.",
        "• Net income of $1.90 billion, an increase of 22% compared to fiscal year 2023.",
        "• GAAP EPS of $4.10, an increase of 24% compared to fiscal year 2023.",
        "FOURTH QUARTER 2024 FINANCIAL HIGHLIGHTS",
        "• Revenue of $1.93 billion, an increase of 25% year over year.",
        "• Net income of $510 million, an increase of 28% year over year.",
        "• GAAP EPS of $1.10, an increase of 30% year over year.",
    )


def test_verify_fy_stored_matches_doc_sections() -> None:
    html = _fy_q4_doc_html()
    stored = "\n".join(
        [
            "ACME REPORTS FOURTH QUARTER AND FULL YEAR 2024 RESULTS",
            "• Revenue of $7.00 billion, an increase of 19% compared to fiscal year 2023.",
            "• Net income of $1.90 billion, an increase of 22% compared to fiscal year 2023.",
            "• GAAP EPS of $4.10, an increase of 24% compared to fiscal year 2023.",
        ]
    )
    live = extract_press_release_highlights(html)
    assert live is not None
    assert "Revenue of $1.93 billion" in live  # the scope fix picks Q4
    assert verify_fy_stored(html, stored, live) is True


def test_verify_fy_stored_rejects_quarter_stored() -> None:
    # Stored already holds the quarter section: nothing to re-sync.
    html = _fy_q4_doc_html()
    live = extract_press_release_highlights(html)
    assert live is not None
    assert verify_fy_stored(html, live, live) is False


def test_verify_fy_stored_rejects_single_section_doc() -> None:
    html = _contact_release_html(
        "ACME REPORTS FULL YEAR 2024 RESULTS",
        "FULL YEAR 2024 FINANCIAL HIGHLIGHTS",
        "• Revenue of $7.00 billion, an increase of 19% compared to fiscal year 2023.",
        "• Net income of $1.90 billion, an increase of 22% compared to fiscal year 2023.",
        "• GAAP EPS of $4.10, an increase of 24% compared to fiscal year 2023.",
    )
    live = extract_press_release_highlights(html)
    assert live is not None
    assert verify_fy_stored(html, live, live) is False
