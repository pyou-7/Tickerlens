"""Batch 263 blast diff: line-by-line before/after over the full-text
blast JSONs. Every added line must be a bullet-led narrative line;
flag any removed line, any non-bullet addition, any table-residue
addition, and any dangling colon-ended opener served.
"""
import difflib
import json
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import hard_table, is_residue

before = json.load(open("/tmp/batch263_text_before.json"))
after = json.load(open("/tmp/batch263_text_after3.json"))
changed = sorted(k for k in before if before[k].get("text", "") != after[k].get("text", ""))
print(f"changed exhibits: {len(changed)}")

bad = []
total_added = 0
total_removed = 0
for key in changed:
    b = before[key].get("text", "").split("\n")
    a = after[key].get("text", "").split("\n")
    added = []
    removed = []
    for line in difflib.unified_diff(b, a, lineterm=""):
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            removed.append(line[1:])
    total_added += len([x for x in added if x.strip()])
    total_removed += len([x for x in removed if x.strip()])
    print(f"--- {key}: +{len([x for x in added if x.strip()])} -{len([x for x in removed if x.strip()])}")
    for x in added:
        if not x.strip():
            continue
        print(f"    + {x[:180]!r}")
        if not x[:1] in "•◦-·▪■○*":
            bad.append((key, "NOT-BULLET", x))
        if hard_table(x) or is_residue(x):
            bad.append((key, "TABLE-RESIDUE", x))
        if x.rstrip().endswith(":") and x is added[-1]:
            bad.append((key, "DANGLING-COLON", x))
    for x in removed:
        if x.strip():
            print(f"    - {x[:180]!r}")
            bad.append((key, "REMOVED", x))

print(f"\ntotal added non-blank: {total_added}; total removed non-blank: {total_removed}")
print(f"bad lines: {len(bad)}")
for key, kind, text in bad:
    print(f"  {key} [{kind}] {text[:180]!r}")
