"""Batch 173: tail guards — footnote pointers, bare-numbered footnote
sentences, bare quote-attribution role lines, symbol-legend dash form,
and the "Key Points:" heading skip. The guards live at every collection
path that serves them (lede loop, leading-bullet block, Highlights
sections): Walmart's legend only surfaced through its Third-Quarter
Highlights section, which the lede-path tests never exercised.

The batch-172 lede dateline skip was reverted because the freed budget
line filled with these shapes; this batch adds the guards instead, with
no dateline change (a whole-line dateline skip drops real narrative in
80/1699 blast quarters — see the batch-173 blast analysis).
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _FOOTNOTE_POINTER_RE,
    _extract_highlights_sections,
    _is_bare_numbered_footnote,
    _is_bare_role_line,
    _LEDE_SYMBOL_LEGEND_RE,
    _opens_footnote_def,
    extract_press_release_highlights,
)


def test_pointer_opens_footnote_def():
    assert _FOOTNOTE_POINTER_RE.match("1 See additional information")
    assert _FOOTNOTE_POINTER_RE.match("1 Refer to the tables")
    assert _FOOTNOTE_POINTER_RE.match("2 See the Non-GAAP Measures section")
    assert _FOOTNOTE_POINTER_RE.match("1. See the appendix")
    assert not _FOOTNOTE_POINTER_RE.match("1 Revenue grew 12 percent")
    assert not _FOOTNOTE_POINTER_RE.match("See the tables below")
    assert _opens_footnote_def("1 See additional information", "")
    assert _opens_footnote_def("1 Refer to the tables", "")


def test_pointer_covers_parenthesized_form():
    # Carnival's tail pointer: "(See \u201cNon-GAAP Financial Measures\u201d
    # and \u201cReconciliation of Forecasted Data\u201d)" — a cross-reference
    # wrapped in parens, never narrative.
    assert _FOOTNOTE_POINTER_RE.match(
        "(See \u201cNon-GAAP Financial Measures\u201d and \u201cReconciliation of Forecasted Data\u201d)"
    )
    assert _opens_footnote_def(
        "(See \u201cNon-GAAP Financial Measures\u201d and \u201cReconciliation of Forecasted Data\u201d)", ""
    )
    assert not _FOOTNOTE_POINTER_RE.match("Revenue grew 5% year-over-year.")


def test_bare_numbered_footnote_opens():
    # WMT / CSX / XOM footnote sentences.
    assert _is_bare_numbered_footnote(
        "2 Comp sales for the 13-week period ended October 25th, 2024 "
        "compared to the 13-week period ended October 27th, 2023."
    )
    assert _is_bare_numbered_footnote(
        "1 Net debt is total debt of $39.0 billion less cash."
    )
    assert _is_bare_numbered_footnote("3 Source: Rystad Energy, outlook.")
    assert _is_bare_numbered_footnote(
        "1 Year-over-year comparisons utilize revised results."
    )


def test_bare_numbered_footnote_guards():
    # Unterminated: a wrapped bullet continuation, never a footnote.
    assert not _is_bare_numbered_footnote("12 of them in Texas")
    # Over 500 chars: a page/table mega-line, not a footnote.
    assert not _is_bare_numbered_footnote("2 " + "word " * 80 + ".")
    # Bullet with a footnote key: a bullet item, not a footnote.
    assert not _is_bare_numbered_footnote(
        "2 \u2022 Strategic acquisition of Arctos announced today."
    )
    # Lowercase quantity word after the number: a wrapped bullet
    # continuation (batch 164's mirror negative), not a footnote.
    assert not _is_bare_numbered_footnote(
        "1 million shares are included in the diluted count."
    )
    # Year-led prose and tickers are not bare-numbered footnotes.
    assert not _is_bare_numbered_footnote("2025 was a strong year.")
    assert not _is_bare_numbered_footnote("3M Reports Third Quarter Results.")
    # Headline loop still finds the headline past a footnote block.
    assert _opens_footnote_def("1 See additional information.", "")


def test_bare_role_line():
    assert _is_bare_role_line("Chief Financial Officer")
    assert _is_bare_role_line("President and Chief Executive Officer")
    assert _is_bare_role_line("Chief Executive Officer")
    assert _is_bare_role_line("General Counsel")
    assert not _is_bare_role_line("Our Chief Financial Officer said so.")
    assert not _is_bare_role_line("Investor Relations")
    assert not _is_bare_role_line("Robert S. Fauber")
    assert not _is_bare_role_line("Senior Vice President, Finance")


def test_symbol_legend_dash_form():
    assert _LEDE_SYMBOL_LEGEND_RE.match("NM = not meaningful")
    assert _LEDE_SYMBOL_LEGEND_RE.match("\u201ccc\u201d - constant currency")
    assert _LEDE_SYMBOL_LEGEND_RE.match('"cc" - constant currency')
    assert not _LEDE_SYMBOL_LEGEND_RE.match("Revenue grew 5%.")
    assert not _LEDE_SYMBOL_LEGEND_RE.match("cc - constant currency")


def _extract(body_lines):
    # Like batch 169's _letter_html: no lorem filler (it trips the
    # page-line guard on section joins); the verbatim lines below keep
    # the document over the 800-char floor on their own.
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


def test_lede_drops_wmt_footnote_run():
    out = _extract([
        "Walmart Reports Third Quarter Results",
        "\u2022Consolidated revenue of $169.6 billion, up 5.5%, or 6.2% (cc)1",
        "\u2022Consolidated gross margin rate up 21 bps, led by Walmart U.S.",
        "\u2022Consolidated operating income up $0.5 billion, or 8.2%, up 9.8% (cc)1 "
        "due to higher gross margins and growth in membership income; also benefited "
        "from reduced losses in eCommerce",
        "\u2022ROA at 7.8%; ROI at 15.1%1, up 100 bps",
        "\u2022Global eCommerce sales grew 27%, led by store-fulfilled pickup & delivery and marketplace",
        "\u2022Global advertising business3 grew 28%, including 26% for Walmart Connect in the U.S.",
        "\u2022Adjusted EPS1 of $0.58 excludes the effect, net of tax, from a net loss of $0.01 on equity and other investments",
        "\u2022Global inventory down 1.0%, including a decrease of 0.6% for Walmart U.S.; in-stock levels healthy",
        "1 See additional information at the end of the release regarding non-GAAP financial measures.",
        "2 Comp sales for the 13-week period ended October 25th, 2024 compared to the 13-week period ended October 27th, 2023, and excludes fuel.",
        "3 Our global advertising business is recorded in either net sales or as a reduction to cost of sales, depending on the nature of the advertising arrangement.",
        "\u201ccc\u201d - constant currency",
    ])
    assert out is not None
    assert "See additional information" not in out
    assert "Comp sales for the 13-week" not in out
    assert "global advertising business is recorded" not in out
    assert "constant currency" not in out
    assert "Consolidated revenue of $169.6 billion" in out
    assert "Global eCommerce sales grew 27%" in out


def test_lede_drops_mco_role_lines():
    out = _extract([
        "MOODY'S CORPORATION REPORTS RESULTS FOR THIRD QUARTER 2024",
        "NEW YORK, NY - October 22, 2024 - Moody's Corporation (NYSE: MCO) today announced results for the third quarter of 2024, and updated its outlook for full year 2024.",
        "\u201cMoody\u2019s record-breaking revenue performance in the third quarter is a testament to our unwavering status as the Agency of Choice for our customers and our actions to prime the business for durable future growth. In parallel, we delivered strong recurring revenue growth in our analytics business, driven by investments and innovation.\u201d",
        "President and Chief Executive Officer",
        "\u201cThis was a fantastic quarter for Moody\u2019s, with revenue increasing 23%. MIS transactional revenue grew 70%, outpacing issuance growth of 51% and driving a 29% increase in operating cash flow. As a result of this remarkable performance, we are raising our adjusted diluted EPS guidance and narrowing the range to $11.90 to $12.10.\u201d",
        "Chief Financial Officer",
        "\u2022Revenue increased 23% from the prior-year period.",
        "\u2022Foreign currency translation had an immaterial impact on MCO\u2019s revenue.",
    ])
    assert out is not None
    assert "President and Chief Executive Officer" not in out
    assert "Chief Financial Officer" not in out
    assert "record-breaking revenue performance" in out
    assert "Revenue increased 23%" in out


def test_lede_skips_key_points_heading():
    out = _extract([
        "THE WALT DISNEY COMPANY REPORTS FOURTH QUARTER EARNINGS",
        "BURBANK, Calif. \u2013 The Walt Disney Company today reported earnings for its fourth quarter and full year ended September 28, 2024.",
        "Financial Results for the Quarter and Full Year:",
        "\u2022Revenues increased 6% for Q4 to $22.6 billion from $21.2 billion in the prior-year quarter, and 3% for the year to $91.4 billion from $88.9 billion in the prior year.",
        "\u2022Income before income taxes declined 6% to $0.9 billion in Q4 from $1.0 billion in the prior-year quarter and increased 59% for the year to $7.6 billion from $4.8 billion in the prior year.",
        "\u2022Diluted earnings per share (EPS) for Q4 increased 79% to $0.25 from $0.14 in the prior-year quarter, and for the year more than doubled to $2.72 from $1.29 in the prior year.",
        "Key Points:",
        "\u2022We achieved strong 23% growth in total segment operating income(1) for Q4 and 21% for the year, and 39% growth in adjusted EPS(1) to $1.14 from $0.82 for Q4 and 32% to $4.97 from $3.76 for the year.",
        "\u2022Diluted EPS increased 79% to $0.25 for Q4 and more than doubled to $2.72 for the year.",
    ])
    assert out is not None
    assert "We achieved strong 23% growth" in out
    assert out.count("Key Points:") == 0


def test_highlights_section_drops_legend_and_role_lines():
    # Walmart Q3 FY2025, verbatim shapes: the legend sits after the
    # footnote run inside the Third-Quarter Highlights section, and the
    # section collector is the path that serves it — the lede-path
    # tests never exercised this filter.
    sections = _extract_highlights_sections([
        "Third-Quarter Highlights",
        "\u2022Consolidated revenue of $169.6 billion, up 5.5%, or 6.2% (cc)1",
        "\u2022Consolidated gross margin rate up 21 bps, led by Walmart U.S.",
        "\u2022Global eCommerce sales grew 27%, led by store-fulfilled pickup & delivery and marketplace",
        "\u2022Global advertising business3 grew 28%, including 26% for Walmart Connect in the U.S.",
        "1 See additional information at the end of the release regarding non-GAAP financial measures.",
        "\u201ccc\u201d - constant currency",
        "Chief Financial Officer",
        "Key Financial Metrics",
    ])
    assert sections
    text = "\n".join(sections[0])
    assert "See additional information" not in text
    assert "constant currency" not in text
    assert "Chief Financial Officer" not in text
    assert "Consolidated revenue of $169.6 billion" in text
    assert "Global eCommerce sales grew 27%" in text


def test_section_path_wmt_end_to_end():
    # The full WMT shape: the section wins over the lede (batch 102
    # financial priority), so the legend must not survive the section
    # filter even though the lede loop would also have dropped it.
    out = _extract([
        "Walmart Reports Third Quarter Results",
        "BENTONVILLE, Ark., November 19, 2024 - Walmart Inc. (NYSE: WMT) announces third-quarter results with strong growth in revenue and operating income, and raises its guidance for FY25 with net sales expected to grow 4.8% to 5.1% in constant currency.",
        "Third-Quarter Highlights",
        "\u2022Consolidated revenue of $169.6 billion, up 5.5%, or 6.2% (cc)1",
        "\u2022Consolidated gross margin rate up 21 bps, led by Walmart U.S.",
        "\u2022Consolidated operating income up $0.5 billion, or 8.2%, up 9.8% (cc)1 due to higher gross margins and growth in membership income; also benefited from reduced losses in eCommerce",
        "\u2022ROA at 7.8%; ROI at 15.1%1, up 100 bps",
        "\u2022Global eCommerce sales grew 27%, led by store-fulfilled pickup & delivery and marketplace",
        "\u2022Global advertising business3 grew 28%, including 26% for Walmart Connect in the U.S.",
        "\u2022Adjusted EPS1 of $0.58 excludes the effect, net of tax, from a net loss of $0.01 on equity and other investments",
        "\u2022Global inventory down 1.0%, including a decrease of 0.6% for Walmart U.S.; in-stock levels healthy",
        "1 See additional information at the end of the release regarding non-GAAP financial measures.",
        "2 Comp sales for the 13-week period ended October 25th, 2024 compared to the 13-week period ended October 27th, 2023, and excludes fuel.",
        "3 Our global advertising business is recorded in either net sales or as a reduction to cost of sales, depending on the nature of the advertising arrangement.",
        "\u201ccc\u201d - constant currency",
        "Key Financial Metrics",
        "Dollars in billions, except per share data. Dollar and percentage changes may not sum precisely due to rounding.",
    ])
    assert out is not None
    assert "See additional information" not in out
    assert "Comp sales for the 13-week" not in out
    assert "global advertising business is recorded" not in out
    assert "constant currency" not in out
    assert "Consolidated revenue of $169.6 billion" in out
    assert "Global inventory down 1.0%" in out
