"""Batch 247 repair: the highlights sweep, gate S6 — the ADSK x6 rows
batch 246 carried forward.

Each of the six ADSK loss rows differs from live in exactly two ways:

1. Dateline dash spacing: the stored dateline reads "SAN FRANCISCO,
   MAY 22, 2025 -- Autodesk ..." while live emits "2025-- Autodesk"
   (glued). Spacing-only — closed by the batch-247 norm rule in
   scripts/batch231_repair.py (canonicalize spaces around "--" when
   a 4-digit year precedes it, per line; the year anchor keeps the
   "Label -- prose" marker the batch-244 S5 classifier keys on). The
   norm blast (scripts/batch247_probe2.py census before / after)
   flips zero rows: no row's only difference was the dash, so the
   rule changes no classification on its own — its effect shows
   only through this gate.

2. A trailing table-furniture run: the stored row ends on a bare
   period label ("First Quarter Fiscal 2026") plus, on five of the
   six rows, the results-table units header ("(In millions, except
   percentages and per share amounts) Q1 FY26 YoY Change"). The live
   extraction drops both by design (they head the results table), but
   the S3 residue does not recognize them: _is_period_subheading
   requires a trailing "Results", and the units header matches no
   table predicate in its combined form.

Gate S6 is gate S4 with a trailing-furniture rescue in the loss
check: the stored lines live does not carry, that are not S3
residue, must sit in a suffix run of the stored row (1-3 lines),
anchored by a bare period label, every line a furniture shape or
already S3 residue (the units header is itself a table line, so
the run is a mix of the two) — and the run must verify against
the source document (verify_trailing_furniture): the run's lines
appear consecutively in the doc's text, after live's last line,
with a table-residue line immediately after them. That is what
makes the gate doc-aware rather than shape-only: a "First Quarter
Fiscal 2026" heading over prose live drops would not sit directly
before table data, so it could never pass. The 2026-04-30 row
carries only the label (no units header) and verifies the same way.

Still blocked by design (NOT repaired here): the remaining 183
SKIP-loss rows (content live genuinely drops — Amazon's business
bullets, letter prose, interleaved CINF quotes, Ford mega-lines,
PLTR pre-section quotes, DE's prose-separated quote, AXON letter
prose, BKR/BIIB); DRI 2026-08-30 live-table; ABNB 2024-12-31; COF
2025-06-30; DIS x4 added-table; ADBE 2025-11-28 + 2026-05-29; INTC
x6; V 2025-09-30; DG 2024-11-01; JPM's "n "-prefixed bullets; BRK.B
Q3 FY2026 mid-body table residue; KHC date-pair header; DLR TOC-only
live extraction; ABNB 2023-12-31; CCI 2026-09-30 guidance furniture,
LUV tail, SPG/MU/BMY tables, DIS footnote shape, batch-184 list, C
slide-deck exhibit, batch-157 gate skips, DASH truncated para; GILD's
guidance tail ends on a "Key Updates" heading; AppLovin's
"Summary:2" heading wart; wordy value lines as a future fuser class;
still-truncated stored highlights rows; the FAST/EL lede warts; the
AMT 2023-12-31 / 2024-03-31 / 2024-06-30 NULL-stored-highlights
seeding gap.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch247_repair.py
       .venv/bin/python scripts/batch247_repair.py
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
)
from tickerlens.data.filings import (
    _html_to_text,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"

# A bare period label heading a results table ("First Quarter Fiscal
# 2026"): quarter word + "Fiscal" + year, nothing else. The "Results"
# form is already S3 residue (_is_period_subheading); this is the
# label form the seed rows carry instead. No "Results", no figures
# beyond the year, no bullet — prose can never match it.
_BARE_PERIOD_LABEL_RE = re.compile(
    r"^(?:First|Second|Third|Fourth) Quarter Fiscal \d{4}$"
)
# A results-table units/period header ("(In millions, except
# percentages and per share amounts) Q1 FY26 YoY Change"): a
# parenthesized units phrase, a quarter code, and the YoY Change
# column label. The parenthetical + period code + column label
# together are table furniture by construction — a highlights bullet
# never carries all three.
_TABLE_UNITS_HEADER_RE = re.compile(
    r"^\(In [^)]+\)\s+Q[1-4] FY\d{2}\s+YoY Change$"
)


def _is_bare_period_label(ln: str) -> bool:
    return bool(_BARE_PERIOD_LABEL_RE.match(ln.strip()))


def _is_table_units_header(ln: str) -> bool:
    return bool(_TABLE_UNITS_HEADER_RE.match(ln.strip()))


def _is_trailing_furniture_line(ln: str) -> bool:
    return _is_bare_period_label(ln) or _is_table_units_header(ln)


def verify_trailing_furniture(
    html: str, live: str, run: list[str]
) -> bool:
    """Source-verified trailing furniture: the run's lines appear
    consecutively in the doc's own text, after live's last line, with
    a table-residue line immediately after them. The doc — not a
    shape heuristic — proves the label heads the results table: the
    ADSK run sits at doc lines 9-10, right after the served quote
    (line 8) and right before the "Revenue $ 1,633 15 %" data row.
    Returns False when any of those facts is missing, so a heading
    over dropped prose can never pass."""
    l_lines = non_empty(live)
    if not l_lines or not run:
        return False
    doc_lines = [
        norm(ln.strip())
        for ln in _html_to_text(html).split("\n")
        if ln.strip()
    ]
    run_norm = [norm(x) for x in run]
    live_last = norm(l_lines[-1])
    try:
        i_live = doc_lines.index(live_last)
    except ValueError:
        return False
    n = len(run)
    for j in range(i_live + 1, len(doc_lines) - n + 1):
        if doc_lines[j : j + n] != run_norm:
            continue
        after = doc_lines[j + n] if j + n < len(doc_lines) else ""
        if after and is_residue(after):
            return True
    return False


def sweep_gate_s6(stored: str, live: str, html: str) -> str | None:
    """Gate S6: gate S4 with the trailing-furniture rescue. Returns
    None when the swap is allowed, else the SKIP reason (same
    vocabulary as gate S4)."""
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
    # The loss check, with the S6 trailing-furniture rescue. The tail
    # run is the maximal suffix of stored lines live does not carry:
    # every line before it must be in live or S3 residue (the old
    # loss check), and every line in it must be furniture-shaped or
    # S3 residue — the units header is already S3 residue (a table
    # line), so the run is a mix of the two, not furniture alone.
    # The run must be anchored by a bare period label, be at most 3
    # lines, and verify against the doc (consecutive after live's
    # last line, table data immediately after). A stored row whose
    # tail is real content live drops fails here exactly as in S4.
    tail_start = len(s_lines)
    while tail_start > 0 and s_lines[tail_start - 1] not in live_set:
        tail_start -= 1
    for i, x in enumerate(s_lines[:tail_start]):
        if x not in live_set and not is_residue_s3(
            x, s_lines[i + 1] if i + 1 < len(s_lines) else "", live_set
        ):
            return "loss"
    run = s_lines[tail_start:]
    if run:
        if (
            len(run) > 3
            or not _is_bare_period_label(run[0])
            or any(
                not _is_trailing_furniture_line(x)
                and not is_residue_s3(
                    x,
                    s_lines[tail_start + j + 1]
                    if tail_start + j + 1 < len(s_lines)
                    else "",
                    live_set,
                )
                for j, x in enumerate(run)
            )
            or not verify_trailing_furniture(html, live, run)
        ):
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
    repaired: dict[str, list[str]] = {}
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
        r6 = sweep_gate_s6(stored, live, html)
        if r6 is None:
            counts["S6"] = counts.get("S6", 0) + 1
            repaired.setdefault("S6", []).append(key)
            if not DRY:
                con.execute(
                    "UPDATE quarterly_financials "
                    "SET press_release_highlights = ? "
                    "WHERE cik = ? AND period_end = ?",
                    (live, cik, pe),
                )
            print(f"    S6 {key} {len(stored)}->{len(live)}")
            continue
        rk = f"SKIP-{r6}"
        counts[rk] = counts.get(rk, 0) + 1
        skip_lists.setdefault(rk, []).append(key)
    if not DRY:
        con.commit()
    print(f"\nDRY_RUN={DRY} counts: {counts}")
    for cls, keys in sorted(repaired.items()):
        print(f"repaired ({cls}): {len(keys)}: {', '.join(keys)}")
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
