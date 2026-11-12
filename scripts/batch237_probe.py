"""Batch 237 probe: dump stored vs batch-235-new guidance text for the
27 diff-figures rows carried forward from batch 236 — the rows the
repair gates skip because the figure multisets differ:

  * AMT x3 — the new extraction adds a whole table the stored row lacks.
  * AAL x3 — the new extraction drops the press-release header lines
    (title / dateline / "Page 3"), a lede/anchor change, not a fuser
    change.
  * CHD x2, FDX, GEV x2, GIS x2, V 2024-09-30, DAL 2024-12-31, DPZ, MU,
    META, MCO x2, SPG x5, CLX 2025-12-31 — mostly different-vintage
    sections or footnote-def prose drops.

Usage: .venv/bin/python scripts/batch237_probe.py
Prints a unified diff per row (stored -> new) plus the figure multiset
delta, so a lede/header-drop gate (or per-shape fixes) can be designed
from real shapes.
"""
import difflib
import json
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch236_repair import _figures, _diff_explainable, _residue

DB = "tickerlens.db"
NEW_JSON = "hidden_files/blast235_guidance_new.json"


def main() -> None:
    with open(NEW_JSON) as f:
        new_map = json.load(f)
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.management_guidance "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.management_guidance IS NOT NULL"
    ).fetchall()
    by_ticker: dict[str, list[tuple[str, str]]] = {}
    for key, val in new_map.items():
        by_ticker.setdefault(key.split("_")[0], []).append((key, val))

    targets = []
    for ticker, period, stored in rows:
        match = None
        for key, val in by_ticker.get(ticker, []):
            if key.endswith("_" + period + ".html"):
                match = (key, val)
                break
        if match is None or match[1] is None or match[1] == stored:
            continue
        new_text = match[1]
        lines = [ln for ln in new_text.splitlines() if ln.strip()]
        if _residue(lines):
            continue
        f_new, f_stored = _figures(new_text), _figures(stored)
        expl = _diff_explainable(stored, new_text)
        if f_new == f_stored and not expl:
            continue
        if f_new - f_stored:
            targets.append((ticker, period, stored, new_text, "added"))
            continue
        # gate B check: removed figures in dropped chrome?
        s_lines = [ln for ln in stored.splitlines() if ln.strip()]
        n_lines = [ln for ln in new_text.splitlines() if ln.strip()]
        from batch236_repair import _chrome_flags, _removed_indices
        flags = _chrome_flags(s_lines)
        chrome_figs: Counter = Counter()
        for idx in sorted(_removed_indices(s_lines, n_lines)):
            if flags[idx]:
                chrome_figs.update(_figures(s_lines[idx]))
        removed_figs = f_stored - f_new
        if removed_figs - chrome_figs:
            targets.append((ticker, period, stored, new_text, "removed"))
            continue
        if expl:
            continue
        # would be gate B — not a diff-figures row
    print(f"diff-figures rows: {len(targets)}")
    for ticker, period, stored, new_text, kind in sorted(targets):
        print(f"\n===== {ticker} {period} [{kind}] =====")
        fig_new = _figures(new_text or "")
        fig_stored = _figures(stored or "")
        print(f"  figures only in stored: {list((fig_stored - fig_new).elements())}")
        print(f"  figures only in new:    {list((fig_new - fig_stored).elements())}")
        print("--- diff stored -> new ---")
        for ln in difflib.unified_diff(
            (stored or "").splitlines(), (new_text or "").splitlines(),
            lineterm="", n=1,
        ):
            print(ln)


if __name__ == "__main__":
    main()
