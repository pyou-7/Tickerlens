"""Batch 268 probe: census the press-release highlights rows and list the
SKIP-loss set grouped by ticker, so one coherent group can be picked for
the batch-268 repair. Read-only: no DB writes, no extractor change.
"""
import os
import sqlite3
import sys
from collections import Counter

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


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights, q.cik "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    counts: dict[str, int] = {}
    skip_loss: list[str] = []
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
            counts["S4-resync"] = counts.get("S4-resync", 0) + 1
            continue
        cls5 = classify_s5(stored, live)
        if cls5 is not None:
            counts[f"S5-{cls5}"] = counts.get(f"S5-{cls5}", 0) + 1
            continue
        if sweep_gate_s6(stored, live, html) is None:
            counts["S6"] = counts.get("S6", 0) + 1
            continue
        if sweep_gate_s7(stored, live) is None:
            counts["S7"] = counts.get("S7", 0) + 1
            continue
        if sweep_gate_s8(stored, live, html) is None:
            counts["S8"] = counts.get("S8", 0) + 1
            continue
        r9 = sweep_gate_s9(stored, live, html)
        if r9 is None:
            counts["S9-resync"] = counts.get("S9-resync", 0) + 1
            continue
        if sweep_gate_s10(stored, live) is None:
            counts["S10-resync"] = counts.get("S10-resync", 0) + 1
            continue
        if sweep_gate_s11(stored, live) is None:
            counts["S11-resync"] = counts.get("S11-resync", 0) + 1
            continue
        r12 = sweep_gate_s12(stored, live)
        if r12 is None:
            counts["S12"] = counts.get("S12", 0) + 1
            continue
        if sweep_gate_s13(stored, live, html) is None:
            counts["S13-resync"] = counts.get("S13-resync", 0) + 1
            continue
        counts["SKIP-loss"] = counts.get("SKIP-loss", 0) + 1
        skip_loss.append(key)
    print(f"counts: {counts}")
    by_ticker = Counter(k.split("_")[0] for k in skip_loss)
    print(f"SKIP-loss by ticker ({len(skip_loss)}): {dict(by_ticker.most_common())}")
    for k in skip_loss:
        print(f"  {k}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
