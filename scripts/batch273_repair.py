"""Batch 273 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
AXON x6 override.

Axon's stored rows for 6 quarters are stale snapshots of the
seed-era extractor: headline + shareholder-letter prose (\"Axon AI --
The AI Era Plan\", \"Axon Week 2025\", \"Axon Software & Services\",
\"Axon 911\", the 2026 product-ecosystem letter, \"The Axon Ecosystem\"),
each ~2800-4000 chars and truncated mid-sentence or mid-list by the
old 4000-char cap (2025-06-30 ends on the dangling \"\u2022Draft One: 11
hours\"; 2026-06-30 ends mid-sentence on a drone-response anecdote).
The current extractor serves the lede fallback for these rows (no
leading block, no section anchor): headline + 4-5 figure bullets
(Software & Services / Cloud & Services revenue, ARR, net income /
non-GAAP net income / Adjusted EBITDA, raised outlook) + the lede
paragraph opening the letter.

The two Q4 siblings (2024-12-31, 2025-12-31) already store the live
shape (stored == live under norm) -- the consistency cross-check,
and a re-seed reproduces the live shape for all 6.

The design question is the one settled in batches 266-270 (BNY,
BKR, AMZN, COR, V): the highlights card's job is the quarter's key
financial figures, and the stored prose is narrative detail -- live
carries the headline revenue / ARR / net-income / EBITDA / outlook
figures the stored row lacks as bullets, while the stored row's
unique figures are narrative, not quarterly figures (the $159B total
addressable market and $74B market-opportunity figures in the
2025-09-30 letter; the 70%/75% time-savings and 40%/120% report-
writing figures elsewhere). The stored \"\u2022\" lines, where present,
are customer quotes and product-feature lists (\"Sense: Connected
sensors identify an incident...\"), not figure bullets. The stored
prose is a partial capture, not an editorial choice: every row is
truncated by the old cap.

The F x6 group was diagnosed in this batch and is NOT re-synced:
live gains the 4 figure bullets + dateline + quotes but DROPS the
\"Business Segment Highlights\" table (Ford Blue / Model e / Pro
wholesales, revenue, EBIT) that the stored rows hold, so it is a
genuine trade-off, not a stale-snapshot repair -- it needs a
decision (or an extractor change that serves both tables) of its
own. The AXON re-sync is clean: no figure loss, Q4 siblings
already in sync.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch273_repair.py
       .venv/bin/python scripts/batch273_repair.py
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

# key -> (stored distinctive fragment, live distinctive fragment).
AXON_KEYS = {
    "AXON_2024-09-30": (
        "Axon AI \u2014 The AI Era Plan",
        "Axon Cloud & Services revenue grows 36% to $203 million",
    ),
    "AXON_2025-03-31": (
        "Axon Week 2025",
        "Software & Services revenue grows 39% to $263 million",
    ),
    "AXON_2025-06-30": (
        "Axon Software & Services",
        "Software & Services revenue grows 39% to $292 million",
    ),
    "AXON_2025-09-30": (
        "Axon 911",
        "Software & Services revenue grows 41% to $305 million",
    ),
    "AXON_2026-03-31": (
        "In April, Axon introduced a series of innovations",
        "Software & Services revenue grows 35% to $355 million",
    ),
    "AXON_2026-06-30": (
        "The Axon Ecosystem",
        "Annual recurring revenue grows 39% to $1.6 billion",
    ),
}
AXON_SIBLINGS = ("AXON_2024-12-31", "AXON_2025-12-31")

FIGURE_BULLET_RE = re.compile(r"\u2022.*\$.*(?:revenue|income|EBITDA)", re.I)


def _live(key):
    return F.extract_press_release_highlights(
        open(f"{CACHE}/{key}.html", encoding="utf-8").read()
    )


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

    # --- Batch 273 AXON override (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1113, SKIP-loss 93).
    sib_ok = []
    for sib in AXON_SIBLINGS:
        sib_pe = sib.split("_", 1)[1]
        sib_stored = con.execute(
            "SELECT q.press_release_highlights "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'AXON' AND q.period_end = ?",
            (sib_pe,),
        ).fetchone()[0]
        sib_live = _live(sib)
        ok = (
            sib_stored is not None
            and sib_live is not None
            and norm(sib_stored) == norm(sib_live)
            and FIGURE_BULLET_RE.search(sib_live) is not None
        )
        sib_ok.append(ok)
        print(f"  sibling {sib} already-live-shape: {ok}")
    for key, (s_frag, l_frag) in AXON_KEYS.items():
        pe = key.split("_", 1)[1]
        row = con.execute(
            "SELECT q.press_release_highlights, q.cik "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'AXON' AND q.period_end = ?",
            (pe,),
        ).fetchone()
        stored, cik = row
        live = _live(key)
        s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
        l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
        live_bullets = [ln for ln in l_lines if ln.startswith("\u2022")]
        stale = (
            stored is not None
            and len(stored) > 2500
            and s_frag in stored
            and not any(FIGURE_BULLET_RE.search(ln) for ln in s_lines)
        )
        gates = {
            "stored-is-letter-prose": stale,
            "live-is-figure-bullets": (
                live is not None
                and len(live_bullets) >= 3
                and sum(1 for b in live_bullets if "$" in b) >= 3
                and l_frag in live
            ),
            "same-headline": (
                stored is not None
                and live is not None
                and s_lines
                and l_lines
                and s_lines[0] == l_lines[0]
            ),
            "siblings-already-live-shape": all(sib_ok),
        }
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  AXON-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  AXON-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (letter prose -> live figure bullets)")
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
