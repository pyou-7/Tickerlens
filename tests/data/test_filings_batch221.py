"""Batch 221: live pins for the CSCO contact-name repair.

The stored highlights rows for CSCO 2026-01-24 / 2026-04-25 / 2026-07-25
open with the bare contact-names line "Robyn Blum Sami Badri" — a
pre-batch-179 extraction that predates the contact-block skip. The
current extractor already drops the block (synthetic pin:
test_contact_block_names_before_phones_are_skipped); these pins run it
against the three real cached exhibits, so a regression in the
contact-block lookahead fails here first. The stored rows are the
narrative section while live extraction serves the bullet highlights,
so the repair is line-level (strip the names line), not a swap.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

EXPECTED_HEADLINE = {
    "2026-01-24": "CISCO REPORTS SECOND QUARTER EARNINGS",
    "2026-04-25": "CISCO REPORTS THIRD QUARTER EARNINGS",
    "2026-07-25": "CISCO REPORTS FOURTH QUARTER AND FISCAL YEAR 2026 EARNINGS",
}


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def test_csco_real_exhibits_drop_contact_names() -> None:
    for pe, headline in EXPECTED_HEADLINE.items():
        hl = extract_press_release_highlights(_read(f"CSCO_{pe}.html"))
        assert hl is not None
        assert "Robyn Blum" not in hl
        assert "Sami Badri" not in hl
        assert "cisco.com" not in hl
        assert "408" not in hl
        assert hl.split("\n\n")[0] == headline


def test_csco_real_exhibits_serve_bullet_highlights() -> None:
    # Live extraction serves headline + bullet highlights, not the
    # narrative section the stored rows carry — which is why the
    # batch-221 repair strips the names line instead of swapping.
    for pe in EXPECTED_HEADLINE:
        hl = extract_press_release_highlights(_read(f"CSCO_{pe}.html"))
        assert hl is not None
        assert "\n• " in hl or hl.startswith("CISCO REPORTS")
        assert "Revenue -- Total revenue was $" not in hl
