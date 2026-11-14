"""Batch 250 regression tests.

Gate S8 (scripts/batch250_repair.py): the trailing-guidance swap.
A stored highlights row whose only difference from the live
extraction is a trailing run opening on the release's guidance
section — the heading (\"Full Year YYYY Financial Guidance\"), the
guidance intro sentence, and the first rows of the guidance table —
may be re-synced to the live text (BIIB x3).

The safety property is the doc check, not the shape: the tail must
appear consecutively in the source document right after live's
last line (bare page-number lines skipped — Biogen paginates the
exhibit), with a guidance-table continuation line immediately
after it. A guidance heading over prose live drops could never
pass, because the line after it would be prose, not table
continuation. The stored prefix must equal live exactly, the tail
is at most 5 lines, opens on a full-line guidance heading, and
carries no bullets; live must be clean by the S5 live-side checks.
The full-cache census re-syncs exactly the three BIIB rows
(SKIP-loss 172 -> 169) and moves no other cohort.
"""
import sys

sys.path.insert(0, "scripts")

from batch250_repair import (
    _is_guidance_continuation,
    _is_guidance_head,
    sweep_gate_s8,
    verify_trailing_guidance,
)
from tickerlens.data.filings import extract_press_release_highlights
from tests.data.test_filings import _contact_release_html

_BULLETS = [
    "• Third quarter 2024 GAAP and Non-GAAP collaboration profit "
    "sharing was a net expense of approximately $69 million.",
    "• Third quarter 2024 GAAP other expense was approximately "
    "$15 million.",
]
_FIN_POS = "Financial Position"
_CASH_BULLET = (
    "• Third quarter 2024 net cash flow from operations was "
    "approximately $936 million."
)
_SHARES_BULLET = (
    "• For the third quarter of 2024 the Company’s weighted average "
    "diluted shares were approximately 146 million."
)
_TAIL = [
    "Full Year 2024 Financial Guidance",
    "For the full year 2024, Biogen now expects a Non-GAAP diluted "
    "EPS guidance range as follows:",
    "Prior FY 2024 Guidance Updated FY 2024 Guidance",
    "Non-GAAP diluted EPS $15.75 to $16.25",
]
_AFTER = "Reflecting growth of ~9% at the mid-point*"
_AFTER2 = "$16.10 to $16.60"


def _biib_html(*tail: str, after: str = _AFTER) -> str:
    # The page-number line ("3") sits between the last highlights
    # bullet and the guidance heading, as in the real exhibit.
    return _contact_release_html(
        "Cambridge, Mass. – October 30, 2024",
        *_BULLETS,
        _FIN_POS,
        _CASH_BULLET,
        _SHARES_BULLET,
        "3",
        *tail,
        after,
        _AFTER2,
    )


def _live() -> str:
    live = extract_press_release_highlights(_biib_html(*_TAIL))
    assert live is not None
    return live


def _stored(*tail: str) -> str:
    return "\n".join(
        [
            "Cambridge, Mass. – October 30, 2024",
            *_BULLETS,
            _FIN_POS,
            _CASH_BULLET,
            _SHARES_BULLET,
            *tail,
        ]
    )


def test_extractor_stops_at_guidance_heading() -> None:
    live = _live()
    assert "Financial Guidance" not in live
    assert live.split("\n")[-1] == _SHARES_BULLET


def test_guidance_head_forms() -> None:
    assert _is_guidance_head("Full Year 2024 Financial Guidance")
    assert _is_guidance_head("Fiscal 2025 Financial Guidance")
    assert _is_guidance_head("Full Year 2026 Guidance")
    assert not _is_guidance_head("Full Year 2024 Business Update")
    assert not _is_guidance_head("Full Year 2024 Financial Guidance and Outlook")
    assert not _is_guidance_head(
        "• Full Year 2024 Financial Guidance"
    )
    assert not _is_guidance_head("Financial Guidance")


def test_guidance_continuation_forms() -> None:
    assert _is_guidance_continuation("Reflecting growth of ~9% at the mid-point*")
    assert _is_guidance_continuation("($0.95)")
    assert _is_guidance_continuation("Updated Guidance $14.50 to $15.50")
    assert _is_guidance_continuation("$16.10 to $16.60")
    assert not _is_guidance_continuation(
        "Biogen will host a conference call to discuss the results."
    )
    assert not _is_guidance_continuation(
        "For the full year 2024, Biogen now expects a Non-GAAP diluted "
        "EPS guidance range as follows:"
    )


def test_s8_biib_shape_passes() -> None:
    live = _live()
    html = _biib_html(*_TAIL)
    assert sweep_gate_s8(_stored(*_TAIL), live, html) is None


def test_s8_fiscal_head_variant_passes() -> None:
    tail = ["Fiscal 2025 Financial Guidance", *_TAIL[1:]]
    html = _biib_html(*tail)
    live = extract_press_release_highlights(html)
    assert live is not None
    assert live.split("\n")[-1] == _SHARES_BULLET
    assert sweep_gate_s8(_stored(*tail), live, html) is None


def test_s8_non_guidance_head_refused() -> None:
    tail = ["Full Year 2024 Business Update", *_TAIL[1:]]
    live = _live()
    html = _biib_html(*tail)
    assert sweep_gate_s8(_stored(*tail), live, html) == "loss"


def test_s8_prefix_mismatch_refused() -> None:
    # Stored drops a live bullet: not a trailing-guidance row.
    live = _live()
    html = _biib_html(*_TAIL)
    stored = "\n".join(
        [
            "Cambridge, Mass. – October 30, 2024",
            _BULLETS[0],
            _FIN_POS,
            _CASH_BULLET,
            _SHARES_BULLET,
            *_TAIL,
        ]
    )
    assert sweep_gate_s8(stored, live, html) == "loss"


def test_s8_bullet_in_tail_refused() -> None:
    tail = [*_TAIL, "• Updated Guidance $14.50 to $15.50"]
    live = _live()
    html = _biib_html(*tail)
    assert sweep_gate_s8(_stored(*tail), live, html) == "loss"


def test_s8_tail_over_five_lines_refused() -> None:
    tail = [*_TAIL, _AFTER, _AFTER2]
    live = _live()
    html = _biib_html(*tail)
    assert sweep_gate_s8(_stored(*tail), live, html) == "loss"


def test_s8_doc_run_broken_refused() -> None:
    # A filler line between the last bullet and the guidance heading
    # breaks the consecutive doc run: the tail is not the next
    # section in the document.
    html = _contact_release_html(
        "Cambridge, Mass. – October 30, 2024",
        *_BULLETS,
        _FIN_POS,
        _CASH_BULLET,
        _SHARES_BULLET,
        "3",
        "About Biogen",
        *_TAIL,
        _AFTER,
        _AFTER2,
    )
    live = _live()
    assert sweep_gate_s8(_stored(*_TAIL), live, html) == "loss"


def test_s8_prose_after_tail_refused() -> None:
    # The line after the tail is prose, not a guidance-table
    # continuation: the heading does not head a table.
    html = _biib_html(
        *_TAIL,
        after="Biogen will host a conference call to discuss the results.",
    )
    live = _live()
    assert sweep_gate_s8(_stored(*_TAIL), live, html) == "loss"


def test_verify_trailing_guidance_page_number_skip() -> None:
    live = _live()
    html = _biib_html(*_TAIL)
    assert verify_trailing_guidance(html, live, _TAIL)


def test_verify_trailing_guidance_no_after_line() -> None:
    # The tail is the last thing in the document: nothing proves it
    # heads a table, so verification fails closed.
    html = _contact_release_html(
        "Cambridge, Mass. – October 30, 2024",
        *_BULLETS,
        _FIN_POS,
        _CASH_BULLET,
        _SHARES_BULLET,
        "3",
        *_TAIL,
    )
    live = _live()
    assert not verify_trailing_guidance(html, live, _TAIL)
