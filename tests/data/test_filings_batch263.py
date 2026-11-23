"""Batch 263 regression tests.

Batch 262 made the batch-259 premise false: ◦ (U+25E6) joined
_BULLET_LEAD_RE, so a colon-ended sub-list opener's items ARE bullets
now. Two paths change:

(1) Lede extension: a colon-ended bullet is collected exactly when
its items are bullets (the next content line is a bullet start) and
there is room for at least one child (content < 11 — collecting the
opener at the cap strands it dangling, ABT Q4 FY2025). A table-intro
opener ("Net earnings includes:") is still refused: its continuation
is table rows, not bullets.

(2) Leading-bullet-block cap: the batch-259 bullet-run extension is
mirrored — while the next content line is a bullet and the last
collected line is one too, collection continues to the 18-line bound
(DIS Q4 FY2025: the run hits 14 exactly on the "• Sports: ... For
Q4:" parent, whose ◦ children the completion allowance refuses).

Plus the overrun heading guard: the overrun path never pulls a
section heading as a "continuation" (EL 2025-03-31 served "BEAUTY
GAINS AND OPERATIONAL HIGHLIGHTS3" because the CEO quote's opening
“ never closes, so the terminated-break is suppressed). A repeated
page header inside a wrapped item is the exception: AMGN
2023-12-31's ◦ bullet wraps across the repeated headline, and the
line after the header continues the bullet's sentence — the header
is skipped transparently instead of breaking the lede.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_lede_caps_heading,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _html(lines):
    return "<html><body>" + "".join(f"<p>{ln}</p>" for ln in lines) + "</body></html>"


_FILLER = (
    "About Acme Corp: Acme Corp is a leading global provider of "
    "household and personal care products, serving consumers in more "
    "than one hundred countries with a portfolio of trusted brands "
    "spanning laundry, cleaning, oral care, skin care and pet care, "
    "and the Company remains committed to sustainable growth, "
    "operational excellence and returning capital to shareholders "
    "through dividends and share repurchases over the long term."
)


def test_is_lede_caps_heading():
    assert _is_lede_caps_heading("BEAUTY GAINS AND OPERATIONAL HIGHLIGHTS3")
    assert _is_lede_caps_heading("GUIDANCE AND OUTLOOK")
    assert _is_lede_caps_heading("FOURTH-QUARTER BUSINESS OVERVIEW")
    assert not _is_lede_caps_heading("Net sales decreased 10% to $3.6 billion.")
    assert not _is_lede_caps_heading("Revenue of $5.6 billion increased 6%")
    assert not _is_lede_caps_heading("The Company paid dividends of $492 million.")
    assert not _is_lede_caps_heading("• Net sales decreased 10%.")
    assert not _is_lede_caps_heading("")
    assert not _is_lede_caps_heading("A" * 91)


def test_colon_opener_with_bullet_children_served():
    # EL-shaped synthetic: the opener's items are ◦ bullets, so the
    # opener and its sub-list are served; the section heading after
    # the sub-list still ends the lede (overrun heading guard).
    lines = [
        "ACME CORP REPORTS FISCAL 2026 THIRD QUARTER RESULTS",
        "New York, May 1, 2026 - Acme Corp today reported its financial "
        "results for the third quarter ended March 31, 2026.",
        "Jane Smith, President and Chief Executive Officer, said, “In the "
        "third quarter, we delivered our organic sales outlook.”",
        "“Our global business showed sequential improvement across all "
        "regions and channels during the third quarter.”",
        "• Net sales decreased 10% to $3.6 billion.",
        "• Gross margin expanded 310 basis points, to 75.0%.",
        "• Operating margin declined to 8.6% from 13.5%.",
        "• For the nine months ended March 31, 2026:",
        "◦ Net cash flows provided by operating activities decreased.",
        "◦ Capital expenditures decreased to $395 million.",
        "BEAUTY GAINS AND OPERATIONAL HIGHLIGHTS3",
    ]
    out = extract_press_release_highlights(_html([*lines, _FILLER])) or ""
    assert "Operating margin declined to 8.6%" in out
    assert "For the nine months ended March 31, 2026:" in out
    assert "Net cash flows provided by operating activities decreased." in out
    assert "Capital expenditures decreased to $395 million." in out
    assert "BEAUTY GAINS" not in out


def test_colon_opener_with_table_children_refused():
    # A table-intro opener is still refused: its continuation is
    # table label lines, not bullets, so the lookahead fails and the
    # bullet-break below ends the lede cleanly instead.
    lines = [
        "ACME CORP REPORTS FISCAL 2026 THIRD QUARTER RESULTS",
        "New York, May 1, 2026 - Acme Corp today reported its financial "
        "results for the third quarter ended March 31, 2026.",
        "Jane Smith, President and Chief Executive Officer, said, “In the "
        "third quarter, we delivered our organic sales outlook.”",
        "“Our global business showed sequential improvement across all "
        "regions and channels during the third quarter.”",
        "• Net sales decreased 10% to $3.6 billion.",
        "• Gross margin expanded 310 basis points, to 75.0%.",
        "• Operating margin declined to 8.6% from 13.5%.",
        "• Net earnings includes:",
        "Common stock $ 1,234 $ 1,100",
        "Preferred stock $ 456 $ 400",
    ]
    out = extract_press_release_highlights(_html([*lines, _FILLER])) or ""
    assert "Operating margin declined to 8.6%" in out
    assert "Net earnings includes:" not in out
    assert "Common stock $ 1,234" not in out


def test_el_q3_2025_real_exhibit_opener_children_served():
    out = _live("EL_2025-03-31")
    assert "Effective tax rate was 34.0%" in out
    assert "Diluted net earnings per common share decreased to $.44" in out
    assert "For the nine months ended March 31, 2025:" in out
    assert "Net cash flows provided by operating activities decreased" in out
    assert "Capital expenditures decreased to $395 million" in out
    assert "The Company paid dividends of $492 million." in out
    assert "BEAUTY GAINS" not in out


def test_el_q4_2025_real_exhibit_opener_children_served():
    out = _live("EL_2024-12-31")
    assert "Fuel sustainable growth through bold efficiencies:" in out
    assert "Address the impact of further volume deleverage" in out
    assert "Reimagine the way we work:" in out


def test_bsx_q3_2023_real_exhibit_region_opener_served():
    out = _live("BSX_2023-09-30")
    assert "Achieved the following net sales growth in each region" in out
    assert "United States (U.S.) : 8.5 percent reported and operational" in out
    assert "Latin America and Canada (LACA): 22.0 percent reported" in out


def test_cof_q3_2023_real_exhibit_provision_opener_served():
    # The first provision opener + marketing child were already served
    # pre-budget; the second opener group (charge-offs children + the
    # net-interest-margin bullet) is what batch 263 adds.
    out = _live("COF_2023-09-30")
    assert "Provision for credit losses decreased $206 million" in out
    assert "Net charge-offs of $2.0 billion." in out
    assert "$322 million loan reserve build." in out
    assert "Net interest margin of 6.69 percent" in out


def test_dis_q4_2025_real_exhibit_sports_experiences_served():
    out = _live("DIS_2025-09-27")
    assert "Sports: Q4 segment operating income of $911 million" in out
    assert "Domestic ESPN operating income declined 3%" in out
    assert "Domestic advertising revenue increased 8%" in out
    assert "Experiences: Record full year segment operating income" in out
    assert "International Parks & Experiences operating income grew 25%" in out
    # Batch 264: the Experiences sub-list completes — the second ◦
    # child ("Domestic Parks ...") is served too, so ◦ goes 9 -> 10.
    assert "Domestic Parks & Experiences operating income grew 9%" in out
    assert "Guidance and Outlook" not in out
    assert out.count("◦") == 10
    assert out.count("•") == 8


def test_dis_q3_2025_real_exhibit_sports_child_served():
    out = _live("DIS_2025-06-28")
    assert "Domestic ESPN operating income declined 7%" in out
    assert "Experiences: Segment operating income of $2.5 billion" in out


def test_dis_q4_2024_real_exhibit_fiscal_year_opener_served():
    out = _live("DIS_2024-09-28")
    assert "Fiscal 2025:" in out
    assert "High-single digit adjusted EPS(1) growth" in out
    assert "Target dividend growth that tracks our earnings growth" in out


def test_amgn_q4_2023_real_exhibit_repeated_header_skipped():
    # The ◦ bullet wraps across the repeated page headline: the header
    # is skipped transparently and the bullet's sentence completes.
    # The headline itself is still the output's first line, so it
    # appears exactly once — the mid-bullet repeat is gone.
    out = _live("AMGN_2023-12-31")
    assert out.count("AMGEN REPORTS FOURTH QUARTER AND FULL YEAR 2023") == 1
    assert "For the fourth quarter, GAAP operating income decreased" in out
    assert "the full year, GAAP operating income decreased from $9.6 billion" in out


def test_fcx_q1_2026_real_exhibit_opener_served():
    out = _live("FCX_2026-03-31")
    assert "Average unit net cash costs were $1.91 per pound of copper" in out
    assert "Operating cash flows totaled $1.5 billion" in out
