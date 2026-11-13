"""Batch 245 probe: decompose the 203 SKIP-loss rows left after batch 244
(first-diff cohort closed at 0; SKIP-loss 206 -> 203).

For every stored highlights row with a cached exhibit, classify under
the current extractor + gates S4/S5, and for each SKIP-loss row print
the lost stored lines: stored lines (after S4's chrome strip +
headline alignment + flattened split) that are absent from live
under norm() and are not S3 residue. The lost lines are what blocks
the swap — the probe groups them by shape so the next gate (S6)
can be scoped.

Also re-censuses the cohort totals to confirm 203.

Usage: .venv/bin/python scripts/batch245_probe.py > /tmp/batch245_dump.txt
"""
import os
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch241_repair import is_residue_s3
from batch242_repair import (
    _align_headline,
    _split_flattened,
    _strip_leading_chrome,
    sweep_gate_s4,
)
from batch244_repair import classify_s5
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

_QUOTE_RE = re.compile(r'[“"]([^”"]{20,})[”"]')
_FIGURE_RE = re.compile(r"[\$\d]")


def lost_lines(stored: str, live: str) -> list[str]:
    """Stored lines S4's loss check rejects, in stored order."""
    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    s_lines = _split_flattened(s_lines, l_lines)
    s_lines = _strip_leading_chrome(s_lines)
    s_lines, relation = _align_headline(s_lines, l_lines)
    if relation is None:
        return []
    live_set = set(l_lines)
    live_norm_set = {norm(x) for x in l_lines}
    lost = []
    for i, x in enumerate(s_lines):
        nxt = s_lines[i + 1] if i + 1 < len(s_lines) else ""
        if x not in live_set and norm(x) not in live_norm_set:
            if not is_residue_s3(x, nxt, live_set):
                lost.append(x)
    return lost


def shape(ln: str) -> str:
    """One-word shape bucket for a lost line."""
    s = ln.strip()
    if _QUOTE_RE.search(s) or s.startswith(("“", '"')):
        return "quote"
    if s.endswith(":") and len(s) < 80:
        return "heading-tail"
    if re.search(r"\b(announced|declared|approved|authorized|completed|"
                 r"acquired|entered into|launched|appointed|elected)\b",
                 s, re.IGNORECASE):
        return "strategic-bullet"
    if _FIGURE_RE.search(s) and len(s) > 120:
        return "figure-prose"
    if _FIGURE_RE.search(s):
        return "figure-line"
    if len(s) > 200:
        return "long-prose"
    return "short-prose"


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    totals: Counter[str] = Counter()
    loss_keys: list[str] = []
    shape_count: Counter[str] = Counter()
    shape_rows: dict[str, list[str]] = {}
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            totals["live-none"] += 1
            continue
        if norm(stored) == norm(live):
            totals["in-sync"] += 1
            continue
        r4 = sweep_gate_s4(stored, live)
        if r4 is None:
            totals["S4-repairable"] += 1
            continue
        cls5 = classify_s5(stored, live)
        if cls5:
            totals[f"S5-{cls5}"] += 1
            continue
        totals[f"SKIP-{r4}"] += 1
        if r4 == "loss":
            loss_keys.append(key)
            for ln in lost_lines(stored, live):
                sh = shape(ln)
                shape_count[sh] += 1
                shape_rows.setdefault(sh, []).append(f"{key} :: {ln[:160]}")
    print("CENSUS (current extractor + gates S4/S5):")
    for k, n in sorted(totals.items()):
        print(f"  {k}: {n}")
    print(f"\nLOSS ROWS: {len(loss_keys)}")
    print("\nLOST-LINE SHAPES:")
    for sh, n in shape_count.most_common():
        print(f"  {sh}: {n}")
    for sh in ("quote", "heading-tail", "strategic-bullet", "figure-prose",
               "figure-line", "long-prose", "short-prose"):
        items = shape_rows.get(sh, [])
        if not items:
            continue
        print(f"\n--- {sh.upper()} ({len(items)} lines) ---")
        for item in items[:60]:
            print(f"  {item}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
