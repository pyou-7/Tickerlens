"""Batch 277 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
EBAY x5 override.

EBAY's stored rows for 5 quarters are stale snapshots of the seed-era
extractor: headline + the "Business Highlights" narrative section only
-- the long eBay Live / anniversary / Depop / collectibles bullets --
with no financial-figure bullet and no CEO/CFO quote at all. The
current extractor serves the release's "Financial Highlights" section
for these rows: headline + 7 figure bullets (Revenue, GMV, GAAP and
non-GAAP net income / EPS, operating margins, operating + free cash
flow, capital returns) -- 14 bullets for 2025-12-31, which adds the
"Full Year 2025 Financial Highlights" block.

Why the seed-era extractor captured only the business section: in
these 5 releases the layout is headline -> a short teaser bullet
block -> dateline paragraph -> CEO/CFO quotes -> "Business Highlights"
-> "Impact" -> "Financial Highlights". The seed-era capture took the
business section; the current extractor anchors on the Financial
Highlights section. (The 2025-06-30 raw lines show the shape: the
teaser block at lines 7-17, quotes at 21-22, Business Highlights at
23-45, Financial Highlights at 55-69.)

The four EBAY siblings (2024-09-30, 2024-12-31, 2025-03-31,
2026-09-30) already store the live shape (stored == live under norm)
-- the consistency cross-check. The older three store headline +
quotes + financial bullets + the Business Highlights section; the
2026-09-30 sibling stores headline + 7 figure bullets only, i.e. the
same shape the 5 re-synced rows take.

The design question is the one settled in batches 266-270 (BNY, BKR,
AMZN, COR, V), 273 (AXON) and 276 (CEG): the highlights card's job
is the quarter's key financial figures. Live carries every one of
them; the stored rows lack them entirely. The stored rows' unique
figures fall into three droppable classes, pinned per row below as
an exact allowlist: (a) advertising revenue ($482M total / $455M
first-party, 2.5% of GMV, +19%/+17% -- 2025-06-30); (b) cumulative /
charity amounts ($1B+ Seller Capital distributed since 2021, $49M
eBay for Charity in Q3 -- 2025-09-30); (c) single collectible sale
prices ($16.5M Pikachu Illustrator card -- 2026-03-31; $4.3M Jordan
card, $2.8M Gretzky jersey -- 2026-06-30). 2025-12-31's stored row
has no $/% figure at all. No stored-only figure is an EPS, revenue,
GMV, margin, cash-flow, or capital-return figure.

The AZO x5 and MU x5 groups were probed in batch 276 and are NOT
re-synced here -- each needs its own batch. AZO x5: stored is SHORTER
than live (664-1512 chars vs 2434-3052), i.e. the stored rows look
like truncated ledes and live the fuller lede, so the S12 refusal is
a line-matching question, not a content loss -- needs its own probe
of the dateline paragraph. MU x5: small length deltas (~70 chars)
with first-loss line "Quarterly Financial Results" -- needs its own
probe.

Open, noted not fixed: the 5 re-synced releases' CEO/CFO quotes are
in the exhibit (after the dateline paragraph) but neither stored nor
live serves them -- the extractor's section anchor does not pick up
quotes that sit between the dateline and the Business Highlights
heading (the older EBAY quarters do serve quotes). Also the
2025-12-31 live reproduces the release's own typo, "or 4.26 per
diluted share" (missing $) -- source text, not an extractor defect.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch277_repair.py
       .venv/bin/python scripts/batch277_repair.py
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

FIG_RE = re.compile(r"\$[\d,]+(?:\.\d+)?(?:\s*(?:billion|million|trillion))?|\d+(?:\.\d+)?%")

# key -> (stored distinctive fragment, live distinctive fragment,
#          exact stored-only $/% figure set).
EBAY_KEYS = {
    "EBAY_2025-06-30": (
        "eBay formally launched eBay Live in the U.K.",
        "Revenue was $2.7 billion, up 6%",
        {"$482 million", "$455 million", "2.5%", "19%", "17%"},
    ),
    "EBAY_2025-09-30": (
        "eBay celebrated its 30th anniversary",
        "Revenue was $2.8 billion, up 9%",
        {"$1 billion", "$49 million"},
    ),
    "EBAY_2025-12-31": (
        "The company expanded eBay Live, its interactive live-stream shopping experience, to Germany and Australia",
        "Revenue was $3.0 billion, up 15%",
        set(),
    ),
    "EBAY_2026-03-31": (
        "eBay announced a definitive agreement to acquire Depop",
        "Revenue was $3.1 billion, up 19%",
        {"$16.5 million"},
    ),
    "EBAY_2026-06-30": (
        "On July 30, 2026, eBay closed its acquisition of Depop Limited",
        "Revenue was $3.1 billion, up 15%",
        {"$4.3 million", "$2.8 million"},
    ),
}
EBAY_SIBLINGS = (
    "EBAY_2024-09-30",
    "EBAY_2024-12-31",
    "EBAY_2025-03-31",
    "EBAY_2026-09-30",
)


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

    # --- Batch 277 EBAY override (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1131, SKIP-loss 75).
    sib_ok = []
    for sib in EBAY_SIBLINGS:
        sib_pe = sib.split("_", 1)[1]
        sib_stored = con.execute(
            "SELECT q.press_release_highlights "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'EBAY' AND q.period_end = ?",
            (sib_pe,),
        ).fetchone()[0]
        sib_live = _live(sib)
        ok = (
            sib_stored is not None
            and sib_live is not None
            and norm(sib_stored) == norm(sib_live)
        )
        sib_ok.append(ok)
        print(f"  sibling {sib} already-live-shape: {ok}")
    for key, (s_frag, l_frag, figs_allowed) in EBAY_KEYS.items():
        pe = key.split("_", 1)[1]
        row = con.execute(
            "SELECT q.press_release_highlights, q.cik "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'EBAY' AND q.period_end = ?",
            (pe,),
        ).fetchone()
        stored, cik = row
        live = _live(key)
        s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
        l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
        live_bullets = [ln for ln in l_lines if ln.startswith("\u2022")]
        s_figs = set(FIG_RE.findall(stored or ""))
        l_figs = set(FIG_RE.findall(live or ""))
        gates = {
            "stored-is-business-section": (
                stored is not None and s_frag in stored
            ),
            "stored-is-narrative-only": (
                stored is not None
                and "Revenue was" not in stored
                and "per diluted share" not in stored
            ),
            "live-is-financial-figure-bullets": (
                live is not None
                and len(live_bullets) >= 7
                and sum(1 for b in live_bullets if "$" in b) >= 2
                and l_frag in live
                and "per diluted share" in live
            ),
            "same-headline": (
                stored is not None
                and live is not None
                and s_lines
                and l_lines
                and s_lines[0] == l_lines[0]
            ),
            "stored-only-figures-allowlisted": (
                s_figs - l_figs == figs_allowed
            ),
            "live-gains-figures": len(l_figs - s_figs) >= 2,
            "siblings-already-live-shape": all(sib_ok),
        }
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  EBAY-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  EBAY-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (business section -> live financial block)")
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
