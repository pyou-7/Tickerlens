"""Batch 247 regression tests.

Two pieces, both closing the ADSK x6 rows batch 246 carried forward:

1. A norm rule (scripts/batch231_repair.py): spacing around a double
   hyphen is canonicalized when a 4-digit year precedes it, so the
   seed-era "SAN FRANCISCO, MAY 22, 2025 -- Autodesk ..." dateline
   equals the live "2025-- Autodesk ..." one. The year anchor is
   load-bearing: a general collapse would erase the "Label -- prose"
   marker the batch-244 S5 classifier keys on, and the full suite
   caught exactly that — so the rule stays narrow.

2. Gate S6 (scripts/batch247_repair.py): the stored row may end on a
   trailing table-furniture run — a bare period label ("First Quarter
   Fiscal 2026") plus the results-table units header ("(In millions,
   except percentages and per share amounts) Q1 FY26 YoY Change").
   The gate is doc-aware, not shape-only: the run must appear
   consecutively in the source doc after live's last line, with a
   table-residue line immediately after it — proving the label heads
   the results table rather than prose live drops. The full-cache
   census flips zero rows under the norm rule alone; the gate
   re-syncs exactly the six ADSK rows (SKIP-loss 189 -> 183).
"""
import sys

sys.path.insert(0, "scripts")

from batch231_repair import norm
from batch247_repair import (
    _is_bare_period_label,
    _is_table_units_header,
    sweep_gate_s6,
)
from tickerlens.data.filings import extract_press_release_highlights
from tests.data.test_filings import _contact_release_html

_HEADLINE = "AUTODESK, INC. ANNOUNCES FISCAL 2026 FIRST QUARTER RESULTS"
_BULLET = (
    "- First quarter revenue grew 15 percent, and 16 percent on a "
    "constant currency basis, to $1.6 billion"
)
# The live dateline (glued dash) and the stored one (spaced dash)
# differ only in "--" spacing — the norm rule's whole job.
_DATELINE_LIVE = (
    "SAN FRANCISCO, MAY 22, 2025-- Autodesk, Inc. (NASDAQ: ADSK) "
    "today reported financial results for the first quarter of fiscal "
    "2026, ended April 30, 2025."
)
_DATELINE_STORED = _DATELINE_LIVE.replace("2025-- ", "2025 -- ")
_QUOTES = [
    "“Against an uncertain backdrop, our strong performance set us up "
    "well for the year,” said Andrew Anagnost, Autodesk president and "
    "chief executive officer.",
    "“Q1 was another strong quarter. We have not seen changes in "
    "overall business momentum,” said Janesh Moorjani, Autodesk CFO.",
]
_LABEL = "First Quarter Fiscal 2026"
_UNITS = "(In millions, except percentages and per share amounts) Q1 FY26 YoY Change"
_DATA_ROW = "Revenue $ 1,633 15 %"


def _adsk_html(*tail: str) -> str:
    return _contact_release_html(
        _HEADLINE, _BULLET, _DATELINE_LIVE, *_QUOTES, *tail
    )


def _adsk_stored(*tail: str) -> str:
    return "\n".join(
        [_HEADLINE, _BULLET, _DATELINE_STORED, *_QUOTES, *tail]
    )


def test_norm_collapses_double_hyphen_spacing() -> None:
    # The ADSK dateline pair: identical once the year-anchored "--"
    # spacing is gone.
    assert norm(_DATELINE_STORED) == norm(_DATELINE_LIVE)
    # A year-anchored dash collapses; a bare prose dash does not.
    assert norm("in fiscal 2025 -- revenue grew") == (
        "in fiscal 2025-- revenue grew"
    )
    assert norm("Revenue grew -- sharply this quarter") == (
        "Revenue grew -- sharply this quarter"
    )
    # The "Label -- prose" marker the S5 narrative classifier keys on
    # survives norm untouched — a general "--" collapse broke two
    # batch-244 tests, which is why the rule is year-anchored.
    assert norm("Product Revenue -- increased sharply") == (
        "Product Revenue -- increased sharply"
    )
    # But content differences survive: only spaces are removed.
    assert norm("Q1 -- Q2") != norm("Q1 -- Q3")
    assert norm("Revenue $1.6 -- $1.7 billion") != norm(
        "Revenue $1.6 -- $1.8 billion"
    )


def test_bare_period_label_shapes() -> None:
    for q in ("First", "Second", "Third", "Fourth"):
        assert _is_bare_period_label(f"{q} Quarter Fiscal 2026")
    # The "Results" form is S3 residue, not the bare label.
    assert not _is_bare_period_label("First Quarter Fiscal 2026 Results")
    # No "Fiscal", no year, a bullet lead, or trailing prose: no match.
    assert not _is_bare_period_label("First Quarter 2026")
    assert not _is_bare_period_label("First Quarter Fiscal")
    assert not _is_bare_period_label("• First Quarter Fiscal 2026")
    assert not _is_bare_period_label(
        "First Quarter Fiscal 2026 was strong"
    )


def test_table_units_header_shapes() -> None:
    assert _is_table_units_header(_UNITS)
    assert _is_table_units_header(
        "(In millions, except per share data) Q3 FY27 YoY Change"
    )
    # No YoY Change column, no period code, no parenthetical: no match.
    assert not _is_table_units_header(
        "(In millions, except percentages and per share amounts) Q1 FY26"
    )
    assert not _is_table_units_header(
        "(In millions, except percentages and per share amounts) YoY Change"
    )
    assert not _is_table_units_header("Q1 FY26 YoY Change")
    assert not _is_table_units_header(
        "(In millions) Total Net Revenue $ 1,633 15 %"
    )


def test_gate_s6_repairs_adsk_shape() -> None:
    # The full ADSK shape: live serves headline + bullet + dateline +
    # quotes; stored adds the spaced dateline plus the trailing
    # label + units header. The doc carries the run right before the
    # results-table data row, so the gate allows the swap.
    html = _adsk_html(_LABEL, _UNITS, _DATA_ROW)
    live = extract_press_release_highlights(html)
    assert live is not None
    assert _LABEL not in live
    assert _UNITS not in live
    stored = _adsk_stored(_LABEL, _UNITS)
    assert sweep_gate_s6(stored, live, html) is None


def test_gate_s6_repairs_label_only_run() -> None:
    # The 2026-04-30 row carries only the label, no units header.
    html = _adsk_html(_LABEL, _DATA_ROW)
    live = extract_press_release_highlights(html)
    assert live is not None
    stored = _adsk_stored(_LABEL)
    assert sweep_gate_s6(stored, live, html) is None


def test_gate_s6_refuses_run_not_before_table() -> None:
    # The same stored row, but the doc puts prose after the label
    # instead of table data: the run does not head a table, so the
    # doc verification refuses and the row stays loss.
    html = _adsk_html(
        _LABEL, _UNITS, "Revenue grew nicely this quarter."
    )
    live = extract_press_release_highlights(html)
    assert live is not None
    stored = _adsk_stored(_LABEL, _UNITS)
    assert sweep_gate_s6(stored, live, html) == "loss"


def test_gate_s6_refuses_content_after_label() -> None:
    # A real content bullet after the furniture run: the tail is not
    # furniture-only, so the gate refuses.
    html = _adsk_html(
        _LABEL, _UNITS, _DATA_ROW,
        "• Repurchased $500 million of shares during the quarter",
    )
    live = extract_press_release_highlights(html)
    assert live is not None
    stored = _adsk_stored(
        _LABEL, _UNITS,
        "• Repurchased $500 million of shares during the quarter",
    )
    assert sweep_gate_s6(stored, live, html) == "loss"


def test_gate_s6_refuses_label_mid_row() -> None:
    # The label sits mid-row, over a bullet live drops: the S3
    # section-subheading guard refuses it (the next line is not in
    # live), and the dropped bullet is unexplained too — so the gate
    # refuses. A mid-row label rescues nothing.
    html = _adsk_html(_LABEL, _UNITS, _DATA_ROW)
    live = extract_press_release_highlights(html)
    assert live is not None
    stored = "\n".join(
        [
            _HEADLINE,
            _LABEL,
            "• Repurchased $500 million of shares during the quarter",
            _BULLET,
            _DATELINE_STORED,
            *_QUOTES,
        ]
    )
    assert sweep_gate_s6(stored, live, html) == "loss"
