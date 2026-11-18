"""Batch 274 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
F x9 override.

Ford's exhibits are flattened page images: each page is one mega-line
prefixed with its bare page number. The leading-bullet block's
item-close rule ended the block one page early, stranding the next
page -- the segment table, the segment narrative, or the outlook
page. Batch 274's extractor fix adds a page-marker continuation
(suppress the close when the next line is the next page of the same
flattened body, carrying figures itself or in the bullets it
introduces) plus two heading breaks: a standalone "Cautionary Note
on Forward-Looking Statements" page ends the block (the page matched
the numbered-footnote-definition shape, so the footnote-definition
skip used to swallow it and the block ran on into the safe-harbor
risk bullets), and a "Conference Call Details" page ends it (call
logistics, not results; without the break the block ran through the
call page and the 9000-char cap truncated the card mid-sentence).

The gate chain re-syncs F 2026-09-30 via S4 (its stored row is a
lede + risk bullets; live is the lede + segment table, no risk
bullets). The other 9 F rows the gates refuse, because norm() glues
adjacent lines: its footnote-key rule `([,.])\\s+(\\d)` runs on the
whole string with `\\s` matching newlines, so a line ending in "."
or "," followed by a digit-starting line becomes one normed line,
and the gates' exact line-match fails even though every figure is
present. That is a diagnosed follow-up (fixing norm shifts the
census baseline for all 2543 rows), so this batch closes F via the
established deliberate-override pattern instead (figure-level gates,
like AXON/BNY/BKR/AMZN/COR/V in batches 266-270, 273).

Blast radius of the extractor fix (full 1,699-exhibit cache): exactly
9 rows move, all Ford, no other ticker. Figure-level check on the new
live: 0 missing $/% figures in every F row.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch274_repair.py
       .venv/bin/python scripts/batch274_repair.py
"""
import os
import re
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
from batch261_repair import sweep_gate_s13
from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"

FIG_RE = re.compile(r"\$ ?\d[\d,\.]* ?(?:billion|million|trillion)?|\d[\d,\.]* ?%|\(\d[\d,\.]*\) ?%?")

# key -> live distinctive fragment proving the stranded page is served.
FORD_KEYS = {
    "F_2024-06-30": "Business Segment Highlights",
    "F_2024-09-30": "Business Segment Highlights",
    "F_2024-12-31": "Ford Blue Segment Wholesales (000) 758 774",
    "F_2025-03-31": "Ford Blue Segment Wholesales (000) 626 588",
    "F_2025-06-30": "Ford Blue reported $661 million in EBIT",
    "F_2025-09-30": "A 2025 adjusted EBIT headwind of $1.5 billion to $2 billion",
    "F_2025-12-31": "Business Segment Highlights",
    "F_2026-03-31": "Business Segment Highlights",
    "F_2026-06-30": "Ford Blue EBIT of $5.0 billion to $5.5 billion",
}


def _live(key):
    return F.extract_press_release_highlights(
        open(f"{CACHE}/{key}.html", encoding="utf-8").read()
    )


def _missing_figures(stored: str, live: str) -> list[str]:
    live_n = norm(live)
    return [f for f in sorted(set(FIG_RE.findall(stored))) if norm(f) not in live_n]


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
            continue
        r13 = sweep_gate_s13(stored, live, html)
        if r13 is None:
            counts["S13"] = counts.get("S13", 0) + 1
            _resync(key, stored, live, cik, pe)
            continue
        rk = f"SKIP-{r12}"
        counts[rk] = counts.get(rk, 0) + 1
        skip_lists.setdefault(rk, []).append(key)

    # --- Batch 274 F override (deliberate, gated; see docstring) ---
    # The sweep above re-syncs F 2026-09-30 via S4; the other 9 F rows
    # are refused only by norm()'s cross-line glue (exact line-match
    # fails on glued mega-lines), not by any figure loss: the
    # figure-level gate below is the real check.
    for key, live_frag in FORD_KEYS.items():
        pe = key.split("_", 1)[1]
        row = con.execute(
            "SELECT q.press_release_highlights, q.cik "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'F' AND q.period_end = ?",
            (pe,),
        ).fetchone()
        stored, cik = row
        live = _live(key)
        s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
        l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
        live_bullets = [ln for ln in l_lines if ln.startswith("\u2022")]
        missing = _missing_figures(stored, live) if stored and live else ["(no text)"]
        gates = {
            "same-headline": (
                stored is not None
                and live is not None
                and s_lines
                and l_lines
                and s_lines[0] == l_lines[0]
            ),
            "zero-figure-loss": not missing,
            "live-figure-bullets": (
                live is not None
                and len(live_bullets) >= 3
                # A figure bullet carries a $ or % figure (FIG_RE), not
                # just a $: F 2024-09-30's bullets include "Ford Pro
                # revenue increases 13%" and "15 cents per share" --
                # real figures, no $ sign. The $-only calibration from
                # the AXON override would refuse it.
                and sum(1 for b in live_bullets if FIG_RE.search(b)) >= 3
            ),
            "segment-table-preserved": (
                live is not None
                and ("Business Segment Highlights" not in stored or "Business Segment Highlights" in live)
                and ("Total Company Highlights" not in stored or "Total Company Highlights" in live)
            ),
            "stranded-page-served": live is not None and live_frag in live,
            "no-truncation": live is not None and not live.rstrip().endswith("\u2026"),
            "not-already-in-sync": not (stored is not None and live is not None and norm(stored) == norm(live)),
        }
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  F-override SKIP {key}: failed gates {failed}"
                  + (f" missing_figs={missing[:6]}" if "zero-figure-loss" in failed else ""))
            continue
        print(f"  F-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (stranded page re-served, 0 figures lost)")
        if not DRY:
            con.execute(
                "UPDATE quarterly_financials "
                "SET press_release_highlights = ? "
                "WHERE cik = ? AND period_end = ?",
                (live, cik, pe),
            )
            repaired.append(f"{key} (override)")
            check = con.execute(
                "SELECT press_release_highlights FROM quarterly_financials "
                "WHERE cik = ? AND period_end = ?",
                (cik, pe),
            ).fetchone()[0]
            assert check == live, f"post-write mismatch for {key}"
            print(f"    {key} DB-verified byte-identical to live")
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
