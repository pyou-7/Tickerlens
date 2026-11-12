"""Batch 236 repair: re-sync stored management_guidance rows to the
batch-235 fused extraction, under the batch-235 gates plus two
extensions:

Gate A (fuse-only re-sync, unchanged): figures(new) == figures(stored)
as multisets, no residue in the new text, and the stored-vs-new diff is
explainable line by line.

Gate B (footnote-drop re-sync, extended): figures(new) ⊆ figures(stored)
and every removed figure sits in a dropped footnote/chrome line. The
extension is the wrapped footnote-def continuation: a removed line that
continues a footnote definition whose opener sits on the previous stored
line(s) — BMY's "3 February was calculated ... foreign" /
"exchange rates as of April 23, 2025.", EMR's "2 Underlying orders do
not" / "include AspenTech.", ELV's bare "3." def
"... serves as the estimated full" / "year adjustment amount.".
A continuation is recognized only when the previous stored line is a
footnote-def line (opener, bare-number key, def line, or continuation)
that ends mid-sentence (no terminal punctuation) and the line itself
starts lowercase and is not a table label/value line. Chrome figures
for gate B are now counted over REMOVED lines only (batch 235 counted
them over all stored lines, which could mask a removed figure that
also appears in a kept chrome line).

Tail-truncation clause (gate A and B share the explainability check):
a removed line that is the last non-blank stored line, ends with the
collector's "…" truncation marker, carries no figures, and is not a
table row is a dangling prose fragment, not content — CHD's
"Church & Dwight Co., Inc. (NYSE: CHD) will…" boilerplate tail.

Also reports (never writes) the cohorts it does not touch:
diff-figures (different vintage/section), new-residue (GE's interleaved
FCF row, EL/ELV "(Unaudited)" section labels — probe false positives),
stored-null (SKYD 2026-06-30), no-row.

Usage: dry-run (default, prints every re-sync + diff for inspection)
  .venv/bin/python scripts/batch236_repair.py
apply:
  .venv/bin/python scripts/batch236_repair.py --apply

Idempotent: re-running after --apply finds all targets in sync and
re-syncs nothing.
"""
import difflib
import json
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _GUIDANCE_FIGURE_RE,
    _GUIDANCE_RULE_LINE_RE,
    _guidance_footnote_opener,
    _is_guidance_prior_updated_header,
    _is_guidance_table_label,
    _is_guidance_value_line,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
NEW_JSON = "hidden_files/blast235_guidance_new.json"

_LOW_HIGH_ONLY_RE = re.compile(r"^(low|high)(\s+(low|high|end))*\s*$", re.I)
_BARE_NUMBER_KEY_RE = re.compile(r"^\d{1,3}[.)]$")
_BARE_MONTH_RE = re.compile(
    r"^(january|february|march|april|may|june|july|august|september|october|november|december)$",
    re.I,
)
_TERMINAL_PUNCT_RE = re.compile(r"[.!?…\"”')\]]\s*$")


def _figures(text: str) -> Counter:
    return Counter(
        re.sub(r"\s+", "", m.group(0)) for m in _GUIDANCE_FIGURE_RE.finditer(text)
    )


def _residue(lines: list[str]) -> list[str]:
    problems = []
    for i, ln in enumerate(lines):
        if _GUIDANCE_RULE_LINE_RE.match(ln):
            problems.append(f"rule line: {ln!r}")
        if _guidance_footnote_opener(ln):
            problems.append(f"footnote opener: {ln!r}")
        if _is_guidance_table_label(ln) and i + 1 < len(lines):
            if _is_guidance_value_line(lines[i + 1]):
                problems.append(f"unfused split row: {ln!r} / {lines[i + 1]!r}")
    return problems


def _norm_words(text: str) -> str:
    return re.sub(r"[^0-9a-z%]+", " ", text.lower()).strip()


def _is_def_continuation(ln: str, prev: str) -> bool:
    """True when ln continues a footnote definition whose previous line
    ends mid-sentence: it starts lowercase, the previous line carries no
    terminal punctuation, and ln is not a table row."""
    s = ln.strip()
    if not s or not s[0].islower():
        return False
    if _TERMINAL_PUNCT_RE.search(prev.strip()):
        return False
    if _GUIDANCE_RULE_LINE_RE.match(ln):
        return False
    if _is_guidance_table_label(ln) or _is_guidance_value_line(ln):
        return False
    return True


def _chrome_flags(s_lines: list[str]) -> list[bool]:
    """Per-line bool: True when the stored line is dropped chrome /
    footnote furniture rather than content: a rule line, a footnote
    opener, a Low/High-only header, a prior/updated header, a bare
    month line, a bare-number footnote key, the definition line right
    after a bare-number key, or a wrapped def-continuation line (a
    lowercase continuation of a footnote-def line that ends
    mid-sentence)."""
    flags: list[bool] = []
    prev = ""
    prev_is_def = False
    prev_is_bare_key = False
    for ln in s_lines:
        s = ln.strip()
        chrome = False
        is_def = False
        if _GUIDANCE_RULE_LINE_RE.match(ln):
            chrome = True
        elif _guidance_footnote_opener(ln):
            chrome = True
            is_def = True
        elif _LOW_HIGH_ONLY_RE.match(s):
            chrome = True
        elif _is_guidance_prior_updated_header(ln):
            chrome = True
        elif _BARE_MONTH_RE.match(s):
            chrome = True
        elif _BARE_NUMBER_KEY_RE.match(s):
            chrome = True
            is_def = True
        elif prev_is_bare_key:
            chrome = True
            is_def = True
        elif prev_is_def and _is_def_continuation(ln, prev):
            chrome = True
            is_def = True
        flags.append(chrome)
        prev = ln
        prev_is_def = is_def
        prev_is_bare_key = _BARE_NUMBER_KEY_RE.match(s) is not None
    return flags


def _is_tail_truncation(ln: str, is_last: bool) -> bool:
    """True when a removed line is the stored text's last line, ends with
    the collector's truncation marker, carries no figures, and is not a
    table row: a dangling prose fragment, not guidance content."""
    s = ln.strip()
    if not is_last or not s.endswith("…"):
        return False
    if _figures(ln):
        return False
    if _is_guidance_table_label(ln) or _is_guidance_value_line(ln):
        return False
    return True


def _diff_explainable(stored: str, new: str) -> list[str]:
    """Return a list of unexplained diff hunks (empty = explainable).
    Uses difflib opcodes on non-blank lines: a removed line must be
    dropped chrome, a tail-truncated fragment, or covered by an added
    fused line; an added line must be a fused form of stored lines."""
    s_lines = [ln for ln in stored.splitlines() if ln.strip()]
    n_lines = [ln for ln in new.splitlines() if ln.strip()]
    flags = _chrome_flags(s_lines)
    sm = difflib.SequenceMatcher(a=s_lines, b=n_lines, autojunk=False)
    problems: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        removed = s_lines[i1:i2]
        added = n_lines[j1:j2]
        added_words = " ".join(_norm_words(a) for a in added)
        for k, ln in enumerate(removed):
            idx = i1 + k
            if flags[idx]:
                continue
            if _is_tail_truncation(ln, idx == len(s_lines) - 1):
                continue
            words = _norm_words(ln).split()
            if words and all(w in added_words for w in words):
                continue
            problems.append(f"unexplained removed line: {ln!r}")
        for ln in added:
            words = _norm_words(ln).split()
            stored_words = " ".join(_norm_words(s) for s in s_lines)
            if words and all(w in stored_words for w in words):
                continue
            problems.append(f"unexplained added line: {ln!r}")
    return problems


def _removed_indices(s_lines: list[str], n_lines: list[str]) -> set[int]:
    sm = difflib.SequenceMatcher(a=s_lines, b=n_lines, autojunk=False)
    out: set[int] = set()
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            out.update(range(i1, i2))
    return out


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
    gate_b: list[tuple[str, str]] = []
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
        f_new, f_stored = _figures(new_text), _figures(stored)
        expl = _diff_explainable(stored, new_text)
        if f_new == f_stored and not expl:
            gate_a.append((ticker, period))
            continue
        if f_new - f_stored:
            skipped["diff-figures"] += 1
            skip_detail.append(
                (ticker, period, f"diff-figures added={dict(f_new - f_stored)}")
            )
            continue
        # Gate B: removed figures must sit in dropped chrome lines —
        # counted over removed lines only.
        removed_figs = f_stored - f_new
        s_lines = [ln for ln in stored.splitlines() if ln.strip()]
        n_lines = [ln for ln in new_text.splitlines() if ln.strip()]
        flags = _chrome_flags(s_lines)
        chrome_figs: Counter = Counter()
        for idx in sorted(_removed_indices(s_lines, n_lines)):
            if flags[idx]:
                chrome_figs.update(_figures(s_lines[idx]))
        if removed_figs - chrome_figs:
            skipped["diff-figures"] += 1
            skip_detail.append(
                (ticker, period, f"diff-figures removed-unexplained={dict(removed_figs - chrome_figs)}")
            )
            continue
        if expl:
            skipped["unexplained-diff"] += 1
            skip_detail.append((ticker, period, "unexplained: " + "; ".join(expl)))
            continue
        gate_b.append((ticker, period))

    print(f"gate A (fuse-only re-sync): {len(gate_a)}")
    print(f"gate B (footnote-drop re-sync): {len(gate_b)}")
    print("skipped:", dict(skipped))
    for ticker, period, why in sorted(skip_detail):
        print(f"  SKIP {ticker} {period}: {why}")

    targets = gate_a + gate_b
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
