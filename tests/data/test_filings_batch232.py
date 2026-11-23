"""Batch 232: the trailing dangling table/list intro — the live
extraction ends on (or strands mid-body) a colon-ended intro whose
table was dropped: Berkshire's "Net earnings includes:" (+ its row
label above it), FedEx's "...have been adjusted for:", Gilead's
bullet "...primarily driven by:", Fastenal's "...were as follows:"
(+ the SG&A data row the lede loop missed — its 6-word label
dilutes figure density to 36%, under the 40% bar, because the
spaced "$" was not counted as a figure).

The fix lives in the final cleanup only (_clean_highlights_result)
plus one count in _is_lede_data_row: a trailing colon-ended line is
dangling by construction (whatever it introduces is not served), so
the batch-226 colon rule loses its residue-cascade gate and gains
the long-intro tail phrases; a line whose post-terminator fragment
is a dangling intro is truncated at the terminator instead of
popped, tail and mid-body (AutoZone's dateline paragraph, Bristol
Myers' in-line-products sentence, Centene's summary sentence,
Fastenal's product/end-market paragraphs); and a standalone "$"
token counts as a figure for data-row density.

Blast-radius method: highlights + guidance old-vs-new over 1,699
cached exhibits (scripts/batch232_cache_blast.py,
scripts/batch232_guidance_blast.py, hidden_files/blast232/):
34 highlights diffs, 0 guidance diffs, all verified line-by-line
(AZO x12 dateline truncations; BMY x1; BRK.B x7 label+intro
cascades; CNC x1; DIS x1 dangling "Fiscal 2025:" bullet; FAST x8
DSR truncations + the 2025-03-31 SG&A row and the freed end-market
paragraph; FDX x3; GILD x1). The spaced-$ count flipped no prose
line to a data row anywhere in the cache.

Live pins run the extractor against the real cached exhibits; the
unit pins cover each new predicate and its guards directly.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _clean_highlights_result,
    _is_lede_data_row,
    _is_trailing_dangling_intro,
    _truncate_trailing_dangling_intro,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _lines(hl: str) -> list[str]:
    return [ln for ln in hl.splitlines() if ln.strip()]


# --- live pins: the dangling intro is gone, the content stays -------


def test_brkb_label_and_colon_intro_dropped() -> None:
    for key in ("BRK.B_2025-03-31", "BRK.B_2025-06-30", "BRK.B_2026-06-30"):
        hl = extract_press_release_highlights(_read(f"{key}.html"))
        assert hl is not None
        assert "Net earnings includes:" not in hl
        assert "Net earnings attributable to Berkshire shareholders" not in hl
        assert _lines(hl)[-1].endswith("per share amounts).")


def test_brkb_older_quarters_label_and_intro_dropped() -> None:
    # The 2024 quarters carry the same tail in the stored rows; the
    # cascade clears them too (blast: 2024-03-31, 2024-06-30).
    for key in ("BRK.B_2024-03-31", "BRK.B_2024-06-30"):
        hl = extract_press_release_highlights(_read(f"{key}.html"))
        assert hl is not None
        assert "Net earnings includes:" not in hl
        assert "Net earnings attributable to Berkshire shareholders" not in hl


def test_fdx_adjusted_for_intro_dropped() -> None:
    for key in ("FDX_2024-05-31", "FDX_2025-02-28", "FDX_2026-05-31"):
        hl = extract_press_release_highlights(_read(f"{key}.html"))
        assert hl is not None
        assert "have been adjusted for:" not in hl
        assert _lines(hl)[-1].startswith("MEMPHIS, Tenn.")


def test_gild_dangling_bullet_dropped() -> None:
    # Batch 262: no longer dropped — the "◦" sub-bullet joins
    # _BULLET_LEAD_RE, so the revenue bullet's ◦ sub-list is recognized
    # and the colon-opener is served with its sub-bullets instead of
    # being cut as dangling.
    hl = extract_press_release_highlights(_read("GILD_2026-06-30.html"))
    assert hl is not None
    assert "primarily driven by:" in hl
    assert "Total second quarter 2026 revenues increased 10%" in hl
    assert "◦ Higher sales of HIV products" in hl
    assert _lines(hl)[-1].startswith(
        "• During the second quarter 2026, Gilead generated $3.6 billion"
    )


def test_fast_sga_row_and_dsr_intro_dropped() -> None:
    hl = extract_press_release_highlights(_read("FAST_2025-03-31.html"))
    assert hl is not None
    assert "Selling, general, and administrative (SG&A) expenses" not in hl
    assert "were as follows:" not in hl
    assert "From an end market standpoint" in hl
    assert _lines(hl)[-1].endswith("declining sales with resellers.")
    prod = [x for x in _lines(hl) if x.startswith("From a product standpoint")][0]
    assert prod.endswith("reflecting continued soft manufacturing demand.")


def test_fast_older_quarters_dsr_intro_truncated() -> None:
    for key in ("FAST_2024-03-31", "FAST_2024-12-31"):
        hl = extract_press_release_highlights(_read(f"{key}.html"))
        assert hl is not None
        assert "were as follows:" not in hl
        assert "From a product standpoint" in hl
        assert "From an end market standpoint" in hl


def test_azo_dateline_intro_truncated() -> None:
    hl = extract_press_release_highlights(_read("AZO_2023-11-18.html"))
    assert hl is not None
    assert "are as follows:" not in hl
    assert "net sales of $4.2 billion" in _lines(hl)[1]
    assert _lines(hl)[1].endswith("fiscal 2023 (12 weeks).")


def test_azo_fourth_quarter_basis_intro_truncated() -> None:
    # The 16-week/52-week basis variant ("...are computed on a
    # 16-week and 52-week basis and are as follows:").
    hl = extract_press_release_highlights(_read("AZO_2024-08-31.html"))
    assert hl is not None
    assert "are as follows:" not in hl
    assert "adjusted sales were up 2.6%." in _lines(hl)[1]


def test_bmy_driven_by_intro_truncated() -> None:
    hl = extract_press_release_highlights(_read("BMY_2023-12-31.html"))
    assert hl is not None
    assert "largely driven by:" not in hl
    assert "Revenues for in-line products in the fourth quarter were $8.7 billion" in hl


def test_cnc_summary_intro_truncated() -> None:
    hl = extract_press_release_highlights(_read("CNC_2025-06-30.html"))
    assert hl is not None
    assert "were as follows:" not in hl
    dateline = [x for x in _lines(hl) if x.startswith("ST. LOUIS, July 25, 2025")][0]
    assert dateline.endswith("June 30, 2025.")


def test_dis_fiscal_2025_opener_children_served() -> None:
    # Batch 263: the batch-232 pin is reversed — "• Fiscal 2025:" is
    # a genuine guidance sub-list opener, not a dangling intro: its
    # items are ◦ bullets, so the leading-block bullet-run extension
    # serves the opener and all four children. (Old name:
    # test_dis_dangling_fiscal_bullet_dropped.)
    # Batch 264: the sub-list completes — the bullet-run extension
    # stopped at the 18-line bound on the fourth child, stranding
    # the last two ◦ children; the sub-list completion serves them,
    # so the last line is now the Entertainment child.
    hl = extract_press_release_highlights(_read("DIS_2024-09-28.html"))
    assert hl is not None
    assert "Fiscal 2025:" in hl
    assert "High-single digit adjusted EPS(1) growth" in hl
    assert "Target dividend growth that tracks our earnings growth" in hl
    assert "Targeting $3 billion in stock repurchases" in hl
    assert _lines(hl)[-1].startswith(
        "◦ Entertainment: Double digit percentage segment operating "
        "income growth compared to fiscal 2024"
    )


# --- unit pins: the dangling-intro predicate ------------------------


def test_is_trailing_dangling_intro() -> None:
    assert _is_trailing_dangling_intro("Net earnings includes:")
    assert _is_trailing_dangling_intro("EPS ($):")
    assert _is_trailing_dangling_intro("• Fiscal 2025:")
    assert _is_trailing_dangling_intro(
        "This year’s and last year’s quarterly consolidated results "
        "have been adjusted for:"
    )
    assert _is_trailing_dangling_intro(
        "• Total second quarter 2026 revenues increased 10% to $7.8 "
        "billion compared to the same period in 2025, primarily driven by:"
    )
    assert _is_trailing_dangling_intro(
        "The DSR change when compared to the same period in the prior "
        "year and the percent of sales in the period were as follows:"
    )
    assert _is_trailing_dangling_intro("The components consist of:")
    # A long colon line that is NOT a table/list intro stays put.
    assert not _is_trailing_dangling_intro(
        "During the quarter we completed the following strategic initiatives:"
    )
    # No trailing colon, no intro.
    assert not _is_trailing_dangling_intro("Revenue grew 10% in the quarter.")
    assert not _is_trailing_dangling_intro("Outlook: strong growth ahead")
    # A quote intro is content, never residue.
    assert not _is_trailing_dangling_intro(
        "“We are pleased with the results,” commented Jane Smith, Chief Executive Officer:"
    )
    assert not _is_trailing_dangling_intro("said Daniel O’Day, Chairman and CEO:")


def test_truncate_trailing_dangling_intro() -> None:
    assert (
        _truncate_trailing_dangling_intro(
            "Revenue grew 10% in the quarter. The breakdown is as follows:"
        )
        == "Revenue grew 10% in the quarter."
    )
    # A pure intro line has no terminator: nothing to truncate to.
    assert _truncate_trailing_dangling_intro("Net earnings includes:") is None
    # A bullet-led line never qualifies (its fragment is the bullet).
    assert (
        _truncate_trailing_dangling_intro(
            "• Total revenues increased 10%, primarily driven by:"
        )
        is None
    )
    # A comma fragment is a wrap continuation, not a dangling intro.
    assert (
        _truncate_trailing_dangling_intro(
            "Revenue grew 10%. Sales were strong, driven by"
        )
        is None
    )


def test_clean_highlights_truncates_mid_body_intro() -> None:
    body = (
        "Headline Goes Here And It Is Long Enough To Pass The Floor Check For This Test Body\n\n"
        "• First bullet with real content about the quarter and its results for investors.\n"
        "Revenue grew 10% in the quarter. The breakdown is as follows:\n"
        "• Second bullet with more content about guidance and the outlook for next year.\n"
    )
    out = _clean_highlights_result(body)
    assert "The breakdown is as follows:" not in out
    assert "Revenue grew 10% in the quarter." in out
    assert "Second bullet with more content" in out


def test_clean_highlights_pops_short_colon_without_residue() -> None:
    # Batch 226 pinned the opposite: a bare list intro with no
    # residue popped above it stayed put. Batch 232 removes the
    # cascade gate — a trailing colon line is dangling by
    # construction, so the intro pops and the cascade still runs.
    body = (
        "Headline Goes Here And It Is Long Enough To Pass The Floor Check For This Test Body\n\n"
        "• First bullet with real content about the quarter and its results for investors.\n"
        "• Second bullet with more content about guidance and the outlook for next year.\n"
        "Net earnings includes:\n"
    )
    out = _clean_highlights_result(body)
    assert not out.endswith("Net earnings includes:")


def test_clean_highlights_colon_cascade_with_label() -> None:
    body = (
        "Headline Goes Here And It Is Long Enough To Pass The Floor Check For This Test Body\n\n"
        "• First bullet with real content about the quarter and its results for investors.\n"
        "• Second bullet with more content about guidance and the outlook for next year.\n"
        "Earnings are stated on an after-tax basis. (Dollar amounts are in millions, except for per share amounts).\n"
        "Net earnings attributable to Berkshire shareholders\n"
        "Net earnings includes:\n"
    )
    out = _clean_highlights_result(body)
    assert "Net earnings includes:" not in out
    assert "Net earnings attributable to Berkshire shareholders" not in out
    assert "after-tax basis" in out


# --- unit pins: the spaced-$ figure count ---------------------------


def test_is_lede_data_row_spaced_dollar() -> None:
    assert _is_lede_data_row(
        "Selling, general, and administrative (SG&A) expenses $ 490.0 471.4 3.9 %"
    )
    assert _is_lede_data_row("Net sales $ 1,959.4 1,895.1 3.4 %")
    # Wrapped prose with spaced $ figures stays prose: 4 figures
    # over 21 tokens is 19%, under the 40% bar, and the extended
    # $-figure band refuses scaled $ figures ("$ 2.0 billion").
    # (A short line with 2 bare $ figures is a data row by the
    # pre-existing batch-157 $-figure branch — the density count
    # is not what decides that shape.)
    assert not _is_lede_data_row(
        "We delivered strong financial results in the first quarter, "
        "generating $ 2.0 billion in total revenue and $ 66 million in net income"
    )
    # The established prose guard (batch 178): scaled $ figures in
    # a terminated sentence are content, not a row.
    assert not _is_lede_data_row(
        "We delivered strong financial results in Q1, generating $2.0 billion "
        "in total revenue, $66 million in net income,"
    )
