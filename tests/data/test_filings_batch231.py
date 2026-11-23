"""Batch 231: the source-verified stale-row sweep. 528 stored
highlights rows differ from the current live extraction; earlier
batches would not blanket-swap them because the stored source was
unverified. The sweep swaps only rows whose source exhibit is
verified (headline match, datelines present, no real content lost)
and whose live text is clean — no added table row, no dangling
table-intro tail, no mid-sentence body start. 79 highlights rows
repair under gate S; 18 NULL-guidance rows fill under gate G
(Darden x8, Enphase x10 — real outlook prose).

These pins document the sweep's decisions on real cached exhibits:
the table-dominated guidance that keeps AppLovin x7 / DuPont x4 /
Skyworks x1 unfilled, the mid-sentence fragment that keeps Airbnb
2024-12-31 stale, and the added content that justifies the swaps
that do happen. The four blocked-tail pins (BRK.B x3, FAST, FDX,
GILD) documented the live extraction ending on a dangling table
intro; batch 232 trims those intros in the extractor, so the pins
now assert the clean tails and the rows repair under its gate S2.
No code change in this batch — the gates live in scripts/batch231_repair.py; the pins anchor the extractor
behavior the gates rely on.
"""
import os
import re
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _LEDE_BARE_UNITS_LOWER_RE,
    _LEDE_BARE_UNITS_RE,
    _footnote_def_block_len,
    _is_lede_data_row,
    _is_lede_period_header,
    _is_lede_table_header,
    _is_lede_table_line,
    _is_trailing_caps_line,
    _is_trailing_row_label,
    _is_trailing_table_data_row,
    _is_trailing_table_header_orphan,
    _is_trailing_units_period_header,
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


def _lines(text: str) -> list[str]:
    return [ln for ln in text.split("\n") if ln.strip()]


def _is_tableish(ln: str) -> bool:
    return bool(
        _is_lede_data_row(ln)
        or _is_lede_table_header(ln)
        or _is_lede_period_header(ln)
        or _is_trailing_units_period_header(ln)
        or _is_trailing_table_data_row(ln)
        or _is_trailing_table_header_orphan(ln)
        or _LEDE_BARE_UNITS_RE.match(ln)
        or _LEDE_BARE_UNITS_LOWER_RE.match(ln)
        or _is_lede_table_line(ln)
        or _is_trailing_row_label(ln)
        or _is_trailing_caps_line(ln)
        or re.fullmatch(r"\(\d+\)", ln)
        or _footnote_def_block_len([ln], 0)
    )


def _guidance_body_table_frac(guidance: str) -> float:
    """Table-ish fraction over the lines after the heading line."""
    gl = _lines(guidance)
    body = gl[1:] if len(gl) > 1 else []
    return sum(1 for x in body if _is_tableish(x)) / max(len(body), 1)


# --- Formerly blocked tails: batch 232 trims the dangling table
# intro in the extractor, so the live text is clean and these rows
# are repairable under gate S2. ---


def test_brkb_live_ends_on_dangling_table_intro():
    for key in ("BRK.B_2025-06-30", "BRK.B_2025-09-30", "BRK.B_2026-06-30"):
        lines = _lines(_live(key))
        assert "Net earnings includes:" not in lines
        assert "Net earnings attributable to Berkshire shareholders" not in lines
        assert lines[-1].endswith("per share amounts).")


def test_fast_live_ends_on_dangling_table_intro():
    lines = _lines(_live("FAST_2025-03-31"))
    assert "were as follows:" not in _live("FAST_2025-03-31")
    assert "Selling, general, and administrative (SG&A) expenses" not in _live(
        "FAST_2025-03-31"
    )
    assert lines[-1].endswith("declining sales with resellers.")


def test_fdx_live_ends_on_dangling_table_intro():
    lines = _lines(_live("FDX_2026-05-31"))
    assert "have been adjusted for:" not in _live("FDX_2026-05-31")
    assert lines[-1].startswith("MEMPHIS, Tenn.")


def test_gild_live_last_bullet_is_cut_off():
    # Batch 262: the "◦" sub-bullet joins _BULLET_LEAD_RE, so the
    # revenue bullet's ◦ sub-list is now recognized and the bullet is
    # no longer dangling — the full bullet list is served (5 bullets +
    # 2 sub-bullets) and the highlights end on the cash-flow bullet,
    # not the CEO quote.
    lines = _lines(_live("GILD_2026-06-30"))
    assert "primarily driven by:" in _live("GILD_2026-06-30")
    assert "Total second quarter 2026 revenues increased 10%" in _live(
        "GILD_2026-06-30"
    )
    assert "During the second quarter 2026, Gilead generated $3.6 billion in operating cash flow." in lines[-1]


# --- Blocked fragment: live body opens mid-sentence. ---


def test_abnb_live_body_opens_mid_sentence():
    lines = _lines(_live("ABNB_2024-12-31"))
    assert lines[1].startswith("driven by the growth of nights")


# --- Blocked guidance: the guidance section is a flattened table. ---


def test_app_guidance_is_a_flattened_table():
    for key in ("APP_2024-12-31", "APP_2025-03-31", "APP_2025-06-30"):
        g = _live_guidance(key)
        assert g is not None
        assert "Financial Guidance Summary" in _lines(g)[0]
        assert _guidance_body_table_frac(g) >= 0.5


def test_dd_guidance_is_a_flattened_table():
    g = _live_guidance("DD_2024-12-31")
    assert g is not None
    assert _lines(g)[0] == "2025 Financial Outlook"
    assert _guidance_body_table_frac(g) >= 0.5
    # The figures survive in the CFO quotes, but the section as served
    # is a table — the fill waits on a guidance-table treatment.
    assert "net sales of about $3.025 billion" in g


def test_skyd_guidance_is_heading_over_table_residue():
    g = _live_guidance("SKYD_2026-06-30")
    assert g is not None
    assert _lines(g)[0] == "Outlook"
    assert _guidance_body_table_frac(g) >= 0.9


# --- Fill targets: real outlook prose, low table fraction. ---


def test_dri_guidance_is_prose_outlook():
    g = _live_guidance("DRI_2024-11-24")
    assert g is not None
    assert _lines(g)[0] == "Fiscal 2025 Financial Outlook"
    assert "Total sales of approximately $12.1 billion" in g
    assert _guidance_body_table_frac(g) < 0.2


def test_dri_short_reaffirmation_guidance_is_prose():
    # Only a heading + one reaffirmation sentence; the heading is the
    # sole tableish line, so the body fraction is 0.
    g = _live_guidance("DRI_2026-08-30")
    assert g is not None
    assert "reaffirmed all aspects of its full year financial outlook" in g
    assert "$11.10 to $11.35" in g
    assert _guidance_body_table_frac(g) < 0.2


def test_enph_guidance_is_prose_outlook():
    g = _live_guidance("ENPH_2025-03-31")
    assert g is not None
    assert _lines(g)[0] == "SECOND QUARTER 2025 FINANCIAL OUTLOOK"
    assert "Revenue to be within a range of $340.0 million" in g
    assert _guidance_body_table_frac(g) < 0.2


# --- Swap premises: the live extraction adds real content and drops
# only residue, for rows the sweep repairs. ---


def test_abbv_live_adds_real_bullets():
    live = _live("ABBV_2024-09-30")
    assert "Successfully Completed Acquisition of Cerevel" in live
    assert "Raises 2024 Adjusted Diluted EPS Guidance Range" in live
    assert "Announces 2025 Dividend Increase of 5.8 Percent" in live


def test_ftnt_live_adds_record_bullets():
    live = _live("FTNT_2025-03-31")
    assert "Record first quarter Non-GAAP operating margin of 34%" in live
    assert "Record Cash flow from operations of $863 million" in live
    assert "Record Free cash flow of $783 million" in live


def test_arcc_live_drops_section_labels_adds_quotes():
    live = _live("ARCC_2024-09-30")
    lines = _lines(live)
    assert "DIVIDEND DECLARATIONS" not in lines
    # The phrase survives inside the headline; the standalone section
    # label line is what the live extraction drops.
    assert "SEPTEMBER 30, 2024 FINANCIAL RESULTS" not in lines
    assert "We reported strong third quarter Core EPS" in live


def test_bby_live_drops_table_residue():
    live = _live("BBY_2024-11-02")
    assert "Domestic comparable online sales % change1" not in live
    assert "International comparable sales % change1" not in live
    assert "Comparable Sales Declined 2.9%" in live


def test_bmy_live_serves_portfolio_narrative():
    live = _live("BMY_2024-09-30")
    assert "Growth Portfolio worldwide revenues increased to $5.8 billion" in live
    assert "($ amounts in millions)" not in live


def test_eix_live_drops_admin_line_adds_bullet():
    live = _live("EIX_2024-06-30")
    assert "Media Relations: (626) 302-2255" not in live
    assert "Reiterates long-term core EPS growth rate targets" in live


def test_enph_live_tail_is_pre_existing():
    # The dangling intro line is already in the stored row, so the
    # swap only drops residue lines — it does not add a new tail.
    live = _live("ENPH_2025-03-31")
    lines = _lines(live)
    assert lines[-1].endswith("compared with the prior quarter:")
    assert "Revenue of $356.1 million" in live
