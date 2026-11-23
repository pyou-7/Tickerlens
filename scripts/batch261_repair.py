"""Batch 261 repair: gate S13 (bullet-superset + quote-tail truncation)
plus the re-sync pass for the rows it blesses.

S13 shape (CINF Q1/Q2 x4): stored carries the Investment-section
bullets + a long CEO-quote run (3 quote groups); live carries the
Insurance + Investment bullets — a strict bullet superset — and only
the first 3 quote lines, the designed batch-246/249 quote cap. The
removed stored lines are quote lines and their group headings, all
after the last stored bullet; the added live lines are financial
bullets and the heading that introduces them.

The full-census simulation in scripts/batch261_s13_probe.py shows S13
blesses exactly those 4 rows and nothing else. Two refusals pin the
narrowness: the CINF Q3 lede rows (stored bullets lost — a different
section, not a superset) and BKR 2024-12-31 (stored also drops its
dateline, which the gate refuses via the heading-shape bound: the
dateline is a 30-word dated sentence, not a quote-group heading, so
it cannot pass as quote-tail material. The dateline guard is
defense-in-depth for predicate-recognized dateline shapes — the BKR
dateline's parenthesized date does not match _is_dateline_sentence,
so the shape bound is what stops it).

The runner re-runs the full gate chain (S4/S5/S6/S7/S8/S9/S10/S11/S12
then S13) and re-syncs the rows the gates bless (S4/S9/S10/S11/S12/
S13), exactly as the batch-260 repair did. It is idempotent (dry
re-run finds 0 S13 rows).

Usage: DRY_RUN=1 .venv/bin/python scripts/batch261_repair.py
       .venv/bin/python scripts/batch261_repair.py
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import non_empty, norm
from batch241_repair import _is_dateline_sentence
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
from batch255_repair import sweep_gate_s12
from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"

_BULLET_FIRST = "•●–—◾◦▪■·○*"


def _is_bullet(ln: str) -> bool:
    s = ln.strip()
    return bool(s) and (s[0] in _BULLET_FIRST or bool(F._BULLET_LEAD_RE.match(s)))


def _is_financial(ln: str) -> bool:
    return bool(F._FINANCIAL_LINE_RE.search(ln))


def _is_quote_run_line(ln: str) -> bool:
    """True for one line of a multi-line executive quote run.

    _is_executive_quote_line requires the quote to CLOSE on the same
    line, so it misses wrapped quotes: CINF's quote groups span 3
    lines each, opening on the attribution line and closing on the
    third. A run line either opens with a quote mark (a wrapped
    continuation) or is an attribution-first opener (quote verb +
    opening mark, even unclosed). A line starting with a curly quote
    is a quote continuation in flattened releases, never prose.
    """
    s = ln.strip()
    if not s:
        return False
    if s[0] in ("“", '"'):
        return True
    m = re.search(r"[“\"]", s)
    if m is None:
        return False
    return bool(F._QUOTE_VERB_RE.search(s[: m.start()]))


def _is_quote_group_heading(ln: str) -> bool:
    """True for a short figure-free label heading a quote group
    ("Keeping Our Focus", "Committed to Long-Term Investment
    Strategy"). The adjacency exemption must be heading-shaped: a
    dateline also precedes the quote run (BKR) but is a 30-word
    dated sentence, never a heading — without the shape bound it
    would pass as a "heading" and the gate would bless dateline
    loss as quote loss."""
    s = ln.strip()
    if not s or len(s.split()) > 8:
        return False
    if "$" in s or any(c.isdigit() for c in s):
        return False
    if s[0] in ("“", '"', "•"):
        return False
    return True


def sweep_gate_s13(stored: str, live: str, html=None) -> str | None:
    """None when S13 blesses the re-sync, else a refusal reason.

    Blesses iff: headlines align; every stored bullet line is present
    in live (normalized); live has strictly more bullet lines than
    stored; every stored line not in live sits after the last stored
    bullet and is a quote-run line or a quote-group heading (a dateline
    is refused outright); every live line not in stored is a financial
    bullet or a figure-free heading immediately followed by a bullet.
    """
    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    s_lines = _split_flattened(s_lines, l_lines)
    s_lines = _strip_leading_chrome(s_lines)
    s_lines, relation = _align_headline(s_lines, l_lines)
    if relation is None:
        return "first-diff"
    live_norm = {norm(x) for x in l_lines}
    stored_norm_set = {norm(x) for x in s_lines}
    s_bullets = [x for x in s_lines if _is_bullet(x)]
    l_bullets = [x for x in l_lines if _is_bullet(x)]
    if not s_bullets:
        return "no-stored-bullets"
    missing = [b for b in s_bullets if norm(b) not in live_norm]
    if missing:
        return f"stored-bullet-lost:{missing[0][:60]!r}"
    if len(l_bullets) <= len(s_bullets):
        return "no-bullet-gain"
    # Removed stored lines: quote-tail only, after the last bullet.
    last_bullet_idx = max(i for i, x in enumerate(s_lines) if _is_bullet(x))
    for i, x in enumerate(s_lines):
        if norm(x) in live_norm:
            continue
        if i <= last_bullet_idx:
            return f"removed-before-last-bullet:{x[:60]!r}"
        if _is_dateline_sentence(x):
            return f"removed-dateline:{x[:60]!r}"
        nxt = s_lines[i + 1] if i + 1 < len(s_lines) else ""
        prv = s_lines[i - 1] if i > 0 else ""
        if _is_quote_run_line(x):
            continue
        if (_is_quote_run_line(nxt) or _is_quote_run_line(prv)) and (
            _is_quote_group_heading(x)
        ):
            continue
        return f"removed-not-quote-tail:{x[:60]!r}"
    # Added live lines: financial bullets or headings introducing bullets.
    for i, x in enumerate(l_lines):
        if norm(x) in stored_norm_set:
            continue
        if _is_bullet(x) and _is_financial(x):
            continue
        nxt = l_lines[i + 1] if i + 1 < len(l_lines) else ""
        if _is_bullet(nxt) and "$" not in x and not any(c.isdigit() for c in x):
            continue
        return f"added-not-bullet-or-heading:{x[:60]!r}"
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

    def _resync(key, stored, live, cik, pe):
        repaired.append(key)
        if not DRY:
            con.execute(
                "UPDATE quarterly_financials "
                "SET press_release_highlights = ? "
                "WHERE cik = ? AND period_end = ?",
                (live, cik, pe),
            )
        print(f"    {key} {len(stored)}->{len(live)}")

    for t, pe, stored, cik in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            counts["SKIP-nocache"] = counts.get("SKIP-nocache", 0) + 1
            continue
        html = open(path, encoding="utf-8").read()
        live = F.extract_press_release_highlights(html)
        if live is None:
            counts["SKIP-live-none"] = counts.get("SKIP-live-none", 0) + 1
            continue
        if norm(stored) == norm(live):
            counts["B"] = counts.get("B", 0) + 1
            continue
        if sweep_gate_s4(stored, live) is None:
            counts["S4"] = counts.get("S4", 0) + 1
            _resync(key, stored, live, cik, pe)
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
            _resync(key, stored, live, cik, pe)
            continue
        r10 = sweep_gate_s10(stored, live)
        if r10 is None:
            counts["S10"] = counts.get("S10", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        r11 = sweep_gate_s11(stored, live)
        if r11 is None:
            counts["S11"] = counts.get("S11", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        r12 = sweep_gate_s12(stored, live)
        if r12 is None:
            counts["S12"] = counts.get("S12", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        r13 = sweep_gate_s13(stored, live, html)
        if r13 is None:
            counts["S13"] = counts.get("S13", 0) + 1
            _resync(key, stored, live, cik, pe)
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
