"""Batch 195 repair: replace stored highlights rows the batch-195 extractor
improves, under the batch-194 highlights-specific gates.

The batch-195 extractor (leading-bullet block skips a colon-ended
list-intro heading ahead of the bullets; the Highlights section collector
and the leading-bullet continuation break on a guidance/outlook table
heading only when the next content line is not a bullet) changes 29
cached exhibits' highlights text (blast195 base vs new). 16 of those
quarters have stored highlights rows; this script repairs the stored rows
where the change is a pure improvement: the live text keeps every stored
line that is not a defect line. Defect lines are footnote-definition /
asterisk-note / rounding-note block lines, "-more-", table-start /
call-notice lines, boilerplate, and admin lines. Datelines are NOT defect
here (unlike the batch-193 guidance gates): the dateline paragraph is
legitimate lede content and must survive in live.

Expected skips (gate-correct, not failures): the DIS quarters — the
winner flips from the lede to the leading bullet block, which drops the
stored dateline paragraph; the APD Q3/Q4 FY2024 ranking flips — the
financial bullets win over the stored business bullets; APD Q3 FY2025 —
the leading block drops the stored trailing sales paragraph. Those stored
rows keep their old (not wrong) output until a later batch addresses the
one-winner ranking or the lede budget.

Two gate refinements over batch 194, both documented here because the
gates are the safety net, not the extractor:
  - Colon-heading exemption: a stored line matching _is_lede_colon_heading
    is a list-intro / section heading, not content — the lede loop skips
    such headings (batch 177) and the leading-bullet block skips them too
    (batch 195), so the new live drops them by design. Without the
    exemption the APD Q2 FY2025 repair is refused on its "Q2 FY25 Summary
    of Results (comparisons versus prior year):" intro line although every
    content line survives.
  - Bullet-space normalization: norm() strips the space after a leading
    bullet glyph, so a stored "• Data Cloud ..." line matches the live
    "•Data Cloud ..." line. The CRM Q2 FY2026 stored row is otherwise
    byte-identical in content to the new live; the only difference is the
    bullet spacing the seed-time extractor wrote.
Live is fetched from EDGAR via the service (batch-192 pattern), so no
gate rests on blast output alone; where a blast file exists the live text
must also be byte-identical to it.

Run dry:  .venv/bin/python scripts/batch195_repair.py
Run write: .venv/bin/python scripts/batch195_repair.py --write
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
BLAST_DIR = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast195/new")
BLAST_BASE_DIR = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast195/base")
TARGETS = [
    ("APD", "2024-09-30"),
    ("APD", "2024-12-31"),
    ("APD", "2025-03-31"),
    ("APD", "2025-06-30"),
    ("CPB", "2025-08-03"),
    ("CRM", "2025-07-31"),
    ("CSCO", "2025-10-25"),
    ("CSCO", "2026-01-24"),
    ("CSCO", "2026-04-25"),
    ("CSCO", "2026-07-25"),
    ("DIS", "2024-09-28"),
    ("DIS", "2024-12-28"),
    ("DIS", "2025-03-29"),
    ("DIS", "2025-06-28"),
    ("DIS", "2025-09-27"),
    ("DIS", "2025-12-27"),
]

TELECONF_RE = re.compile(r"^earnings teleconference", re.IGNORECASE)
TELECONF_ACCESS_RE = re.compile(r"^access the fiscal.*teleconference", re.IGNORECASE)
HOST_WEBCAST_RE = re.compile(r"\bwill host\b[^.]*\bwebcast\b", re.IGNORECASE)
_DECORATION_RE = re.compile(r"^[-#\s]+$")


def norm(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    # Batch 195: a stored "• X" line and a live "•X" line are the same
    # content — the seed-time extractor wrote a space after the bullet
    # glyph and the current one does not. Strip it so the preservation
    # check compares content, not bullet spacing.
    s = re.sub(r"^([•●–—])\s+", r"\1", s)
    return s


def _is_defect_line(lines: list[str], i: int) -> bool:
    """True when stored line i is droppable repair material (see module
    docstring). Block-aware: a footnote-definition / note line drops with
    its wrapped continuations, so the caller walks the stored lines with
    this predicate and skips whole blocks."""
    ln = lines[i]
    if _is_lede_colon_heading(ln):
        return True  # Batch 195: a colon-ended list-intro / section
        # heading is heading material, never content — the lede loop
        # (batch 177) and the leading-bullet block (batch 195) both skip
        # it, so the new live drops it by design.
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
    """Indices of stored lines that are defect lines (whole blocks)."""
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


def _truncated_tail_status(
    ln: str, old_live_lines: list[str], new_live_lines: list[str]
) -> str | None:
    """Classify a stored line ending in "…" (a 4000-char-cap truncation).

    Returns "kept" when its prefix opens a line the new live keeps, and
    "defect" when its prefix opens a line the old live served and the new
    live drops (the dropped next-section heading). Otherwise None.
    """
    prefix = ln.rstrip().removesuffix("…").strip()
    if len(prefix) < 3 or prefix == ln.rstrip():
        return None
    for new_ln in new_live_lines:
        if norm(new_ln).startswith(norm(prefix)):
            return "kept"
    for old_ln in old_live_lines:
        if norm(old_ln).startswith(norm(prefix)) and norm(old_ln) != norm(prefix):
            if not any(norm(new_ln) == norm(old_ln) for new_ln in new_live_lines):
                return "defect"
    return None


def _live_has_defect(live: str) -> list[str]:
    # Atomic lines, not "\n\n" paragraphs: the stored highlights body
    # joins its lines with "\n" (headline + "\n\n" + body), so a
    # paragraph-level split would hide dropped lines behind the first
    # bullet's first 60 chars (APD 2024-12-31: one giant paragraph).
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


def main() -> None:
    db = get_session()
    n_repaired = 0
    skipped: list[tuple[str, str, str]] = []
    for ticker, pe in TARGETS:
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
            skipped.append((ticker, pe, "live != blast new"))
            continue
        live_defect = _live_has_defect(live)
        if live_defect:
            skipped.append((ticker, pe, f"live carries defect: {live_defect[0]!r}"))
            continue
        old_live_lines: list[str] = []
        base_path = BLAST_BASE_DIR / f"{ticker}_{pe}.txt"
        if base_path.exists():
            old_live_lines = [
                ln
                for ln in base_path.read_text(encoding="utf-8").split("\n")
                if ln.strip()
            ]
        new_live_lines = [ln for ln in live.split("\n") if ln.strip()]
        stored_lines = [ln for ln in (l.strip() for l in stored.split("\n")) if ln]
        defects = _defect_spans(stored_lines)
        flat_live = norm(live)
        missing = []
        for i, ln in enumerate(stored_lines):
            if i in defects:
                continue
            if ln.rstrip().endswith("…"):
                status = _truncated_tail_status(ln, old_live_lines, new_live_lines)
                if status in ("kept", "defect"):
                    continue
            key = norm(ln)[:60]
            if key not in flat_live:
                missing.append(ln[:80])
        if missing:
            skipped.append((ticker, pe, f"live drops stored line: {missing[0]!r}"))
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
