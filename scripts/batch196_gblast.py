"""Batch 196 guidance blast: dump extract_management_guidance over every
cached exhibit to <outdir>/<TICKER>_<PERIOD>.txt (one file per exhibit
with guidance). Run once with the new code, once with the old code
(git stash), then classify with scripts/batch193_gblast_analyze.py.
Usage: .venv/bin/python scripts/batch196_gblast.py <outdir>
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_management_guidance

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

n = 0
for name in sorted(os.listdir(CACHE)):
    if not name.endswith(".html"):
        continue
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    out = extract_management_guidance(html)
    if out:
        open(os.path.join(OUT, name[:-5] + ".txt"), "w", encoding="utf-8").write(out)
        n += 1
print(f"guidance texts: {n} -> {OUT}")
