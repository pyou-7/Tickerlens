"""Batch 280 probe: DGX x4 SKIP-loss rows.

First-loss lines point at a strategic-bullets section in stored
("Serving Clinicians and Health Systems" / "Serving Customers and
Delivering Innovations" headings; a Corewell Health bullet) that live
does not serve. Compare stored vs live per row, char counts, and the
exact stored-only / live-only lines. DRY RUN only — no DB writes.

Usage: .venv/bin/python scripts/batch280_probe.py
"""
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
KEYS = ["DGX_2025-09-30", "DGX_2025-12-31", "DGX_2026-03-31",
        "DGX_2026-06-30"]


def main() -> int:
    con = sqlite3.connect(DB)
    for key in KEYS:
        t, pe = key.split("_")
        stored = con.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = ? AND q.period_end = ?", (t, pe)
        ).fetchone()[0]
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        live = F.extract_press_release_highlights(html)
        print(f"\n{'='*100}\n{key}: stored {len(stored)} chars, live {len(live)} chars, "
              f"delta {len(live) - len(stored)}")
        sl = [x for x in stored.splitlines() if x.strip()]
        ll = [x for x in live.splitlines() if x.strip()]
        print(f"stored lines: {len(sl)}, live lines: {len(ll)}")
        print("--- STORED-ONLY lines (exact, not in live) ---")
        lset = set(ll)
        for x in sl:
            if x not in lset:
                print(f"  S: {x[:400]}")
        print("--- LIVE-ONLY lines (exact, not in stored) ---")
        sset = set(sl)
        for x in ll:
            if x not in sset:
                print(f"  L: {x[:400]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
