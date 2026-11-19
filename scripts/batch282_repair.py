"""Batch 282 repair: re-run the full gate chain (S4/S5/S6/S7/S8/S9/S10/
S11/S12/S13) and re-sync the rows the gates bless, plus the deliberate
CRWD x3 override.

CrowdStrike's releases open with a headline, CEO + CFO quotes, seven
financial bullets (Revenue, ARR, Subscription Gross Margin,
Income/Loss from Operations, Net Income/Loss, Cash Flow, Cash and
Cash Equivalents), then a "Recent Highlights" bullet list. The 3
stored rows are truncated snapshots: each stops at 13 lines -- the
CEO/CFO quotes are missing on all 3, and the Recent Highlights list
stops 4 bullets short -- and each carries whitespace defects the
current extractor fixed ("million ," / "billion ," space-before-comma,
"gr oss" / "Equivalen ts" intra-word splits, "2024 1 ." spaced
footnote keys). Live is a strict superset modulo whitespace: every
stored line appears in live after removing all whitespace, in order;
the headline is identical; and no stored $/% figure is missing from
live. Live also gains figures the stored rows lack (the $4 billion
ARR milestone and 97% gross retention on 2024-10-31, the $10 billion
ARR target on 2025-04-30, $221/$333/$284 million on 2025-07-31).

The 5 CRWD siblings (2025-01-31, 2025-10-31, 2026-01-31, 2026-04-30,
2026-07-31) already store the live shape (stored == live under
norm) -- the consistency cross-check.

No extractor change in batch 282: the re-sync is a DB repair. The
design question is the one settled in batches 266-281: the
highlights card's job is the quarter's key financial figures, and
live carries strictly more of them here at zero figure loss. The
quotes and award bullets live adds are already served on the 5
sibling quarters, so the re-sync is a consistency repair, not a
design change.

Open, noted not fixed: the remaining SKIP-loss rows after this
batch (largest groups DHI x4, GPC x4 -- both lose stored figures on
re-sync, so neither is a strict-superset repair; each needs its own
probe).

Usage: DRY_RUN=1 .venv/bin/python scripts/batch282_repair.py
       .venv/bin/python scripts/batch282_repair.py
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

# key -> (live distinctive last bullet fragment,
#          exact stored-only $/% figure set).
CRWD_KEYS = {
    "CRWD_2024-10-31": (
        "• Unveiled a series of new and enhanced offerings during the eighth annual Fal.Con",
        set(),
    ),
    "CRWD_2025-04-30": (
        "• Revealed new Falcon Data Protection innovations",
        set(),
    ),
    "CRWD_2025-07-31": (
        "• Released CrowdStrike Falcon Next-Gen Identity Security",
        set(),
    ),
}
CRWD_SIBLINGS = (
    "CRWD_2025-01-31",
    "CRWD_2025-10-31",
    "CRWD_2026-01-31",
    "CRWD_2026-04-30",
    "CRWD_2026-07-31",
)


def _live(key):
    return F.extract_press_release_highlights(
        open(f"{CACHE}/{key}.html", encoding="utf-8").read()
    )


def _squash(s):
    return re.sub(r"\s+", "", s)


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

    # --- Batch 282 CRWD override (deliberate, gated; see docstring) ---
    # The sweep above repairs 0 (baseline: B 1153, SKIP-loss 53).
    sib_ok = []
    for sib in CRWD_SIBLINGS:
        sib_pe = sib.split("_", 1)[1]
        sib_stored = con.execute(
            "SELECT q.press_release_highlights "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'CRWD' AND q.period_end = ?",
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
    for key, (l_frag, figs_allowed) in CRWD_KEYS.items():
        pe = key.split("_", 1)[1]
        row = con.execute(
            "SELECT q.press_release_highlights, q.cik "
            "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'CRWD' AND q.period_end = ?",
            (pe,),
        ).fetchone()
        stored, cik = row
        live = _live(key)
        s_lines = [ln for ln in stored.split("\n") if ln.strip()] if stored else []
        l_lines = [ln for ln in live.split("\n") if ln.strip()] if live else []
        s_figs = set(FIG_RE.findall(stored or ""))
        l_figs = set(FIG_RE.findall(live or ""))
        # Stored is a whitespace-defective subsequence of live: every
        # stored line, with all whitespace removed, matches a live line
        # in order. This is what makes the re-sync zero-loss -- the
        # stored-only exact-match lines are spacing variants, not
        # dropped content.
        l_squashed = [_squash(ln) for ln in l_lines]
        idx = 0
        subsequence = True
        for ln in s_lines:
            sx = _squash(ln)
            while idx < len(l_squashed) and l_squashed[idx] != sx:
                idx += 1
            if idx >= len(l_squashed):
                subsequence = False
                break
            idx += 1
        gates = {
            "headline-identical": (
                s_lines and l_lines and s_lines[0] == l_lines[0]
            ),
            "stored-is-whitespace-subsequence-of-live": subsequence,
            "stored-truncated-at-13-lines": (
                len(s_lines) == 13 and len(l_lines) == 19
            ),
            "stored-only-figures-allowlisted": (
                s_figs - l_figs == figs_allowed
            ),
            "live-is-full-shape": (
                live is not None
                and l_frag in live
                and "said George Kurtz" in live
                and "Burt Podbere" in live
                and "Recent Highlights" in live
            ),
            "live-gains-figures": len(l_figs - s_figs) >= 2,
            "siblings-already-live-shape": all(sib_ok),
        }
        failed = [g for g, ok in gates.items() if not ok]
        if failed:
            print(f"  CRWD-override SKIP {key}: failed gates {failed}")
            continue
        print(f"  CRWD-override {'WOULD-RESYNC' if DRY else 'RESYNC'} {key} "
              f"{len(stored)}->{len(live)} (truncated 13-line snapshot -> live full shape)")
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
