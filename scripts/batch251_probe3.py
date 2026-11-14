"""Batch 251 probe3: test the candidate gate S9 shape across the whole
169-row loss cohort — the summary-heading swap.

Shape: the only stored lines lost are period headings
("YYYY <Quarter> Results" / "YYYY Full Year Results|Outlook"), and the
only live lines added are bullets at the tail of live. Report every row
that passes the shape, with its lost/added lines, so the doc check can
be judged before any gate is written.

Usage: .venv/bin/python scripts/batch251_probe3.py
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch251_probe import classify
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

_PERIOD_HEAD_RE = re.compile(
    r"^\d{4} (?:First|Second|Third|Fourth) Quarter Results$"
)
_FY_HEAD_RE = re.compile(r"^\d{4} Full Year (?:Results|Outlook)$")


def _is_period_head(ln: str) -> bool:
    s = ln.strip()
    return bool(_PERIOD_HEAD_RE.match(s) or _FY_HEAD_RE.match(s))


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    shape_hits: list[str] = []
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None or norm(stored) == norm(live):
            continue
        if classify(stored, live, html) != "loss":
            continue
        s_lines = non_empty(stored)
        l_lines = non_empty(live)
        s_norm = [norm(x) for x in s_lines]
        l_norm = [norm(x) for x in l_lines]
        l_set = set(l_norm)
        s_set = set(s_norm)
        lost = [x for x in s_lines if norm(x) not in l_set]
        added = [x for x in l_lines if norm(x) not in s_set]
        if not lost or not all(_is_period_head(x) for x in lost):
            continue
        if not added or not all(x.startswith("•") for x in added):
            continue
        # stored-minus-headings must equal live-minus-added, in order,
        # and the added bullets must be a tail run of live.
        s_kept = [x for x in s_norm if x in l_set]
        l_kept = [x for x in l_norm if x in s_set]
        if s_kept != l_kept:
            print(f"{key}: SHAPE-FAIL kept-order differs")
            continue
        tail = l_lines[len(l_lines) - len(added):]
        if [norm(x) for x in tail] != [norm(x) for x in added]:
            print(f"{key}: SHAPE-FAIL added not tail")
            continue
        shape_hits.append(key)
        print(f"{key}: SHAPE-HIT lost={len(lost)} added={len(added)}")
        for x in lost:
            print(f"    LOST  {x}")
        for x in added:
            print(f"    ADDED {x[:160]}")
    print(f"\nSHAPE HITS: {len(shape_hits)}: {', '.join(shape_hits)}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
