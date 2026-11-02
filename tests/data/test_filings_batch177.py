"""Batch 177: heading and table-header lines riding the lede.

Three attested classes, all consuming one of the 6 lede lines and
starving a real bullet:
  - Moody's Q4 2025: the summary-table title "FOURTH QUARTER AND
    FULL YEAR SUMMARY FINANCIALS" plus its column-header line "MCO
    Diluted EPS MCO Adjusted Diluted EPS2" sit in the lede above the
    CEO quote and the bullets.
  - Capital One: the adjusting-items table header "Impact After-Tax
    Diluted EPS" (5 rows) and its list-intro "The quarter included
    the following adjusting items:" fill the last lede lines.
  - Disney Q3 2026: "Fiscal 2026 outlook:" sits above the outlook
    bullets; Q1 2026 and the Q4/FY lines serve "Financial Results
    for the Quarter:" / "... and Full Year:" the same way.
Fix: three lede-loop skips — _is_lede_colon_heading (colon-ended
list-intro / section heading), _is_lede_table_header (figure-less
capital-led metric-label line), and the _is_lede_heading_fragment
bound extended 4 -> 8 words with a headline-verb guard so a longer
all-caps sub-headline is never mistaken for a table title.
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_lede_colon_heading,
    _is_lede_heading_fragment,
    _is_lede_table_header,
    extract_press_release_highlights,
)


def test_colon_heading_attested_lines():
    # Disney's section headings and Capital One's list intro.
    assert _is_lede_colon_heading("Financial Results for the Quarter:")
    assert _is_lede_colon_heading(
        "Financial Results for the Quarter and Full Year:"
    )
    assert _is_lede_colon_heading("Fiscal 2026 outlook:")
    assert _is_lede_colon_heading("Fourth Quarter 2024:")
    assert _is_lede_colon_heading("For the full year:")
    assert _is_lede_colon_heading(
        "Third quarter highlights, year over year:"
    )
    assert _is_lede_colon_heading("Q1 FY26 Summary of Results:")
    # List-intro idiom, verb or not.
    assert _is_lede_colon_heading(
        "Business highlights included the following:"
    )
    assert _is_lede_colon_heading(
        "The quarter included the following adjusting items:"
    )
    assert _is_lede_colon_heading(
        "Full year 2026 Non-GAAP diluted EPS range is expected as follows:"
    )


def test_colon_heading_keeps_quote_attribution_and_prose():
    # A quote attribution ends with a colon but is never a heading:
    # dropping it would orphan the quote.
    assert not _is_lede_colon_heading(
        "Sundar Pichai, CEO of Google and Alphabet, said:"
    )
    # A prose lead-in carries a verb.
    assert not _is_lede_colon_heading(
        "Our guidance assumes the following metrics will improve:"
    )
    # A figure-carrying line is content, not a heading.
    assert not _is_lede_colon_heading("Revenue of $25.2 billion:")
    # A bullet is never a heading.
    assert not _is_lede_colon_heading(
        "•Revenues increased 7% for the quarter:"
    )


def test_table_header_attested_lines():
    assert _is_lede_table_header("MCO Diluted EPS MCO Adjusted Diluted EPS2")
    assert _is_lede_table_header("MCO Diluted EPS MCO Adjusted Diluted EPS1")
    assert _is_lede_table_header("Impact After-Tax Diluted EPS")


def test_table_header_keeps_sub_headlines():
    # All-caps sub-headlines carry a headline verb.
    assert not _is_lede_table_header(
        "Q2 ORGANIC SALES AND ADJUSTED EPS EXCEED OUTLOOK"
    )
    assert not _is_lede_table_header(
        "COMPANY MAINTAINS FULL-YEAR REVENUE AND EPS GUIDANCE"
    )
    assert not _is_lede_table_header(
        "RESETTING DIVIDEND TO ACCELERATE DEBT REDUCTION"
    )
    assert not _is_lede_table_header(
        "Investment Income Leads Second-Quarter Profits"
    )
    # Real bullets and prose with figures are never headers.
    assert not _is_lede_table_header(
        "•Diluted EPS up 8% and Adjusted Diluted EPS2 up 13% from the prior-year period."
    )
    assert not _is_lede_table_header(
        "MCO revenue of $2.0 billion increased 1% from the prior-year period."
    )


def test_long_caps_heading_fragment():
    # Moody's summary-table title: 6 words, all caps, no verb, no figures.
    assert _is_lede_heading_fragment(
        "FOURTH QUARTER AND FULL YEAR SUMMARY FINANCIALS"
    )
    # Short fragments keep the old behavior.
    assert _is_lede_heading_fragment("RESULTS FOR THE QUARTER")
    assert _is_lede_heading_fragment("QUARTER")


def test_long_caps_fragment_keeps_sub_headlines():
    # A longer all-caps line with a headline verb is the sub-headline.
    assert not _is_lede_heading_fragment(
        "Q2 ORGANIC SALES AND ADJUSTED EPS EXCEED OUTLOOK"
    )
    assert not _is_lede_heading_fragment(
        "AMERICAN WATER REPORTS SOLID SECOND QUARTER RESULTS"
    )
    assert not _is_lede_heading_fragment(
        "COMPANY MAINTAINS FULL-YEAR REVENUE AND EPS GUIDANCE"
    )
    # Over the 8-word cap, or carrying a year in the 5-8 word band, it
    # is not a fragment. (A <=4-word all-caps line keeps the old
    # behavior — "FOURTH QUARTER 2025 RESULTS" is still a fragment
    # under the pre-existing bound.)
    assert not _is_lede_heading_fragment(
        "CHIPOTLE HIGHLIGHTS BRAND STRENGTH AND INNOVATION IN FIRST QUARTER RESULTS"
    )
    assert not _is_lede_heading_fragment("FOURTH QUARTER 2025 FINANCIAL RESULTS")
    assert _is_lede_heading_fragment("FOURTH QUARTER 2025 RESULTS")


def _extract(body_lines):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


def test_mco_style_release_drops_heading_lines():
    out = _extract(
        [
            "MOODY'S CORPORATION REPORTS RESULTS FOR FOURTH QUARTER AND FULL YEAR 2025; SETS OUTLOOK FOR 2026",
            "NEW YORK, NY - February 18, 2026 - Moody's Corporation (NYSE: MCO) today announced results "
            "for the fourth quarter and full year 2025 and provided its outlook for full year 2026.",
            "FOURTH QUARTER AND FULL YEAR SUMMARY FINANCIALS",
            "MCO Diluted EPS MCO Adjusted Diluted EPS2",
            "“Our 2025 results demonstrate the tremendous demand for Moody’s solutions and our ability to "
            "execute with precision and speed. We delivered record revenue of $7.7 billion and diluted and adjusted diluted EPS growth of 21% and 20%, respectively. By scaling decision grade, contextual intelligence that is embedded directly into customer workflows — across our platforms, third party systems, and AI enabled interfaces — we are expanding the ways in which Moody’s remains central to high stakes decision making.”",
            "•MCO revenue was $1.9 billion, a 13% increase from the prior-year period.",
            "•Foreign currency translation favorably impacted MCO revenue by 2%.",
            "•MCO operating cash flow was $1.1 billion in the fourth quarter.",
        ]
    )
    assert out is not None
    assert "FOURTH QUARTER AND FULL YEAR SUMMARY FINANCIALS" not in out
    assert "MCO Diluted EPS MCO Adjusted Diluted EPS2" not in out
    assert "MCO revenue was $1.9 billion" in out
    assert "Foreign currency translation" in out
    assert "operating cash flow was $1.1 billion" in out


def test_disney_style_release_drops_outlook_heading():
    out = _extract(
        [
            "To Our Shareholders and the Broader Investment Community",
            "Our strong fiscal Q3 results and reiterated full-year outlook reinforce our confidence that we are uniquely well positioned. Decades of IP investment have built deep fan connections that translate into strong financial results. Our accelerating global guests growth at Experiences, Toy Story 5's theatrical and consumer products success, and strong ESPN viewership gains all helped expand our consumer reach this quarter.",
            "Revenues increased 7% for the third quarter to $25.2 billion from $23.7 billion in Q3 fiscal 2025. "
            "Diluted earnings per share (EPS) decreased to $1.51 from $2.92 in Q3 fiscal 2025.",
            "Fiscal 2026 outlook:",
            "•We continue to expect fiscal 2026 adjusted EPS growth of approximately 12%.",
            "•We expect Q4 total segment operating income of approximately $4.9 billion.",
        ]
    )
    assert out is not None
    assert "Fiscal 2026 outlook:" not in out
    assert "adjusted EPS growth of approximately 12%" in out
    assert "Q4 total segment operating income" in out


def test_quote_attribution_survives_colon_heading_skip():
    out = _extract(
        [
            "ALPHABET REPORTS THIRD QUARTER 2025 RESULTS",
            "MOUNTAIN VIEW, Calif. – Alphabet Inc. (NASDAQ: GOOGL, GOOG) today announced financial results for the quarter ended September 30, 2025. Alphabet reported consolidated revenues of $102.3 billion, up 16% year over year, with Google Services revenues of $76.5 billion and Google Cloud revenues of $15.2 billion.",
            "Sundar Pichai, CEO of Google and Alphabet, said:",
            "“We had a strong quarter with growth across the company, driven by AI. Our AI investments are paying off for users and customers, with strong momentum in Cloud and Search, and we are seeing real traction in our AI Overviews and Gemini app as millions of people turn to them every day.”",
            "•Google Cloud revenues increased 34% to $15.2 billion.",
            "•YouTube advertising revenues increased 12% to $9.8 billion.",
            "•Google Services revenues increased 14% to $76.5 billion.",
            "•Operating income increased 22% to $31.2 billion, and net income was $25.8 billion.",
        ]
    )
    assert out is not None
    assert "Sundar Pichai, CEO of Google and Alphabet, said:" in out
    assert "strong quarter with growth" in out


def test_section_path_drops_colon_sub_heading():
    # Datadog-style: a Highlights section whose financial bullets are
    # followed by a "Third Quarter & Recent Business Highlights:"
    # sub-heading and then the business bullets. The sub-heading is the
    # same dangling heading as in the lede loop — the section collector
    # needs the skip too, or the heading rides the stored row.
    out = _extract(
        [
            "Datadog Announces Third Quarter 2024 Financial Results",
            "NEW YORK, Nov. 7, 2024 - Datadog, Inc. (NASDAQ: DDOG), the monitoring and security platform for cloud applications, today announced financial results for its third quarter ended September 30, 2024.",
            "Third Quarter 2024 Financial Highlights:",
            "•Revenue was $690 million, an increase of 26% year-over-year.",
            "•GAAP operating income was $20 million; GAAP operating margin was 3%.",
            "•Non-GAAP operating income was $173 million; non-GAAP operating margin was 25%.",
            "•GAAP net income per diluted share was $0.14; non-GAAP net income per diluted share was $0.46.",
            "•Operating cash flow was $229 million, with free cash flow of $204 million.",
            "Third Quarter & Recent Business Highlights:",
            "•As of September 30, 2024, we had about 3,490 customers with ARR of $100,000 or more, an increase of 12% from about 3,130 as of September 30, 2023.",
            "•Named a Leader in the 2024 Gartner Magic Quadrant for Digital Experience Monitoring.",
            "•Released its State of Cloud Security 2024 report.",
        ]
    )
    assert out is not None
    assert "Third Quarter & Recent Business Highlights:" not in out
    assert "Revenue was $690 million" in out
    assert "3,490 customers with ARR of $100,000 or more" in out
    assert "Named a Leader in the 2024 Gartner Magic Quadrant" in out
