"""Batch 250 repair: the highlights sweep, gate S8 — the
trailing-guidance gate (BIIB x3).

Each of the three BIIB loss rows differs from live in exactly one
way: the stored row ends on the opening of the release's guidance
section — the heading (\"Full Year YYYY Financial Guidance\"), the
guidance intro sentence, and the first rows of the guidance table
(\"Prior FY YYYY Guidance Updated FY YYYY Guidance\", \"Non-GAAP
diluted EPS $15.75 to $16.25\"). The live extraction ends at the
last highlights bullet by design (the batch-222 trim stops at the
guidance section), and the seed-era stored text over-included the
next section: the stored prefix equals live exactly, and the tail
is the guidance section's opening, nothing else.

Gate S8 blesses the swap stored -> live when:
  1. the stored prefix equals live exactly under norm (no other
     stored line is lost, no live line is added);
  2. the tail is short (1-5 lines) and opens on a full-line
     guidance heading (\"Full Year YYYY Financial Guidance\" or the
     \"Fiscal YYYY\" analog);
  3. no tail line is a bullet (a bullet would be highlights
     content, not a guidance table);
  4. live is clean by the S5 live-side checks (no table, no
     residue-heavy text, no dangling tail, no fragment);
  5. the tail verifies against the source document
     (verify_trailing_guidance): the tail lines appear consecutively
     in the doc right after live's last line (bare page-number lines
     skipped — Biogen paginates the exhibit, and a \"3\" sits between
     the last bullet and the heading on two of the three rows), and
     the doc line after the tail is a guidance-table continuation
     (a residue figure line, a \"mid-point\" footnote, or a
     \"Guidance ... $...\" line). That is what makes the gate
     doc-aware rather than shape-only: a guidance heading over prose
     live drops could never pass, because the line after it would be
     prose, not table continuation.

The dropped lines are guidance-section content, not highlights
content — the same S5 argument (stored was never highlights there),
applied to a trailing run instead of a whole row. The guidance
figures themselves are not invented or altered anywhere: the swap
only removes them from the highlights text, where the extractor
never serves them; the release's guidance table stays in the
cached exhibit.

Still blocked by design (NOT repaired here): the remaining
SKIP-loss rows (content live genuinely drops — Amazon's business
bullets, CINF's lede-bullet vs section-bullet selection, AXON
letter prose, Ford's flattened tables and truncated seed lines,
BKR's quote-after-section shape, BIIB 2026-06-30's product-bullet
vs financial-bullet selection); DRI 2026-08-30 live-table;
ABNB 2024-12-31; COF 2025-06-30; DIS x4 added-table; ADBE
2025-11-28 + 2026-05-29; INTC x6; V 2025-09-30; DG 2024-11-01;
JPM's \"n \"-prefixed bullets; BRK.B Q3 FY2026 mid-body table
residue; KHC date-pair header; DLR TOC-only live extraction;
ABNB 2023-12-31; CCI 2026-09-30 guidance furniture, LUV tail,
SPG/MU/BMY tables, DIS footnote shape, batch-184 list, C
slide-deck exhibit, batch-157 gate skips, DASH truncated para;
GILD's guidance tail ends on a \"Key Updates\" heading; AppLovin's
\"Summary:2\" heading wart; wordy value lines as a future fuser
class; still-truncated stored highlights rows; the FAST/EL lede
warts; the AMT 2023-12-31 / 2024-03-31 / 2024-06-30
NULL-stored-highlights seeding gap.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch250_repair.py
       .venv/bin/python scripts/batch250_repair.py
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import is_residue, non_empty, norm
from batch242_repair import sweep_gate_s4
from batch244_repair import _BULLET_LEADS, _live_is_clean, classify_s5
from batch247_repair import sweep_gate_s6
from batch248_repair import sweep_gate_s7
from tickerlens.data.filings import (
    _html_to_text,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"

# A full-line guidance-section heading: "Full Year 2024 Financial
# Guidance" (Biogen, all three rows) or the "Fiscal YYYY" analog.
# The year + "Guidance" + nothing else is what makes it a section
# heading rather than a highlights bullet that mentions guidance.
_GUIDANCE_HEAD_RE = re.compile(
    r"^(?:Full Year|Fiscal) \d{4} (?:Financial )?Guidance$"
)
# Bare page numbers Biogen's exhibit pagination leaves between the
# last highlights bullet and the guidance heading ("3" on two of
# the three rows).
_PAGE_NUMBER_RE = re.compile(r"^\d{1,3}$")


def _is_guidance_head(ln: str) -> bool:
    return bool(_GUIDANCE_HEAD_RE.match(ln.strip()))


def _is_guidance_continuation(ln: str) -> bool:
    """True for a doc line that continues a guidance table: a residue
    figure line (\"($0.95)\", \"Updated Guidance $14.50 to $15.50\"),
    a mid-point footnote (\"Reflecting growth of ~9% at the
    mid-point*\"), or a \"Guidance ... $...\" line. Prose is never a
    continuation, so a guidance heading over dropped prose fails."""
    s = ln.strip()
    return (
        is_residue(s)
        or "mid-point" in s.lower()
        or ("guidance" in s.lower() and "$" in s)
    )


def verify_trailing_guidance(html: str, live: str, tail: list[str]) -> bool:
    """Source-verified trailing guidance: the tail's lines appear
    consecutively in the doc's own text, right after live's last
    line (bare page-number lines skipped), with a guidance-table
    continuation line immediately after them. The doc — not a shape
    heuristic — proves the tail opens the guidance section: the
    BIIB tails sit at doc lines 82-85 / 88-92 / 94-98, right after
    the diluted-shares bullet and right before the table's next
    rows. Returns False when any of those facts is missing."""
    l_lines = non_empty(live)
    if not l_lines or not tail:
        return False
    doc_lines = [
        norm(ln.strip())
        for ln in _html_to_text(html).split("\n")
        if ln.strip()
    ]
    tail_norm = [norm(x) for x in tail]
    live_last = norm(l_lines[-1])
    try:
        i_live = doc_lines.index(live_last)
    except ValueError:
        return False
    j = i_live + 1
    while j < len(doc_lines) and _PAGE_NUMBER_RE.match(doc_lines[j]):
        j += 1
    if doc_lines[j : j + len(tail)] != tail_norm:
        return False
    k = j + len(tail)
    while k < len(doc_lines) and _PAGE_NUMBER_RE.match(doc_lines[k]):
        k += 1
    if k >= len(doc_lines):
        return False
    return _is_guidance_continuation(doc_lines[k])


def sweep_gate_s8(stored: str, live: str, html: str) -> str | None:
    """Gate S8: the trailing-guidance swap. Returns None when the
    swap is allowed, else the SKIP reason (\"loss\" — the row stays in
    the loss cohort exactly as before)."""
    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    if not s_lines or not l_lines:
        return "loss"
    if len(s_lines) <= len(l_lines):
        return "loss"
    tail = s_lines[len(l_lines) :]
    if len(tail) > 5:
        return "loss"
    # The stored prefix must equal live exactly: no other stored
    # line is lost and no live line is added.
    if [norm(x) for x in s_lines[: len(l_lines)]] != [norm(x) for x in l_lines]:
        return "loss"
    if not _is_guidance_head(tail[0]):
        return "loss"
    if any(x.startswith(_BULLET_LEADS) for x in tail):
        return "loss"
    if not _live_is_clean(l_lines, set(s_lines)):
        return "live-table"
    if not verify_trailing_guidance(html, live, tail):
        return "loss"
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
    for t, pe, stored, cik in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            counts["SKIP-nocache"] = counts.get("SKIP-nocache", 0) + 1
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            counts["SKIP-live-none"] = counts.get("SKIP-live-none", 0) + 1
            continue
        if norm(stored) == norm(live):
            counts["B"] = counts.get("B", 0) + 1
            continue
        if sweep_gate_s4(stored, live) is None:
            counts["S4"] = counts.get("S4", 0) + 1
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
            repaired.append(key)
            if not DRY:
                con.execute(
                    "UPDATE quarterly_financials "
                    "SET press_release_highlights = ? "
                    "WHERE cik = ? AND period_end = ?",
                    (live, cik, pe),
                )
            print(f"    S8 {key} {len(stored)}->{len(live)}")
            continue
        rk = f"SKIP-{r8}"
        counts[rk] = counts.get(rk, 0) + 1
        skip_lists.setdefault(rk, []).append(key)
    if not DRY:
        con.commit()
    print(f"\nDRY_RUN={DRY} counts: {counts}")
    print(f"repaired (S8): {len(repaired)}: {', '.join(repaired)}")
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
