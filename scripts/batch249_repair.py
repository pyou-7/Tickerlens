"""Batch 249 repair: the highlights sweep — the pre-section executive
quote.

The batch-249 extractor fix prepends the executive-quote run that
sits between the dateline and a Highlights section heading to the
winning section (Palantir shape). Full-cache blast: 24 rows change,
0 rows lose content — 21 rows gain only quote lines (ADBE x6,
ANET x2, CRWD x4, CSX, EBAY x3, PLTR x5, verified quote-only by
scripts/batch249_probe3.py) and the 3 PLTR SKIP-loss rows gain the
quote plus the section's remaining bullets, because their stored
rows are truncated seed-era extractions carrying only the first 2
of 12 bullets. All 24 classify S4 under the new extractor, so this
repair re-syncs them under gate S4 (its loss check is
one-directional: no stored line lost, no table added) and the
DB-verification below proves each re-synced row byte-identical to
live. SKIP-loss 168 -> 165 after this repair.

Still blocked by design (NOT repaired here): the remaining 165
SKIP-loss rows (real content live drops — Amazon business bullets,
executive quotes in other shapes, letter prose); ABNB 2024-12-31
(fragment), COF 2025-06-30 (tail), DIS x4 (added-table), DRI
2026-08-30 (live-table); plus the standing list from batch 248.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch249_repair.py
       .venv/bin/python scripts/batch249_repair.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm
from batch242_repair import sweep_gate_s4
from batch244_repair import classify_s5
from batch247_repair import sweep_gate_s6
from batch248_repair import sweep_gate_s7
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights, q.cik "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    counts: dict[str, int] = {}
    repaired: list[str] = []
    skip_lists: dict[str, list[str]] = {}
    for t, pe, stored, cik in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            counts["SKIP-nocache"] = counts.get("SKIP-nocache", 0) + 1
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            counts["SKIP-live-none"] = counts.get("SKIP-live-none", 0) + 1
            continue
        if norm(stored) == norm(live):
            counts["B"] = counts.get("B", 0) + 1
            continue
        if sweep_gate_s4(stored, live) is None:
            counts["S4"] = counts.get("S4", 0) + 1
            repaired.append(key)
            if not DRY:
                con.execute(
                    "UPDATE quarterly_financials "
                    "SET press_release_highlights = ? "
                    "WHERE cik = ? AND period_end = ?",
                    (live, cik, pe),
                )
            print(f"    S4 {key} {len(stored)}->{len(live)}")
            continue
        cls5 = classify_s5(stored, live)
        if cls5 is not None:
            rk = f"S5-{cls5}"
            counts[rk] = counts.get(rk, 0) + 1
            skip_lists.setdefault(rk, []).append(key)
            continue
        r6 = sweep_gate_s6(stored, live, html)
        if r6 is None:
            counts["S6"] = counts.get("S6", 0) + 1
            continue
        r7 = sweep_gate_s7(stored, live)
        if r7 is None:
            counts["S7"] = counts.get("S7", 0) + 1
            continue
        rk = f"SKIP-{r6 if r6 is not None else r7}"
        counts[rk] = counts.get(rk, 0) + 1
        skip_lists.setdefault(rk, []).append(key)
    if not DRY:
        con.commit()
    print(f"\nDRY_RUN={DRY} counts: {counts}")
    print(f"repaired (S4): {len(repaired)}: {', '.join(repaired)}")
    for rk in sorted(skip_lists):
        keys = skip_lists[rk]
        if rk == "SKIP-loss":
            print(f"  {rk} ({len(keys)}): {', '.join(keys)}")
        else:
            print(f"  {rk} ({len(keys)})")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
