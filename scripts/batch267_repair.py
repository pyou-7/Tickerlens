"""Batch 267 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
BKR 2024-12-31 override.

No extractor change this batch. The BKR_2024-12-31 stored row is the
full-year bullets (7 bullets, $28.2B orders) + the lede prose (dateline
paragraph + three Lorenzo Simonelli CEO-quote paragraphs + the "Baker
Hughes Company News Release" trailer) — a stale snapshot of the
seed-era extractor, when the combined section did not qualify. The
current extractor serves the combined section outright for this
exhibit: the "Fourth-quarter highlights" anchor (6 Q4 bullets) followed
by the "Full-year highlights" sub-heading (batch-195 sub-heading rule)
and the same 7 full-year bullets, 14 section lines / 13 figure lines,
with no leading bullet block and no CEO prose. The gates refuse the
re-sync (SKIP-loss: stored is a different section than live), so the
override below re-syncs exactly this one row under per-row gates:
stored is the full-year-bullets + lede-quote shape, live is the
combined Q4 + full-year section with the same headline, and the Q4
sibling BKR_2025-12-31 already stores the combined shape (stored ==
live), so the re-sync makes the two Q4 quarters consistent. The
trade-off is stated plainly: the quarter page loses the CEO-quote
prose (its figures — $3.8B IET orders, $13B full-year orders, the 20%
margin targets — duplicate the bullets or are narrative) and gains the
6 Q4 bullets the stored row lacks entirely; the 7 full-year bullets
are preserved verbatim (modulo the "• " spacing the normalizer
already treats as equal). A re-seed reproduces the live shape.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch267_repair.py
       .venv/bin/python scripts/batch267_repair.py
"""
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
from batch261_repair import sweep_gate_s13
from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"

BKR_KEY = "BKR_2024-12-31"
BKR_SIBLING = "BKR_2025-12-31"


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

    # --- Batch 267 BKR override (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1084, SKIP-loss 121).
    # BKR_2024-12-31 is the only override target; every gate below must
    # pass or the row is left untouched and reported. The Q4 sibling
    # BKR_2025-12-31 already stores the combined shape (stored == live
    # under norm), which is the consistency cross-check.
    pe = BKR_KEY.split("_", 1)[1]
    row = con.execute(
        "SELECT q.press_release_highlights, q.cik "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = 'BKR' AND q.period_end = ?",
        (pe,),
    ).fetchone()
    stored_b, cik_b = row
    live_b = F.extract_press_release_highlights(
        open(f"{CACHE}/{BKR_KEY}.html", encoding="utf-8").read()
    )
    sib_pe = BKR_SIBLING.split("_", 1)[1]
    sib_stored = con.execute(
        "SELECT q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = 'BKR' AND q.period_end = ?",
        (sib_pe,),
    ).fetchone()[0]
    sib_live = F.extract_press_release_highlights(
        open(f"{CACHE}/{BKR_SIBLING}.html", encoding="utf-8").read()
    )
    gates = {
        "stored-is-fullyear-plus-lede-quote": (
            stored_b is not None
            and stored_b.startswith(
                "Baker Hughes Announces Fourth-Quarter and Full-Year 2024 Results")
            and "Orders of $28.2 billion" in stored_b
            and "HOUSTON & LONDON (January 30, 2025)" in stored_b
            and "Lorenzo Simonelli" in stored_b
            and stored_b.rstrip().endswith("Baker Hughes Company News Release")
        ),
        "live-is-combined-section": (
            live_b is not None
            and live_b.startswith(
                "Baker Hughes Announces Fourth-Quarter and Full-Year 2024 Results")
            and "• Orders of $7.5 billion" in live_b
            and "Full-year highlights" in live_b
            and "• Orders of $28.2 billion" in live_b
            and "Lorenzo Simonelli" not in live_b
            and "News Release" not in live_b
        ),
        "same-headline": (
            stored_b is not None
            and live_b is not None
            and stored_b.split("\n")[0] == live_b.split("\n")[0]
        ),
        "sibling-already-combined-shape": (
            sib_stored is not None
            and sib_live is not None
            and norm(sib_stored) == norm(sib_live)
            and "Full-year highlights" in sib_live
            and "• Orders of $7.9 billion" in sib_live
        ),
    }
    failed = [g for g, ok in gates.items() if not ok]
    if failed:
        print(f"  BKR-override SKIP {BKR_KEY}: failed gates {failed}")
    else:
        print(f"  BKR-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {BKR_KEY} "
              f"{len(stored_b)}->{len(live_b)} (full-year+lede-quote -> combined section)")
        if not DRY:
            con.execute(
                "UPDATE quarterly_financials "
                "SET press_release_highlights = ? "
                "WHERE cik = ? AND period_end = ?",
                (live_b, cik_b, pe),
            )
            repaired.append(f"{BKR_KEY} (override)")
            # Post-write verify: stored must now equal live byte-for-byte.
            check = con.execute(
                "SELECT press_release_highlights FROM quarterly_financials "
                "WHERE cik = ? AND period_end = ?",
                (cik_b, pe),
            ).fetchone()[0]
            assert check == live_b, f"post-write mismatch for {BKR_KEY}"
            print(f"    {BKR_KEY} DB-verified byte-identical to live")
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
