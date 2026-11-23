"""Batch 239 highlights blast: old-vs-new live highlights extraction over
every cached exhibit. The fix touches the shared footnote opener, so
the highlights blast must be diffed line-by-line alongside guidance.

Usage:
  .venv/bin/python scripts/batch239_highlights_blast.py /home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast239/h_old
  # (after the fix)
  .venv/bin/python scripts/batch239_highlights_blast.py /home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast239/h_new
  diff -r /home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast239/h_old /home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast239/h_new
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

out_dir = sys.argv[1]
os.makedirs(out_dir, exist_ok=True)

files = sorted(f for f in os.listdir(CACHE) if f.endswith(".html"))
print(f"{len(files)} cached exhibits")
for name in files:
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    try:
        full = extract_press_release_highlights(html)
    except Exception as exc:  # noqa: BLE001
        print(f"{name} EXTRACT FAILED: {exc}")
        continue
    out_path = os.path.join(out_dir, name[: -len(".html")] + ".txt")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(full or "None")
print(f"wrote {len(files)} outputs to {out_dir}")
