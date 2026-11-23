"""Batch 262 probe 5: verify ALL 42 blast-changed exhibits — every added
line must be a bullet-led narrative line (◦/•), never table residue."""
import difflib
import json
import re
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

import tickerlens.data.filings as F
from tickerlens.data.filings import extract_press_release_highlights
from batch231_repair import hard_table, is_residue

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
OLD = re.compile(r"^(?:[•●–—◾]\s?|-\s|l\s|n\s)")
NEW = F._BULLET_LEAD_RE

before = json.load(open("/tmp/batch262_blast_before.json"))
after = json.load(open("/tmp/batch262_blast_after.json"))
changed = sorted(k for k in before if before[k] != after.get(k))

bad = []
total_added = 0
for key in changed:
    html = open(f"{CACHE}/{key}.html", encoding="utf-8", errors="replace").read()
    F._BULLET_LEAD_RE = OLD
    b = extract_press_release_highlights(html) or ""
    F._BULLET_LEAD_RE = NEW
    a = extract_press_release_highlights(html) or ""
    for line in difflib.unified_diff(b.split("\n"), a.split("\n"), lineterm=""):
        if line.startswith("+") and not line.startswith("+++"):
            total_added += 1
            text = line[1:]
            if text.strip() == "":
                continue
            if not text[:1] in "◦•":
                bad.append((key, "NOT-BULLET", text))
            if hard_table(text) or is_residue(text):
                bad.append((key, "TABLE-RESIDUE", text))
    # also: any removed lines?
    for line in difflib.unified_diff(b.split("\n"), a.split("\n"), lineterm=""):
        if line.startswith("-") and not line.startswith("---"):
            bad.append((key, "REMOVED", line[1:]))

print(f"changed exhibits: {len(changed)}; added lines: {total_added}")
print(f"bad lines: {len(bad)}")
for key, kind, text in bad:
    print(f"  {key} [{kind}] {text!r}")
