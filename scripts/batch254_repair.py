"""Batch 254 repair: gate S11, the section-heading-label swap — re-sync
the DHR x7 rows whose seed-era stored highlights carry the bare
"Key <Quarter> <Year> Results" section heading that the current
extractor drops.

The DHR shape, identical across all 7 rows: stored is 7 lines
(tagline, headline, dateline, "Key Third Quarter 2024 Results"
heading, 3 bullets); live is 7 lines (tagline, headline, dateline,
the same 3 bullets, + 1 genuine content line — the CEO-quote
paragraph in 4 rows, the first full-year bullet in 2024-12-31, a
4th "Key Results" bullet in 2026-03-27 / 2026-06-26). The swap is
a 1-for-1 trade of a redundant label for real content: the heading
repeats the quarter the headline already names ("Danaher Reports
Third Quarter 2024 Results"), carries no figure, and the current
extractor's section path strips section headings everywhere else
too — keeping it would be a DHR-only exception, not a fix.

Gate S11 is S4 with the heading-label rescue in the loss check.
The addition side is S4's own policing, unchanged: live-table
fraction, added-table (a genuinely added line must not be
table-shaped), tail, fragment. S7 refuses the addition by design
(its symmetric check bans all added content); S4 refuses the
heading loss by design (its loss check is exact-match). The
heading pattern is exact — "Key {First|Second|Third|Fourth}
Quarter {year} Results" — a label with no figures; a heading
carrying a figure does not match and still refuses as loss.

The full-cache blast must move only the DHR x7 rows (loss -> s11)
and move no row to loss; the repair re-syncs all 7 (in-sync 1042,
loss 148 after). The repair is idempotent (dry re-run finds 0
S4/S9/S10/S11 rows).

Usage: DRY_RUN=1 .venv/bin/python scripts/batch254_repair.py
       .venv/bin/python scripts/batch254_repair.py
"""
import os
import re
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
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"

_KEY_RESULTS_HEADING_RE = re.compile(
    r"^Key (First|Second|Third|Fourth) Quarter \d{4} Results$"
)


def _is_key_results_heading(ln: str) -> bool:
    """A bare "Key <Quarter> <Year> Results" section label: no figure,
    no dollar, no percent — a label the headline already states."""
    return bool(_KEY_RESULTS_HEADING_RE.match(ln.strip()))


def sweep_gate_s11(stored: str, live: str) -> str | None:
    """Gate S11: gate S4 with the section-heading-label rescue in the
    loss check. Returns None when the swap is allowed, else the SKIP
    reason (same vocabulary as gate S4).

    The loss side: a stored line live does not carry exactly is
    excused only when it is a bare "Key ... Results" heading label
    or S3 residue. The addition side is S4's own policing,
    unchanged: live-table fraction, added-table, tail, fragment.
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
        if _is_key_results_heading(x):
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
        rk = f"SKIP-{r11}"
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
