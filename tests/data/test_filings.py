from datetime import date

from tickerlens.data.filings import (
    AnnualFiling,
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
