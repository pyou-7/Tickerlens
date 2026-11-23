"""Batch 242 probe 3: test the CTVA single-line-split hypothesis.

CTVA's stored highlights are ONE line: the headline + bullets
flattened with " • " separators (seed-era flattening). The live
extraction has 11-15 lines: the same headline + the same bullets
as separate lines. If splitting the stored line on the bullet
separator yields parts that match the live lines (bullet glyph
stripped, under norm), the rows are repairable under a gate that
treats the single flattened line as its split parts.

Prints, per CTVA row, any split part that does not match a live
line and any live line not matched by a split part.

Usage: .venv/bin/python scripts/batch242_probe3.py
"""
import re
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

_SPLIT_RE = re.compile(r"\s+[•◦▪■●–—‣·○◆▸►]\s+")


def split_flattened(line: str) -> list[str]:
    """Split a seed-era single-line flattening into its headline +
    bullet parts. The first part is the headline; the rest are
    bullet texts (glyph stripped by the split)."""
    return [p.strip() for p in _SPLIT_RE.split(line.strip()) if p.strip()]


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = 'CTVA' AND q.press_release_highlights IS NOT NULL "
        "ORDER BY q.period_end"
    ).fetchall()
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        s_lines = non_empty(stored)
        l_lines = non_empty(live)
        assert len(s_lines) == 1, (key, len(s_lines))
        parts = split_flattened(s_lines[0])
        # Live lines with their leading bullet glyph stripped, so a
        # split part can compare equal to a live bullet line.
        live_bare = [re.sub(r"^[•◦▪■●–—‣·○◆▸►]\s+", "", x) for x in l_lines]
        print(f"=== {key}  parts {len(parts)} / live {len(l_lines)}")
        for i, p in enumerate(parts):
            if norm(p) not in {norm(x) for x in live_bare}:
                print(f"  PART {i} unmatched: {p[:180]}")
        live_norm = {norm(x) for x in live_bare}
        for j, x in enumerate(live_bare):
            if norm(x) not in {norm(p) for p in parts}:
                print(f"  LIVE {j} unmatched: {x[:180]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
