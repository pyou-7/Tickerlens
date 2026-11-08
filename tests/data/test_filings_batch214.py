"""Batch 214: press-release highlights 4000-char cap raised to 9000,
with the shareholder-letter fallback kept at 4000 and a safe-harbor cut.

The batch-213 carry-forward class, applied to highlights: survey over
all 1,699 cached exhibits (scripts/batch214_survey.py): 54 sections
exceed 4000 chars uncapped, max genuine 8797 (CART 2023-09-30, bullets
+ guidance + footnotes ending at its natural close), p99 5791, median
1250 — and 114 of 2489 stored rows end with the truncation "…". The
section/lede line budgets are the runaway bound; the char cap only
needs to cover the longest genuine section, so the default moves
4000 -> 9000.

Two carve-outs, both blast-verified over the full cache:
  * Shareholder letters falling through to the standard path keep the
    old 4000 cap: their "highlights" is the letter body (COIN
    2023-12-31 runs 18,949 chars uncapped), so the cap is the only
    bound and raising it would only serve more letter prose.
  * A "Cautionary Note on Forward-Looking Statements" heading cuts
    the assembled result there (Ford Q1 2025: the heading sits
    mid-line in a flattened footnote bullet and 1,894 chars of risk
    list follow it). The exact heading is matched — a bare
    "Forward-Looking Statements" line appears in 519 cached exhibits
    and genuine outlook prose mentions forward-looking figures.
"""

import os

from tickerlens.data.filings import (
    _clean_highlights_result,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _long_bullet_lines(n: int, chars_per_line: int) -> list[str]:
    """Genuine-looking financial highlight bullets of ~chars_per_line."""
    lines = ["ACME REPORTS FOURTH QUARTER 2025 RESULTS", "Highlights"]
    for k in range(n):
        sentence = (
            f"• Revenue of ${k + 10}.5 billion grew {k + 4}% year over year, "
            f"with adjusted diluted earnings per share of ${k + 2}.10, "
            f"reflecting continued momentum in the core business and "
            f"disciplined cost management across all operating segments "
            f"during the fiscal year and into the next period."
        )
        while len(sentence) < chars_per_line:
            sentence += " Demand remained steady across every region."
        lines.append(sentence[:chars_per_line].rsplit(" ", 1)[0] + ".")
    return lines


# --- synthetic: the cap no longer truncates a genuine long section ---


def test_default_cap_keeps_5000_char_highlights_whole():
    html = _contact_release_html(*_long_bullet_lines(11, 450))
    result = extract_press_release_highlights(html)
    assert result is not None
    assert len(result) > 4000
    assert not result.endswith("…")
    assert "Revenue of $20.5 billion" in result


def test_explicit_4000_cap_still_truncates():
    # The parameter is honored: an explicit 4000 cap reproduces the
    # old stored truncation on the same section.
    html = _contact_release_html(*_long_bullet_lines(11, 450))
    result = extract_press_release_highlights(html, max_chars=4000)
    assert result is not None
    assert result.endswith("…")
    assert len(result) <= 4001
    whole = extract_press_release_highlights(html)
    assert whole is not None
    assert whole.startswith(result[:-1].rstrip())


# --- safe-harbor cut: unit level ---


def test_clean_result_cuts_at_cautionary_note_heading():
    body = (
        "ACME REPORTS RESULTS\n\n"
        "• Revenue grew 10% year over year to $5.5 billion, with adjusted "
        "diluted earnings per share of $2.10, reflecting continued momentum "
        "in the core business and disciplined cost management across all "
        "operating segments during the fiscal year.\n\n"
        "The following applies to the information throughout this release: "
        "Cautionary Note on Forward-Looking Statements Statements herein "
        "may constitute forward-looking statements.\n\n"
        "• Risk one: the business could be affected by defects.\n\n"
        "• Risk two: suppliers could fail to deliver on schedule."
    )
    cleaned = _clean_highlights_result(body)
    assert "Cautionary Note" not in cleaned
    assert "Risk one" not in cleaned
    assert "Revenue grew 10%" in cleaned
    assert cleaned.rstrip().endswith("release:")


def test_clean_result_without_cautionary_note_is_untouched():
    body = (
        "ACME REPORTS RESULTS\n\n"
        "• Revenue grew 10% year over year.\n\n"
        "Our forward-looking investment in the core business continues."
    )
    assert _clean_highlights_result(body) == body


def test_clean_result_cut_keeps_short_result_whole():
    # The batch-153 floor rule: a cut that would leave <200 chars is
    # not kept — a wart is better than dropping the row.
    body = "ACME REPORTS RESULTS\n\nCautionary Note on Forward-Looking Statements risk."
    assert _clean_highlights_result(body) == body


# --- real-exhibit pins ---


def test_cart_q3_2023_served_whole_at_8797_chars():
    result = extract_press_release_highlights(_load("CART_2023-09-30.html"))
    assert result is not None
    assert len(result) == 8797
    assert not result.endswith("…")
    assert result.startswith("• GTV of $7,494 million")
    assert "Includes cash and cash equivalents" in result


def test_eqix_q2_2024_served_whole_at_7001_chars():
    result = extract_press_release_highlights(_load("EQIX_2024-06-30.html"))
    assert result is not None
    assert len(result) == 7001
    assert not result.endswith("…")


def test_ford_q1_2025_cut_before_safe_harbor_risk_list():
    result = extract_press_release_highlights(_load("F_2025-03-31.html"))
    assert result is not None
    assert len(result) == 5280
    assert not result.endswith("…")
    assert "Cautionary Note" not in result
    assert "long-term success depends" not in result
    assert "suspends financial guidance" in result
    assert result.rstrip().endswith("wholesale unit volumes.")


def test_coinbase_letter_fallback_stays_at_4000_cap():
    # Shareholder letter falling through to the standard path: the
    # 9000 default must NOT extend the letter-body runaway.
    result = extract_press_release_highlights(_load("COIN_2023-12-31.html"))
    assert result is not None
    assert len(result) == 3998
    assert result.endswith("…")


def test_affirm_letter_fallback_stays_at_4000_cap():
    result = extract_press_release_highlights(_load("AFRM_2024-06-30.html"))
    assert result is not None
    assert len(result) == 3997
    assert result.endswith("…")


def test_ed_q4_2025_genuine_long_section_served_whole():
    result = extract_press_release_highlights(_load("ED_2025-12-31.html"))
    assert result is not None
    assert len(result) == 7168
    assert not result.endswith("…")
    assert "adjusted earnings per share" in result
