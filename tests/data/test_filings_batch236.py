"""Batch 236: the wrapped footnote-def continuation gate — the 3
unexplained-diff rows carried forward from batch 234 (CHD 2026-03-31,
ELV 2025-09-30, EMR 2024-09-30) plus the BMY 2025-03/06/09 footnote-drop
rows gate B skipped in batch 235, and the 2 CARR fuse-only rows batch
235 missed.

Root cause, all in the repair gate (scripts/batch236_repair.py), not the
extractor — the live extraction was already clean; only the stored rows
were stale:
- A footnote definition that wraps across two stored lines leaves its
  continuation line unexplained: BMY's "3 February was calculated ...
  foreign" / "exchange rates as of April 23, 2025.", EMR's
  "2 Underlying orders do not" / "include AspenTech.", ELV's bare "3."
  def "... serves as the estimated full" / "year adjustment amount.".
  The gate now recognizes a def-continuation: the previous stored line
  is a footnote-def line that ends mid-sentence and the line itself
  starts lowercase and is not a table row.
- CHD's stored row ends on a dangling boilerplate fragment,
  "Church & Dwight Co., Inc. (NYSE: CHD) will…", truncated by the
  collector. The gate now accepts a removed last line that ends with
  "…" and carries no figures as a tail-truncated fragment.
- Gate B's chrome-figure accounting is tightened to removed lines only
  (batch 235 counted chrome figures over all stored lines, which could
  mask a removed figure that also appears in a kept chrome line).

Live pins run the gate's explainability check against the real stored
rows and the batch-235 blast extraction; the unit pins cover the
continuation predicate, the chrome-flag walk, and the tail-truncation
clause directly.
"""
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def _load_script():
    path = REPO / "scripts" / "batch236_repair.py"
    spec = importlib.util.spec_from_file_location("batch236_repair", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rep = _load_script()

OLD_JSON = REPO / "hidden_files" / "blast233_guidance_new.json"
NEW_JSON = REPO / "hidden_files" / "blast235_guidance_new.json"


def _old_and_new(ticker: str, period: str) -> tuple[str, str]:
    """Frozen pre-233 (old) vs batch-235 (new) blast extractions — stable
    inputs, so the pins stay meaningful after the stored rows are
    re-synced."""
    old_map = json.loads(OLD_JSON.read_text())
    new_map = json.loads(NEW_JSON.read_text())
    key = ticker + "_" + period + ".html"
    return old_map[key], new_map[key]


def test_continuation_after_wrapped_opener():
    lines = [
        "3 February was calculated using foreign exchange rates as of January 9, 2025, and April was calculated using foreign",
        "exchange rates as of April 23, 2025.",
    ]
    flags = rep._chrome_flags(lines)
    assert flags == [True, True]


def test_continuation_after_bare_key_def():
    lines = [
        "3.",
        "Adjustment item represents the midpoint of a projected range and serves as the estimated full",
        "year adjustment amount.",
    ]
    flags = rep._chrome_flags(lines)
    assert flags == [True, True, True]


def test_continuation_chain_stops_at_terminal_punctuation():
    # The def line ends with a period, so the next lowercase line is a
    # new sentence, not a continuation.
    lines = [
        "1.",
        "Adjustment item resides in the Corporate & Other reportable segment.",
        "something lowercase that follows.",
    ]
    flags = rep._chrome_flags(lines)
    assert flags == [True, True, False]


def test_lowercase_line_after_content_is_not_chrome():
    lines = [
        "Total Revenues",
        "some lowercase note.",
    ]
    flags = rep._chrome_flags(lines)
    assert flags == [False, False]


def test_value_line_after_opener_is_not_continuation():
    lines = [
        "2 Underlying orders do not",
        "$2.98",
    ]
    flags = rep._chrome_flags(lines)
    assert flags == [True, False]


def test_tail_truncation_clause():
    assert rep._is_tail_truncation(
        "Church & Dwight Co., Inc. (NYSE: CHD) will…", True
    )
    # Not the last line: a truncated fragment mid-text is suspicious.
    assert not rep._is_tail_truncation(
        "Church & Dwight Co., Inc. (NYSE: CHD) will…", False
    )
    # No ellipsis marker: a complete last line is content.
    assert not rep._is_tail_truncation("Church & Dwight Co., Inc.", True)
    # A truncated line carrying a figure is content until proven otherwise.
    assert not rep._is_tail_truncation("Sales will be $23 billion…", True)


def test_gate_explainable_bmy_2025_03_31():
    stored, new = _old_and_new("BMY", "2025-03-31")
    assert rep._diff_explainable(stored, new) == []


def test_gate_explainable_bmy_2025_06_30():
    stored, new = _old_and_new("BMY", "2025-06-30")
    assert rep._diff_explainable(stored, new) == []


def test_gate_explainable_bmy_2025_09_30():
    stored, new = _old_and_new("BMY", "2025-09-30")
    assert rep._diff_explainable(stored, new) == []


def test_gate_explainable_elv_2025_09_30():
    stored, new = _old_and_new("ELV", "2025-09-30")
    assert rep._diff_explainable(stored, new) == []


def test_gate_explainable_emr_2024_09_30():
    stored, new = _old_and_new("EMR", "2024-09-30")
    assert rep._diff_explainable(stored, new) == []


def test_gate_explainable_chd_2026_03_31():
    stored, new = _old_and_new("CHD", "2026-03-31")
    assert rep._diff_explainable(stored, new) == []


def test_gate_explainable_carr_2026_06_30():
    stored, new = _old_and_new("CARR", "2026-06-30")
    assert rep._diff_explainable(stored, new) == []


def test_gate_explainable_carr_2026_09_30():
    stored, new = _old_and_new("CARR", "2026-09-30")
    assert rep._diff_explainable(stored, new) == []
