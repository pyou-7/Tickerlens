"""Batch 261 regression tests: Wingdings "n" bullets + gate S13
(bullet-superset + quote-tail truncation).

1. The "n" bullet (JPM's mangled bullet marker, same Wingdings glyph
   family as batch 175's "l"; CINF uses the same "n" as the " n "
   separator in its subsidiary masthead). A lone "n" plus a space is
   never prose, so "n " joins _BULLET_LEAD_RE and
   _FRAGMENTED_BULLET_RE on the same argument as "l ". JPM's exhibits
   are not in the blast cache, so this is verified by the predicate
   tests plus a zero-delta blast, not by a JPM exhibit. The space
   stays required: a line starting with the letter "n" glued to a
   word ("net income ...") is prose, not a bullet.
2. Gate S13 (scripts/batch261_repair.py): CINF Q1/Q2 rows whose stored
   text carries the Investment-section bullets + a long CEO-quote run,
   while live carries the Insurance + Investment bullets (a strict
   bullet superset) and only the first 3 quote lines (the designed
   batch-246/249 quote cap). The full-census simulation shows S13
   blesses exactly those 4 rows. The controls below pin the guards:
   the CINF Q3 lede shape (stored bullets lost), the BKR shape (a
   removed dateline is not quote-tail material), an added prose line,
   and a no-bullet-gain diff all still refuse.
3. Ranking decision (recorded, not code): lede-priority and
   density-first are both rejected by the cache-wide simulation in
   scripts/batch261_probe.py — lede-priority would fix the 2 Q3
   lede-stored CINF rows but break the 3 in-sync section-stored rows
   (net -1 on the census), and density-first flips 27 winners to
   thinner sections (ADBE Financial -> Business Segment; CRM quarter
   -> guidance). Count-based selection stays; the docstring in
   _extract_highlights_section now states the implemented rule.
"""
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch261_repair import (
    _is_quote_group_heading,
    _is_quote_run_line,
    sweep_gate_s13,
)
from tickerlens.data.filings import (
    _BULLET_LEAD_RE,
    _FRAGMENTED_BULLET_RE,
    _is_inline_bullet_start,
)


def test_wingdings_n_bullet_matches():
    assert _BULLET_LEAD_RE.match("n Reported revenues of $5.4 billion")
    assert _BULLET_LEAD_RE.match("n GAAP continuing EPS of $3.43")
    # The space is required: a line starting with the letter "n" glued
    # to a word is prose, not a bullet.
    assert not _BULLET_LEAD_RE.match("net income grew 5%")
    assert not _BULLET_LEAD_RE.match("n")
    assert not _BULLET_LEAD_RE.match("n/a")
    # The existing glyphs and the "l" bullet are untouched.
    assert _BULLET_LEAD_RE.match("•Record sales of $4.04 billion")
    assert _BULLET_LEAD_RE.match("- Record sales of $4.04 billion")
    assert _BULLET_LEAD_RE.match("l Reported revenues of $5.4 billion")
    assert not _BULLET_LEAD_RE.match("-$1,234")


def test_wingdings_n_inline_and_fragmented():
    assert _is_inline_bullet_start("n Third-quarter net income of $820 million")
    assert not _is_inline_bullet_start("net income of $820 million")
    assert _FRAGMENTED_BULLET_RE.match("n Net")
    assert not _FRAGMENTED_BULLET_RE.match("n Net income grew")


# Real CINF 2025-03-31 shape, values shortened: stored carries the
# Investment bullets + the full quote run (3 groups); live carries the
# Insurance + Investment bullets + the first quote group only (cap 3).
_STORED_CINF = (
    "Cincinnati Financial Reports First-Quarter 2025 Results\n"
    "•14% or $35 million increase in first-quarter 2025 pretax investment income, including a 24% increase in bond interest income.\n"
    "•Three-month increase of less than 1% in fair value of total investments at March 31, 2025.\n"
    "•$4.994 billion parent company cash and marketable securities at March 31, 2025, down 4% from year-end 2024.\n"
    "Prepared to Respond\n"
    "Stephen M. Spray, president and chief executive officer, commented: “The Cincinnati Insurance Companies were prepared for the unprecedented losses.\n"
    "“For 75 years, our capital and risk management strategies have consistently provided a strong foundation for long-term success.\n"
    "“Our first-quarter 2025 combined ratio of 113.3% included 25 points related to natural catastrophe losses.\n"
    "Keeping Our Focus\n"
    "“The confidence we have in our pricing capabilities and segmentation strategy allows us to keep our focus.\n"
    "“We were founded by four independent agents, and our goal remains to have the breadth of products and services agents need.\n"
    "“We again recorded double-digit growth in new business written premiums and strong renewal pricing.\n"
    "Committed to Long-Term Investment Strategy\n"
)
_LIVE_CINF = (
    "Cincinnati Financial Reports First-Quarter 2025 Results\n"
    "• 113.3% first-quarter 2025 property casualty combined ratio, increased from 93.6% for the first quarter of 2024.\n"
    "• 11% growth in first-quarter net written premiums, including price increases and premium growth initiatives.\n"
    "• $383 million first-quarter 2025 property casualty new business written premiums, up 11%.\n"
    "• $21 million first-quarter 2025 life insurance subsidiary net income, up $2 million compared with the first quarter of 2024.\n"
    "Investment and Balance Sheet Highlights\n"
    "• 14% or $35 million increase in first-quarter 2025 pretax investment income, including a 24% increase in bond interest income.\n"
    "• Three-month increase of less than 1% in fair value of total investments at March 31, 2025.\n"
    "• $4.994 billion parent company cash and marketable securities at March 31, 2025, down 4% from year-end 2024.\n"
    "Prepared to Respond\n"
    "Stephen M. Spray, president and chief executive officer, commented: “The Cincinnati Insurance Companies were prepared for the unprecedented losses.\n"
    "“For 75 years, our capital and risk management strategies have consistently provided a strong foundation for long-term success.\n"
    "“Our first-quarter 2025 combined ratio of 113.3% included 25 points related to natural catastrophe losses.\n"
)


def test_s13_blesses_cinf_superset_shape():
    assert sweep_gate_s13(_STORED_CINF, _LIVE_CINF) is None


def test_s13_refuses_lede_rows():
    # CINF Q3 shape: stored is the lede bullets, live is the sections
    # — a different section, not a superset.
    stored = (
        "Cincinnati Financial Reports Third-Quarter 2024 Results\n"
        "Cincinnati, October 24, 2024 – Cincinnati Financial Corporation (Nasdaq: CINF) today reported:\n"
        "•Third-quarter 2024 net income of $820 million, or $5.20 per share.\n"
        "•$88.32 book value per share at September 30, 2024, up $11.26 since year-end.\n"
    )
    assert sweep_gate_s13(stored, _LIVE_CINF) is not None


def test_s13_refuses_dateline_removal():
    # BKR shape: stored also drops its dateline, which is a 30-word
    # dated sentence — not a quote-group heading.
    stored = (
        "Baker Hughes Company Announces Fourth-Quarter and Full-Year 2024 Results\n"
        "•Orders of $28.2 billion, including $13.0 billion of IET orders.\n"
        "•Revenue of $27.8 billion, up 9% year-over-year.\n"
        "HOUSTON & LONDON (January 30, 2025) – Baker Hughes Company (Nasdaq: BKR) (\"Baker Hughes\" or the \"Company\") announced results today for the fourth-quarter and full-year 2024.\n"
        "\"2024 proved to be a momentous year for Baker Hughes.\n"
        "\"IET booked $3.8 billion of orders in the fourth quarter.\n"
        "Baker Hughes Company News Release\n"
    )
    live = (
        "Baker Hughes Company Announces Fourth-Quarter and Full-Year 2024 Results\n"
        "• Orders of $7.5 billion, including $3.8 billion of IET orders.\n"
        "• Revenue of $7.4 billion, up 8% year-over-year.\n"
        "Full-year highlights\n"
        "• Orders of $28.2 billion, including $13.0 billion of IET orders.\n"
        "• Revenue of $27.8 billion, up 9% year-over-year.\n"
    )
    assert sweep_gate_s13(stored, live) is not None


def test_s13_refuses_added_prose_and_no_gain():
    # Live adds a prose line that is neither a financial bullet nor a
    # heading introducing bullets.
    live_prose = _LIVE_CINF + "We delivered strong results across the business.\n"
    assert sweep_gate_s13(_STORED_CINF, live_prose) is not None
    # No bullet gain: live drops the quote tail but adds no bullets.
    live_no_gain = (
        "Cincinnati Financial Reports First-Quarter 2025 Results\n"
        "• 14% or $35 million increase in first-quarter 2025 pretax investment income, including a 24% increase in bond interest income.\n"
        "• Three-month increase of less than 1% in fair value of total investments at March 31, 2025.\n"
        "• $4.994 billion parent company cash and marketable securities at March 31, 2025, down 4% from year-end 2024.\n"
        "Prepared to Respond\n"
        "Stephen M. Spray, president and chief executive officer, commented: “The Cincinnati Insurance Companies were prepared for the unprecedented losses.\n"
    )
    assert sweep_gate_s13(_STORED_CINF, live_no_gain) is not None


def test_quote_run_lines():
    # Wrapped continuations open with a quote mark; the attribution
    # opener carries a quote verb even when the quote never closes on
    # its own line (the single-line predicate misses both shapes).
    assert _is_quote_run_line(
        "“The confidence we have in our pricing capabilities allows us to keep our focus."
    )
    assert _is_quote_run_line(
        "Stephen M. Spray, president and chief executive officer, commented: “The Cincinnati Insurance Companies were prepared."
    )
    assert _is_quote_run_line('"2024 proved to be a momentous year for Baker Hughes.')
    # Plain prose and a dateline with quoted terms are not quote runs.
    assert not _is_quote_run_line("We delivered strong results across the business.")
    assert not _is_quote_run_line(
        "HOUSTON & LONDON (January 30, 2025) – Baker Hughes Company (Nasdaq: BKR) "
        '("Baker Hughes" or the "Company") announced results today.'
    )
    assert _is_quote_group_heading("Keeping Our Focus")
    assert _is_quote_group_heading("Committed to Long-Term Investment Strategy")
    assert not _is_quote_group_heading(
        "HOUSTON & LONDON (January 30, 2025) – Baker Hughes Company announced results today."
    )
