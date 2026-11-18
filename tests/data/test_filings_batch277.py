"""Batch 277 regression tests.

EBAY's releases for 5 quarters open headline -> teaser bullets ->
dateline -> CEO/CFO quotes -> "Business Highlights" -> "Impact" ->
"Financial Highlights", and the stored rows are stale snapshots of
the seed-era extractor: headline + the "Business Highlights"
narrative section only (eBay Live / anniversary / Depop / collectibles
bullets), with no financial-figure bullet and no quote at all. The
current extractor anchors on the "Financial Highlights" section:
headline + 7 figure bullets (Revenue, GMV, GAAP and non-GAAP net
income / EPS, operating margins, operating + free cash flow, capital
returns) -- 14 bullets for 2025-12-31, which adds the "Full Year 2025
Financial Highlights" block.

The four EBAY siblings (2024-09-30, 2024-12-31, 2025-03-31,
2026-09-30) already store the live shape (stored == live), which is
the consistency cross-check for the re-sync. The older three store
headline + quotes + financial bullets + the Business Highlights
section; the 2026-09-30 sibling stores headline + 7 figure bullets
only, i.e. the same shape the 5 re-synced rows take.

The design question is the one settled in batches 266-270 (BNY, BKR,
AMZN, COR, V), 273 (AXON) and 276 (CEG): the highlights card's job
is the quarter's key financial figures. Live carries every one of
them; the stored rows lack them entirely. The stored rows' unique
figures are advertising revenue ($482M total / $455M first-party,
2025-06-30), cumulative / charity amounts ($1B+ Seller Capital since
2021, $49M eBay for Charity, 2025-09-30), and single collectible
sale prices ($16.5M Pikachu card, 2026-03-31; $4.3M Jordan card and
$2.8M Gretzky jersey, 2026-06-30); 2025-12-31's stored row has no
$/% figure at all. No stored-only figure is an EPS, revenue, GMV,
margin, cash-flow, or capital-return figure.

No extractor change in batch 277: the re-sync is a DB repair.

Open, noted not fixed: the 5 re-synced releases' CEO/CFO quotes are
in the exhibit (after the dateline paragraph) but neither stored nor
live serves them -- the extractor's section anchor does not pick up
quotes that sit between the dateline and the Business Highlights
heading (the older EBAY quarters do serve quotes). The AZO x5 and
MU x5 groups were probed in batch 276 and are NOT re-synced here:
AZO's stored rows are shorter than live (truncated ledes vs the
fuller live lede -- a line-matching question); MU's first-loss line
is the "Quarterly Financial Results" heading with small length
deltas. No test is pinned for them here.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# key, headline, first figure bullet (prefix), live non-empty lines,
# stored narrative fragment that must NOT appear in live.
FINANCIAL_QUARTERS = (
    (
        "EBAY_2025-06-30",
        "eBay Inc. Reports Second Quarter 2025 Results",
        "\u2022 Revenue was $2.7 billion, up 6%",
        8,
        "eBay formally launched eBay Live in the U.K.",
    ),
    (
        "EBAY_2025-09-30",
        "eBay Inc. Reports Third Quarter 2025 Results",
        "\u2022 Revenue was $2.8 billion, up 9%",
        8,
        "eBay celebrated its 30th anniversary",
    ),
    (
        "EBAY_2025-12-31",
        "eBay Inc. Reports Fourth Quarter and Full Year 2025 Results",
        "\u2022 Revenue was $3.0 billion, up 15%",
        16,
        "The company expanded eBay Live, its interactive live-stream shopping experience, to Germany and Australia",
    ),
    (
        "EBAY_2026-03-31",
        "eBay Inc. Reports First Quarter 2026 Results",
        "\u2022 Revenue was $3.1 billion, up 19%",
        8,
        "eBay announced a definitive agreement to acquire Depop",
    ),
    (
        "EBAY_2026-06-30",
        "eBay Inc. Reports Second Quarter 2026 Results",
        "\u2022 Revenue was $3.1 billion, up 15%",
        8,
        "On July 30, 2026, eBay closed its acquisition of Depop Limited",
    ),
)

# The siblings already store the live shape: headline, first line
# (a CEO quote for the older three, the first figure bullet for
# 2026-09-30), live non-empty lines. The older three store headline
# + quotes + financial bullets + the Business Highlights section.
SIBLING_QUARTERS = (
    (
        "EBAY_2024-09-30",
        "eBay Inc. Reports Third Quarter 2024 Results",
        "\u201cWe achieved another quarter of positive GMV growth",
        19,
        True,
    ),
    (
        "EBAY_2024-12-31",
        "eBay Inc. Reports Fourth Quarter and Full Year 2024 Results",
        "\u201ceBay achieved three consecutive quarters of GMV growth",
        18,
        False,
    ),
    (
        "EBAY_2025-03-31",
        "eBay Inc. Reports First Quarter 2025 Results",
        "\u201ceBay\u2019s first quarter results were ahead of expectations",
        19,
        True,
    ),
    (
        "EBAY_2026-09-30",
        "eBay Inc. Reports Third Quarter 2026 Results",
        "\u2022 Revenue was $3.2 billion, up 14%",
        8,
        False,
    ),
)


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def test_financial_quarters_serve_figure_bullets():
    for key, headline, first_bullet, n_lines, stored_frag in FINANCIAL_QUARTERS:
        live = _live(key)
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert lines[1].startswith(first_bullet), key
        assert len(lines) == n_lines, key
        bullets = [ln for ln in lines if ln.startswith("\u2022")]
        assert len(bullets) >= 7, key
        assert sum(1 for b in bullets if "$" in b) >= 2, key
        assert "per diluted share" in live, key
        assert stored_frag not in live, key
        assert "Business Highlights" not in live, key


def test_sibling_quarters_keep_live_shape():
    for key, headline, first_line, n_lines, has_business in SIBLING_QUARTERS:
        live = _live(key)
        lines = _live_lines(key)
        assert lines[0] == headline, key
        assert lines[1].startswith(first_line), key
        assert len(lines) == n_lines, key
        assert "per diluted share" in live, key
        assert ("Business Highlights" in live) == has_business, key
