"""Batch 232 guidance blast: old-vs-new live guidance extraction over
every cached exhibit.

No discovery, no fetching: iterates the HTML cache at CACHE so both runs
see byte-identical input. Filenames encode TICKER_period_end.

Usage:
  .venv/bin/python scripts/batch232_guidance_blast.py /home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast232/g_new
  git stash -- src/tickerlens tests
  .venv/bin/python scripts/batch232_guidance_blast.py /home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast232/g_old
  git stash pop
  diff -r /home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast232/g_old /home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast232/g_new
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_management_guidance

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

out_dir = sys.argv[1] if len(sys.argv) > 1 else "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast232/g_new"
os.makedirs(out_dir, exist_ok=True)

files = sorted(f for f in os.listdir(CACHE) if f.endswith(".html"))
print(f"{len(files)} cached exhibits")
for name in files:
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    try:
        g = extract_management_guidance(html)
    except Exception as exc:  # noqa: BLE001
        print(f"{name} EXTRACT FAILED: {exc}")
        continue
    out_path = os.path.join(out_dir, name[: -len(".html")] + ".txt")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(g or "None")
print(f"wrote {len(files)} outputs to {out_dir}")
