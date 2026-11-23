"""Batch 197: bullet-run splitting for ●/○ separators, and a bullet
exemption for the page-line guard — Instacart and Booking highlights
rescued from None.

The batch-125 splitter only split " • " runs. Instacart's shareholder
letter, Booking's release, and Affirm's letter join their bullet runs
with " ● " (Instacart also " ○ " for sub-bullets), so the split never
fired: all 10 cached CART quarters, all 7 BKNG quarters, and AFRM
2024-12-31 extracted None — their "Financial Highlights" bullets sit
mid-line in a mega-line no anchor ever sees. The downstream glyph set
already treats ●/○ as bullets (_BULLET_LEAD_RE, the lone-marker test),
so the fix only extends the batch-125 mechanism to the glyphs the
documents actually use.

Six CART quarters needed a second fix: their sections extract fine
once split, but the batch-105 page-line guard (no headline + a line
over 1000 chars) discards the whole section because the section's
narrative paragraphs are flattened mega-lines too (1200–2500 chars).
A bullet-led line now exempts the paragraph — a page-line dump has no
bullet lines, and the exhibits the guard still protects (EOG's
image-only packets, Ford's early risk-factor releases, COIN's decks)
do not move in the blast.

Pin is behavioral: on the pre-fix code (blast base) CART_2024-09-30,
CART_2024-12-31, and BKNG_2025-06-30 all extract None.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _split_bullet_runs,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _live(ticker_period: str) -> str | None:
    html = open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ).read()
    return extract_press_release_highlights(html)


# --- unit: ● and ○ runs split like • runs ----------------------------------


def test_black_circle_run_splits():
    mega = (
        "Q3'24 Financial Update Q3'24 Financial Highlights ● GTV of $8,303 "
        "million, up 11% year-over-year. ● Orders of 72.9 million, up 10% "
        "year-over-year. ● Total revenue of $852 million, up 12% "
        "year-over-year, representing 10.3% of GTV. ● Transaction revenue "
        "of $606 million, up 12% year-over-year, representing 7.3% of GTV. "
        "● Advertising & other revenue of $246 million, up 11% "
        "year-over-year, representing 3.0% of GTV."
    )
    assert len(mega) > 300
    pieces = _split_bullet_runs([mega])
    assert pieces[0] == "Q3'24 Financial Update Q3'24 Financial Highlights"
    assert pieces[1] == "• GTV of $8,303 million, up 11% year-over-year."
    assert pieces[2] == "• Orders of 72.9 million, up 10% year-over-year."
    assert pieces[3].startswith("• Total revenue of $852 million")


def test_white_circle_run_splits():
    mega = (
        "Additional Business Updates Consumers We're constantly investing "
        "in ways to make our service more personalized and interactive for "
        "our customers, while also helping them find more ways to save on "
        "Instacart. ○ Launched new capabilities, including gamified quests, "
        "location-based coupons, and aisle-aware advertising formats, "
        "driving new savings for customers and opportunities for brands "
        "and retailers to engage with consumers. ○ Launched carts at "
        "regional favorites Bowman's Market and Soelberg's Market in Utah, "
        "Queen's Price Chopper in Kansas, and added more locations."
    )
    assert len(mega) > 300
    pieces = _split_bullet_runs([mega])
    assert pieces[0].startswith("Additional Business Updates")
    assert pieces[1].startswith("• Launched new capabilities")
    assert pieces[2].startswith("• Launched carts at regional favorites")


def test_short_and_single_separator_lines_untouched():
    assert _split_bullet_runs(["Revenue up 5% ● margins steady"]) == [
        "Revenue up 5% ● margins steady"
    ]
    assert _split_bullet_runs(["GTV up 11% ○ orders up 10%"]) == [
        "GTV up 11% ○ orders up 10%"
    ]


# --- live: CART's Financial Highlights bullets are served -------------------


def test_cart_2024_q3_financial_highlights_served():
    out = _live("CART_2024-09-30")
    assert out is not None
    assert "GTV of $8,303 million, up 11% year-over-year" in out
    assert "Orders of 72.9 million, up 10% year-over-year" in out
    assert "Adjusted EBITDA of $227 million, up 39% year-over-year" in out
    assert "Dear Shareholders" not in out  # salutation is never content


def test_cart_2024_q4_quarter_bullets_served_not_full_year():
    # Batch 244 supersedes the batch-197 pin: the row is a quarter,
    # so the quarter's Highlights section wins over the full-year one
    # (quarter-scope beats full-year scope when it financially
    # qualifies). Batch 197 pinned the old 12-line window, which
    # straddled the FY/Q4 boundary and served the FY figures
    # ($33,461M GTV, $885M EBITDA) on a quarterly row; the quarter's
    # own figures ($8,645M GTV, $252M EBITDA) are the right ones.
    out = _live("CART_2024-12-31")
    assert out is not None
    assert "GTV of $8,645 million, up 10% year-over-year" in out  # Q4
    assert "Orders of 77.5 million, up 11% year-over-year" in out  # Q4
    assert "Adjusted EBITDA of $252 million, up 27% year-over-year" in out  # Q4
    assert "GTV of $33,461 million, up 10% year-over-year" not in out  # FY24
    assert "Adjusted EBITDA of $885 million, up 38% year-over-year" not in out  # FY24
    assert "Dear Shareholders" not in out  # salutation is never content


def test_cart_2025_q2_bullets_served():
    out = _live("CART_2025-06-30")
    assert out is not None
    assert "GTV of $9,081 million, up 11% year-over-year" in out
    assert "GAAP net income of $116 million, up 92% year-over-year" in out


# --- live: BKNG's headline and room-nights bullets are served --------------


def test_bkng_2025_q2_headline_and_bullets_served():
    out = _live("BKNG_2025-06-30")
    assert out is not None
    assert out.startswith(
        "Booking Holdings Reports Second Quarter 2025 Financial Results"
    )
    assert "Room nights grew 8% compared to the second quarter of 2024" in out
    assert "Gross bookings grew 13% compared to the second quarter of 2024" in out
    assert "Revenue grew 16% compared to the second quarter of 2024" in out


# --- live: the ●-split only reflows already-served text elsewhere ----------


def test_afrm_scorecard_bullets_split_out():
    out = _live("AFRM_2023-12-31")
    assert out is not None
    assert "• GMV grew 32% year over year to $7.5 billion" in out
    assert "• Revenue grew 48% year over year to $591 million" in out


def test_coin_deck_bullets_split_out():
    out = _live("COIN_2026-03-31")
    assert out is not None
    assert "• Global" in out
    assert "• Efficient" in out
    assert "• Programmable" in out


# --- live: the guard still protects the honestly-blank exhibits ------------


def test_eog_still_none():
    assert _live("EOG_2024-12-31") is None  # image-only exhibit


def test_ford_early_release_still_none():
    # Ford's 2023-12-31 exhibit has no Highlights section and its
    # risk-factor bullets sit past the lede budget; the bullet exemption
    # to the page-line guard must not rescue it.
    assert _live("F_2023-12-31") is None
