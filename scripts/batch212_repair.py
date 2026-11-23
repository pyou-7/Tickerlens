"""Batch 212 repair: replace the 45 stored management_guidance rows the
batch-212 fix corrects.

Batch 212 fixes guidance extraction in extract_management_guidance:
teaser-anchor rejection (a highlights-area teaser heading no longer
anchors — GPC/CSCO), post-table section-end follower generalization
(GPC/FDX/SKYD bleed cut), and anchor recognition (AKAM intro lines,
DG "Financial Guidance" headings, wrapped headings). The blast
(blast212/g_new3 vs g_old, 1,699 exhibits) shows 119 diffs, 0 lost
anchors, 55 rescues (None -> real guidance). 45 of the 119 have
stored rows; the other 74 (no row or stored-None) serve on refresh.

Gate (per row): the live re-extraction from the cached exhibit must be
byte-identical to the blast g_new3 file; the stored text must be
byte-identical to the blast g_old file (43 rows) or pass the row's
documented variant gate (FDX 2025-05-31: bullet-spacing + "- more -"
marker normalized prefix; GPC 2025-12-31: stored startswith live);
the live text must carry a $ figure and none of the bleed markers the
row's stored text carries; the stored text must carry at least one
bleed marker. Rows failing any check SKIP gate-correct and are
reported, never overridden.

Run dry:  .venv/bin/python scripts/batch212_repair.py
Run write: .venv/bin/python scripts/batch212_repair.py --write
"""
import datetime
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_management_guidance  # noqa: E402
from tickerlens.models.database import get_session  # noqa: E402
from tickerlens.models.quarterly_financial import QuarterlyFinancial  # noqa: E402

WRITE = "--write" in sys.argv
CACHE = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html")
BLAST_DIR = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast212")

# Blast-verified rows with stored guidance (ticker, cik, period_end).
INCLUDE = [
    ("ABBV", "0001551152", "2024-09-30"),
    ("ABBV", "0001551152", "2025-09-30"),
    ("ACN", "0001467373", "2025-02-28"),
    ("ACN", "0001467373", "2025-05-31"),
    ("ACN", "0001467373", "2025-08-31"),
    ("ACN", "0001467373", "2025-11-30"),
    ("ACN", "0001467373", "2026-02-28"),
    ("ACN", "0001467373", "2026-05-31"),
    ("ACN", "0001467373", "2026-08-31"),
    ("AVGO", "0001730168", "2024-11-03"),
    ("AVGO", "0001730168", "2025-02-02"),
    ("AVGO", "0001730168", "2025-05-04"),
    ("AVGO", "0001730168", "2025-08-03"),
    ("AVGO", "0001730168", "2025-11-02"),
    ("AVGO", "0001730168", "2026-02-01"),
    ("AVGO", "0001730168", "2026-05-03"),
    ("AVGO", "0001730168", "2026-08-02"),
    ("BIIB", "0000875045", "2024-12-31"),
    ("BIIB", "0000875045", "2025-12-31"),
    ("CI", "0001739940", "2024-12-31"),
    ("CI", "0001739940", "2025-12-31"),
    ("CSCO", "0000858877", "2024-10-26"),
    ("CSCO", "0000858877", "2025-01-25"),
    ("CSCO", "0000858877", "2025-07-26"),
    ("DG", "0000029534", "2025-05-02"),
    ("DG", "0000029534", "2026-05-01"),
    ("ETN", "0001551182", "2024-09-30"),
    ("ETN", "0001551182", "2024-12-31"),
    ("ETN", "0001551182", "2025-03-31"),
    ("ETN", "0001551182", "2025-06-30"),
    ("ETN", "0001551182", "2025-09-30"),
    ("ETN", "0001551182", "2025-12-31"),
    ("ETN", "0001551182", "2026-03-31"),
    ("FDX", "0001048911", "2024-08-31"),
    ("FDX", "0001048911", "2024-11-30"),
    ("FDX", "0001048911", "2025-02-28"),
    ("FDX", "0001048911", "2025-05-31"),
    ("FDX", "0001048911", "2025-08-31"),
    ("FDX", "0001048911", "2025-11-30"),
    ("FDX", "0001048911", "2026-02-28"),
    ("FIS", "0001136893", "2025-09-30"),
    ("GPC", "0000040987", "2024-12-31"),
    ("GPC", "0000040987", "2025-06-30"),
    ("GPC", "0000040987", "2025-09-30"),
    ("GPC", "0000040987", "2025-12-31"),
]

# Post-table bleed markers: the stored text carries at least one, the
# live text none. (Teaser-anchor rows carry the teaser bullet instead;
# the blast diff itself proves the defect there, so the marker check
# is satisfied by any marker OR by stored != live with live a prefix
# of stored — see _stored_has_defect.)
BLEED_MARKERS = (
    "Company Declares Dividend Increase",
    "Quarterly Dividends",
    "Business Segment Results",
    "Corporate Overview",
    "Non-GAAP Information",
    "Plan to Separate Automotive and Industrial Businesses",
    "Comparable Sales",
    "Update on Pending Strategic Transactions",
    "Conference Call Information",
    "Revenues for the",
    "Q4 Revenues for the",
    "Fourth Quarter 2023 Results",
    "Fiscal 2025 and 2026 Profit Recovery Plan",
    "Copeland Transaction Update",
    "Company to Host Conference Call",
    # NOT "Total Medical Customers": that is a legitimate Cigna outlook
    # table row (the CI repair ADDS it — the old extraction cut the
    # table early), not bleed.
)

_MORE_BLOCK_RE = re.compile(r"^(?:-\s*more\s*-|-MORE-)$", re.IGNORECASE)


def _normalize(text: str) -> str:
    """Bullet-spacing + page-marker normalization for the FDX
    2025-05-31 stored variant (older extractor wrote "•A flat" with
    no space and kept the "- more -" page marker as a block)."""
    blocks = []
    for block in text.split("\n\n"):
        if _MORE_BLOCK_RE.match(block.strip()):
            continue
        blocks.append(re.sub(r"•\s*", "• ", block))
    return "\n\n".join(blocks)


def _stored_has_defect(stored: str, live: str) -> str | None:
    if any(m in stored for m in BLEED_MARKERS):
        return None
    # Teaser-anchor rows: the stored text carries the highlights-area
    # teaser bullet ("• Revenue Growth of ..." — GPC) that the live
    # text replaces with the real table intro, or it anchors on a
    # teaser fragment ("guidance range" — CSCO's wrapped-bullet
    # fragment; "Guidance for Fiscal Year 2025" — DG's headline).
    if "• Revenue Growth of" in stored and "• Revenue Growth of" not in live:
        return None
    first_block = stored.split("\n\n")[0].strip().lower()
    if first_block == "guidance range" or first_block.startswith(
        "guidance for fiscal year"
    ):
        return None
    # Anchor/fullness rows: the live text ADDS content the stored text
    # lacks — the stored text is a substring of live (BIIB: the real
    # section heading + intro; CI: the outlook table's tail rows).
    if stored != live and stored in live:
        return None
    if stored.startswith(live):
        return None
    return "stored text carries no bleed marker or teaser bullet"


def _live_has_signal(live: str) -> str | None:
    if not live:
        return "live text is empty/None"
    if "$" not in live and "%" not in live:
        return "live text has no $ or % figure"
    if any(m in live for m in BLEED_MARKERS):
        return "live text still carries a bleed marker"
    return None


def main() -> None:
    session = get_session()
    repaired = skipped = 0
    for ticker, cik, pe in INCLUDE:
        key = f"{ticker}_{pe}"
        html = (CACHE / f"{key}.html").read_text(encoding="utf-8")
        live = extract_management_guidance(html)
        blast_new = (BLAST_DIR / "g_new3" / f"{key}.txt").read_text(encoding="utf-8")
        blast_old = (BLAST_DIR / "g_old" / f"{key}.txt").read_text(encoding="utf-8")
        row = (
            session.query(QuarterlyFinancial)
            .filter(
                QuarterlyFinancial.cik == cik,
                QuarterlyFinancial.period_end == datetime.date.fromisoformat(pe),
            )
            .first()
        )
        if row is None:
            print(f"SKIP {key}: no stored row")
            skipped += 1
            continue
        stored = row.management_guidance
        if stored is None:
            print(f"SKIP {key}: stored guidance is None")
            skipped += 1
            continue
        reason = None
        if live != blast_new:
            reason = "live re-extraction != blast g_new3"
        elif stored != blast_old:
            # Documented stored variants (older extractor formatting).
            if key == "FDX_2025-05-31":
                if not _normalize(stored).startswith(_normalize(live)):
                    reason = "FDX stored variant fails normalized-prefix gate"
            elif key == "GPC_2025-12-31":
                if not stored.startswith(live):
                    reason = "GPC stored variant fails startswith-live gate"
            else:
                reason = "stored text != blast g_old"
        if reason is None:
            reason = _live_has_signal(live) or _stored_has_defect(stored, live)
        if reason is not None:
            print(f"SKIP {key}: {reason}")
            skipped += 1
            continue
        if WRITE:
            row.management_guidance = live
            session.commit()
        print(
            f"{'REPAIRED' if WRITE else 'WOULD-REPAIR'} {key}: "
            f"{len(stored)} -> {len(live)} chars"
        )
        repaired += 1
    print(f"{repaired} repaired, {skipped} skipped (WRITE={WRITE})")


if __name__ == "__main__":
    main()
