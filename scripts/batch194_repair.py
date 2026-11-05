"""Batch 194 repair: replace stored highlights rows the batch-194 extractor
improves, under highlights-specific gates.

The batch-194 extractor (lede loop and Highlights section collector skip
"-more-" page markers and end the section at a heading-shaped line after
one; _clean_highlights_result pops a trailing "-more-" or a bare
company-name signature) changes 3 cached exhibits' highlights text
(blast194 base vs new2) and changes KMX Q1 FY2027 the same way (no
cached exhibit — verified by live EDGAR fetch). This script repairs the
stored rows where the change is a pure cleanup: the live text keeps every
stored line that is not a defect line. Defect lines are footnote-
definition / asterisk-note / rounding-note block lines, "-more-", table-
start / call-notice lines, boilerplate, and admin lines. Datelines are
NOT defect here (unlike the batch-193 guidance gates): the dateline
paragraph is legitimate lede content and must survive in live.

Truncated-tail exemption (the APD 2026-03-31 case): the stored row ends
with "Fiscal…" — the 4000-char cap truncated the next-section heading
"Fiscal 2026 Second Quarter Results by Business Segment" mid-word when
the row was stored. A stored line ending in "…" counts as preserved when
its prefix opens a line the new live keeps (cap-truncated content), and
as a defect line when its prefix opens a line the old live served and the
new live drops (the dropped heading). Without the exemption the
preservation gate refuses the repair on a 7-character line.

Live is fetched from EDGAR via the service (batch-192 pattern), so no
gate rests on blast output alone; where a blast file exists the live text
must also be byte-identical to it.

Run dry:  .venv/bin/python scripts/batch194_repair.py
Run write: .venv/bin/python scripts/batch194_repair.py --write
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
    _rounding_note_block_len,
    extract_press_release_highlights,
)
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.services.financials import FinancialsService
from tickerlens.services.ir_download import discover_earnings_filings

WRITE = "--write" in sys.argv
BLAST_DIR = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast194/new")
BLAST_BASE_DIR = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast194/base")
TARGETS = [("APD", "2024-12-31"), ("APD", "2026-03-31"), ("KMX", "2026-05-31")]

TELECONF_RE = re.compile(r"^earnings teleconference", re.IGNORECASE)
TELECONF_ACCESS_RE = re.compile(r"^access the fiscal.*teleconference", re.IGNORECASE)
HOST_WEBCAST_RE = re.compile(r"\bwill host\b[^.]*\bwebcast\b", re.IGNORECASE)
_DECORATION_RE = re.compile(r"^[-#\s]+$")


def norm(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    return s


def _is_defect_line(lines: list[str], i: int) -> bool:
    """True when stored line i is droppable repair material (see module
    docstring). Block-aware: a footnote-definition / note line drops with
    its wrapped continuations, so the caller walks the stored lines with
    this predicate and skips whole blocks."""
    ln = lines[i]
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
            skipped.append((ticker, pe, "live != blast new2"))
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
