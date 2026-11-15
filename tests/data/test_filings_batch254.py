"""Batch 254 regression tests.

Gate S11 (scripts/batch254_repair.py): S4 with the
section-heading-label rescue in the loss check. The DHR shape:
stored carries the bare "Key <Quarter> <Year> Results" section
heading the current extractor drops, and live serves one more
genuine content line in its place (the CEO-quote paragraph, the
first full-year bullet, or a 4th Key Results bullet). The heading
repeats the quarter the headline already names, carries no figure,
and the extractor's section path strips section headings
everywhere else — so the swap trades a redundant label for real
content and the gate blesses it. S7 refuses the addition by
design; S4 refuses the heading loss by design. The full-cache
blast moves exactly the DHR x7 rows (SKIP-loss 155 -> 148) and
moves no other cohort.
"""
import sys

sys.path.insert(0, "scripts")

from batch254_repair import _is_key_results_heading, sweep_gate_s11

_TAGLINE = "Innovation at the speed of life"
_HEADLINE = "Danaher Reports Third Quarter 2024 Results"
_DATELINE = (
    "WASHINGTON D.C., October 22, 2024-- Danaher Corporation (NYSE: DHR) "
    "(the “Company”) today announced results for the quarter ended "
    "September 27, 2024. All results in this release reflect only "
    "continuing operations unless otherwise noted."
)
_HEADING = "Key Third Quarter 2024 Results"
_BULLETS = [
    "• Net earnings were $818 million, or $1.12 per diluted common share and non-GAAP adjusted diluted net earnings per common share were $1.71.",
    "• Revenues increased 3.0% year-over-year to $5.8 billion and non-GAAP core revenue increased 0.5%.",
    "• Operating cash flow was $1.5 billion and non-GAAP free cash flow was $1.2 billion.",
]
_QUOTE = (
    "Rainer M. Blair, President and Chief Executive Officer, stated, "
    "“Our team delivered strong third quarter results, including "
    "better-than-expected revenue growth. We were especially pleased "
    "with the continued positive momentum in our bioprocessing business "
    "and believe Cepheid gained market share in molecular testing "
    "again this quarter.”"
)

_STORED = "\n".join([_TAGLINE, _HEADLINE, _DATELINE, _HEADING] + _BULLETS)
_LIVE = "\n".join([_TAGLINE, _HEADLINE, _DATELINE] + _BULLETS + [_QUOTE])


def test_s11_passes_on_the_dhr_quote_shape() -> None:
    assert sweep_gate_s11(_STORED, _LIVE) is None


def test_s11_passes_on_the_dhr_fourth_bullet_shape() -> None:
    # 2026-03-27 shape: the added line is a 4th Key Results bullet,
    # not the quote.
    live = "\n".join(
        [_TAGLINE, _HEADLINE, _DATELINE]
        + _BULLETS
        + ["• Non-GAAP core revenue increased 3.0% year-over-year."]
    )
    assert sweep_gate_s11(_STORED, live) is None


def test_heading_detector_is_exact() -> None:
    assert _is_key_results_heading("Key Third Quarter 2024 Results")
    assert _is_key_results_heading("Key Fourth Quarter 2024 Results")
    assert _is_key_results_heading("Key First Quarter 2026 Results")
    # A heading carrying a figure is content, not a bare label.
    assert not _is_key_results_heading(
        "Key Third Quarter 2024 Results $5.8 billion"
    )
    # A different label shape is not this gate's business.
    assert not _is_key_results_heading("Third Quarter 2024 Results")
    assert not _is_key_results_heading("Key Third Quarter Results")
    assert not _is_key_results_heading("Key 2024 Results")


def test_s11_still_refuses_a_dropped_bullet() -> None:
    # Live drops the cash-flow bullet entirely: real content loss,
    # not a heading label — the gate must refuse.
    live = "\n".join(
        [_TAGLINE, _HEADLINE, _DATELINE] + _BULLETS[:2] + [_QUOTE]
    )
    assert sweep_gate_s11(_STORED, live) == "loss"


def test_s11_still_refuses_a_changed_figure() -> None:
    # "$818 million" becomes "$819 million": the bullet is stored
    # content with a different figure — the heading rescue cannot
    # excuse it.
    live = _LIVE.replace("$818 million", "$819 million")
    assert sweep_gate_s11(_STORED, live) == "loss"


def test_s11_still_refuses_a_heading_with_a_figure() -> None:
    # The lost line carries a figure, so it is not a bare label.
    stored = _STORED.replace(
        _HEADING, "Key Third Quarter 2024 Results $5.8 billion"
    )
    assert sweep_gate_s11(stored, _LIVE) == "loss"


def test_s11_still_refuses_an_added_table_row() -> None:
    # Live adds a table row under the bullets: the addition is
    # policed by S4's added-table check, not waved through.
    live = _LIVE + "\nTotal revenues $5,800 $5,600 3%"
    assert sweep_gate_s11(_STORED, live) == "added-table"


def test_s11_still_refuses_a_dangling_tail() -> None:
    # Live ends on a dangling heading: S4's tail check still fires.
    live = _LIVE + "\nOutlook:"
    assert sweep_gate_s11(_STORED, live) == "tail"
