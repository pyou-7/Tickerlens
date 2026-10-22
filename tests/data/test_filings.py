from datetime import date

from tickerlens.data.filings import (
    AnnualFiling,
    _html_to_text,
    extract_risk_factors,
    filing_doc_url,
    latest_annual_filing,
)

# A trimmed 10-K shape: a table of contents that *links* to "Item 1A. Risk Factors"
# (a short false match), then the real section with substantial body text, bounded
# by "Item 2. Properties".
_REAL_BODY = (
    "Our business is subject to numerous risks and uncertainties. "
    "A prolonged economic downturn could reduce demand for our products. "
    "We depend on a limited number of suppliers and any disruption could harm results. "
    "Cybersecurity incidents may compromise sensitive data and damage our reputation. "
    "Changes in tax law or regulation could increase our costs of doing business. "
    "Foreign currency fluctuations may adversely affect our reported revenue. "
    "Intense competition may erode our market share and pressure our margins. "
    "We may be unable to attract and retain the key personnel our operations require. "
    "Product defects or recalls could expose us to liability and reputational harm. "
    "Our international operations subject us to political and legal uncertainty. "
    "Failure to protect our intellectual property could diminish our competitive position. "
)

_TEN_K_HTML = f"""
<html><head><style>.x{{color:red}}</style></head><body>
  <table>
    <tr><td>Item 1A. Risk Factors</td><td>15</td></tr>
    <tr><td>Item 1B. Unresolved Staff Comments</td><td>40</td></tr>
    <tr><td>Item 2. Properties</td><td>41</td></tr>
  </table>
  <h2>Item 1A. Risk Factors</h2>
  <p>{_REAL_BODY}</p>
  <h2>Item 2. Properties</h2>
  <p>We own and lease facilities around the world.</p>
</body></html>
"""


def test_extract_risk_factors_ignores_toc_and_returns_real_section() -> None:
    result = extract_risk_factors(_TEN_K_HTML)
    assert result is not None
    assert "prolonged economic downturn" in result
    # Bounded correctly — the Properties body must not bleed in.
    assert "lease facilities" not in result
    # The short TOC page number must not be the chosen section.
    assert result.strip() != "15"


def test_extract_risk_factors_strips_noscript_content() -> None:
    body = "We face material operational and financial risks across our business. " * 12
    html = (
        "<body><noscript>ENABLE JAVASCRIPT NAVIGATION MENU</noscript>"
        f"<h2>Item 1A. Risk Factors</h2><p>{body}</p>"
        "<h2>Item 2. Properties</h2></body>"
    )
    result = extract_risk_factors(html)
    assert result is not None
    assert "ENABLE JAVASCRIPT" not in result


def test_extract_risk_factors_returns_none_when_section_absent() -> None:
    html = "<html><body><p>Item 1. Business. We make things.</p></body></html>"
    assert extract_risk_factors(html) is None


def test_extract_risk_factors_returns_none_when_only_toc_stub() -> None:
    # Item 1A appears but is immediately followed by the next item — too short to
    # be the real section.
    html = "<body>Item 1A. Risk Factors 15 Item 1B. Unresolved Staff Comments 40</body>"
    assert extract_risk_factors(html) is None


def test_extract_risk_factors_truncates_to_max_chars() -> None:
    body = "risk sentence. " * 400  # ~6000 chars, well over the cap
    html = f"<body><h2>Item 1A. Risk Factors</h2><p>{body}</p><h2>Item 2. Properties</h2></body>"
    result = extract_risk_factors(html, max_chars=1000)
    assert result is not None
    assert len(result) <= 1001  # 1000 + ellipsis, minus the trailing partial word
    assert result.endswith("…")


def test_extract_risk_factors_stops_at_cybersecurity_item_1c() -> None:
    long_body = "We face material risks to our operations and financial condition. " * 12
    html = (
        f"<body><h2>Item 1A. Risk Factors</h2><p>{long_body}</p>"
        "<h2>Item 1C. Cybersecurity</h2><p>We maintain a security program.</p></body>"
    )
    result = extract_risk_factors(html)
    assert result is not None
    assert "security program" not in result


def test_extract_risk_factors_rescues_span_split_heading() -> None:    # DFIN-prepared 10-Ks (MSFT, BRK.B, MCD, INTC, ...) split the real heading
    # across adjacent <span>s with no whitespace: "RIS</span><span>K FACTORS".
    # The old tag->space join corrupted this to "RIS K FACTORS", so the real
    # heading never matched and only the TOC stub survived -> None.
    html = f"""
    <html><body>
      <table>
        <tr><td><a href="#item_1a_risk_factors">Risk Factors</a></td><td>14</td></tr>
        <tr><td>Item 1B. Unresolved Staff Comments</td><td>29</td></tr>
      </table>
      <p id="item_1a_risk_factors"><span>ITEM 1A. RIS</span><span>K FACTORS</span></p>
      <p>{_REAL_BODY}</p>
      <p><span>ITEM 1B. UNRESOLVED STAFF COMMENTS</span></p>
    </body></html>
    """
    result = extract_risk_factors(html)
    assert result is not None
    assert "prolonged economic downturn" in result
    assert result.strip() != "14"


def test_extract_risk_factors_matches_em_dash_heading_separator() -> None:
    # Dell's 10-K heads the section "ITEM 1A — RISK FACTORS" (em dash); the
    # separator class must cover it or only the TOC stub matches -> None.
    body = "We face material operational and financial risks. " * 20
    html = (
        "<body><table><tr><td>Item 1A. Risk Factors</td><td>16</td></tr></table>"
        f"<p>ITEM 1A — RISK FACTORS</p><p>{body}</p>"
        "<p>ITEM 1B. UNRESOLVED STAFF COMMENTS</p></body>"
    )
    result = extract_risk_factors(html)
    assert result is not None
    assert "material operational and financial risks" in result


def test_extract_risk_factors_falls_back_to_bare_caps_heading() -> None:
    # McDonald's/Citi style: no "Item 1A" prefix anywhere, one standalone
    # all-caps "RISK FACTORS" line heads the real section.
    body = "Our business results are subject to a variety of risks. " * 20
    html = (
        "<body><table><tr><td>Item 1A Risk Factors</td><td>27</td></tr></table>"
        f"<p>Some Company 2025 Annual Report 26</p><p>RISK FACTORS</p><p>{body}</p>"
        "<p>Item 1B. Unresolved Staff Comments</p></body>"
    )
    result = extract_risk_factors(html)
    assert result is not None
    assert "subject to a variety of risks" in result


def test_extract_risk_factors_ignores_caps_running_headers() -> None:
    # Honeywell style: "RISK FACTORS" repeats as a running page header — the
    # fallback must not fire on ambiguity.
    body = "We face material operational and financial risks. " * 4  # < floor
    headers = "<p>RISK FACTORS</p>".join(f"<p>page {i} filler</p>" for i in range(6))
    html = f"<body>{headers}<p>{body}</p></body>"
    assert extract_risk_factors(html) is None


def test_extract_risk_factors_no_fallback_when_real_heading_is_cross_ref() -> None:
    # BNY/WFC style: the real "ITEM 1A. RISK FACTORS" heading matched but the
    # section is only an incorporation-by-reference stub — the fallback must
    # not second-guess the document's own structure, even when the lone caps
    # line heads a long section that would pass the floor on its own.
    long_body = "See our annual report for the full discussion of risks. " * 20
    html = (
        "<body><p>ITEM 1A. RISK FACTORS</p>"
        "<p>The information required by this Item is set forth in our Annual Report.</p>"
        "<p>ITEM 1B. UNRESOLVED STAFF COMMENTS</p><p>None.</p>"
        f"<p>RISK FACTORS</p><p>{long_body}</p>"
        "<p>ITEM 2. PROPERTIES</p></body>"
    )
    assert extract_risk_factors(html) is None


def test_html_to_text_concatenates_adjacent_inline_spans() -> None:
    # Adjacent inline elements with no whitespace render concatenated in a
    # browser; the linearizer must not invent a space between them.
    assert _html_to_text("<p>RIS</span><span>K FACTORS</p>") == "RISK FACTORS"
    # Genuine whitespace between elements is preserved.
    assert _html_to_text("<p><span>Q3</span> <span>revenue</span></p>") == "Q3 revenue"
    # Non-inline tags still separate content (table cells must not glue).
    assert _html_to_text("<td>foo</td><td>bar</td>") == "foo bar"


def test_latest_annual_filing_picks_most_recent_10k() -> None:
    submissions = {
        "filings": {
            "recent": {
                "form": ["10-Q", "10-K", "8-K", "10-K"],
                "accessionNumber": ["a-q", "a-k-2023", "a-8k", "a-k-2024"],
                "primaryDocument": ["q.htm", "k2023.htm", "8k.htm", "k2024.htm"],
                "filingDate": ["2025-02-01", "2023-11-01", "2025-01-15", "2024-11-01"],
            }
        }
    }
    filing = latest_annual_filing(submissions)
    assert filing is not None
    assert filing.accession == "a-k-2024"
    assert filing.primary_doc == "k2024.htm"


def test_latest_annual_filing_none_when_no_10k() -> None:
    submissions = {
        "filings": {"recent": {"form": ["10-Q"], "accessionNumber": ["a"],
                               "primaryDocument": ["q.htm"], "filingDate": ["2025-02-01"]}}
    }
    assert latest_annual_filing(submissions) is None


def test_filing_doc_url_builds_archive_path() -> None:
    filing = AnnualFiling(accession="0000320193-24-000123", primary_doc="aapl-20240928.htm",
                          filing_date=date(2024, 11, 1))
    url = filing_doc_url("0000320193", filing)
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019324000123/aapl-20240928.htm"
    )


# ── extract_press_release_highlights ─────────────────────────────────────────

from tickerlens.data.filings import extract_press_release_highlights  # noqa: E402


def _release_html(
    *,
    headline: str = "Acme Corp Reports Fourth Quarter 2025 Results",
    include_highlights: bool = True,
    include_admin_line: bool = True,
) -> str:
    lede = (
        "CUPERTINO, California — Acme Corp today announced financial results for its "
        "fiscal 2025 fourth quarter ended December 31, 2025. The Company posted quarterly "
        "revenue of 50.2 billion dollars, up 8 percent year over year, and quarterly diluted "
        "earnings per share of 2.10 dollars, up 12 percent year over year. Gross margin was "
        "44 percent, reflecting a strong product mix and continued services growth."
    )
    quote = (
        '"We delivered record revenue this quarter," said Jane Doe, Chief Executive Officer. '
        '"Our installed base reached a new all-time high across every product category." '
    ) * 3
    bullets = "".join(
        f"<li>{b}. Additional context comparing against prior periods.</li>"
        for b in [
            "Revenue of 50.2 billion dollars, up 8 percent year over year",
            "Diluted EPS of 2.10 dollars, up 12 percent year over year",
            "Operating cash flow of 15.3 billion dollars, a quarterly record",
        ]
    )
    highlights = f"<h2>Financial Highlights</h2><ul>{bullets}</ul>" if include_highlights else ""
    admin = "<p>FOR IMMEDIATE RELEASE</p>" if include_admin_line else ""
    return f"""<html><head><title>EX-99.1</title></head><body>
{admin}
<h1>{headline}</h1>
<p>{lede}</p><p>{quote}</p>
{highlights}
<h2>ABOUT ACME CORP</h2><p>Acme Corp designs and sells widgets worldwide.</p>
<h2>Forward-Looking Statements</h2><p>This press release contains forward-looking statements.</p>
</body></html>"""


def test_extract_pr_highlights_uses_highlights_section() -> None:
    result = extract_press_release_highlights(_release_html())
    assert result is not None
    assert "Acme Corp Reports Fourth Quarter 2025 Results" in result
    assert "Revenue of 50.2 billion dollars" in result
    # Boilerplate must not leak in.
    assert "forward-looking statements" not in result.lower()
    assert "widgets worldwide" not in result.lower()


def test_extract_pr_highlights_skips_admin_line_and_title() -> None:
    result = extract_press_release_highlights(_release_html())
    assert result is not None
    assert "EX-99.1" not in result
    assert "FOR IMMEDIATE RELEASE" not in result


def test_extract_pr_highlights_falls_back_to_lede() -> None:
    result = extract_press_release_highlights(_release_html(include_highlights=False))
    assert result is not None
    assert "CUPERTINO, California" in result
    assert "forward-looking statements" not in result.lower()


def test_extract_pr_highlights_skips_sec_exhibit_headers() -> None:
    """Regression: real EDGAR ex-99 exhibits (e.g. Apple's) open with SEC
    exhibit headers — EX-99.1 labels, page numbers, filenames — that must not
    be mistaken for the headline or consume the lede budget."""
    lede = (
        "CUPERTINO, California — Acme Corp today announced financial results for its "
        "fiscal 2025 fourth quarter ended December 31, 2025. The Company posted quarterly "
        "revenue of 50.2 billion dollars, up 8 percent year over year, and quarterly diluted "
        "earnings per share of 2.10 dollars, up 12 percent year over year. Gross margin was "
        "44 percent, reflecting a strong product mix and continued services growth."
    )
    html = f"""<html><head><title>EX-99.1</title></head><body>
<p>EX-99.1</p><p>2</p><p>a8-kex991q4202509272025.htm</p><p>EX-99.1</p>
<p>Exhibit 99.1</p>
<h1>Acme Corp Reports Fourth Quarter 2025 Results</h1>
<p>iPhone drives record September quarter revenue</p>
<p>{lede}</p><p>Services revenue reaches new all-time high, up 14 percent.</p>
<p>The board of directors declared a cash dividend of 0.25 dollars per share, payable
in January to shareholders of record, reflecting confidence in the Company's
long-term cash generation and capital return program.</p>
<h2>ABOUT ACME CORP</h2><p>Acme Corp designs and sells widgets worldwide.</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert result.startswith("Acme Corp Reports Fourth Quarter 2025 Results")
    assert "CUPERTINO, California" in result
    assert "EX-99.1" not in result
    assert "a8-kex991q4202509272025.htm" not in result
    assert "Exhibit 99.1" not in result
    assert "widgets worldwide" not in result.lower()


def test_extract_pr_highlights_returns_none_for_stub() -> None:
    assert extract_press_release_highlights("<html><body>too short</body></html>") is None


def test_extract_pr_highlights_truncates_to_max_chars() -> None:
    body = "record revenue quarter. " * 400
    html = f"<html><body><h1>Acme Reports Results</h1><p>{body}</p></body></html>"
    result = extract_press_release_highlights(html, max_chars=1000)
    assert result is not None
    assert len(result) <= 1001  # 1000 + ellipsis, minus the trailing partial word
    assert result.endswith("…")


# ── extract_management_guidance & extract_transcript_excerpts ─────────────────

from tickerlens.data.filings import (
    extract_management_guidance,
    extract_transcript_excerpts,
)


def test_extract_management_guidance_finds_section() -> None:
    html = """<html><body>
    <h1>Acme Corp Q3 Results</h1>
    <p>Acme Corp today reported revenue of $10 billion, up 15 percent year over year.</p>
    <h2>Business Outlook</h2>
    <p>Acme's outlook for the fourth quarter of fiscal 2026 is as follows:</p>
    <p>• Revenue is expected to be between $11.5 billion and $12.0 billion.</p>
    <p>• GAAP gross margin is expected to be approximately 45.0%.</p>
    <p>• Diluted earnings per share is expected to be $0.85 to $0.90.</p>
    <h2>Condensed Consolidated Statements of Operations</h2>
    <p>Revenue: $10,000</p>
    <h2>About Acme Corp</h2>
    </body></html>"""
    guidance = extract_management_guidance(html)
    assert guidance is not None
    assert "Business Outlook" in guidance
    assert "$11.5 billion" in guidance
    assert "gross margin" in guidance.lower()
    assert "Condensed Consolidated" not in guidance


def test_extract_management_guidance_returns_none_when_absent() -> None:
    html = """<html><body>
    <h1>Acme Corp Q3 Results</h1>
    <p>Acme Corp today reported revenue of $10 billion, up 15 percent year over year.</p>
    <p>The company continues to execute well across all segments.</p>
    <h2>About Acme Corp</h2>
    <p>Widgets worldwide.</p>
    </body></html>"""
    assert extract_management_guidance(html) is None


def test_extract_transcript_excerpts_finds_quotes() -> None:
    html = """<html><body>
    <h1>Acme Corp Q3 Results</h1>
    <p>“Our AI business is growing at unprecedented rates, driving strong customer adoption worldwide,” said Jane Doe, Chief Executive Officer.</p>
    <p>“We generated record free cash flow of $4.5 billion this quarter, demonstrating strong operating discipline,” noted John Smith, Chief Financial Officer.</p>
    <h2>Financial Highlights</h2>
    <p>Revenue up 20%.</p>
    </body></html>"""
    excerpts = extract_transcript_excerpts(html)
    assert excerpts is not None
    assert "Jane Doe" in excerpts
    assert "John Smith" in excerpts
    assert "Our AI business is growing" in excerpts
    assert "•" in excerpts


def test_extract_transcript_excerpts_returns_none_when_no_quotes() -> None:
    html = """<html><body>
    <h1>Acme Corp Q3 Results</h1>
    <p>Acme Corp today reported revenue of $10 billion, up 15 percent year over year.</p>
    <p>The company continues to execute well across all segments.</p>
    </body></html>"""
    assert extract_transcript_excerpts(html) is None


def test_extract_transcript_excerpts_finds_speaker_first_quotes() -> None:
    # JPMorgan-style attribution: "Jamie Dimon, Chairman and CEO, commented: "…"".
    html = """<html><body>
    <h1>JPMorgan Chase Q4 Results</h1>
    <p>Jamie Dimon, Chairman and CEO, commented: “The Firm concluded the year with a strong
    fourth quarter, generating net income of $14.7 billion on revenue of $45 billion.”</p>
    <p>“Our fortress balance sheet allowed us to support clients through volatile markets,” said Jane Doe, Chief Financial Officer.</p>
    </body></html>"""
    excerpts = extract_transcript_excerpts(html)
    assert excerpts is not None
    assert "Jamie Dimon" in excerpts
    assert "fortress balance sheet" in excerpts


def test_extract_transcript_excerpts_finds_attribution_with_phrase_before_colon() -> None:
    # "commented on the financial results:" — words between verb and colon.
    html = """<html><body>
    <h1>JPMorgan Chase Q2 Results</h1>
    <p>JPMorgan Chase & Co. today reported second-quarter 2026 net income of $16.9 billion,
    or $5.80 per share, on revenue of $46.2 billion, reflecting strong performance across
    each of its business segments and continued balance sheet strength.</p>
    <p>Jamie Dimon, Chairman and CEO, commented on the financial results: “The Firm reported
    very strong results in the quarter, generating net income of $16.9 billion.”</p>
    </body></html>"""
    excerpts = extract_transcript_excerpts(html)
    assert excerpts is not None
    assert "Jamie Dimon" in excerpts
    assert "very strong results" in excerpts


def test_extract_management_guidance_quarter_prefixed_long_headings() -> None:
    # Batch-50: long-form quarter-prefixed headings seen in the wild.
    for heading in (
        "Fourth Quarter Fiscal Year 2026 Business Outlook",  # AVGO
        "Full Year Fiscal 2027 Guidance",  # INTU
        "First Quarter Fiscal 2027 Guidance",  # INTU
        "Forward-Looking Guidance",  # INTU
        "Full-year 2026 guidance:",  # JNJ
    ):
        html = f"""<html><body>
        <h1>Acme Corp Q3 Results</h1>
        <h2>{heading}</h2>
        <p>Revenue is expected to be between $11.5 billion and $12.0 billion next quarter, with strong growth across all segments and continued momentum.</p>
        <p>GAAP gross margin is expected to be approximately 45.0% on the strength of the product mix.</p>
        <h2>Condensed Consolidated Statements of Operations</h2>
        <p>Revenue: $10,000</p>
        </body></html>"""
        guidance = extract_management_guidance(html)
        assert guidance is not None, heading
        assert heading in guidance
        assert "$11.5 billion" in guidance
        assert "Condensed Consolidated" not in guidance


def test_extract_press_release_highlights_skips_leading_contact_block() -> None:
    # Batch-50: JNJ's ex-99 puts media/investor contacts before the headline and
    # has no "Highlights" section. The old code picked "Media contact:" as the
    # headline and let "Investor contact:" terminate the lede fallback, yielding
    # None for the whole release.
    html = """<html><body>
    <p>EX-99.1</p><p>2</p><p>a2026q2exhibit991.htm</p><p>EX-99.1</p><p>Exhibit 99.1</p>
    <p>Media contact:</p><p>media-relations@its.jnj.com</p>
    <p>Investor contact:</p><p>investor-relations@its.jnj.com</p>
    <p>For immediate release</p>
    <p>Johnson &amp; Johnson reports Q2 2026 results, raises 2026 outlook</p>
    <p>• 2026 Second-Quarter reported sales growth of 6.6% to $25.3 billion with operational growth of 5.6% and adjusted operational growth of 7.1%.</p>
    <p>• 2026 Second-Quarter earnings per share (EPS) of $2.27 and adjusted EPS of $2.90, reflecting strong operational performance across the portfolio.</p>
    <p>• Strong operational performance results in the Company increasing 2026 guidance with estimated reported sales growth now expected at the high end.</p>
    <p>New Brunswick, N.J. (July 15, 2026) – Johnson &amp; Johnson today announced results for second-quarter 2026, delivering another quarter of strong growth.</p>
    <h2>About Johnson &amp; Johnson</h2>
    <p>Boilerplate company description.</p>
    </body></html>"""
    hl = extract_press_release_highlights(html)
    assert hl is not None
    assert "Johnson & Johnson reports Q2 2026 results" in hl
    assert "$25.3 billion" in hl
    assert "media-relations@its.jnj.com" not in hl
    assert "Media contact" not in hl
    assert "About Johnson" not in hl


def test_extract_press_release_highlights_skips_bare_contact_block() -> None:
    # Batch-90: CHD's ex-99 opens with a company masthead, a bare "Contact:"
    # header, and name/title/phone detail lines before the headline. The old
    # code picked the masthead as the headline and let "Contact:" terminate the
    # lede fallback via the boilerplate regex, yielding None for the release.
    html = """<html><body>
    <p>EX-99.1</p><p>2</p><p>chd-ex99_1.htm</p><p>EX-99.1</p>
    <p>Church &amp; Dwight Co., Inc.</p>
    <p>News Release</p>
    <p>Contact:</p><p>Lee McChesney</p><p>Chief Financial Officer</p><p>609-806-1200</p>
    <p>CHURCH &amp; DWIGHT DELIVERS STRONG SECOND QUARTER RESULTS</p>
    <p>Q2 NET SALES, ORGANIC SALES AND ADJUSTED EPS EXCEED OUTLOOK</p>
    <p>RAISES FULL-YEAR 2026 SALES, EPS, AND CASH FLOW OUTLOOK</p>
    <p>EWING, NJ, July 31, 2026 \u2013 Church &amp; Dwight Co., Inc. (NYSE: CHD) today announced
    that the Company exceeded its second quarter outlook with stronger than expected
    sales and earnings growth across all three divisions, driven primarily by volume
    growth of 4.3% and positive price and product mix of 1.5%. Net sales increased
    1.6% to $1,530.0 million in the second quarter, exceeding the Company\u2019s outlook
    of a 1% decline and reflecting the benefits of its successful 2025 strategic
    portfolio actions across the household and personal care businesses.</p>
    <h2>About Church &amp; Dwight</h2>
    <p>Boilerplate company description.</p>
    </body></html>"""
    hl = extract_press_release_highlights(html)
    assert hl is not None
    assert "CHURCH & DWIGHT DELIVERS STRONG SECOND QUARTER RESULTS" in hl
    assert "Q2 NET SALES" in hl
    assert "exceeded its second quarter outlook" in hl
    assert "Lee McChesney" not in hl
    assert "Chief Financial Officer" not in hl
    assert "609-806-1200" not in hl
    assert "Contact:" not in hl
    # The masthead must not become the headline.
    assert not hl.startswith("Church & Dwight Co., Inc.")


def test_extract_press_release_highlights_skips_trailing_contacts_section() -> None:
    # Batch-90: Oracle-style bare "Contact:" block with name/department/phone/
    # email detail lines before a title-case headline, plus a trailing
    # "Contacts:" section whose detail lines must not pollute the lede.
    html = """<html><body>
    <p>EX-99.1</p><p>2</p><p>d20034dex991.htm</p><p>EX-99.1</p><p>Exhibit 99.1</p>
    <p>Contact:</p><p>Ken Bond</p><p>Oracle Investor Relations</p><p>1.650.607.0349</p>
    <p>ken.bond@oracle.com</p>
    <p>Oracle Reports Fiscal 2026 Second Quarter Results</p>
    <p>AUSTIN, Texas, December 10, 2026 \u2013 Oracle Corporation (NYSE: ORCL) today announced
    fiscal 2026 second quarter results with total revenue of $16.0 billion, up 8% in
    USD, driven by continued strength in cloud services and license support. Cloud
    revenue was up 24% as demand for Oracle Cloud Infrastructure continued to exceed
    available supply, and the Company signed several large multi-year agreements with
    enterprise customers across healthcare, financial services, and manufacturing.</p>
    <p>Contacts:</p><p>Deborah Hellinger</p><p>Oracle Corporate Communications</p>
    <p>1.212.508.7935</p><p>deborah.hellinger@oracle.com</p>
    <h2>About Oracle</h2>
    <p>Boilerplate company description.</p>
    </body></html>"""
    hl = extract_press_release_highlights(html)
    assert hl is not None
    assert "Oracle Reports Fiscal 2026 Second Quarter Results" in hl
    assert "$16.0 billion" in hl
    assert "Ken Bond" not in hl
    assert "Deborah Hellinger" not in hl
    assert "1.650.607.0349" not in hl
    assert "oracle.com" not in hl
    assert "About Oracle" not in hl


def test_skip_contact_block_is_bounded() -> None:
    # Batch-90: a misfired contact header must not swallow the release body —
    # at most 8 detail lines are skipped.
    from src.tickerlens.data.filings import _skip_contact_block

    lines = ["Contact:"] + [f"detail fragment {n}" for n in range(12)] + [
        "The real headline finally appears here with enough words"
    ]
    assert _skip_contact_block(lines, 0) == 9  # header + 8 details


def test_extract_press_release_highlights_skips_table_of_contents_packet() -> None:
    # Batch-91: SPG's ex-99 is a combined earnings-release + supplemental packet
    # that opens with a table of contents (cover block, section-title /
    # page-number pairs, footnote, mini-TOC). The old code picked "TABLE OF
    # CONTENTS" as the headline and filled the lede with TOC entries, yielding
    # None for the whole release. SPG's release also starts with a "Contacts:"
    # block (handled by batch-90's _skip_contact_block) and wraps its headline
    # across two lines.
    html = """<html><body>
    <p>EX-99.1</p><p>2</p><p>tm2620726d2_ex99-1.htm</p><p>EXHIBIT 99.1</p>
    <p>TABLE OF CONTENTS</p>
    <p>SIMON PROPERTY GROUP</p>
    <p>EARNINGS RELEASE &amp;</p>
    <p>SUPPLEMENTAL INFORMATION</p>
    <p>UNAUDITED SECOND QUARTER</p>
    <p>TABLE OF CONTENTS</p>
    <p>Earnings Release(1)</p><p>2–11</p>
    <p>Overview</p><p>12</p>
    <p>Financial Data</p>
    <p>Selected Financial and Equity Information</p><p>14</p>
    <p>Guidance Reconciliation</p><p>43</p>
    <p>(1)</p>
    <p>Includes reconciliation of consolidated net income to FFO and Real Estate FFO.</p>
    <p>2Q 2026 SUPPLEMENTAL</p><p>1</p>
    <p>TABLE OF CONTENTS</p>
    <p>EARNINGS RELEASE</p>
    <p>Contacts:</p><p>Tom Ward</p><p>317-685-7330 Investors</p>
    <p>Nicole Kennon</p><p>704-804-1960 Media</p>
    <p>Simon\u00ae Reports Second Quarter 2026 Results and</p>
    <p>Increases Guidance for Full Year 2026 Real Estate FFO Per Share</p>
    <p>INDIANAPOLIS, August 10, 2026 \u2013 Simon\u00ae, a real estate investment trust engaged in the ownership of premier shopping, dining, entertainment and mixed-use destinations, today reported results for the quarter ended June 30, 2026, with Real Estate FFO per share growing 7.9% year-over-year on broad-based leasing demand and accelerated traffic.</p>
    <h2>About Simon</h2>
    <p>Boilerplate company description.</p>
    </body></html>"""
    hl = extract_press_release_highlights(html)
    assert hl is not None
    # The wrapped headline is joined across its line break.
    assert (
        "Simon\u00ae Reports Second Quarter 2026 Results and "
        "Increases Guidance for Full Year 2026 Real Estate FFO Per Share"
    ) in hl
    assert "today reported results for the quarter ended June 30, 2026" in hl
    # No TOC residue: heading, entries, page numbers, footnote, mini-TOC.
    assert "TABLE OF CONTENTS" not in hl
    assert "Earnings Release(1)" not in hl
    assert "2–11" not in hl
    assert "SUPPLEMENTAL INFORMATION" not in hl
    assert "Includes reconciliation of consolidated net income" not in hl
    # No contact-block residue.
    assert "Tom Ward" not in hl
    assert "317-685-7330" not in hl
    assert "Contacts:" not in hl
    assert "About Simon" not in hl


def test_skip_toc_requires_page_numbers() -> None:
    # Batch-91: a stray "table of contents" mention in a normal release must
    # not trigger the skip — at least 2 page-number lines are required.
    from src.tickerlens.data.filings import _skip_toc

    lines = [
        "TABLE OF CONTENTS",
        "The full report is available in the table of contents section",
        "of our investor relations website for further reference today.",
        "Acme Corp Reports Fourth Quarter 2025 Results",
    ]
    assert _skip_toc(lines, 0) == 0


def test_skip_toc_stops_at_release_banner() -> None:
    # Batch-91: a TOC followed by a "For Immediate Release" banner stops the
    # skip at the banner — the headline pass then finds the real headline.
    from src.tickerlens.data.filings import _skip_toc

    lines = [
        "TABLE OF CONTENTS",
        "Earnings Release",
        "2–11",
        "Overview",
        "12",
        "For Immediate Release",
        "Acme Corp Reports Fourth Quarter 2025 Results",
    ]
    assert _skip_toc(lines, 0) == 5


def test_join_wrapped_headline_joins_conjunction_break() -> None:
    # Batch-91: a headline broken after a conjunction joins its continuation.
    from src.tickerlens.data.filings import _join_wrapped_headline

    lines = [
        "Simon\u00ae Reports Second Quarter 2026 Results and",
        "Increases Guidance for Full Year 2026 Real Estate FFO Per Share",
        "INDIANAPOLIS, August 10, 2026 \u2013 the lede starts here with a period.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == (
        "Simon\u00ae Reports Second Quarter 2026 Results and "
        "Increases Guidance for Full Year 2026 Real Estate FFO Per Share"
    )
    assert next_i == 2


def test_join_wrapped_headline_ignores_sentence_lede() -> None:
    # Batch-91: a headline ending in a wrap word is NOT joined to a
    # sentence-terminated lede line — the guard keeps short headlines from
    # swallowing the lede.
    from src.tickerlens.data.filings import _join_wrapped_headline

    lines = [
        "Acme Corp Reports Fourth Quarter 2025 Results and",
        "Net income was 5.2 billion dollars, up 8 percent year over year.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "Acme Corp Reports Fourth Quarter 2025 Results and"
    assert next_i == 1


def test_join_wrapped_headline_ignores_complete_headline() -> None:
    # Batch-91: a headline that doesn't end on a wrap word is left alone.
    from src.tickerlens.data.filings import _join_wrapped_headline

    lines = [
        "Acme Corp Reports Fourth Quarter 2025 Results",
        "CUPERTINO, California \u2014 the lede starts here with a period.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "Acme Corp Reports Fourth Quarter 2025 Results"
    assert next_i == 1


def test_extract_highlights_ignores_zwsp_and_furnished_parenthetical() -> None:
    # Batch-50: Deere's ex-99 pads sections with zero-width-space lines and
    # opens with "(Furnished herewith)". The zwsp lines filled the 6-line lede
    # cap with invisible text and the parenthetical became the headline,
    # yielding None for the whole release.
    zwsp = "​"
    html = f"""<html><body>
    <p>EX-99.1</p><p>2</p><p>de-20260820xex99d1.htm</p><p>EX-99.1</p><p>Exhibit 99.1</p>
    <p>(Furnished herewith)</p>
    <p>{zwsp}</p><p>{zwsp}</p><p>{zwsp}</p>
    <p>News Release</p>
    <p>{zwsp}</p>
    <p>Media Inquiries:</p><p>PublicRelations@JohnDeere.com</p>
    <p>{zwsp}</p>
    <p>Deere Reports Third Quarter Net Income of $1.379 Billion</p>
    <p>● Disciplined execution drives stronger-than-expected results across the enterprise, with net sales and revenues of $12.018 billion for the quarter.</p>
    <p>● Net income guidance improved to $4.75 billion to $5.00 billion for fiscal 2026, reflecting resilient demand in production agriculture.</p>
    <p>MOLINE, Illinois (August 20, 2026) – Deere &amp; Company reported net income of $1.379 billion for the third quarter ended July 26, 2026.</p>
    <p>● Production and precision agriculture net sales rose 12 percent on strong order books and improved factory efficiency across all major product lines.</p>
    <p>● Small agriculture and turf net sales increased 4 percent as retail demand stabilized and dealer inventories reached healthier levels entering the season.</p>
    <p>● Construction and forestry net sales grew 7 percent, supported by infrastructure spending and a recovering North American rental channel.</p>
    <h2>About Deere</h2>
    <p>Boilerplate company description.</p>
    </body></html>"""
    hl = extract_press_release_highlights(html)
    assert hl is not None
    assert "Deere Reports Third Quarter Net Income" in hl
    assert "$4.75 billion to $5.00 billion" in hl
    assert "Furnished herewith" not in hl
    assert "Media Inquiries" not in hl
    assert zwsp not in hl


def test_extract_risk_factors_matches_legacy_parenthesized_item_1a() -> None:
    # Halliburton style: legacy "Item 1(a)" numbering as a full heading line,
    # closed below by "Item 1(b)". The doc also carries two traps that must not
    # match: a TOC entry with "Item 1(a)." and "Risk Factors" on separate lines,
    # and a mid-sentence cross-reference ("see Part I, Item 1(a). Risk Factors").
    html = f"""
    <html><body>
      <p>Item 1(a).</p><p>Risk Factors</p><p>9</p>
      <p>Item 1. Business. We provide services worldwide.</p>
      <p>For information related to environmental matters, see Notes to Consolidated
      Financial Statements, Note 11 and Part I, Item 1(a). Risk Factors.</p>
      <p>Item 1(a). Risk Factors.</p>
      <p>{_REAL_BODY}</p>
      <p>Item 1(b). Unresolved Staff Comments.</p>
      <p>None.</p>
    </body></html>
    """
    result = extract_risk_factors(html)
    assert result is not None
    assert "prolonged economic downturn" in result
    # Bounded below by the legacy 1(b) end marker.
    assert "None." not in result
    # The TOC split-lines entry and the mid-sentence cross-reference must not
    # win longest-section-wins: no Business or cross-ref text may bleed in.
    assert "provide services worldwide" not in result
    assert "environmental matters" not in result


def test_extract_risk_factors_matches_legacy_item_1a_spaced_parens() -> None:
    # ICE style: all-caps legacy numbering, with a space inside the parens of
    # the closing marker ("ITEM 1 (B). UNRESOLVED STAFF COMMENTS").
    html = f"""
    <html><body>
      <p>ITEM 1(A). RISK FACTORS</p>
      <p>{_REAL_BODY}</p>
      <p>ITEM 1 (B). UNRESOLVED STAFF COMMENTS</p>
      <p>None.</p>
    </body></html>
    """
    result = extract_risk_factors(html)
    assert result is not None
    assert "prolonged economic downturn" in result
    assert "None." not in result


def test_extract_risk_factors_matches_runin_heading() -> None:
    # GE Aerospace style: "RISK FACTORS." directly followed by prose on the
    # same line — no standalone heading line, no "Item 1A" prefix.
    intro = "The following discussion of the material factors that may make an investment speculative or risky. "
    html = f"""
    <html><body>
      <p>RISK FACTORS. {intro}{_REAL_BODY}</p>
      <p>STRATEGIC RISKS. Strategic risk relates to business plans. {_REAL_BODY}</p>
    </body></html>
    """
    result = extract_risk_factors(html)
    assert result is not None
    # The section starts after the run-in heading, with the heading consumed.
    assert result.startswith("The following discussion")
    assert "material factors that may make an investment" in result


def test_extract_risk_factors_falls_back_to_title_case_heading() -> None:
    # Intel / Morgan Stanley style: title-case "Risk Factors" with no item
    # prefix. The TOC entry (followed by a page number) and the running page
    # headers (also followed by page numbers) must be excluded; only the real
    # heading — followed by prose — is viable.
    html = f"""
    <html><body>
      <p>Risk Factors</p><p>37</p>
      <p>MD&amp;A. Results of operations.</p>
      <p>Risk Factors</p>
      <p>{_REAL_BODY}</p>
      <p>Risk Factors</p><p>38</p>
      <p>We are in a highly competitive and rapidly changing industry. {_REAL_BODY}</p>
      <p>Item 1B. Unresolved Staff Comments</p><p>None.</p>
    </body></html>
    """
    result = extract_risk_factors(html)
    assert result is not None
    assert "prolonged economic downturn" in result
    assert "None." not in result
    # The TOC page number must not leak into the extracted section.
    assert "Results of operations" not in result


def test_extract_risk_factors_longest_caps_section_beats_running_headers() -> None:
    # Honeywell style: the real all-caps heading plus identical running page
    # headers later in the section — all followed by prose. Longest-section-wins
    # picks the real (earliest) heading, not a mid-section fragment.
    html = f"""
    <html><body>
      <p>TABLE OF CONTENTS</p>
      <p>RISK FACTORS</p>
      <p>Our business results are subject to many risks. {_REAL_BODY}</p>
      <p>30 Honeywell International Inc.</p>
      <p>TABLE OF CONTENTS</p>
      <p>RISK FACTORS</p>
      <p>Regulatory and economic changes may affect our flexibility. {_REAL_BODY}</p>
      <p>ITEM 1B. Unresolved Staff Comments</p><p>None.</p>
    </body></html>
    """
    result = extract_risk_factors(html)
    assert result is not None
    assert "Our business results are subject to many risks" in result
    assert "Regulatory and economic changes" in result
    assert "None." not in result


def test_extract_risk_factors_ignores_title_case_toc_entry() -> None:
    # A title-case "Risk Factors" TOC entry followed by a page number is not a
    # viable fallback candidate — with no real heading, the answer stays None.
    html = "<html><body><p>Risk Factors</p><p>37</p><p>Item 1. Business. We make things.</p></body></html>"
    assert extract_risk_factors(html) is None


def test_extract_risk_factors_matches_dotted_item_1a() -> None:
    # Clorox style: dotted "ITEM 1.A. RISK FACTORS" standalone heading line,
    # closed below by dotted "ITEM 1.B. UNRESOLVED STAFF COMMENTS". The dotted
    # alternative is full-line anchored like the legacy parenthesized one, so
    # a mid-sentence "see Item 1.A. Risk Factors" cross-reference cannot match
    # and steal longest-section-wins.
    html = f"""
    <html><body>
      <p>For more information on risks from cybersecurity threats, see
      &ldquo;Risk Factors&rdquo; in Item 1.A. of this Annual Report on Form 10-K.</p>
      <p>ITEM 1.A. RISK FACTORS</p>
      <p>{_REAL_BODY}</p>
      <p>ITEM 1.B. UNRESOLVED STAFF COMMENTS</p>
      <p>None.</p>
    </body></html>
    """
    result = extract_risk_factors(html)
    assert result is not None
    assert "prolonged economic downturn" in result
    # Bounded below by the dotted 1.B end marker.
    assert "None." not in result
    # The mid-sentence cross-reference must not win longest-section-wins.
    assert "cybersecurity threats" not in result


def test_extract_risk_factors_dotted_heading_requires_standalone_line() -> None:
    # The dotted form must not match when "ITEM 1.A." and "RISK FACTORS" are
    # split across TOC lines — only the standalone heading line qualifies.
    html = f"""
    <html><body>
      <p>ITEM 1.A.</p><p>RISK FACTORS</p><p>9</p>
      <p>ITEM 1.A. RISK FACTORS</p>
      <p>{_REAL_BODY}</p>
      <p>ITEM 2. PROPERTIES</p>
    </body></html>
    """
    result = extract_risk_factors(html)
    assert result is not None
    assert "prolonged economic downturn" in result


# Batch-93 press-release extraction fixtures: each body carries enough real
# release prose to clear _MIN_RELEASE_CHARS (800), like a genuine exhibit.
_BATCH93_BODY = """
    <p>ZURICH, July 21, 2026 – The company today announced financial results for the second
    quarter ended June 30, 2026, delivering another quarter of strong underwriting performance
    across its global property and casualty businesses, with disciplined expense management
    and favorable prior-period reserve development contributing to the combined ratio.</p>
    <p>"We had an excellent quarter by every measure," said the Chairman and Chief Executive
    Officer. "Our diversified global platform, superior underwriting talent, and consistent
    execution produced double-digit growth in operating income and strong premium growth
    in the quarter, positioning us well for the remainder of the year."</p>
    <p>Net premiums written increased 3.6% in the quarter, or 5.1% in constant dollars,
    reflecting rate increases, exposure growth, and strong customer retention across
    commercial and consumer lines in North America, Europe, and Asia Pacific.</p>
    """


def test_extract_pr_highlights_skips_masthead_address_block() -> None:
    # Batch-93: Chubb's ex-99 opens with a company-name masthead followed by a
    # head-office address block (street, city/postal, country, URL, handle).
    # The old code picked the street line ("Bärengasse 32") as the headline and
    # burned the 6-line lede budget on address residue, yielding None.
    html = f"""<html><body>
    <p>EX-99.1</p><p>2</p><p>d78544dex991.htm</p><p>EX-99.1</p><p>Exhibit 99.1</p>
    <p>Chubb Limited</p>
    <p>Bärengasse 32</p><p>CH-8001 Zurich</p><p>Switzerland</p>
    <p>www.chubb.com</p><p>@Chubb</p>
    <p>News Release</p>
    <p>Chubb Reports Second Quarter Per Share Net Income of $7.30 and</p>
    <p>Per Share Core Operating Income of $7.26, Up 18.2%</p>
    <p>Net income was $2.85 billion versus $2.97 billion prior year, and core operating income was $2.84 billion, up 14.6%.</p>
    {_BATCH93_BODY}
    <h2>About Chubb</h2>
    <p>Boilerplate company description.</p>
    </body></html>"""
    hl = extract_press_release_highlights(html)
    assert hl is not None
    assert hl.startswith("Chubb Reports Second Quarter")
    assert "Bärengasse 32" not in hl
    assert "CH-8001 Zurich" not in hl
    assert "Switzerland" not in hl
    assert "www.chubb.com" not in hl
    assert "$2.85 billion" in hl


def test_extract_pr_highlights_skips_prefixed_contact_block() -> None:
    # Batch-93: Synopsys' ex-99 heads contact blocks with role prefixes
    # ("INVESTOR CONTACT:", "EDITORIAL CONTACT:"). The old header regex only
    # matched bare "Contact:", and the single-line contact skip fired first on
    # the prefixed header — so "Tushar Jain" became the headline.
    html = f"""<html><body>
    <p>EX-99.1</p><p>2</p><p>d157153dex991.htm</p><p>EX-99.1</p><p>Exhibit 99.1</p>
    <p>PRESS RELEASE</p>
    <p>INVESTOR CONTACT:</p><p>Tushar Jain</p><p>Synopsys, Inc.</p>
    <p>650-584-4289</p><p>Synopsys-ir@synopsys.com</p>
    <p>EDITORIAL CONTACT:</p><p>Cara Walker</p><p>Synopsys, Inc.</p>
    <p>650-584-5000</p><p>corp-pr@synopsys.com</p>
    <p>Synopsys Posts Financial Results for Third Quarter Fiscal Year 2026</p>
    <p>Quarterly revenue of $2.477 billion, reflecting broad-based strength across the business segments.</p>
    {_BATCH93_BODY}
    <h2>About Synopsys</h2>
    <p>Boilerplate company description.</p>
    </body></html>"""
    hl = extract_press_release_highlights(html)
    assert hl is not None
    assert hl.startswith("Synopsys Posts Financial Results")
    assert "Tushar Jain" not in hl
    assert "Cara Walker" not in hl
    assert "650-584-4289" not in hl
    assert "corp-pr@synopsys.com" not in hl
    assert "$2.477 billion" in hl


def test_extract_pr_highlights_skips_spaced_letter_kicker() -> None:
    # Batch-93: Humana's ex-99 uses a spaced-letter "n e w s r e l e a s e"
    # kicker that the admin-line regex did not recognize, so it became the
    # headline.
    html = f"""<html><body>
    <p>EX-99.1</p><p>2</p><p>hum-2026q2xex99x1briefxjul.htm</p><p>EX-99.1</p>
    <p>n e w s r e l e a s e</p>
    <p>Exhibit 99.1</p>
    <p>Humana Inc.</p>
    <p>101 East Main Street</p><p>P.O. Box 1438</p><p>Louisville, KY 40202</p>
    <p>http://www.humana.com</p>
    <p>FOR MORE INFORMATION CONTACT:</p><p>Lisa Stoner</p>
    <p>Humana Investor Relations</p><p>Telephone: (502) 580-3680</p>
    <p>Humana Reports Second Quarter 2026 Financial Results;</p>
    <p>Reaffirms Full Year 2026 Adjusted EPS Guidance</p>
    <p>Second quarter 2026 GAAP earnings per share of $4.10 and adjusted earnings per share of $6.25, both ahead of expectations.</p>
    {_BATCH93_BODY}
    <h2>About Humana</h2>
    <p>Boilerplate company description.</p>
    </body></html>"""
    hl = extract_press_release_highlights(html)
    assert hl is not None
    assert hl.startswith("Humana Reports Second Quarter 2026")
    assert "n e w s r e l e a s e" not in hl
    assert "101 East Main Street" not in hl
    assert "Lisa Stoner" not in hl
    assert "$4.10" in hl


def test_extract_pr_highlights_prefixed_header_ordering() -> None:
    # The contact-block header check must run before the single-line contact
    # skip: "Investor Relations Contact:" matches both regexes, and only the
    # block skip consumes the detail lines (name/title/phone/email).
    html = f"""<html><body>
    <p>EX-99.1</p><p>Exhibit 99.1</p>
    <p>Investor Relations Contact:</p><p>Daniel E. Bachus</p>
    <p>Chief Financial Officer</p><p>Grand Canyon Education, Inc.</p>
    <p>602-639-6648</p><p>Dan.bachus@gce.com</p>
    <p>GRAND CANYON EDUCATION, INC. REPORTS SECOND QUARTER 2026 RESULTS</p>
    <p>Net revenue increased 7.2% to $258.4 million for the second quarter of 2026 compared to the second quarter of 2025.</p>
    {_BATCH93_BODY}
    <h2>About Grand Canyon Education</h2>
    <p>Boilerplate company description.</p>
    </body></html>"""
    hl = extract_press_release_highlights(html)
    assert hl is not None
    assert "GRAND CANYON EDUCATION, INC. REPORTS" in hl
    assert "Daniel E. Bachus" not in hl
    assert "Chief Financial Officer" not in hl
    assert "602-639-6648" not in hl
    assert "$258.4 million" in hl


# ── batch 94: shareholder-letter metric-table extraction ────────────────────
# Duolingo (and Affirm, Coinbase) publish quarterly results as a shareholder
# letter rather than a press release. The "Q2 Highlights" section is a metric
# table flattened by text extraction into label / value / change line triples;
# the old code terminated section collection at the first value line
# ("58.7M".isupper() is True) and the mission-statement cover starved the lede
# fallback, so every quarter yielded None. The metric-table mode renders the
# table as honest prior → current bullets.
#
# Padding body (letters run long; the extractor needs 800+ text chars).
_BATCH94_LETTER_BODY = """
<p>We believe our user growth acceleration is due to three factors: product
changes, marketing impact, and a one-time event. We continually improve the
app using a process we call The Green Machine, testing hundreds of
experiments each week to optimize retention, learning outcomes, and
monetization. The main metric we use to evaluate stickiness is the current
user retention rate, which we track across cohorts and platforms.</p>
<p>We have evolved our brand reach beyond our own social media accounts,
and the vast majority of our user growth continues to be organic. We
remain focused on building a larger and more durable business while
reinvesting in product, engineering, and content for the long term.</p>
"""
_DUOL_LETTER_HTML = f"""<html><body>
<p>EX-99.2</p><p>3</p><p>q2fy26duolingo6-30x26share.htm</p><p>EX-99.2</p>
<p>shareholder</p><p>letter</p><p>Q2 2026</p>
<p>our mission is</p><p>to develop the</p><p>best education</p>
<p>in the world</p><p>and make it universally available.</p>
<p>DUOLINGO Q2 2026 2</p>
<p>Q2 Highlights</p>
<p>User Metrics Q2 2025 Q2 2026</p>
<p>Daily Active Users 47.7M</p><p>58.7M</p><p>23% YoY</p>
<p>Paid Subscribers 10.9M</p><p>12.7M</p><p>at period end 17% YoY</p>
<p>Financial Metrics Q2 2025 Q2 2026</p>
<p>Revenue $252.3M</p><p>$298.5M</p><p>18% YoY</p>
<p>Net Cash Provided by Operating Activities</p><p>$90.7M</p><p>$88.3M</p>
<p>35.9% margin</p><p>29.6% margin</p>
<p>DUOLINGO Q2 2026 3</p>
<p>Dear shareholders,</p>
<p>Q2 was a strong quarter.</p>
{_BATCH94_LETTER_BODY}
</body></html>"""


def test_extract_pr_highlights_shareholder_letter_metric_table() -> None:
    # Batch-94: the last zero-highlight company (DUOL). The Highlights metric
    # table must render as prior → current bullets under their group headers,
    # with the letter title as headline — not the mission-statement cover.
    hl = extract_press_release_highlights(_DUOL_LETTER_HTML)
    assert hl is not None
    assert hl.startswith("Shareholder Letter Q2 2026")
    assert "User Metrics" in hl
    assert "Financial Metrics" in hl
    assert "- Daily Active Users: (47.7M → 58.7M 23% YoY)" in hl
    assert "- Paid Subscribers: (10.9M → 12.7M at period end 17% YoY)" in hl
    assert "- Revenue: ($252.3M → $298.5M 18% YoY)" in hl
    # Margin-pair change lines read as prior → current.
    assert "- Net Cash Provided by Operating Activities: ($90.7M → $88.3M 35.9% margin → 29.6% margin)" in hl
    # The batch-93 failure signature: the all-caps value line that used to
    # terminate collection must now be content, not a terminator.
    assert "58.7M" in hl
    # No cover/running-header/letter-body pollution.
    assert "our mission is" not in hl
    assert "DUOLINGO Q2 2026 3" not in hl
    assert "Dear shareholders," not in hl


def test_extract_pr_highlights_shareholder_detection_requires_title_shape() -> None:
    # "Dear shareholders" prose in a CEO quote must not trigger the letter
    # mode — detection requires the cover-title shape in the document head.
    html = f"""<html><body>
    <p>EX-99.1</p>
    <p>Acme Reports Second Quarter 2026 Results</p>
    <p>"Dear shareholders, Q2 was a strong quarter," said the CEO.</p>
    <p>Revenue grew 18% to $298.5 million compared with the prior year quarter.</p>
    <p>Daily active users rose 23% year over year to 58.7 million.</p>
    <p>Adjusted EBITDA margin was 25.9% for the second quarter of 2026.</p>
    {_BATCH93_BODY}
    </body></html>"""
    hl = extract_press_release_highlights(html)
    assert hl is not None
    assert hl.startswith("Acme Reports Second Quarter 2026 Results")
    assert "Shareholder Letter" not in hl
    assert "→" not in hl  # no metric bullets in a narrative release


def test_extract_pr_highlights_shareholder_letter_thin_table_falls_back() -> None:
    # A shareholder letter whose Highlights section is not a metric table
    # does not fabricate metric bullets — the standard press-release path
    # handles it exactly as before (narrative content, no "→" bullets).
    html = f"""<html><body>
    <p>EX-99.2</p><p>shareholder</p><p>letter</p><p>Q2 2026</p>
    <p>Q2 Highlights</p>
    <p>We had a great quarter across every measure of the business.</p>
    <p>Dear shareholders,</p>
    {_BATCH94_LETTER_BODY}
    </body></html>"""
    hl = extract_press_release_highlights(html)
    if hl is not None:
        assert "→" not in hl
        assert "Shareholder Letter" not in hl


def test_extract_pr_highlights_shareholder_letter_q4_fy_mixed_columns() -> None:
    # Batch-94: Duolingo's Q4/FY letter mixes column layouts. The cover uses
    # the slash form ("Q4 / FY 2025"); the "Financial Metrics" group header is
    # wrapped across two lines ("Financial Metrics Q4 2025" / "FY 2025"); its
    # columns are different periods (Q4 vs FY), so values must NOT read as
    # prior → current — they join with "; ". Footnote lines terminate the
    # table instead of becoming junk bullets.
    html = f"""<html><body>
    <p>EX-99.2</p><p>3</p><p>q4fy25duolingo12-31x25shar.htm</p><p>EX-99.2</p>
    <p>shareholder</p><p>letter</p><p>Q4 / FY 2025</p>
    <p>our mission is</p><p>to develop the</p><p>best education</p>
    <p>in the world</p><p>and make it universally available.</p>
    <p>DUOLINGO Q4 / FY 2025 2</p>
    <p>Q4 and FY25 Highlights</p>
    <p>User Metrics Q4 2024 Q4 2025</p>
    <p>Daily Active Users 40.5M</p><p>52.7M</p><p>30% YoY</p>
    <p>Financial Metrics Q4 2025</p><p>FY 2025</p>
    <p>Revenue $282.9M</p><p>$1,037.6M</p><p>35% YoY</p><p>39% YoY</p>
    <p>Net Income (1) $42.0M</p><p>$414.1M</p>
    <p>(1) During the year ended December 31, 2025, the Company released the valuation allowance previously recorded against deferred tax assets.</p>
    <p>DUOLINGO Q4 / FY 2025 3</p>
    <p>Dear shareholders,</p>
    {_BATCH94_LETTER_BODY}
    </body></html>"""
    hl = extract_press_release_highlights(html)
    assert hl is not None
    # Slash-form cover quarter, not the table's prior-year column.
    assert hl.startswith("Shareholder Letter Q4 2025")
    # YoY group keeps the prior → current reading.
    assert "- Daily Active Users: (40.5M → 52.7M 30% YoY)" in hl
    # Wrapped group header joined; cross-period columns joined with "; ".
    assert "Financial Metrics" in hl
    assert "- Revenue: ($282.9M; $1,037.6M 35% YoY; 39% YoY)" in hl
    assert "- Net Income (1): ($42.0M; $414.1M)" in hl
    # Footnote and running header never become content.
    assert "(1) During the year" not in hl
    assert "DUOLINGO Q4 / FY 2025 3" not in hl
    assert "Dear shareholders," not in hl


# ── Batch 97: partial-highlight residual forensics ────────────────────────────

def _nee_style_html() -> str:
    # NextEra: the exhibit header renders bare "EX-99" (no ".1"). Without the
    # batch-97 admin fix, "EX-99" became the headline and extraction failed.
    return """<html><body>
<p>EX-99</p><p>2</p><p>neeq12026exhibit99.htm</p><p>EX-99</p>
<p>Exhibit 99</p>
<p>NextEra Energy, Inc.</p>
<p>Media Line: 561-694-4442</p>
<p>April 23, 2026</p>
<p>FOR IMMEDIATE RELEASE</p>
<h1>NextEra Energy reports first-quarter 2026 financial results</h1>
<p>&#8226; NextEra Energy delivers strong first-quarter results.</p>
<p>&#8226; FPL grows regulatory capital employed by approximately 8.8 percent.</p>
<p>JUNO BEACH, Fla. - NextEra Energy, Inc. (NYSE: NEE) today reported 2026
first-quarter net income attributable to NextEra Energy of 1.8 billion dollars,
up 10 percent year over year, driven by continued growth at FPL and record
origination at NextEra Energy Resources. Adjusted earnings were 2.1 billion dollars,
up 12 percent, reflecting strong operational performance across both segments and
continued customer growth in Florida. The company also announced a quarterly dividend
increase and reaffirmed its long-term growth expectations through 2028.</p>
</body></html>"""


def test_bare_ex99_header_is_admin():
    result = extract_press_release_highlights(_nee_style_html())
    assert result is not None
    assert result.startswith("NextEra Energy reports first-quarter 2026")
    assert "EX-99" not in result.split("\n")[0]


def test_page_x_of_y_header_is_admin():
    html = """<html><body>
<p>EX-99.1</p><p>Page 1 of 24</p><p>Exhibit 99.1</p>
<h1>MetLife Announces 3Q 2025 Results</h1>
<p>&#8226; Net income was 818 million dollars, or 1.22 per share.</p>
<p>&#8226; Adjusted earnings increased 15 percent to 1.6 billion dollars.</p>
<p>NEW YORK - MetLife, Inc. today announced third quarter 2025 results with
net income of 818 million dollars and adjusted earnings of 1.6 billion dollars,
reflecting higher variable investment income and volume growth. Book value per share
was 39.52 dollars, up 1 percent, while adjusted book value per share increased 3 percent
to 56.57 dollars. The company returned approximately 875 million dollars to shareholders
via share repurchases and common stock dividends during the quarter. Total assets under
management grew to 852 billion dollars, and the company maintained a strong risk-based
capital ratio well above regulatory requirements.</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert result.startswith("MetLife Announces 3Q 2025 Results")


def test_release_date_line_is_admin():
    # Lilly puts "August 7, 2025" before the headline — it must not become it.
    html = """<html><body>
<p>EX-99.1</p><p>2</p><p>q225lillysalesandearningsp.htm</p><p>EX-99.1</p>
<p>August 7, 2025</p>
<p>For release: Immediately</p>
<h1>Lilly reports second-quarter 2025 financial results and raises guidance</h1>
<p>&#8226; Revenue in Q2 2025 increased 38 percent to 15.56 billion dollars.</p>
<p>&#8226; EPS increased 92 percent to 6.29 on a reported basis.</p>
<p>INDIANAPOLIS, August 7, 2025 - Eli Lilly and Company today announced its
financial results for the second quarter of 2025, with revenue growth driven
by volume from Zepbound and Mounjaro. The company also completed strategic acquisitions
to strengthen its pipeline in cardiometabolic health and genetic medicines, positioning
for sustained growth into 2026 and beyond with a robust late-stage pipeline. Research
and development expenses were 3.1 billion dollars, up 8 percent, reflecting continued
investment in the company's priority therapeutic areas.</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert result.startswith("Lilly reports second-quarter 2025")
    assert "August 7, 2025" not in result.split("\n")[0]


def test_table_shaped_highlights_section_rejected():
    # Lilly's "Selected Revenue Highlights" is a product-revenue table, not
    # narrative bullets — it must not hijack the section; the lede serves.
    html = """<html><body>
<p>EX-99.1</p>
<h1>Lilly reports second-quarter 2025 financial results</h1>
<p>&#8226; Revenue in Q2 2025 increased 38 percent to 15.56 billion dollars
driven by volume growth from Zepbound and Mounjaro.</p>
<p>&#8226; EPS increased 92 percent to 6.29 on a reported basis and 61 percent
to 6.31 on a non-GAAP basis.</p>
<p>INDIANAPOLIS - Eli Lilly and Company today announced financial results for
the second quarter of 2025, delivering strong performance across the
portfolio with continued momentum in obesity and diabetes medicines. The quarter also
saw the initiation of three new Phase 3 programs and positive readouts across the
oncology portfolio, supporting the company's raised full-year outlook.</p>
<h2>Selected Revenue Highlights</h2>
<p>(Dollars in millions)</p>
<p>Second-Quarter</p><p>Year-to-Date</p>
<p>Selected Products 2025 2024 % Change 2025 2024 % Change</p>
<p>Mounjaro $ 5,198.9 $ 3,090.8 68% $ 9,040.7 $ 4,897.4 85%</p>
<p>Zepbound $ 3,383.8 $ 1,243.6 172% $ 6,523.8 $ 2,100.4 211%</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "Lilly reports second-quarter 2025" in result
    assert "Mounjaro $ 5,198.9" not in result
    assert "Revenue in Q2 2025 increased 38 percent" in result


def test_footnote_verb_highlight_not_a_heading():
    # WM footnote prose "...prepared to highlight and facilitate..." contains
    # the verb "highlight" — it is not a section heading.
    html = """<html><body>
<p>EX-99.1</p>
<h1>WM Announces Fourth Quarter and Full-Year 2025 Earnings</h1>
<p>Focus on operational excellence drives the company's best-ever operating
expenses as a percentage of revenue for the fourth quarter and full year,
with robust operational performance and strong growth expected to continue.</p>
<p>Houston - WM today announced financial results for the fourth quarter and
full year 2025, reporting revenue growth and margin expansion across the
solid waste network and sustainability investments.</p>
<h2>HIGHLIGHTS FOR the fourth quarter and FULL YEAR 2025</h2>
<p>($ in millions)</p>
<p>Operating EBITDA</p>
<p>$ 1,925</p>
<p>(a) The summary of free cash flow has been prepared to highlight and
facilitate understanding of the principal cash flow elements.</p>
<p>Free cash flow is not a measure of financial performance under generally
accepted accounting principles and is not intended to replace the
consolidated statement of cash flows.</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "WM Announces Fourth Quarter" in result
    assert "prepared to highlight and facilitate" not in result


def test_lede_drops_table_fragment_runs():
    # MetLife's metric table sits between the headline and the bullets — the
    # fragment run must not fill the lede budget.
    html = """<html><body>
<p>EX-99.1</p><p>Page 1 of 24</p><p>Exhibit 99.1</p>
<h1>MetLife Announces 3Q 2025 Results</h1>
<p>Earnings</p><p>Per Share</p><p>3Q 2025</p><p>Net</p>
<p>Income $1.22</p><p>Adjusted</p><p>Earnings $2.37</p>
<p>Return</p><p>on Equity (ROE)</p><p>3Q 2025</p><p>ROE 13.1%</p>
<p>&#8226; Net income was 818 million dollars, or 1.22 per share, reflecting
strong underwriting results across the business segments.</p>
<p>&#8226; Adjusted earnings increased 15 percent to 1.6 billion dollars,
primarily driven by higher variable investment income and volume growth.</p>
<p>&#8226; Premiums, fees and other revenues were 12.5 billion dollars, with
growth in all segments except MetLife Holdings. Net investment income rose 16 percent
to 6.1 billion dollars on higher private equity returns, and the company expanded its
MetLife Xcelerator partnership in Latin America during the quarter. The board declared a quarterly dividend
of 0.63 per share, payable in the fourth quarter, consistent with the company's
long-standing commitment to returning capital to shareholders.</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert result.startswith("MetLife Announces 3Q 2025 Results")
    assert "Net income was 818 million dollars" in result
    # Table fragments must not consume the lede.
    assert "Income $1.22" not in result


# ── Cover title-block skip (batch 100) ──────────────────────────────────────
# Goldman Sachs opens its ex-99.1 with a cover page (quarter-period title +
# "Earnings Results", inline media/investor contacts, masthead + address,
# repeated banner) before the real headline. The naive pick took the cover
# title and filled the lede with contact/masthead lines.


def _gs_cover_html(
    *,
    period_lines=("Second Quarter 2026",),
    banner="SECOND QUARTER 2026 EARNINGS RESULTS",
    headline_lines=(
        "Goldman Sachs Reports Second Quarter Earnings Per Common",
        "Share of $20.98 and Increases the Quarterly Dividend to $5.00",
        "Per Common Share in the Third Quarter",
    ),
) -> str:
    cover = "".join(f"<p>{ln}</p>" for ln in period_lines)
    cover += "<p>Earnings Results</p>"
    cover += "<p>Media Relations: Tony Fratto 212-902-5400</p>"
    cover += "<p>Investor Relations: Jehan Ilahi 212-902-0300</p>"
    cover += "<p>The Goldman Sachs Group, Inc.</p>"
    cover += "<p>200 West Street | New York, NY 10282</p>"
    cover += f"<p>{banner}</p>"
    headline = "".join(f"<p>{ln}</p>" for ln in headline_lines)
    table = (
        "<p>Financial Summary</p><p>Net Revenues</p><p>2Q26</p>"
        "<p>$20.34 billion</p><p>Net Earnings</p><p>2Q26</p>"
        "<p>$6.63 billion</p><p>Book Value Per Share</p><p>2Q26</p><p>$367.67</p>"
    )
    lede = (
        "<p>NEW YORK, July 14, 2026 \u2013 The Goldman Sachs Group, Inc. (NYSE: GS) "
        "today reported net revenues of $20.34 billion and net earnings of $6.63 "
        "billion for the second quarter ended June 30, 2026. Net revenues were "
        "$37.57 billion and net earnings were $12.26 billion for the first half "
        "of 2026, reflecting strong performance across the franchise.</p>"
    )
    return (
        "<html><body><p>EX-99.1</p><p>2</p><p>a2q26gsearningsresults.htm</p>"
        "<p>EX-99.1</p><p>Exhibit 99.1</p>"
        f"{cover}{headline}{table}{lede}</body></html>"
    )


def test_cover_block_skip_picks_real_headline() -> None:
    result = extract_press_release_highlights(_gs_cover_html())
    assert result is not None
    assert result.startswith(
        "Goldman Sachs Reports Second Quarter Earnings Per Common Share of "
        "$20.98 and Increases the Quarterly Dividend to $5.00 "
        "Per Common Share in the Third Quarter"
    )
    # Cover residue must not leak into the headline or lede.
    assert "Tony Fratto" not in result
    assert "200 West Street" not in result
    assert "SECOND QUARTER 2026 EARNINGS RESULTS" not in result
    # The real narrative lede survives the metric table.
    assert "NEW YORK, July 14, 2026" in result
    assert "net revenues of $20.34 billion" in result


def test_cover_block_wrapped_period_title_and_title_case_banner() -> None:
    # Q4 shape: "Full Year and" / "Fourth Quarter 2025" cover title and a
    # title-case (not all-caps) banner repeat.
    result = extract_press_release_highlights(
        _gs_cover_html(
            period_lines=("Full Year and", "Fourth Quarter 2025"),
            banner="Full Year and Fourth Quarter 2025 Earnings Results",
            headline_lines=(
                "Goldman Sachs Reports Earnings Per Common Share of $51.32 for 2025 and",
                "Increases the Quarterly Dividend to $4.50 Per Common Share",
            ),
        )
    )
    assert result is not None
    assert result.startswith(
        "Goldman Sachs Reports Earnings Per Common Share of $51.32 for 2025 and "
        "Increases the Quarterly Dividend to $4.50 Per Common Share"
    )
    assert "Tony Fratto" not in result


def test_cover_block_three_line_period_title() -> None:
    # Older Donnelley vintage: "Full Year" / "and" / "Fourth Quarter 2024".
    result = extract_press_release_highlights(
        _gs_cover_html(
            period_lines=("Full Year", "and", "Fourth Quarter 2024"),
            banner="Full Year and Fourth Quarter 2024 Earnings Results",
            headline_lines=(
                "Goldman Sachs Reports Earnings Per Common Share of $40.54 for 2024",
            ),
        )
    )
    assert result is not None
    assert result.startswith(
        "Goldman Sachs Reports Earnings Per Common Share of $40.54 for 2024"
    )
    assert "Full Year" not in result.split("\n\n")[0]
    assert "Tony Fratto" not in result


def test_cover_block_quarter_then_bare_year_title() -> None:
    # Older Donnelley vintage: "Third Quarter" / "2024".
    result = extract_press_release_highlights(
        _gs_cover_html(
            period_lines=("Third Quarter", "2024"),
            banner="Third Quarter 2024 Earnings Results",
            headline_lines=(
                "Goldman Sachs Reports Third Quarter Earnings Per Common Share of $8.40",
            ),
        )
    )
    assert result is not None
    assert result.startswith(
        "Goldman Sachs Reports Third Quarter Earnings Per Common Share of $8.40"
    )
    assert "Tony Fratto" not in result


def test_cover_block_section_heading_stops_headline_join() -> None:
    # Q1 shape: single-line headline directly above the metric table — the
    # "Financial Summary" heading must not be swallowed into the headline.
    result = extract_press_release_highlights(
        _gs_cover_html(
            period_lines=("First Quarter 2026",),
            banner="First Quarter 2026 Earnings Results",
            headline_lines=(
                "Goldman Sachs Reports First Quarter Earnings Per Common Share of $17.55",
            ),
        )
    )
    assert result is not None
    assert result.startswith(
        "Goldman Sachs Reports First Quarter Earnings Per Common Share of $17.55"
    )
    assert "Financial Summary" not in result.split("\n\n")[0]


def test_cover_block_no_fire_without_kind_line() -> None:
    # Period title not followed by "Earnings Results" — standard path keeps
    # the old behavior (cover title picked as headline).
    html = _gs_cover_html().replace("<p>Earnings Results</p>", "<p>At a Glance</p>")
    result = extract_press_release_highlights(html)
    assert result is not None
    assert result.startswith("Second Quarter 2026")


def test_cover_block_no_fire_without_contact_phone() -> None:
    # Contact lines without phone numbers — the cover shape is not confirmed.
    html = _gs_cover_html().replace("212-902-5400", "").replace("212-902-0300", "")
    result = extract_press_release_highlights(html)
    assert result is not None
    assert result.startswith("Second Quarter 2026")


def test_cover_block_no_fire_without_banner() -> None:
    html = _gs_cover_html().replace(
        "<p>SECOND QUARTER 2026 EARNINGS RESULTS</p>", ""
    )
    result = extract_press_release_highlights(html)
    assert result is not None
    assert result.startswith("Second Quarter 2026")


def test_table_heading_folds_into_fragment_run() -> None:
    # A short table heading above 2+ fragment rows drops with the run...
    lede = (
        "CUPERTINO, California \u2014 Acme Corp today announced financial results for its "
        "fiscal 2025 fourth quarter ended December 31, 2025. The Company posted quarterly "
        "revenue of 50.2 billion dollars, up 8 percent year over year, with strong "
        "performance across every segment of the business. Diluted earnings per share "
        "were 2.10 dollars, up 12 percent year over year, reflecting operating leverage "
        "and a favorable product mix. The board declared a quarterly dividend of 0.25 "
        "dollars per share, payable in the first quarter, consistent with the company's "
        "long-standing commitment to returning capital to shareholders. Gross margin was "
        "44 percent, reflecting a strong product mix and continued services growth. "
        "Operating cash flow reached a quarterly record, supporting ongoing investment "
        "in the business."
    )
    html = f"""<html><body>
<p>EX-99.1</p><p>Exhibit 99.1</p>
<h1>Acme Corp Reports Fourth Quarter 2025 Results</h1>
<p>Financial Summary</p><p>Net Revenues</p><p>4Q25</p><p>$50.2 billion</p>
<p>Book Value Per Share</p><p>4Q25</p><p>$100.00</p>
<p>{lede}</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "Book Value Per Share" not in result
    assert "$100.00" not in result
    assert "CUPERTINO, California" in result
    # ...while a short 2-fragment run with no heading is still kept.
    html2 = f"""<html><body>
<p>EX-99.1</p><p>Exhibit 99.1</p>
<h1>Acme Corp Reports Fourth Quarter 2025 Results</h1>
<p>4Q25</p><p>$50.2 billion</p>
<p>{lede}</p>
</body></html>"""
    result2 = extract_press_release_highlights(html2)
    assert result2 is not None
    assert "$50.2 billion" in result2


# ── Batch 101: separator-less endnote markers are footnotes, not lede ─────────
# EOG's ex-99.1 is a pure supplemental-financial packet (TOC + tables +
# endnotes, no narrative). Its endnotes are lettered "(B)Production volumes
# ..." with the marker running straight into the text — the old
# _LEDE_FOOTNOTE_RE required [\s.] after the marker, so the endnote
# boilerplate filled the 6-line lede budget and got STORED as the quarter's
# highlights (EOG Q1 FY2026: 976 chars of footnote definitions). A
# supplement-only packet must honestly yield None.


def test_lede_footnote_re_matches_separator_less_markers():
    from tickerlens.data.filings import _LEDE_FOOTNOTE_RE

    assert _LEDE_FOOTNOTE_RE.match("(B)Production volumes from Bahrain operations")
    assert _LEDE_FOOTNOTE_RE.match("(a) Represents the principal cash flow elements")
    assert _LEDE_FOOTNOTE_RE.match("(1) During the year ended December 31")
    assert _LEDE_FOOTNOTE_RE.match("(A)Effective January 1, 2026, EOG combined")
    # Parenthetical asides are not footnote markers.
    assert not _LEDE_FOOTNOTE_RE.match("(in millions)")
    assert not _LEDE_FOOTNOTE_RE.match("Revenue (in millions) was up")
    assert not _LEDE_FOOTNOTE_RE.match("Net income rose 5 percent")


def test_supplement_packet_endnotes_not_stored_as_highlights():
    # EOG shape: TOC, then tables, then lettered endnotes with no narrative.
    html = """<html><body>
<p>EX-99.1</p><p>2</p><p>exh99-1080426.htm</p>
<p>PRESS RELEASE OF EOG RESOURCES, INC.</p><p>EXHIBIT 99.1</p>
<p>Table of Contents</p>
<p>Second Quarter 2026</p>
<p>Supplemental Financial and Operating Data</p>
<p>Income Statements 10</p><p>Volumes and Prices 11</p><p>Balance Sheets 12</p>
<p>9</p><p>Income Statements</p>
<p>In millions of USD, except share data (in millions) and per share data (Unaudited)</p>
<p>Crude Oil and Condensate 3,293 2,974 3,243 2,991</p>
<p>Natural Gas Liquids 572 534 604 666</p>
<p>Net Income 1,463 1,345 1,471 701</p>
<p>10</p><p>Volumes and Prices</p>
<p>(Unaudited)</p>
<p>Crude Oil and Condensate Volumes (MBbld) (A)</p>
<p>United States 500.9 503.1 532.9 544.5</p>
<p>Endnotes</p>
<p>(B)Production volumes from Bahrain operations; natural gas realized price represents contract price less partner's processing and distribution costs.</p>
<p>(C)Dollars per barrel or per thousand cubic feet, as applicable. Excludes the impact of financial commodity and other derivative instruments.</p>
<p>(D)Thousand barrels of oil equivalent per day or million barrels of oil equivalent, as applicable; includes crude oil and condensate, NGLs and natural gas.</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is None
    assert "Bahrain operations" not in (result or "")


# ── Batch 102: financial bullets beat business "Highlights" section ─────────
_PAD_PARAGRAPH = ("Acme Corp is a leading global provider of widgets and enterprise "
    "solutions serving customers in more than forty countries worldwide with "
    "innovative products, reliable service, and a steadfast commitment to quality. ")

# Halliburton's Q2 2026 earnings release opens with financial bullets right
# after the headline ("Net income of $0.64 per diluted share ...") and only
# much later carries a "Selective Technology & Highlights" section of
# business-PR bullets (product launches, partnerships). The extractor used
# to return the first "Highlights" heading match, so the financial figures
# were buried for a financials app. Candidate sections (the leading bullet
# block plus every "Highlights" section) now compete on financial density;
# ties break to the earliest candidate (the pre-batch-102 behavior).

_HAL_FINANCIAL_BULLETS = """
<p>HALLIBURTON ANNOUNCES SECOND QUARTER 2026 RESULTS</p>
<p>\u2022Net income of $0.64 per diluted share.</p>
<p>\u2022Adjusted net income per diluted share of $0.55.</p>
<p>\u2022Revenue of $5.7 billion and operating margin of 14%.</p>
<p>\u2022Cash flow from operations of $824 million and free cash flow of $668 million.</p>
<p>HOUSTON \u2013 July 21, 2026 \u2013 Halliburton Company (NYSE: HAL) announced today net
income of $534 million, or $0.64 per diluted share, for the second quarter of 2026.</p>
"""


def test_financial_leading_bullets_beat_later_business_highlights():
    html = f"""<html><body>
<p>EX-99.1</p><p>2</p><p>livemastererdocument.htm</p><p>EX-99.1</p>
<p>Exhibit 99.1</p>
{_HAL_FINANCIAL_BULLETS}
<p>Selective Technology &amp; Highlights</p>
<p>\u2022Halliburton and Shape Digital entered a strategic collaboration to advance digital
asset performance management through a unified asset view.</p>
<p>\u2022Halliburton launched the Xaminer Deep Testing logging service, the newest addition
to its wireline portfolio.</p>
<p>About Halliburton</p>
<p>Halliburton is one of the world's largest providers of products and services to the
energy industry.</p>
<p>Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. </p></body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "Net income of $0.64 per diluted share" in result
    assert "Revenue of $5.7 billion" in result
    # The business-PR bullets must not displace the financial figures.
    assert "Shape Digital" not in result
    assert "Xaminer" not in result


def test_business_only_highlights_section_kept_when_nothing_financial():
    # No leading bullets and a narrative-only "Highlights" section: the
    # pre-batch-102 behavior (return it) is preserved.
    html = """<html><body>
<p>ACME CORP ANNOUNCES FOURTH QUARTER 2025 RESULTS</p>
<p>CUPERTINO, California \u2013 Acme Corp today announced results for its fourth quarter.</p>
<p>Financial Highlights</p>
<p>\u2022Acme completed the strategic acquisition of Widgets GmbH, expanding its
European footprint.</p>
<p>\u2022The board approved a new research campus in Austin, Texas.</p>
<p>\u2022Acme was named a top employer by a national survey.</p>
<p>About Acme Corp</p>
<p>Acme Corp makes widgets.</p>
<p>Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. </p></body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "Widgets GmbH" in result


def test_later_financial_section_beats_earlier_business_section():
    # Two "Highlights" sections: the earlier one is business narrative, the
    # later one carries figures — the financial one wins.
    html = """<html><body>
<p>ACME CORP ANNOUNCES FOURTH QUARTER 2025 RESULTS</p>
<p>CUPERTINO, California \u2013 Acme Corp today announced results for its fourth quarter.</p>
<p>Business Highlights</p>
<p>\u2022Acme completed the strategic acquisition of Widgets GmbH, expanding its
European footprint.</p>
<p>\u2022The board approved a new research campus in Austin, Texas.</p>
<p>\u2022Acme was named a top employer by a national survey.</p>
<p>\u2022New widget line shipped to fifty enterprise customers this quarter.</p>
<p>FINANCIAL HIGHLIGHTS</p>
<p>\u2022Revenue of $50.2 billion, up 8 percent year over year.</p>
<p>\u2022Diluted earnings per share of $2.10, up 12 percent.</p>
<p>\u2022Gross margin of 44 percent.</p>
<p>\u2022Returned $24 billion to shareholders via dividends and repurchases.</p>
<p>About Acme Corp</p>
<p>Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. </p></body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "Revenue of $50.2 billion" in result
    assert "Widgets GmbH" not in result


def test_leading_block_without_highlights_heading_serves_as_section():
    # A release with leading financial bullets and NO highlights heading:
    # the bullets are the highlights (previously the 6-line lede, now the
    # full block — same content family).
    html = f"""<html><body>
<p>EX-99.1</p>
{_HAL_FINANCIAL_BULLETS}
<p>About Halliburton</p>
<p>Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. </p></body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "Revenue of $5.7 billion" in result
    assert "free cash flow of $668 million" in result


def test_financial_density_threshold_rejects_mixed_prose_section():
    # A highlights section with only one $-line among prose is narrative,
    # not financial: earliest candidate (the section) still wins — no
    # reordering on a thin signal.
    html = """<html><body>
<p>ACME CORP ANNOUNCES FOURTH QUARTER 2025 RESULTS</p>
<p>CUPERTINO, California \u2013 Acme Corp today announced results for its fourth quarter.</p>
<p>Highlights</p>
<p>\u2022Acme completed the strategic acquisition of Widgets GmbH, expanding its
European footprint.</p>
<p>\u2022The board approved a new research campus in Austin, Texas, a $500 million
investment over five years.</p>
<p>\u2022Acme was named a top employer by a national survey.</p>
<p>\u2022New widget line shipped to fifty enterprise customers this quarter.</p>
<p>\u2022Chief executive Jane Doe commented on a strong quarter of execution.</p>
<p>\u2022The company expects continued momentum into next year.</p>
<p>About Acme Corp</p>
<p>Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. Acme Corp pad. </p></body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "Widgets GmbH" in result


def test_wrapped_financial_bullets_still_win_over_business_section():
    # HAL Q2 2025 shape: a financial bullet wraps across two lines
    # ("... free cash flow1 of / approximately $582 million."). The wrapped
    # continuation must not end the leading block, and the later business
    # "Selective Technology & Highlights" section must not displace it.
    html = """<html><body>
<p>EX-99.1</p><p>2</p><p>livemastererdocument.htm</p><p>EX-99.1</p>
<p>Exhibit 99.1</p>
<p>HALLIBURTON ANNOUNCES SECOND QUARTER 2025 RESULTS</p>
<p>\u2022Net income of $0.55 per diluted share.</p>
<p>\u2022Cash flow from operations of $896 million and free cash flow1 of</p>
<p>approximately $582 million.</p>
<p>\u2022Revenue of $5.5 billion and operating margin of 13%.</p>
<p>\u2022Approximately $250 million of share repurchases.</p>
<p>HOUSTON \u2013 July 22, 2025 \u2013 Halliburton Company (NYSE: HAL) announced today net
income of $472 million, or $0.55 per diluted share, for the second quarter of 2025.</p>
<p>This compares to net income for the first quarter of 2025 of $204 million, or $0.24 per
diluted share.</p>
<p>Selective Technology &amp; Highlights</p>
<p>\u2022Halliburton jointly developed a new process with Chevron U.S.A. Inc., enabling
closed-loop, feedback-driven completions in Colorado.</p>
<p>\u2022Halliburton and Nabors Industries achieved the first fully automated surface and
subsurface execution of rotary and slide drilling operations in Oman.</p>
<p>About Halliburton</p>
<p>Halliburton is one of the world's largest providers of products and services to the
energy industry, serving customers in more than eighty countries with innovative
technologies and dependable execution across the full well lifecycle.</p>
<p>""" + ("Halliburton pad. " * 60) + """</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "Net income of $0.55 per diluted share" in result
    assert "Revenue of $5.5 billion" in result
    assert "approximately $582 million" in result
    assert "Chevron" not in result


# ── Batch 104: footnote-definition legend lines are never the headline ────────
# GEV's Workiva ex-99 opens with a footnote legend block
# ("1 Defined as remaining performance obligation (RPO)" /
# "*Non-GAAP Financial Measure" / "Page 1") before the real headline, and the
# numeric definition line was picked as the headline. Southern Company's
# exhibit showed the follow-on shape: skipping bare "Page 1" exposed the lone
# "News" kicker as the would-be headline.

_GEV_LEGEND_HTML = """<html><body>
<p>EX-99</p><p>2</p><p>gevpressrelease2q25.htm</p><p>EX-99</p>
<p>1 Defined as remaining performance obligation (RPO)</p>
<p>*Non-GAAP Financial Measure</p>
<p>Page 1</p>
<p>GE Vernova reports second quarter 2025 financial results</p>
<p>Strong 2Q'25 results with continued growth, margin expansion and positive cash flow; raising 2025 guidance</p>
<p>Second Quarter 2025 Highlights:</p>
<p>\u2022Orders of $12.4B, +4% organically; continued strong demand at Power and Electrification</p>
<p>\u2022Backlog1 growth of $5.2B sequentially from equipment and services</p>
<p>\u2022Revenue of $9.1B, +11%, +12% organically* with growth in both equipment and services</p>
<p>\u2022Net income of $0.5B; net income margin of 5.4%</p>
<p>About GE Vernova</p>
<p>""" + "GE Vernova pad. " * 60 + """</p>
</body></html>"""

_SO_KICKER_HTML = """<html><body>
<p>EX-99</p><p>2</p><p>ex99-pressreleaseq22024.htm</p><p>EX-99</p><p>Exhibit 99</p>
<p>Page 1</p>
<p>News</p>
<p>Media Contact: Southern Company Media Relations</p>
<p>404-506-5333 or 1-866-506-5333</p>
<p>southerncompany.com</p>
<p>Investor Relations Contact:</p>
<p>Scott Gammill</p>
<p>404-506-0901</p>
<p>sagammil@southernco.com</p>
<p>August 1, 2024</p>
<p>Southern Company reports second-quarter 2024 earnings</p>
<p>ATLANTA \u2013 Southern Company today reported second-quarter earnings of $1.2 billion, or $1.10 per share, compared with $838 million, or $0.79 per share, in the second quarter of 2023.</p>
<p>Excluding the items described below, Southern Company earned $1.1 billion, or $1.03 per share, during the second quarter of 2024, compared with $990 million, or $0.93 per share, during the second quarter of 2023.</p>
<p>About Southern Company</p>
<p>""" + "Southern Company pad. " * 60 + """</p>
</body></html>"""


def test_footnote_def_re_matches_legend_shapes():
    from tickerlens.data.filings import _FOOTNOTE_DEF_RE

    assert _FOOTNOTE_DEF_RE.match("1 Defined as remaining performance obligation (RPO)")
    assert _FOOTNOTE_DEF_RE.match("2 Represents the principal cash flow elements")
    assert _FOOTNOTE_DEF_RE.match("1 Includes restructuring charges")
    assert _FOOTNOTE_DEF_RE.match("*Non-GAAP Financial Measure")
    assert _FOOTNOTE_DEF_RE.match("\u2020Excludes one-time items")


def test_footnote_def_re_rejects_real_headline_shapes():
    from tickerlens.data.filings import _FOOTNOTE_DEF_RE

    # 4-digit years, "1Q"-style quarter opens, and numeric-opening prose are
    # all plausible headlines — none carries a definition verb, so none may
    # be swallowed.
    assert not _FOOTNOTE_DEF_RE.match("2025 outlook raised on strong demand")
    assert not _FOOTNOTE_DEF_RE.match("1Q26 record quarter for widgets")
    assert not _FOOTNOTE_DEF_RE.match("1 billion in buybacks announced")
    assert not _FOOTNOTE_DEF_RE.match("News")
    # A spaced asterisk is prose punctuation, not a legend marker.
    assert not _FOOTNOTE_DEF_RE.match("* Non-GAAP Financial Measure")


def test_gev_legend_lines_never_become_headline():
    # GEV Q2 FY2025 shape: footnote-definition legend block precedes the
    # headline. The real headline must lead; no legend line may appear.
    result = extract_press_release_highlights(_GEV_LEGEND_HTML)
    assert result is not None
    headline = result.split("\n")[0]
    assert headline == "GE Vernova reports second quarter 2025 financial results"
    assert "Defined as remaining performance obligation" not in result
    assert "*Non-GAAP Financial Measure" not in result
    assert "Page 1" not in result
    assert "Orders of $12.4B" in result


def test_lone_news_kicker_and_bare_page_never_become_headline():
    # SO Q2 FY2024 shape: bare "Page 1" then a lone "News" kicker, then a
    # contact block and the date, then the real headline. Skipping "Page 1"
    # must not promote the kicker — the real headline must win.
    result = extract_press_release_highlights(_SO_KICKER_HTML)
    assert result is not None
    headline = result.split("\n")[0]
    assert headline == "Southern Company reports second-quarter 2024 earnings"
    assert headline != "News"
    assert "Page 1" not in result.split("\n\n")[0]


def test_news_corp_headline_not_swallowed_by_news_kicker_rule():
    # The lone-"News" admin rule must not eat a headline that merely starts
    # with the word News.
    html = """<html><body>
<p>EX-99.1</p>
<p>NEWS CORP ANNOUNCES SECOND QUARTER 2025 RESULTS</p>
<p>New York \u2013 News Corp today reported revenue of $2.1 billion, up 5% compared to the prior year, driven by growth in the Digital Real Estate Services and Book Publishing segments.</p>
<p>Net income for the quarter was $312 million, or $0.54 per diluted share, reflecting higher operating leverage and continued cost discipline across the portfolio.</p>
<p>About News Corp</p>
<p>""" + "News Corp pad. " * 60 + """</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert result.split("\n")[0] == "NEWS CORP ANNOUNCES SECOND QUARTER 2025 RESULTS"


def test_lede_pass_skips_footnote_def_lines():
    # Footnote-definition legends appearing after the headline (no Highlights
    # section, so the lede fallback runs) are skipped, not stored.
    html = """<html><body>
<p>EX-99.1</p>
<p>ACME CORP REPORTS THIRD QUARTER 2025 RESULTS</p>
<p>1 Defined as remaining performance obligation</p>
<p>*Non-GAAP Financial Measure</p>
<p>CUPERTINO, California \u2013 Acme Corp today announced revenue of $4.2 billion for the third quarter, up 9% year over year, with growth across all major product categories and geographies.</p>
<p>Net income was $812 million, or $1.04 per diluted share, compared with net income of $701 million, or $0.91 per diluted share, in the prior-year quarter.</p>
<p>About Acme Corp</p>
<p>""" + "Acme Corp pad. " * 60 + """</p>
</body></html>"""
    result = extract_press_release_highlights(html)
    assert result is not None
    assert result.split("\n")[0] == "ACME CORP REPORTS THIRD QUARTER 2025 RESULTS"
    assert "Defined as remaining performance obligation" not in result
    assert "*Non-GAAP Financial Measure" not in result
    assert "revenue of $4.2 billion" in result


# ── Batch 105: contact-block residue must not become the headline ─────────────
# Fresh-ticker seeding (PGR, NKE, NFLX, CRM) surfaced a defect family the
# earlier contact-block fixes missed: the headline pass stopped at a contact
# header it didn't recognize, or _skip_contact_block broke early on a
# multi-name detail line, so "The Progressive Corporation Company Contact:" /
# "Paul Trussell Sandra Carreon-John" became the stored headline. A DB-wide
# blast-radius scan found the same residue on ~50 quarters across 10 tickers
# (HSY, CSCO, AAL, HLT, HCA-stale, AON, LUV), all repaired by re-extraction.

_FILLER_105 = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor "
    "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis "
    "nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. "
    "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu "
    "fugiat nulla pariatur. "
)


def _contact_release_html(*lines: str) -> str:
    body = "".join(f"<p>{ln}</p>" for ln in lines)
    return f"<html><body>{body}<p>{_FILLER_105 * 4}</p><h2>About Acme</h2><p>Boilerplate.</p></body></html>"


def test_contact_header_company_prefixed_is_skipped() -> None:
    # Progressive: "The Progressive Corporation Company Contact:" — a company-
    # name-prefixed contact header the old regex didn't recognize, so it
    # became the headline.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99", "NEWS RELEASE",
            "The Progressive Corporation Company Contact:",
            "300 North Commons Blvd. Julianna Paterra",
            "Mayfield Village, Ohio 44143 (719) 432-2509",
            "http://www.progressive.com",
            "investor_relations@progressive.com",
            "PROGRESSIVE REPORTS JUNE RESULTS",
            "MAYFIELD VILLAGE, OHIO -- July 15, 2026 -- The Progressive Corporation "
            "(NYSE:PGR) today reported results for the month and quarter ended June 30, 2026.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "PROGRESSIVE REPORTS JUNE RESULTS"
    assert "Company Contact" not in hl
    assert "progressive.com" not in hl


def test_contact_block_names_before_emails_are_skipped() -> None:
    # Nike: the header matched, but _skip_contact_block broke on the four-word
    # names line ("Paul Trussell Sandra Carreon-John") as "content", making it
    # the headline. A name/title line followed by an email is still detail.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "q1fy27exhibit991er.htm", "EX-99.1",
            "Investor Contact: Media Contact:",
            "Paul Trussell Sandra Carreon-John",
            "investor.relations@nike.com",
            "media.relations@nike.com",
            "NIKE, INC. REPORTS FISCAL 2027 FIRST QUARTER RESULTS",
            "BEAVERTON, Ore., Oct. 1, 2026 -- NIKE, Inc. (NYSE:NKE) today reported "
            "fiscal 2027 financial results for its first quarter ended August 31, 2026.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "NIKE, INC. REPORTS FISCAL 2027 FIRST QUARTER RESULTS"
    assert "Trussell" not in hl
    assert "nike.com" not in hl


def test_contact_header_financial_role_prefix() -> None:
    # Hershey: "FINANCIAL CONTACT:" — the role-prefix list lacked "financial",
    # so the header fell through to the single-line contact skip and the
    # names line became the headline.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "EXHIBIT 99.1 - PRESS RELEASE DATED JULY 30, 2026",
            "FINANCIAL CONTACT: MEDIA CONTACT:",
            "Anoori Naughton Allison Kleinfelter",
            "anaughton@hersheys.com akleinfelter@hersheys.com",
            "Hershey Reports Second-Quarter 2026 Financial Results",
            "HERSHEY, Pa., July 30, 2026 - The Hershey Company (NYSE: HSY) today "
            "announced net sales and earnings for the second quarter ended June 28, 2026.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Hershey Reports Second-Quarter 2026 Financial Results"
    assert "Naughton" not in hl
    assert "hersheys.com" not in hl


def test_contact_header_bare_role_labels() -> None:
    # American Airlines: bare "Corporate Communications" / "Investor Relations"
    # labels with no colon head the contact blocks; the old regex required the
    # colon, so "Corporate Communications" became the headline.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "a8kerexhibit991q2-26.htm", "EX-99.1", "Exhibit 99.1",
            "Corporate Communications",
            "mediarelations@aa.com",
            "Investor Relations",
            "investor.relations@aa.com",
            "FOR RELEASE: Thursday, July 23, 2026",
            "American Airlines continues to execute on commercial priorities, "
            "delivering highest quarterly revenue in company history",
            "FORT WORTH, Texas -- American Airlines Group Inc. (NASDAQ: AAL) today "
            "reported its second-quarter 2026 financial results.",
        )
    )
    assert hl is not None
    assert "American Airlines continues to execute on commercial priorities" in hl.split("\n\n")[0]
    assert "Corporate Communications" not in hl
    assert "aa.com" not in hl


def test_contact_header_with_inline_detail() -> None:
    # Hilton: "Investor Contact 7930 Jones Branch Drive" — the header carries
    # inline address detail and no colon, so the old regex missed it and
    # "Charlie Ruehr" became the headline.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "q22026earningsrelease.htm", "PRESS RELEASE",
            "Investor Contact 7930 Jones Branch Drive",
            "Charlie Ruehr",
            "McLean, VA 22102",
            "+1 703 883 1000 ir.hilton.com",
            "Media Contact",
            "Kent Landers",
            "+1 703 883 3246",
            "Hilton Reports Second Quarter Results",
            "MCLEAN, VA (July 28, 2026) - Hilton Worldwide Holdings Inc. (NYSE: HLT) "
            "today reported its second quarter 2026 results.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Hilton Reports Second Quarter Results"
    assert "Charlie Ruehr" not in hl
    assert "Kent Landers" not in hl
    assert "703 883" not in hl


def test_contact_block_names_before_phones_are_skipped() -> None:
    # Cisco: the names line is followed by company tokens and phone numbers —
    # the lookahead must see through one non-contact line to the phones.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "exhibit991pressrelease-q4f.htm", "EX-99.1",
            "Press Contact: Investor Relations Contact:",
            "Robyn Blum Sami Badri",
            "Cisco Cisco",
            "1 (408) 930-8548 1 (469) 420-4834",
            "rojenkin@cisco.com sambadri@cisco.com",
            "CISCO REPORTS FOURTH QUARTER AND FISCAL YEAR 2026 EARNINGS",
            "News Summary: record top and bottom-line performance with double-digit "
            "growth in Q4 and FY 2026.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "CISCO REPORTS FOURTH QUARTER AND FISCAL YEAR 2026 EARNINGS"
    assert "Robyn Blum" not in hl
    assert "cisco.com" not in hl


def test_contact_block_lookahead_does_not_swallow_headline() -> None:
    # The email/phone lookahead must not consume a real headline: a Title-Case
    # headline (shaped like "Best Buy Reports First Quarter Results") followed
    # by narrative — not by an email — still becomes the headline.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "Contact:",
            "Ken Bond",
            "Oracle Investor Relations",
            "1.650.607.0349",
            "ken.bond@oracle.com",
            "Best Buy Reports First Quarter Results",
            "RICHFIELD, Minn., May 29, 2026 -- Best Buy Co., Inc. (NYSE: BBY) today "
            "announced results for the first quarter ended May 2, 2026.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Best Buy Reports First Quarter Results"
    assert "Ken Bond" not in hl


def test_skip_contact_block_lookahead_unit() -> None:
    # Direct unit test of the batch-105 lookahead: a content-shaped name line
    # followed by an email stays inside the block; one followed by narrative
    # ends it.
    from tickerlens.data.filings import _skip_contact_block

    lines = [
        "Investor Contact:",
        "Paul Trussell Sandra Carreon-John",
        "investor.relations@nike.com",
        "NIKE, INC. REPORTS FISCAL 2027 FIRST QUARTER RESULTS",
    ]
    assert _skip_contact_block(lines, 0) == 3

    lines2 = [
        "Investor Contact:",
        "Paul Trussell Sandra Carreon-John",
        "NIKE, INC. REPORTS FISCAL 2027 FIRST QUARTER RESULTS",
    ]
    # No email/phone follows the names line: the block ends there, as before
    # (the lookahead only extends the block when contact evidence follows).
    assert _skip_contact_block(lines2, 0) == 1


def test_contact_header_bare_role_no_colon() -> None:
    # RTX: bare "Media Contact" / "Investor Contact" with no colon head the
    # same block shape. The old regex required the colon, so the phone number
    # became the headline. Batch 105 (surfaced by the live repair).
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "a2026-07x238xkerexhibit99.htm", "EX-99", "Exhibit 99",
            "Media Contact",
            "202.384.2474",
            "Investor Contact",
            "781.522.5123",
            "RTX Reports Q2 2026 Results",
            "ARLINGTON, Va., July 23, 2026 -- RTX (NYSE: RTX) reports second "
            "quarter 2026 results.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "RTX Reports Q2 2026 Results"
    assert "202.384.2474" not in hl
    assert "Media Contact" not in hl


def test_masthead_residue_run_without_company_name() -> None:
    # General Dynamics: an address-block masthead with no company-name line
    # ("11011 Sunset Hills Road" / "Reston, Virginia 20190 News" /
    # "www.gd.com") before the contact block. The street address became the
    # headline. Batch 105 (surfaced by the live repair).
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99", "gd-20250330exhibit991.htm", "EX-99", "Exhibit 99.1",
            "11011 Sunset Hills Road",
            "Reston, Virginia 20190 News",
            "www.gd.com",
            "Contact: Jeff A. Davis",
            "Tel: 703 876 3483",
            "press@generaldynamics.com",
            "General Dynamics Reports First-Quarter 2025 Financial Results",
            "RESTON, Va., April 23, 2026 -- General Dynamics (NYSE: GD) today "
            "reported first-quarter 2025 financial results.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "General Dynamics Reports First-Quarter 2025 Financial Results"
    assert "Sunset Hills Road" not in hl
    assert "Jeff A. Davis" not in hl


def test_news_from_kicker_is_skipped() -> None:
    # AEP: "News from AEP" kicker before the real headline (batch-104 handled
    # the lone "News"; this generalizes to "News from <Company>"). Batch 105
    # (surfaced by the live repair).
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99", "a1q20268kpressreleaseex991.htm", "EX-99", "Exhibit 99.1",
            "News from AEP",
            "AEP Reports First-Quarter 2026 Earnings",
            "COLUMBUS, Ohio, April 29, 2026 -- American Electric Power (NASDAQ: "
            "AEP) today reported first-quarter 2026 earnings.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "AEP Reports First-Quarter 2026 Earnings"
    assert "News from AEP" not in hl


def test_orphaned_name_fragment_is_skipped() -> None:
    # Dollar General: the logo/name fragment "Dollar" on its own line before
    # the wrapped "General Corporation Reports ..." headline. The fragment
    # became the headline. Batch 105 (surfaced by the live repair).
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99", "tm2616084d1_ex99.htm", "EX-99", "EXHIBIT 99", "Exhibit 99",
            "Dollar",
            "General Corporation Reports First Quarter 2026 Results",
            "GOODLETTSVILLE, Tenn. -- Dollar General Corporation (NYSE: DG) "
            "today reported financial results for its first quarter ended May 1, 2026.",
        )
    )
    assert hl is not None
    assert "General Corporation Reports First Quarter 2026 Results" in hl.split("\n\n")[0]
    assert not hl.startswith("Dollar\n")


def test_leading_url_run_is_stripped_for_headline() -> None:
    # Ford: a page-image exhibit whose "line" is a whole page starting with
    # social links. The URL run became the headline. Batch 105 (surfaced by
    # the live repair).
    page1 = (
        "1 https://ford.to/facebook https://x.com/ford https://ford.to/linkedin "
        "Ford Reports First-Quarter 2026 Financial Results; Raises Full-Year Guidance "
        "\u2022 First-quarter revenue of $43.3 billion; net income of $2.5 billion. "
        "DEARBORN, Mich., April 29, 2026 -- Ford Motor Company (NYSE: F) today announced "
        "its first-quarter 2026 financial results. " + _FILLER_105 * 6
    )
    page2 = (
        "2 Total Company Highlights First Quarter 2025 2026 Change Wholesale Units (000) "
        "971 934 (4)% Revenue ($B) 40.7 43.3 6 % Net Income ($B) 0.5 2.5. " + _FILLER_105 * 6
    )
    html = (
        "<html><body><p>EX-99</p><p>exhibit99toapril292026fo.htm</p><p>EX-99</p>"
        f"<p>{page1}</p><p>{page2}</p></body></html>"
    )
    hl = extract_press_release_highlights(html)
    assert hl is not None
    assert hl.split("\n\n")[0] == "Ford Reports First-Quarter 2026 Financial Results; Raises Full-Year Guidance"
    assert "ford.to" not in hl.split("\n\n")[0]


def test_company_name_wrapped_headline_is_joined() -> None:
    # Genuine Parts Company: the company name on its own line followed by a
    # headline-verb line ("Reports Fourth Quarter ...") is a wrapped headline,
    # not a masthead. The old code skipped the name as a masthead and left a
    # fragment headline. Batch 105 (surfaced by the live repair).
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "d44894dex991.htm", "EX-99.1", "Exhibit 99.1",
            "www.genpt.com",
            "News Release",
            "February 17, 2026",
            "Genuine Parts Company",
            "Reports Fourth Quarter and Full-Year 2025 Results",
            "ATLANTA, Feb. 17, 2026 -- Genuine Parts Company (NYSE: GPC) today "
            "reported fourth quarter and full-year 2025 results.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Genuine Parts Company Reports Fourth Quarter and Full-Year 2025 Results"
    assert "genpt.com" not in hl


def test_company_name_masthead_still_skipped() -> None:
    # Guard: a company-name line followed by NON-headline text is still a
    # masthead and must be skipped (the batch-90 CHD behavior).
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "chd-ex99_1.htm", "EX-99.1",
            "Church & Dwight Co., Inc.",
            "News Release",
            "Contact:",
            "Lee McChesney",
            "CHURCH & DWIGHT DELIVERS STRONG SECOND QUARTER RESULTS",
            "EWING, NJ, July 31, 2026 -- Church & Dwight Co., Inc. (NYSE: CHD) today "
            "announced that the Company exceeded its second quarter outlook.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "CHURCH & DWIGHT DELIVERS STRONG SECOND QUARTER RESULTS"
    assert not hl.startswith("Church & Dwight Co., Inc.\n")


def test_dash_wrapped_page_number_never_headline() -> None:
    # Batch 106: Merck's Donnelley exhibits open with "- 1 -" (dash-wrapped
    # page number) before the real headline. It was stored as the headline.
    from tickerlens.data.filings import _ADMIN_LINE_RE
    assert _ADMIN_LINE_RE.match("- 1 -")
    assert _ADMIN_LINE_RE.match("-1-")
    assert _ADMIN_LINE_RE.match("- 12 -")
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "Exhibit 99.1",
            "- 1 -",
            "News Release",
            "Merck & Co., Inc., Rahway, N.J., USA Announces",
            "Second-Quarter 2026 Financial Results",
            "RAHWAY, N.J., Aug. 4, 2026 -- Merck today announced results.",
        )
    )
    assert hl is not None
    head = hl.split("\n\n")[0]
    assert head == (
        "Merck & Co., Inc., Rahway, N.J., USA Announces "
        "Second-Quarter 2026 Financial Results"
    )


def test_bare_dash_never_headline() -> None:
    # Batch 106: Merck's page footers render a bare "-" line that was stored
    # as the headline on two quarters.
    from tickerlens.data.filings import _ADMIN_LINE_RE
    assert _ADMIN_LINE_RE.match("-")
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "Exhibit 99.1",
            "-",
            "Freeport Reports",
            "Second-Quarter 2026 Results",
            "PHOENIX, AZ, July 23, 2026 -- Freeport reported results.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Freeport Reports Second-Quarter 2026 Results"


def test_verb_fragment_headline_joins_continuation() -> None:
    # Batch 106: a headline ending with a headline verb ("Freeport Reports")
    # is a company+verb fragment; the continuation ("Second-Quarter and
    # Six-Month 2026 Results") is part of the headline, not the lede.
    from tickerlens.data.filings import _join_wrapped_headline
    lines = [
        "Freeport Reports",
        "Second-Quarter and Six-Month 2026 Results",
        "PHOENIX, AZ, July 23, 2026 -- the lede starts here with a period.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "Freeport Reports Second-Quarter and Six-Month 2026 Results"
    assert next_i == 2


def test_verb_fragment_headline_ignores_sentence_lede() -> None:
    # Guard: a genuine "[Company] Reports" short headline followed by a
    # sentence-terminated lede line must NOT join — the terminal punctuation
    # guard keeps short headlines from swallowing the lede.
    from tickerlens.data.filings import _join_wrapped_headline
    lines = [
        "Acme Corp Reports",
        "Net income was 5.2 billion dollars, up 8 percent year over year.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "Acme Corp Reports"
    assert next_i == 1


def test_verb_fragment_joins_long_continuation() -> None:
    # Batch 106: Merck's continuation runs 119 chars — the old 100-char cap
    # blocked the join. Long continuations still join when every other guard
    # passes (no terminal punctuation, no bullet/admin/contact markers).
    from tickerlens.data.filings import _join_wrapped_headline
    cont = (
        "Second-Quarter 2026 Financial Results; Highlights Key Regulatory and "
        "Clinical Milestones Across Broad, Diverse Pipeline"
    )
    assert len(cont) > 100
    lines = ["Merck & Co., Inc., Rahway, N.J., USA Announces", cont,
             "Financial Highlights"]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == (
        "Merck & Co., Inc., Rahway, N.J., USA Announces " + cont
    )
    assert next_i == 2


def test_suite_address_masthead_residue_skipped() -> None:
    # Batch 106: United Rentals' masthead ("United Rentals, Inc." /
    # "100 First Stamford Place, Suite 700" / "Stamford, CT 06902" /
    # "Telephone: ..." / "unitedrentals.com") — the 6-word suite address
    # slipped past the 4-word masthead-residue guard and became the headline.
    from tickerlens.data.filings import _looks_like_masthead_residue
    assert _looks_like_masthead_residue("100 First Stamford Place, Suite 700")
    # Guard: a digit-bearing headline without a suite designator and over 4
    # words is still NOT residue.
    assert not _looks_like_masthead_residue("Q2 2026 Revenue Up 15 Percent Year Over Year")
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "Exhibit 99.1",
            "United Rentals, Inc.",
            "100 First Stamford Place, Suite 700",
            "Stamford, CT 06902",
            "Telephone: 203 622 3131",
            "unitedrentals.com",
            "United Rentals Announces Record Second Quarter Results",
            "STAMFORD, Conn. -- July 22, 2026 -- United Rentals today announced results.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "United Rentals Announces Record Second Quarter Results"


def test_page_number_fragments_never_headline() -> None:
    # Batch 106: Merck's "- 1 -" page number can split across lines ("-" /
    # "1 -"). Both fragments are admin, never headline material.
    from tickerlens.data.filings import _ADMIN_LINE_RE
    assert _ADMIN_LINE_RE.match("1 -")
    assert _ADMIN_LINE_RE.match("- 1")
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "Exhibit", "99.1",
            "-",
            "1 -",
            "News Release",
            "Merck & Co., Inc., Rahway, N.J.,",
            "USA Announces Second-Quarter 2025 Financial Results",
            "RAHWAY, N.J. -- Merck today announced results.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "Merck & Co., Inc., Rahway, N.J., USA Announces "
        "Second-Quarter 2025 Financial Results"
    )


def test_comma_wrapped_headline_joins() -> None:
    # Batch 106: a headline ending with a comma ("Merck & Co., Inc., Rahway,
    # N.J.,") is a wrap fragment — a complete headline never ends with a
    # comma. The continuation joins under the usual guards.
    from tickerlens.data.filings import _join_wrapped_headline
    lines = [
        "Merck & Co., Inc., Rahway, N.J.,",
        "USA Announces Second-Quarter 2025 Financial Results",
        "RAHWAY, N.J. -- the lede starts here with a period.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == (
        "Merck & Co., Inc., Rahway, N.J., USA Announces "
        "Second-Quarter 2025 Financial Results"
    )
    assert next_i == 2


def test_multi_line_headline_iterates_joins() -> None:
    # Batch 106: "WM Announces" / "Fourth Quarter and" / "Full Year 2025
    # Results" — the verb-fragment join fires, then the wrap-word ("and")
    # join fires again. Iteration is bounded and each join re-checks guards.
    from tickerlens.data.filings import _join_wrapped_headline
    lines = [
        "WM Announces",
        "Fourth Quarter and",
        "Full Year 2025 Results",
        "HOUSTON -- the lede starts here with a period.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "WM Announces Fourth Quarter and Full Year 2025 Results"
    assert next_i == 3


def test_multi_join_stops_at_bullet() -> None:
    # Guard: iteration stops at a bullet line even if the headline ends with
    # a wrap word — the bullet guard applies to every join.
    from tickerlens.data.filings import _join_wrapped_headline
    lines = [
        "Acme Reports",
        "Fourth Quarter and",
        "• Bullet lede starts here",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "Acme Reports Fourth Quarter and"
    assert next_i == 2


def test_split_news_release_kicker_never_headline() -> None:
    # Batch 106: Merck's Donnelley exhibits split the kicker across lines
    # ("News" / "Release"). "News" was already admin; bare "Release" is now
    # too. A real headline is never one word.
    from tickerlens.data.filings import _ADMIN_LINE_RE
    assert _ADMIN_LINE_RE.match("Release")
    assert _ADMIN_LINE_RE.match("Press")
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "Exhibit 99.1",
            "-",
            "1 -",
            "News",
            "Release",
            "Merck & Co.,",
            "Inc., Rahway, N.J., USA Announces Third-Quarter 2025 Financial Results",
            "RAHWAY, N.J. -- Merck today announced results.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "Merck & Co., Inc., Rahway, N.J., USA Announces "
        "Third-Quarter 2025 Financial Results"
    )


def test_ampersand_wrap_headline_joins() -> None:
    # Batch 106: "Merck &" — the & in the wrap-tail list never matched
    # because \b doesn't fire between space and &. Symbols match without a
    # word boundary; words keep \b on both sides ("Anderson" must not match).
    from tickerlens.data.filings import _HEADLINE_WRAP_TAIL_RE, _join_wrapped_headline
    assert _HEADLINE_WRAP_TAIL_RE.search("Merck &")
    assert _HEADLINE_WRAP_TAIL_RE.search("Results and")
    assert not _HEADLINE_WRAP_TAIL_RE.search("Anderson Cooper")
    assert not _HEADLINE_WRAP_TAIL_RE.search("Quarterly Results")
    lines = [
        "Merck &",
        "Co., Inc., Rahway, N.J., USA Announces First-Quarter 2026 Financial Results",
        "RAHWAY, N.J. -- the lede starts here with a period.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == (
        "Merck & Co., Inc., Rahway, N.J., USA Announces "
        "First-Quarter 2026 Financial Results"
    )
    assert next_i == 2


def test_lone_comma_never_headline() -> None:
    # Batch 106: Deere's exhibit has a stray "," line before the real
    # headline. A headline never ends with (or is) a comma.
    from tickerlens.data.filings import _ADMIN_LINE_RE
    assert _ADMIN_LINE_RE.match(",")
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "Exhibit 99.1",
            ",",
            "Deere Reports Net Income of $1.245 Billion for Fourth Quarter",
            "MOLINE, Ill. -- Deere today announced results.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Deere Reports Net Income of $1.245 Billion for Fourth Quarter"


def test_trailing_comma_stripped_from_headline() -> None:
    # Batch 106: when the continuation is too long to join (URI Q4 2025's
    # 166-char sub-headline), the picked headline ends with a comma — strip
    # it rather than storing the wart.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "Exhibit 99.1",
            "United Rentals Announces Fourth Quarter and Full-Year 2025 Results,",
            "Introduces 2026 Outlook for Growth, and Announces Plan to Return Approximately $2 Billion to Shareholders in 2026 Supported by New $5 Billion Share Repurchase Program",
            "STAMFORD, Conn. -- United Rentals today announced results.",
        )
    )
    assert hl is not None
    head = hl.split("\n\n")[0]
    assert head == "United Rentals Announces Fourth Quarter and Full-Year 2025 Results"
    assert not head.endswith(",")


def test_bullet_highlights_with_dollar_and_percent_are_not_a_table() -> None:
    # Batch 107: Amphenol's "Third Quarter 2024 Highlights:" bullets each
    # carry $ and % ("Record sales of $4.04 billion, up 26%...") — four such
    # bullets tripped the data_rows >= 4 threshold and the genuine narrative
    # section was discarded as a financial table, leaving 6 APH quarters
    # with no highlights. Bullet-led lines are prose, not table rows.
    from tickerlens.data.filings import _looks_like_financial_table
    bullets = [
        "• Record sales of $4.04 billion, up 26% in U.S. dollars",
        "• Record GAAP Diluted EPS of $0.48, up 17% compared to prior year",
        "• Record Adjusted Diluted EPS of $0.50, up 28% compared to prior year",
        "• GAAP and record Adjusted Operating Margin of 20.3% and 21.9%",
        "• Operating and Free Cash Flow of $704 million and $476 million",
    ]
    assert not _looks_like_financial_table(bullets)


def test_table_rows_without_bullets_still_detected() -> None:
    # The batch-97 guard still fires on real tables (Lilly/WM shapes): units
    # parentheticals and $+% data rows without bullets.
    from tickerlens.data.filings import _looks_like_financial_table
    assert _looks_like_financial_table([
        "Trulicity $1,234  $1,100  12%",
        "Mounjaro $987  $800  23%",
        "Verzenio $654  $600  9%",
        "Jardiance $321  $300  7%",
    ])
    assert _looks_like_financial_table([
        "(Dollars in millions)",
        "Revenue  10,000  9,000",
    ])


def test_bare_masthead_name_skipped_for_real_headline() -> None:
    # Batch 107: Amphenol heads the release with the bare company name (no
    # corporate suffix) + kicker/address block before the real headline.
    # The name must not become the headline.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "Exhibit 99.1",
            "Amphenol",
            "News Release",
            "World Headquarters",
            "358 Hall Avenue",
            "Wallingford, CT 06492",
            "Telephone (203) 265-8900",
            "AMPHENOL REPORTS RECORD THIRD QUARTER 2024 RESULTS",
            "Third Quarter 2024 Highlights:",
            "• Record sales of $4.04 billion, up 26% in U.S. dollars",
            "• Record GAAP Diluted EPS of $0.48, up 17% compared to prior year",
            "Wallingford, Connecticut, October 23, 2024. Amphenol Corporation "
            "(NYSE: APH) today reported third quarter 2024 results.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "AMPHENOL REPORTS RECORD THIRD QUARTER 2024 RESULTS"


def test_bare_masthead_name_kept_when_no_headline_follows() -> None:
    # The skip only fires when a headline-shaped line follows past a
    # residue block — a genuine short headline with no masthead shape
    # after it is picked as-is.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "United Airlines",
            "CHICAGO, Oct. 15, 2025 -- United Airlines today announced "
            "third-quarter 2025 financial results with filler text to pass "
            "the minimum length requirement for extraction to succeed here.",
        )
    )
    assert hl is not None
    # No residue block + no later headline: the name stays (honest fallback
    # for docs with no clear headline, e.g. BRK.B — batch 109: UAL's releases
    # do have real headlines; the stored company-name headlines were stale
    # extractions, repaired live).
    assert hl.split("\n\n")[0] == "United Airlines"


def test_conjunction_lead_continuation_joins() -> None:
    # Batch 107: "AMPHENOL REPORTS RECORD FOURTH QUARTER" / "AND FULL YEAR
    # 2024 RESULTS" — a mid-phrase wrap with the conjunction leading the
    # continuation line.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "AMPHENOL REPORTS RECORD FOURTH QUARTER",
            "AND FULL YEAR 2024 RESULTS",
            "Fourth Quarter 2024 Highlights:",
            "• Sales of $4.3 billion, up 30% in U.S. dollars",
            "Wallingford, Connecticut, January 22, 2025. Amphenol Corporation "
            "today reported fourth quarter 2024 results.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "AMPHENOL REPORTS RECORD FOURTH QUARTER AND FULL YEAR 2024 RESULTS"
    )


def test_conjunction_lead_does_not_swallow_lede() -> None:
    # A headline followed by a lede sentence that merely starts with "And"
    # but ends with terminal punctuation is not joined.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "ACME REPORTS RECORD QUARTER",
            "And the outlook for next year is strong and positive.",
            "Wallingford, Connecticut, October 23, 2024. Acme Corporation "
            "today reported third quarter 2024 results with enough filler "
            "text to pass the minimum extraction length requirement.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "ACME REPORTS RECORD QUARTER"


def test_wrap_tail_still_joins_after_masthead_skip_change() -> None:
    # Guard: the batch-106 verb-fragment join ("WM Announces" / "Fourth
    # Quarter and" / "Full Year 2025 Results") must not be stolen by the
    # batch-107 bare-masthead skip — a verb tail is a wrap fragment, never
    # a masthead name.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "WM Announces",
            "Fourth Quarter and",
            "Full Year 2025 Results",
            "HOUSTON -- WM today announced results with enough filler text "
            "to pass the minimum extraction length requirement for this "
            "regression test of the wrapped-headline join behavior.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "WM Announces Fourth Quarter and Full Year 2025 Results"


def test_full_address_masthead_never_headline() -> None:
    # Batch 107: Equifax heads releases with a 50-char street address
    # ("1550 Peachtree Street, N.W. Atlanta, Georgia 30309") that clears
    # the 48-char bound in _looks_like_masthead_residue and became the
    # headline for all 8 quarters. A full address is an admin line.
    from tickerlens.data.filings import _ADMIN_LINE_RE
    assert _ADMIN_LINE_RE.match("1550 Peachtree Street, N.W. Atlanta, Georgia 30309")
    assert not _ADMIN_LINE_RE.match("2025 Results Are In")
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "Exhibit 99.1",
            "1550 Peachtree Street, N.W. Atlanta, Georgia 30309",
            "NEWS RELEASE",
            "Contact:",
            "Trevor Burns Kate Walker",
            "Investor Relations Media Relations",
            "trevor.burns@equifax.com mediainquiries@equifax.com",
            "Equifax Delivers Strong 10% Revenue Growth in Third Quarter 2026",
            "ATLANTA, OCTOBER 20, 2026 -- Equifax today announced results.",
            "• Third quarter reported revenue of $1.693 billion, up 10%",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "Equifax Delivers Strong 10% Revenue Growth in Third Quarter 2026"
    )


def test_ordinal_tail_headline_joins() -> None:
    # Batch 108: a headline ending on a period/ordinal word ("Plug Power
    # Third", "Kroger Reports Fourth") is a wrapped-headline fragment, not a
    # complete headline — the continuation sits on the next line.
    from src.tickerlens.data.filings import _join_wrapped_headline

    lines = [
        "Plug Power Third",
        "Quarter 2025 Highlights",
        "$177 Million in Quarterly Revenue",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "Plug Power Third Quarter 2025 Highlights"
    assert next_i == 2


def test_ordinal_tail_full_joins() -> None:
    # Batch 108: "Full" is a period word too ("Intercontinental Exchange
    # Reports Strong Full" / "Year 2025 Results").
    from src.tickerlens.data.filings import _join_wrapped_headline

    lines = [
        "Intercontinental Exchange Reports Strong Full",
        "Year 2025 Results",
        "ATLANTA -- the lede starts here with a period.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "Intercontinental Exchange Reports Strong Full Year 2025 Results"
    assert next_i == 2


def test_quarter_tail_bare_year_joins() -> None:
    # Batch 108: "{ordinal} Quarter" / bare year ("Intercontinental Exchange
    # Reports Second Quarter" / "2026"). The year is never a lede start, so
    # the digit-lead guard is bypassed for this exact shape only.
    from src.tickerlens.data.filings import _join_wrapped_headline

    lines = [
        "Intercontinental Exchange Reports Second Quarter",
        "2026",
        "ATLANTA -- the lede starts here with a period.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "Intercontinental Exchange Reports Second Quarter 2026"
    assert next_i == 2


def test_ordinal_tail_multi_join_with_conjunction() -> None:
    # Batch 108: the ordinal join composes with the batch-107 conjunction
    # lead ("Kroger Reports Second" / "Quarter 2026 Results" /
    # "and Updates Guidance for 2026").
    from src.tickerlens.data.filings import _join_wrapped_headline

    lines = [
        "Kroger Reports Second",
        "Quarter 2026 Results",
        "and Updates Guidance for 2026",
        "Second Quarter Highlights",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == (
        "Kroger Reports Second Quarter 2026 Results and Updates Guidance for 2026"
    )
    assert next_i == 3


def test_ordinal_tail_ignores_sentence_lede() -> None:
    # Batch 108: the continuation guards still apply — a sentence-terminated
    # lede line never joins an ordinal-tail fragment.
    from src.tickerlens.data.filings import _join_wrapped_headline

    lines = [
        "Kroger Reports Fourth",
        "Quarter results were strong overall.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "Kroger Reports Fourth"
    assert next_i == 1


def test_bare_year_without_quarter_tail_not_joined() -> None:
    # Batch 108: a bare year joins ONLY after "{ordinal} Quarter" / "Full
    # Year" — a complete headline is never glued to a stray year line.
    from src.tickerlens.data.filings import _join_wrapped_headline

    lines = [
        "Acme Reports Results",
        "2026",
        "Net income was strong this quarter.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == "Acme Reports Results"
    assert next_i == 1


def test_ordinal_fragment_not_misread_as_bare_masthead() -> None:
    # Batch 108: end-to-end regression for the batch-107 _skip_bare_masthead_name
    # misfire — "Plug Power Third" was read as a bare masthead name, its
    # continuation "Quarter 2025 Highlights" as digit-bearing residue, and
    # "$177 Million in Quarterly Revenue" was picked as the headline.
    from src.tickerlens.data.filings import _skip_bare_masthead_name

    lines = [
        "Plug Power Third",
        "Quarter 2025 Highlights",
        "$177 Million in Quarterly Revenue",
    ]
    assert _skip_bare_masthead_name(lines, 0) is None
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "Exhibit 99.1",
            "Plug Power Third",
            "Quarter 2025 Highlights",
            "$177 Million in Quarterly Revenue",
            "Continued Global Market Expansion and Operational Progress",
            "SLINGERLANDS, N.Y., November 10, 2025 - Plug Power Inc. (NASDAQ: PLUG), "
            "a global leader in comprehensive hydrogen solutions, today announced "
            "its financial results for the third quarter ended September 30, 2025.",
            "• For the third quarter 2025, revenue was $177 million, up 13% year over year.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Plug Power Third Quarter 2025 Highlights"


def test_fragment_join_continues_through_wrap() -> None:
    # Batch 108: a 1-word fragment join must not stop on a dangling wrap tail
    # ("Kroger" / "Reports Third Quarter 2025 Results and" / "Updates") — the
    # joined fragment feeds through the wrap joiner.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "Exhibit 99.1",
            "Kroger",
            "Reports Third Quarter 2025 Results and",
            "Updates",
            "Guidance for 2025",
            "Third Quarter",
            "Highlights",
            "CINCINNATI, November 20, 2025 - The Kroger Co. (NYSE: KR) today "
            "reported its third quarter 2025 results.",
            "• Identical Sales without fuel increased 2.6%.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Kroger Reports Third Quarter 2025 Results and Updates"


def test_verb_lead_join_continues_through_wrap() -> None:
    # Batch 108: same for the company-name + headline-verb join ("Genuine
    # Parts Company" / "Reports Fourth Quarter and" / "Full-Year 2025 Results").
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "Exhibit 99.1",
            "Genuine Parts Company",
            "Reports Fourth Quarter and",
            "Full-Year 2025 Results",
            "ATLANTA, February 18, 2026 - Genuine Parts Company (NYSE: GPC) "
            "today reported fourth quarter and full-year 2025 results.",
            "• Fourth quarter sales were $5.8 billion, up 2.1%.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "Genuine Parts Company Reports Fourth Quarter and Full-Year 2025 Results"
    )


def test_xcel_address_block_masthead_skipped() -> None:
    # Batch 108: Xcel Energy heads releases with a street address, a
    # date+city+ZIP line, and the all-caps company name before the real
    # headline. None of them may become the headline.
    filler = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 20
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.01", "Exhibit 99.01",
            "414 Nicollet Mall",
            "July 30, 2026 Minneapolis, MN 55401",
            "XCEL ENERGY",
            "SECOND QUARTER 2026 EARNINGS REPORT",
            "•Second quarter diluted GAAP and ongoing earnings per share were $0.93.",
            "MINNEAPOLIS -- Xcel Energy Inc. (NASDAQ: XEL) today reported 2026 "
            "second quarter GAAP earnings.",
            filler,
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "SECOND QUARTER 2026 EARNINGS REPORT"


def test_all_caps_name_before_all_caps_headline_skipped() -> None:
    # Batch 108: the all-caps masthead rule is narrow — a mixed-case short
    # line before a headline is not skipped by it.
    from src.tickerlens.data.filings import _looks_like_headline

    assert _looks_like_headline("SECOND QUARTER 2026 EARNINGS REPORT")
    assert not _looks_like_headline("Xcel Energy")


def test_department_line_in_masthead_not_headline() -> None:
    # Batch 109: PACCAR heads the release with "PACCAR Inc" / "Public Affairs
    # Department" / PO box / city / "Contact:" block before the real headline.
    # The department line is masthead residue, not the headline — and the
    # masthead skip must stop at the contact header so the contact block is
    # skipped by the contact-header branch (not stranded as headline
    # candidates).
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "Exhibit 99.1",
            "PACCAR Inc",
            "Public Affairs Department",
            "P.O. Box 1518",
            "Bellevue, WA 98009",
            "Contact:",
            "Ken Hastings",
            "(425) 468-7530",
            "ken.hastings@paccar.com",
            "FOR IMMEDIATE RELEASE",
            "PACCAR Increases Quarterly Revenues and Profits",
            "July 28, 2026, Bellevue, Washington -- PACCAR achieved very good "
            "revenues and increased net income in the second quarter of 2026.",
            "Financial Highlights - Second Quarter 2026",
            "• Consolidated net sales and revenues of $7.55 billion.",
            "• Consolidated net income of $752.0 million.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "PACCAR Increases Quarterly Revenues and Profits"


def test_masthead_block_skip_stops_at_contact_header() -> None:
    # Batch 109: _skip_masthead_block consumes the address block but stops at
    # the contact header — the contact block belongs to the headline pass's
    # contact-header branch.
    from src.tickerlens.data.filings import _skip_masthead_block

    lines = [
        "Public Affairs Department",
        "P.O. Box 1518",
        "Bellevue, WA 98009",
        "Contact:",
        "Ken Hastings",
        "(425) 468-7530",
        "PACCAR Increases Quarterly Revenues and Profits",
    ]
    assert _skip_masthead_block(lines, 0) == 3


def test_department_residue_is_narrow() -> None:
    # Batch 109: the department rule is end-anchored and word-count-guarded —
    # a real headline mentioning a department is never masthead residue.
    from src.tickerlens.data.filings import _looks_like_masthead_residue

    assert _looks_like_masthead_residue("Public Affairs Department")
    assert _looks_like_masthead_residue("Investor Relations Dept.")
    assert not _looks_like_masthead_residue(
        "Justice Department announces new antitrust rules today"
    )
    assert not _looks_like_masthead_residue("Department of Energy grants awarded")


def test_semicolon_tail_headline_joins() -> None:
    # Batch 109: a headline ending with a semicolon is a wrapped fragment
    # (RSG: "Republic Services, Inc. Reports Fourth Quarter and Full-Year
    # 2024 Results;" / "Provides 2025 Full-Year Financial Guidance"). A
    # complete headline never ends with a semicolon.
    from src.tickerlens.data.filings import _join_wrapped_headline

    lines = [
        "Republic Services, Inc. Reports Fourth Quarter and Full-Year 2024 Results;",
        "Provides 2025 Full-Year Financial Guidance",
        "● Exceeded full-year guidance.",
    ]
    headline, next_i = _join_wrapped_headline(lines, 0)
    assert headline == (
        "Republic Services, Inc. Reports Fourth Quarter and Full-Year 2024 Results; "
        "Provides 2025 Full-Year Financial Guidance"
    )
    assert next_i == 2


def test_company_name_with_ticker_parenthetical_not_headline() -> None:
    # Batch 109: Citi heads every release with "Citigroup Inc. (NYSE: C)" +
    # date before the real headline ("FIRST QUARTER 2024 RESULTS AND KEY
    # METRICS"). The ticker parenthetical does not make it a headline — the
    # company-name masthead rule still applies.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "Exhibit 99.1",
            "For Immediate Release",
            "Citigroup Inc. (NYSE: C)",
            "April 12, 2024",
            "FIRST QUARTER 2024 RESULTS AND KEY METRICS",
            "CEO COMMENTARY",
            "Citi CEO Jane Fraser said, \"We had a good quarter with filler "
            "text to pass the minimum length requirement for extraction here.\"",
            "New York, April 12, 2024 -- Citigroup Inc. today reported net "
            "income for the first quarter 2024 with additional filler text.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "FIRST QUARTER 2024 RESULTS AND KEY METRICS"


def test_spaced_earnings_release_label_skipped() -> None:
    # Elevance Health: a spaced-letter "E A R N I N G S R E L E A S E"
    # document label heads the release; the real headline follows it.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "2",
            "a3q2024elvearningsrelease.htm",
            "EX-99.1",
            "E A R N I N G S R E L E A S E",
            "ELEVANCE HEALTH REPORTS THIRD QUARTER 2024 RESULTS",
            "Indianapolis, IN - October 17, 2024 - Elevance Health, Inc. (NYSE: ELV) "
            "reported third quarter 2024 results with additional filler text here.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "ELEVANCE HEALTH REPORTS THIRD QUARTER 2024 RESULTS"


def test_wrapped_spaced_earnings_label_skipped() -> None:
    # Elevance Health Q3 2025: the spaced kicker wraps across two lines
    # ("E A R" / "N I N G S R E L E A S E" with thin spaces); both lines are
    # the label, not the headline.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "Exhibit 99.1",
            "E A R",
            "N I N G S \u2009\u2009R E L E A S E",
            "ELEVANCE HEALTH REPORTS THIRD QUARTER 2025 RESULTS",
            "Indianapolis, IN - October 16, 2025 - Elevance Health, Inc. (NYSE: ELV) "
            "reported third quarter 2025 results with additional filler text here.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "ELEVANCE HEALTH REPORTS THIRD QUARTER 2025 RESULTS"


def test_prefixed_earnings_release_label_and_address_block_skipped() -> None:
    # Amgen: a ticker/date-prefixed "AMGN-2024.9.30 EARNINGS RELEASE" label,
    # then "Exhibit 99.1" / "News Release", then a head-office address block
    # (street / city,ST ZIP / telephone / URL) before the real headline.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "2",
            "amgn-20240930earningsrelea.htm",
            "AMGN-2024.9.30 EARNINGS RELEASE",
            "Exhibit 99.1",
            "News Release",
            "One Amgen Center Drive",
            "Thousand Oaks, CA 91320-1799",
            "Telephone 805-447-1000",
            "www.amgen.com",
            "AMGEN REPORTS THIRD QUARTER 2024 FINANCIAL RESULTS",
            "THOUSAND OAKS, Calif. (Oct. 30, 2024) - Amgen (NASDAQ:AMGN) today "
            "announced financial results for the third quarter of 2024 here.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "AMGEN REPORTS THIRD QUARTER 2024 FINANCIAL RESULTS"
    assert "One Amgen Center Drive" not in hl
    assert "Thousand Oaks" not in hl.split("\n\n")[0]


def test_exhibit_dash_marker_skipped() -> None:
    # Air Products: the exhibit marker uses a dash ("EXHIBIT-99.1"), then
    # "Exhibit 99.1" / "News Release" before the real headline.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "exhibit99130sep24.htm",
            "EXHIBIT-99.1",
            "Exhibit 99.1",
            "News Release",
            "Air Products Reports Fiscal 2024 Fourth Quarter GAAP EPS of $8.81",
            "LEHIGH VALLEY, Pa. (November 7, 2024) - Air Products (NYSE:APD) today "
            "reported full-year fiscal 2024 results with additional filler text.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "Air Products Reports Fiscal 2024 Fourth Quarter GAAP EPS of $8.81"
    )


def test_ticker_prefixed_exhibit_marker_skipped() -> None:
    # T-Mobile: a ticker-prefixed exhibit marker ("TMUS EXHIBIT 99.1") heads
    # the release; the real headline follows.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "tmus09302024ex991.htm",
            "TMUS EXHIBIT 99.1",
            "EXHIBIT 99.1",
            "T-Mobile Delivers Industry-Leading Growth in Customers in Q3",
            "Bellevue, WA -- October 23, 2024 -- T-Mobile US, Inc. (NASDAQ: TMUS) "
            "reported third quarter 2024 results with additional filler text.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "T-Mobile Delivers Industry-Leading Growth in Customers in Q3"
    )


def test_echibit_typo_marker_skipped() -> None:
    # Citi Q1 2025: the filer typoed the marker as "ECHIBIT 99.1".
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "ECHIBIT 99.1",
            "News Release",
            "CITIGROUP REPORTS FIRST QUARTER 2025 RESULTS",
            "New York, April 15, 2025 -- Citigroup Inc. today reported net income "
            "for the first quarter 2025 with additional filler text here.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "CITIGROUP REPORTS FIRST QUARTER 2025 RESULTS"


def test_name_prefixed_for_immediate_release_skipped() -> None:
    # TJX: a contact name heads the "FOR IMMEDIATE RELEASE" marker
    # ("Debra McConnell FOR IMMEDIATE RELEASE"); the real headline follows.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "Debra McConnell FOR IMMEDIATE RELEASE",
            "THE TJX COMPANIES, INC. REPORTS Q1 FY26 RESULTS",
            "Framingham, MA -- May 21, 2025 -- The TJX Companies, Inc. today "
            "reported first quarter fiscal 2026 results with filler text here.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "THE TJX COMPANIES, INC. REPORTS Q1 FY26 RESULTS"


def test_batch110_admin_patterns_reject_real_headline_shapes() -> None:
    # The new _ADMIN_LINE_RE alternatives must not swallow real headlines:
    # a "One"-led company name, a headline mentioning an exhibit, a street
    # suffix inside a longer headline, or a city/state without a ZIP.
    from tickerlens.data.filings import _ADMIN_LINE_RE

    assert not _ADMIN_LINE_RE.match("Oneok Announces Fourth Quarter 2025 Results")
    assert not _ADMIN_LINE_RE.match("T-Mobile Delivers Industry-Leading Growth in Q3")
    assert not _ADMIN_LINE_RE.match("Acme Reports Earnings Release Call Details")
    assert not _ADMIN_LINE_RE.match("CUPERTINO, California")
    assert not _ADMIN_LINE_RE.match("Thousand Oaks, CA")
    assert not _ADMIN_LINE_RE.match("One Amgen Center Driveway Expansion Planned")


def test_bare_earnings_release_label_with_exhibit_marker_skipped() -> None:
    # Amgen/Northrop: the bare "EARNINGS RELEASE" label is followed by
    # "Exhibit 99.1" / "News Release" (+ address block), not directly by the
    # headline. The label must still be skipped so the real headline wins.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "2",
            "amgn-20241231earningsrelea.htm",
            "EARNINGS RELEASE",
            "Exhibit 99.1",
            "News Release",
            "One Amgen Center Drive",
            "Thousand Oaks, CA 91320-1799",
            "Telephone 805-447-1000",
            "www.amgen.com",
            "AMGEN REPORTS FOURTH QUARTER AND FULL YEAR 2024 FINANCIAL RESULTS",
            "THOUSAND OAKS, Calif. (Feb. 4, 2025) - Amgen (NASDAQ:AMGN) today "
            "announced financial results for the fourth quarter of 2024 here.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "AMGEN REPORTS FOURTH QUARTER AND FULL YEAR 2024 FINANCIAL RESULTS"
    )


def test_long_headline_within_raised_limit_is_picked() -> None:
    # TJX Q4 FY25: the genuine headline runs 243 chars. At the old 220-char
    # limit it was unpickable (headline came back None and the lede filled
    # with contact detail lines). The raised limit picks it up.
    headline = (
        "THE TJX COMPANIES, INC. REPORTS Q4 AND FY25 RESULTS; Q4 COMP STORE "
        "SALES UP 5%, PRETAX PROFIT MARGIN OF 11.6%, AND FULL YEAR RESULTS "
        "WITH ADDITIONAL DETAIL HERE TO EXCEED THE OLD LIMIT OF TWO HUNDRED "
        "AND TWENTY CHARACTERS FOR HEADLINE LENGTH"
    )
    assert 220 < len(headline) <= 300
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "Exhibit 99.1",
            "CONTACT:",
            "Debra McConnell FOR IMMEDIATE RELEASE",
            "Global Communications Wednesday, February 26, 2025",
            "(508) 390-2323",
            headline,
            "Framingham, MA -- February 26, 2025 -- The TJX Companies, Inc. "
            "today reported fourth quarter fiscal 2025 results with filler.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == headline
    assert "Global Communications" not in hl.split("\n\n")[0]


def test_contact_header_company_name_prefixed_is_skipped() -> None:
    # Qualcomm: "Qualcomm Contact:" — a company-name-prefixed contact header
    # without the word "Company". The old regex only recognized the
    # "... Company Contact:" form, so the header became the headline on every
    # Qualcomm quarter. Batch 111.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "qcom092924erex991.htm", "Exhibit 99.1",
            "FOR IMMEDIATE RELEASE",
            "Qualcomm Contact:",
            "Mauricio Lopez-Hodoyan",
            "Vice President, Investor Relations",
            "Phone: 1-858-658-4813 | e-mail: ir@qualcomm.com",
            "Qualcomm Announces Fourth Quarter and Fiscal 2024 Results",
            "SAN DIEGO - November 6, 2024 - Qualcomm Incorporated (NASDAQ: QCOM) "
            "today announced results for its fourth quarter of fiscal 2024.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Qualcomm Announces Fourth Quarter and Fiscal 2024 Results"
    assert "Qualcomm Contact" not in hl
    assert "ir@qualcomm.com" not in hl
    assert "Mauricio Lopez-Hodoyan" not in hl


def test_contact_header_bare_role_label_with_colon() -> None:
    # BlackRock: "INVESTOR RELATIONS:" / "MEDIA RELATIONS:" — bare role labels
    # with a trailing colon. The old regex required no colon, so the header
    # became the headline on every BlackRock quarter. Batch 111.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "blk-ex99_1.htm", "Exhibit 99.1",
            "INVESTOR RELATIONS:",
            "Caroline Rodda 212.810.3442",
            "MEDIA RELATIONS:",
            "Ed Sweeney 646.231.0268",
            "BlackRock Reports Third Quarter 2024 Diluted EPS of $10.90, or $11.46 as adjusted",
            "New York, October 11, 2024 – BlackRock, Inc. (NYSE: BLK) today "
            "reported financial results for the third quarter of 2024.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "BlackRock Reports Third Quarter 2024 Diluted EPS of $10.90, or $11.46 as adjusted"
    )
    assert "INVESTOR RELATIONS" not in hl.split("\n\n")[0]
    assert "Caroline Rodda" not in hl
    assert "Ed Sweeney" not in hl


def test_contact_header_company_prefixed_never_matches_headline() -> None:
    # The company-name-prefixed branch is full-line anchored at a short line
    # ending in "Contact(s):" — a genuine headline never has that shape, and
    # a contact header with inline detail ("Analyst Contact: Abby Motsinger")
    # is not matched by this branch.
    from tickerlens.data.filings import _CONTACT_HEADER_RE

    assert not _CONTACT_HEADER_RE.match("Analyst Contact: Abby Motsinger")
    assert _CONTACT_HEADER_RE.match("Qualcomm Contact:")
    assert _CONTACT_HEADER_RE.match("INVESTOR RELATIONS:")


def test_dateline_is_never_the_headline() -> None:
    # Berkshire: its releases have no headline — company name + "NEWS
    # RELEASE" + date + dateline, then the lede. The old code stored the
    # company name; the pre-fix code picked the dateline. A dateline is never
    # a headline: the honest result is headline=None with the lede starting
    # after the dateline. Batch 112.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "d940849dex991.htm", "Exhibit 99.1",
            "BERKSHIRE HATHAWAY INC.",
            "NEWS RELEASE",
            "FOR IMMEDIATE RELEASE",
            "August 2, 2025",
            "Omaha, NE (BRK.A; BRK.B) –",
            "Berkshire’s operating results for the second quarter and first "
            "six months of 2025 and 2024 are summarized in the following "
            "paragraphs.",
        )
    )
    assert hl is not None
    assert "BERKSHIRE HATHAWAY" not in hl
    assert "Omaha" not in hl
    assert hl.split("\n\n")[0].startswith("Berkshire’s operating results")


def test_quarter_prefixed_earnings_release_label_is_skipped() -> None:
    # Berkshire Q1: "FIRST QUARTER 2026 EARNINGS RELEASE" sits between the
    # company name and "FOR IMMEDIATE RELEASE". The batch-110 label branches
    # only covered bare "Earnings Release" and single-token prefixes, so the
    # label became the headline. Batch 112.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1", "d74313dex991.htm", "Exhibit 99.1",
            "BERKSHIRE HATHAWAY INC.",
            "FIRST QUARTER 2026 EARNINGS RELEASE",
            "FOR IMMEDIATE RELEASE",
            "May 2, 2026",
            "Omaha, NE (BRK.A; BRK.B) –",
            "Berkshire’s operating results for the first quarters of 2026 "
            "and 2025 are summarized in the following paragraphs.",
        )
    )
    assert hl is not None
    assert "EARNINGS RELEASE" not in hl.split("\n\n")[0]
    assert hl.split("\n\n")[0].startswith("Berkshire’s operating results")


def test_dateline_and_quarter_label_regexes_stay_narrow() -> None:
    # The dateline branch only fires when no headline was found, but the
    # shapes themselves must never match a genuine headline — a real
    # headline never ends with a bare dash after a comma, and never is a
    # quarter-prefixed "earnings release" label.
    from tickerlens.data.filings import _DATELINE_RE, _QUARTER_EARNINGS_LABEL_RE

    assert _DATELINE_RE.match("Omaha, NE (BRK.A; BRK.B) –")
    assert _DATELINE_RE.match("NEW YORK, May 1, 2025 –")
    assert _DATELINE_RE.match("Cupertino, California, October 30, 2025 —")
    assert not _DATELINE_RE.match("Apple Reports Third Quarter Results")
    assert not _DATELINE_RE.match(
        "Mastercard Incorporated Reports Third Quarter 2024 Financial Results"
    )
    assert not _DATELINE_RE.match("Q2 2025 Results – Conference Call")
    assert _QUARTER_EARNINGS_LABEL_RE.match("FIRST QUARTER 2026 EARNINGS RELEASE")
    assert _QUARTER_EARNINGS_LABEL_RE.match("third quarter 2024 earnings release")
    assert not _QUARTER_EARNINGS_LABEL_RE.match(
        "Acme Schedules First Quarter Earnings Release"
    )
