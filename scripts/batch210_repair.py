"""Batch 210 repair: replace the table-of-contents dump in the 8
stored DLR guidance rows with the genuine Core FFO outlook the
batch-210 fix extracts.

Batch 210 adds the TOC-entry anchor rejection to
extract_management_guidance (via _is_toc_entry): a heading that heads
a table-of-contents run (two consecutive title + page-number pairs)
is skipped so the collector anchors on the real outlook section.
The blast (blast210/g_new vs blast210/g_old, 1,699 exhibits) shows
12 diffs, 0 None-flips — all DLR, all TOC dumps replaced by genuine
Core FFO outlook tables. 8 of the 12 have stored rows; the other 4
(2023-12-31, 2024-03-31, 2026-06-30, 2026-09-30) are pre-seeding
quarters with no stored rows and serve on refresh.

Gate (per row): the stored text must be byte-identical to the blast
g_old file (the row is exactly the TOC dump the old extractor
produced), the live re-extraction from the cached exhibit must be
byte-identical to the blast g_new file, the live text must carry
genuine guidance signal ("Core FFO" plus a $ figure range) and no
TOC title ("Consolidated Quarterly Statements of Operations"), and
the stored text must carry that TOC title. Rows failing any check
SKIP gate-correct and are reported, never overridden. Unlike the
tail-cut batches, live is not a prefix of stored here — the whole
text is replaced — so the gate pins both sides to their blast files
instead.

Run dry:  .venv/bin/python scripts/batch210_repair.py
Run write: .venv/bin/python scripts/batch210_repair.py --write
"""
import sys
from pathlib import Path

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_management_guidance  # noqa: E402
from tickerlens.models.database import get_session  # noqa: E402
from tickerlens.models.quarterly_financial import QuarterlyFinancial  # noqa: E402

WRITE = "--write" in sys.argv
CACHE = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html")
BLAST_DIR = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast210")

# Blast-verified TOC replacements with stored rows only.
INCLUDE = [
    "2024-06-30",
    "2024-09-30",
    "2024-12-31",
    "2025-03-31",
    "2025-06-30",
    "2025-09-30",
    "2025-12-31",
    "2026-03-31",
]
CIK = "0001297996"
TOC_MARKER = "Consolidated Quarterly Statements of Operations"


def _live_has_signal(live: str) -> str | None:
    if "Core FFO" not in live:
        return "live text has no Core FFO signal"
    if "$" not in live:
        return "live text has no $ figure"
    if TOC_MARKER in live:
        return "live text still carries the TOC title"
    return None


def main() -> None:
    session = get_session()
    repaired = skipped = 0
    for pe in INCLUDE:
        name = f"DLR_{pe}.html"
        html = (CACHE / name).read_text(encoding="utf-8")
        live = extract_management_guidance(html)
        blast_new = (BLAST_DIR / "g_new" / f"DLR_{pe}.txt").read_text(encoding="utf-8")
        blast_old = (BLAST_DIR / "g_old" / f"DLR_{pe}.txt").read_text(encoding="utf-8")
        row = (
            session.query(QuarterlyFinancial)
            .filter(
                QuarterlyFinancial.cik == CIK,
                QuarterlyFinancial.period_end == pe,
            )
            .one_or_none()
        )
        if row is None or not row.management_guidance:
            print(f"DLR {pe}: SKIP no stored row")
            skipped += 1
            continue
        stored = row.management_guidance
        if stored == live:
            print(f"DLR {pe}: already clean")
            continue
        if live is None or live != blast_new:
            print(f"DLR {pe}: SKIP live != blast g_new file")
            skipped += 1
            continue
        if stored != blast_old:
            print(f"DLR {pe}: SKIP stored != blast g_old file")
            skipped += 1
            continue
        if TOC_MARKER not in stored:
            print(f"DLR {pe}: SKIP stored text has no TOC marker")
            skipped += 1
            continue
        why = _live_has_signal(live)
        if why is not None:
            print(f"DLR {pe}: SKIP {why}")
            skipped += 1
            continue
        print(f"DLR {pe}: REPAIR {len(stored)}->{len(live)} chars")
        if WRITE:
            row.management_guidance = live
            repaired += 1
    if WRITE:
        session.commit()
        print(f"committed: {repaired} repaired, {skipped} skipped")
    else:
        print(f"dry run: {repaired} would repair, {skipped} skipped")
        print("re-run with --write to apply")


if __name__ == "__main__":
    main()
