"""Batch 224: the noun/number-ending hole — a next-line lookahead for the
finish rule, plus a termination lookahead that lets the hard caps yield
when the sentence ends just past them.

A cut landing on a line ending in a noun or figure ("Operating income
was $746 million", "... related to the store portfolio") carries no
unfinished signal — no wrap tail, no comma, no open quote — so the
finish rule treated the item as complete and the trim could not see it
either. Two parts, both gated on the sentence genuinely continuing:

1. Lowercase lookahead (_lede_next_line_continues): the next raw line
   starting lowercase means the sentence wraps on — the finish-item
   decision and the completion allowance at all three caps (lede,
   section, block) treat the item as unfinished. The tail must be
   unterminated: a terminated tail (a closed quote) followed by a
   lowercase-led line is a new sentence's wrap tail, not a
   continuation — AJG's pointer line starts lowercase and must stay
   out (batch 222's regression guard, re-caught here).
2. Termination lookahead (_lede_termination_ahead): the hard caps
   (lede 8 past budget, section 16, block 18) yield when the sentence
   terminates within the next 4 raw lines — Halliburton's sentence ends
   one line past the block's 18-line cap, so an absolute cap strands it
   and the trim walks it back further. Gated on the sentence still being
   unfinished (or the next line continuing it): once the tail
   terminates, the pull stops even when another terminated line sits
   ahead (CI's pointer sentence, AJG's pointer line).

Live pins run the extractor against the real cached exhibits; the unit
pins cover both lookaheads directly.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_sentence_terminated,
    _lede_next_line_continues,
    _lede_termination_ahead,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _last(hl: str) -> str:
    lines = [ln for ln in hl.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


# --- live pins: the hole rows now terminate ------------------------------


def test_hal_q4_2025_sentence_completes_past_block_cap() -> None:
    # The sentence terminates ONE line past the block's 18-line cap
    # ("$748 million in the third quarter of 2025.") — the absolute cap
    # used to strand it at "Operating income was $746 million" and the
    # trim walked it back further, to "in the third".
    hl = extract_press_release_highlights(_read("HAL_2025-12-31.html"))
    assert hl is not None
    assert "Operating income was $746 million" in hl
    assert _is_sentence_terminated(_last(hl))
    assert hl.endswith("$748 million in the third quarter of 2025.")


def test_hal_q2_2025_sentence_completes() -> None:
    hl = extract_press_release_highlights(_read("HAL_2025-06-30.html"))
    assert hl is not None
    assert _is_sentence_terminated(_last(hl))
    assert hl.endswith("million.")


def test_hal_q1_2025_sentence_completes() -> None:
    hl = extract_press_release_highlights(_read("HAL_2025-03-31.html"))
    assert hl is not None
    assert _is_sentence_terminated(_last(hl))
    assert hl.endswith("quarter of 2025.")


def test_dg_q4_2024_sentence_completes() -> None:
    # "... related to the store portfolio" wraps onto "optimization
    # review ..." and terminates three lines later.
    hl = extract_press_release_highlights(_read("DG_2025-01-31.html"))
    assert hl is not None
    assert "related to the store portfolio" in hl
    assert "Store Portfolio Optimization Review" in hl
    assert _is_sentence_terminated(_last(hl))
    assert hl.endswith(
        "related expenses; partially offset by a decrease in professional fees."
    )


def test_dg_q1_2025_sentence_completes() -> None:
    hl = extract_press_release_highlights(_read("DG_2025-05-02.html"))
    assert hl is not None
    assert _is_sentence_terminated(_last(hl))
    assert hl.endswith(
        "were retail labor, incentive compensation, and repairs and maintenance."
    )


def test_dg_q3_2025_sentence_completes() -> None:
    hl = extract_press_release_highlights(_read("DG_2025-10-31.html"))
    assert hl is not None
    assert _is_sentence_terminated(_last(hl))
    assert hl.endswith("costs.")


def test_ci_dateline_wrap_completes() -> None:
    # The dateline sentence wraps: "... The Cigna Group (NYSE: CI) today"
    # continues on the next line ("reported 2024 results, ...").
    hl = extract_press_release_highlights(_read("CI_2024-12-31.html"))
    assert hl is not None
    assert "reported 2024 results" in hl
    assert _is_sentence_terminated(_last(hl))


def test_abnb_letter_sentence_completes() -> None:
    # "... increased 8% compared to the prior" wraps onto "year, driven
    # by continued growth in all regions." and the footnote pointer.
    hl = extract_press_release_highlights(_read("ABNB_2024-09-30.html"))
    assert hl is not None
    assert "compared to the prior" in hl
    assert _is_sentence_terminated(_last(hl))
    assert hl.endswith(
        "to the most comparable GAAP measures is provided at the end of this letter."
    )


def test_dal_complete_bullet_unchanged() -> None:
    # DAL 2024-09-30 is NOT a hole row: the tail is a complete bullet
    # ("... increasing connectivity to popular Mexican destinations")
    # and the next line is the "Culture and People" section heading, so
    # no continuation exists to pull. It serves live (no stored row).
    hl = extract_press_release_highlights(_read("DAL_2024-09-30.html"))
    assert hl is not None
    assert "increasing connectivity to popular Mexican destinations" in hl
    assert "Culture and People" not in hl
    assert "Accrued $320 million in profit sharing" not in hl


def test_ajg_pointer_line_still_not_pulled() -> None:
    # The batch-222 regression guard, re-caught by the first cut of this
    # fix: the pointer line starts lowercase ("reconciliation of the
    # 2023 and 2022 provision ...") but the tail quote closed, so it is
    # not a continuation of the quote.
    hl = extract_press_release_highlights(_read("AJG_2023-09-30.html"))
    assert hl is not None
    assert "is shown on pages 14 and 15" not in hl
    assert hl.endswith("excited about our long-term growth prospects!”")


# --- unit pins: the lowercase lookahead -----------------------------------


def test_next_line_continues_lowercase_wrap() -> None:
    assert _lede_next_line_continues(
        "total revenue of $5.6 billion in the third quarter of 2025. "
        "Operating income was $746 million",
        "in the fourth quarter of 2025, compared to operating income of",
    )
    assert _lede_next_line_continues(
        "an increase of 294 basis points. The increase reflects fourth "
        "quarter impairment charges totaling $214 million related to the "
        "store portfolio",
        "optimization review as discussed below",
    )


def test_next_line_continues_terminated_tail_gate() -> None:
    # A closed quote followed by a lowercase-led line is not a
    # continuation — the pointer line's own wrap, not the quote's.
    assert not _lede_next_line_continues(
        "“I am very pleased with our third quarter performance!”",
        "reconciliation of the 2023 and 2022 provision (benefit) for "
        "income taxes is shown on pages 14 and 15.",
    )
    assert not _lede_next_line_continues(
        "Net income was $746 million.",
        "in the fourth quarter of 2025, compared to",
    )


def test_next_line_continues_new_item_guards() -> None:
    tail = "Operating income was $746 million"
    # A new bullet is a new item, never a continuation.
    assert not _lede_next_line_continues(tail, "• Cash flow from operations")
    # A table row / heading is a new item.
    assert not _lede_next_line_continues(tail, "Total $17.60 7 % 4.5 %")
    assert not _lede_next_line_continues(tail, "Fourth Quarter Results")
    # A footnote definition is never a continuation.
    assert not _lede_next_line_continues(tail, "(1) During the year ended")
    # A figure-led line is deliberately not a continuation.
    assert not _lede_next_line_continues(tail, "$748 million in the third")
    assert not _lede_next_line_continues(tail, "2025, compared to 2024")


# --- unit pins: the termination lookahead ---------------------------------


def test_termination_ahead_one_line_past_cap() -> None:
    # Halliburton: the block cap strands the sentence at the line ending
    # "of"; the terminating line starts with "$" (not a lowercase
    # continuation), so only the termination scan reaches it.
    collected = [
        "• Revenue of $5.7 billion and operating margin of 13%.",
        "total revenue of $5.6 billion in the third quarter of 2025. "
        "Operating income was $746 million",
        "in the fourth quarter of 2025, compared to operating income of "
        "$356 million in the third",
        "quarter of 2025. Excluding “Impairments and other charges”, "
        "adjusted operating income5 in",
        "the fourth quarter of 2025, was $829 million, compared to "
        "adjusted operating income of",
    ]
    assert _lede_termination_ahead(
        collected, ["$748 million in the third quarter of 2025."]
    )


def test_termination_ahead_walks_the_hole() -> None:
    # The scan walks through hole-shaped lines (noun endings, no signal)
    # as long as each is followed by a lowercase-led line, and finds the
    # termination three lines out.
    collected = ["Operating income was $746 million"]
    assert _lede_termination_ahead(
        collected,
        [
            "in the fourth quarter of 2025, compared to operating income of "
            "$356 million in the third",
            "quarter of 2025. Excluding “Impairments and other charges”, "
            "adjusted operating income5 in",
            "the fourth quarter of 2025, was $829 million, compared to "
            "adjusted operating income of",
            "$748 million in the third quarter of 2025.",
        ],
    )


def test_termination_ahead_stops_at_new_item() -> None:
    # A bullet / heading / table line after the tail is a new item, not
    # the sentence's end — the scan stops, False.
    collected = ["increasing connectivity to popular Mexican destinations"]
    assert not _lede_termination_ahead(
        collected, ["Culture and People", "• Accrued $320 million"]
    )
    assert not _lede_termination_ahead(
        collected, ["Total $17.60 7 % 4.5 %"]
    )


def test_termination_ahead_terminated_tail_gate() -> None:
    # A closed quote followed by a terminated pointer line: the pointer
    # is not the quote's continuation, so the scan must not count it.
    collected = ["“I am very pleased with our third quarter performance!”"]
    assert not _lede_termination_ahead(
        collected,
        ["reconciliation of the 2023 and 2022 provision (benefit) for "
         "income taxes is shown on pages 14 and 15."],
    )


def test_termination_ahead_colon_is_not_an_end() -> None:
    # A colon introduces a quote or a table — it never terminates the
    # sentence, so the scan walks past it.
    collected = ["Operating income was $746 million"]
    assert not _lede_termination_ahead(
        collected,
        ["in the fourth quarter of 2025:", "Net earnings includes:"],
    )


def test_termination_ahead_quote_must_close() -> None:
    # A terminated line inside an open quote does not end the sentence —
    # the scan keeps walking until the quote closes.
    collected = ["“We are leading from a position of strength."]
    assert _lede_termination_ahead(
        collected,
        [
            "This era of increased electricity investment has just started, "
            "and we have substantial opportunity ahead of us as we provide "
            "the solutions required to help the world electrify to thrive "
            "and decarbonize.”",
        ],
    )
    # ... but when the quote never closes within the window, False.
    assert not _lede_termination_ahead(
        collected,
        [
            "This era of increased electricity investment has just started, "
            "and we have substantial opportunity ahead of us.",
            "The next sentence opens a new item.",
        ],
    )


def test_termination_ahead_limit_bounds_the_pull() -> None:
    # Termination more than 4 lines out is not "just ahead" — the cap
    # holds and the trim handles the tail (AJG's 12-line quotes).
    collected = ["“Looking ahead, our growth opportunities are immense."]
    assert not _lede_termination_ahead(
        collected,
        [
            "And with continued insurance and reinsurance price increases, "
            "economic growth, increasing",
            "geopolitical tensions, and a growing appreciation for risk, I "
            "believe our team is in a great",
            "position to provide our clients with superior insurance and "
            "risk management solutions.",
            "We have excellent momentum across the business.",
            "This is the fifth line out — past the window.",
        ],
    )
