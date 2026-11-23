"""Batch 238 repair: re-sync stored management_guidance rows to the
batch-238 extraction (the labeled-value opener fix), under the
batch-236/237 gates plus one new gate:

Gate E (labeled-value-add re-sync): figures(new) ⊋ figures(stored)
— the new extraction ADDS figures — but every added figure sits in
an added labeled-value line ("(ETR) ~22.5% ..."), every other diff
hunk is explainable, and no figure is removed. This is the narrow
"new guidance found" shape batch 237 deferred, made provable by the
extractor fix itself: the added lines are exactly the rows the old
opener dropped as false footnote definitions, in the same section
and table as the stored row — not a different vintage or section.
FedEx 2026-09-30 is the attested case: its stored row was seeded
from the broken extraction and lacks the ETR row the live extraction
now restores.

Also expected under the old gates: FDX 2026-05-31 (figures equal
now that the live extraction keeps the ETR row; its stored tail —
the (1) baseline footnote, Corporate Overview, safe harbor — is
press-release furniture under gate D).

Deliberately NOT re-synced (carried forward): GEV x2 (historical-
results table dropped — needs its own gate); AMT x3, CLX, SPG x5,
MCO x2 (new extraction adds a whole table/section — a broad "new
guidance found" gate, not the single-labeled-value-row shape);
the 5 new-residue rows (EL/ELV "(Unaudited)" labels, GE interleaved
FCF row, SKYD fragmentary table); EMR's 4-word wrapped tail; plus
the standing list from batch 234.

Usage: dry-run (default, prints every re-sync + diff for inspection)
  .venv/bin/python scripts/batch238_repair.py
apply:
  .venv/bin/python scripts/batch238_repair.py --apply

Idempotent: re-running after --apply finds all targets in sync and
re-syncs nothing.
"""
import ast
import json
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from tickerlens.data.filings import _is_labeled_value_line
from batch236_repair import (
    _diff_explainable,
    _figures,
    _residue,
)
from batch237_repair import _gate_a_passes, _gate_d_passes

DB = "tickerlens.db"
NEW_JSON = "hidden_files/blast238_guidance_new.json"


def _gate_e_passes(stored: str, new_text: str) -> bool:
    """Gate E: pure-add diff whose only unexplained hunks are added
    labeled-value lines, and every added figure sits in one of them.
    """
    f_new, f_stored = _figures(new_text), _figures(stored)
    added_figs = f_new - f_stored
    if not added_figs or (f_stored - f_new):
        return False
    problems = _diff_explainable(stored, new_text)
    if not problems:
        return False
    labeled: list[str] = []
    for p in problems:
        if not p.startswith("unexplained added line: "):
            return False
        ln = ast.literal_eval(p[len("unexplained added line: "):])
        if not _is_labeled_value_line(ln):
            return False
        labeled.append(ln)
    covered: Counter = Counter()
    for ln in labeled:
        covered.update(_figures(ln))
    return not (added_figs - covered)


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
    print("skipped:", dict(skipped))
    for ticker, period, why in sorted(skip_detail):
        print(f"  SKIP {ticker} {period}: {why}")

    targets = gate_a + gate_d + gate_e
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
