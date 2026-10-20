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
