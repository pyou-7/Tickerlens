"""Batch 251 repair: the highlights sweep, gate S9 — the
summary-heading swap (CHD x4).

Each of the four CHD loss rows differs from live in exactly one
way: the stored row carries the release's two summary-table column
headings — "YYYY <Quarter> Results" and "YYYY Full Year
Results|Outlook" — and only the first two bullets of the run, while
live drops the headings and serves the first four bullets. The
headings are the two columns of the summary table that sits above
the bullet list (Church & Dwight's releases open with a
headline, 2-3 all-caps sub-headlines, the two column headings,
then a 10-bullet run: 5 quarter bullets + 5 full-year-outlook
bullets). The live extraction drops the headings by design
(_is_lede_title_line: heading-shaped, capital-led, ending in a
section word, no headline verb) and serves the quarter bullets
first; the 6-line lede budget stops it at 4 bullets, so live is
itself incomplete — the remaining 6 bullets are a live-side
budget item for a future batch, not part of this swap.

Gate S9 blesses the swap stored -> live when:
  1. the only stored lines lost are exactly two period headings —
     one quarter heading ("YYYY First|Second|Third|Fourth Quarter
     Results") and one full-year heading ("YYYY Full Year
     Results|Outlook");
  2. the only live lines added are 1-4 bullets forming a tail run
     of live;
  3. stored-minus-headings equals live-minus-added, in order (the
     swap changes nothing else);
  4. live is clean by the S5 live-side checks;
  5. the swap verifies against the source document
     (verify_summary_headings): in the doc's own text, the two
     headings sit consecutively immediately before the first stored
     bullet, and the added bullets follow the last stored bullet
     consecutively — the headings head the bullet run and the added
     bullets continue it. A period heading over prose could never
     pass, because the lines around it would not be the run's
     bullets.

The dropped lines are summary-table column headings, not
highlights content — the same S5 argument (stored was never
highlights there), applied to a heading pair instead of a whole
row. The served text improves from 2 bullets + furniture to 4
bullets, all doc-verified.

Still blocked by design (NOT repaired here): the other three CHD
rows (2024-12-31, 2025-06-30, 2025-12-31) — live drops a genuine
sub-headline on each ("ANNOUNCES 4% DIVIDEND INCREASE" x2,
"TOUCHLAND ACQUISITION COMPLETED", "2026 OUTLOOK OF ORGANIC SALES
GROWTH OF 3-4% and ADJUSTED EPS GROWTH OF 5-8%") via the
<=4-word _is_lede_heading_fragment rule (and, for the 2026-OUTLOOK
line, a second drop the probe has not yet attributed), so a swap
would LOSE real news — those rows stay in the loss cohort until
the heading-fragment rule learns a sub-headline guard; the
remaining 165 SKIP-loss rows (F x6, CINF x6, AXON x6, BNY x8,
AMZN x8, DHR x7, DLR x7, V x7, CEG x8, COR x7, and the rest);
DRI 2026-08-30 live-table; ABNB 2024-12-31; COF 2025-06-30;
DIS x4 added-table; ADBE 2025-11-28 + 2026-05-29; INTC x6;
V 2025-09-30; DG 2024-11-01; JPM's "n "-prefixed bullets; BRK.B
Q3 FY2026 mid-body table residue; KHC date-pair header; DLR
TOC-only live extraction; ABNB 2023-12-31; CCI 2026-09-30
guidance furniture, LUV tail, SPG/MU/BMY tables, DIS footnote
shape, batch-184 list, C slide-deck exhibit, batch-157 gate
skips, DASH truncated para; GILD's guidance tail ends on a "Key
Updates" heading; AppLovin's "Summary:2" heading wart; wordy
value lines as a future fuser class; still-truncated stored
highlights rows; the FAST/EL lede warts; the AMT 2023-12-31 /
2024-03-31 / 2024-06-30 NULL-stored-highlights seeding gap.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch251_repair.py
       .venv/bin/python scripts/batch251_repair.py
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch242_repair import sweep_gate_s4
from batch244_repair import _live_is_clean, classify_s5
from batch247_repair import sweep_gate_s6
from batch248_repair import sweep_gate_s7
from batch250_repair import sweep_gate_s8
from tickerlens.data.filings import (
    _html_to_text,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"

# The summary table's two column headings: a quarter column and a
# full-year column. "Results" for the quarter; "Results" or "Outlook"
# for the full year (CHD alternates by quarter).
_QUARTER_HEAD_RE = re.compile(
    r"^\d{4} (?:First|Second|Third|Fourth) Quarter Results$"
)
_FY_HEAD_RE = re.compile(r"^\d{4} Full Year (?:Results|Outlook)$")


def _head_kind(ln: str) -> str | None:
    s = ln.strip()
    if _QUARTER_HEAD_RE.match(s):
        return "quarter"
    if _FY_HEAD_RE.match(s):
        return "fullyear"
    return None


def verify_summary_headings(html: str, stored: str, live: str) -> bool:
    """Source-verified summary headings: in the doc's own text, the
    two lost headings sit consecutively immediately before the first
    stored bullet, and the added bullets follow the last stored bullet
    consecutively. The doc — not a shape heuristic — proves the
    headings head the bullet run and the added bullets continue it:
    the CHD runs sit at doc lines 13-18 / 14-19, headings first, then
    the stored bullets, then the added bullets. Returns False when any
    of those facts is missing."""
    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    s_norm = [norm(x) for x in s_lines]
    l_norm = [norm(x) for x in l_lines]
    l_set = set(l_norm)
    s_set = set(s_norm)
    lost = [x for x in s_lines if norm(x) not in l_set]
    added = [x for x in l_lines if norm(x) not in s_set]
    if len(lost) != 2 or not added:
        return False
    stored_bullets = [x for x in s_lines if x.startswith("•")]
    if not stored_bullets:
        return False
    doc_lines = [
        norm(ln.strip())
        for ln in _html_to_text(html).split("\n")
        if ln.strip()
    ]
    try:
        i_first = doc_lines.index(norm(stored_bullets[0]))
    except ValueError:
        return False
    if i_first < 2:
        return False
    if doc_lines[i_first - 2 : i_first] != [norm(x) for x in lost]:
        return False
    # The stored bullets must run consecutively from the first one,
    # and the added bullets consecutively right after them.
    n_stored = len(stored_bullets)
    if doc_lines[i_first : i_first + n_stored] != [
        norm(x) for x in stored_bullets
    ]:
        return False
    j = i_first + n_stored
    if doc_lines[j : j + len(added)] != [norm(x) for x in added]:
        return False
    return True


def sweep_gate_s9(stored: str, live: str, html: str) -> str | None:
    """Gate S9: the summary-heading swap. Returns None when the swap
    is allowed, else the SKIP reason ("loss" — the row stays in the
    loss cohort exactly as before)."""
    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    if not s_lines or not l_lines:
        return "loss"
    s_norm = [norm(x) for x in s_lines]
    l_norm = [norm(x) for x in l_lines]
    l_set = set(l_norm)
    s_set = set(s_norm)
    lost = [x for x in s_lines if norm(x) not in l_set]
    added = [x for x in l_lines if norm(x) not in s_set]
    if len(lost) != 2:
        return "loss"
    kinds = [_head_kind(x) for x in lost]
    if any(k is None for k in kinds):
        return "loss"
    if sorted(kinds) != ["fullyear", "quarter"]:
        return "loss"
    # Batch 259: the tail bound was 4 — calibrated to the 6-line lede
    # budget, under which live served at most 4 bullets past the
    # sub-headlines. The bullet-run extension raises the lede to 12
    # content lines, so a CHD swap can now add up to 9 tail bullets
    # (10 served, 1 stored). The bound moves to 10: it still refuses
    # a swap bigger than anything the extractor can serve from one
    # bullet run, while the tail-run, order, doc-consecutiveness and
    # live-clean checks below do the real safety work.
    if not added or len(added) > 10:
        return "loss"
    if not all(x.startswith("•") for x in added):
        return "loss"
    # Stored-minus-headings must equal live-minus-added, in order,
    # and the added bullets must be a tail run of live.
    s_kept = [x for x in s_norm if x in l_set]
    l_kept = [x for x in l_norm if x in s_set]
    if s_kept != l_kept:
        return "loss"
    if [norm(x) for x in l_lines[len(l_lines) - len(added) :]] != [
        norm(x) for x in added
    ]:
        return "loss"
    if not _live_is_clean(l_lines, set(s_lines)):
        return "live-table"
    if not verify_summary_headings(html, stored, live):
        return "loss"
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
        rk = f"SKIP-{r9}"
        counts[rk] = counts.get(rk, 0) + 1
        skip_lists.setdefault(rk, []).append(key)
    if not DRY:
        con.commit()
    print(f"\nDRY_RUN={DRY} counts: {counts}")
    print(f"repaired (S9): {len(repaired)}: {', '.join(repaired)}")
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
