"""Batch 278 regression tests.

Micron's releases for 5 quarters open with a headline + 4 figure
bullets (Revenue, GAAP net income, non-GAAP net income, operating
cash flow -- 8 bullets for the Q4 rows, which add the full-year set),
followed in the exhibit by the "Quarterly Financial Results" summary
table. The stored rows are stale snapshots of the seed-era extractor:
the same bullets with no space after the bullet glyph ("•Revenue of
...") plus the table's header lines trailing the bullets:

    Quarterly Financial Results
    (in millions, except per share amounts) GAAP(1)
    Non-GAAP(2)                      (Q1-Q3 rows only)

The current extractor serves the clean shape: "• " bullets, no table
residue. The residue lines carry no $/% figure, and the bullet bodies
are identical modulo the glyph spacing, so the re-sync loses no
figure. The 4 newer MU siblings (2025-11-27, 2026-02-26, 2026-05-28,
2026-09-03) already store the live shape (stored == live under
norm), which is the consistency cross-check for the re-sync.

No extractor change in batch 278: the re-sync is a DB repair. The
3 oldest cached MU releases (2023-11-30, 2024-02-29, 2024-05-30)
have no stored highlights row at all.

Open, noted not fixed: the AZO x5 group (stored rows shorter than
live -- a line-matching question, needs its own probe of the dateline
paragraph). No test is pinned for it here.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# key, headline, first figure bullet (prefix), live non-empty lines,
# bullet count.
RESYNCED_QUARTERS = (
    (
        "MU_2024-08-29",
        "MICRON TECHNOLOGY, INC. REPORTS RESULTS FOR THE FOURTH QUARTER AND FULL YEAR OF FISCAL 2024",
        "\u2022 Revenue of $7.75 billion versus $6.81 billion",
        11,
        8,
    ),
    (
        "MU_2024-11-28",
        "MICRON TECHNOLOGY, INC. REPORTS RESULTS FOR THE FIRST QUARTER OF FISCAL 2025",
        "\u2022 Revenue of $8.71 billion versus $7.75 billion",
        6,
        4,
    ),
    (
        "MU_2025-02-27",
        "MICRON TECHNOLOGY, INC. REPORTS RESULTS FOR THE SECOND QUARTER OF FISCAL 2025",
        "\u2022 Revenue of $8.05 billion versus $8.71 billion",
        6,
        4,
    ),
    (
        "MU_2025-05-29",
        "MICRON TECHNOLOGY, INC. REPORTS RESULTS FOR THE THIRD QUARTER OF FISCAL 2025",
        "\u2022 Revenue of $9.30 billion versus $8.05 billion",
        6,
        4,
    ),
    (
        "MU_2025-08-28",
        "MICRON TECHNOLOGY, INC. REPORTS RESULTS FOR THE FOURTH QUARTER AND FULL YEAR OF FISCAL 2025",
        "\u2022 Revenue of $11.32 billion versus $9.30 billion",
        11,
        8,
    ),
)

# Siblings already store the live shape: headline, first figure bullet,
# live non-empty lines, bullet count.
SIBLING_QUARTERS = (
    (
        "MU_2025-11-27",
        "MICRON TECHNOLOGY, INC. REPORTS RESULTS FOR THE FIRST QUARTER OF FISCAL 2026",
        "\u2022 Revenue of $13.64 billion versus $11.32 billion",
        6,
        4,
    ),
    (
        "MU_2026-02-26",
        "MICRON TECHNOLOGY, INC. REPORTS RESULTS FOR THE SECOND QUARTER OF FISCAL 2026",
        "\u2022 Revenue of $23.86 billion versus $13.64 billion",
        6,
        4,
    ),
    (
        "MU_2026-05-28",
        "MICRON TECHNOLOGY, INC. REPORTS RECORD RESULTS FOR THE THIRD QUARTER OF FISCAL 2026",
        "\u2022 Revenue of $41.46 billion versus $23.86 billion",
        6,
        4,
    ),
    (
        "MU_2026-09-03",
        "MICRON TECHNOLOGY, INC. REPORTS RECORD FISCAL",
        "\u2022 Revenue of $54.23 billion versus $41.46 billion",
        11,
        8,
    ),
)

# Table-header residue the seed-era extractor captured and live drops.
RESIDUE = (
    "Quarterly Financial Results",
    "(in millions, except per share amounts)",
)


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _live_lines(ticker_period: str) -> list[str]:
    return [ln for ln in _live(ticker_period).split("\n") if ln.strip()]


def _check_shape(key, headline, first_bullet, n_lines, n_bullets):
    live = _live(key)
    lines = _live_lines(key)
    assert lines[0] == headline, key
    assert lines[1].startswith(first_bullet), key
    assert len(lines) == n_lines, key
    bullets = [ln for ln in lines if ln.startswith("\u2022")]
    assert len(bullets) == n_bullets, key
    assert all(b.startswith("\u2022 ") for b in bullets), key
    assert "per diluted share" in live, key
    for residue in RESIDUE:
        assert residue not in live, key


def test_resynced_quarters_serve_clean_bullets():
    for key, headline, first_bullet, n_lines, n_bullets in RESYNCED_QUARTERS:
        _check_shape(key, headline, first_bullet, n_lines, n_bullets)


def test_sibling_quarters_keep_live_shape():
    for key, headline, first_bullet, n_lines, n_bullets in SIBLING_QUARTERS:
        _check_shape(key, headline, first_bullet, n_lines, n_bullets)
