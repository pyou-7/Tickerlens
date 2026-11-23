"""Batch 192 survey: #-led lines, '*-led lines, '-more-' across the cached exhibits."""
import os, re, sys
from collections import Counter
sys.path.insert(0, "src")
from tickerlens.data.filings import _html_to_text, _split_bullet_runs

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
hash_lines = Counter()
star_lines = Counter()
more_files = 0
more_total = 0
for name in sorted(os.listdir(CACHE)):
    if not name.endswith(".html"):
        continue
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    text = _html_to_text(html)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    lines = _split_bullet_runs(lines)
    for ln in lines:
        if ln.startswith("#"):
            hash_lines[ln[:70]] += 1
        if ln.startswith("* "):
            star_lines[ln[:70]] += 1
        if ln.strip().lower() == "-more-":
            more_total += 1
    if any(ln.strip().lower() == "-more-" for ln in lines):
        more_files += 1
print("=== #-led lines (distinct, top 30) ===")
for ln, n in hash_lines.most_common(30):
    print(f"{n:4d}  {ln!r}")
print("=== '* '-led lines (distinct, top 40) ===")
for ln, n in star_lines.most_common(40):
    print(f"{n:4d}  {ln!r}")
print(f"=== '-more-': {more_total} occurrences in {more_files} files ===")
