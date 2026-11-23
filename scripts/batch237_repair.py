"""Batch 237 repair: re-sync stored management_guidance rows to the
batch-235 fused extraction, under the batch-236 gates plus three
extensions (all gate-side; the extractor is unchanged, so the blast235
file stays the current extraction):

Gate A (fuse-only re-sync, unchanged): figures(new) == figures(stored)
as multisets, no residue in the new text, and the stored-vs-new diff is
explainable line by line.

Gate D (header / footnote-drop / tail-furniture re-sync): figures(new)
⊆ figures(stored) and every removed figure sits in a dropped
footnote/chrome line (batch 236, plus the batch-237 extensions below)
or in a tail-furniture line, and the diff is explainable. This closes
the diff-figures rows whose removed lines are press-release furniture
rather than guidance data:

  * AAL x3 — the stored row ends on (or is interrupted by) the release
    header triple: title line / dateline / "Page N". The header triple
    is now chrome-flagged.
  * DAL 2024-12-31 — footnote defs whose continuations the batch-236
    continuation guard rejected: the table-label predicate
    false-positives on lowercase prose ("for historical comparison
    figures", "impact of the CrowdStrike-caused outage in 2024"), so a
    lowercase-starting line is no longer treated as a label.
  * CHD x2, GIS x2, ADSK, DPZ, META, MU — the stored row ends in a
    press-release furniture tail (webcast notice, company description,
    safe harbor, Regulation G definitions, product highlights,
    corporate-news section). A tail-furniture line is a line in the
    trailing removed run at or after a furniture opener (boilerplate
    marker or short non-guidance heading), carrying no $ or % figure
    and not a value line.
  * Domino's glued footnote keys ("globe1:") now normalize like the
    spaced stored form ("globe 1 :").

Deliberately NOT re-synced (carried forward):
  * FDX 2026-05-31 — the "(ETR) ~23% ..." guidance row is dropped by
    the live extraction (the footnote opener matches its parenthesized
    label) and the gate now refuses to credit such a labeled-value
    line as chrome. Fixing the opener is an extractor change for the
    next batch; re-syncing now would delete the ~23% ETR figure from
    the stored row.
  * GEV x2 — the new extraction drops a historical-results table
    (real $ figures, different section); needs its own gate.
  * AMT x3, CLX, SPG x5, MCO x2 — the new extraction ADDS guidance
    figures the stored row lacks (a whole table / section); needs a
    "new guidance found" gate with section verification.
  * V 2024-09-30 — head furniture (earnings-presentation pointer +
    webcast / Investor Day notices at the top, not the tail); needs a
    head-furniture gate.
  * EL / ELV x2 / GE / SKYD — new-residue rows (unchanged from batch 236).

Usage: dry-run (default, prints every re-sync + diff for inspection)
  .venv/bin/python scripts/batch237_repair.py
apply:
  .venv/bin/python scripts/batch237_repair.py --apply

Idempotent: re-running after --apply finds all targets in sync and
re-syncs nothing.
"""
import json
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch236_repair import (
    _chrome_flags,
    _diff_explainable,
    _figures,
    _removed_indices,
    _residue,
    _tail_furniture_indices,
)

DB = "tickerlens.db"
NEW_JSON = "hidden_files/blast235_guidance_new.json"


def _gate_a_passes(stored: str, new_text: str) -> bool:
    """Gate A: fuse-only — figures equal as multisets and the diff is
    explainable."""
    return (
        _figures(new_text) == _figures(stored)
        and not _diff_explainable(stored, new_text)
    )


def _gate_d_passes(stored: str, new_text: str) -> bool:
    """Gate D: figures(new) ⊆ figures(stored), every removed figure
    sits in a dropped chrome or tail-furniture line (counted over
    removed lines only), and the diff is explainable."""
    f_new, f_stored = _figures(new_text), _figures(stored)
    if f_new - f_stored:
        return False
    if _diff_explainable(stored, new_text):
        return False
    removed_figs = f_stored - f_new
    s_lines = [ln for ln in stored.splitlines() if ln.strip()]
    n_lines = [ln for ln in new_text.splitlines() if ln.strip()]
    flags = _chrome_flags(s_lines)
    tail_idx = _tail_furniture_indices(s_lines, n_lines, new_text)
    covered: Counter = Counter()
    for idx in sorted(_removed_indices(s_lines, n_lines)):
        if flags[idx] or idx in tail_idx:
            covered.update(_figures(s_lines[idx]))
    return not (removed_figs - covered)


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
        # Explainable but a removed figure sits outside chrome/tail
        # lines — report which, for the next batch's gate design.
        removed_figs = f_stored - f_new
        s_lines = [ln for ln in stored.splitlines() if ln.strip()]
        n_lines = [ln for ln in new_text.splitlines() if ln.strip()]
        flags = _chrome_flags(s_lines)
        tail_idx = _tail_furniture_indices(s_lines, n_lines, new_text)
        covered: Counter = Counter()
        for idx in sorted(_removed_indices(s_lines, n_lines)):
            if flags[idx] or idx in tail_idx:
                covered.update(_figures(s_lines[idx]))
        skipped["diff-figures"] += 1
        skip_detail.append(
            (ticker, period, f"diff-figures removed-unexplained={dict(removed_figs - covered)}")
        )

    print(f"gate A (fuse-only re-sync): {len(gate_a)}")
    print(f"gate D (header/footnote/tail-furniture re-sync): {len(gate_d)}")
    print("skipped:", dict(skipped))
    for ticker, period, why in sorted(skip_detail):
        print(f"  SKIP {ticker} {period}: {why}")

    targets = gate_a + gate_d
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
