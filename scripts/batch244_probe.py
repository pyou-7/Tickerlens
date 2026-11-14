"""Batch 244 probe: decompose the 15 SKIP-first-diff rows left after
batch 243 (as censused by the batch-243 probe) under gates S4/S5, and
source-verify the s5-fy-stored rows against their own docs.

Also re-prints the before/after blast counts for the batch-244
extractor fix (quarter-scoped Highlights sections beat full-year
ones): the fix flips AGNC x2 to S4-repairable, flips CART x2 + ANET
x1 out of in-sync (their stored rows hold the FULL YEAR section),
and EBAY x1 + FTNT x1 were already SKIP-loss — all five are
s5-fy-stored.

Usage: .venv/bin/python scripts/batch244_probe.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch242_repair import sweep_gate_s4
from batch244_repair import classify_s5, verify_fy_stored
from tickerlens.data.filings import (
    _extract_highlights_sections_anchored,
    _highlights_section_scope,
    _html_to_text,
    _split_bullet_runs,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"

FIRST_DIFF_243 = [
    "AGNC_2024-12-31", "AGNC_2025-12-31", "APO_2024-09-30",
    "APO_2024-12-31", "APO_2025-03-31", "APO_2025-06-30",
    "APO_2025-09-30", "APO_2025-12-31", "APO_2026-03-31",
    "APO_2026-06-30", "COIN_2026-03-31", "CSCO_2026-01-24",
    "CSCO_2026-04-25", "CSCO_2026-07-25", "NFLX_2025-06-30",
]
FY_STORED = [
    "ANET_2024-12-31", "CART_2024-12-31", "CART_2025-12-31",
    "EBAY_2024-12-31", "FTNT_2025-12-31",
]


def main() -> int:
    con = sqlite3.connect(DB)
    print("FIRST-DIFF-243 DECOMPOSITION (new extractor):")
    for key in FIRST_DIFF_243:
        t, pe = key.split("_")[0], key.split("_", 1)[1]
        stored = con.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik WHERE c.ticker = ? "
            "AND q.period_end = ?",
            (t, pe),
        ).fetchone()[0]
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        r4 = sweep_gate_s4(stored, live) if live else "live-none"
        cls5 = classify_s5(stored, live) if live else None
        fy = verify_fy_stored(html, stored, live) if live else False
        verdict = "S4" if r4 is None else (cls5 or ("s5-fy-stored" if fy else f"SKIP-{r4}"))
        print(f"  {key}: {verdict}")
    print("\nFY-STORED VERIFICATION (doc's own sections):")
    for key in FY_STORED:
        t, pe = key.split("_")[0], key.split("_", 1)[1]
        stored = con.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik WHERE c.ticker = ? "
            "AND q.period_end = ?",
            (t, pe),
        ).fetchone()[0]
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        lines = [ln.strip() for ln in _html_to_text(html).split("\n") if ln.strip()]
        lines = _split_bullet_runs(lines)
        secs = _extract_highlights_sections_anchored(lines)
        anchors = [
            f"{_highlights_section_scope(a)}:{a[:48]}" for a, _, _ in secs
        ]
        print(f"  {key}: verify={verify_fy_stored(html, stored, live)}")
        print(f"    anchors: {anchors}")
        print(f"    stored[0]: {non_empty(stored)[0][:90]}")
        print(f"    live[0]:   {non_empty(live)[0][:90]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
