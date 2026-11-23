"""Batch 261 probe: CINF lede-vs-section selection + cache-wide
measurement of two candidate ranking rules.

CINF x6 (carried forward): the lede bullets (net income / operating
income / book value / value creation) never compete — the subsidiary
masthead lines ("The Cincinnati Insurance Company n The Cincinnati
Indemnity Company", Wingdings "n" separators) break the
_leading_bullet_block scan before the headline, and even if collected
the later P&C + investment sections out-score the lede on absolute
figure count (10 vs 5).

This probe prints, per CINF exhibit, the leading block, every anchored
section with (count, len, density), the current winner, and the gate
classification of stored-vs-live; then simulates two ranking
alternatives cache-wide and counts winner flips:
  (a) lede-priority: a financially-qualifying leading block wins outright
  (b) density-first: score by density (count/len) instead of count,
      earliest wins ties

Usage: .venv/bin/python scripts/batch261_probe.py [--cinf-only]
"""
import argparse
import glob
import os
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm
from batch242_repair import sweep_gate_s4
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


def _score(content):
    count = F._financial_line_count(content)
    density = count / max(len(content), 1)
    return (1, count) if (count >= 2 and density >= 0.4) else (0, 0)


def _candidates(lines):
    cands = []
    leading = F._leading_bullet_block(lines)
    if leading is not None:
        cands.append((None, leading, None, []))
    cands.extend(F._extract_highlights_sections_anchored(lines))
    return cands


def _current_winner(cands):
    if not cands:
        return None
    cs = list(cands)
    if any(
        a is not None
        and F._highlights_section_scope(a) == "quarter"
        and _score(c)[0] == 1
        for a, c, _, _ in cs
    ):
        cs = [
            (a, c, i, t)
            for a, c, i, t in cs
            if a is None or F._highlights_section_scope(a) != "fullyear"
        ]
    best = max(cs, key=lambda c: _score(c[1]))
    if _score(best[1])[0] <= 0:
        best = cs[0]
    return best


def _lede_priority_winner(cands):
    if not cands:
        return None
    cs = list(cands)
    if any(
        a is not None
        and F._highlights_section_scope(a) == "quarter"
        and _score(c)[0] == 1
        for a, c, _, _ in cs
    ):
        cs = [
            (a, c, i, t)
            for a, c, i, t in cs
            if a is None or F._highlights_section_scope(a) != "fullyear"
        ]
    for cand in cs:
        if cand[0] is None and _score(cand[1])[0] == 1:
            return cand
    best = max(cs, key=lambda c: _score(c[1]))
    if _score(best[1])[0] <= 0:
        best = cs[0]
    return best


def _density_winner(cands):
    if not cands:
        return None
    cs = list(cands)
    if any(
        a is not None
        and F._highlights_section_scope(a) == "quarter"
        and _score(c)[0] == 1
        for a, c, _, _ in cs
    ):
        cs = [
            (a, c, i, t)
            for a, c, i, t in cs
            if a is None or F._highlights_section_scope(a) != "fullyear"
        ]

    def dscore(content):
        count = F._financial_line_count(content)
        density = count / max(len(content), 1)
        return (1, density) if (count >= 2 and density >= 0.4) else (0, 0)

    best = max(cs, key=lambda c: dscore(c[1]))
    if dscore(best[1])[0] <= 0:
        best = cs[0]
    return best


def _classify(stored, live, html):
    if live is None:
        return "SKIP-live-none"
    if norm(stored) == norm(live):
        return "B in-sync"
    if sweep_gate_s4(stored, live) is None:
        return "S4 re-sync"
    cls5 = classify_s5(stored, live)
    if cls5 is not None:
        return f"SKIP-S5-{cls5}"
    if sweep_gate_s6(stored, live, html) is None:
        return "S6 re-sync"
    if sweep_gate_s7(stored, live) is None:
        return "S7 re-sync"
    if sweep_gate_s8(stored, live, html) is None:
        return "S8 re-sync"
    if sweep_gate_s9(stored, live, html) is None:
        return "S9 re-sync"
    if sweep_gate_s10(stored, live) is None:
        return "S10 re-sync"
    if sweep_gate_s11(stored, live) is None:
        return "S11 re-sync"
    if sweep_gate_s12(stored, live) is None:
        return "S12 re-sync"
    return "SKIP-loss"


def _lines(html):
    text = F._html_to_text(html)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    return F._split_bullet_runs(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cinf-only", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    stored = {
        f"{t}_{pe}": hl
        for t, pe, hl in con.execute(
            "SELECT c.ticker, q.period_end, q.press_release_highlights "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE q.press_release_highlights IS NOT NULL"
        )
    }

    print("===== CINF exhibits =====")
    for path in sorted(glob.glob(os.path.join(CACHE, "CINF_*.html"))):
        key = os.path.basename(path)[:-5]
        html = open(path, encoding="utf-8").read()
        lines = _lines(html)
        cands = _candidates(lines)
        live = F.extract_press_release_highlights(html)
        print(f"\n--- {key} (stored: {'yes' if key in stored else 'NO ROW'})")
        for anchor, content, idx, tail in cands:
            cnt = F._financial_line_count(content)
            print(
                f"  cand anchor={anchor!r} idx={idx} n={len(content)} "
                f"fig={cnt} dens={cnt / max(len(content), 1):.2f} "
                f"score={_score(content)}"
            )
            print(f"    first: {content[0][:110]!r}")
        cur = _current_winner(cands)
        lp = _lede_priority_winner(cands)
        dn = _density_winner(cands)
        print(f"  current winner: anchor={cur[0]!r} score={_score(cur[1])}")
        print(f"  lede-priority winner: anchor={lp[0]!r} score={_score(lp[1])}")
        print(f"  density-first winner: anchor={dn[0]!r}")
        if key in stored:
            print(f"  stored-vs-live: {_classify(stored[key], live, html)}")
            print(f"  stored first line: {stored[key].splitlines()[0][:110]!r}")
            print(f"  live first body: {(live or '').splitlines()[2][:110] if live and len(live.splitlines()) > 2 else ''!r}")

    if args.cinf_only:
        return
    print("\n===== cache-wide winner flips =====")
    lp_flips, dn_flips = [], []
    no_leading = 0
    for path in sorted(glob.glob(os.path.join(CACHE, "*.html"))):
        key = os.path.basename(path)[:-5]
        html = open(path, encoding="utf-8").read()
        lines = _lines(html)
        cands = _candidates(lines)
        if not cands:
            continue
        if cands[0][0] is not None:
            no_leading += 1
        cur = _current_winner(cands)
        lp = _lede_priority_winner(cands)
        dn = _density_winner(cands)
        if lp is not cur and lp[1] is not cur[1]:
            lp_flips.append((key, cur[0], _score(cur[1]), lp[0], _score(lp[1])))
        if dn is not cur and dn[1] is not cur[1]:
            dn_flips.append((key, cur[0], _score(cur[1]), dn[0], _score(dn[1])))
    print(f"exhibits with no leading-bullet candidate: {no_leading}")
    print(f"\nlede-priority flips: {len(lp_flips)}")
    for k, ca, cs, la, ls in lp_flips:
        print(f"  {k}: current anchor={ca!r} {cs} -> lede {ls}")
    print(f"\ndensity-first flips: {len(dn_flips)}")
    for k, ca, cs, da, ds in dn_flips:
        print(f"  {k}: current anchor={ca!r} {cs} -> density anchor={da!r} {ds}")


if __name__ == "__main__":
    main()
