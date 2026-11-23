"""Batch 196 repair: replace stored guidance rows the current extractor
improves, under a structural tail-drop gate.

Batch 193 repaired 113 stored guidance rows but skipped 294
gate-correct: its preservation gate ("live must keep every stored
line") cannot tell results narrative from guidance content, so rows
whose stored text is pre-193 over-collection (guidance bullets
followed by up to ~3,800 chars of results narrative, segment prose,
call notices and footnote legends, cut at the 4,000-char cap) waited
for a follow-up. This is that follow-up — but the fix is a repair
gate, not the multi-section merge the batch-193 docstring guessed at:
the dropped content sits under a next-section heading, not in a
second guidance section (APD's dropped tail starts at "Fiscal 2025
Full-Year Consolidated Results"; the merge would add nothing here —
APD's second "Outlook" section only duplicates the first section's
bullets, CRM's only adds a bridge table already summarized in its
bullets, DAL's stored text already equals live).

Gate (per row with a cached exhibit, source "8-K guidance, ..."):
  1. live is not None, != stored, >= 100 chars, == blast196/new output.
  2. live carries no defect lines (batch-193 _live_has_defect).
  3. Every dropped stored paragraph (non-defect, bullet-insensitive
     60-char key absent from flattened live) passes the structural
     test: it sits at/after the first next-section heading in the
     stored paragraph sequence, or it is itself a next-section heading,
     or it matches a known junk shape (footnote/call/boilerplate/
     -more-/page/decoration/dateline/bare date/webcast-host).
  4. Guard: a dropped paragraph matching a guidance heading blocks
     the repair (a second guidance section — merge work, not a tail
     drop). FSLR's "Volume Sold 18GW to 20GW" is the gate-correct
     skip that proves the guard: a genuine guidance table row the
     collector drops (its unit metric carries no $/%), so the row is
     not repaired.
  5. Added live paragraphs (not in stored) must carry guidance signal
     ($, %, guidance word, bullet) or be a short table fragment, and
     must not be call-logistics lines (conference call / webcast /
     dial / passcode / replay). CI's live text adds dial-in logistics
     the stored text lacks, so its three quarters skip gate-correct —
     their stored text already serves the outlook content.

Run dry:  .venv/bin/python scripts/batch196_repair.py
Run write: .venv/bin/python scripts/batch196_repair.py --write
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

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
    _is_guidance_heading,
    _is_lede_call_announcement,
    _rounding_note_block_len,
    extract_management_guidance,
)
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial

from batch193_repair import _defect_spans, _live_has_defect  # noqa: E402

WRITE = "--write" in sys.argv
CACHE = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html")
BLAST_DIR = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast196/new")

HOST_WEBCAST_RE = re.compile(r"\bwill host\b[^.]*\bwebcast\b", re.IGNORECASE)
HOST_CALL_RE = re.compile(r"\bwill (?:be )?host(?:ing)?\b[^.]*\bconference call\b", re.IGNORECASE)
_BARE_DATE_RE = re.compile(r"^[A-Z][a-z]+ \d{1,2}, \d{4}$")
_DECORATION_RE = re.compile(r"^[-#\s]+$")
_CALL_LOGISTICS_RE = re.compile(
    r"conference call|webcast|dial[ -]?in|passcode|replay|call-in numbers",
    re.IGNORECASE,
)
_GUIDANCE_WORDS_RE = re.compile(
    r"\b(expect|guidance|outlook|forecast|target|anticipat|project|revenue|eps|margin|capex|capital expenditures|sales|income|growth)\b",
    re.IGNORECASE,
)

# Next-section heading keywords: a stored paragraph that is a short,
# single-line, non-bullet heading (no sentence punctuation) containing
# one of these phrases ends the guidance section, so every dropped
# paragraph at/after it is next-section content, not guidance. The
# shape constraints matter: a guidance bullet never looks like this,
# and guidance prose is either a bullet or a terminated sentence.
# ("about" is a prefix rule, not a contains: an "About <Company>"
# heading; a guidance sentence starting "About $..." carries figures.)
_NEXT_SECTION_KEYWORDS = (
    "consolidated results",
    "results by business segment",
    "segment results",
    "results for the quarter",
    "recent news",
    "recent developments",
    "key recent events",
    "key updates",
    "news and highlights",
    "business highlights",
    "operational highlights",
    "segment highlights",
    "recent highlights",
    "definitions",
    "non-gaap information",
    "note on non-gaap",
    "supplemental reporting measures",
    "store count",
    "divisional performance",
    "ceo letter",
    "dividend declaration",
    "segment operating review",
    "product and pipeline update",
    "available information",
    "guidance reconciliation",
    "conference call",
    "webcast",
)


def norm196(s: str) -> str:
    """Batch-193 norm, bullet- and digit-spacing-insensitive: batch 195
    changed bullet spacing ("• Initiates" -> "•Initiates"), and the
    stored text renders a superscript footnote digit with a space
    ("2024 OUTLOOK 2") where the live text has none ("2024 OUTLOOK2"),
    so a stored heading's 60-char key must match its live form."""
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    s = re.sub(r"^•\s+", "•", s)
    s = re.sub(r"\s+(?=\d)", "", s)
    return s


def _is_junk_para(p: str) -> bool:
    """True when a dropped paragraph is known junk (mid-text drops)."""
    if not p.strip(" \t\n\r\u200b\ufeff"):
        return True
    lines = [p]
    if _footnote_def_block_len(lines, 0):
        return True
    if _rounding_note_block_len(lines, 0) or _asterisk_note_block_len(lines, 0):
        return True
    if p.strip() == "-more-":
        return True
    if _DECORATION_RE.match(p):
        return True
    if _BARE_DATE_RE.match(p.strip()):
        return True
    if _BOILERPLATE_RE.match(p) or _ADMIN_LINE_RE.match(p):
        return True
    if _FINANCIAL_TABLE_START_RE.match(p):
        return True
    if _DATELINE_LEAD_RE.match(p) or _GUIDANCE_PAREN_DATELINE_RE.match(p):
        return True
    if _is_lede_call_announcement(p):
        return True
    if HOST_WEBCAST_RE.search(p) or HOST_CALL_RE.search(p):
        return True
    if _CALL_LOGISTICS_RE.search(p):
        # A call/webcast logistics line ("A replay of the broadcast
        # will be available ...", "The call-in numbers ...") is event
        # logistics, never guidance — but never a bullet: a guidance
        # bullet never announces a replay.
        if not p.startswith("•"):
            return True
    if "made available at" in p.lower():
        return True
    if "litigation reform act" in p.lower():
        # A safe-harbor disclaimer paragraph ("... Securities Litigation
        # Reform Act of 1995 ...") is disclaimer prose, never guidance.
        return True
    if re.search(r"\bfounded in \d{4}\b", p) and re.search(
        r"\bis (the|a|one of the) (leading|largest)\b", p, re.IGNORECASE
    ):
        # About-company prose ("Church & Dwight ... founded in 1846,
        # is the leading U.S. producer ...") is company description,
        # never guidance.
        return True
    if (m := _CONFERENCE_CALL_NOTICE_RE.search(p)) is not None and m.start() <= 120:
        return True
    if (m := _CALL_QA_SESSION_RE.search(p)) is not None and m.start() <= 120:
        return True
    return False


def _is_next_section_heading(p: str) -> bool:
    """True when a stored paragraph is a next-section heading."""
    p = p.strip()
    if len(p) > 120 or "\n" in p:
        return False
    if p.startswith("•"):
        return False
    if _FINANCIAL_TABLE_START_RE.match(p):
        return True
    low = p.lower()
    if low.startswith("about ") and "$" not in p and "%" not in p:
        return True
    # A heading has no sentence punctuation (a parenthetical suffix
    # like "(comparison versus prior year)" is fine) and no figures.
    if re.search(r"[.!?]\s", p) or p.endswith((".", "!", "?")):
        return False
    return any(k in low for k in _NEXT_SECTION_KEYWORDS)


def _added_para_ok(p: str) -> bool:
    """True when an added live paragraph is genuine guidance content."""
    if _CALL_LOGISTICS_RE.search(p):
        return False
    if "$" in p or "%" in p:
        return True
    if _GUIDANCE_WORDS_RE.search(p):
        return True
    if p.startswith("•") or p.startswith("·"):
        return True
    # A short table fragment (period label, table header) is guidance
    # furniture, not content — but a bare short line with no figures
    # and no guidance words is not trusted.
    if len(p) <= 40 and re.search(r"\d{4}|Q[1-4]|FY\d{2}|H[12]\b", p):
        return True
    return False


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
            skipped.append((ticker, pe, "live != blast196 new"))
            continue
        live_defect = _live_has_defect(live)
        if live_defect:
            skipped.append((ticker, pe, f"live carries defect: {live_defect[0]!r}"))
            continue
        stored_paras = [ln for ln in (l.strip() for l in stored.split("\n\n")) if ln]
        live_paras = [ln for ln in (l.strip() for l in live.split("\n\n")) if ln]
        defects = _defect_spans(stored_paras)
        flat_live = norm196(live)
        # First next-section heading in stored order = the boundary.
        boundary = None
        for i, p in enumerate(stored_paras):
            if _is_next_section_heading(p):
                boundary = i
                break
        # Dropped stored paragraphs: non-defect, key absent from live.
        dropped: list[tuple[int, str]] = []
        for i, p in enumerate(stored_paras):
            if i in defects:
                continue
            if norm196(p)[:60] not in flat_live:
                dropped.append((i, p))
        bad_drop = None
        for i, p in dropped:
            first_line = p.split("\n")[0].strip()
            if _is_guidance_heading(first_line):
                bad_drop = f"dropped para is a guidance heading: {first_line[:80]!r}"
                break
            if boundary is not None and i >= boundary:
                continue
            if _is_next_section_heading(p):
                continue
            if _is_junk_para(p):
                continue
            bad_drop = f"dropped para before boundary: {p[:80]!r}"
            break
        if bad_drop:
            skipped.append((ticker, pe, bad_drop))
            continue
        # Added live paragraphs must be genuine guidance content.
        flat_stored = norm196(stored)
        bad_add = None
        for p in live_paras:
            if norm196(p)[:60] not in flat_stored:
                if not _added_para_ok(p):
                    bad_add = f"added live para not guidance: {p[:80]!r}"
                    break
        if bad_add:
            skipped.append((ticker, pe, bad_add))
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
