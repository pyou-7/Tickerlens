"""Batch 248 probe 2: size the gate-S7 (spacing-only) cohort.

For every SKIP-loss row under the current gates, check whether the
S4 loss check would pass if a stored line absent from live were
excused when it is spacing-equivalent to a live line:

  spacing_equivalent(a, b): the two lines have the same non-space
  character sequence AND the same digit runs (so no space deletion
  can merge "10 0" into "100"), i.e. they differ only by spaces
  that sit between non-digit characters or next to a curly quote.

Prints every candidate with its differing line pairs (char-level
opcodes) so the cohort can be judged by hand before any repair.
Also prints the S4/S5/S6 verdicts for the 7 "other" rows from the
batch-248 census, and the effect of a norm quote-space rule.

Usage: .venv/bin/python scripts/batch248_probe2.py
"""
import difflib
import os
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch242_repair import (
    _align_headline,
    _split_flattened,
    _strip_leading_chrome,
    sweep_gate_s4,
)
from batch244_repair import classify_s5
from batch247_repair import sweep_gate_s6
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

_DIGIT_RUN_RE = re.compile(r"\d+")


def _space_only_opcodes(a: str, b: str) -> list | None:
    """Opcodes between a and b if they differ only by spaces, else None."""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete" and a[i1:i2].strip() == "":
            continue
        if tag == "insert" and b[j1:j2].strip() == "":
            continue
        return None
    return sm.get_opcodes()


def spacing_equivalent(a: str, b: str) -> bool:
    """True when a and b differ only by spaces that never join two
    digit runs. The non-space character sequence must be identical
    (no content added/removed/changed) and the digit runs must be
    identical (a space between two digits can never be dropped or
    added — \"10 0\" vs \"100\" is a figure change, not spacing)."""
    if a == b:
        return True
    if "".join(a.split()) != "".join(b.split()):
        return False
    if _DIGIT_RUN_RE.findall(a) != _DIGIT_RUN_RE.findall(b):
        return False
    return _space_only_opcodes(a, b) is not None


def s7_would_repair(stored: str, live: str) -> tuple[bool, list]:
    """S4 entry + S4 loss check with the spacing-equivalence rescue.
    Returns (would_repair, rescued_pairs)."""
    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    s_lines = _split_flattened(s_lines, l_lines)
    s_lines = _strip_leading_chrome(s_lines)
    s_lines, relation = _align_headline(s_lines, l_lines)
    if relation is None:
        return False, []
    live_set = set(l_lines)
    rescued = []
    for x in s_lines:
        if x in live_set:
            continue
        match = next((y for y in l_lines if spacing_equivalent(x, y)), None)
        if match is None:
            return False, []
        rescued.append((x, match))
    return True, rescued


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    candidates: list[tuple[str, list]] = []
    other_rows: list[str] = []
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None or norm(stored) == norm(live):
            continue
        r4 = sweep_gate_s4(stored, live)
        r5 = classify_s5(stored, live)
        r6 = sweep_gate_s6(stored, live, html)
        if r4 == "loss" and r5 is None and r6 == "loss":
            ok, rescued = s7_would_repair(stored, live)
            if ok:
                candidates.append((key, rescued))
        elif r4 != "loss":
            other_rows.append(f"{key}: s4={r4} s5={r5} s6={r6}")
    print(f"S7 candidates: {len(candidates)}")
    for key, rescued in candidates:
        print(f"\n=== {key}: {len(rescued)} rescued line(s)")
        for a, b in rescued:
            sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag != "equal":
                    print(f"  {tag}: S[{i1}:{i2}]={a[max(0,i1-25):i2+25]!r} "
                          f"L[{j1}:{j2}]={b[max(0,j1-25):j2+25]!r}")
    print(f"\nOTHER rows ({len(other_rows)}):")
    for r in other_rows:
        print(f"  {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
