"""Batch 241: highlights sweep gate S3 — the 345 SKIP-loss rows from
the batch 231/232 source-verified stale-row sweep.

Root causes, all in the sweep comparison / gate (scripts/
batch231_repair.py norm, scripts/batch241_repair.py gate S3), not
the extractor — the live extraction was already right; only the
stored rows were stale or the census was wrong:

- 103 rows were never stale in substance: stored and live differ
  only in flattening spacing. norm() canonicalized "•" only; the
  seed-era rows also carry "◦"/"▪"/"■"/"●"/"–" bullets without the
  space ("◦New AMD ..." vs "◦ New AMD ..."), trademark spacing
  ("Apple ®" vs "Apple®"), and a footnote key spaced off its comma
  or period ("$1.64, 1 up" vs "$1.64,1 up"; "basis. 1" vs
  "basis.1"). The norm extension reclassifies those rows as
  already-new (B), no write.
- 55 rows re-sync under gate S3: the stored row carries chrome the
  live extraction drops by design — a dateline sentence (AAL/DIS/
  CHTR/CVS), a period subheading (ALL/GILD/CL "Third Quarter 2025
  Results"), a table-section header (AVGO "Net revenue by segment"),
  a section subheading over kept content (CVS "CEO Commentary") —
  plus a dateline-presence exemption when live carries no dateline
  at all. Every other gate-S condition is unchanged, and the repair
  is DB-verified 55/55 byte-identical to the live extraction.

The gate pins below use synthetic stored/live pairs modeled line
for line on the real rows (the DB rows are already re-synced, so
the pre-repair text is reconstructed from the probe diffs); the
norm pins use the real AAPL/AMD line strings verbatim.
"""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def _load_script(name: str):
    path = REPO / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sweep = _load_script("batch231_repair")
rep = _load_script("batch241_repair")
norm = sweep.norm


# --- norm() canonicalization -------------------------------------------

def test_norm_bullet_glyph_spacing():
    for stored, live in [
        ("◦New AMD EPYC 9005 Series processors.", "◦ New AMD EPYC 9005 Series processors."),
        ("▪Strong performance in the first half.", "▪ Strong performance in the first half."),
        ("■Strong General Insurance net premiums.", "■ Strong General Insurance net premiums."),
        ("●Net cash from operating activities was $701 million.", "● Net cash from operating activities was $701 million."),
        ("–Sales of $10.4 billion driven by growth.", "– Sales of $10.4 billion driven by growth."),
        ("•At the Advancing AI 2024 event.", "• At the Advancing AI 2024 event."),
    ]:
        assert norm(stored) == norm(live)


def test_norm_trademark_spacing():
    assert norm("CUPERTINO, CALIFORNIA — Apple ® today announced") == norm(
        "CUPERTINO, CALIFORNIA — Apple® today announced"
    )


def test_norm_footnote_key_spacing():
    assert norm("Diluted earnings per share was $1.64, 1 up 12 percent") == norm(
        "Diluted earnings per share was $1.64,1 up 12 percent"
    )
    assert norm("on an adjusted basis. 1") == norm("on an adjusted basis.1")


def test_norm_keeps_content_differences():
    assert norm("on an adjusted basis. 1") != norm("on an adjusted basis. 2")
    assert norm("ended Sept. 1, 2025") != norm("ended Sept. 2, 2025")
    assert norm("Net revenue $6.2 billion") != norm("Net revenue $6.3 billion")
    assert norm("Q1 25 revenue") != norm("Q1 26 revenue")


# --- chrome predicates ---------------------------------------------------

def test_period_subheading_positives():
    for ln in [
        "Third Quarter 2025 Results",
        "Third Quarter 2025 Financial Results",
        "Third Quarter Total Company Results (GAAP)",
        "Third Quarter Total Company Results (Base Business - Non-GAAP)*",
        "First Quarter 2026 Results",
    ]:
        assert rep._is_period_subheading(ln), ln


def test_period_subheading_negatives():
    for ln in [
        "Fourth quarter highlights",  # lowercase + "highlights", not "Results"
        "Third Quarter 2025 Revenue",
        "Creating shareholder value",
        "Third Quarter 2025 Results and Outlook",  # trailing prose
    ]:
        assert not rep._is_period_subheading(ln), ln


def test_table_section_header():
    assert rep._is_table_section_header(
        "Net revenue by segment", "(Dollars in millions) Q1 25 Q1 24 Change"
    )
    # Same shape before a bullet is a group label, not table chrome.
    assert not rep._is_table_section_header(
        "Creating shareholder value", "• Delivered fiscal fourth quarter adjusted EBITDA"
    )
    # Figures or a terminator disqualify it.
    assert not rep._is_table_section_header(
        "Net revenue $14,916", "(Dollars in millions) Q1 25 Q1 24 Change"
    )
    assert not rep._is_table_section_header(
        "Net revenue by segment:", "(Dollars in millions) Q1 25 Q1 24 Change"
    )


def test_section_subheading():
    live_set = {
        "“Our integrated model accelerates our ability.”",
        "• Total revenues of $17.3 billion in the third quarter.",
    }
    assert rep._is_section_subheading(
        "CEO Commentary", "“Our integrated model accelerates our ability.”", live_set
    )
    assert rep._is_section_subheading(
        "Third Quarter 2025 Results",
        "• Total revenues of $17.3 billion in the third quarter.",
        live_set,
    )
    # Heading over content live drops is not chrome.
    assert not rep._is_section_subheading(
        "Creating shareholder value",
        "• Delivered fiscal fourth quarter adjusted EBITDA margin* of 44.1 percent",
        live_set,
    )
    # Lowercase words / too many words disqualify it.
    assert not rep._is_section_subheading(
        "Fourth quarter highlights", "• Revenue of $1.020 billion", live_set
    )
    assert not rep._is_section_subheading(
        "Third Quarter 2025 Financial Results and Outlook",
        "• Total revenues of $17.3 billion in the third quarter.",
        live_set,
    )


def test_dateline_sentence():
    for ln in [
        "FORT WORTH, Texas — American Airlines Group Inc. (NASDAQ: AAL) today reported its fourth-quarter results, including:",
        "BURBANK, Calif. – The Walt Disney Company today reported earnings for its fourth quarter.",
        "Stamford, Connecticut - November 1, 2024 - Charter Communications, Inc. (along with its subsidiaries, the “Company” or “Charter”), which operates the Spectrum brand.",
        "WOONSOCKET, RHODE ISLAND, November 6, 2024 - CVS Health Corporation (NYSE: CVS) today announced operating results for the three months ended September 30, 2024.",
    ]:
        assert rep._is_dateline_sentence(ln), ln
    for ln in [
        "The Company reported strong results today.",
        "• Revenue grew 10% year over year.",
        "Net revenue by segment",
    ]:
        assert not rep._is_dateline_sentence(ln), ln


# --- gate S3 on pairs modeled on the real rows --------------------------

def test_gate_s3_repairs_aal_dateline_row():
    stored = (
        "AMERICAN AIRLINES REPORTS FOURTH-QUARTER AND FULL-YEAR 2024 FINANCIAL RESULTS\n"
        "FORT WORTH, Texas — American Airlines Group Inc. (NASDAQ: AAL) today reported its fourth-quarter and full-year 2024 financial results, including:\n"
        "• Record fourth-quarter revenue of $13.7 billion and record full-year revenue of $54.2 billion\n"
        "• Generated $4 billion in full-year operating cash flow\n"
    )
    live = (
        "AMERICAN AIRLINES REPORTS FOURTH-QUARTER AND FULL-YEAR 2024 FINANCIAL RESULTS\n"
        "• Record fourth-quarter revenue of $13.7 billion and record full-year revenue of $54.2 billion\n"
        "• Generated $4 billion in full-year operating cash flow\n"
        "• Achieved total debt reduction goal of $15 billion from peak levels\n"
        "“The American Airlines team achieved a number of important objectives in 2024,” said American's CEO Robert Isom.\n"
    )
    assert rep.sweep_gate_s3(stored, live) is None


def test_gate_s3_repairs_avgo_table_row():
    stored = (
        "Broadcom Inc. Announces First Quarter Fiscal Year 2025 Financial Results and Quarterly Dividend\n"
        "GAAP Non-GAAP\n"
        "(Dollars in millions, except per share data) Q1 25 Q1 24 Change Q1 25 Q1 24 Change\n"
        "Net revenue $ 14,916 $ 11,961 +25 % $ 14,916 $ 11,961 +25 %\n"
        "Net revenue by segment\n"
        "(Dollars in millions) Q1 25 Q1 24 Change\n"
        "Semiconductor solutions $ 8,212 55 % $ 7,390 62 % +11 %\n"
    )
    live = (
        "Broadcom Inc. Announces First Quarter Fiscal Year 2025 Financial Results and Quarterly Dividend\n"
        "• Revenue of $14,916 million for the first quarter, up 25 percent from the prior year period\n"
        "• GAAP net income of $5,503 million for the first quarter\n"
    )
    assert rep.sweep_gate_s3(stored, live) is None


def test_gate_s3_repairs_cl_subheading_row():
    stored = (
        "Colgate-Palmolive Company Announces 3rd Quarter 2025 Results\n"
        "• Net sales increased 2.0%; Organic sales* increased 0.4%\n"
        "• GAAP EPS increased 1% to $0.91\n"
        "Third Quarter Total Company Results (GAAP)\n"
        "($ in millions except per share amounts) 2025 2024 Change\n"
        "Net Sales $5,131 $5,033 +2.0 %\n"
        "Third Quarter Total Company Results (Base Business - Non-GAAP)*\n"
        "2025 2024 Change\n"
        "Organic Sales Growth +0.4 %\n"
    )
    live = (
        "Colgate-Palmolive Company Announces 3rd Quarter 2025 Results\n"
        "• Net sales increased 2.0%; Organic sales* increased 0.4%\n"
        "• GAAP EPS increased 1% to $0.91\n"
    )
    assert rep.sweep_gate_s3(stored, live) is None


def test_gate_s3_repairs_cvs_row():
    stored = (
        "CVS HEALTH CORPORATION REPORTS THIRD QUARTER 2024 RESULTS\n"
        "• Third quarter total revenues increased to $95.4 billion, up 6.3% compared to the prior year\n"
        "• Third quarter GAAP diluted EPS of $0.07 and Adjusted EPS of $1.09\n"
        "CEO Commentary\n"
        "“Our integrated model accelerates our ability to uniquely do what is most important to today’s health care consumers.”\n"
        "— David Joyner, CVS Health President and CEO\n"
        "WOONSOCKET, RHODE ISLAND, November 6, 2024 - CVS Health Corporation (NYSE: CVS) today announced operating results for the three months ended September 30, 2024.\n"
    )
    live = (
        "CVS HEALTH CORPORATION REPORTS THIRD QUARTER 2024 RESULTS\n"
        "• Third quarter total revenues increased to $95.4 billion, up 6.3% compared to the prior year\n"
        "• Third quarter GAAP diluted EPS of $0.07 and Adjusted EPS of $1.09\n"
        "• Generated year-to-date cash flow from operations of $7.2 billion\n"
        "“Our integrated model accelerates our ability to uniquely do what is most important to today’s health care consumers.”\n"
        "— David Joyner, CVS Health President and CEO\n"
    )
    assert rep.sweep_gate_s3(stored, live) is None


def test_gate_s3_still_blocks_genuine_loss():
    # Amazon: stored carries the business-highlights bullets live does
    # not — a different bullet block, not chrome. Overwriting would
    # lose content, so the gate must still refuse.
    stored = (
        "AMAZON.COM ANNOUNCES THIRD QUARTER RESULTS\n"
        "• Held its annual Prime Big Deal Days shopping event, with record sales.\n"
        "• Announced its first-ever fuel savings offer for Prime members.\n"
    )
    live = (
        "AMAZON.COM ANNOUNCES THIRD QUARTER RESULTS\n"
        "• Net sales increased 11% to $158.9 billion in the third quarter.\n"
        "• AWS segment sales increased 19% year-over-year to $27.5 billion.\n"
    )
    assert rep.sweep_gate_s3(stored, live) == "loss"


def test_gate_s3_still_blocks_different_dateline():
    # Live carries a DIFFERENT dateline (another quarter's release):
    # the exemption only fires when live carries no dateline at all.
    stored = (
        "CVS HEALTH CORPORATION REPORTS THIRD QUARTER 2024 RESULTS\n"
        "• Third quarter total revenues increased to $95.4 billion, up 6.3% compared to the prior year\n"
        "WOONSOCKET, RHODE ISLAND, November 6, 2024 - CVS Health Corporation (NYSE: CVS) today announced operating results for the three months ended September 30, 2024.\n"
    )
    live = (
        "CVS HEALTH CORPORATION REPORTS THIRD QUARTER 2024 RESULTS\n"
        "WOONSOCKET, RHODE ISLAND, February 12, 2025 - CVS Health Corporation (NYSE: CVS) today announced operating results for the three months ended December 31, 2024.\n"
        "• Third quarter total revenues increased to $95.4 billion, up 6.3% compared to the prior year\n"
    )
    assert rep.sweep_gate_s3(stored, live) == "dateline-mismatch"


def test_gate_s3_still_blocks_added_table():
    stored = (
        "THE WALT DISNEY COMPANY REPORTS FOURTH QUARTER AND FULL YEAR EARNINGS FOR FISCAL 2024\n"
        "BURBANK, Calif. – The Walt Disney Company today reported earnings for its fourth quarter and full year ended September 28, 2024.\n"
        "• Revenues increased 6% for Q4 to $22.6 billion.\n"
    )
    live = (
        "THE WALT DISNEY COMPANY REPORTS FOURTH QUARTER AND FULL YEAR EARNINGS FOR FISCAL 2024\n"
        "• Revenues increased 6% for Q4 to $22.6 billion.\n"
        "Total segment operating income $1.1 billion $0.3 billion\n"
    )
    assert rep.sweep_gate_s3(stored, live) == "added-table"
