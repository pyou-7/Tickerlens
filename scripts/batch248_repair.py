"""Batch 248 repair: the highlights sweep, gate S7 — the spacing-only
swap.

The batch-248 probe decomposes the 183 SKIP-loss rows and finds 15
whose stored-vs-live difference is spacing only: the seed-era stored
rows carry a stray space inside a word (\"Re cent\", \"M acquarie\",
\"JD Powe r\", \"Equivalen ts\", \"com pared\", \"Strategi c\", \"wer e\",
\"an d\"), a space inside curly quotes (\"See “ Reconciliation ...\"
vs \"See “Reconciliation ...”, DE's trailing \"succeed. ”\"), a
spaced slash (\"Y /Y\"), or a space before a closing paren after a
trademark (\"IBX® )\"). The affected rows:

  APLD x6 (quote spaces + \"Re cent\" + \"M acquarie\"), AXP 2026-06-30
  (\"JD Powe r\"), CRM 2024-10-31 (\"Y /Y\", \"an d\"), CRWD x2
  (\"Equivalen ts\", \"com pared\"), DE 2026-08-02 (trailing quote
  space), EQIX 2025-06-30 (\"IBX® )\"), ET x3 (\"wer e\",
  \"Strategi c Highlights\").

Gate S7 is gate S4 with a spacing-equivalence rescue in the loss
check: a stored line absent from live is excused when it is
spacing-equivalent to a live line — the two lines share the same
non-space character sequence AND the same digit runs, and differ
only by spaces. The digit-run condition is load-bearing: it is what
keeps \"10 0\" vs \"100\" (a figure change, not spacing) from ever
passing, and the non-space-sequence condition is what keeps any
added, dropped, or changed word out. The rescue is symmetric: every
live line must also be in stored, spacing-equivalent to a stored
line, or S3 residue — so live cannot smuggle in added content under
the spacing cover. Every other gate-S4 condition is unchanged
(dateline check, live-table fraction, added-table, tail, fragment).

No norm() change ships with this batch, deliberately: the quote-space
and split-word cases are all covered by the gate's pairwise check,
and the batch-247 lesson is that a global comparison change needs a
blast of its own — the gate is the narrower instrument here.

Still blocked by design (NOT repaired here): the remaining 168
SKIP-loss rows (real content live drops — Amazon business bullets,
executive quotes in other shapes, letter prose); ABNB 2024-12-31
(fragment), COF 2025-06-30 (tail), DIS x4 (added-table), DRI
2026-08-30 (live-table); plus the standing list from batch 247.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch248_repair.py
       .venv/bin/python scripts/batch248_repair.py
"""
import difflib
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
from batch247_repair import sweep_gate_s6
from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"

_DIGIT_RUN_RE = re.compile(r"\d+")


def _space_only_opcodes(a: str, b: str) -> list | None:
    """Opcodes between a and b if they differ only by spaces, else
    None. A replace/insert/delete opcode is allowed only when the
    changed span is all spaces."""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete" and a[i1:i2].strip() == "":
            continue
        if tag == "insert" and b[j1:j2].strip() == "":
            continue
        return None
    return sm.get_opcodes()


def spacing_equivalent(a: str, b: str) -> bool:
    """True when a and b differ only by spaces that never join two
    digit runs. Two conditions, both load-bearing:

    - the non-space character sequences are identical, so no word
      or figure is added, dropped, or changed — only spacing moves;
    - the digit runs are identical, so a space between two digits
      can never be dropped or added: \"10 0\" vs \"100\" is a figure
      change, not a spacing artifact, and is refused.

    A space between two letters (\"Re cent\" vs \"Recent\"), next to a
    curly quote (\"See “ Reconciliation\" vs \"See “Reconciliation\"),
    around a slash (\"Y /Y\" vs \"Y/Y\"), or before a closing paren
    (\"IBX® )\" vs \"IBX®)\") all pass; any content difference fails.
    """
    if a == b:
        return True
    if "".join(a.split()) != "".join(b.split()):
        return False
    if _DIGIT_RUN_RE.findall(a) != _DIGIT_RUN_RE.findall(b):
        return False
    return _space_only_opcodes(a, b) is not None


def sweep_gate_s7(stored: str, live: str) -> str | None:
    """Gate S7: gate S4 with the spacing-equivalence rescue in the
    loss check, applied symmetrically. Returns None when the swap is
    allowed, else the SKIP reason (same vocabulary as gate S4)."""
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
    # The loss check, with the S7 spacing rescue: a stored line live
    # does not carry is excused only when it is spacing-equivalent
    # to a live line (same characters, same digit runs, spaces only).
    # S3 residue is excused exactly as in S4.
    for i, x in enumerate(s_lines):
        if x in live_set:
            continue
        nxt = s_lines[i + 1] if i + 1 < len(s_lines) else ""
        if is_residue_s3(x, nxt, live_set):
            continue
        if any(spacing_equivalent(x, y) for y in l_lines):
            continue
        return "loss"
    # Symmetric coverage: live may not add content the stored row
    # never had. A live line must be in stored, spacing-equivalent
    # to a stored line, or S3 residue (a residue line live carries
    # is table furniture, already policed by the fraction check).
    s_set = set(s_lines)
    for y in l_lines:
        if y in s_set:
            continue
        if any(spacing_equivalent(y, x) for x in s_lines):
            continue
        if is_residue(y):
            continue
        return "added-content"
    lfrac = sum(1 for x in l_lines if is_residue(x)) / max(len(l_lines), 1)
    if lfrac >= 0.4 or has_dateline_table_shape(l_lines):
        return "live-table"
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
        r7 = sweep_gate_s7(stored, live)
        if r7 is None:
            counts["S7"] = counts.get("S7", 0) + 1
            repaired.setdefault("S7", []).append(key)
            if not DRY:
                con.execute(
                    "UPDATE quarterly_financials "
                    "SET press_release_highlights = ? "
                    "WHERE cik = ? AND period_end = ?",
                    (live, cik, pe),
                )
            print(f"    S7 {key} {len(stored)}->{len(live)}")
            continue
        # Keep the census comparable: report the pre-S7 (S6) reason.
        r6 = sweep_gate_s6(stored, live, html)
        rk = f"SKIP-{r6 if r6 is not None else r7}"
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
