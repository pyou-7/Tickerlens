"""Batch 255 repair: gate S12, the stored-truncation swap — re-sync
the rows whose seed-era stored highlights carry a line the seeder
truncated mid-sentence (trailing "…") while the current extractor
serves the full line.

The shape, identical across the cohort: exactly one stored line is
lost, and that line — minus its trailing "…" — is a strict prefix
of a live line that is strictly longer. CEG x3 (2025-06-30,
2025-12-31, 2026-06-30): the stored "Nuclear Operations" bullet /
capacity-factor line is cut at "…" and live carries the same line
to its end; live also adds one genuine bullet (the "Natural Gas,
Oil, and Renewables Operations" bullet) in each row. EQIX x2
(2024-12-31, 2025-09-30): the same shape, once the batch-255 norm
fix glues the spaced "TM" trademark marker ("Exchange TM" vs live
"ExchangeTM", "Intelligence TM" vs "IntelligenceTM") — without
that fix the TM line differs by spacing alone and the row can
never clear the loss check. The "…" is the seed-era truncation
marker: the seeder capped long lines, so the stored line is a
prefix of the live line by construction, never a different
sentence. The swap trades a truncated line for its own full text
plus one genuine bullet, so it is strictly more informative.

Gate S12 is S4 with the truncation-prefix rescue in the loss
check. The rescue is narrow by construction: the stored line
must end with "…" (a truncated line, not a complete one), the
prefix (minus "…") must be at least 80 chars (a heading or label
can never qualify — the smallest rescued base is 117 chars), and
it must be a strict prefix of a live line that is strictly
longer. The addition side is S4's own policing, unchanged:
live-table fraction, added-table, tail, fragment. DASH 2025-06-30
is the proof the rescue stays narrow: its "In Q2 2025, Total
Orders ..." line IS a truncated-prefix shape, but its other lost
line (the approach paragraph, whose cohort-definition tail live
drops) is not rescued — live's line is a prefix of stored's, the
reverse direction — so the row still refuses as loss. F x6 is the
same reverse direction throughout (live truncates the flattened
mega-line; stored carries the longer one, whose tail holds real
segment narrative and outlook) and stays loss. A line ending in
"…" whose live continuation changes a figure is not a prefix
(the figure differs), so a changed figure still refuses — the
prefix test is exact, not fuzzy.

The full-cache blast must move only the 5 rows (CEG x3 + EQIX x2)
from loss to s12 and move no row to loss; the repair re-syncs all
5 (in-sync 1049, loss 143 after). The repair is idempotent (dry
re-run finds 0 S4/S9/S10/S11/S12 rows).

Usage: DRY_RUN=1 .venv/bin/python scripts/batch255_repair.py
       .venv/bin/python scripts/batch255_repair.py
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
from batch248_repair import sweep_gate_s7
from batch250_repair import sweep_gate_s8
from batch251_repair import sweep_gate_s9
from batch253_repair import sweep_gate_s10
from batch254_repair import sweep_gate_s11
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"

_MIN_TRUNCATED_PREFIX = 80


def _is_truncated_prefix_of_live(line: str, live_norm_lines: list[str]) -> bool:
    """A stored line the seeder truncated mid-sentence: it ends with
    "…" and the text before it is a strict prefix of a live line
    that is strictly longer. The 80-char floor keeps headings and
    labels out — a truncated line is long prose or a long bullet by
    construction (smallest rescued base in the cohort is 117)."""
    nline = norm(line).rstrip()
    if not nline.endswith("…"):
        return False
    base = nline.rstrip("…").rstrip()
    if len(base) < _MIN_TRUNCATED_PREFIX:
        return False
    return any(
        ln.startswith(base) and len(ln) > len(nline)
        for ln in live_norm_lines
    )


def sweep_gate_s12(stored: str, live: str) -> str | None:
    """Gate S12: gate S4 with the stored-truncation rescue in the
    loss check. Returns None when the swap is allowed, else the SKIP
    reason (same vocabulary as gate S4).

    The loss side: a stored line live does not carry exactly is
    excused when it is S3 residue or a truncated line whose full
    text live carries (strict prefix, "…" marker, 80-char floor).
    The addition side is S4's own policing, unchanged: live-table
    fraction, added-table, tail, fragment.
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
    live_norm_lines = [norm(x) for x in l_lines]
    for i, x in enumerate(s_lines):
        if x in live_set:
            continue
        nxt = s_lines[i + 1] if i + 1 < len(s_lines) else ""
        if is_residue_s3(x, nxt, live_set):
            continue
        if _is_truncated_prefix_of_live(x, live_norm_lines):
            continue
        return "loss"
    lfrac = sum(1 for x in l_lines if is_residue(x)) / max(len(l_lines), 1)
    if lfrac >= 0.4 or has_dateline_table_shape(l_lines):
        return "live-table"
    s_set = set(s_lines)
    if any(hard_table(x) for x in l_lines if x not in s_set):
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
        r11 = sweep_gate_s11(stored, live)
        if r11 is None:
            counts["S11"] = counts.get("S11", 0) + 1
            repaired.append(key)
            if not DRY:
                con.execute(
                    "UPDATE quarterly_financials "
                    "SET press_release_highlights = ? "
                    "WHERE cik = ? AND period_end = ?",
                    (live, cik, pe),
                )
            print(f"    S11 {key} {len(stored)}->{len(live)}")
            continue
        r12 = sweep_gate_s12(stored, live)
        if r12 is None:
            counts["S12"] = counts.get("S12", 0) + 1
            repaired.append(key)
            if not DRY:
                con.execute(
                    "UPDATE quarterly_financials "
                    "SET press_release_highlights = ? "
                    "WHERE cik = ? AND period_end = ?",
                    (live, cik, pe),
                )
            print(f"    S12 {key} {len(stored)}->{len(live)}")
            continue
        rk = f"SKIP-{r12}"
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
