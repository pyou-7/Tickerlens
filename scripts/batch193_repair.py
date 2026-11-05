"""Batch 193 repair: replace stored guidance rows the batch-193 extractor
improves, under guidance-specific gates.

The batch-193 extractor (footnote blocks skipped in-loop, next-section
heading breaks, "-more-" / title-line skips, period-label and anchor
fixes) changes 448 cached exhibits' guidance text (blast193 new8 vs
base) and gains 31 more. This script repairs the stored rows where the
change is a pure cleanup: the live text keeps every stored line that is
not a defect line. Defect lines are footnote-definition / asterisk-note /
rounding-note block lines, "-more-", teleconference / call-notice lines,
boilerplate lines, page markers, and datelines. Rows whose stored text
carries next-section results narrative (APD's Consolidated Results prose,
DAL's cost-performance narrative, CRM's margin table under the new
revenue-table section) SKIP gate-correct: the preservation gate cannot
tell results narrative from guidance content, so those rows wait for the
multi-section merge follow-up. The script never overrides a gate.

Live is re-extracted from the cached exhibit inside this script, so no
gate rests on blast output alone; where a blast file exists the live text
must also be byte-identical to it.

Run dry:  .venv/bin/python scripts/batch193_repair.py
Run write: .venv/bin/python scripts/batch193_repair.py --write
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
    _DATELINE_LEAD_RE,
    _FINANCIAL_TABLE_START_RE,
    _GUIDANCE_PAREN_DATELINE_RE,
    _asterisk_note_block_len,
    _footnote_def_block_len,
    _is_lede_call_announcement,
    _rounding_note_block_len,
    extract_management_guidance,
)
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial

WRITE = "--write" in sys.argv
CACHE = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html")
BLAST_DIR = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast193/new")

TELECONF_RE = re.compile(r"^earnings teleconference", re.IGNORECASE)
TELECONF_ACCESS_RE = re.compile(r"^access the fiscal.*teleconference", re.IGNORECASE)
HOST_WEBCAST_RE = re.compile(r"\bwill host\b[^.]*\bwebcast\b", re.IGNORECASE)
_PAREN_WORD_HEADER_RE = re.compile(r"^\([A-Za-z]+\)\d?(?:\s+[A-Z][a-z]*)?$")
_DECORATION_RE = re.compile(r"^[-#\s]+$")


def _is_paren_word_header(ln: str) -> bool:
    """True for a parenthesized-word table header ("(Prior) July",
    "(Updated)4" — BMY's guidance-table headers). The extractor collects
    these (batch 193's paren-header exemption), so the repair gates must
    not call them footnote defects: BMY 2026-09-30's live text carries
    "(Prior) October" and a gate that flags it refuses a clean repair."""
    return bool(_PAREN_WORD_HEADER_RE.match(ln))


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
    if _is_paren_word_header(ln):
        return False
    if _footnote_def_block_len(lines, i):
        return True
    if _rounding_note_block_len(lines, i) or _asterisk_note_block_len(lines, i):
        return True
    if ln.strip() == "-more-":
        return True
    if _DECORATION_RE.match(ln):
        # A rule/decoration line ("--- # # # ---" — COP's separator).
        return True
    if _FINANCIAL_TABLE_START_RE.match(ln):
        # A table-start / call / webcast heading is next-section content
        # (AKAM's "Quarterly Conference Call"), never guidance.
        return True
    if TELECONF_RE.match(ln) or TELECONF_ACCESS_RE.match(ln):
        return True
    if _is_lede_call_announcement(ln) or HOST_WEBCAST_RE.search(ln):
        return True
    if (m := _CONFERENCE_CALL_NOTICE_RE.search(ln)) is not None and m.start() <= 120:
        return True
    if (m := _CALL_QA_SESSION_RE.search(ln)) is not None and m.start() <= 120:
        # GIS's pre-recorded-remarks / webcasted-Q&A notice (and its
        # continuation lines) — same 120-char guard as the extractor.
        return True
    if _BOILERPLATE_RE.match(ln):
        return True
    if _ADMIN_LINE_RE.match(ln):
        return True
    if _DATELINE_LEAD_RE.match(ln) or _GUIDANCE_PAREN_DATELINE_RE.match(ln):
        return True
    return False


def _defect_spans(lines: list[str]) -> set[int]:
    """Indices of stored lines that are defect lines (whole blocks)."""
    out: set[int] = set()
    i = 0
    while i < len(lines):
        if _is_paren_word_header(lines[i]):
            i += 1
            continue
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
    lines = [ln for ln in (l.strip() for l in live.split("\n\n")) if ln]
    bad = []
    for i, ln in enumerate(lines):
        if _is_defect_line(lines, i):
            bad.append(ln[:90])
    return bad


def main() -> None:
    db = get_session()
    rows = (
        db.execute(
            select(QuarterlyFinancial).where(
                QuarterlyFinancial.management_guidance.isnot(None),
                QuarterlyFinancial.management_guidance != "",
            )
        )
        .scalars()
        .all()
    )
    print(f"stored guidance rows: {len(rows)}")
    n_no_cache = n_no_diff = n_repaired = 0
    skipped: list[tuple[str, str, str]] = []
    for row in rows:
        ticker = (
            db.execute(select(Company.ticker).where(Company.cik == row.cik)).scalar_one_or_none()
        )
        if ticker is None:
            skipped.append(("", str(row.period_end), "no company row"))
            continue
        pe = row.period_end.isoformat()
        html_path = CACHE / f"{ticker}_{pe}.html"
        if not html_path.exists():
            n_no_cache += 1
            continue
        html = html_path.read_text(encoding="utf-8")
        live = extract_management_guidance(html)
        stored = row.management_guidance or ""
        if live is None or live == stored:
            n_no_diff += 1
            continue
        if not (row.management_guidance_source or "").startswith("8-K guidance, "):
            skipped.append((ticker, pe, f"source {row.management_guidance_source!r}"))
            continue
        if len(live) < 100:
            skipped.append((ticker, pe, f"live {len(live)} chars < 100"))
            continue
        blast_path = BLAST_DIR / f"{ticker}_{pe}.txt"
        if blast_path.exists() and blast_path.read_text(encoding="utf-8") != live:
            skipped.append((ticker, pe, "live != blast new8"))
            continue
        live_defect = _live_has_defect(live)
        if live_defect:
            skipped.append((ticker, pe, f"live carries defect: {live_defect[0]!r}"))
            continue
        stored_lines = [ln for ln in (l.strip() for l in stored.split("\n\n")) if ln]
        defects = _defect_spans(stored_lines)
        flat_live = norm(live)
        missing = []
        for i, ln in enumerate(stored_lines):
            if i in defects:
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
            row.management_guidance = live
    if WRITE:
        db.commit()
        print(f"committed {n_repaired} repairs")
    else:
        print(f"dry run: {n_repaired} would repair (use --write to apply)")
    print(f"no cached exhibit: {n_no_cache}, live==stored or None: {n_no_diff}, skipped: {len(skipped)}")
    for ticker, pe, why in skipped:
        print(f"  SKIP {ticker} {pe}: {why}")


if __name__ == "__main__":
    main()
