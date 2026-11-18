"""Batch 272 survey 2: lines containing 'highlights' with a trailing tail
after the word (', ...' etc.) that the current section anchor does NOT
match — the population an anchor widening would newly anchor.

Read-only.
"""
import glob
import os
import re
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
    seen: dict[str, list[str]] = {}
    for path in sorted(glob.glob(os.path.join(CACHE, "*.html"))):
        key = os.path.basename(path)[:-5]
        for ln in lines_of(path):
            if "highlight" not in ln.lower():
                continue
            if F._HIGHLIGHTS_SECTION_ANCHOR_RE.search(ln):
                continue
            # trailing tail after 'highlights': comma/semicolon + text
            m = re.search(r"highlights?\s*[,;:]\s*(.+)$", ln, re.IGNORECASE)
            if not m:
                continue
            tail = m.group(1)
            seen.setdefault(ln, []).append(key)
    print(f"{len(seen)} distinct non-anchor highlights-with-tail lines")
    for ln, keys in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        print(f"\n{len(keys)}x {ln!r}")
        print(f"   e.g. {', '.join(keys[:6])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
