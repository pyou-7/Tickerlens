"""Batch 239 repair: re-sync stored management_guidance rows to the
batch-239 extraction (the split-currency fix), under the batch-236 /
237 / 238 gates plus two new ones:

Gate F (new-guidance-found re-sync): the new extraction ADDS whole
guidance tables/sections the stored row lacks — American Tower's
Tenant Billings Growth + Capital Expenditures tables and FULL YEAR
OUTLOOK preamble, Clorox's adjusted-EPS reconciliation rows,
Simon's fused per-share table rows, Moody's Analytics segment rows.
A row re-syncs when every removed line is dropped chrome, tail
furniture, a truncation fragment, a fused re-render, or a lone
currency placeholder, every added line is guidance-shaped (a fused
row, a value/label/header/units line, outlook prose, or a wordy
value after its label), and the section is anchored — either a
shared fused value row (same table, same vintage: a new fused row
whose figures are all in the stored text) or the stub variant (the
stored row carries no $ or % at all and the new text opens on a
guidance heading).

Gate H (historical-results-table drop re-sync): the new extraction
DROPS a historical-results table the stored row wrongly carries —
GE Vernova's "Total Company Results" table (prior-year columns,
GAAP Metrics) trailing the segment-guidance bullets. A row re-syncs
when no figure is added, every removed line is dropped chrome, a
fused re-render, or part of the trailing historical-results table
block (headed by a results-table title, containing a GAAP Metrics
line and a period header), and the new text still carries guidance
figures.

Deliberately NOT re-synced (carried forward): the 5 new-residue
rows (EL/ELV "(Unaudited)" labels, GE interleaved FCF row, SKYD
fragmentary table); EMR's 4-word wrapped tail still unfused; plus
the standing list from batch 234. ELV 2024-03-31's blast diff has
no stored row at all (no quarterly_financials row for that period),
so there is nothing to re-sync — the extractor improvement applies
when the row is seeded.

Usage: dry-run (default, prints every re-sync + diff for inspection)
  .venv/bin/python scripts/batch239_repair.py
apply:
  .venv/bin/python scripts/batch239_repair.py --apply

Idempotent: re-running after --apply finds all targets in sync and
re-syncs nothing.
"""
import ast
import difflib
import json
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from tickerlens.data.filings import (
    _GUIDANCE_FIGURE_RE,
    _guidance_value_figures,
    _is_guidance_header_line,
    _is_guidance_period_label,
    _is_guidance_prior_updated_header,
    _is_guidance_table_label,
    _is_guidance_units_line,
    _is_guidance_value_line,
    _is_sentence_terminated,
    _split_guidance_fused_row,
)
from batch236_repair import (
    _chrome_flags,
    _diff_explainable,
    _figures,
    _is_tail_truncation,
    _norm_words,
    _removed_indices,
    _residue,
    _tail_furniture_indices,
)
from batch237_repair import _gate_a_passes, _gate_d_passes
from batch238_repair import _gate_e_passes

DB = "tickerlens.db"
NEW_JSON = "hidden_files/blast239_guidance_new.json"

_GUIDANCE_WORD_RE = re.compile(
    r"\b(outlook|guidance|forecast|estimates?|expected|raising|"
    r"reaffirming|increasing|reiterates|reaffirm)\b",
    re.IGNORECASE,
)
# A results-table title: the heading of a historical-results table
# ("Total Company Results") as opposed to a guidance heading.
_RESULTS_TITLE_RE = re.compile(r"total (company )?results", re.IGNORECASE)
_GAAP_METRICS_RE = re.compile(r"gaap metrics", re.IGNORECASE)
_RESULTS_PERIOD_RE = re.compile(
    r"(three|twelve|nine|six) months ended|year-on-year|year-on-$",
    re.IGNORECASE,
)


def _is_loose_label(s: str) -> bool:
    """True for a label-like phrase, without the fuser's verb /
    qualifier guards: 1-12 words, alphabetic, unterminated, and
    digit-free once footnote keys are stripped. The gate's fused-row
    check needs the looser shape because real fused rows carry
    verb-y labels ("Start-up capital projects" — "projects" is a
    verb word) and footnote-keyed labels ("Discretionary capital
    projects(2)"), which _is_guidance_table_label refuses; the
    anchor and figure accounting carry the safety, not the label
    predicate."""
    s = s.strip().rstrip(":")
    words = s.split()
    if not 1 <= len(words) <= 12:
        return False
    if not any(ch.isalpha() for ch in s):
        return False
    if _is_sentence_terminated(s):
        return False
    t = re.sub(r"\([0-9a-z]\)", "", s)
    t = re.sub(r"\d+$", "", t).replace("*", "")
    return not re.search(r"\d", t)


def _is_values_tail(s: str) -> bool:
    """True when s is only figures plus table joiners (" / ", " to ",
    " – ", "> ", "~ ", "N/A", "NC") — the values half of a fused
    row. Figure spans are removed first (the figure regex also
    matches a bare parenthesized key, so "(2)" never strands); what
    is left must be joiner words and punctuation only."""
    if not _guidance_value_figures(s):
        return False
    rest = _GUIDANCE_FIGURE_RE.sub(" ", s)
    rest = re.sub(
        r"\b(to|n/a|nc|billion|million|thousand)\b", " ", rest, flags=re.I
    )
    rest = re.sub(r"[^0-9a-z]+", " ", rest.lower())
    return not rest.strip()


def _is_fused_row_line(ln: str) -> bool:
    """True for an already-fused guidance-table row, colon-joined
    ("Discretionary capital projects(2): $ 780 to $ 810",
    "Estimated net income ...: $6.67 / $6.92") or bare
    ("Total Tenant Billings Growth ~4.3% >7% ~5.5%",
    "Start-up capital projects 65 to 85"). Looser than
    _split_guidance_fused_row: the fuser's own joiner (" / ") and
    qualifier (">7%") break its value-line predicate, and its verb
    guard refuses "Start-up capital projects" — but a fused row is
    still recognizable as label + values-tail, and the gate's anchor
    proves the row belongs to this table."""
    if ": " in ln:
        label, values = ln.split(": ", 1)
        if _is_loose_label(label) and _is_values_tail(values):
            return True
    m = _GUIDANCE_FIGURE_RE.search(ln)
    if m:
        label, values = ln[: m.start()].strip(), ln[m.start() :].strip()
        if label and _is_loose_label(label) and _is_values_tail(values):
            return True
    return False


def _squash(s: str) -> str:
    """Alphanumeric-only lowercased form: "free cash fl ow" and
    "free cash flow" squash equal, so a de-glued re-render
    ("• Power :" -> "• Power:", "an d" -> "and") matches its stored
    line exactly. Only spacing/punctuation may differ — the digits
    and words must be identical."""
    return re.sub(r"[^0-9a-z]+", "", s.lower())


def _is_spacing_rerender(ln: str, lines: list[str]) -> bool:
    """True when ln is a spacing/punctuation re-render of one of the
    given lines."""
    sq = _squash(ln)
    return any(_squash(x) == sq for x in lines)


def _is_guidance_shaped_added_line(
    ln: str, added: list[str], k: int, stored_words: str, s_lines: list[str]
) -> bool:
    """True when an added line is guidance-shaped: a fused re-render
    of stored lines, a spacing re-render, a table row / value /
    label / header / units line, an outlook heading or intro line,
    outlook prose (or prose in a block that carries outlook prose),
    or a wordy value line right after its label ("MA Revenue" /
    "Increase in the mid-single-digit percent range NC" — the
    batch-234 wordy-value class, figure-less by construction)."""
    words = _norm_words(ln).split()
    if words and all(w in stored_words for w in words):
        return True
    if _is_spacing_rerender(ln, s_lines):
        return True
    if _is_guidance_value_line(ln):
        return True
    if _is_guidance_table_label(ln):
        return True
    if _is_guidance_header_line(ln):
        return True
    if _is_guidance_period_label(ln):
        return True
    if _is_guidance_units_line(ln):
        return True
    if _is_guidance_prior_updated_header(ln):
        return True
    if _split_guidance_fused_row(ln) is not None:
        return True
    if _is_fused_row_line(ln):
        return True
    if ln.strip().lower() == "previous":
        return True
    if _GUIDANCE_WORD_RE.search(ln) and "$" not in ln and "%" not in ln:
        return True
    if _is_sentence_terminated(ln) and _GUIDANCE_WORD_RE.search(ln):
        return True
    if _is_sentence_terminated(ln) and any(
        _is_sentence_terminated(a) and _GUIDANCE_WORD_RE.search(a)
        for a in added
    ):
        return True
    if (
        k > 0
        and not _figures(ln)
        and _is_guidance_table_label(added[k - 1])
    ):
        return True
    return False


def _removed_line_ok(
    ln: str,
    idx: int,
    flags: list[bool],
    tail_idx: set[int],
    s_lines: list[str],
    added: list[str],
    added_words: str,
) -> bool:
    """True when a removed line is explainable: dropped chrome, tail
    furniture, a truncation fragment, a fused re-render, a spacing
    re-render, a lone currency placeholder ("$" / "%" — a
    split-cell remnant carrying no figure and no words), a page
    line ("Page 3 of 13"), or a lone "End" (the second half of a
    wrapped "Low End" / "High End" column header — the Low/High
    halves are already chrome)."""
    if flags[idx] or idx in tail_idx:
        return True
    if _is_tail_truncation(ln, idx == len(s_lines) - 1):
        return True
    if not _norm_words(ln).strip() and not _figures(ln):
        return True
    if re.match(r"(?i)^page\s+\d+(\s+of\s+\d+)?$", ln.strip()):
        return True
    if ln.strip().lower() == "end":
        return True
    if _is_spacing_rerender(ln, added):
        return True
    words = _norm_words(ln).split()
    return bool(words) and all(w in added_words for w in words)


def _gate_f_anchor(stored: str, new_text: str) -> bool:
    """Section anchor: either a shared fused value row (a new fused
    row whose figures — $ or % bearing — are all in the stored text,
    proving the same table and vintage) or the stub variant (the
    stored row carries no $ or % at all and the new text opens on a
    guidance heading)."""
    s_lines = [ln for ln in stored.splitlines() if ln.strip()]
    n_lines = [ln for ln in new_text.splitlines() if ln.strip()]
    f_stored = _figures(stored)
    for ln in n_lines:
        if not _is_fused_row_line(ln):
            continue
        figs = _figures(ln)
        if not figs:
            continue
        if not any("$" in f or "%" in f for f in figs):
            continue
        if not (figs - f_stored):
            return True
    if "$" not in stored and "%" not in stored:
        if n_lines and _GUIDANCE_WORD_RE.search(n_lines[0]):
            if "$" in new_text or "%" in new_text:
                return True
    return False


def _gate_f_passes(stored: str, new_text: str) -> bool:
    """Gate F: new-guidance-found re-sync (see module docstring)."""
    s_lines = [ln for ln in stored.splitlines() if ln.strip()]
    n_lines = [ln for ln in new_text.splitlines() if ln.strip()]
    if not s_lines or not n_lines:
        return False
    if "$" not in new_text and "%" not in new_text:
        return False
    # Stub mode: the stored row carries no $ or % at all, so it holds
    # no guidance value to lose — a removed line only has to be
    # data-less (not a value line, not a fused row). The shared-row
    # mode keeps the strict removed-line rule.
    stub = "$" not in stored and "%" not in stored
    flags = _chrome_flags(s_lines)
    tail_idx = _tail_furniture_indices(s_lines, n_lines, new_text)
    stored_words = " ".join(_norm_words(s) for s in s_lines)
    sm = difflib.SequenceMatcher(a=s_lines, b=n_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        removed = s_lines[i1:i2]
        added = n_lines[j1:j2]
        added_words = " ".join(_norm_words(a) for a in added)
        for k, ln in enumerate(removed):
            if _removed_line_ok(
                ln, i1 + k, flags, tail_idx, s_lines, added, added_words
            ):
                continue
            if stub and not _is_guidance_value_line(ln) and not _is_fused_row_line(ln):
                continue
            return False
        for k, ln in enumerate(added):
            if not _is_guidance_shaped_added_line(
                ln, added, k, stored_words, s_lines
            ):
                return False
    return _gate_f_anchor(stored, new_text)


def _historical_results_table_indices(
    s_lines: list[str], removed_idx: set[int]
) -> set[int]:
    """Indices of a trailing historical-results table block: a
    contiguous removed run that is a suffix of the stored text and
    contains a results-table title (the run may start with
    spacing-rerender lines of kept guidance — GE Vernova's bullets
    de-glue in the same replace opcode — so the title is searched
    for inside the run, not required at its head), a GAAP Metrics
    line, and a period header. Empty when no such block exists."""
    if not removed_idx:
        return set()
    n = len(s_lines)
    # Maximal contiguous removed runs.
    runs: list[list[int]] = []
    cur: list[int] = []
    for i in sorted(removed_idx):
        if cur and i == cur[-1] + 1:
            cur.append(i)
        else:
            if cur:
                runs.append(cur)
            cur = [i]
    if cur:
        runs.append(cur)
    for run in runs:
        if run[-1] != n - 1:
            continue
        title_at = None
        for i in run:
            if _RESULTS_TITLE_RE.search(s_lines[i].strip()):
                title_at = i
                break
        if title_at is None:
            continue
        body = "\n".join(s_lines[i] for i in run if i >= title_at)
        if not _GAAP_METRICS_RE.search(body):
            continue
        if not _RESULTS_PERIOD_RE.search(body):
            continue
        return {i for i in run if i >= title_at}
    return set()


def _is_heading_fragment(ln: str, idx: int) -> bool:
    """True for a short figure-less heading fragment at the head of
    the stored text ("2025 financial guidance. ”" — the sentence's
    opening, orphaned when the new extraction starts at the section
    heading). It carries no $ or % figure, so no guidance value is
    lost with it."""
    if idx != 0:
        return False
    if "$" in ln or "%" in ln:
        return False
    return len(ln.split()) <= 8


def _gate_h_passes(stored: str, new_text: str) -> bool:
    """Gate H: historical-results-table drop re-sync (see module
    docstring)."""
    s_lines = [ln for ln in stored.splitlines() if ln.strip()]
    n_lines = [ln for ln in new_text.splitlines() if ln.strip()]
    if not s_lines or not n_lines:
        return False
    if "$" not in new_text and "%" not in new_text:
        return False
    f_new, f_stored = _figures(new_text), _figures(stored)
    if f_new - f_stored:
        return False
    flags = _chrome_flags(s_lines)
    tail_idx = _tail_furniture_indices(s_lines, n_lines, new_text)
    stored_words = " ".join(_norm_words(s) for s in s_lines)
    removed_idx = _removed_indices(s_lines, n_lines)
    table_idx = _historical_results_table_indices(s_lines, removed_idx)
    sm = difflib.SequenceMatcher(a=s_lines, b=n_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        removed = s_lines[i1:i2]
        added = n_lines[j1:j2]
        added_words = " ".join(_norm_words(a) for a in added)
        for k, ln in enumerate(removed):
            idx = i1 + k
            if idx in table_idx:
                continue
            if _is_heading_fragment(ln, idx):
                continue
            if not _removed_line_ok(
                ln, idx, flags, tail_idx, s_lines, added, added_words
            ):
                return False
        for ln in added:
            if _is_spacing_rerender(ln, s_lines):
                continue
            words = _norm_words(ln).split()
            if words and all(w in stored_words for w in words):
                continue
            return False
    return True


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
