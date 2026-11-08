"""Batch 214 cache-only blast: new default (9000-char cap, letter
fallback 4000, safe-harbor cut) vs old (4000) press-release highlights
extraction over every cached exhibit. No discovery, no fetching:
iterates the HTML cache so both runs see byte-identical input.
Filenames encode TICKER_period_end.

Every diff must be a pure extension: old ends with the truncation
ellipsis, new starts with old-minus-ellipsis, new never ends with
"…". Letter exhibits (AFRM/COIN shareholder letters falling through
to the standard path) must be byte-identical — the 4000 fallback cap
freezes them. F 2025-03-31 is the one safe-harbor cut: its new text
is a pure extension that ends at 5280 chars, before the "Cautionary
Note on Forward-Looking Statements" heading.

Usage:
  .venv/bin/python scripts/batch214_cache_blast.py hidden_files/blast214/h_new hidden_files/blast214/h_old
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

new_dir, old_dir = sys.argv[1], sys.argv[2]
os.makedirs(new_dir, exist_ok=True)
os.makedirs(old_dir, exist_ok=True)

files = sorted(f for f in os.listdir(CACHE) if f.endswith(".html"))
print(f"{len(files)} cached exhibits")
diffs = 0
identical = 0
for name in files:
    html = open(os.path.join(CACHE, name), encoding="utf-8").read()
    try:
        new = extract_press_release_highlights(html)
        old = extract_press_release_highlights(html, max_chars=4000)
    except Exception as exc:  # noqa: BLE001
        print(f"{name} EXTRACT FAILED: {exc}")
        continue
    stem = name[: -len(".html")]
    with open(os.path.join(new_dir, stem + ".txt"), "w", encoding="utf-8") as fh:
        fh.write(new or "None")
    with open(os.path.join(old_dir, stem + ".txt"), "w", encoding="utf-8") as fh:
        fh.write(old or "None")
    if (new or "None") != (old or "None"):
        diffs += 1
        # Every diff must be a pure extension of the old truncation.
        assert old is not None and new is not None, f"{name}: None mismatch"
        assert old.endswith("…"), f"{name}: old does not end with ellipsis"
        assert new.startswith(old[:-1].rstrip()), f"{name}: new is not an extension of old"
        assert not new.endswith("…"), f"{name}: new still truncated"
        assert "Cautionary Note on Forward-Looking Statements" not in new, (
            f"{name}: safe-harbor heading survived in new"
        )
        print(f"  DIFF {stem}: {len(old)} -> {len(new)}")
    else:
        identical += 1
print(f"wrote {len(files)} outputs; {diffs} diffs (all pure extensions), {identical} identical")
