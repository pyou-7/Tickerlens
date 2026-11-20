"""Batch 286 census: run the full gate chain (S4..S13) over all stored
rows vs live extraction; report counts and, for each SKIP-loss row, the
first stored line the S12 loss check flags. DRY RUN only — no DB writes.

Usage: .venv/bin/python scripts/batch286_census.py
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
from batch255_repair import sweep_gate_s12, non_empty, _split_flattened, _strip_leading_chrome, _align_headline, is_residue_s3, _is_truncated_prefix_of_live
from batch261_repair import sweep_gate_s13
from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def first_loss_line(stored, live):
    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    s_lines = _split_flattened(s_lines, l_lines)
    s_lines = _strip_leading_chrome(s_lines)
    s_lines, relation = _align_headline(s_lines, l_lines)
    if relation is None:
        return "<first-diff>"
    live_set = set(l_lines)
    live_norm_lines = [norm(x) for x in l_lines]
    for i, x in enumerate(s_lines):
        if x in live_set:
            continue
        nxt = s_lines[i + 1] if i + 1 < len(s_lines) else ""
        if is_residue_s3(x, nxt, live_set):
            continue
        if _is_truncated_prefix_of_live(x, live_norm_lines):
            continue
        return x
    return "<none?>"  # S12 returned a reason but no loss line found here


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    counts: Counter = Counter()
    loss_rows = []
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            counts["SKIP-nocache"] += 1
            continue
        html = open(path, encoding="utf-8").read()
        live = F.extract_press_release_highlights(html)
        if live is None:
            counts["SKIP-live-none"] += 1
            continue
        if norm(stored) == norm(live):
            counts["B"] += 1
            continue
        if sweep_gate_s4(stored, live) is None:
            counts["S4"] += 1
            continue
        cls5 = classify_s5(stored, live)
        if cls5 is not None:
            counts[f"S5-{cls5}"] += 1
            continue
        if sweep_gate_s6(stored, live, html) is None:
            counts["S6"] += 1
            continue
        if sweep_gate_s7(stored, live) is None:
            counts["S7"] += 1
            continue
        if sweep_gate_s8(stored, live, html) is None:
            counts["S8"] += 1
            continue
        if sweep_gate_s9(stored, live, html) is None:
            counts["S9"] += 1
            continue
        if sweep_gate_s10(stored, live) is None:
            counts["S10"] += 1
            continue
        if sweep_gate_s11(stored, live) is None:
            counts["S11"] += 1
            continue
        r12 = sweep_gate_s12(stored, live)
        if r12 is None:
            counts["S12"] += 1
            continue
        if sweep_gate_s13(stored, live, html) is None:
            counts["S13"] += 1
            continue
        rk = f"SKIP-{r12}"
        counts[rk] += 1
        if r12 == "loss":
            loss_rows.append((key, first_loss_line(stored, live)))
    print("counts:", dict(counts))
    print(f"\nSKIP-loss rows: {len(loss_rows)}")
    by_ticker: Counter = Counter(k.split("_")[0] for k, _ in loss_rows)
    print("by ticker:", dict(by_ticker))
    for key, loss in loss_rows:
        print(f"\n{key} :: {loss[:220]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
