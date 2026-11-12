"""Batch 237 diagnose: for each of the 27 diff-figures rows, print exactly
which census check blocks it — new-residue, added figures, gate-B chrome
shortfall (removed figures not sitting in chrome-flagged lines, with the
unflagged removed lines listed), or unexplained diff lines.
"""
import json
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch236_repair import (
    _chrome_flags,
    _diff_explainable,
    _figures,
    _removed_indices,
    _residue,
)

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

    for ticker, period, stored in sorted(rows):
        match = None
        for key, val in by_ticker.get(ticker, []):
            if key.endswith("_" + period + ".html"):
                match = (key, val)
                break
        if match is None or match[1] is None or match[1] == stored:
            continue
        new_text = match[1]
        lines = [ln for ln in new_text.splitlines() if ln.strip()]
        probs = _residue(lines)
        f_new, f_stored = _figures(new_text), _figures(stored)
        expl = _diff_explainable(stored, new_text)
        if f_new == f_stored and not expl and not probs:
            continue
        if probs:
            print(f"{ticker} {period}: NEW-RESIDUE {probs}")
            continue
        if f_new - f_stored:
            print(f"{ticker} {period}: ADDED {dict(f_new - f_stored)}")
            continue
        s_lines = [ln for ln in stored.splitlines() if ln.strip()]
        n_lines = [ln for ln in new_text.splitlines() if ln.strip()]
        flags = _chrome_flags(s_lines)
        chrome_figs: Counter = Counter()
        unflagged_removed = []
        for idx in sorted(_removed_indices(s_lines, n_lines)):
            if flags[idx]:
                chrome_figs.update(_figures(s_lines[idx]))
            else:
                unflagged_removed.append((idx, s_lines[idx]))
        shortfall = (f_stored - f_new) - chrome_figs
        print(f"{ticker} {period}: removed-figs={dict(f_stored - f_new)} "
              f"chrome-covered={dict(chrome_figs)} shortfall={dict(shortfall)} "
              f"expl={expl}")
        for idx, ln in unflagged_removed:
            print(f"    unflagged removed [{idx}]: {ln[:160]!r}")
    con.close()


if __name__ == "__main__":
    main()
