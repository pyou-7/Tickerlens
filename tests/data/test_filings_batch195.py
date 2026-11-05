"""Batch 195: bullet content gated by headings is served, not cut.

APD Q1 FY2025 (2024-12-31) served only its headline + 1 dividend bullet
(310 chars) although the release opens with its two top financial
bullets and a Guidance bullet pair. Two heading shapes gated the bullets:

  - the leading-bullet block broke on its first line, the colon-ended
    list intro "Q1 FY25 (comparisons versus prior year):" — the lede
    loop already skips such headings (batch 177) but the leading-bullet
    block never did, so the two financial bullets under it never
    competed;
  - the Highlights section collector broke on the bare "Guidance"
    sub-heading via _is_lede_table_heading — the same predicate that
    ends a section at AppLovin's "First Quarter 2026 Financial Guidance
    Summary" table title. A guidance heading that introduces bullets is
    a sub-heading, not a table title, so the break now fires only when
    the next content line is not a bullet (same look-ahead in the
    leading-bullet block's continuation branch). The heading itself is
    collected as a label line — the stored APD row carries it as a
    non-defect line, and ADBE's served output already keeps section
    headings mid-section.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _leading_bullet_block,
    _next_content_line_is_bullet,
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


# --- unit: the bullet look-ahead -------------------------------------------

def test_next_content_line_is_bullet():
    assert _next_content_line_is_bullet(
        ["Guidance", "•Maintain fiscal 2025 guidance of $12.70 to $13.00."], 0
    )
    # A page-number admin line between the heading and its bullets is skipped.
    assert _next_content_line_is_bullet(["Guidance", "2", "•Maintain guidance."], 0)
    # A "·"-led bullet counts (batch 138/139 flattened bullets).
    assert _next_content_line_is_bullet(["Guidance", "·Maintain guidance."], 0)
    # A table row after the heading is a table, not bullets.
    assert not _next_content_line_is_bullet(
        ["First Quarter 2026 Financial Guidance Summary", "Revenue $1.0B $1.1B"], 0
    )
    # Nothing after the heading: no bullets.
    assert not _next_content_line_is_bullet(["Guidance"], 0)
    # Prose after the heading is not a bullet.
    assert not _next_content_line_is_bullet(
        ["Guidance", "The company expects a strong year ahead."], 0
    )


# --- unit: the leading-bullet intro skip ------------------------------------

def test_leading_bullet_block_skips_colon_intro():
    block = _leading_bullet_block(
        [
            "Q1 FY25 (comparisons versus prior year):",
            "•GAAP EPS of $2.77, up one percent; GAAP net income of $650 million, up five percent; and GAAP net income margin of 22.2 percent, up 150 basis points.",
            "•Adjusted EPS of $2.86, up one percent; adjusted EBITDA of $1.2 billion, up one percent; and adjusted EBITDA margin of 40.6 percent, up 140 basis points.",
            "Fiscal 2025 and Recent Highlights",
            "•Increased quarterly dividend to $1.79 per share.",
        ]
    )
    assert block is not None
    assert len(block) == 2
    assert "GAAP EPS of $2.77" in block[0]
    assert "Adjusted EPS of $2.86" in block[1]
    # The intro line itself is a heading, never content.
    assert not any("comparisons versus prior year" in ln for ln in block)


def test_leading_bullet_block_intro_without_bullets_is_none():
    assert (
        _leading_bullet_block(
            [
                "Summary:",
                "First quarter sales of $2.9 billion were down two percent from the prior year as lower volumes and unfavorable currency were partially offset by higher pricing across the portfolio.",
            ]
        )
        is None
    )


# --- end-to-end: the APD shape (leading intro + Guidance sub-heading) ------

APD_BODY = [
    "Acme Reports Fiscal 2025 First Quarter Results",
    "Q1 FY25 (comparisons versus prior year):",
    "•GAAP EPS of $2.77, up one percent; GAAP net income of $650 million, up five percent; and GAAP net income margin of 22.2 percent, up 150 basis points, reflecting higher pricing net of power and fuel costs across the portfolio.",
    "•Adjusted EPS of $2.86, up one percent; adjusted EBITDA of $1.2 billion, up one percent; and adjusted EBITDA margin of 40.6 percent, up 140 basis points, primarily due to favorable business mix and higher pricing.",
    "Fiscal 2025 and Recent Highlights",
    "•The company appointed Jane Smith as Chief Financial Officer, effective immediately, bringing more than twenty years of experience in finance and operations across the industrial sector and a track record of driving productivity.",
    "NEW YORK, February 6, 2025 - Acme Corp today reported first quarter fiscal 2025 results, with strong performance across every segment and continued progress on productivity and pricing initiatives throughout the quarter.",
]


def test_leading_intro_bullets_compete():
    # The leading block (2 financial bullets) beats the Highlights
    # section (1 figure-free bullet) on financial count, so the
    # quarter's top numbers are served — on old code the intro broke
    # the block and only the section bullet was served.
    out = _extract(APD_BODY)
    assert out is not None
    assert "GAAP EPS of $2.77" in out
    assert "Adjusted EPS of $2.86" in out
    assert "comparisons versus prior year" not in out
    assert "Jane Smith as Chief Financial Officer" not in out


def test_guidance_subheading_keeps_section_bullets():
    # The APD shape with the Highlights section winning: the leading
    # financial bullets are gone, the section carries the dividend and
    # Guidance bullets, and the Guidance bullets must survive in it.
    body = [
        "Acme Reports Fiscal 2025 First Quarter Results",
        "Fiscal 2025 and Recent Highlights",
        "•Increased quarterly dividend on the common stock to $1.79 per share, marking the 43rd consecutive year of dividend increases; the company expects to return approximately $1.6 billion to shareholders in 2025.",
        "Guidance",
        "•Maintain fiscal 2025 full-year adjusted EPS guidance of $12.70 to $13.00; fiscal 2025 second quarter adjusted EPS guidance of $2.75 to $2.85.",
        "•Expect fiscal year 2025 capital expenditures in the range of $4.5 billion to $5.0 billion.",
        "NEW YORK, February 6, 2025 - Acme Corp today reported first quarter fiscal 2025 results, with strong performance across every segment and continued progress on productivity and pricing initiatives throughout the quarter.",
        "Commenting on the results, Chief Executive Officer Jane Smith said, “We delivered a strong quarter across every segment of the business, with momentum building into the second half of the year as new products gain share.”",
    ]
    out = _extract(body)
    assert out is not None
    assert "Increased quarterly dividend" in out
    assert "Guidance" in out
    assert "Maintain fiscal 2025 full-year adjusted EPS guidance" in out
    assert "Expect fiscal year 2025 capital expenditures" in out


def test_guidance_table_heading_still_ends_section():
    # AppLovin shape: the guidance-summary heading is followed by a
    # table row, not bullets — the section still ends there.
    out = _extract(
        [
            "Acme Reports First Quarter 2026 Results",
            "First Quarter Highlights",
            "•Net income of $500 million, up 10% year over year, on revenue of $2.1 billion, an increase of 8% from the prior year period, driven by higher volumes and favorable currency and lower costs from productivity.",
            "•Revenue of $2.1 billion increased 8%, reflecting four percent higher volumes, four percent favorable currency, and two percent higher pricing across the portfolio and new products.",
            "•Adjusted EPS of $1.20, up 12% year over year, driven by higher volumes, favorable currency, and lower costs from productivity and lower depreciation across the business.",
            "First Quarter 2026 Financial Guidance Summary",
            "Revenue $1.0 billion $1.1 billion",
            "Operating Income $100 million $120 million",
            "Commenting on the results, Chief Executive Officer Jane Smith said, “We delivered a strong quarter across every segment of the business, with momentum building into the second half of the year as new products gain share.”",
        ]
    )
    assert out is not None
    assert "Net income of $500 million" in out
    assert "Financial Guidance Summary" not in out
    assert "Revenue $1.0 billion $1.1 billion" not in out


def test_leading_block_guidance_subheading_keeps_bullets():
    # No Highlights heading at all: the leading block runs through a
    # bare "Guidance" sub-heading into the guidance bullets.
    out = _extract(
        [
            "Acme Reports First Quarter 2026 Results",
            "•GAAP EPS of $2.77, up one percent; GAAP net income of $650 million, up five percent; and GAAP net income margin of 22.2 percent, up 150 basis points, reflecting higher pricing net of power and fuel costs across the portfolio.",
            "•Adjusted EPS of $2.86, up one percent; adjusted EBITDA of $1.2 billion, up one percent; and adjusted EBITDA margin of 40.6 percent, up 140 basis points, primarily due to favorable business mix and higher pricing.",
            "Guidance",
            "•Maintain fiscal 2026 full-year adjusted EPS guidance of $12.70 to $13.00; fiscal 2026 second quarter adjusted EPS guidance of $2.75 to $2.85, reflecting continued momentum across the portfolio.",
            "•Expect fiscal year 2026 capital expenditures in the range of $4.5 billion to $5.0 billion, including investments in new capacity and productivity initiatives.",
        ]
    )
    assert out is not None
    assert "GAAP EPS of $2.77" in out
    assert "Guidance" in out
    assert "Maintain fiscal 2026 full-year adjusted EPS guidance" in out
    assert "Expect fiscal year 2026 capital expenditures" in out


# --- real exhibit: APD 2024-12-31 -------------------------------------------

def test_apd_q1_fy2025_serves_guidance_bullets():
    out = _live("APD_2024-12-31")
    assert len(out) > 2000  # was 310: headline + 1 dividend bullet only
    assert "Increased quarterly dividend" in out
    assert "Guidance" in out
    assert "Maintain fiscal 2025 full-year adjusted EPS guidance" in out
    assert "Expect fiscal year 2025 capital expenditures" in out
    assert "Fiscal 2025 First Quarter Consolidated Results" in out
    assert "First quarter sales of $2.9 billion were down two percent" in out
    # Defect lines the new extractor drops.
    assert "-more-" not in out
    assert "#Earnings per share is calculated" not in out
    assert "*Certain results in this release" not in out
