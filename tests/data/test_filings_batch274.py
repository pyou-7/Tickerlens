"""Batch 274 regression tests.

Ford's exhibits are flattened page images: each page is one mega-line
prefixed with its bare page number ("2 Total Company Highlights ...",
"3 Business Segment Highlights ...", "2 The company reported ...").
The leading-bullet block's item-close rule treated a terminated
continuation line as the end of the bullet item, so the block ended
one page early and stranded the next page — the segment table, the
segment narrative, or the outlook page, each carrying figures the
stored rows hold (F x6 SKIP-loss). The fix has three pieces, all in
`_leading_bullet_block`:

1. Page-marker continuation (`_is_page_marker_page`): when the
   item-close would fire but the next line is the next page of the
   same flattened body — a mega-line before it, a page-number +
   capital-letter opener after it, carrying figures itself or in
   the bullets it introduces — the close is suppressed and the block
   keeps collecting the page.
2. Cautionary-heading break: a standalone "Cautionary Note on
   Forward-Looking Statements" page ends the block. The page matches
   the numbered-footnote-definition shape, so the footnote-definition
   skip used to swallow it transparently and the block ran on into
   the safe-harbor risk bullets (F 2026-09-30). The break is the
   batch-214 final cut applied at collection.
3. Conference-call break: a "Conference Call Details" page ends the
   block — call logistics, not results. Without it the block ran
   through the call page and the 9000-char cap truncated the card
   mid-sentence (F 2024-06-30, F 2024-09-30).

Blast radius (full 1,699-exhibit cache): exactly 9 rows move, all
Ford — the 6 SKIP-loss rows plus the 4 previously in-sync Ford rows
gaining their segment tables, minus F 2025-03-31 (already serving
its table). No other ticker moves.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_page_marker_page,
    _leading_bullet_block,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _mega(text: str, n: int = 1100) -> str:
    """A terminated mega-line: `text` repeated to at least n chars."""
    out = text
    while len(out) < n:
        out += " " + text
    return out


def _lines(*ls: str) -> list[str]:
    return list(ls)


# --- _is_page_marker_page -----------------------------------------------

PAGE_PREV = _mega("Revenue was $48.2 billion, an increase from a year ago.")
TABLE_NEXT = (
    "2 Total Company Highlights Fourth Quarter Full Year 2023 2024 Change "
    "Wholesale Units (000) 1,152 1,188 3 % Revenue ($B) 46.0 48.2 5 % "
    + "x" * 900
)
SEGMENT_NEXT = (
    "3 Business Segment Highlights Fourth Quarter Full Year 2023 2024 Change "
    "Ford Blue Segment Wholesales (000) 758 774 2 % Revenue ($B) $ 26.2 $ 27.3 4 % "
    + "x" * 900
)


def test_page_marker_page_table_and_segment():
    lines = _lines(PAGE_PREV, TABLE_NEXT)
    assert _is_page_marker_page(lines, 0) is True
    lines = _lines(PAGE_PREV, SEGMENT_NEXT)
    assert _is_page_marker_page(lines, 0) is True


def test_page_marker_page_short_outlook_opener_with_figure_bullets():
    # F 2025-09-30: the outlook opener is only 335 chars and carries
    # its figures in the bullets below it, not in the opener itself.
    opener = (
        "3 Full-Year 2025 Outlook Ford's underlying business is performing "
        "at the high end of the guidance range previously outlined in February, "
        "while absorbing a $1.0 billion net tariff headwind. Additionally, the "
        "company expects a headwind of $1.0 billion or less."
    )
    bullet = "\u2022 A 2025 adjusted EBIT headwind of $1.5 billion to $2 billion."
    lines = _lines(PAGE_PREV, opener, bullet)
    assert _is_page_marker_page(lines, 0) is True


def test_page_marker_page_short_outlook_opener_with_figures():
    # F 2026-06-30's opener is 162 chars with no $ in it; the segment
    # guidance bullets that follow carry the figures.
    opener = (
        "4 Full-Year 2026 Outlook Building on strong first-half results, "
        "the company is raising full-year 2026 guidance. Ford now expects:"
    )
    bullet = "\u2022 Ford Blue EBIT of $5.0 billion to $5.5 billion."
    lines = _lines(PAGE_PREV, opener, bullet)
    assert _is_page_marker_page(lines, 0) is True


def test_page_marker_page_rejects_short_prev():
    lines = _lines("Revenue was $48.2 billion.", TABLE_NEXT)
    assert _is_page_marker_page(lines, 0) is False


def test_page_marker_page_rejects_data_row():
    lines = _lines(PAGE_PREV, "9 4 971 193" + " 1" * 600)
    assert _is_page_marker_page(lines, 0) is False


def test_page_marker_page_rejects_lowercase_wrap():
    lines = _lines(PAGE_PREV, "3 percentage points (from 51% in Q3 2022 to 54% in Q3 2023), " + "x" * 900)
    assert _is_page_marker_page(lines, 0) is False


def test_page_marker_page_rejects_contacts_page():
    # F 2026-03-31: the page after the outlook page is contacts — no
    # figures in it, and the footnote bullet behind it is figure-free —
    # so the block must end at the outlook page instead of running on
    # into the footnotes and truncating at the 9000-char cap.
    contacts = (
        "5 Contacts Media David Tovar 1.773.682.7954 dtovar9@ford.com "
        "Equity Investment Community Lynn Antipas Tyson 1.203.616.5689 "
        "ltyson4@ford.com"
    )
    footnote = "\u2022 See tables later in this release for the nature and amount of special items."
    lines = _lines(PAGE_PREV, contacts, footnote)
    assert _is_page_marker_page(lines, 0) is False


def test_page_marker_page_rejects_period_fragment():
    # "3 Months Ended" is a period fragment, not a page: the marker
    # matches and it opens with a capital, but there is no figure in
    # it and no figure-carrying bullet follows it. (When a $-bullet
    # does follow, the predicate returns True — harmless, because the
    # period-header break ends the block on the next iteration.)
    lines = _lines(PAGE_PREV, "3 Months Ended", "\u2022 Revenue grew during the quarter.")
    assert _is_page_marker_page(lines, 0) is False


# --- _leading_bullet_block, synthetic ------------------------------------

BULLETS = (
    "\u2022 Fourth-quarter revenue increased to $48.2 billion; net income of $1.8 billion.",
    "\u2022 Full-year revenue increased to $185 billion; net income of $5.9 billion.",
)


def test_block_continues_onto_table_page():
    # A realistic dense table page (~1600 chars, figure-dense like the
    # real Ford Total Company line) is collected, not skipped as a
    # footnote definition.
    row = (
        "Wholesale Units (000) 1,152 1,188 3 % Revenue ($B) 46.0 48.2 5 % "
        "Net Income ($B) 1.8 2.4 33 % Adjusted EBIT ($B) 2.5 2.9 16 % "
    )
    table = (
        "2 Total Company Highlights Fourth Quarter Full Year 2023 2024 Change "
        + _mega(row, 1500)
    )
    prev = _mega("The company posted fourth-quarter revenue of $48.2 billion.")
    block = _leading_bullet_block(_lines(*BULLETS, prev, table))
    assert block is not None
    assert table in block


def test_block_continues_onto_short_outlook_page_and_bullets():
    # The outlook opener is a 335-char numbered line, so the
    # footnote-definition skip swallows it transparently — the
    # suppression's job is to let the block REACH the guidance bullets
    # past it. The bullets carry the figures; the opener is dropped
    # again post-selection as a colon-ended list intro.
    opener = (
        "3 Full-Year 2025 Outlook Ford's underlying business is performing "
        "at the high end of the guidance range previously outlined in February, "
        "while absorbing a $1.0 billion net tariff headwind. Additionally, the "
        "company expects a headwind of $1.0 billion or less."
    )
    bullet = "\u2022 A 2025 adjusted EBIT headwind of $1.5 billion to $2 billion."
    prev = _mega("The company reported third-quarter revenue of $50.5 billion.")
    block = _leading_bullet_block(_lines(*BULLETS, prev, opener, bullet))
    assert block is not None
    assert bullet in block


def test_block_stops_at_contacts_page():
    contacts = (
        "5 Contacts Media David Tovar 1.773.682.7954 dtovar9@ford.com "
        "Equity Investment Community Lynn Antipas Tyson 1.203.616.5689 "
        "ltyson4@ford.com"
    )
    footnote = "\u2022 See tables later in this release for the nature and amount of special items."
    prev = _mega("The company raised its full-year adjusted EBIT guidance to $8.5 billion.")
    block = _leading_bullet_block(_lines(*BULLETS, prev, contacts, footnote))
    assert block is not None
    assert contacts not in block
    assert footnote not in block


def test_block_stops_at_cautionary_heading():
    cautionary = (
        "4 Cautionary Note on Forward-Looking Statements Statements included "
        "or incorporated by reference herein may constitute \u201cforward-looking "
        "statements\u201d within the meaning of the Private Securities Litigation "
        "Reform Act of 1995. Forward-looking statements are based on expectations."
    )
    risk = "\u2022 Ford's long-term success depends on delivering the Ford+ plan."
    prev = _mega("The company posted third-quarter revenue of $49.5 billion.")
    block = _leading_bullet_block(_lines(*BULLETS, prev, cautionary, risk))
    assert block is not None
    assert cautionary not in block
    assert risk not in block


def test_block_keeps_bullet_carrying_cautionary_string():
    # The Cautionary string glued inside a footnote bullet (F 2025-03-31's
    # wholesale bullet) must NOT break the block: only a heading-shaped
    # line ends it.
    bullet = (
        "\u2022 Wholesale unit and production volumes include Ford and Lincoln brand "
        "vehicles. See materials supporting the conference call at "
        "shareholder.ford.com for further discussion of wholesale unit volumes. "
        "Cautionary Note on Forward-Looking Statements Statements included herein "
        "may constitute forward-looking statements."
    )
    prev = _mega("The company posted first-quarter revenue of $40.7 billion.")
    block = _leading_bullet_block(_lines(*BULLETS, prev, bullet))
    assert block is not None
    assert bullet in block


def test_block_stops_at_conference_call_heading():
    call = (
        "5 Conference Call Details Ford Motor Company (NYSE: F) and Ford Motor "
        "Credit Company released their second-quarter 2024 financial results "
        "today. The companies will host a conference call to discuss the results."
    )
    prev = _mega("The company reported second-quarter revenue of $50.2 billion.")
    block = _leading_bullet_block(_lines(*BULLETS, prev, call))
    assert block is not None
    assert call not in block


def test_block_keeps_bullet_mentioning_conference_call():
    bullet = "\u2022 The company will host a conference call at 5 p.m. to discuss results."
    prev = _mega("The company reported second-quarter revenue of $50.2 billion.")
    block = _leading_bullet_block(_lines(*BULLETS, prev, bullet))
    assert block is not None
    assert bullet in block


# --- Ford end-to-end ------------------------------------------------------

def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def test_ford_q4_2024_serves_both_tables():
    live = _live("F_2024-12-31")
    lines = _live_lines("F_2024-12-31")
    assert len(lines) == 9
    assert "Business Segment Highlights" in live
    assert "Ford Blue Segment Wholesales (000) 758 774" in live
    assert "Total Company Highlights" in live
    assert "Conference Call Details" not in live
    assert not live.rstrip().endswith("\u2026")


def test_ford_q2_2025_serves_segment_narrative():
    live = _live("F_2025-06-30")
    assert len(_live_lines("F_2025-06-30")) == 9
    assert "Business Segment Highlights" in live
    assert "Ford Blue reported $661 million in EBIT" in live
    # The conference-call page is not a separate line: the narrative
    # page's tail carries the call details glued inside the same
    # mega-line (known wart — the page is one line and cannot be
    # split). No standalone conference-call page is collected.
    assert not any(
        ln.strip().split(" ", 1)[-1].startswith("Conference Call Details")
        for ln in _live_lines("F_2025-06-30")
    )
    assert not live.rstrip().endswith("\u2026")


def test_ford_q3_2025_serves_outlook_prose_and_bullets():
    # The outlook prose opener itself is not in live: the
    # footnote-definition skip swallows it in the block and the
    # colon-heading post-selection drop removes it anyway (it ends
    # "Full-year 2025 guidance now reflects:"). Its figures ride in
    # the guidance bullets, which is what the card needs.
    live = _live("F_2025-09-30")
    assert len(_live_lines("F_2025-09-30")) == 12
    assert "A 2025 adjusted EBIT headwind of $1.5 billion to $2 billion" in live
    assert "That Ford has line of sight to mitigate at least $1.0 billion" in live
    assert "Cautionary Note on Forward-Looking Statements" not in live
    assert "Ford's long-term success depends" not in live
    assert not live.rstrip().endswith("\u2026")


def test_ford_q1_2026_serves_tables_and_outlook_without_contacts():
    live = _live("F_2026-03-31")
    assert len(_live_lines("F_2026-03-31")) == 8
    assert "Business Segment Highlights" in live
    assert "Total Company Highlights" in live
    assert "Full-Year 2026 Outlook" in live
    assert "Contacts Media David Tovar" not in live
    assert "@ford.com" not in live
    assert not live.rstrip().endswith("\u2026")


def test_ford_q2_2026_serves_segment_guidance_bullets():
    live = _live("F_2026-06-30")
    assert len(_live_lines("F_2026-06-30")) == 18
    assert "Ford Blue EBIT of $5.0 billion to $5.5 billion" in live
    assert "Ford Pro EBIT of $7.0 billion to $7.5 billion" in live
    assert "Ford Model e loss of approximately $4.0 billion" in live
    assert "Ford Credit earnings before taxes above $2.5 billion" in live
    assert not live.rstrip().endswith("\u2026")


def test_ford_q3_2026_drops_risk_bullets():
    live = _live("F_2026-09-30")
    assert len(_live_lines("F_2026-09-30")) == 9
    assert "Business Segment Highlights" in live
    assert "Cautionary Note on Forward-Looking Statements" not in live
    assert "Ford's long-term success depends" not in live
    assert "Ford's vehicles could be affected by defects" not in live


def test_ford_early_quarters_gain_segment_table_without_truncation():
    for key, n_lines in (("F_2024-06-30", 7), ("F_2024-09-30", 7)):
        live = _live(key)
        assert len(_live_lines(key)) == n_lines, key
        assert "Business Segment Highlights" in live, key
        assert "Conference Call Details" not in live, key
        assert not live.rstrip().endswith("\u2026"), key


def test_ford_q1_2025_unchanged():
    # F 2025-03-31 already served its segment table (inside the lede
    # mega-line) and does not move in the blast; pin it stays put.
    live = _live("F_2025-03-31")
    assert len(_live_lines("F_2025-03-31")) == 8
    assert "Business Segment Highlights" in live
    assert "Ford Blue Segment Wholesales (000) 626 588" in live
    assert "Cautionary Note on Forward-Looking Statements" not in live
