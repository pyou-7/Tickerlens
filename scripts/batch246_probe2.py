"""Batch 246 probe 2: where does the quote sit in the doc?

For a sample of quote-only rows, dump stored vs live line by line, then
locate the stored quote lines inside the source doc's line list and
print the surrounding context (10 lines before/after), so the mechanism
is visible: is the quote inside the lede budget, right after the lede,
inside a Highlights section the collector cut short, or after a table
break?

Usage: .venv/bin/python scripts/batch246_probe2.py > /tmp/batch246_dump2.txt
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty
from batch245_probe import lost_lines
from batch246_probe import is_quote_line
from tickerlens.data.filings import (
    _html_to_text,
    _split_bullet_runs,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

SAMPLE = [
    "ADI_2024-11-02",
    "ADI_2025-05-03",
    "DECK_2024-09-30",
    "F_2025-03-31",
    "PLTR_2024-09-30",
    "APLD_2025-08-31",
]


def doc_lines(html: str) -> list[str]:
    text = _html_to_text(html)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    return _split_bullet_runs(lines)


def main() -> int:
    con = sqlite3.connect(DB)
    for key in SAMPLE:
        t, pe = key.split("_", 1)
        stored = con.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = ? AND q.period_end = ?",
            (t, pe),
        ).fetchone()[0]
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        lost = lost_lines(stored, live)
        print(f"\n{'=' * 100}\n{key}\n{'=' * 100}")
        print("--- STORED (numbered) ---")
        for i, ln in enumerate(non_empty(stored)):
            mark = "  <-- LOST" if ln in lost else ""
            print(f"  S{i:02d}: {ln[:200]}{mark}")
        print("--- LIVE (numbered) ---")
        for i, ln in enumerate(non_empty(live)):
            print(f"  L{i:02d}: {ln[:200]}")
        print("--- QUOTE POSITION IN DOC ---")
        lines = doc_lines(html)
        for q in [x for x in lost if is_quote_line(x)]:
            frag = q.strip()[:60]
            hit = [i for i, ln in enumerate(lines) if frag[:40] in ln or ln[:40] in frag]
            print(f"  quote frag: {frag!r} -> doc lines {hit}")
            for h in hit[:1]:
                lo, hi = max(0, h - 8), min(len(lines), h + 10)
                for j in range(lo, hi):
                    print(f"    D{j:03d}: {lines[j][:180]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
