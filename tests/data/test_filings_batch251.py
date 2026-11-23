"""Batch 251 regression tests.

Gate S9 (scripts/batch251_repair.py): the summary-heading swap.
A stored highlights row whose only difference from the live
extraction is the release's two summary-table column headings —
"YYYY <Quarter> Results" and "YYYY Full Year Results|Outlook" —
plus the live text serving more bullets from the same run, may be
re-synced to the live text (CHD x4).

The safety property is the doc check, not the shape: the two
headings must sit consecutively in the source document immediately
before the first stored bullet, and the added bullets must follow
the last stored bullet consecutively — the headings head the bullet
run and the added bullets continue it. A period heading over prose
could never pass, because the lines around it would not be the
run's bullets. The stored row must lose nothing else (a stored
sub-headline live drops, as on the other three CHD rows, blocks
the swap), the added lines must all be bullets at live's tail,
stored-minus-headings must equal live-minus-added in order, and
live must be clean by the S5 live-side checks. The full-cache
census re-syncs exactly the four CHD rows (SKIP-loss 169 -> 165)
and moves no other cohort.
"""
import sys

sys.path.insert(0, "scripts")

from batch251_repair import sweep_gate_s9, verify_summary_headings
from tickerlens.data.filings import extract_press_release_highlights
from tests.data.test_filings import _contact_release_html

_HEADLINE = "CHURCH & DWIGHT REPORTS Q3 2024 RESULTS"
_SUBHEADS = [
    "Q3 NET SALES, GROSS MARGIN, ADJUSTED EPS AND CASH FLOW EXCEED OUTLOOK",
    "AFFIRMS FULL YEAR NET SALES AND ADJUSTED EPS OUTLOOK",
]
_HEADINGS = ["2024 Third Quarter Results", "2024 Full Year Outlook"]
_BULLETS = [
    "• Net Sales +3.8%: Domestic +3.3%, Int’l +9.5%, SPD -8.0%",
    "• Organic Sales¹ +4.3%: Domestic +3.3%, Int’l +8.1%, SPD +7.5%",
    "• Adjusted Gross Margin¹ +60 bps",
    "• Reported Loss per Share -$0.31, Adjusted EPS $0.79 ¹",
    "• YTD Cash from Operations of $863.9 million",
    "• Net Sales +3.5%; Organic Sales +4.0%¹",
]
_DATELINE = (
    "EWING, NJ, November 1, 2024 – Church & Dwight Co., Inc. (NYSE: CHD) "
    "today announced the Company exceeded its outlook."
)


def _chd_html(*doc_lines: str) -> str:
    return _contact_release_html(
        "Church & Dwight Co., Inc.",
        "News Release",
        "Contact:",
        "Rick Dierker",
        _HEADLINE,
        *_SUBHEADS,
        *_HEADINGS,
        *doc_lines,
        _DATELINE,
    )


def _chd_live() -> str:
    live = extract_press_release_highlights(_chd_html(*_BULLETS))
    assert live is not None
    return live


def _chd_stored(*extra_lost: str) -> str:
    return "\n\n".join(
        [_HEADLINE, *_SUBHEADS, *_HEADINGS, *_BULLETS[:2], *extra_lost]
    )


def test_extractor_drops_summary_headings_and_serves_bullets() -> None:
    # The real extractor, end to end, on the CHD shape: the two
    # summary-table column headings never reach the served text, and
    # all six quarter bullets are served (batch 259: the bullet-run
    # extension completes the run to the 12-line cap — the old
    # 6-line budget stopped it at 4).
    live = _chd_live()
    assert "2024 Third Quarter Results" not in live
    assert "2024 Full Year Outlook" not in live
    for bullet in _BULLETS:
        assert bullet in live


def test_gate_s9_passes_chd_shape() -> None:
    stored = _chd_stored()
    live = _chd_live()
    html = _chd_html(*_BULLETS)
    assert sweep_gate_s9(stored, live, html) is None


def test_gate_s9_passes_full_year_results_variant() -> None:
    # The Q4 shape: "2024 Fourth Quarter Results" + "2024 Full Year
    # Results" (not Outlook) — same gate, same doc proof.
    headings = ["2024 Fourth Quarter Results", "2024 Full Year Results"]
    html = _contact_release_html(
        "Church & Dwight Co., Inc.",
        "News Release",
        "Contact:",
        "Rick Dierker",
        _HEADLINE,
        *_SUBHEADS,
        *headings,
        *_BULLETS,
        _DATELINE,
    )
    live = extract_press_release_highlights(html)
    assert live is not None
    stored = "\n\n".join([_HEADLINE, *_SUBHEADS, *headings, *_BULLETS[:2]])
    assert sweep_gate_s9(stored, live, html) is None


def test_gate_s9_refuses_lost_subheadline() -> None:
    # A stored sub-headline live still drops blocks the swap — a swap
    # would lose real news, so the gate refuses even though the
    # headings match. The doc carries the sub-headline between the
    # subheads and the headings, exactly as the real exhibit does.
    # Batch 252: the case used to ride on "ANNOUNCES 4% DIVIDEND
    # INCREASE" — the extractor now serves that line, so the refusal
    # rides on "AFFIRMS LONG-TERM TARGETS", a 4-word verb line live
    # still drops by design (it reads as a heading, and sparing it
    # would starve a real bullet under the 6-line budget).
    html = _contact_release_html(
        "Church & Dwight Co., Inc.",
        "News Release",
        "Contact:",
        "Rick Dierker",
        _HEADLINE,
        *_SUBHEADS,
        "AFFIRMS LONG-TERM TARGETS",
        *_HEADINGS,
        *_BULLETS,
        _DATELINE,
    )
    live = extract_press_release_highlights(html)
    assert live is not None
    assert "AFFIRMS LONG-TERM TARGETS" not in live
    stored = "\n\n".join(
        [
            _HEADLINE,
            *_SUBHEADS,
            "AFFIRMS LONG-TERM TARGETS",
            *_HEADINGS,
            *_BULLETS[:2],
        ]
    )
    assert sweep_gate_s9(stored, live, html) == "loss"


def test_gate_s9_refuses_single_heading() -> None:
    # Only one period heading lost — not the two-column summary
    # shape, so the gate refuses.
    stored = "\n\n".join(
        [_HEADLINE, *_SUBHEADS, _HEADINGS[0], *_BULLETS[:2]]
    )
    live = _chd_live()
    html = _chd_html(*_BULLETS)
    assert sweep_gate_s9(stored, live, html) == "loss"


def test_gate_s9_refuses_two_quarter_headings() -> None:
    # Two headings of the same kind (quarter + quarter) are not the
    # quarter/full-year column pair.
    headings = ["2024 Third Quarter Results", "2024 Fourth Quarter Results"]
    html = _contact_release_html(
        "Church & Dwight Co., Inc.",
        "News Release",
        "Contact:",
        "Rick Dierker",
        _HEADLINE,
        *_SUBHEADS,
        *headings,
        *_BULLETS,
        _DATELINE,
    )
    live = extract_press_release_highlights(html)
    assert live is not None
    stored = "\n\n".join([_HEADLINE, *_SUBHEADS, *headings, *_BULLETS[:2]])
    assert sweep_gate_s9(stored, live, html) == "loss"


def test_gate_s9_refuses_non_bullet_addition() -> None:
    # Live adds a prose line (a quote opener) instead of bullets —
    # the added lines must all be bullets.
    live = "\n\n".join(
        [_HEADLINE, *_SUBHEADS, *_BULLETS[:2], _BULLETS[2], _DATELINE]
    )
    stored = _chd_stored()
    html = _chd_html(*_BULLETS)
    assert sweep_gate_s9(stored, live, html) == "loss"


def test_gate_s9_refuses_added_bullets_not_tail() -> None:
    # The added bullets must be a tail run of live — an added bullet
    # buried mid-text (with a stored bullet after it) is not the
    # continuation of the run.
    live = "\n\n".join(
        [_HEADLINE, *_SUBHEADS, _BULLETS[0], _BULLETS[2], _BULLETS[1]]
    )
    stored = _chd_stored()
    html = _chd_html(*_BULLETS)
    assert sweep_gate_s9(stored, live, html) == "loss"


def test_gate_s9_refuses_broken_doc_run() -> None:
    # The doc check, not the shape, is the proof: a prose line
    # between the headings and the first bullet means the headings
    # do not head the bullet run, so the swap is refused even
    # though the shape matches.
    html = _contact_release_html(
        "Church & Dwight Co., Inc.",
        "News Release",
        "Contact:",
        "Rick Dierker",
        _HEADLINE,
        *_SUBHEADS,
        *_HEADINGS,
        "The table below summarizes the quarter.",
        *_BULLETS,
        _DATELINE,
    )
    live = _chd_live()
    stored = _chd_stored()
    assert sweep_gate_s9(stored, live, html) == "loss"
    assert verify_summary_headings(html, stored, live) is False


def test_gate_s9_refuses_added_bullets_not_consecutive_in_doc() -> None:
    # The added bullets must follow the stored bullets consecutively
    # in the doc — a filler line between the stored bullets and the
    # added ones breaks the run and the gate refuses.
    html = _contact_release_html(
        "Church & Dwight Co., Inc.",
        "News Release",
        "Contact:",
        "Rick Dierker",
        _HEADLINE,
        *_SUBHEADS,
        *_HEADINGS,
        *_BULLETS[:2],
        "The table below summarizes the quarter.",
        *_BULLETS[2:4],
        _DATELINE,
    )
    live = _chd_live()
    stored = _chd_stored()
    assert sweep_gate_s9(stored, live, html) == "loss"


def test_gate_s9_refuses_bullet_mismatch() -> None:
    # A stored bullet that differs from live's (a figure changed)
    # is a content difference, not a heading swap.
    stored = "\n\n".join(
        [
            _HEADLINE,
            *_SUBHEADS,
            *_HEADINGS,
            _BULLETS[0],
            "• Organic Sales¹ +4.9%: Domestic +3.3%, Int’l +8.1%, SPD +7.5%",
        ]
    )
    live = _chd_live()
    html = _chd_html(*_BULLETS)
    assert sweep_gate_s9(stored, live, html) == "loss"


def test_gate_s9_refuses_residue_heavy_live() -> None:
    # Live is residue-heavy (the S5 live-side checks): stored and
    # live both carry five flattened table rows alongside the
    # bullets, so live is 5/12 residue and the gate refuses with
    # "live-table" even though the heading shape matches. The doc
    # check is never reached — the live-side refusal fires first.
    _rows = [
        "2024 2023 Change Net Sales $1,501.1 $1,446.2 3.8%",
        "2024 2023 Change Gross Profit $684.2 $639.5 7.0%",
        "2024 2023 Change Operating Income $210.4 $198.7 5.9%",
        "2024 2023 Change Net Income $142.9 $131.2 8.9%",
        "2024 2023 Change Diluted EPS $0.58 $0.53 9.4%",
    ]
    stored = "\n\n".join(
        [_HEADLINE, *_SUBHEADS, *_HEADINGS, *_rows, *_BULLETS[:2]]
    )
    live = "\n\n".join([_HEADLINE, *_SUBHEADS, *_rows, *_BULLETS[:4]])
    html = _chd_html(*_BULLETS, *_rows)
    assert sweep_gate_s9(stored, live, html) == "live-table"


def test_gate_s9_refuses_more_than_ten_added_bullets() -> None:
    # Batch 259 recalibrated the tail bound from 4 to 10: the lede's
    # bullet-run extension serves up to 12 content lines, so a CHD
    # swap can now add up to 9 tail bullets. 11 is outside the gate.
    # The cap fires before the doc check, so the extra bullets need
    # not sit in the document (same construction as the old test):
    # stored keeps 2 bullets, live serves 13, so 11 are added.
    extra = [
        "• Cash from Operations ~$1.1 billion (previously $1.08 billion)",
        "• Gross Margin expanded 100 basis points to 46.0%",
        "• Adjusted EPS grew 12% to $1.02",
        "• Net Sales grew 4% to $1.5 billion",
        "• Organic Sales grew 5% in the quarter",
        "• Reported EPS grew 8% to $0.95",
        "• Cash from Operations of $400 million",
    ]
    live = "\n\n".join([_HEADLINE, *_SUBHEADS, *_BULLETS, *extra])
    stored = _chd_stored()
    html = _chd_html(*_BULLETS)
    assert sweep_gate_s9(stored, live, html) == "loss"
