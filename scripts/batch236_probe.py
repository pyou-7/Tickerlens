"""Batch 236 probe: dump stored vs batch-235-new guidance text for the
carried-forward cohorts:

  * BMY 2025-03-31 / 2025-06-30 / 2025-09-30 — gate-B-skipped in batch 235:
    the removed figures sit in wrapped footnote-def continuation lines
    the gate does not recognize as chrome.
  * The 3 unexplained-diff rows: CHD 2026-03-31 (truncated prose line),
    ELV 2025-09-30 (wrapped footnote-def continuation),
    EMR 2024-09-30 (wrapped-label fragment).

Usage: .venv/bin/python scripts/batch236_probe.py
Prints a unified diff per row (stored -> new) plus the figure multiset
delta, so the gate extension can be designed from real shapes.
"""
import difflib
import json
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")

from tickerlens.data.filings import _GUIDANCE_FIGURE_RE

DB = "tickerlens.db"
NEW_JSON = "hidden_files/blast235_guidance_new.json"
OLD_JSON = "hidden_files/blast233_guidance_new.json"

TARGETS = [
    ("BMY", "2025-03-31"),
    ("BMY", "2025-06-30"),
    ("BMY", "2025-09-30"),
    ("CHD", "2026-03-31"),
    ("ELV", "2025-09-30"),
    ("EMR", "2024-09-30"),
]


def _figures(text: str) -> Counter:
    return Counter(
        re.sub(r"\s+", "", m.group(0)) for m in _GUIDANCE_FIGURE_RE.finditer(text)
    )


def main() -> None:
    with open(NEW_JSON) as f:
        new_map = json.load(f)
    with open(OLD_JSON) as f:
        old_map = json.load(f)
    con = sqlite3.connect(DB)
    for ticker, period in TARGETS:
        stored = con.execute(
            "SELECT q.management_guidance FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = ? AND q.period_end = ?",
            (ticker, period),
        ).fetchone()
        if not stored:
            print(f"===== {ticker} {period}: NO DB ROW =====")
            continue
        stored = stored[0]
        key = next(
            (k for k in new_map if k.startswith(ticker + "_") and k.endswith("_" + period + ".html")),
            None,
        )
        print(f"===== {ticker} {period} ({key}) =====")
        if key is None:
            print("  no blast exhibit")
            print("--- stored ---")
            print(stored)
            print()
            continue
        new_text = new_map[key]
        old_text = old_map.get(key)
        print(f"  stored == new: {stored == new_text}")
        print(f"  stored == old-blast: {stored == old_text}")
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
        print()


if __name__ == "__main__":
    main()
