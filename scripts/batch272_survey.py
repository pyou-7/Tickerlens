"""Batch 272 survey: fragment-runs (per _drop_table_fragment_runs) that sit
directly under a colon-ended bullet — the population a DRI-style
sub-list exemption would touch. For each cached exhibit, print the
preceding bullet line and the run rows.

Read-only.
"""
import glob
import os
import sys
from collections import Counter

sys.path.insert(0, "src")

from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def lines_of(path):
    html = open(path, encoding="utf-8", errors="replace").read()
    text = F._html_to_text(html)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    return F._split_bullet_runs(lines)


def main() -> int:
    total = Counter()
    hits = []
    for path in sorted(glob.glob(os.path.join(CACHE, "*.html"))):
        key = os.path.basename(path)[:-5]
        lines = lines_of(path)
        i = 0
        while i < len(lines):
            j = i
            if (
                F._looks_like_table_heading(lines[j])
                and j + 2 < len(lines)
                and F._looks_like_table_fragment(lines[j + 1])
                and F._looks_like_table_fragment(lines[j + 2])
            ):
                j += 1
            k = j
            while k < len(lines) and F._looks_like_table_fragment(lines[k]):
                k += 1
            if k - i >= 3:
                prev = lines[i - 1] if i > 0 else ""
                run = lines[i:k]
                if prev.startswith("•") and prev.rstrip().endswith(":"):
                    hits.append((key, prev, run))
                    total["colon-bullet-preceded"] += 1
                else:
                    total["other-preceded"] += 1
                i = k
                continue
            i += 1
    print(f"exhibits scanned; fragment-runs: {dict(total)}")
    print(f"colon-bullet-preceded runs: {len(hits)}")
    for key, prev, run in hits:
        print(f"\n== {key}  prev={prev!r}")
        for r in run:
            print(f"    {r!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
