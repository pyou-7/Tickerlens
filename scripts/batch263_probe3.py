"""Batch 263 probe 3: dump raw body lines around the EL nine-months
opener and the DIS Sports/Experiences parents, straight from the cached
exhibits, to see the exact sub-list shape and what follows it.
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import _html_to_text, _split_bullet_runs

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def dump(key, anchor, before=2, after=14):
    html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
    text = _html_to_text(html)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    lines = _split_bullet_runs(lines)
    print(f"===== {key} =====")
    for idx, ln in enumerate(lines):
        if anchor in ln:
            for j in range(max(0, idx - before), min(len(lines), idx + after)):
                mark = ">>>" if j == idx else "   "
                print(f"{mark} [{j}] {ln[:200]!r}")
            print()
            return
    print("anchor not found:", anchor)


dump("EL_2025-03-31", "For the nine months ended March 31, 2025:")
dump("EL_2024-06-30", "For the nine months")
dump("DIS_2025-09-27", "Sports: Q4 segment")
dump("DIS_2025-09-27", "Experiences:")
