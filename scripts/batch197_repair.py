"""Batch 197 repair: replace stored highlights rows the batch-197 extractor
rescues from None / reflows, under a reflow/dump-replacement gate.

The batch-197 extractor (bullet-run splitting for ●/○ separators, plus a
bullet exemption for the batch-105 page-line guard) changes 21 cached
exhibits' highlights text (blast197 base vs new2): BKNG x7 and CART x10
go from None to real highlights, AFRM x3 and COIN x1 are reflows of
already-served text. 14 of those quarters have stored highlights rows.

The batch-194/195 preservation gate ("every stored non-defect line
survives in live") cannot apply here: the stored rows ARE the pre-fix
shape — CART's are 4000-char shareholder-letter dumps (the letter opener,
truncated before the Financial Highlights section), BKNG's/COIN's are
single mega-lines with inline " ● " bullets. Their "lines" are giant
paragraphs that survive nowhere in live as lines, so preservation is
checked in the reflow direction instead, with a per-ticker gate:

  - BKNG / COIN (inline-bullet mega-line): every live bullet line's
    normalized text (●/○ normalized to •, whitespace collapsed) must
    appear as a substring of the stored text — the live bullets are the
    stored mega-line's bullets, split out. No live content may be new.
  - CART (letter dump): the stored text must start with "Dear
    Shareholders," (the dump class — the letter opener the extractor
    now refuses to serve as highlights), and the live figures must match
    the row's stored XBRL figures: "Total revenue of $X million" vs
    revenue/1e6 and "GAAP net income of $Y million" vs net_income/1e6,
    within $1.5M rounding. The stored dump is truncated before the
    highlights section, so no bullet-substring check is possible; the
    figure cross-check is the independent guard that the live text is
    about the right quarter.

Common gates (batch-195 pattern): live fetched from EDGAR via the
service; source label must match the stored source; live >= 200 chars;
live differs from stored; where a blast file exists the live text must
be byte-identical to it (new2 = both fixes); live carries no defect
lines (footnote/asterisk/rounding blocks, "-more-", table-start,
call-notice, boilerplate, admin).

Expected skips (gate-correct): none of the 14 targets is expected to
skip — CART's figure check is designed for its bullet wording and
BKNG/COIN's substring check for theirs. AFRM's three changed quarters
have no stored rows (2023-09-30/2024-03-31) or a NULL row (2023-12-31,
refilled by the normal refresh path), so they are not targets here.

Run dry:  .venv/bin/python scripts/batch197_repair.py
Run write: .venv/bin/python scripts/batch197_repair.py --write
"""
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "src")

from sqlalchemy import select

from tickerlens.data.filings import (
    _ADMIN_LINE_RE,
    _BOILERPLATE_RE,
    _CALL_QA_SESSION_RE,
    _CONFERENCE_CALL_NOTICE_RE,
    _FINANCIAL_TABLE_START_RE,
    _asterisk_note_block_len,
    _footnote_def_block_len,
    _is_lede_call_announcement,
    _is_lede_colon_heading,
    _rounding_note_block_len,
    extract_press_release_highlights,
)
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.services.financials import FinancialsService
from tickerlens.services.ir_download import discover_earnings_filings

WRITE = "--write" in sys.argv
BLAST_DIR = Path(
    "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast197/new2"
)
# (ticker, period_end, gate) — gate "dump" for CART's letter dumps,
# "reflow" for BKNG/COIN's inline-bullet mega-lines.
TARGETS = [
    ("CART", "2024-09-30", "dump"),
    ("CART", "2024-12-31", "dump"),
    ("CART", "2025-03-31", "dump"),
    ("CART", "2025-06-30", "dump"),
    ("CART", "2025-09-30", "dump"),
    ("CART", "2025-12-31", "dump"),
    ("BKNG", "2024-12-31", "reflow"),
    ("BKNG", "2025-03-31", "reflow"),
    ("BKNG", "2025-06-30", "reflow"),
    ("BKNG", "2025-09-30", "reflow"),
    ("BKNG", "2025-12-31", "reflow"),
    ("BKNG", "2026-03-31", "reflow"),
    ("BKNG", "2026-06-30", "reflow"),
    ("COIN", "2026-03-31", "reflow"),
]

TELECONF_RE = re.compile(r"^earnings teleconference", re.IGNORECASE)
TELECONF_ACCESS_RE = re.compile(r"^access the fiscal.*teleconference", re.IGNORECASE)
HOST_WEBCAST_RE = re.compile(r"\bwill host\b[^.]*\bwebcast\b", re.IGNORECASE)
_DECORATION_RE = re.compile(r"^[-#\s]+$")
_REVENUE_RE = re.compile(r"Total revenue of \$([\d,]+(?:\.\d+)?) million")
_NET_INCOME_RE = re.compile(r"GAAP net income of \$([\d,]+(?:\.\d+)?) million")


def norm(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    s = re.sub(r"^([•●–—])\s+", r"\1", s)
    return s


def _norm_bullet_text(s: str) -> str:
    """Normalize a bullet line for substring comparison: collapse
    whitespace, unify the bullet glyphs (●/○ read as •), drop the
    leading bullet + space."""
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[•●○]\s*", "", s)
    return s


def _is_defect_line(lines: list[str], i: int) -> bool:
    """True when stored line i is droppable repair material (batch-195
    predicate, unchanged: the defect-line scan on live is the same)."""
    ln = lines[i]
    if _is_lede_colon_heading(ln):
        return True
    if _footnote_def_block_len(lines, i):
        return True
    if _rounding_note_block_len(lines, i) or _asterisk_note_block_len(lines, i):
        return True
    if ln.strip() == "-more-":
        return True
    if _DECORATION_RE.match(ln):
        return True
    if _FINANCIAL_TABLE_START_RE.match(ln):
        return True
    if TELECONF_RE.match(ln) or TELECONF_ACCESS_RE.match(ln):
        return True
    if _is_lede_call_announcement(ln) or HOST_WEBCAST_RE.search(ln):
        return True
    if (m := _CONFERENCE_CALL_NOTICE_RE.search(ln)) is not None and m.start() <= 120:
        return True
    if (m := _CALL_QA_SESSION_RE.search(ln)) is not None and m.start() <= 120:
        return True
    if _BOILERPLATE_RE.match(ln):
        return True
    if _ADMIN_LINE_RE.match(ln):
        return True
    return False


def _defect_spans(lines: list[str]) -> set[int]:
    out: set[int] = set()
    i = 0
    while i < len(lines):
        if _footnote_def_block_len(lines, i):
            n = _footnote_def_block_len(lines, i)
            out.update(range(i, i + n))
            i += n
            continue
        if _rounding_note_block_len(lines, i) or _asterisk_note_block_len(lines, i):
            n = _rounding_note_block_len(lines, i) or _asterisk_note_block_len(lines, i)
            out.update(range(i, i + n))
            i += n
            continue
        if _is_defect_line(lines, i):
            out.add(i)
        i += 1
    return out


def _live_has_defect(live: str) -> list[str]:
    lines = [ln for ln in (l.strip() for l in live.split("\n")) if ln]
    bad = []
    for i, ln in enumerate(lines):
        if _is_defect_line(lines, i):
            bad.append(ln[:90])
    return bad


def fetch_live(ticker, cik, pe):
    """Return (live, src) or (None, None, reason) via the EDGAR service."""
    svc = FinancialsService()
    try:
        periods = discover_earnings_filings(
            ticker, svc.edgar_client, n_quarters=10,
            oldest_period_end=date.fromisoformat(pe),
        )
    except Exception as exc:  # noqa: BLE001
        return None, None, f"discover failed: {type(exc).__name__} {exc}"
    by_pe = {str(p.period_end): p for p in periods}
    period = by_pe.get(pe)
    if period is None:
        return None, None, "period not discovered"
    try:
        live, src, _, _, _, _ = svc._fetch_press_release_disclosures(cik, period)
    except Exception as exc:  # noqa: BLE001
        return None, None, f"extract failed: {type(exc).__name__} {exc}"
    return live, src, None


def _figure_check(live: str, qrow) -> str | None:
    """CART dump gate: live figures must match the row's XBRL figures.

    ANY-match, not first-match: a Q4 release's live text opens with the
    full-year bullets ("Total revenue of $3,378 million" for FY2024)
    before the quarter bullets ("Total revenue of $883 million"), and
    the row's revenue is the quarter's — the first match is the FY
    figure, the matching one is the second. Same for net income.
    """
    revs = [float(v.replace(",", "")) for v in _REVENUE_RE.findall(live)]
    if not revs:
        return "live has no 'Total revenue of $X million' line"
    if qrow.revenue is None or not any(
        abs(r - qrow.revenue / 1e6) <= 1.5 for r in revs
    ):
        return f"live revenues {revs} vs stored ${qrow.revenue / 1e6 if qrow.revenue else None}M"
    nis = [float(v.replace(",", "")) for v in _NET_INCOME_RE.findall(live)]
    if nis and qrow.net_income is not None and not any(
        abs(n - qrow.net_income / 1e6) <= 1.5 for n in nis
    ):
        # Two revenue figures means the live text carries both the
        # full-year and the quarter bullets (a Q4 release): the section's
        # 12-line budget then cuts the quarter's net-income bullet (the
        # FY bullets + heading + first quarter bullets fill it), so the
        # only net-income figure present is the FY one and it cannot
        # match the quarter's. The revenue leg already ties live to the
        # right quarter, so the net-income leg is waived in that shape.
        if len(revs) < 2:
            return f"live net incomes {nis} vs stored ${qrow.net_income / 1e6}M"
    return None


def main() -> None:
    db = get_session()
    n_repaired = 0
    skipped: list[tuple[str, str, str]] = []
    for ticker, pe, gate in TARGETS:
        cik = db.execute(
            select(Company.cik).where(Company.ticker == ticker)
        ).scalar_one_or_none()
        if cik is None:
            skipped.append((ticker, pe, "no company row"))
            continue
        qrow = db.execute(
            select(QuarterlyFinancial).where(
                QuarterlyFinancial.cik == cik,
                QuarterlyFinancial.period_end == date.fromisoformat(pe),
            )
        ).scalar_one_or_none()
        if qrow is None or not qrow.press_release_highlights:
            skipped.append((ticker, pe, "no stored highlights row"))
            continue
        stored = qrow.press_release_highlights or ""
        live, src, err = fetch_live(ticker, cik, pe)
        if err:
            skipped.append((ticker, pe, err))
            continue
        if live is None:
            skipped.append((ticker, pe, "live is None"))
            continue
        if src != qrow.press_release_source:
            skipped.append(
                (ticker, pe, f"source mismatch live={src!r} stored={qrow.press_release_source!r}")
            )
            continue
        if len(live) < 200:
            skipped.append((ticker, pe, f"live too short ({len(live)})"))
            continue
        if live == stored:
            skipped.append((ticker, pe, "live == stored (nothing to repair)"))
            continue
        blast_path = BLAST_DIR / f"{ticker}_{pe}.txt"
        if blast_path.exists() and blast_path.read_text(encoding="utf-8") != live:
            skipped.append((ticker, pe, "live != blast new2"))
            continue
        live_defect = _live_has_defect(live)
        if live_defect:
            skipped.append((ticker, pe, f"live carries defect: {live_defect[0]!r}"))
            continue
        if gate == "dump":
            # CART: stored must be the letter-dump class, and live
            # figures must match the row's XBRL figures.
            if not stored.startswith("Dear Shareholders,"):
                skipped.append((ticker, pe, "stored is not a letter dump"))
                continue
            fig_err = _figure_check(live, qrow)
            if fig_err:
                skipped.append((ticker, pe, fig_err))
                continue
        else:
            # BKNG/COIN: stored must be the inline-bullet mega-line
            # class, and every live bullet must already be in stored.
            if " ● " not in stored and " ○ " not in stored:
                skipped.append((ticker, pe, "stored has no inline bullets"))
                continue
            flat_stored = _norm_bullet_text(norm(stored))
            missing = []
            for ln in (l.strip() for l in live.split("\n")):
                if not ln.startswith("•"):
                    continue
                key = _norm_bullet_text(ln)
                if key and key not in flat_stored:
                    missing.append(ln[:80])
            if missing:
                skipped.append((ticker, pe, f"live bullet not in stored: {missing[0]!r}"))
                continue
        print(f"REPAIR {ticker} {pe}: {len(stored)} -> {len(live)} chars")
        n_repaired += 1
        if WRITE:
            qrow.press_release_highlights = live
    if WRITE:
        db.commit()
        print(f"committed {n_repaired} repairs")
    else:
        print(f"dry run: {n_repaired} would repair (use --write to apply)")
    print(f"skipped: {len(skipped)}")
    for ticker, pe, why in skipped:
        print(f"  SKIP {ticker} {pe}: {why}")


if __name__ == "__main__":
    main()
