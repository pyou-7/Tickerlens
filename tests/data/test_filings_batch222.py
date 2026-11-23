"""Batch 222: highlights never end mid-sentence — completion allowance
plus clean-drop trim.

The lede finish rule's 4-line overrun cap (and the Highlights-section
collector's 12-line cap, and the leading-bullet block's 14-line cap)
could strand a quote or sentence mid-item, so stored highlights ended
"“We have excellent" (AJG) or "said David M. Cordani," (CI) or "and
slot" (GEV). The fix has three parts, all gated on the finish rule's
own unfinished signals:

1. Completion allowance: when the cap is hit and the tail item is
   still unfinished, allow up to 4 more lines (lede 4->8 past budget,
   section 12->16 follow lines, block 14->18) so the sentence can
   terminate and the quote close.
2. Clean-drop trim (_trim_unfinished_tail): when even the allowance
   is not enough (AJG's 12-line quotes), drop the dangling tail back
   to the last complete sentence instead of serving the fragment.
3. The quote test is the TAIL test (_lede_tail_quote_open): a stray
   mark from an earlier quote must not keep the allowance pulling
   after the tail's own quote closed (GIS pulled the next section's
   heading + bullets; AJG pulled the "shown on pages 14 and 15"
   pointer line). And the section collector judges qualification on
   a snapshot of its first 12 follow lines, so the extended tail's
   $/% figures can never flip a narrative section to "table"
   (CINF Q4 2025 was discarded for the lede fallback).

Live pins run the extractor against the real cached exhibits; the
unit pins cover the trim and the tail-quote test directly.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_sentence_terminated,
    _lede_tail_quote_open,
    _trim_unfinished_tail,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _last(hl: str) -> str:
    lines = [ln for ln in hl.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


# --- live pins: allowance completes the quote/sentence -------------------


def test_ci_quote_completes_with_attribution() -> None:
    hl = extract_press_release_highlights(_read("CI_2025-06-30.html"))
    assert hl is not None
    assert "said David M. Cordani," not in hl.split("\n")[-1]
    assert "David M. Cordani" in hl
    assert "chairman and CEO of The Cigna Group" in hl
    assert _is_sentence_terminated(_last(hl))
    assert hl.endswith("business mix.”")


def test_gev_quote_completes() -> None:
    hl = extract_press_release_highlights(_read("GEV_2025-06-30.html"))
    assert hl is not None
    assert "and slot" not in _last(hl)
    assert _is_sentence_terminated(_last(hl))
    assert hl.endswith("accelerating faster.”")


def test_hal_quote_completes() -> None:
    hl = extract_press_release_highlights(_read("HAL_2026-06-30.html"))
    assert hl is not None
    assert _is_sentence_terminated(_last(hl))
    assert hl.endswith("was $683 million.")


def test_ajg_long_quote_completes() -> None:
    # The 2025-12-31 quote ("We have excellent...") completes within
    # the allowance now that the finish rule pulls the continuation.
    hl = extract_press_release_highlights(_read("AJG_2025-12-31.html"))
    assert hl is not None
    assert "We have excellent" not in _last(hl)
    assert _is_sentence_terminated(_last(hl))
    assert "just getting started!”" in hl


def test_ajg_pointer_line_not_pulled() -> None:
    # The first quote never closes in the source (no closing mark), so
    # the whole-text open-quote test used to keep the allowance pulling
    # past the second quote — into the "reconciliation ... is shown on
    # pages 14 and 15" pointer line. The tail test stops at the second
    # quote's close.
    hl = extract_press_release_highlights(_read("AJG_2023-09-30.html"))
    assert hl is not None
    assert "is shown on pages 14 and 15" not in hl
    assert hl.endswith("excited about our long-term growth prospects!”")


# --- live pins: trim drops the dangling tail -------------------------------


def test_gev_quote_completes_past_section_cap() -> None:
    # Batch 224 (renamed from test_gev_unfinishable_quote_trimmed_to_
    # dateline): GEV Q3 2025's quote needs 5 lines past the section cap;
    # the batch-222 allowance gives 4, so the trim used to drop the quote
    # fragment back to the terminated dateline. The termination lookahead
    # sees the quote's closing line just past the cap, so the section
    # pulls it and the quote completes instead of being trimmed.
    hl = extract_press_release_highlights(_read("GEV_2025-09-30.html"))
    assert hl is not None
    assert "said GE Vernova CEO" in hl
    assert "Scott Strazik" in hl
    assert _is_sentence_terminated(_last(hl))
    assert hl.endswith("decarbonize.”")


def test_fdx_quote_fragment_trimmed() -> None:
    hl = extract_press_release_highlights(_read("FDX_2026-02-28.html"))
    assert hl is not None
    assert "Our strategy not only strengthens" not in _last(hl)
    assert _is_sentence_terminated(_last(hl))


# --- live pins: no regressions ----------------------------------------------


def test_cinf_section_not_discarded_as_table() -> None:
    # The extended section tail's $/% figures must not flip the
    # Highlights section to "table": the section (with its
    # property-casualty bullets) still wins over the lede fallback.
    hl = extract_press_release_highlights(_read("CINF_2025-12-31.html"))
    assert hl is not None
    assert "85.2% fourth-quarter 2025 property casualty combined ratio" in hl
    assert "Cincinnati, February 9, 2026" not in hl  # the lede dateline
    assert _is_sentence_terminated(_last(hl))


def test_gis_next_section_not_pulled_in() -> None:
    # The tail quote closed, so the allowance must stop there — the
    # "Fourth Quarter Results Summary" heading and its bullets belong
    # to the next section, not the highlights.
    hl = extract_press_release_highlights(_read("GIS_2026-05-31.html"))
    assert hl is not None
    assert "Fourth Quarter Results Summary" not in hl
    assert "Net sales were up 1 percent to $4.6 billion" not in hl
    assert hl.endswith("over the long term.”")


def test_nike_bullet_tail_untouched() -> None:
    # Bullets are complete items without terminal punctuation — the
    # trim must never eat them.
    hl = extract_press_release_highlights(_read("NKE_2025-02-28.html"))
    assert hl is not None
    assert _last(hl) == "• Diluted earnings per share was $0.54"


# --- unit pins: tail-quote test ----------------------------------------------


def test_tail_quote_open() -> None:
    # An unclosed first quote plus a closed second quote: the tail's
    # quote closed, whatever the first did.
    assert not _lede_tail_quote_open(
        [
            "“Looking ahead, our opportunities are immense.",
            "geopolitical tensions, and a growing appreciation for risk.",
            "“I am very pleased with our third quarter performance!”",
        ]
    )
    # A quote that never closes: still open.
    assert _lede_tail_quote_open(
        ["“Overall, the global P/C insurance market continues to grow with"]
    )
    # No marks at all: not open.
    assert not _lede_tail_quote_open(["Revenue was $5.7 billion."])
    # A curly open closed by a straight mark counts as closed.
    assert not _lede_tail_quote_open(["“We had a strong quarter." '"'])


# --- unit pins: trim ----------------------------------------------------------


def test_trim_drops_wrap_tail_to_terminated_line() -> None:
    # The remaining lede must clear the 200-char floor (batch 153),
    # so the terminated line carries enough real content.
    lede = [
        "BLOOMFIELD, CT, July 31, 2025 – Global health company The Cigna Group (NYSE: CI) "
        "today reported strong second quarter 2025 results, reflecting continued growth and "
        "solid performance across its diverse portfolio of businesses.",
        "“We have excellent",
    ]
    assert _trim_unfinished_tail(lede) == [lede[0]]
    # A multi-line unfinished quote drops as one fragment.
    lede = [
        "BLOOMFIELD, CT, July 31, 2025 – Global health company The Cigna Group (NYSE: CI) "
        "today reported strong second quarter 2025 results, reflecting continued growth and "
        "solid performance across its diverse portfolio of businesses.",
        "“Looking ahead, our growth opportunities are immense. And with",
        "continued price increases, economic growth, increasing",
    ]
    assert _trim_unfinished_tail(lede) == [lede[0]]


def test_trim_leaves_bullets_headings_and_terminated_lines() -> None:
    assert _trim_unfinished_tail(
        ["Revenue grew.", "• Diluted earnings per share was $0.54"]
    ) == ["Revenue grew.", "• Diluted earnings per share was $0.54"]
    assert _trim_unfinished_tail(["Revenue grew.", "Financial Outlook"]) == [
        "Revenue grew.",
        "Financial Outlook",
    ]
    assert _trim_unfinished_tail(["Revenue grew.", "Costs fell."]) == [
        "Revenue grew.",
        "Costs fell.",
    ]


def test_trim_floor_keeps_short_unfinished_lede() -> None:
    # Nothing terminated to fall back to, and the whole lede is under
    # the 200-char floor: a wart is better than dropping the row.
    lede = ["“We have excellent"]
    assert _trim_unfinished_tail(lede) == lede
