"""Batch 194: "-more-" page markers end the highlights lede at the next
section heading, and a truncated-tail repair exemption.

The lede loop (and the Highlights section collector) never skipped the
"-more-" page-continuation marker — the guidance collector gained the
skip in batch 193, but the highlights paths did not. APD Q2 FY2026
served "-more-" plus the next section's heading ("Fiscal 2026 Second
Quarter Results by Business Segment") as highlights, and its stored row
ends with the footnote lines (fixed in batch 192), "-more-", and a
"Fiscal…" tail truncated by the 4000-char cap. The fix, all in
extract_press_release_highlights:
  - "-more-" lines are skipped in the lede loop and the section
    collector (never content, never budget);
  - a heading-shaped line right after a "-more-" ends the lede /
    section, when the previously collected line is terminated — the
    heading's content belongs to the next section. A wrapped paragraph
    continuing across the page break is never heading-shaped (its head
    is sentence-case, or its previous line is unterminated), and a
    quote-attribution tail ends with a comma, so both stay collectable;
    table mode suppresses the break (batch 185: prose after a table is
    still collected);
  - _clean_highlights_result also pops a trailing "-more-" (paths that
    bypass the loops, e.g. shareholder-letter / flat-table modes).
The repair gate gains a truncated-tail exemption: a stored line ending
in "…" whose prefix is a strict prefix of a line the old extractor
served and the new one drops (the cap-truncated heading) counts as a
defect line, not a dropped content line.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _clean_highlights_result,
    _is_more_page_section_heading,
    _is_trailing_company_signature,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _live(ticker_period: str) -> str:
    html = open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ).read()
    out = extract_press_release_highlights(html)
    assert out is not None, f"{ticker_period} extracted None"
    return out


def _extract(body_lines):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


# --- unit: the heading shape after a "-more-" -------------------------------

def test_more_page_heading_shape():
    assert _is_more_page_section_heading(
        "Fiscal 2026 Second Quarter Results by Business Segment"
    )
    assert _is_more_page_section_heading("Fourth Quarter Segment Results")
    # A terminated sentence is prose, not a heading.
    assert not _is_more_page_section_heading(
        "Second quarter sales of $3.2 billion increased nine percent."
    )
    # A quote-attribution tail ends with a comma, not a heading.
    assert not _is_more_page_section_heading(
        "Commenting on the results, Chief Executive Officer Jane Smith said,"
    )
    # A colon-ended attribution is sentence-terminated, not a heading.
    assert not _is_more_page_section_heading(
        "Commenting on the results, Chief Executive Officer Jane Smith said:"
    )
    # A bullet is content, not a heading.
    assert not _is_more_page_section_heading(
        "•Segment revenue of $9.9 billion grew 99%"
    )
    # A dateline opens a paragraph, not a section.
    assert not _is_more_page_section_heading(
        "LEHIGH VALLEY, Pa. (April 30, 2026) - Air Products (NYSE:APD)"
    )
    # Figures / currency are data, not a heading.
    assert not _is_more_page_section_heading(
        "Second Quarter Results by Segment $3.2 Billion"
    )
    # Sentence-case prose (a wrapped paragraph head) is not a heading.
    assert not _is_more_page_section_heading(
        "On a non-GAAP basis, second quarter adjusted operating income"
    )
    # An all-caps table title is caught by the loop's own table breaks.
    assert not _is_more_page_section_heading(
        "CONSOLIDATED STATEMENTS OF OPERATIONS"
    )


# --- end-to-end: the APD shape (lede path) ---------------------------------
# No bullets: a pure-prose lede forces the lede loop (a leading bullet
# block would win the section pick and never reach the loop).

APD_BODY = [
    "Air Products Reports Fiscal 2026 Second Quarter Results",
    "Fiscal 2026 Second Quarter Consolidated Results (comparison versus prior year)",
    "LEHIGH VALLEY, Pa. (April 30, 2026) - Air Products (NYSE:APD) today reported second quarter fiscal 2026 GAAP operating income of $753 million and GAAP EPS of $3.19, each up over 130%, and GAAP operating margin of 23.7 percent, compared to negative 79.8 percent in the prior year.",
    "On a non-GAAP basis, second quarter adjusted operating income of $753 million and adjusted EPS of $3.20 each increased 19 percent, reflecting higher on-site volumes, favorable currency and lower costs driven by productivity and lower depreciation.",
    "Second quarter sales of $3.2 billion increased nine percent, reflecting four percent higher volumes, four percent favorable currency and two percent higher energy cost pass-through, partially offset by one percent lower pricing.",
    "Commenting on the results, Chief Executive Officer Eduardo Menezes said, “Despite macroeconomic volatility, Air Products delivered 19% growth in adjusted EPS and adjusted operating income improvement across segments. We saw higher on-site volumes and made continued progress on productivity and pricing.”",
    "-more-",
    "Fiscal 2026 Second Quarter Results by Business Segment",
    "Three Months Ended March 31, 2026",
    "Sales",
    "$3,200",
]


def test_lede_ends_at_more_page_heading():
    out = _extract(APD_BODY)
    assert out is not None
    assert "-more-" not in out
    assert "Results by Business Segment" not in out
    assert "Three Months Ended March 31, 2026" not in out
    # The quote paragraph — the last real lede line — is still served.
    assert "Despite macroeconomic volatility" in out
    assert "Second quarter sales of $3.2 billion increased nine percent" in out
    # The results heading that introduces the lede prose stays.
    assert "Fiscal 2026 Second Quarter Consolidated Results" in out


def test_more_page_continuation_still_collected():
    # A paragraph wrapped across the page break: the line before the
    # marker is unterminated, so the continuation after it is collected,
    # not treated as a new section.
    out = _extract(
        [
            "Acme Reports First Quarter 2026 Results",
            "NEW YORK, April 28, 2026 - Acme Corp (NYSE: ACME) today reported first quarter 2026 net income of $500 million, or $1.20 per diluted share, up 10% year over year, on revenue of $2.1 billion, an increase of 8% from the prior year period, as higher pricing, net of power and fuel costs, was partially offset by higher costs related to incentive compensation and inflation, partially mitigated by productivity improvements.",
            "First quarter sales rose sharply on higher volumes and",
            "-more-",
            "favorable currency, up 4% year over year, with pricing adding another 2% across the portfolio and new products contributing a further point of growth.",
            "Commenting on the results, Chief Executive Officer Jane Smith said, “We delivered a strong quarter across every segment of the business, with momentum building into the second half of the year as new products gain share and productivity improves.”",
        ]
    )
    assert out is not None
    assert "-more-" not in out
    assert "favorable currency, up 4% year over year" in out
    assert "We delivered a strong quarter" in out


def test_more_page_quote_attribution_still_collected():
    # A quote attribution after the marker ends with a comma, so it is
    # not a heading — the quote that follows is still collected.
    out = _extract(
        [
            "Acme Reports First Quarter 2026 Results",
            "NEW YORK, April 28, 2026 - Acme Corp (NYSE: ACME) today reported first quarter 2026 net income of $500 million, or $1.20 per diluted share, up 10% year over year, on revenue of $2.1 billion, an increase of 8% from the prior year period, as higher pricing, net of power and fuel costs, was partially offset by higher costs related to incentive compensation and inflation, partially mitigated by productivity improvements.",
            "First quarter sales of $2.1 billion increased 8 percent, reflecting four percent higher volumes and four percent favorable currency across the portfolio, with pricing adding another 2 percent and new products contributing a further point of growth.",
            "-more-",
            "Commenting on the results, Chief Executive Officer Jane Smith said,",
            "“We delivered a strong quarter across every segment of the business, with momentum building into the second half of the year and new products gaining share.”",
        ]
    )
    assert out is not None
    assert "-more-" not in out
    assert "We delivered a strong quarter" in out


def test_highlights_section_ends_at_more_page_heading():
    # A Highlights section whose bullets span a page break: the bullets
    # before the marker stay, the heading after it ends the section, and
    # the next section's bullet is never served. (Bullets are padded long
    # so the document clears the extractor's 800-char floor.)
    out = _extract(
        [
            "Acme Reports Third Quarter 2026 Results",
            "Third Quarter Highlights",
            "•Net income of $500 million, up 10% year over year, on revenue of $2.1 billion, an increase of 8% from the prior year period, driven by higher volumes and favorable currency.",
            "•Revenue of $2.1 billion increased 8%, reflecting four percent higher volumes, four percent favorable currency, and two percent higher pricing across the portfolio.",
            "•Adjusted EPS of $1.20, up 12% year over year, driven by higher volumes, favorable currency, and lower costs from productivity and lower depreciation.",
            "-more-",
            "Fourth Quarter Segment Results",
            "•Segment revenue of $9.9 billion grew 99% year over year on strong demand and new product launches across every region and channel.",
            "About Acme",
            "Acme is a leading provider of widgets and gadgets worldwide.",
        ]
    )
    assert out is not None
    assert "-more-" not in out
    assert "Segment revenue of $9.9 billion" not in out
    assert "Fourth Quarter Segment Results" not in out
    assert "Net income of $500 million" in out
    assert "Adjusted EPS of $1.20" in out


# --- trailing "-more-" / signature trim -------------------------------------

def test_clean_highlights_result_pops_trailing_more():
    result = _clean_highlights_result(
        "Acme Reports First Quarter 2026 Results\n\n"
        "First quarter sales of $2.1 billion increased 8 percent, reflecting "
        "four percent higher volumes and four percent favorable currency "
        "across the portfolio, with pricing adding another 2 percent.\n"
        "-more-"
    )
    assert "-more-" not in result
    assert "First quarter sales of $2.1 billion" in result


def test_trailing_company_signature_shape():
    assert _is_trailing_company_signature("CarMax, Inc.")
    assert _is_trailing_company_signature("Air Products and Chemicals, Inc.")
    assert _is_trailing_company_signature("Apple Inc.")
    assert _is_trailing_company_signature("3M Company")
    # A prose sentence ending in a suffix is not a signature.
    assert not _is_trailing_company_signature(
        "The transaction was approved by Apple Inc."
    )
    # A bullet is content, not a signature.
    assert not _is_trailing_company_signature("•Net income of $500 million.")
    # Figures / currency are data, not a signature.
    assert not _is_trailing_company_signature("CarMax, Inc. $500 million")
    # Too long to be a bare name.
    assert not _is_trailing_company_signature(
        "CarMax, Inc. Reports First Quarter Fiscal 2027 Results Today"
    )


def test_clean_highlights_result_pops_trailing_signature():
    result = _clean_highlights_result(
        "Acme Reports First Quarter 2026 Results\n\n"
        "First quarter sales of $2.1 billion increased 8 percent, reflecting "
        "four percent higher volumes and four percent favorable currency "
        "across the portfolio, with pricing adding another 2 percent.\n"
        "Acme Corp."
    )
    assert "Acme Corp." not in result
    assert "First quarter sales of $2.1 billion" in result


def test_kmx_shaped_section_drops_more_and_signature():
    # CarMax Q1 FY2027 shape: bullets, a "(1) Comparisons..." footnote,
    # "-more-", then the page-2 header "CarMax, Inc." — the skip frees a
    # section slot the signature would otherwise fill, and the trailing
    # trim drops it. (Bullets are padded long so the document clears the
    # extractor's 800-char floor.)
    out = _extract(
        [
            "CarMax Reports First Quarter Fiscal 2027 Results",
            "First Quarter Highlights",
            "•Bought 322,000 vehicles from consumers and dealers, a decrease of 4.4%, with total unit sales growing across retail and wholesale channels.",
            "•SG&A expenses decreased 3.7% or $24.5 million to $635.2 million. Ongoing cost reduction efforts, combined with total unit growth, drove strong SG&A leverage.",
            "•CarMax Auto Finance (CAF) penetration expanded 150 basis points year over year to 43.3%, reflecting continued execution of our full spectrum growth strategy.",
            "•Net earnings per diluted share of $1.31 versus $1.38 a year ago.",
            "(1) Comparisons to the prior year’s first quarter unless otherwise stated.",
            "-more-",
            "CarMax, Inc.",
            "Page 2 of 13",
            "CEO Commentary:",
            "“I came to CarMax because I saw a strong foundation, an award-winning, people-first culture, and significant potential to grow the business.”",
        ]
    )
    assert out is not None
    assert "-more-" not in out
    assert "Comparisons to the prior year" not in out
    assert "CarMax, Inc." not in out
    assert "Net earnings per diluted share of $1.31" in out


# --- real exhibit: APD 2026-03-31 -------------------------------------------

def test_apd_2026_03_31_live_ends_at_quote():
    out = _live("APD_2026-03-31")
    assert "-more-" not in out
    assert "Results by Business Segment" not in out
    assert "Despite macroeconomic volatility" in out
    assert "Second quarter sales of $3.2 billion increased nine percent" in out
