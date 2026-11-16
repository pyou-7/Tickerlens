"""Batch 264 probe: dump the raw text lines of the DIS_2025-09-27 exhibit
around the Experiences parent, to see the stranded 2nd child and what
follows it (how many ◦ children, next heading, end of highlights).
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import _html_to_text

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

html = open(f"{CACHE}/DIS_2025-09-27.html", encoding="utf-8").read()
text = _html_to_text(html)
lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
print("total non-empty lines:", len(lines))
for idx, ln in enumerate(lines):
    if "Experiences" in ln or "Domestic Parks" in ln or "International Parks" in ln:
        for j in range(max(0, idx - 1), min(len(lines), idx + 12)):
            mark = ">>>" if j == idx else "   "
            print(f"{mark} [{j}] {ln if j == idx else lines[j]!r}"[:400])
        print()
