"""Batch 163 regression tests: Workiva page-flattened releases are
salvaged instead of discarded by the batch-105 page-line guard.

Shopify's Q3 2024 release (exhibit `a3pr.htm`) flattens each page into a
single mega-line: the dateline lede, the CEO/CFO quotes, the headline, and
the metric table all run together with no line breaks, so no headline line
ever exists and the page-line guard returned None — SHOP's only blank
quarter (the other 7 extract fine). The fix salvages such a line when it
opens with a dateline: split at sentence boundaries, keep the narrative
sentences as the lede, drop footnote/table-residue sentences, and rescue a
release title sitting at the head of the table fragment as the headline.
A dateline-less page line (Bank of America slide deck, batch 105) still
returns None, and documents that currently extract never reach the salvage.
"""

from tickerlens.data.filings import (
    _PAGE_DATELINE_RE,
    _salvage_page_line_lede,
    _split_page_line_sentences,
    extract_press_release_highlights,
)


def _bare_release_html(*lines: str) -> str:
    body = "".join(f"<p>{ln}</p>" for ln in lines)
    return f"<html><body>{body}</body></html>"


# Real Q3 2024 exhibit text (SHOP `a3pr.htm`, fetched 2026-10-31): the
# exhibit header lines plus the page-1 mega-line and the page-2 outlook
# line, exactly as `_html_to_text` renders them.
SHOP_Q3_2024_PAGE1 = '1 Internet, Everywhere - November 12, 2024 - Shopify Inc. (NYSE, TSX: SHOP), a leading commerce technology company announced today financial results for the quarter ended September 30, 2024. “Q3 was outstanding, further establishing Shopify as a leader in powering commerce anywhere, anytime. Our unified commerce platform is becoming the go-to choice for merchants of all sizes,” said Harley Finkelstein, President of Shopify. “As the busiest shopping season of the year for our merchants approaches, they trust Shopify to provide the tools, unmatched speed, and reliability to maximize their success.” Jeff Hoffmeister, Chief Financial Officer of Shopify, said, “Shopify achieved 26% revenue growth and 19% free cash flow margin this quarter, marking our sixth consecutive quarter of greater than 25% revenue growth excluding logistics. Moreover, we have grown free cash flow margin sequentially each quarter this year, consistent with what we delivered last year. These results demonstrate the durability of our business, our multiple avenues for growth and continued discipline of balancing both future growth investment and operational leverage.” (1) See notes below for definitions of GMV, MRR and additional information on Free Cash Flow and Free Cash Flow margin, which are non-GAAP financial measures and are reconciled to the comparable GAAP measure in the Condensed Consolidated Statement of Cash Flows. Shopify Q3 2024 Revenue Growth Accelerates to 26%, Free Cash Flow Margin Expands to 19% Three months ended September 30, 2024 September 30, 2023 GMV 69,715 56,205 MRR 175 137 Revenues 2,162 1,714 Gross profit 1,118 901 Operating income 283 122 Free cash flow 421 276 YoY revenues growth rate 26% 25% Free cash flow margin 19% 16% Selected Business Performance Information(1) (In US $ millions, except percentages) Exhibit 99.1'

SHOP_Q3_2024_PAGE2 = '2 2024 Outlook The outlook that follows supersedes all prior financial outlook statements made by Shopify, constitutes forward-looking information within the meaning of applicable securities laws, and is based on a number of assumptions and subject to a number of risks. Actual results could vary materially as a result of numerous factors, including certain risk factors, many of which are beyond Shopify’s control. Please see “Forward-looking Statements” below for more information. For the fourth quarter of 2024, we expect: • Revenues to grow at a mid-to-high-twenties percentage rate on a year-over-year basis; • Gross profit dollars to grow at a year-over-year rate similar to Q3 2024; • GAAP operating expense as a percentage of revenues to be 32% to 33%; • Stock-based compensation to be $120 million; and • Free cash flow margin to be similar to Q4 2023. Quarterly Conference Call Shopify’s management team will hold a conference call to discuss our third-quarter results today, November 12, 2024, at 8:30 a.m. ET. The conference call will be webcast on the investor relations section of Shopify’s website at www.shopifyinvestors.com/news-and-events. An archived replay of the webcast will be available following the conclusion of the call. Shopify’s Third Quarter 2024 Interim Unaudited Condensed Consolidated Financial Statements and Notes and its Third Quarter 2024 Management’s Discussion and Analysis will be available on Shopify’s website at www.shopifyinvestors.com and will be filed on SEDAR+ at www.sedarplus.ca and on EDGAR at www.sec.gov. About Shopify Shopify is the leading global commerce company that provides essential internet infrastructure for commerce, offering trusted tools to start, scale, market, and run a retail business of any size. Shopify makes commerce better for everyone with a platform and services that are engineered for speed, customization, reliability, and security, while delivering a better shopping experience for consumers online, in store and everywhere in between. Shopify powers millions of businesses in more than 175 countries and is trusted by brands such as Mattel, Gymshark, Heinz, FTD, Netflix, Kylie Cosmetics, SKIMS, Supreme, and many more. For more information visit www.shopify.com CONTACT INVESTORS: Carrie Gillard Director, Investor Relations IR@shopify.com CONTACT MEDIA: Alex Lyons Senior Lead, External Communications press@shopify.com Notes: (1)Gross Merchandise Volume, or GMV, represents the total dollar value of orders facilitated through the Shopify platform including certain apps and channels for which a revenue-sharing arrangement is in place in the period, net of refunds, and inclusive of shipping and handling, duty and value-added taxes. Monthly Recurring Revenue, or MRR, is calculated by multiplying the number of merchants by the average monthly subscription plan fee in effect on the last day of that period and is used by management as a directional indicator of subscription solutions revenue going forward assuming merchants maintain their subscription plan the following month. In the three months ended March 31, 2024, the Company revised the inclusion of paid trials in the calculation of MRR. Free Cash Flow and Free Cash Flow Margin are non-GAAP financial measures which are reconciled below in the Condensed Consolidated Statement of Cash Flows.'

SHOP_Q3_2024_LINES = [
    "EX-99.1",
    "2",
    "a3pr.htm",
    "EX-99.1",
    SHOP_Q3_2024_PAGE1,
    SHOP_Q3_2024_PAGE2,
]


def test_shop_q3_2024_salved_end_to_end() -> None:
    # Batch 163: was None (batch-105 guard); now the real headline plus a
    # quote lede carrying the quarter's figures.
    result = extract_press_release_highlights(_bare_release_html(*SHOP_Q3_2024_LINES))
    assert result is not None
    headline, _, body = result.partition("\n\n")
    assert headline == (
        "Shopify Q3 2024 Revenue Growth Accelerates to 26%, "
        "Free Cash Flow Margin Expands to 19%"
    )
    assert body.startswith(
        "Internet, Everywhere - November 12, 2024 - Shopify Inc. "
        "(NYSE, TSX: SHOP), a leading commerce technology company "
        "announced today financial results for the quarter ended "
        "September 30, 2024."
    )
    assert "Q3 was outstanding" in body
    assert "Shopify achieved 26% revenue growth and 19% free cash flow margin" in body
    assert "GMV" not in body
    assert "69,715" not in body
    assert "2024 Outlook" not in body


def test_salved_result_fails_without_the_fix() -> None:
    # The salvage is the only path to a result here: the first paragraph
    # is a 1000+ char page-line with no headline, so the batch-105 guard
    # fires. Guard the regression by asserting the salvage itself is what
    # produces the lede.
    salvaged = _salvage_page_line_lede(SHOP_Q3_2024_PAGE1)
    assert salvaged is not None
    assert salvaged.startswith(
        "Shopify Q3 2024 Revenue Growth Accelerates to 26%, "
        "Free Cash Flow Margin Expands to 19%\n\nInternet, Everywhere"
    )


def test_page_dateline_regex() -> None:
    assert _PAGE_DATELINE_RE.match(SHOP_Q3_2024_PAGE1)
    assert _PAGE_DATELINE_RE.match(
        "NEW YORK, July 30, 2026 - Acme Inc. announced second quarter results."
    )
    assert _PAGE_DATELINE_RE.match(
        "2 OMAHA, May 2, 2026 - Berkshire Hathaway Inc. reported first quarter results."
    )
    assert not _PAGE_DATELINE_RE.match(
        "1 Consolidated Statements of Operations (In millions) Three months ended"
    )
    assert not _PAGE_DATELINE_RE.match(
        "Revenue Growth Accelerates to 26%, Free Cash Flow Margin Expands to 19%"
    )


def test_sentence_splitter_abbreviation_guard() -> None:
    # "Inc." before a paren is a continuation, not a sentence end; the
    # closing-quote terminator ("...success." + Jeff) does split.
    sentences = _split_page_line_sentences(
        "Internet, Everywhere - November 12, 2024 - Shopify Inc. (NYSE, TSX: SHOP), "
        "a leading commerce technology company announced results. "
        "\u201cAs the busiest shopping season approaches, they trust Shopify.\u201d "
        "Jeff Hoffmeister, Chief Financial Officer of Shopify, said, "
        "\u201cShopify achieved 26% revenue growth.\u201d"
    )
    assert sentences[0].endswith("announced results.")
    assert "Shopify Inc." in sentences[0]
    assert sentences[1].startswith("\u201cAs the busiest")
    assert sentences[2].startswith("Jeff Hoffmeister")
    assert len(sentences) == 3


def test_sentence_splitter_no_split_on_abbreviations() -> None:
    sentences = _split_page_line_sentences(
        "The U.S. business grew. Mr. Smith said revenue rose. See Fig. 2 for detail."
    )
    assert len(sentences) == 3
    assert sentences[0] == "The U.S. business grew."
    assert sentences[1] == "Mr. Smith said revenue rose."


def test_salvage_rejects_dateline_less_page_line() -> None:
    # Bank of America slide deck (batch 105): a page-line with no dateline
    # and no narrative sentences still returns None.
    assert _salvage_page_line_lede(
        "1 Bank of America Reports Third Quarter 2024 Net Income of $6.9 Billion "
        "Consumer Banking Global Wealth and Investment Management Global Banking "
        "Global Markets All Other 6,900 5,400 3,200 2,100 900 700"
    ) is None


def test_salvage_rejects_table_only_dateline_line() -> None:
    # A dateline followed only by table residue is not a lede.
    assert _salvage_page_line_lede(
        "Internet, Everywhere - November 12, 2024 - Shopify Q3 2024 Revenue "
        "Growth Accelerates to 26% Three months ended September 30, 2024 "
        "September 30, 2023 GMV 69,715 56,205 MRR 175 137 Revenues 2,162 1,714"
    ) is None


def test_salvage_rejects_single_sentence_line() -> None:
    assert _salvage_page_line_lede(
        "Internet, Everywhere - November 12, 2024 - Shopify Inc. announced results."
    ) is None


def test_salvage_stops_at_boilerplate_and_drops_footnote() -> None:
    salvaged = _salvage_page_line_lede(
        "OMAHA, May 2, 2026 - Acme Inc. announced first quarter results today. "
        "Revenue grew 12 percent year over year to $410 million. "
        "Gross margin expanded to 31 percent as subscription solutions grew 26 percent. "
        "(1) See notes below for definitions of non-GAAP measures. "
        "Forward-looking Statements This release contains forward-looking statements "
        "about future events that may differ materially."
    )
    assert salvaged is not None
    assert "Revenue grew 12 percent" in salvaged
    assert "Gross margin expanded" in salvaged
    assert "See notes below" not in salvaged
    assert "Forward-looking" not in salvaged
