"""Batch 193 guidance-blast analyzer: classify every old-vs-new diff.

Removed lines must be one of: footnote-def / asterisk-note / rounding-note
block lines, '-more-', teleconference/access lines, or next-section content
(results narrative, segment prose, About prose, risk/disclaimer prose) that
the new section-end break drops. Added lines must be genuine guidance
content freed by the skipped footnotes (guidance bullets, outlook prose,
outlook-table lines) — never footnote lines, '-more-', teleconference, or
next-section prose.

Also lists exhibits that lost guidance entirely (in base, not in new) and
exhibits that gained guidance (in new, not in base).
"""
import difflib
import os
import re
import sys

sys.path.insert(0, "src")
from tickerlens.data.filings import (
    _ASTERISK_NOTE_LEAD_RE,
    _FOOTNOTE_DEF_RE,
    _footnote_def_block_len,
    _asterisk_note_block_len,
    _rounding_note_block_len,
)

BASE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gblast193/base"
NEW = sys.argv[2] if len(sys.argv) > 2 else "/tmp/gblast193/new8"

# Correct-removal shapes: a removed line matching one of these is next-section
# content, not a guidance loss — conference-call notices, datelines, CEO
# quotes ("... said, ..."), metric-glossary definitions ("Term: definition
# sentence" or "Term ... represents/refers to ..." — Axon's Statistical
# Definitions, Chipotle's metric glossary), and table headers for
# results/segment tables.
NOT_A_LOSS = re.compile(
    r"conference call|webcast|replay|"
    r"said,|said \"|"
    r"^[A-Z][A-Za-z ]{3,40}: [A-Z][a-z]|"
    r"^[A-Z][A-Za-z ,']{3,60}\b(represent[s]?|refer[s]? to|is defined as)\b",
    re.IGNORECASE,
)

base_files = {f for f in os.listdir(BASE) if f.endswith(".txt")}
new_files = {f for f in os.listdir(NEW) if f.endswith(".txt")}
print(f"base: {len(base_files)}  new: {len(new_files)}")
print(f"lost guidance entirely: {sorted(base_files - new_files)}")
print(f"gained guidance: {sorted(new_files - base_files)}")

GUIDANCE_WORDS = re.compile(
    r"\b(expect|guidance|outlook|forecast|target|anticipat|project|revenue|eps|margin|capex|capital expenditures)\b",
    re.IGNORECASE,
)
FOOTNOTE_WORDS = re.compile(
    r"^(#|\*|\(\d+\)|\d{1,3}\s)|non-GAAP financial measure|is defined as|are defined as",
    re.IGNORECASE,
)
JUNK_WORDS = re.compile(
    r"^(-more-|Page \d+ of \d+|About |Cautionary Note|Forward-Looking Statements|"
    r"teleconference|conference call|webcast|Consolidated Results|Results by Business Segment|"
    r"News and Highlights|Recent News)",
    re.IGNORECASE,
)

n_diff = 0
removed_total = added_total = 0
bad_removed = []
bad_added = []
unclassified_removed = []
for name in sorted(base_files & new_files):
    b = open(os.path.join(BASE, name), encoding="utf-8").read()
    n = open(os.path.join(NEW, name), encoding="utf-8").read()
    if b == n:
        continue
    n_diff += 1
    b_lines = [l for l in b.split("\n\n")]
    n_lines = [l for l in n.split("\n\n")]
    sm = difflib.SequenceMatcher(a=b_lines, b=n_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            for ln in b_lines[i1:i2]:
                removed_total += 1
                if (
                    _footnote_def_block_len([ln], 0)
                    or _asterisk_note_block_len([ln], 0)
                    or _rounding_note_block_len([ln], 0)
                    or ln.strip() == "-more-"
                    or re.match(r"(?i)^earnings teleconference", ln)
                    or re.match(r"(?i)^access the fiscal.*teleconference", ln)
                ):
                    continue
                # A removed guidance-content line is a loss: a bullet or
                # prose line carrying guidance vocabulary that is not a
                # section heading and not results narrative.
                if GUIDANCE_WORDS.search(ln) and not re.match(
                    r"(?i)^(news and highlights|fiscal \d{4} .*consolidated results|"
                    r"fiscal \d{4} .*results by business segment|.*consolidated results)",
                    ln,
                ) and not NOT_A_LOSS.search(ln):
                    bad_removed.append((name, ln[:130]))
                else:
                    unclassified_removed.append((name, ln[:130]))
        if tag in ("insert", "replace"):
            for ln in n_lines[j1:j2]:
                added_total += 1
                if (
                    _footnote_def_block_len([ln], 0)
                    or _asterisk_note_block_len([ln], 0)
                    or _rounding_note_block_len([ln], 0)
                    or ln.strip() == "-more-"
                    or re.match(r"(?i)^earnings teleconference", ln)
                    or JUNK_WORDS.match(ln)
                ):
                    bad_added.append((name, ln[:130]))

print(f"\ndiff files: {n_diff}")
print(f"removed lines: {removed_total}, added lines: {added_total}")
print(f"removed lines flagged as guidance-content losses: {len(bad_removed)}")
for name, ln in bad_removed[:60]:
    print(f"  LOSS {name}: {ln!r}")
print(f"removed lines unclassified (next-section content expected): {len(unclassified_removed)}")
print(f"added lines flagged as junk: {len(bad_added)}")
for name, ln in bad_added[:60]:
    print(f"  JUNK-ADD {name}: {ln!r}")
# Save the unclassified removed lines for eyeballing.
with open("/tmp/gblast193_unclassified.txt", "w", encoding="utf-8") as fh:
    for name, ln in unclassified_removed:
        fh.write(f"{name}: {ln}\n")
print(f"\nunclassified removed lines saved to /tmp/gblast193_unclassified.txt ({len(unclassified_removed)} lines)")
with open("/tmp/gblast193_losses.txt", "w", encoding="utf-8") as fh:
    for name, ln in bad_removed:
        fh.write(f"{name}: {ln}\n")
print(f"flagged losses saved to /tmp/gblast193_losses.txt ({len(bad_removed)} lines)")
