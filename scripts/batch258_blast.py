"""Batch 258 blast: extract highlights from every cached exhibit in
blast_html and record headline + full-text hash. Run before and after
a fix; diff the two JSONs to measure blast radius.

Usage: .venv/bin/python scripts/batch258_blast.py <out.json>
"""
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def main():
    out_path = sys.argv[1]
    results = {}
    files = sorted(glob.glob(os.path.join(CACHE, "*.html")))
    for f in files:
        key = os.path.basename(f)[:-5]
        with open(f, encoding="utf-8", errors="replace") as fh:
            html = fh.read()
        try:
            hl = extract_press_release_highlights(html)
        except Exception as e:  # noqa: BLE001 - blast must never die mid-run
            results[key] = {"error": f"{type(e).__name__}: {e}"}
            continue
        results[key] = {
            "headline": (hl or "").split("\n\n")[0].strip() if hl else None,
            "len": len(hl) if hl else 0,
            "sha": hashlib.sha256((hl or "").encode()).hexdigest()[:12]
            if hl
            else None,
        }
    json.dump(results, open(out_path, "w"), indent=1)
    print(f"wrote {out_path} ({len(results)} entries)", flush=True)


if __name__ == "__main__":
    main()
