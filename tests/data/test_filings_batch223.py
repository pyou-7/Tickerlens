"""Batch 223: numbered event announcements are narrative, not footnotes.

The Highlights-section collector dropped APLD's two "Recent Operational
Highlights" items ("1.The Company announced ... $160 million private
placement ..." / "2.The Company added two additional clusters ...")
because _is_bare_numbered_footnote treats any terminated bare-numbered
sentence as a footnote definition. Cache survey (4,034 bare-numbered
footnote lines): the "The Company / We" openers are otherwise
definitions and disclaimers ("We define Adjusted Net Income ...",
"The Company does not provide a reconciliation ...", "The Company
declared and paid quarterly dividends ...", "We calculate average
revenue per subscriber ...") — and a sequential run under a Highlights
heading is usually a footnote run too (AGNC's "1.Represents a non-GAAP
measure. / 2.Please refer to ...", AXP's 6-item definition run), so
neither subject nor sequence discriminates. The fix exempts only
"The Company" + an event verb (announced, added, launched, ...):
exactly APLD's two lines match in the whole cache.

Live pins run the extractor against the real cached exhibits; the unit
pins cover the exemption and its guards directly.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_bare_numbered_footnote,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


# --- live pins: APLD's numbered items are served, quote still completes ---


def test_apld_numbered_operational_highlights_served() -> None:
    hl = extract_press_release_highlights(_read("APLD_2024-08-31.html"))
    assert hl is not None
    assert "1.The Company announced on September 5, 2024" in hl
    assert "$160 million private placement financing" in hl
    assert "2.The Company added two additional clusters" in hl
    assert "increasing the total to six clusters" in hl
    # The heading is no longer dangling, and the batch-222 quote
    # completion survives the two extra lines (no cap regression).
    assert "Recent Operational Highlights" in hl
    assert "effective Monday, October 14th.\"" in hl


def test_agnc_footnote_run_still_dropped() -> None:
    hl = extract_press_release_highlights(_read("AGNC_2024-12-31.html"))
    assert hl is not None
    assert "Represents a non-GAAP measure" not in hl
    assert "Please refer to Net Interest Spread Components" not in hl


def test_axp_footnote_run_still_dropped() -> None:
    hl = extract_press_release_highlights(_read("AXP_2025-06-30.html"))
    assert hl is not None
    assert "As used in this release, FX-adjusted information assumes" not in hl
    assert "Adjusted diluted earnings per common share, a non-GAAP measure" not in hl


def test_anet_prior_period_footnote_still_dropped() -> None:
    hl = extract_press_release_highlights(_read("ANET_2026-03-31.html"))
    assert hl is not None
    assert "Prior period amounts have been updated" not in hl
    assert "Financial Outlook" not in hl  # dangling heading stays out


# --- unit pins: the exemption and its guards ------------------------------


def test_event_announcement_is_not_a_footnote() -> None:
    assert not _is_bare_numbered_footnote(
        "1.The Company announced on September 5, 2024 that it has entered into"
        " definitive agreements for a $160 million private placement financing."
    )
    assert not _is_bare_numbered_footnote(
        "2.The Company added two additional clusters to our Cloud Services Business."
    )
    assert not _is_bare_numbered_footnote(
        "1. The Company launched a new data center campus in Texas."
    )


def test_definition_and_disclaimer_openers_still_footnotes() -> None:
    assert _is_bare_numbered_footnote(
        "1We define Adjusted Net Income as net income attributable to Comcast Corporation."
    )
    assert _is_bare_numbered_footnote(
        "1The Company does not provide a reconciliation for non-GAAP estimates."
    )
    assert _is_bare_numbered_footnote(
        "1 The Company declared and paid quarterly dividends of $1.00 per share."
    )
    assert _is_bare_numbered_footnote(
        "3 We calculate average revenue per subscriber as total revenues divided by subscribers."
    )
    assert _is_bare_numbered_footnote(
        "1.Represents a non-GAAP measure. Prior to the fourth quarter 2023, this measure was referred to as net spread income."
    )
    assert _is_bare_numbered_footnote(
        "2.Please refer to Net Interest Spread Components by Funding Source included in this release."
    )


def test_event_verb_list_is_narrow() -> None:
    # "declared" (DKS dividend footnote) and "had" (borrowings footnote)
    # are deliberately NOT event verbs; a non-subject-led event sentence
    # ("In fiscal 2025, the Company expanded ...") is not exempted either.
    assert _is_bare_numbered_footnote(
        "7.The Company declared and paid quarterly dividends of $1.00 per share in fiscal 2023."
    )
    assert _is_bare_numbered_footnote(
        "5.The Company had no outstanding borrowings under its revolving credit facility."
    )
    assert _is_bare_numbered_footnote(
        "3In fiscal 2025, the Company expanded its Luxury fragrance brand portfolio."
    )
    # A company-name subject is not exempted: AXP's award line rides a
    # footnote run and stays dropped.
    assert _is_bare_numbered_footnote(
        "6 American Express received the highest score in the J.D. Power 2025 study."
    )
