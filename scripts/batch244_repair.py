"""Batch 244 repair: the highlights sweep, gate S5 — the 15 SKIP-first-diff
rows left after batch 243 (AGNC x2, APO x8, COIN x1, CSCO x3, NFLX x1).

Decomposition (batch 243 probe dump, /tmp/batch244_dump.txt):

  APO x8 -- stored is a flattened earnings-deck TABLE (3 lines, ~4000
      chars: "3Q'24 Per Share YTD'24 Per Share GAAP Financial Measures
      ($ in millions, except per share amounts) Net Income ... $787
      $1.30 ..." + a second table line). The live extraction is the
      release's clean lede (headline + dateline + CEO quote +
      dividends). The stored row was never highlights — it is the
      deck's financial tables flattened into prose.
  CSCO x3 -- stored is the release's DETAIL narrative ("Revenue --
      Total revenue was $15.3 billion ...", "Gross Margin -- ...",
      "Operating Expenses -- ...", 11 of 12 lines label-dash prose).
      Live is the real bullet Highlights section.
  COIN x1 (2026-03-31) -- stored is a single 3994-char line of
      forward-looking-statements DISCLAIMER boilerplate ("Disclaimers
      Cautionary Note Regarding Forward-Looking Statements ... Private
      Securities Litigation Reform Act of 1995 ..."). Live is the
      shareholder deck's real Q1 content (mission, market stats).
      Still slide-deck soup, but strictly better than a disclaimer.
  NFLX x1 (2025-06-30) -- stored is the letter's CONTENT-SLATE
      section (hit-series view counts) plus footnote furniture (a
      "___" separator, numbered footnote defs, bare URLs). Live is
      the letter's BUSINESS highlights (revenue +16%, margin 34%,
      forecast raise, key objectives). The content slate is a
      different section, not the highlights; re-syncing drops it by
      design, and the furniture with it.
  AGNC x2 -- NOT a gate row: the stored Q4 figures are right and the
      live extraction was wrong (it picked the FULL YEAR section over
      the quarter's — batch 244 extractor fix: quarter-scoped sections
      beat full-year ones when they financially qualify). After the
      fix the live extraction is the Q4 section and S4 repairs them.
  CART x2 + ANET x1 -- the MIRROR image, found by the before/after
      cache blast: these rows were in-sync BEFORE the fix because
      both stored and live were the FULL YEAR section. The fix moves
      live to the quarter section, so the stored row (annual figures
      on a quarterly row: CART GTV $33,461M stored vs $8,645M live)
      must be re-synced too. Class s5-fy-stored, source-verified
      against the doc itself (see verify_fy_stored): the stored text
      IS the doc's full-year section and live IS its quarter section.
      ANET is the same shape (headline + FY Financial section stored,
      headline + Q4 Financial section live) — S4 alone calls it loss,
      because the FY section carries lines the Q4 section lacks.

Gate S5 is a WRONG-SECTION gate, not a chrome gate: it fires only
when the stored row positively matches one of the four wrong-section
shapes above AND the live text is a clean highlights/lede capture
(no table fraction, no added table lines, no dangling tail, no
fragment second line — the same live-side checks as S3/S4). It runs
AFTER S4: a row S4 already repairs never reaches S5, and a row S5
does not recognize keeps its S4 SKIP reason. The loss check is
deliberately NOT applied here — the dropped stored lines are, by
construction of the shape match, not highlights content (table rows,
detail prose, disclaimer boilerplate, a non-highlights section +
furniture). A stored row that is a real highlights block with a
footnote or two appended does NOT match any shape (no table-units
phrase, no label-dash majority, no disclaimer head, no separator /
numbered-URL furniture pair), so it stays blocked as loss.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch244_repair.py
       .venv/bin/python scripts/batch244_repair.py
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import (
    hard_table,
    has_dateline_table_shape,
    is_residue,
    non_empty,
    norm,
)
from batch242_repair import sweep_gate_s4
from tickerlens.data.filings import (
    _extract_highlights_sections_anchored,
    _highlights_section_scope,
    _html_to_text,
    _split_bullet_runs,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"

_TABLE_UNITS_PHRASE_RE = re.compile(
    r"\(\$\s*in\s+(millions|thousands|billions),\s*except per share amounts\)",
    re.IGNORECASE,
)
_LABEL_DASH_RE = re.compile(r"^[A-Z][A-Za-z][A-Za-z &/'\-]+ -- ")
_SEPARATOR_RE = re.compile(r"^_+$")
_NUMBERED_URL_RE = re.compile(r"^\d+\s+https?://\S+")
_BULLET_LEADS = ("•", "◦", "▪", "■", "●", "–", "—", "‣", "·", "○", "◆", "▸", "►")
_DISCLAIMER_RES = (
    re.compile(r"^disclaimers?\b", re.IGNORECASE),
    re.compile(r"cautionary note regarding forward-looking statements", re.IGNORECASE),
    re.compile(r"private securities litigation reform act of 1995", re.IGNORECASE),
)


def _bullet_lines(lines: list[str]) -> list[str]:
    return [x for x in lines if x.startswith(_BULLET_LEADS)]


def _live_is_clean(l_lines: list[str], s_set: set) -> bool:
    """The S3/S4 live-side checks: live must not be a table, must not
    add table lines, must not end on residue or a dangling heading,
    and must not open on a fragment continuation."""
    lfrac = sum(1 for x in l_lines if is_residue(x)) / max(len(l_lines), 1)
    if lfrac >= 0.4 or has_dateline_table_shape(l_lines):
        return False
    # Batch 244: a bullet-led line is a bullet, never a table row —
    # _is_lede_data_row fires on figure-dense bullet text ("◦ Earnings
    # per Share: GAAP: $0.80; Non-GAAP: $1.04", Cisco's Q2 results
    # summary), so the added-table check exempts line-leading bullets.
    # A flattened table row never leads with a bullet glyph.
    if any(
        hard_table(x)
        for x in l_lines
        if x not in s_set and not x.startswith(_BULLET_LEADS)
    ):
        return False
    last = l_lines[-1] if l_lines else ""
    if last not in s_set and (is_residue(last) or last.rstrip().endswith(":")):
        return False
    if len(l_lines) > 1 and l_lines[1][:1].islower():
        return False
    return True


def classify_s5(stored: str, live: str) -> str | None:
    """Return the S5 wrong-section class when the swap is allowed, else
    None (not an S5 row — the caller keeps the S4 SKIP reason)."""
    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    if not s_lines or not l_lines:
        return None
    s_set = set(s_lines)
    if not _live_is_clean(l_lines, s_set):
        return None

    # s5-table: stored is a flattened earnings-deck table (APO x8).
    # Few lines, very long, carries a table-units phrase; live is a
    # clean lede without it.
    if (
        len(s_lines) <= 4
        and len(stored) >= 2000
        and any(_TABLE_UNITS_PHRASE_RE.search(x) for x in s_lines)
        and not any(_TABLE_UNITS_PHRASE_RE.search(x) for x in l_lines)
        and len(l_lines) >= 4
    ):
        return "s5-table"

    # s5-narrative: stored is detail-section prose (CSCO x3). A
    # majority of stored lines are "Label -- prose" section lines,
    # while live opens on a headline and carries real bullets.
    if (
        s_lines
        and sum(1 for x in s_lines if _LABEL_DASH_RE.match(x)) / len(s_lines) >= 0.6
        and len(_bullet_lines(l_lines)) >= 3
        and not l_lines[0].startswith(_BULLET_LEADS)
    ):
        return "s5-narrative"

    # s5-disclaimer: stored is forward-looking-statements boilerplate
    # (COIN x1). One or two lines, disclaimer-headed; live is real
    # content of at least 4 lines.
    head = " ".join(s_lines[0].split()[:12])
    if (
        len(s_lines) <= 2
        and any(rx.search(stored[:400]) for rx in _DISCLAIMER_RES)
        and len(l_lines) >= 4
        and not any(rx.search(l_lines[0]) for rx in _DISCLAIMER_RES)
    ):
        return "s5-disclaimer"

    # s5-wrong-section: stored is a non-highlights letter section
    # carrying footnote furniture (NFLX x1) — a "___" separator or
    # numbered-URL footnote lines — while live is bullet highlights
    # with none of that furniture.
    furniture = any(_SEPARATOR_RE.match(x) for x in s_lines) or sum(
        1 for x in s_lines if _NUMBERED_URL_RE.match(x)
    ) >= 2
    if (
        furniture
        and not any(_SEPARATOR_RE.match(x) for x in l_lines)
        and not any(_NUMBERED_URL_RE.match(x) for x in l_lines)
        and l_lines[0].startswith(_BULLET_LEADS)
        and len(_bullet_lines(l_lines)) >= 3
    ):
        return "s5-wrong-section"

    return None


def verify_fy_stored(html: str, stored: str, live: str) -> bool:
    """Source-verified s5-fy-stored: the stored row IS the doc's
    full-year Highlights section and live IS its quarter section
    (CART x2, ANET x1 — the mirror image of the AGNC rows). The
    doc's own anchored sections are the evidence, not a figure
    heuristic: stored must equal a fullyear-scoped candidate and
    live a quarter-scoped one, under norm. A shared first line (the
    headline, ANET) is dropped from both sides before comparing;
    a stored row that merely resembles the FY section never matches.
    Returns False when the doc has no dual sections at all, so a
    release whose only financial section is the full-year one can
    never be re-synced by this check."""
    lines = [ln.strip() for ln in _html_to_text(html).split("\n") if ln.strip()]
    lines = _split_bullet_runs(lines)
    sections = _extract_highlights_sections_anchored(lines)
    fy = [c for a, c in sections if _highlights_section_scope(a) == "fullyear"]
    qtr = [c for a, c in sections if _highlights_section_scope(a) == "quarter"]
    if not fy or not qtr:
        return False
    s_lines, l_lines = non_empty(stored), non_empty(live)
    if not s_lines or not l_lines:
        return False
    shared_headline = s_lines[0] == l_lines[0]
    s_body = s_lines[1:] if shared_headline else s_lines
    l_body = l_lines[1:] if shared_headline else l_lines
    s_norm = norm("\n".join(s_body))
    l_norm = norm("\n".join(l_body))
    return any(norm("\n".join(c)) == s_norm for c in fy) and any(
        norm("\n".join(c)) == l_norm for c in qtr
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
    repaired: dict[str, list[str]] = {}
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
        reason4 = sweep_gate_s4(stored, live)
        if reason4 is None:
            counts["S4"] = counts.get("S4", 0) + 1
            repaired.setdefault("S4", []).append(key)
            if not DRY:
                con.execute(
                    "UPDATE quarterly_financials "
                    "SET press_release_highlights = ? "
                    "WHERE cik = ? AND period_end = ?",
                    (live, cik, pe),
                )
            print(f"    S4 {key} {len(stored)}->{len(live)}")
            continue
        cls5 = classify_s5(stored, live)
        if cls5 is None and verify_fy_stored(html, stored, live):
            cls5 = "s5-fy-stored"
        if cls5 is not None:
            counts[cls5] = counts.get(cls5, 0) + 1
            repaired.setdefault(cls5, []).append(key)
            if not DRY:
                con.execute(
                    "UPDATE quarterly_financials "
                    "SET press_release_highlights = ? "
                    "WHERE cik = ? AND period_end = ?",
                    (live, cik, pe),
                )
            print(f"    {cls5} {key} {len(stored)}->{len(live)}")
            continue
        rk = f"SKIP-{reason4}"
        counts[rk] = counts.get(rk, 0) + 1
        skip_lists.setdefault(rk, []).append(key)
    if not DRY:
        con.commit()
    print(f"\nDRY_RUN={DRY} counts: {counts}")
    for cls, keys in sorted(repaired.items()):
        print(f"repaired ({cls}): {len(keys)}: {', '.join(keys)}")
    for rk in sorted(skip_lists):
        keys = skip_lists[rk]
        if rk in ("SKIP-tail", "SKIP-fragment", "SKIP-live-table",
                  "SKIP-added-table", "SKIP-dateline-mismatch"):
            print(f"  {rk} ({len(keys)}): {', '.join(keys)}")
        else:
            print(f"  {rk} ({len(keys)})")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
