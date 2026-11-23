"""Batch 260 probe: the 3 rows batch 259 left in loss (EIX x2, BRO
2026-09-30) plus the other SKIP-added-table / SKIP-fragment rows.

Diagnosis (batch 259's docstring misattributed the EIX cause):
- EIX x2: S4 "added-table" is tripped NOT by the added EPS bullet
  (hard_table is False on it) but by the leading contact line
  "Investor Relations: Sam Ramraj, (626) 302-2540" — the phone number
  matches _is_lede_data_row / _is_trailing_table_data_row. The line
  is present in stored too, but _strip_leading_chrome removes it
  from stored only, so the added-table scan sees it as live-only.
  Candidate fix A: strip leading chrome from the live lines as well
  (front-only, same predicate) before the added-table scan.
- BRO 2026-09-30: S4 "fragment" fires on live's second line
  "including total revenues of $1.7 billion, ..." — a lowercase
  headline continuation that stored carries in the same position.
  Candidate fix B: exempt the fragment refusal when live's second
  line equals stored's second line (post-alignment).

This probe lists every SKIP-added-table / SKIP-fragment row with its
offending line(s), then simulates fixes A and B across the full
cached census and reports exactly which rows change classification.

Usage: .venv/bin/python scripts/batch260_probe.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import hard_table, non_empty, norm
from batch242_repair import (
    _align_headline,
    _split_flattened,
    _strip_leading_chrome,
    sweep_gate_s4,
)
from batch244_repair import classify_s5
from batch247_repair import sweep_gate_s6
from batch248_repair import sweep_gate_s7
from batch250_repair import sweep_gate_s8
from batch251_repair import sweep_gate_s9
from batch253_repair import sweep_gate_s10
from batch254_repair import sweep_gate_s11
from batch255_repair import sweep_gate_s12
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def _s4_variant(stored, live, fix_a=False, fix_b=False):
    """Local copy of sweep_gate_s4 with candidate fixes toggled.

    Fix A: strip leading chrome from live lines before the
    added-table scan. Fix B: exempt the fragment refusal when live's
    second line equals stored's second line post-alignment.
    """
    from batch241_repair import _is_dateline_sentence, is_residue_s3
    from batch231_repair import has_dateline_table_shape, is_residue

    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    s_lines = _split_flattened(s_lines, l_lines)
    s_lines = _strip_leading_chrome(s_lines)
    s_lines, relation = _align_headline(s_lines, l_lines)
    if relation is None:
        return "first-diff"
    live_set = set(l_lines)
    live_has_dateline = any(_is_dateline_sentence(x) for x in l_lines)
    s_datelines = [x for x in s_lines if _is_dateline_sentence(x)]
    if not live_has_dateline:
        s_datelines = []
    live_norm_set = {norm(x) for x in l_lines}
    if not all(norm(d) in live_norm_set for d in s_datelines):
        return "dateline-mismatch"
    for i, x in enumerate(s_lines):
        nxt = s_lines[i + 1] if i + 1 < len(s_lines) else ""
        if x not in live_set and not is_residue_s3(x, nxt, live_set):
            return "loss"
    lfrac = sum(1 for x in l_lines if is_residue(x)) / max(len(l_lines), 1)
    if lfrac >= 0.4 or has_dateline_table_shape(l_lines):
        return "live-table"
    s_set = set(s_lines)
    scan_lines = _strip_leading_chrome(l_lines) if fix_a else l_lines
    if any(hard_table(x) for x in scan_lines if x not in s_set):
        return "added-table"
    last = l_lines[-1] if l_lines else ""
    if last not in s_set and (
        is_residue(last) or last.rstrip().endswith(":")
    ):
        return "tail"
    if len(l_lines) > 1 and l_lines[1][:1].islower():
        if fix_b and len(s_lines) > 1 and l_lines[1] == s_lines[1]:
            pass
        else:
            return "fragment"
    return None


def full_chain(stored, live, html, s4fn):
    """Run the gate chain with a given S4; return (bucket, detail)."""
    if norm(stored) == norm(live):
        return "B", None
    if s4fn(stored, live) is None:
        return "S4", None
    cls5 = classify_s5(stored, live)
    if cls5 is not None:
        return f"S5-{cls5}", None
    if sweep_gate_s6(stored, live, html) is None:
        return "S6", None
    if sweep_gate_s7(stored, live) is None:
        return "S7", None
    if sweep_gate_s8(stored, live, html) is None:
        return "S8", None
    if sweep_gate_s9(stored, live, html) is None:
        return "S9", None
    if sweep_gate_s10(stored, live) is None:
        return "S10", None
    if sweep_gate_s11(stored, live) is None:
        return "S11", None
    if sweep_gate_s12(stored, live) is None:
        return "S12", None
    return "SKIP-loss", None


def main():
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    targets = {}
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
        if r4 in ("added-table", "fragment"):
            s_lines = _strip_leading_chrome(
                _split_flattened(non_empty(stored), non_empty(live))
            )
            s_lines, _rel = _align_headline(s_lines, non_empty(live))
            s_set = set(s_lines)
            print(f"\n===== {key} S4={r4}")
            print(f"  live[0]: {non_empty(live)[0][:120]!r}")
            print(f"  live[1]: {non_empty(live)[1][:120]!r}")
            print(f"  stored[1]: {s_lines[1][:120]!r}" if len(s_lines) > 1 else "  stored: <1 line>")
            for x in non_empty(live):
                if x not in s_set and hard_table(x):
                    print(f"  HARD-TABLE added line: {x[:160]!r}")
            targets[key] = (stored, live, html)

    print("\n\n### Full-census simulation of fixes A and B")
    variants = {
        "current": lambda s, l: sweep_gate_s4(s, l),
        "fixA": lambda s, l: _s4_variant(s, l, fix_a=True),
        "fixB": lambda s, l: _s4_variant(s, l, fix_b=True),
        "fixA+B": lambda s, l: _s4_variant(s, l, fix_a=True, fix_b=True),
    }
    for name, fn in variants.items():
        moved = []
        for t, pe, stored in rows:
            key = f"{t}_{pe}"
            path = f"{CACHE}/{key}.html"
            if not os.path.exists(path):
                continue
            html = open(path, encoding="utf-8").read()
            live = extract_press_release_highlights(html)
            if live is None:
                continue
            before, _ = full_chain(stored, live, html, sweep_gate_s4)
            after, _ = full_chain(stored, live, html, fn)
            if before != after:
                moved.append((key, before, after))
        print(f"\n--- {name}: {len(moved)} rows change bucket")
        for key, b, a in moved:
            print(f"    {key}: {b} -> {a}")
    con.close()


if __name__ == "__main__":
    main()
