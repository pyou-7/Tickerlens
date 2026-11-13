"""Batch 243: the highlights sweep's last first-diff row with an
extractor cause — the orphaned AMT contact role line — plus the
closure of the first-diff cohort.

Root cause (extractor, not the sweep): American Tower heads every
release with a contact block shaped

    Contact: Adam Smith
    Senior Vice President, Investor Relations and FP&A
    Telephone: (617) 375-7500

The role line is content-shaped (7 words), so _skip_contact_block
only keeps skipping past it when the lookahead finds contact
evidence in the next two lines. The only evidence after it is the
"Telephone:" line — but that line matches _ADMIN_LINE_RE (its
telephone alternative), and the batch-151 lookahead skips admin
lines when gathering the following lines. The gather therefore
jumped over the phone, saw [headline, India-sale prose], found no
evidence, and ended the block at the role line; the headline pass
then took the role line as the headline of every AMT quarter (the
batch-242 wart: the 7 repaired AMT rows open on it).

Fix: a line that itself carries contact evidence (a phone number
or a contact-line match) is never skipped as admin while gathering
the lookahead's following lines. The batch-151 behavior is
unchanged — a bare admin line ("FOR IMMEDIATE RELEASE") still
doesn't consume a slot — because it carries no phone/contact
evidence; only the evidence line itself now counts.

Probe finding (scripts/batch243_probe.py): the 16 first-diff rows
decompose into zero repairable rows — AGNC x2 (stored quarter-only
highlights vs live full-year highlights, different figures: a
different exhibit), AMT 2024-09-30 (this fix: stored headline +
India-sale prose + 3 bullets vs live role line + period subhead +
8 bullets + dateline + CEO quote), APO x8 (stored flattened
earnings table vs live lede prose — all figures would be lost),
COIN (stored slide-deck disclaimer junk vs live slide-deck
content), CSCO x3 (stored body prose vs live highlights bullets —
segment margins, tax rates, cash flow would be lost), NFLX
2025-06-30 (stored content-view bullets vs live letter-opening
bullets — different sections). All 16 are section/exhibit
selection, a design question no gate can prove safe; the cohort
closes at 16 with the AMT row's cause fixed at the extractor.
"""
from tickerlens.data.filings import (
    _skip_contact_block,
    extract_press_release_highlights,
)


def test_skip_contact_block_telephone_line_counts_as_evidence() -> None:
    # The AMT shape: a content-shaped role line whose only following
    # contact evidence is a "Telephone:" line. The telephone line
    # matches _ADMIN_LINE_RE, so the old gather skipped it as admin
    # and the block ended at the role line (skip -> 1, role line
    # stranded as the headline). With the fix the phone counts and
    # the block runs to the real headline.
    lines = [
        "Contact: Adam Smith",
        "Senior Vice President, Investor Relations and FP&A",
        "Telephone: (617) 375-7500",
        "AMERICAN TOWER CORPORATION REPORTS THIRD QUARTER 2024 FINANCIAL RESULTS",
    ]
    assert _skip_contact_block(lines, 0) == 3


def test_skip_contact_block_admin_line_without_evidence_still_skipped() -> None:
    # Batch 151 negative, unchanged: a bare admin line between the
    # name line and the headline carries no phone/contact evidence,
    # so it still doesn't consume a lookahead slot and the block
    # still ends at the name line.
    lines = [
        "Investor Contact:",
        "Paul Trussell Sandra Carreon-John",
        "FOR IMMEDIATE RELEASE",
        "NIKE, INC. REPORTS FISCAL 2027 FIRST QUARTER RESULTS",
    ]
    assert _skip_contact_block(lines, 0) == 1


def test_skip_contact_block_tel_abbreviation_line_counts_as_evidence() -> None:
    # The "Tel:" / "Phone:" abbreviations match the same admin
    # telephone alternative, so they count as evidence the same way.
    lines = [
        "Contact: Jane Doe",
        "Vice President, Investor Relations",
        "Tel: 617-375-7500",
        "ACME CORP REPORTS THIRD QUARTER 2025 RESULTS",
    ]
    assert _skip_contact_block(lines, 0) == 3


def test_extract_highlights_amt_contact_block_yields_real_headline() -> None:
    # End-to-end on the AMT shape, modeled line for line on the real
    # Q3 2024 exhibit: contact header + name + role line + telephone
    # line, then the real headline, the India-sale prose, the
    # CONSOLIDATED HIGHLIGHTS section, and its bullets.
    html = """<html><body>
    <p>EX-99.1</p><p>2</p><p>pressreleaseq32024.htm</p><p>EX-99.1</p>
    <p>Exhibit 99.1</p>
    <p>Contact: Adam Smith</p>
    <p>Senior Vice President, Investor Relations and FP&amp;A</p>
    <p>Telephone: (617) 375-7500</p>
    <p>AMERICAN TOWER CORPORATION REPORTS THIRD QUARTER 2024 FINANCIAL RESULTS</p>
    <p>On September 12, 2024, American Tower Corporation (the "Company" or "American Tower") completed the sale of 100% of the equity interests in its operations in India to Data Infrastructure Trust.</p>
    <p>CONSOLIDATED HIGHLIGHTS</p>
    <p>Third Quarter 2024</p>
    <p>&#9679; Total revenue grew by less than 0.1% to $2,522 million</p>
    <p>&#9679; Total property revenue decreased 1.0% to $2,470 million</p>
    <p>&#9679; Net income decreased 235.2% to a net loss of $(780) million</p>
    <p>Boston, Massachusetts - October 29, 2024: American Tower Corporation (NYSE: AMT) today reported financial results for the quarter ended September 30, 2024.</p>
    <p>Steven Vondran, American Tower's Chief Executive Officer, stated, "Adjusted for certain non-cash items in the quarter, including the loss taken upon closing our ATC India sale, our third quarter results were strong."</p>
    </body></html>"""
    hl = extract_press_release_highlights(html)
    assert hl is not None
    first = hl.split("\n\n")[0]
    assert first == (
        "AMERICAN TOWER CORPORATION REPORTS THIRD QUARTER 2024 "
        "FINANCIAL RESULTS"
    )
    assert "Senior Vice President" not in hl
    assert "375-7500" not in hl
    assert "Total revenue grew by less than 0.1% to $2,522 million" in hl
    assert "Total property revenue decreased 1.0% to $2,470 million" in hl
