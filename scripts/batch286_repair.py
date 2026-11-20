"""Batch 286 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
CLX x2 + DG x1 + EXPE x1 + SPG x1 overrides (the last five remaining
zero-figure-loss re-syncs, same class: stored defective/truncated,
live fuller or cleaner, siblings already live-shape).

CLX_2024-12-31 + CLX_2025-09-30: the stored rows carry the seed-era
lead-in line ("The following are recent strategic and operational
highlights:") + the no-space bullet defect ("•Grew" / "•Introduced"),
and are truncated mid-segment-results (2024-12-31 stops before the
Household segment; 2025-09-30 stops before the final Household EBIT
bullet). Live serves the full block without the lead-in, with spaced
bullets: headline identical, no stored $/% figure is missing from
live, and live gains 1 figure each (Household net sales -11% /
Household EBIT -55%). All 6 cached CLX siblings already store the
live shape.

DG_2024-11-01: the stored headline drops the company's first word
("General Corporation Reports Third Quarter 2024 Results" for Dollar
General). Body identical, figures equal. Live serves the correct
headline. All 7 cached DG siblings already store the live shape.

EXPE_2025-03-31: the stored row carries the no-space bullet defect
("•Booked") and serves the bullets + CEO quote. Live serves the
release's three teaser subheads + dateline + the same bullets with
spaced markers: headline identical, no stored $/% figure is missing
from live (figures equal). The stored row's unique content is the CEO
quote — none of it EPS, revenue, margin, or cash-flow figures. All 7
cached EXPE siblings already store the live shape.

SPG_2025-09-30: the stored row carries standalone "•" bullet-marker
lines (the CB_2024-06-30 defect class) and is truncated (teaser lines
only, no dateline). Live serves the clean teaser lines + dateline:
headline identical, figures equal. All 6 cached SPG siblings already
store the live shape. (SPG_2024-09-30 loses $118.1M / $0.32 on
re-sync and stays held.)

No extractor change in batch 286: the re-syncs are DB repairs. The
design question is the one settled in batches 266-285: the
highlights card's job is the quarter's key financial figures, and
live carries strictly more of them here at zero figure loss. The
stored rows' unique content is a lead-in line (CLX), a dropped
headline word (DG), a CEO quote (EXPE), and stray bullet markers
(SPG) — none of it EPS, revenue, margin, or cash-flow figures.

Open, noted not fixed: the remaining SKIP-loss rows after this batch
(largest groups DHI x4, GPC x4, APH x3, BLK x3, CSX x3, DASH x3,
EQIX x3 — all lose stored figures on re-sync; DASH x3 + EQIX x3
figure-probed in batch 286: DASH stored shareholder-letter narrative
carries unique ex-Deliveroo growth figures live drops; EQIX stored
operational bullets carry bookings figures ($378M/$424M) live drops;
both held as trade-offs; SPG 2024-09-30 held; CSX x3 held as a
group since batch 285). With this batch, the zero-figure-loss
candidate list from batch 283 is exhausted.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch286_repair.py
       .venv/bin/python scripts/batch286_repair.py
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

CLX_SIBLINGS = (
    "CLX_2024-06-30",
    "CLX_2024-09-30",
    "CLX_2025-03-31",
    "CLX_2025-06-30",
    "CLX_2025-12-31",
    "CLX_2026-03-31",
)
DG_SIBLINGS = (
    "DG_2025-01-31",
    "DG_2025-05-02",
    "DG_2025-08-01",
    "DG_2025-10-31",
    "DG_2026-01-30",
    "DG_2026-05-01",
    "DG_2026-07-31",
)
EXPE_SIBLINGS = (
    "EXPE_2024-09-30",
    "EXPE_2024-12-31",
    "EXPE_2025-06-30",
    "EXPE_2025-09-30",
    "EXPE_2025-12-31",
    "EXPE_2026-03-31",
    "EXPE_2026-06-30",
)
SPG_SIBLINGS = (
    "SPG_2024-12-31",
    "SPG_2025-03-31",
    "SPG_2025-06-30",
    "SPG_2025-12-31",
    "SPG_2026-03-31",
    "SPG_2026-06-30",
)

LEAD_IN = "The following are recent strategic and operational highlights:"


def _live(key):
    return F.extract_press_release_highlights(
        open(f"{CACHE}/{key}.html", encoding="utf-8").read()
    )


def _siblings_live_shape(con, ticker, siblings):
    ok_all = []
    for sib in siblings:
        sib_pe = sib.split("_", 1)[1]
        sib_stored = con.execute(
            "SELECT q.press_release_highlights "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = ? AND q.period_end = ?",
            (ticker, sib_pe),
        ).fetchone()[0]
        sib_live = _live(sib)
        ok = (
            sib_stored is not None
            and sib_live is not None
            and norm(sib_stored) == norm(sib_live)
        )
        ok_all.append(ok)
        print(f"  sibling {sib} already-live-shape: {ok}")
    return ok_all


def _fetch(con, ticker, pe):
    return con.execute(
        "SELECT q.press_release_highlights, q.cik "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE c.ticker = ? AND q.period_end = ?",
        (ticker, pe),
    ).fetchone()


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

    # --- Batch 286 overrides (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1162, SKIP-loss 44).
    overrides = []

    # CLX_2024-12-31: stored lead-in + no-space bullets, truncated
    # before the Household segment -> live full block.
    clx_sib_ok = _siblings_live_shape(con, "CLX", CLX_SIBLINGS)
    pe = "2024-12-31"
    stored, cik = _fetch(con, "CLX", pe)
    live = _live("CLX_2024-12-31")
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "headline-identical": (
            s_lines and l_lines and s_lines[0] == l_lines[0]
        ),
        "stored-has-lead-in-and-spacing-defect": (
            stored is not None
            and LEAD_IN in stored
            and "•Grew" in stored
            and LEAD_IN not in (live or "")
            and "•Grew" not in (live or "")
        ),
        "stored-is-truncated": (
            stored is not None
            and "Household (Bags and Wraps; Cat Litter; Grilling)" not in stored
        ),
        "stored-only-figures-allowlisted": (s_figs - l_figs == set()),
        "live-is-full-block": (
            live is not None
            and "• Grew share in seven of its eight categories" in live
            and "Household (Bags and Wraps; Cat Litter; Grilling)" in live
            and "• Net sales decreased 11%, driven by 11 points of lower volume." in live
            and len(l_lines) == 13
        ),
        "live-gains-figures": len(l_figs - s_figs) >= 1,
        "siblings-already-live-shape": all(clx_sib_ok),
    }
    overrides.append(("CLX_2024-12-31", "CLX", pe, stored, cik, live, gates))

    # CLX_2025-09-30: stored lead-in + no-space bullets, truncated
    # before the final Household EBIT bullet -> live full block.
    pe = "2025-09-30"
    stored, cik = _fetch(con, "CLX", pe)
    live = _live("CLX_2025-09-30")
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "headline-identical": (
            s_lines and l_lines and s_lines[0] == l_lines[0]
        ),
        "stored-has-lead-in-and-spacing-defect": (
            stored is not None
            and LEAD_IN in stored
            and "•Introduced" in stored
            and LEAD_IN not in (live or "")
            and "•Introduced" not in (live or "")
        ),
        "stored-is-truncated": (
            stored is not None
            and "Segment adjusted EBIT decreased 55%" not in stored
        ),
        "stored-only-figures-allowlisted": (s_figs - l_figs == set()),
        "live-is-full-block": (
            live is not None
            and "• Introduced new products inspired by emerging consumer trends" in live
            and "• Segment adjusted EBIT decreased 55%, primarily due to lower net sales." in live
            and len(l_lines) == 13
        ),
        "live-gains-figures": len(l_figs - s_figs) >= 1,
        "siblings-already-live-shape": all(clx_sib_ok),
    }
    overrides.append(("CLX_2025-09-30", "CLX", pe, stored, cik, live, gates))

    # DG_2024-11-01: stored headline drops "Dollar" -> live correct
    # headline, body identical.
    dg_sib_ok = _siblings_live_shape(con, "DG", DG_SIBLINGS)
    pe = "2024-11-01"
    stored, cik = _fetch(con, "DG", pe)
    live = _live("DG_2024-11-01")
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "stored-headline-drops-dollar": (
            s_lines
            and s_lines[0] == "General Corporation Reports Third Quarter 2024 Results"
            and l_lines
            and l_lines[0] == "Dollar General Corporation Reports Third Quarter 2024 Results"
        ),
        "body-identical": (
            s_lines[1:] == l_lines[1:] and len(l_lines) == 12
        ),
        "stored-only-figures-allowlisted": (s_figs - l_figs == set()),
        "live-carries-quarter-figures": (
            live is not None
            and "sales increased 5.0% to $10.2 billion" in live
            and "Gross\nprofit as a percentage of net sales was 28.8%" in live
        ),
        "siblings-already-live-shape": all(dg_sib_ok),
    }
    overrides.append(("DG_2024-11-01", "DG", pe, stored, cik, live, gates))

    # EXPE_2025-03-31: stored no-space bullets + CEO quote -> live
    # teaser subheads + dateline + spaced bullets.
    expe_sib_ok = _siblings_live_shape(con, "EXPE", EXPE_SIBLINGS)
    pe = "2025-03-31"
    stored, cik = _fetch(con, "EXPE", pe)
    live = _live("EXPE_2025-03-31")
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "headline-identical": (
            s_lines and l_lines and s_lines[0] == l_lines[0]
        ),
        "stored-has-spacing-defect-and-quote": (
            stored is not None
            and "•Booked" in stored
            and "Ariane Gorin" in stored
            and "•Booked" not in (live or "")
            and "Ariane Gorin" not in (live or "")
        ),
        "stored-only-figures-allowlisted": (s_figs - l_figs == set()),
        "live-is-subheads-dateline-bullets": (
            live is not None
            and "Meets top-line guidance, delivering 4% bookings growth and 3% revenue growth year-over-year" in live
            and "SEATTLE, WA – May 8, 2025" in live
            and "• Booked room nights grew 6%" in live
            and "• Paid quarterly dividend of $0.40 per share on March 27, 2025." in live
            and len(l_lines) == 13
        ),
        "siblings-already-live-shape": all(expe_sib_ok),
    }
    overrides.append(("EXPE_2025-03-31", "EXPE", pe, stored, cik, live, gates))

    # SPG_2025-09-30: stored standalone "•" lines + truncated ->
    # live clean teaser lines + dateline.
    spg_sib_ok = _siblings_live_shape(con, "SPG", SPG_SIBLINGS)
    pe = "2025-09-30"
    stored, cik = _fetch(con, "SPG", pe)
    live = _live("SPG_2025-09-30")
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "headline-identical": (
            s_lines and l_lines and s_lines[0] == l_lines[0]
        ),
        "stored-has-standalone-bullet-lines": (
            "•" in s_lines and "•" not in l_lines
        ),
        "stored-is-truncated": (
            stored is not None and "INDIANAPOLIS" not in stored
        ),
        "stored-only-figures-allowlisted": (s_figs - l_figs == set()),
        "live-is-clean-block": (
            live is not None
            and "Increases Full Year 2025 Real Estate FFO per share guidance" in live
            and "Raises quarterly dividend by 4.8% year-over-year to $2.20 per share" in live
            and "INDIANAPOLIS, November 3, 2025" in live
            and len(l_lines) == 5
        ),
        "siblings-already-live-shape": all(spg_sib_ok),
    }
    overrides.append(("SPG_2025-09-30", "SPG", pe, stored, cik, live, gates))

    for key, ticker, pe, stored, cik, live, gates in overrides:
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  batch286-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  batch286-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (stored defective/truncated -> live full block)")
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
