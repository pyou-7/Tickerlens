"""Batch 240 repair: re-sync stored management_guidance rows to the
batch-240 extraction, under the batch-236 / 237 / 238 / 239 gates
plus the batch-240 residue exemptions:

- EL 2025-12-31, ELV 2024-12-31, ELV 2025-12-31 (gate A): the live
  extraction fuses the reconciliation-table rows; the "(Unaudited)"
  lines are table-header labels, not footnote definitions, so the
  probe no longer flags them as residue.
- SKYD 2026-06-30 (gate A): the live extraction fuses the Studios
  row; the "Direct-to-Consumer" row carries six value units, which
  the fuser refuses by design, so the probe no longer flags it.
- EMR 2024-09-30 (gate A): the live extraction joins the wrapped
  "Acquisition / Divestiture Fees and Related Costs" label (the
  4-word continuation the batch-235 cap refused).
- GE 2025-09-30 (gate A): the live extraction drops the "(a – FCF*
  conversion ..." footnote definition (letter-dash key); the removed
  line is dropped chrome carrying no figures, so figures are equal
  and the diff is explainable — it passes the stricter gate A before
  gate D is even tried.
- GE 2025-06-30 (gate F): the live extraction adds the remaining
  table columns (interleaved FCF/conversion values) plus the "*"
  legend line, and drops the two letter-dash footnote definitions;
  the section is anchored by the shared fused Operating profit row,
  and the only removed line is a spacing re-render of a kept label.

Deliberately NOT re-synced (carried forward): the standing list from
batch 234 (345 SKIP-loss rows; 82 first-diff + 10 dateline-mismatch
rows; ABNB 2024-12-31; ADBE 2025-11-28 + 2026-05-29; INTC x6;
V 2025-09-30; DG 2024-11-01; JPM's "n "-prefixed bullets; BRK.B Q3
FY2026 mid-body table residue; KHC date-pair header; DLR TOC-only
live extraction; ABNB 2023-12-31; CCI 2026-09-30 guidance furniture,
LUV tail, SPG/MU/BMY tables, DIS footnote shape, batch-184 list, C
slide-deck exhibit, batch-157 gate skips, DASH truncated para;
GILD's guidance tail ends on a "Key Updates" heading; AppLovin's
"Summary:2" heading wart; wordy value lines as a future fuser class;
still-truncated stored highlights rows). ELV 2024-03-31's blast diff
has no stored row at all (no quarterly_financials row for that
period), so there is nothing to re-sync there.

Usage: dry-run (default, prints every re-sync + diff for inspection)
  .venv/bin/python scripts/batch240_repair.py
apply:
  .venv/bin/python scripts/batch240_repair.py --apply

Idempotent: re-running after --apply finds all targets in sync and
re-syncs nothing.
"""
import difflib
import json
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch236_repair import _diff_explainable, _figures, _residue
from batch237_repair import _gate_a_passes, _gate_d_passes
from batch238_repair import _gate_e_passes
from batch239_repair import _gate_f_passes, _gate_h_passes

DB = "tickerlens.db"
NEW_JSON = "hidden_files/blast240_guidance_new.json"


def main() -> None:
    apply = "--apply" in sys.argv
    with open(NEW_JSON) as f:
        new_map = json.load(f)
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.management_guidance "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.management_guidance IS NOT NULL"
    ).fetchall()

    by_ticker: dict[str, list[tuple[str, str]]] = {}
    for key, val in new_map.items():
        by_ticker.setdefault(key.split("_")[0], []).append((key, val))

    gate_a: list[tuple[str, str]] = []
    gate_d: list[tuple[str, str]] = []
    gate_e: list[tuple[str, str]] = []
    gate_f: list[tuple[str, str]] = []
    gate_h: list[tuple[str, str]] = []
    skipped: Counter = Counter()
    skip_detail: list[tuple[str, str, str]] = []
    for ticker, period, stored in rows:
        match = None
        for key, val in by_ticker.get(ticker, []):
            if key.endswith("_" + period + ".html"):
                match = (key, val)
                break
        if match is None:
            skipped["nocache"] += 1
            continue
        key, new_text = match
        if new_text is None:
            skipped["live-none"] += 1
            continue
        if new_text == stored:
            skipped["in-sync"] += 1
            continue
        lines = [ln for ln in new_text.splitlines() if ln.strip()]
        probs = _residue(lines)
        if probs:
            skipped["new-residue"] += 1
            skip_detail.append((ticker, period, "new-residue: " + "; ".join(probs)))
            continue
        if _gate_a_passes(stored, new_text):
            gate_a.append((ticker, period))
            continue
        if _gate_d_passes(stored, new_text):
            gate_d.append((ticker, period))
            continue
        if _gate_e_passes(stored, new_text):
            gate_e.append((ticker, period))
            continue
        if _gate_f_passes(stored, new_text):
            gate_f.append((ticker, period))
            continue
        if _gate_h_passes(stored, new_text):
            gate_h.append((ticker, period))
            continue
        f_new, f_stored = _figures(new_text), _figures(stored)
        if f_new - f_stored:
            skipped["diff-figures-added"] += 1
            skip_detail.append(
                (ticker, period, f"diff-figures added={dict(f_new - f_stored)}")
            )
            continue
        expl = _diff_explainable(stored, new_text)
        if expl:
            skipped["unexplained-diff"] += 1
            skip_detail.append((ticker, period, "unexplained: " + "; ".join(expl)))
            continue
        skipped["diff-figures"] += 1
        skip_detail.append((ticker, period, "diff-figures (removed outside chrome/tail)"))

    print(f"gate A (fuse-only re-sync): {len(gate_a)}")
    print(f"gate D (header/footnote/tail-furniture re-sync): {len(gate_d)}")
    print(f"gate E (labeled-value-add re-sync): {len(gate_e)}")
    print(f"gate F (new-guidance-found re-sync): {len(gate_f)}")
    print(f"gate H (historical-results-table drop re-sync): {len(gate_h)}")
    print("skipped:", dict(skipped))
    for ticker, period, why in sorted(skip_detail):
        print(f"  SKIP {ticker} {period}: {why}")

    targets = gate_a + gate_d + gate_e + gate_f + gate_h
    if not targets:
        print("nothing to re-sync.")
        return
    if apply:
        for ticker, period in targets:
            new_text = dict(by_ticker[ticker])[ticker + "_" + period + ".html"]
            con.execute(
                "UPDATE quarterly_financials SET management_guidance = ? "
                "WHERE cik = (SELECT cik FROM companies WHERE ticker = ?) "
                "AND period_end = ?",
                (new_text, ticker, period),
            )
        con.commit()
        print(f"applied: {len(targets)} rows re-synced.")
    else:
        print(f"dry-run: {len(targets)} rows would re-sync (use --apply).")
        for ticker, period in sorted(targets):
            print(f"  RESYNC {ticker} {period}")
    con.close()


if __name__ == "__main__":
    main()
