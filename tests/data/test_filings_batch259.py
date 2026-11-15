"""Batch 259 regression tests.

CHD's lede budget: live served only 4 of CHD's 10 summary bullets.
The release's own summary is a bullet run under two section labels
("2024 First Quarter Results" / "2024 Full Year Outlook"), and the
6-line lede budget is shared with the two caps sub-headlines, so the
run was cut after 4 bullets and the whole FY-outlook group was lost.
The fix: a bullet-list lede keeps collecting while the next line is
a bullet and the last collected line is one too, up to the 12-line
section cap. A non-bullet past the budget still falls through to the
finish logic, so prose ledes keep the hard 6-line cap.

Guard (found by the full-cache blast): a colon-ended bullet is a
sub-list opener, not a complete item ("• For the nine months ended
March 31, 2025:", "• ... Expand Profit Recovery and Growth Plan
to:") — its items sit on ◦ lines the loop does not recognize as
bullets, so collecting the opener strands the lede at an unfinished
item and the overrun path then pulls the sub-list plus the next
section heading (EL 2025-03-31 served "BEAUTY GAINS AND
OPERATIONAL HIGHLIGHTS3" as a highlight; ABT/EL Q4 served the
opener dangling with nothing after it). The opener is refused, so
the bullet-break ends the lede cleanly instead.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_press_release_highlights

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _live(ticker_period: str) -> str:
    with open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ) as fh:
        return extract_press_release_highlights(fh.read()) or ""


def _html(lines):
    return "<html><body>" + "".join(f"<p>{ln}</p>" for ln in lines) + "</body></html>"


# Long trailing filler so synthetic docs clear _MIN_RELEASE_CHARS
# (800). It sits after every line the lede could serve, so it never
# reaches the extraction: the budget, the bullet-break, or the
# colon-opener break all stop the loop before it.
_FILLER = (
    "About Acme Corp: Acme Corp is a leading global provider of "
    "household and personal care products, serving consumers in more "
    "than one hundred countries with a portfolio of trusted brands "
    "spanning laundry, cleaning, oral care, skin care and pet care, "
    "and the Company remains committed to sustainable growth, "
    "operational excellence and returning capital to shareholders "
    "through dividends and share repurchases over the long term."
)


# --- CHD-shaped synthetic: headline + 2 caps sub-headlines + labels + 10 bullets ---
_CHD_LINES = [
    "ACME CORP REPORTS FIRST QUARTER 2026 RESULTS",
    "Q1 NET SALES, GROSS MARGIN AND EPS EXCEED OUTLOOK",
    "RAISES OUTLOOK FOR FULL YEAR GROSS MARGIN AND EPS",
    "2026 First Quarter Results",
    "2026 Full Year Outlook",
    "• Net Sales +5.1%: Domestic +4.3%, Int’l +10.6%, SPD +1.0%",
    "• Organic Sales +5.2%: Domestic +4.3%, Int’l +8.8%, SPD +7.2%",
    "• Gross Margin +220 bps",
    "• Reported EPS $0.93, Adjusted EPS $0.96",
    "• Cash from Operations of $263 million",
    "• Net Sales +4% to 5%; Organic Sales +4% to 5%",
    "• Gross Margin expansion raised to +75 bps",
    "• Reported EPS +9.5-10.5%",
    "• Adjusted EPS raised to +8-9%",
    "• Cash from Operations ~$1.05 billion",
]


def test_bullet_run_serves_all_ten_bullets():
    out = extract_press_release_highlights(_html([*_CHD_LINES, _FILLER])) or ""
    for bullet in (
        "Net Sales +5.1%",
        "Organic Sales +5.2%",
        "Gross Margin +220 bps",
        "Reported EPS $0.93",
        "Cash from Operations of $263 million",
        "Net Sales +4% to 5%",
        "Gross Margin expansion raised to +75 bps",
        "Reported EPS +9.5-10.5%",
        "Adjusted EPS raised to +8-9%",
        "Cash from Operations ~$1.05 billion",
    ):
        assert bullet in out, f"missing bullet: {bullet}"
    assert out.count("•") == 10


def test_bullet_run_capped_at_twelve_content_lines():
    # 2 sub-headlines + 14 bullets: the run stops at 12 total content
    # lines, so bullets 11-14 are never served. (Bullets directly
    # after the headline take the leading-bullet-block path with its
    # own 18-line cap instead, so the sub-headlines + labels mirror
    # the CHD shape that goes through the lede.)
    lines = [
        "ACME CORP REPORTS FIRST QUARTER 2026 RESULTS",
        "Q1 NET SALES, GROSS MARGIN AND EPS EXCEED OUTLOOK",
        "RAISES OUTLOOK FOR FULL YEAR GROSS MARGIN AND EPS",
        "2026 First Quarter Results",
        "2026 Full Year Outlook",
    ] + [
        f"• Metric {n:02d} grew 5% year over year to ${n}.0 billion."
        for n in range(1, 15)
    ]
    out = extract_press_release_highlights(_html([*lines, _FILLER])) or ""
    assert "Metric 10 grew" in out
    assert "Metric 11 grew" not in out
    assert "Metric 14 grew" not in out
    assert out.count("•") == 10


def test_bullet_run_stops_at_prose():
    # A dateline paragraph after the run is body prose, not a
    # continuation: the run ends and the prose is never served.
    lines = [
        "ACME CORP REPORTS FIRST QUARTER 2026 RESULTS",
        "Q1 NET SALES, GROSS MARGIN AND EPS EXCEED OUTLOOK",
        "RAISES OUTLOOK FOR FULL YEAR GROSS MARGIN AND EPS",
        "• Net Sales +5.1%: Domestic +4.3%, Int’l +10.6%, SPD +1.0%",
        "• Organic Sales +5.2%: Domestic +4.3%, Int’l +8.8%, SPD +7.2%",
        "• Gross Margin +220 bps",
        "• Reported EPS $0.93, Adjusted EPS $0.96",
        "• Cash from Operations of $263 million",
        "• Net Sales +4% to 5%; Organic Sales +4% to 5%",
        "EWING, NJ, May 2, 2026 – Acme Corp today announced the Company "
        "exceeded its outlook with stronger than expected sales growth.",
        "Chief Executive Officer Jane Smith commented, “The Company is "
        "performing extremely well with all three divisions delivering "
        "strong growth.”",
    ]
    out = extract_press_release_highlights(_html([*lines, _FILLER])) or ""
    assert "Cash from Operations of $263 million" in out
    assert "Net Sales +4% to 5%" in out
    assert "exceeded its outlook with stronger than expected" not in out
    assert "performing extremely well" not in out


def test_prose_lede_keeps_six_line_cap():
    # No bullets at all: the hard 6-line cap is unchanged — the 7th
    # prose line is never served.
    lines = [
        "ACME CORP REPORTS FIRST QUARTER 2026 RESULTS",
        "Ewing, NJ, May 2, 2026 – Acme Corp today reported first quarter results.",
        "Net sales increased 5 percent to $1.2 billion in the first quarter.",
        "Gross margin expanded 220 basis points to 45.7 percent.",
        "Reported earnings per share were $0.93 in the first quarter.",
        "Cash from operations was $263 million in the first quarter.",
        "The Company repurchased $100 million of common stock in the quarter.",
        "The Company raised its full year outlook for sales and earnings.",
    ]
    out = extract_press_release_highlights(_html([*lines, _FILLER])) or ""
    assert "repurchased $100 million" in out
    assert "raised its full year outlook" not in out


def test_colon_opener_refused():
    # EL-shaped: the first line past the budget is a sub-list opener.
    # The opener, its ◦ sub-bullets and the next section heading are
    # all refused — the lede ends at the last complete bullet.
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
    assert "For the nine months ended" not in out
    assert "Net cash flows provided" not in out
    assert "BEAUTY GAINS" not in out


def test_chd_q1_2024_real_exhibit_serves_ten_bullets():
    out = _live("CHD_2024-03-31")
    assert "Cash from Operations of $263 million" in out
    assert "Net Sales +4% to 5%; Organic Sales +4% to 5%" in out
    assert "Gross Margin expansion raised to +75 bps" in out
    assert "Adjusted EPS raised to +8-9%" in out
    assert "Cash from Operations ~$1.05 billion" in out
    assert out.count("•") == 10


def test_chd_q3_2025_real_exhibit_serves_ten_bullets():
    out = _live("CHD_2025-09-30")
    assert out.count("•") == 10


def test_el_q3_2025_real_exhibit_no_heading_leak():
    out = _live("EL_2025-03-31")
    assert "Effective tax rate was 34.0%" in out
    assert "Diluted net earnings per common share decreased to $.44" in out
    assert "For the nine months ended" not in out
    assert "BEAUTY GAINS" not in out


def test_abt_q4_2025_real_exhibit_no_dangling_opener():
    out = _live("ABT_2025-12-31")
    assert "two significant regulatory approvals:" not in out
