"""Batch 253 repair: gate S10, the spacing-drift + pure-addition swap —
re-sync the DLR x7 rows the batch-253 extractor fix unblocks.

Two changes ship together:

  * Extractor fix (src/tickerlens/data/filings.py): the black-square
    bullet "◾" (U+25FE) joins _BULLET_LEAD_RE. Digital Realty renders
    its Highlights bullets with it, and the glyph was missing from the
    class — two $+%-carrying ◾ bullets plus the two $+%-carrying
    "Financial Results" narrative lines tripped the data_rows >= 4
    threshold in _looks_like_financial_table, so the genuine 7-bullet
    "Highlights" section was rejected as a financial table and the
    lede fallback served the supplement TOC instead (DLR 2026-03-31:
    live 220 chars of TOC junk vs 1638 stored). The batch-154 defect
    class, a new glyph.
  * Gate S10 (this file): S4 with the S7 spacing-equivalence rescue
    in the loss check. The fix restores the real section, but live
    still differs from the seed-era stored rows in two ways no
    earlier gate accepts: (a) seed-era flattening spaced the curly
    possessive ("Digital Realty ’ s" vs live "Digital Realty’s") and
    left a lone zero-width-space line the current _html_to_text drops
    — both excused by spacing-equivalence / S3 residue, never content;
    (b) live serves one more genuine "Financial Results" narrative
    line than the seed-era section cap did (FFO/EBITDA prose) — a pure
    addition, policed by S4's own fraction / added-table / tail /
    fragment checks. S7 refuses (b) by design (its symmetric check
    bans all added content); S4 refuses (a) by design (its loss check
    is exact-match). S10 is the combination the DLR rows need: the
    loss side is proven by spacing-equivalence (identical non-space
    characters, identical digit runs — no figure can change), the
    addition side by S4's policing. The added-table check excuses
    lines spacing-equivalent to a stored line, for the same reason:
    that content is stored content, not an added table row.

The full-cache blast must move only the DLR x7 rows (loss -> s10)
and move no row to loss; the repair re-syncs all 7 (in-sync 1035,
loss 155 after). The repair is idempotent (dry re-run finds 0
S4/S9/S10 rows).

Usage: DRY_RUN=1 .venv/bin/python scripts/batch253_repair.py
       .venv/bin/python scripts/batch253_repair.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import (
    hard_table,
    has_dateline_table_shape,
    is_residue,
    non_empty,
    norm,
)
from batch241_repair import _is_dateline_sentence, is_residue_s3
from batch242_repair import (
    _align_headline,
    _split_flattened,
    _strip_leading_chrome,
    sweep_gate_s4,
)
from batch244_repair import classify_s5
from batch247_repair import sweep_gate_s6
from batch248_repair import spacing_equivalent, sweep_gate_s7
from batch250_repair import sweep_gate_s8
from batch251_repair import sweep_gate_s9
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"


def sweep_gate_s10(stored: str, live: str) -> str | None:
    """Gate S10: gate S4 with the S7 spacing-equivalence rescue in the
    loss check. Returns None when the swap is allowed, else the SKIP
    reason (same vocabulary as gate S4).

    The loss side: a stored line live does not carry exactly is
    excused only when it is spacing-equivalent to a live line (same
    non-space characters, same digit runs — batch 248's proof that no
    word or figure changes) or S3 residue (the seed-era lone
    zero-width-space line DLR carries). The addition side is S4's
    own policing, unchanged: live-table fraction, added-table (a
    genuinely added line must not be table-shaped; a line
    spacing-equivalent to a stored line is stored content, not an
    addition, so it is excused there too), tail, fragment.
    """
    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    s_lines = _split_flattened(s_lines, l_lines)
    s_lines = _strip_leading_chrome(s_lines)
    s_lines, relation = _align_headline(s_lines, l_lines)
    if relation is None:
        return "first-diff"
    live_set = set(l_lines)
    live_has_dateline = any(_is_dateline_sentence(x) for x in l_lines)
    s_datelines = [x for x in s_lines if _is_dateline_sentence(x)]
    if not live_has_dateline:
        s_datelines = []
    live_norm_set = {norm(x) for x in l_lines}
    if not all(norm(d) in live_norm_set for d in s_datelines):
        return "dateline-mismatch"
    for i, x in enumerate(s_lines):
        if x in live_set:
            continue
        nxt = s_lines[i + 1] if i + 1 < len(s_lines) else ""
        if is_residue_s3(x, nxt, live_set):
            continue
        if any(spacing_equivalent(x, y) for y in l_lines):
            continue
        return "loss"
    lfrac = sum(1 for x in l_lines if is_residue(x)) / max(len(l_lines), 1)
    if lfrac >= 0.4 or has_dateline_table_shape(l_lines):
        return "live-table"
    s_set = set(s_lines)
    if any(
        hard_table(x)
        for x in l_lines
        if x not in s_set
        and not any(spacing_equivalent(x, y) for y in s_lines)
    ):
        return "added-table"
    last = l_lines[-1] if l_lines else ""
    if last not in s_set and (
        is_residue(last) or last.rstrip().endswith(":")
    ):
        return "tail"
    if len(l_lines) > 1 and l_lines[1][:1].islower():
        return "fragment"
    return None


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
        r8 = sweep_gate_s8(stored, live, html)
        if r8 is None:
            counts["S8"] = counts.get("S8", 0) + 1
            continue
        r9 = sweep_gate_s9(stored, live, html)
        if r9 is None:
            counts["S9"] = counts.get("S9", 0) + 1
            repaired.append(key)
            if not DRY:
                con.execute(
                    "UPDATE quarterly_financials "
                    "SET press_release_highlights = ? "
                    "WHERE cik = ? AND period_end = ?",
                    (live, cik, pe),
                )
            print(f"    S9 {key} {len(stored)}->{len(live)}")
            continue
        r10 = sweep_gate_s10(stored, live)
        if r10 is None:
            counts["S10"] = counts.get("S10", 0) + 1
            repaired.append(key)
            if not DRY:
                con.execute(
                    "UPDATE quarterly_financials "
                    "SET press_release_highlights = ? "
                    "WHERE cik = ? AND period_end = ?",
                    (live, cik, pe),
                )
            print(f"    S10 {key} {len(stored)}->{len(live)}")
            continue
        rk = f"SKIP-{r10}"
        counts[rk] = counts.get(rk, 0) + 1
        skip_lists.setdefault(rk, []).append(key)
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
