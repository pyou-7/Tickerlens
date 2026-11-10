"""Batch 229: the "Financial Targets" guidance section — Adobe heads its
guidance section "Financial Targets" (all 12 cached quarters), and the
old code could not see it in either extractor:

  - Highlights: the section collector ran past the heading into the
    targets table, serving guidance rows as highlights in 6 quarters
    (ADBE 2024-03-01 / 2024-05-31 / 2024-08-30 / 2025-05-30 /
    2025-08-29 / 2026-02-27). The heading matches no table shape — no
    outlook/guidance word, so _is_lede_table_heading never fires.
  - Guidance: the guidance extractor returned None for every ADBE
    quarter — no anchor — so ADBE's management_guidance was NULL for
    all 8 stored rows.

The fix: "financial targets" joins _GUIDANCE_HEADING_RE, and the
Highlights section collector breaks at a guidance heading when the next
content line is not a bullet (the batch-195 gate, so a bare "Guidance"
sub-heading that introduces bullets — Air Products — is still kept as
a label line). The blast over 1,699 exhibits found 13 highlights
diffs and 12 guidance diffs, all verified: ADBE x6 (targets table
dropped, real bullets kept — the first section now wins outright),
COR x1 (the "2026 Guidance Fiscal 2025 Actuals" table header breaks
the section, it fails qualification with no bullets, and the lede
serving the real headline bullets wins), EQIX x2 ("Business Outlook"
prose dropped), META x4 ("CFO Outlook Commentary" prose dropped);
guidance ADBE x12, None -> the full targets text.

Live pins run the extractors against the real cached exhibits; the
unit pins cover the new regex alternative and the section-collector
break (plus its bullet gate) directly.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _GUIDANCE_HEADING_RE,
    extract_management_guidance,
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


def _live_guidance(ticker_period: str) -> str | None:
    html = open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ).read()
    return extract_management_guidance(html)


def _extract(body_lines):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


# --- unit pins: the new regex alternative ------------------------------


def test_financial_targets_matches_guidance_heading():
    assert _GUIDANCE_HEADING_RE.match("Financial Targets")
    assert _GUIDANCE_HEADING_RE.match("Financial Targets:")
    assert _GUIDANCE_HEADING_RE.match("FINANCIAL TARGETS")


def test_targets_heading_non_matches():
    # A headline that mentions targets is not a heading (anchored on the
    # lead words), nor is prose that merely mentions targets, nor a bare
    # "Targets" with no "Financial" lead.
    assert not _GUIDANCE_HEADING_RE.match(
        "Adobe Reports Record Revenue in Q2 and Raises FY25 Revenue and EPS Targets"
    )
    assert not _GUIDANCE_HEADING_RE.match("We raised our targets for the year")
    assert not _GUIDANCE_HEADING_RE.match("Targets")
    assert not _GUIDANCE_HEADING_RE.match("Financial Results")
    assert not _GUIDANCE_HEADING_RE.match("Total revenue $5.25 billion")


# --- unit pins: the section-collector break ----------------------------


def test_financial_targets_ends_highlights_section():
    # The ADBE shape: Financial Highlights bullets, then the Business
    # Segment Highlights sub-section, then "Financial Targets" + intro
    # + targets table rows. The section ends at the heading; the table
    # never serves.
    out = _extract(
        [
            "Acme Reports Record Revenue in Q1 Fiscal 2024",
            "First Quarter Fiscal Year 2024 Financial Highlights",
            "•Acme achieved revenue of $5.18 billion in its first quarter of fiscal year 2024, which represents 11 percent year-over-year growth or 12 percent in constant currency.",
            "•GAAP operating income in the first quarter was $907 million and non-GAAP operating income was $2.47 billion.",
            "•Cash flows from operations were $1.17 billion.",
            "First Quarter Fiscal Year 2024 Business Segment Highlights",
            "•Digital Media segment revenue was $3.82 billion, which represents 12 percent year-over-year growth or 13 percent in constant currency.",
            "•Net new Digital Media Annualized Recurring Revenue was $432 million, exiting the quarter with Digital Media ARR of $15.75 billion.",
            "Financial Targets",
            "Acme is providing second quarter targets, which factor in current expectations for the macroeconomic and foreign exchange environments.",
            "Total revenue $5.25 billion to $5.30 billion",
            "Digital Media net new ARR ~$440 million",
            "Digital Media segment revenue $3.87 billion to $3.90 billion",
            "Tax rate GAAP: ~18.5%",
        ]
    )
    assert out is not None
    assert "Acme achieved revenue of $5.18 billion" in out
    assert "Digital Media segment revenue was $3.82 billion" in out
    assert "Financial Targets" not in out
    assert "Total revenue $5.25 billion" not in out
    assert "Digital Media net new ARR ~$440 million" not in out


def test_targets_heading_with_bullets_stays():
    # The batch-195 gate applies to the new heading too: a "Financial
    # Targets" heading that introduces bullets is a sub-heading, not a
    # table title, so the heading and its bullets stay in the section.
    out = _extract(
        [
            "Acme Reports First Quarter 2026 Results",
            "First Quarter Highlights",
            "•Net income of $500 million, up 10% year over year, on revenue of $2.1 billion, an increase of 8% from the prior year period.",
            "Financial Targets",
            "•Total revenue expected in the range of $5.25 billion to $5.30 billion for the second quarter.",
            "•Digital Media net new ARR expected of approximately $440 million.",
            "NEW YORK, February 6, 2026 - Acme Corp today reported first quarter fiscal 2026 results, with strong performance across every segment and continued progress on productivity and pricing initiatives throughout the quarter.",
            "Commenting on the results, Chief Executive Officer Jane Smith said, “We delivered a strong quarter across every segment of the business, with momentum building into the second half of the year as new products gain share.”",
        ]
    )
    assert out is not None
    assert "Net income of $500 million" in out
    assert "Financial Targets" in out
    assert "Total revenue expected in the range of $5.25 billion" in out


# --- live pins: ADBE highlights ------------------------------------------


def test_adbe_2024_03_01_targets_table_gone():
    out = _live("ADBE_2024-03-01")
    assert "Adobe achieved revenue of $5.18 billion" in out
    assert "GAAP operating income in the first quarter was $907 million" in out
    assert "Cash flows from operations were $1.17 billion" in out
    assert "Digital Media segment revenue was $3.82 billion" in out
    assert "Digital Experience segment revenue was $1.29 billion" in out
    assert "Financial Targets" not in out
    assert "Total revenue $5.25 billion to $5.30 billion" not in out
    assert "Digital Media net new ARR ~$440 million" not in out
    assert "Tax rate GAAP: ~18.5%" not in out


def test_adbe_2025_05_30_targets_table_gone():
    out = _live("ADBE_2025-05-30")
    assert "Adobe achieved record revenue of $5.87 billion" in out
    assert "Business Professionals and Consumers Group subscription revenue was $1.60 billion" in out
    assert "Creative and Marketing Professionals Group subscription revenue was $4.02 billion" in out
    assert "Financial Targets" not in out
    assert "Total revenue $5.875 billion to $5.925 billion" not in out
    assert "Earnings per share GAAP: $4.00 to $4.05" not in out


def test_adbe_2026_02_27_targets_prose_gone():
    out = _live("ADBE_2026-02-27")
    assert "Creative & Marketing Professionals subscription revenue was $4.39 billion" in out
    assert "Financial Targets" not in out
    assert "Semrush" not in out


# --- live pins: the blanket guidance-heading break -----------------------


def test_eqix_business_outlook_prose_dropped():
    out = _live("EQIX_2024-06-30")
    assert "export heat from its newest International Business Exchange" in out
    assert "Business Outlook" not in out
    assert "For the third quarter of 2024, the company expects revenues" not in out
    assert "Adjusted EBITDA is expected to range between $1.029 and $1.049 billion" not in out


def test_meta_cfo_outlook_commentary_dropped():
    out = _live("META_2024-03-31")
    assert "Headcount was 69,329 as of March 31, 2024" in out
    assert "CFO Outlook Commentary" not in out
    assert "We expect second quarter 2024 total revenue" not in out
    assert "We expect full-year 2024 total expenses" not in out


def test_cor_guidance_table_section_rejected_lede_wins():
    # The "2026 Guidance Fiscal 2025 Actuals" table header breaks the
    # "Recent Company Highlights" section; with no bullets it fails
    # qualification, so the lede — the real headline bullets — wins.
    out = _live("COR_2025-09-30")
    assert "Revenue of $83.7 Billion for the Fourth Quarter" in out
    assert "Revenue of $321.3 Billion for Fiscal Year 2025" in out
    assert "Company increases its quarterly dividend by 9 percent" in out
    assert "2026 Guidance Fiscal 2025 Actuals" not in out
    assert "Revenue 5% to 7% growth $321.3B" not in out
    assert "Fiscal Year 2026 Expectations" not in out


# --- live pins: ADBE guidance now extracts ------------------------------


def test_adbe_guidance_2023_12_01():
    gd = _live_guidance("ADBE_2023-12-01")
    assert gd is not None  # was None: no anchor
    assert "Financial Targets" in gd
    assert "Total revenue $21.30 billion to $21.50 billion" in gd
    assert "Non-GAAP: $17.60 to $18.00" in gd
    assert "Total revenue $5.10 billion to $5.15 billion" in gd


def test_adbe_guidance_2024_03_01():
    gd = _live_guidance("ADBE_2024-03-01")
    assert gd is not None  # was None: no anchor
    assert "Financial Targets" in gd
    assert "Total revenue $5.25 billion to $5.30 billion" in gd
    assert "Digital Media net new ARR ~$440 million" in gd
    assert "GAAP: $3.35 to $3.40" in gd


def test_adbe_guidance_2024_11_29():
    gd = _live_guidance("ADBE_2024-11-29")
    assert gd is not None  # was None: no anchor
    assert "Total revenue $23.30 billion to $23.55 billion" in gd
    assert "GAAP: $15.80 to $16.10" in gd
    assert "Total revenue $5.63 billion to $5.68 billion" in gd


# --- guard: the batch-195 bullet gate still holds -------------------------


def test_apd_guidance_bullets_still_served():
    # The Air Products "Guidance" sub-heading introducing bullets must
    # survive the new section-collector break (same bullet gate).
    out = _live("APD_2024-12-31")
    assert "Increased quarterly dividend" in out
    assert "Guidance" in out
    assert "Maintain fiscal 2025 full-year adjusted EPS guidance" in out
    assert "Expect fiscal year 2025 capital expenditures" in out
