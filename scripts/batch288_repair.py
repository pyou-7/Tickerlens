"""Batch 288 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
CSX x2 + AMT x1 overrides (furniture-tailed / truncated stored
highlights replaced by the live full blocks; siblings already
live-shape).

CSX_2024-12-31 + CSX_2025-12-31: the stored rows serve the Q4/FY
highlight bullets followed by pure furniture (conference-call
dial-in, webcast, 8-K pointers, footnotes) and a "Financia l"
typo heading. Live serves the dateline paragraphs (with net income
figures) plus the same bullets: headline identical, ZERO stored
$/% figures missing from live, live gains 8/4 figures. The S12
gate flags them only for the furniture lines. CSX x3 was held as
a group since batch 285 because the 2026-06-30 row's live is
shorter than stored (drops the volume paragraph + CEO quote);
that row stays held. The 6 other cached CSX siblings already
store the live shape.

AMT_2024-09-30: the stored row is truncated mid-block (India-sale
paragraph + "CONSOLIDATED HIGHLIGHTS" heading + only the first 3
highlight bullets). Live serves the full 6-bullet block (revenue,
property revenue, net income, Adjusted EBITDA, AFFO) + dateline
+ CEO quote: headline identical, live gains 7 figures, and the
stored row's only unique figure is the "100%" in the India-sale
completion line (allowlisted below). All 11 cached AMT siblings
already store the live shape.

No extractor change in batch 288: the re-syncs are DB repairs. The
design question is the one settled in batches 266-287: the
highlights card's job is the quarter's key financial figures, and
live carries strictly more of them here. The stored rows' unique
content is conference-call furniture (CSX) and a divestiture
completion paragraph (AMT) — none of it EPS, revenue, or margin
headlines.

Open, noted not fixed: the remaining SKIP-loss rows after this
batch (largest groups DHI x4, GPC x4, APH x3, DASH x3, EQIX x3 —
all lose stored figures on re-sync; DASH x3 + EQIX x3 held as
trade-offs since batch 286; CSX_2026-06-30 held; SPG 2024-09-30
held). META_2025-09-30 re-probed this batch: the stored row is
flattened table residue carrying EPS $1.05 / net income the live
bullets drop entirely — held (needs an extractor fix, not a
re-sync). CARR_2024-12-31 probed this batch: stored carries Q4
EPS the live full-year bullets drop — held as a trade-off.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch288_repair.py
       .venv/bin/python scripts/batch288_repair.py
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

CSX_SIBLINGS = (
    "CSX_2024-09-30",
    "CSX_2025-03-31",
    "CSX_2025-06-30",
    "CSX_2025-09-30",
    "CSX_2026-03-31",
    "CSX_2026-09-30",
)
AMT_SIBLINGS = (
    "AMT_2023-12-31",
    "AMT_2024-03-31",
    "AMT_2024-06-30",
    "AMT_2024-12-31",
    "AMT_2025-03-31",
    "AMT_2025-06-30",
    "AMT_2025-09-30",
    "AMT_2025-12-31",
    "AMT_2026-03-31",
    "AMT_2026-06-30",
    "AMT_2026-09-30",
)

# Stored-only $/% figures allowed to be dropped by the AMT override:
# the "100%" in the ATC India sale-completion paragraph. Not an EPS,
# revenue, or margin headline figure. (The CSX overrides require the
# stored-only figure set to be empty.)
AMT_ALLOWLIST = {"100%"}


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

    # --- Batch 288 overrides (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1171, SKIP-loss 35).
    overrides = []

    # CSX_2024-12-31: stored furniture-tailed block -> live full block.
    csx_sib_ok = _siblings_live_shape(con, "CSX", CSX_SIBLINGS)
    pe = "2024-12-31"
    stored, cik = _fetch(con, "CSX", pe)
    live = _live("CSX_2024-12-31")
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "headline-identical": (
            s_lines and l_lines and s_lines[0] == l_lines[0]
        ),
        "stored-has-furniture-tail": (
            stored is not None
            and "CSX executives will conduct a conference call" in stored
            and "Full Year 2024 Financia l Highlights" in stored
            and "CSX executives will conduct a conference call" not in (live or "")
        ),
        "stored-only-figures-empty": (s_figs - l_figs) == set(),
        "live-is-full-block": (
            live is not None
            and "JACKSONVILLE, Fla. – January 23, 2025" in live
            and "Net income was $733 million" in live
            and "Net income for the year was $3.47 billion" in live
            and len(l_lines) == 11
        ),
        "live-gains-figures": len(l_figs - s_figs) >= 8,
        "siblings-already-live-shape": all(csx_sib_ok),
    }
    overrides.append(("CSX_2024-12-31", "CSX", pe, stored, cik, live, gates))

    # CSX_2025-12-31: stored furniture-tailed block -> live full block.
    pe = "2025-12-31"
    stored, cik = _fetch(con, "CSX", pe)
    live = _live("CSX_2025-12-31")
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "headline-identical": (
            s_lines and l_lines and s_lines[0] == l_lines[0]
        ),
        "stored-has-furniture-tail": (
            stored is not None
            and "CSX executives will conduct a conference call" in stored
            and "Full Year 2025 Financia l Highlights" in stored
            and "CSX executives will conduct a conference call" not in (live or "")
        ),
        "stored-only-figures-empty": (s_figs - l_figs) == set(),
        "live-is-full-block": (
            live is not None
            and "JACKSONVILLE, Fla. – January 22, 2026" in live
            and "net earnings of $720 million" in live
            and "Fourth Quarter Financial Highlights1" in live
            and len(l_lines) == 11
        ),
        "live-gains-figures": len(l_figs - s_figs) >= 4,
        "siblings-already-live-shape": all(csx_sib_ok),
    }
    overrides.append(("CSX_2025-12-31", "CSX", pe, stored, cik, live, gates))

    # AMT_2024-09-30: stored truncated block -> live full block.
    amt_sib_ok = _siblings_live_shape(con, "AMT", AMT_SIBLINGS)
    pe = "2024-09-30"
    stored, cik = _fetch(con, "AMT", pe)
    live = _live("AMT_2024-09-30")
    s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
    l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
    s_figs = set(FIG_RE.findall(stored or ""))
    l_figs = set(FIG_RE.findall(live or ""))
    gates = {
        "headline-identical": (
            s_lines and l_lines and s_lines[0] == l_lines[0]
        ),
        "stored-is-truncated": (
            stored is not None
            and len(s_lines) == 7
            and "CONSOLIDATED HIGHLIGHTS" in stored
            and "completed the sale of 100% of the equity interests" in stored
            and "CONSOLIDATED HIGHLIGHTS" not in (live or "")
            and "Adjusted EBITDA" not in stored
        ),
        "stored-only-figures-allowlisted": (
            (s_figs - l_figs) <= AMT_ALLOWLIST
        ),
        "live-is-full-block": (
            live is not None
            and "Adjusted EBITDA decreased 0.9% to $1,687 million" in live
            and "AFFO attributable to AMT common stockholders increased 2.6% to $1,237 million" in live
            and "Boston, Massachusetts – October 29, 2024" in live
            and len(l_lines) == 12
        ),
        "live-gains-figures": len(l_figs - s_figs) >= 7,
        "siblings-already-live-shape": all(amt_sib_ok),
    }
    overrides.append(("AMT_2024-09-30", "AMT", pe, stored, cik, live, gates))

    for key, ticker, pe, stored, cik, live, gates in overrides:
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  batch288-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  batch288-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (stored wrong-block -> live headline figures)")
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
