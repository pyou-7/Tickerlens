"""Batch 210: table-of-contents anchor rejection in the guidance
extractor — a heading that heads a TOC run is a TOC entry, not the
section heading.

Batch-209 carry-forward: DLR over-collection. Every DLR stored
guidance row (8 quarters, ~748 chars each) is the supplement's table
of contents: "2025 Outlook" / "Consolidated Quarterly Statements of
Operations" / "Funds From Operations ..." / ... — the extractor
anchored on the contents-page entry for "2025 Outlook" (line 19 of
the line stream, followed by the bare page number "10") and spent
its whole line budget on TOC titles. The real outlook section sits
~750 lines later ("Digital Realty raised its 2025 Core FFO per share
outlook to $7.15 - $7.25 ...") and was never reached, because the
function returns the first anchor whose collection clears 100 chars.

Fix (extract_management_guidance anchor loop, via _is_toc_entry): a
heading candidate is a TOC entry when the next line is a bare page
number AND the line after that is another title followed by another
bare page number — two consecutive (title, page-number) pairs. The
anchor is skipped and scanning continues to the real heading.

The two-pair requirement is the guard. A single bare number after a
heading is often just a page footer: ELV's "Financial Guidance
Summary" is followed by "6" and then "Elevance Health" (the next
page's content), and SPG's "Guidance Reconciliation" by "43" and
then "(1)" — neither is a contents page, and neither anchor may be
skipped. Both shapes are pinned unchanged.

Blast (blast210/g_new vs blast209/g_new, 1,699 exhibits): 12 diffs,
0 None-flips — all DLR, all TOC dumps replaced by genuine Core FFO
outlook tables. Repair: 8 stored DLR rows.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_guidance_heading,
    _is_toc_entry,
    extract_management_guidance,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _lines_of(html: str) -> list[str]:
    from tickerlens.data.filings import _html_to_text

    text = _html_to_text(html)
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def _doc(*paragraphs: str) -> str:
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return f"<html><body>{body}</body></html>"


# _is_toc_entry unit pins.
def test_toc_entry_matches_two_consecutive_title_number_pairs():
    lines = [
        "2025 Outlook",
        "10",
        "Consolidated Quarterly Statements of Operations",
        "12",
        "Funds From Operations and Core Funds From Operations",
        "13",
    ]
    assert _is_toc_entry(lines, 0) is True


def test_toc_entry_rejects_single_page_number_footer():
    # ELV: heading, one bare number, then the next page's content —
    # a page footer, not a contents page.
    lines = [
        "Financial Guidance Summary",
        "6",
        "Elevance Health expects full-year adjusted EPS of $30.00.",
    ]
    assert _is_toc_entry(lines, 0) is False


def test_toc_entry_rejects_number_then_footnote_marker():
    # SPG: heading, page number, then "(1)" — a reconciliation table
    # header, not a contents page.
    lines = ["Guidance Reconciliation", "43", "(1)", "FFO per share"]
    assert _is_toc_entry(lines, 0) is False


def test_toc_entry_rejects_two_numbers_in_a_row():
    # A heading followed by two bare numbers is a table fragment,
    # not two (title, number) pairs.
    lines = ["2025 Outlook", "10", "12", "Total revenue"]
    assert _is_toc_entry(lines, 0) is False


def test_toc_entry_rejects_short_tail():
    lines = ["2025 Outlook", "10", "Contents"]
    assert _is_toc_entry(lines, 0) is False


# Synthetic end-to-end pins.
def test_toc_anchor_skipped_for_real_outlook_section():
    # DLR shape, compressed: a contents page, then the real outlook
    # section later in the document.
    html = _doc(
        "2025 Outlook",
        "10",
        "Consolidated Quarterly Statements of Operations",
        "12",
        "Funds From Operations and Core Funds From Operations",
        "13",
        "Corporate Profile",
        "Digital Realty owns data centers across North America and "
        "Europe. As of June 30, 2025, the company's 310 data centers "
        "contain applications critical to the day-to-day operations "
        "of technology customers.",
        "2025 Outlook",
        "Digital Realty raised its 2025 Core FFO per share outlook to "
        "$7.15 - $7.25 and its 2025 Constant-Currency Core FFO per "
        "share outlook to $7.10 - $7.20. The assumptions underlying "
        "the outlook are summarized in the following table.",
        "Total revenue",
        "$5.800 - $5.900 billion",
    )
    text = extract_management_guidance(html)
    assert text is not None
    assert "Consolidated Quarterly Statements of Operations" not in text
    assert "Funds From Operations and Core Funds From Operations" not in text
    assert "Core FFO per share outlook to $7.15 - $7.25" in text
    assert "$5.800 - $5.900 billion" in text


def test_single_page_number_after_heading_anchors_normally():
    # ELV shape: the heading is real; the bare number after it is a
    # page footer and the guidance prose follows.
    html = _doc(
        "Financial Guidance Summary",
        "6",
        "Elevance Health expects full-year 2025 adjusted EPS of "
        "$30.00 to $31.00 and revenue of $180 billion, reflecting "
        "strong membership growth and favorable medical cost trends "
        "across its commercial and government businesses.",
    )
    text = extract_management_guidance(html)
    assert text is not None
    assert "adjusted EPS of $30.00 to $31.00" in text


def test_guidance_reconciliation_table_anchors_normally():
    # SPG shape: the heading is real; the number is a page number
    # and "(1)" is the table's footnote marker. The marker and the
    # table fragments drop in collection (footnote machinery), but the
    # anchor itself is not skipped as a TOC entry.
    html = _doc(
        "Guidance Reconciliation",
        "43",
        "(1)",
        "FFO per share",
        "$4.00 - $4.10",
        "The Company expects full-year 2025 FFO per share of $4.00 to "
        "$4.10, same-property NOI growth of 3.0% to 4.0% and occupancy "
        "above 95% across the portfolio.",
    )
    text = extract_management_guidance(html)
    assert text is not None
    assert "FFO per share of $4.00 to $4.10" in text


# Real-exhibit pins (fail on old code: the TOC dump is stored).
def test_dlr_2025_06_30_guidance_is_core_ffo_outlook_not_toc():
    text = extract_management_guidance(_load("DLR_2025-06-30.html"))
    assert text is not None
    assert "Consolidated Quarterly Statements of Operations" not in text
    assert "Summary of Leasing Activity" not in text
    assert "Core FFO per share outlook to $7.15 - $7.25" in text
    assert "Constant-Currency Core FFO per share outlook to $7.10 - $7.20" in text
    assert text.startswith("2025 Outlook")
    # Batch 235: 765 -> 775 as the three-column rows fuse (": " + " / ").
    assert len(text) == 775


def test_dlr_2024_06_30_guidance_is_core_ffo_outlook_not_toc():
    text = extract_management_guidance(_load("DLR_2024-06-30.html"))
    assert text is not None
    assert "Consolidated Quarterly Statements of Operations" not in text
    assert "Core FFO per share and Constant-Currency Core FFO per share outlook of $6.60 - $6.75" in text
    # Batch 235: 735 -> 745 as the three-column rows fuse.
    assert len(text) == 745


def test_dlr_2026_09_30_guidance_is_core_ffo_outlook_not_toc():
    text = extract_management_guidance(_load("DLR_2026-09-30.html"))
    assert text is not None
    assert "Consolidated Quarterly Statements of Operations" not in text
    assert "Core FFO per share (excluding net promote) outlook to $8.30 - $8.35" in text
    # Batch 235: 879 -> 891 as the four-column rows fuse.
    assert len(text) == 891


# Guard pins: no-change behavior — these pass on old code too.
def test_elv_guidance_summary_anchor_unchanged():
    lines = _lines_of(_load("ELV_2023-12-31.html"))
    anchors = [
        (i, ln) for i, ln in enumerate(lines) if _is_guidance_heading(ln)
    ]
    assert anchors, "expected at least one guidance anchor in ELV"
    assert anchors[0][1] == "Financial Guidance Summary"
    assert not _is_toc_entry(lines, anchors[0][0])
    text = extract_management_guidance(_load("ELV_2023-12-31.html"))
    assert text is not None
    # Batch 233: 359 -> 360 as the membership rows fuse.
    # Batch 235: 360 -> 361 as the Employer Group row fuses ("(5.8" + ")%").
    assert len(text) == 361


def test_spg_guidance_reconciliation_anchor_unchanged():
    lines = _lines_of(_load("SPG_2025-06-30.html"))
    anchors = [
        (i, ln) for i, ln in enumerate(lines) if _is_guidance_heading(ln)
    ]
    assert anchors, "expected at least one guidance anchor in SPG"
    recon = [i for i, ln in anchors if ln == "Guidance Reconciliation"]
    assert recon, "expected a Guidance Reconciliation anchor in SPG"
    assert not _is_toc_entry(lines, recon[0])
    text = extract_management_guidance(_load("SPG_2025-06-30.html"))
    assert text is not None
    assert len(text) == 528
