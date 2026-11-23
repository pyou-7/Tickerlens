"""Batch 241 probe: the 345 SKIP-loss highlights rows from the batch
231/232 source-verified stale-row sweep.

SKIP-loss means: the stored highlights row differs from the live
extraction, and the live extraction DROPS stored lines that the sweep
gate does not recognize as residue — i.e. a naive overwrite would
lose real content (Netflix shareholder-letter prose, Visa prose,
Genuine Parts segment prose, ...). The gate refuses those rows, so
they stay stale.

This probe re-runs the sweep classification and dumps, for the loss
rows, exactly which stored lines the live extraction drops, grouped
by ticker — so the dominant loss patterns can be scoped before any
extractor change or gate extension.

Usage: .venv/bin/python scripts/batch241_probe.py
"""
import os
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import (
    is_residue,
    non_empty,
    norm,
    sweep_gate,
)
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    counts: dict[str, int] = {}
    loss_by_ticker: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    lost_line_counter: Counter = Counter()
    loss_examples: dict[str, list[str]] = defaultdict(list)
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            counts["nocache"] = counts.get("nocache", 0) + 1
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            counts["live-none"] = counts.get("live-none", 0) + 1
            continue
        if norm(stored) == norm(live):
            counts["in-sync"] = counts.get("in-sync", 0) + 1
            continue
        reason = sweep_gate(stored, live)
        counts[reason or "repairable"] = counts.get(reason or "repairable", 0) + 1
        if reason == "loss":
            s_lines = non_empty(stored)
            l_set = set(non_empty(live))
            lost = [x for x in s_lines if x not in l_set and not is_residue(x)]
            loss_by_ticker[t].append((key, lost))
            for ln in lost:
                # shape key: first 40 chars, to group repeated prose
                lost_line_counter[ln[:60]] += 1
                if len(loss_examples[ln[:60]]) < 3:
                    loss_examples[ln[:60]].append(key)
    print(f"counts: {counts}")
    print(f"\nloss rows by ticker ({sum(len(v) for v in loss_by_ticker.values())} total):")
    for t, items in sorted(loss_by_ticker.items(), key=lambda kv: -len(kv[1])):
        print(f"  {t}: {len(items)} rows")
    print("\nmost common lost lines (first 60 chars):")
    for ln, n in lost_line_counter.most_common(40):
        print(f"  {n}x {ln!r}  e.g. {loss_examples[ln][:2]}")
    print("\nper-ticker lost-line samples:")
    for t, items in sorted(loss_by_ticker.items(), key=lambda kv: -len(kv[1]))[:12]:
        print(f"\n== {t} ({len(items)} rows) ==")
        for key, lost in items[:3]:
            print(f"  {key}: {len(lost)} lost lines")
            for ln in lost[:6]:
                print(f"    - {ln[:160]}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
