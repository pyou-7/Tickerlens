"""Batch 239 probe: the broad "new guidance found" cohort.

Batch 238 carried forward 11 diff-figures-added rows (AMT x3, CLX,
SPG x5, MCO x2): the new extraction ADDS a whole table/section the
stored row lacks — the broad form of the "new guidance found" gate,
which needs section verification before a stored row may be
overwritten. Also carried: GEV x2 (the new extraction DROPS a
historical-results table — the removal direction) and 2
unexplained-diff rows.

This probe dumps stored-vs-new diffs for all 13 rows plus the 2
unexplained-diff rows, and classifies the added/removed lines:
are they contiguous table rows, do they carry guidance figures
($ / %), and what heading/section do they sit under in the new
text? The section anchor is what would make a broad gate F
provable: the added content must sit inside the same guidance
section as the stored text, not in a different vintage or section.

Usage: .venv/bin/python scripts/batch239_probe.py
"""
import difflib
import json
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch236_repair import _figures, _residue
from batch238_repair import _gate_e_passes
from batch237_repair import _gate_a_passes, _gate_d_passes

DB = "tickerlens.db"
NEW_JSON = "hidden_files/blast238_guidance_new.json"


def _show_diff(ticker: str, period: str, stored: str, new_text: str) -> None:
    s_lines = [ln for ln in stored.splitlines() if ln.strip()]
    n_lines = [ln for ln in new_text.splitlines() if ln.strip()]
    print(f"===== {ticker} {period} =====")
    print(f"  stored lines: {len(s_lines)}, new lines: {len(n_lines)}")
    print(f"  added figures: {dict(_figures(new_text) - _figures(stored))}")
    print(f"  removed figures: {dict(_figures(stored) - _figures(new_text))}")
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        a=s_lines, b=n_lines, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        for ln in s_lines[i1:i2]:
            print(f"  - {ln[:160]}")
        for ln in n_lines[j1:j2]:
            print(f"  + {ln[:160]}")
    print()


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

    added: list[tuple[str, str, str, str]] = []
    removed: list[tuple[str, str, str, str]] = []
    unexplained: list[tuple[str, str, str, str]] = []
    for ticker, period, stored in rows:
        match = None
        for key, val in by_ticker.get(ticker, []):
            if key.endswith("_" + period + ".html"):
                match = (key, val)
                break
        if match is None or match[1] is None or match[1] == stored:
            continue
        key, new_text = match
        lines = [ln for ln in new_text.splitlines() if ln.strip()]
        if _residue(lines):
            continue
        if _gate_a_passes(stored, new_text):
            continue
        if _gate_d_passes(stored, new_text):
            continue
        if _gate_e_passes(stored, new_text):
            continue
        f_new, f_stored = _figures(new_text), _figures(stored)
        if f_new - f_stored and not (f_stored - f_new):
            added.append((ticker, period, stored, new_text))
        elif f_stored - f_new and not (f_new - f_stored):
            removed.append((ticker, period, stored, new_text))
        else:
            unexplained.append((ticker, period, stored, new_text))

    print(f"pure-add rows: {len(added)}")
    print(f"pure-remove rows: {len(removed)}")
    print(f"mixed/unexplained rows: {len(unexplained)}")
    print()
    for ticker, period, stored, new_text in sorted(added):
        _show_diff(ticker, period, stored, new_text)
    for ticker, period, stored, new_text in sorted(removed):
        _show_diff(ticker, period, stored, new_text)
    for ticker, period, stored, new_text in sorted(unexplained):
        _show_diff(ticker, period, stored, new_text)


if __name__ == "__main__":
    main()
