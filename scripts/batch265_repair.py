"""Batch 265 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
CINF x2 override.

No extractor change this batch. The CINF Q3 2024 + Q3 2025 stored rows
are stale snapshots of the pre-batch-222 extractor (batch 134 wrote
them when the section was rejected as a financial table because the CEO
quote's $/% lines pushed data_rows to 4; batch 222's snapshot fix made
the section qualify again). The current extractor serves the section
shape for all 9 CINF quarters — leading block 5 figure lines vs section
9 (batch-102/261 absolute-count rule; even quote-free the section's 7
bullet figure lines beat the lede's 5) — and the other 7 quarters
already store it. The gates refuse the re-sync (SKIP-loss: stored is a
different section than live), so the override below re-syncs exactly
these 2 rows under per-row gates: stored is the lede shape, live is the
current extractor's section shape with the Reports headline, and the
other 7 CINF quarters are stored == live (consistency cross-check —
a re-seed would produce the same text). The lede bullets' headline
numbers (EPS, net income, book value) stay visible on the page in the
quarterly financials tables.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch265_repair.py
       .venv/bin/python scripts/batch265_repair.py
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
from batch250_repair import sweep_gate_s8
from batch251_repair import sweep_gate_s9
from batch253_repair import sweep_gate_s10
from batch254_repair import sweep_gate_s11
from batch255_repair import sweep_gate_s12
from batch261_repair import sweep_gate_s13
from tickerlens.data import filings as F

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

    def _resync(key, stored, live, cik, pe):
        repaired.append(key)
        if not DRY:
            con.execute(
                "UPDATE quarterly_financials "
                "SET press_release_highlights = ? "
                "WHERE cik = ? AND period_end = ?",
                (live, cik, pe),
            )
        print(f"    {key} {len(stored)}->{len(live)}")

    for t, pe, stored, cik in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            counts["SKIP-nocache"] = counts.get("SKIP-nocache", 0) + 1
            continue
        html = open(path, encoding="utf-8").read()
        live = F.extract_press_release_highlights(html)
        if live is None:
            counts["SKIP-live-none"] = counts.get("SKIP-live-none", 0) + 1
            continue
        if norm(stored) == norm(live):
            counts["B"] = counts.get("B", 0) + 1
            continue
        if sweep_gate_s4(stored, live) is None:
            counts["S4"] = counts.get("S4", 0) + 1
            _resync(key, stored, live, cik, pe)
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
        r8 = sweep_gate_s8(stored, live, html)
        if r8 is None:
            counts["S8"] = counts.get("S8", 0) + 1
            continue
        r9 = sweep_gate_s9(stored, live, html)
        if r9 is None:
            counts["S9"] = counts.get("S9", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        r10 = sweep_gate_s10(stored, live)
        if r10 is None:
            counts["S10"] = counts.get("S10", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        r11 = sweep_gate_s11(stored, live)
        if r11 is None:
            counts["S11"] = counts.get("S11", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        r12 = sweep_gate_s12(stored, live)
        if r12 is None:
            counts["S12"] = counts.get("S12", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        r13 = sweep_gate_s13(stored, live, html)
        if r13 is None:
            counts["S13"] = counts.get("S13", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        rk = f"SKIP-{r12}"
        counts[rk] = counts.get(rk, 0) + 1
        skip_lists.setdefault(rk, []).append(key)

    # --- Batch 265 CINF override (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1074, SKIP-loss 131). The
    # two CINF Q3 rows are the only override targets; every gate below
    # must pass or the row is left untouched and reported.
    cinf_keys = ["CINF_2024-09-30", "CINF_2025-09-30"]
    others_ok = True
    for (pe, stored_o) in con.execute(
        "SELECT q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = 'CINF' "
        "AND q.period_end NOT IN ('2024-09-30', '2025-09-30')"
    ).fetchall():
        live_o = F.extract_press_release_highlights(
            open(f"{CACHE}/CINF_{pe}.html", encoding="utf-8").read()
        )
        if norm(stored_o) != norm(live_o):
            others_ok = False
            print(f"  CINF-override ABORT: sibling {pe} is not stored==live")
    if others_ok:
        for key in cinf_keys:
            pe = key.split("_", 1)[1]
            row = con.execute(
                "SELECT q.press_release_highlights, q.cik "
                "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
                "WHERE c.ticker = 'CINF' AND q.period_end = ?",
                (pe,),
            ).fetchone()
            stored_c, cik_c = row
            live_c = F.extract_press_release_highlights(
                open(f"{CACHE}/{key}.html", encoding="utf-8").read()
            )
            gates = {
                "stored-is-lede": (
                    stored_c is not None
                    and stored_c.startswith("Cincinnati Financial Reports ")
                    and "today reported:" in stored_c
                ),
                "live-is-section": (
                    live_c is not None
                    and live_c.startswith("Cincinnati Financial Reports ")
                    and "property casualty combined ratio" in live_c
                    and "Stephen M. Spray" in live_c
                ),
                "same-headline": (
                    stored_c is not None
                    and live_c is not None
                    and stored_c.split("\n")[0] == live_c.split("\n")[0]
                ),
            }
            failed = [g for g, ok in gates.items() if not ok]
            if failed:
                print(f"  CINF-override SKIP {key}: failed gates {failed}")
                continue
            print(f"  CINF-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
                  f"{len(stored_c)}->{len(live_c)} (lede -> section)")
            if not DRY:
                con.execute(
                    "UPDATE quarterly_financials "
                    "SET press_release_highlights = ? "
                    "WHERE cik = ? AND period_end = ?",
                    (live_c, cik_c, pe),
                )
                repaired.append(f"{key} (override)")
                # Post-write verify: stored must now equal live byte-for-byte.
                check = con.execute(
                    "SELECT press_release_highlights FROM quarterly_financials "
                    "WHERE cik = ? AND period_end = ?",
                    (cik_c, pe),
                ).fetchone()[0]
                assert check == live_c, f"post-write mismatch for {key}"
                print(f"    {key} DB-verified byte-identical to live")
    if not DRY:
        con.commit()
    print(f"\nDRY_RUN={DRY} counts: {counts}")
    print(f"repaired: {len(repaired)}: {', '.join(repaired)}")
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
