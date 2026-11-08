"""Batch 213 survey: uncapped management-guidance lengths over every cached
exhibit, vs the 4000-char capped output. Answers the batch-212 carry-forward
(AMT/CHD/CLX 4000-char budget rethink): how much genuine content does the
cap cut, and what cap would cover it?

Usage:
  .venv/bin/python scripts/batch213_survey.py hidden_files/blast213/survey.txt
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_management_guidance

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

out_path = sys.argv[1]
os.makedirs(os.path.dirname(out_path), exist_ok=True)

files = sorted(f for f in os.listdir(CACHE) if f.endswith(".html"))
print(f"{len(files)} cached exhibits")

rows = []
for name in files:
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    try:
        capped = extract_management_guidance(html)
        uncapped = extract_management_guidance(html, max_chars=10**9)
    except Exception as exc:  # noqa: BLE001
        print(f"{name} EXTRACT FAILED: {exc}")
        continue
    cap_len = len(capped) if capped else 0
    unc_len = len(uncapped) if uncapped else 0
    rows.append((name, cap_len, unc_len))

with open(out_path, "w", encoding="utf-8") as fh:
    for name, cap_len, unc_len in rows:
        fh.write(f"{name}\t{cap_len}\t{unc_len}\n")

nonnull = [r for r in rows if r[2] > 0]
over4000 = [r for r in nonnull if r[2] > 4000]
print(f"non-null guidance: {len(nonnull)}")
print(f"uncapped > 4000: {len(over4000)}")
for cap in (5000, 6000, 8000, 10000, 12000):
    print(f"uncapped > {cap}: {sum(1 for r in nonnull if r[2] > cap)}")
unc = sorted(r[2] for r in nonnull)
n = len(unc)
for pct in (50, 75, 90, 95, 99):
    print(f"p{pct}: {unc[int(n * pct / 100)]}")
print(f"max uncapped: {unc[-1]}")
print("top 15 uncapped:")
for name, cap_len, unc_len in sorted(rows, key=lambda r: -r[2])[:15]:
    print(f"  {name}: capped={cap_len} uncapped={unc_len} lost={unc_len - cap_len}")
