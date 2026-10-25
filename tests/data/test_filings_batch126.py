"""Batch 126 regression tests: supplement-only packets are not highlights.

EOG Resources' earnings exhibits are combined release + supplement packets
whose narrative release text lives in full-page images; the text layer holds
only the supplement TOC and tables. The extractor nevertheless returned
"highlights" for 7 of 8 quarters:

- 6 exhibits land on a table footnote definition as the headline (the SPG
  TOC rule over-consumes the TOC and the first tables, stopping at the first
  >140-char line — a footnote legend), e.g. Q2 2026's "(B)Crude oil and
  condensate volumes are from UAE and Bahrain operations..." with a Balance
  Sheets table as the body. Q1 FY2026 stored exactly this shape, the only
  footnote-headline row in the whole DB (2378 stored rows scanned).
- Q3 FY2024 lands on the TOC subtitle as the headline
  ("Supplemental Financial and Operating Data Page") with the TOC entries
  themselves as the body (its TOC has only one standalone page line, so the
  TOC rule's >=2-page requirement never fires and nothing is skipped).

Both guards are narrow and load-bearing: the footnote guard matches only a
single letter/digit in parentheses, so "(NYSE: ACME)" and "(2026)" headlines
keep working; the TOC-body guard requires every body line to be a title +
page number, which a real lede never is. The honest outcome for EOG is
None ("Not available") on all 8 quarters — the image-page narrative is
structurally unextractable, same class as SKYD per batch 48.
"""

from tickerlens.data.filings import extract_press_release_highlights
from tests.data.test_filings import _contact_release_html


def _eog_footnote_html() -> str:
    """Q2 2026 shape: footnote definition picked as headline, table as body."""
    return _contact_release_html(
        "EXHIBIT 99.1",
        "(B)Crude oil and condensate volumes are from UAE and Bahrain operations. Natural gas volumes are from Bahrain operations; natural gas realized price represents contract price less partner's processing and distribution costs.",
        "Balance Sheets",
        "In millions of USD (Unaudited)",
        "2025 2026",
        "MAR JUN SEP DEC MAR JUN SEP DEC",
        "Current Assets",
        "Cash and Cash Equivalents 6,599 5,216 3,530 3,396 3,849 4,907",
    )


def _eog_toc_html() -> str:
    """Q3 FY2024 shape: TOC subtitle as headline, TOC entries as body."""
    return _contact_release_html(
        "EX-99.1",
        "2",
        "exh99-1110724.htm",
        "EXHIBIT 99.1",
        "Table of Contents",
        "Third Quarter 2024",
        "Supplemental Financial and Operating Data Page",
        "Income Statements 13",
        "Wellhead Volumes and Prices 14",
        "Balance Sheets 15",
        "Cash Flow Statements 16",
        "Non-GAAP Financial Measures 17",
        "Adjusted Net Income 18",
    )


def test_footnote_definition_headline_returns_none() -> None:
    assert extract_press_release_highlights(_eog_footnote_html()) is None


def test_toc_subtitle_headline_with_toc_body_returns_none() -> None:
    assert extract_press_release_highlights(_eog_toc_html()) is None


def test_exchange_prefixed_headline_is_preserved() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EXHIBIT 99.1",
            "(NYSE: ACME) ACME CORP REPORTS THIRD QUARTER 2026 RESULTS",
            "Revenue grew 12% to $1.2 billion in the quarter.",
            "Diluted EPS rose to $2.10 from $1.85 a year ago.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "(NYSE: ACME) ACME CORP REPORTS THIRD QUARTER 2026 RESULTS"
    )


def test_year_prefixed_headline_is_preserved() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EXHIBIT 99.1",
            "(2026) ACME CORP REPORTS THIRD QUARTER RESULTS",
            "Revenue grew 12% to $1.2 billion in the quarter.",
            "Diluted EPS rose to $2.10 from $1.85 a year ago.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "(2026) ACME CORP REPORTS THIRD QUARTER RESULTS"


def test_normal_release_with_numbered_lede_lines_is_preserved() -> None:
    # A real lede whose lines end in numbers/years must not trip the
    # TOC-body guard: the guard requires *every* body line to be a title +
    # page number, and prose lines break that pattern.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EXHIBIT 99.1",
            "ACME CORP REPORTS THIRD QUARTER 2026 RESULTS",
            "Revenue grew 12% to $1.2 billion in the quarter.",
            "Diluted EPS rose to $2.10 from $1.85 a year ago.",
            "Operating margin expanded 200 basis points.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "ACME CORP REPORTS THIRD QUARTER 2026 RESULTS"
