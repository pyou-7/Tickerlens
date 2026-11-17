"""Batch 268 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
AMZN x8 override.

Amazon's releases carry TWO bullet blocks: the financial-figures block
("Net sales increased ...", segment sales, operating income, net income)
up top, and the business-narrative block ("Some other highlights since
the company's last earnings announcement include that Amazon:" —
Prime delivery speeds, movie viewers, AWS launches) further down. The
stored rows for 8 quarters are the business block — a stale snapshot of
the seed-era extractor, when the financial block did not qualify (the
bullets' "•" glyph sits on its own line, split from the bold lead-in:
"•" / "Net sales" / "increased 10% ..."). The current extractor serves
the financial block outright for 7 of the 8 (leading bullet block, no
anchored rival, section 9-14 lines), and the lede fallback serves it for
the 8th (2026-06-30: Amazon's 2026 releases lead with three teaser
lines ahead of the dateline, so there is no leading block and no
section anchor — the lede carries the teaser + dateline + the first 8
financial bullets). A re-seed reproduces the live shape for all 8.

The stored rows are also visibly partial captures, not an editorial
choice: each holds 11-12 business bullets and ends mid-list (2025-06-30
ends on the dangling intro "• Innovated across Amazon Nova, including:";
2026-06-30 ends "• Launched serverless infrastructure…"), while the
release's business list runs on. The design question is the one settled
in batches 266/267 (BNY, BKR): the highlights card's job is the
quarter's key financial figures, and the business bullets are narrative
— the live block carries every figure the stored row lacks entirely
(net sales, segment sales, operating income, net income, EPS), while
the stored row's unique content (Prime speeds, Red One viewers, AWS
launch names) is narrative, not quarterly figures.

Known live-shape warts, pinned in tests rather than fixed here:
- Q1-Q3 quarters carry a trailing Jassy CEO-quote paragraph (the quote
  directly follows the last financial bullet with no intervening
  heading, so the section collector's completion allowance pulls it
  in); Q4 quarters end on the net-income bullet (the "Full Year"
  heading terminates the section).
- 2026-06-30's lede stops at 8 bullets (AWS operating income): the
  net-income, non-operating-income and cash-flow bullets are NOT in
  live. The re-sync still stores a strictly better row (headline
  figures the stored row lacks entirely), and the truncation is pinned
  so a future extractor fix fails loudly instead of silently re-staling.
- The 2026-09-30 sibling already stores the live shape (stored ==
  live under norm) — the same lede shape as 2026-06-30 — which is the
  consistency cross-check for the override.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch268_repair.py
       .venv/bin/python scripts/batch268_repair.py
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

# key -> distinctive fragment of the stored row's first business bullet.
AMZN_KEYS = {
    "AMZN_2024-09-30": "Held its annual Prime Big Deal Days shopping event",
    "AMZN_2024-12-31": "Delivered at its fastest speeds ever for Prime members in 2024",
    "AMZN_2025-03-31": "Introduced Alexa+, our next-generation Alexa personal assistant",
    "AMZN_2025-06-30": "Held its biggest Prime Day event ever",
    "AMZN_2025-09-30": "Saw continued strong adoption of Trainium2",
    "AMZN_2025-12-31": "Announced new AWS agreements with OpenAI, Visa, the NBA",
    "AMZN_2026-03-31": "Continued growing custom silicon business",
    "AMZN_2026-06-30": "Exceeded a $25 billion annual revenue run rate for AWS",
}
AMZN_SIBLING = "AMZN_2026-09-30"


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

    # --- Batch 268 AMZN override (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1086, SKIP-loss 122).
    # Each AMZN key must pass every gate or it is left untouched.
    sib_pe = AMZN_SIBLING.split("_", 1)[1]
    sib_stored = con.execute(
        "SELECT q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = 'AMZN' AND q.period_end = ?",
        (sib_pe,),
    ).fetchone()[0]
    sib_live = _live(AMZN_SIBLING)
    sib_ok = (
        sib_stored is not None
        and sib_live is not None
        and norm(sib_stored) == norm(sib_live)
        and "• Net sales increased 12% to $201.9 billion" in sib_live
    )
    print(f"  sibling {AMZN_SIBLING} already-financial-shape: {sib_ok}")
    for key, frag in AMZN_KEYS.items():
        pe = key.split("_", 1)[1]
        row = con.execute(
            "SELECT q.press_release_highlights, q.cik "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'AMZN' AND q.period_end = ?",
            (pe,),
        ).fetchone()
        stored, cik = row
        live = _live(key)
        s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
        l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
        gates = {
            "stored-is-business-bullets": (
                stored is not None
                and len(s_lines) > 1
                and s_lines[1].startswith("• ")
                and frag in s_lines[1]
                and "• Net sales increased" not in stored
            ),
            "live-is-financial-block": (
                live is not None
                and len(l_lines) > 1
                # First bullet of live is the Net-sales figure bullet.
                # (2026-06-30 is the lede shape: three teaser lines and
                # the dateline precede the bullets, so the bullet is not
                # line 1 — find the first "•" line instead.)
                and next(
                    (ln for ln in l_lines if ln.startswith("• ")), ""
                ).startswith("• Net sales increased")
            ),
            "same-headline": (
                stored is not None
                and live is not None
                and s_lines[0] == l_lines[0]
            ),
            "sibling-already-financial-shape": sib_ok,
        }
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  AMZN-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  AMZN-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (business bullets -> financial block)")
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
