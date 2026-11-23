"""Batch 282 regression tests.

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
live. The 5 CRWD siblings (2025-01-31, 2025-10-31, 2026-01-31,
2026-04-30, 2026-07-31) already store the live shape (stored == live
under norm), which is the consistency cross-check for the re-sync.

No extractor change in batch 282: the re-sync is a DB repair.

Open, noted not fixed: the remaining SKIP-loss rows (largest groups
DHI x4, GPC x4 -- both lose stored figures on re-sync, so neither is
a strict-superset repair).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# key, headline, first bullet, last bullet, line count.
# All 3 live shapes are headline + CEO/CFO quotes + 7 financial
# bullets + "Recent Highlights" list, 19 lines.
RESYNCED_QUARTERS = (
    (
        "CRWD_2024-10-31",
        "CrowdStrike Reports Third Quarter Fiscal Year 2025 Financial Results",
        "• Revenue: Total revenue was $1,010.2 million, a 29% increase, compared to $786.0 million in the third quarter of fiscal 2024. Subscription revenue was $962.7 million, a 31% increase, compared to $733.5 million in the third quarter of fiscal 2024.",
        "• Unveiled a series of new and enhanced offerings during the eighth annual Fal.Con cybersecurity conference. Announcements included Endpoint Security; Cloud Security; Identity Protection; Next-Gen SIEM; Exposure Management; Charlotte AI and Falcon for IT innovations; Project Kestrel, a revolutionary new user experience and CrowdStrike Financial Services.",
        19,
    ),
    (
        "CRWD_2025-04-30",
        "CrowdStrike Reports First Quarter Fiscal Year 2026 Financial Results",
        "• Revenue: Total revenue was $1.10 billion, a 20% increase, compared to $921.0 million in the first quarter of fiscal 2025. Subscription revenue was $1.05 billion, a 20% increase, compared to $872.2 million in the first quarter of fiscal 2025.",
        "• Revealed new Falcon Data Protection innovations, enabling security teams to protect sensitive data across endpoints, cloud environments and GenAI and SaaS applications to prevent exfiltration by insiders and identity-based attackers.",
        19,
    ),
    (
        "CRWD_2025-07-31",
        "CrowdStrike Reports Second Quarter Fiscal Year 2026 Financial Results",
        "• Revenue: Total revenue was $1.17 billion, a 21% increase, compared to $963.9 million in the second quarter of fiscal 2025. Subscription revenue was $1.10 billion, a 20% increase, compared to $918.3 million in the second quarter of fiscal 2025.",
        "• Released CrowdStrike Falcon Next-Gen Identity Security, the first unified solution to protect every identity – human, non-human, and AI agent – across the full hybrid identity lifecycle and every environment.",
        19,
    ),
)

# Siblings already store the live shape: headline, line count.
SIBLING_QUARTERS = (
    ("CRWD_2025-01-31", "CrowdStrike Reports Fourth Quarter and Fiscal Year 2025 Financial Results", 16),
    ("CRWD_2025-10-31", "CrowdStrike Reports Third Quarter Fiscal Year 2026 Financial Results", 19),
    ("CRWD_2026-01-31", "CrowdStrike Reports Fourth Quarter and Fiscal Year 2026 Financial Results", 16),
    ("CRWD_2026-04-30", "CrowdStrike Reports First Quarter Fiscal Year 2027 Financial Results", 17),
    ("CRWD_2026-07-31", "CrowdStrike Reports Second Quarter Fiscal Year 2027 Financial Results", 19),
)


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def test_resynced_quarters_serve_full_shape():
    for key, headline, first_bullet, last_bullet, n in RESYNCED_QUARTERS:
        live = _live(key)
        lines = _live_lines(key)
        assert lines[0] == headline, key
        bullets = [ln for ln in lines if ln.startswith("•")]
        assert bullets[0] == first_bullet, key
        assert bullets[-1] == last_bullet, key
        assert len(lines) == n, key
        assert "said George Kurtz" in live, key
        assert "Burt Podbere" in live, key
        assert "Recent Highlights" in live, key
        # The stored snapshots' whitespace defects are gone in live.
        assert "million ," not in live, key
        assert "billion ," not in live, key
        assert "gr oss" not in live, key
        assert "Equivalen ts" not in live, key


def test_sibling_quarters_keep_live_shape():
    for key, headline, n in SIBLING_QUARTERS:
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert len(lines) == n, key
