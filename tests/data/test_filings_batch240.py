"""Batch 240: the remaining new-residue cohort + EMR's wrapped tail.

Batch 239 closed the diff-figures-added and unexplained-diff cohorts
and left 5 new-residue rows (EL/ELV "(Unaudited)" labels, GE's
interleaved FCF row, SKYD's 6-value row) plus EMR's 4-word wrapped
tail. Three of the five are probe false positives — the live
extraction is right and the residue check is wrong — and the other
two are real extractor gaps:

1. GE's table footnotes use a letter-dash key ("(a – Future
   dividends ...", "(b – FCF* conversion: ...") with no closing
   paren, so the shared paren opener never fires and the definitions
   ride the collected guidance. The guidance-local opener now
   matches the shape (single letter + dash only — a multi-letter
   label stays a labeled value, a dash-less paren stays prose).
2. EMR's "Acquisition / Divestiture" label wraps onto "Fees and
   Related Costs" (4 words), past the wrapped-label fragment cap
   of 2. The cap is now 4 — a wrap point is arbitrary, and the other
   guards (prev at most 3 words, no marker on either side, no slash
   in the continuation) still keep complete metrics out.
3. The probe's _residue now exempts the three shapes the extractor
   deliberately keeps or refuses: a bare "(Unaudited)"/"(Audited)"
   table-header label (next line is table-shaped), an interleaved
   row label the fuser correctly refuses to fuse (GE's "FCF*
   Conversion-b)" after the marked "Free cash flow*"), and a row
   with 5+ value units the fuser refuses by design (SKYD's
   "Direct-to-Consumer" carries six).

Blast over all 1,699 cached exhibits (guidance + highlights): the
letter-dash opener drops GE's two footnote definitions and the
wrapped-label cap joins EMR 2024-09-30's tail — and nothing else.
The repair re-syncs EL x1, ELV x2, SKYD x1, EMR 2024-09-30 and GE
2025-09-30 under gate A (6 rows) and GE 2025-06-30 under gate F
(1 row).

All pins are synthetic except the live pins, which run the real
extractor over the frozen cached exhibits — the suite reads no
database. The gate pins are synthetic stored/new pairs copied from
the real diffs.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from tickerlens.data.filings import (  # noqa: E402
    _clean_guidance_footnotes,
    _clean_guidance_result,
    _guidance_footnote_opener,
    _is_wrapped_label_fragment,
    extract_management_guidance,
)
from batch236_repair import (  # noqa: E402
    _is_audit_status_table_label,
    _is_interleaved_label_refusal,
    _residue,
    _value_unit_run,
)
from batch237_repair import _gate_a_passes  # noqa: E402
from batch239_repair import _gate_f_passes  # noqa: E402

CACHE = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html")


# --- Letter-dash footnote keys --------------------------------------

def test_letter_dash_footnote_opener():
    # GE's shapes: en dash, hyphen, em dash, and the definition
    # starting on the next line (the line ends after the dash).
    assert _guidance_footnote_opener(
        "(a – Future dividends and increases to the share buyback "
        "authorization are subject to approval by GE Aerospace's Board "
        "of Directors."
    )
    assert _guidance_footnote_opener("(b – FCF* conversion: FCF*/adjusted net income*")
    assert _guidance_footnote_opener("(a - Future dividends are subject to approval.")
    assert _guidance_footnote_opener("(a — Future dividends are subject to approval.")
    assert _guidance_footnote_opener("(a –")
    assert _guidance_footnote_opener("(c – See the reconciliation table below.")
    # No space between the key and the dash is the same shape.
    assert _guidance_footnote_opener("(a– Future dividends are subject to approval.")


def test_letter_dash_opener_guards():
    # A multi-letter parenthesized label is a labeled value, never a
    # footnote key (batch 238's FDX shape) — and a dash-less paren
    # line stays a prose continuation (batch 176).
    assert not _guidance_footnote_opener("(ETR) ~23% Prior to CY 2026 additional MTM adjustments")
    assert not _guidance_footnote_opener("(MRC) protocol for the study")
    assert not _guidance_footnote_opener("(QoQ) and segment growth")
    # A two-letter key is not a footnote key either.
    assert not _guidance_footnote_opener("(AB – Future dividends are subject to approval.")
    # The plain "(a) ..." form was already an opener — unchanged.
    assert _guidance_footnote_opener("(a) Future dividends are subject to approval.")
    # A bare "(Unaudited)" is still an opener at the predicate level —
    # the table-label exemption lives in _residue, not here.
    assert _guidance_footnote_opener("(Unaudited)")


def test_clean_guidance_footnotes_drops_letter_dash_block():
    # The GE shape: the two definitions chain and drop whole; the
    # "*" legend line ahead of them is not a definition and stays.
    lines = [
        "Operating profit*",
        "$7.8 - $8.2 billion",
        "~$10 billion",
        "* Non-GAAP Financial Measure",
        "(a – Future dividends and increases to the share buyback "
        "authorization are subject to approval by GE Aerospace's Board "
        "of Directors.",
        "(b – FCF* conversion: FCF*/adjusted net income*",
    ]
    out = _clean_guidance_footnotes(lines)
    assert "* Non-GAAP Financial Measure" in out
    assert not any("(a –" in ln for ln in out)
    assert not any("(b –" in ln for ln in out)
    assert "Operating profit*" in out


def test_ge_2025_06_30_drops_footnote_definitions():
    html = (CACHE / "GE_2025-06-30.html").read_text(encoding="utf-8")
    g = extract_management_guidance(html)
    assert g is not None
    assert "(a –" not in g
    assert "(b –" not in g
    assert "Future dividends and increases" not in g
    assert "FCF* conversion: FCF*/adjusted net income" not in g
    # The table itself is intact, including the interleaved rows and
    # the legend line (which is source content, not a definition).
    assert (
        "Operating profit*: $7.8 - $8.2 billion / $8.2 - $8.5 billion / "
        "~$10 billion / ~$11.5 billion" in g
    )
    assert "Free cash flow*" in g
    assert "FCF* Conversion-b)" in g
    assert "* Non-GAAP Financial Measure" in g


# --- Wrapped-label fragment: 4-word continuations -------------------

def test_wrapped_label_fragment_four_word_continuation():
    # EMR's shape: the continuation is four words.
    assert _is_wrapped_label_fragment(
        "Acquisition / Divestiture", "Fees and Related Costs"
    )
    # The batch-233 pins still hold.
    assert _is_wrapped_label_fragment("Underlying Sales", "Growth")
    assert _is_wrapped_label_fragment("Restructuring / Related", "Costs")


def test_wrapped_label_fragment_still_refuses():
    # Five words is still a complete metric, not a fragment.
    assert not _is_wrapped_label_fragment(
        "Acquisition / Divestiture", "Fees and Related Costs Total"
    )
    # A slash in the continuation, a marker on either side, a long
    # prev line, and a header prev line all still refuse.
    assert not _is_wrapped_label_fragment(
        "Acquisition / Divestiture", "U.S. Dollar / Pound Sterling"
    )
    assert not _is_wrapped_label_fragment(
        "Acquisition / Divestiture", "Fees and Related Costs(2)"
    )
    assert not _is_wrapped_label_fragment("Operating Profit*", "Growth")
    assert not _is_wrapped_label_fragment(
        "Top-Line and Cost Structure", "Growth"
    )
    assert not _is_wrapped_label_fragment("Full Year 2025", "Growth")


def test_clean_guidance_result_joins_four_word_wrapped_label():
    collected = [
        "2025 Outlook",
        "Restructuring / Related",
        "Costs",
        "~$0.04",
        "~$0.16",
        "Acquisition / Divestiture",
        "Fees and Related Costs",
        "~$0.01",
        "~$0.04",
        "Adjusted Earnings",
        "Per Share",
        "$1.25",
        "- $1.30",
    ]
    out = _clean_guidance_result(collected)
    assert "Restructuring / Related Costs: ~$0.04 / ~$0.16" in out
    assert (
        "Acquisition / Divestiture Fees and Related Costs: ~$0.01 / ~$0.04"
        in out
    )
    assert "Adjusted Earnings Per Share: $1.25 - $1.30" in out
    # No orphan fragment lines survive.
    assert "Acquisition / Divestiture" not in out
    assert "Fees and Related Costs" not in out


def test_emr_2024_09_30_joins_wrapped_label():
    html = (CACHE / "EMR_2024-09-30.html").read_text(encoding="utf-8")
    g = extract_management_guidance(html)
    assert g is not None
    assert (
        "Acquisition / Divestiture Fees and Related Costs: ~$0.01 / ~$0.04"
        in g
    )


def test_emr_2024_12_31_single_line_label_unchanged():
    # The later quarters carry the full label on one line already —
    # the cap change must not re-render them.
    html = (CACHE / "EMR_2024-12-31.html").read_text(encoding="utf-8")
    g = extract_management_guidance(html)
    assert g is not None
    assert (
        "Acquisition / Divestiture Fees and Related Costs: ~$0.02 ~$0.08"
        in g
    )


# --- _residue exemptions --------------------------------------------

def test_residue_audit_status_table_label():
    # EL's shape: the "(Unaudited)" line sits between the
    # reconciliation title and the period header — a table label,
    # not a footnote definition.
    lines = [
        "Reconciliation between GAAP and Non-GAAP - Net Sales Growth",
        "(Unaudited)",
        "Twelve Months Ending",
        "June 30, 2026(1)",
        "As Reported - GAAP 3% - 5%",
    ]
    assert _residue(lines) == []
    assert _is_audit_status_table_label(lines, 1)
    # ELV's shape: the next line is a period header line.
    lines2 = [
        "Financial Guidance Summary",
        "(Unaudited)",
        "Full Year 2024 Actual Full Year 2025 Outlook",
        "Premium Revenue",
        "$144.2 billion Low double digit growth",
    ]
    assert _residue(lines2) == []
    assert _is_audit_status_table_label(lines2, 1)
    # "(Audited)" is the same class.
    assert _is_audit_status_table_label(
        ["Financial Guidance Summary", "(Audited)", "Full Year 2025 Actual"], 1
    )


def test_residue_audit_status_still_flags_prose():
    # A bare "(Unaudited)" followed by prose is still a footnote
    # opener — the exemption needs the table-shaped next line.
    lines = ["(Unaudited)", "Net sales grew 5% in the quarter."]
    assert not _is_audit_status_table_label(lines, 0)
    assert _residue(lines) == ["footnote opener: '(Unaudited)'"]
    # And a trailing "(Unaudited)" with no next line never exempts.
    assert not _is_audit_status_table_label(["(Unaudited)"], 0)


def test_residue_interleaved_label_refusal():
    # GE's shape: the marked "Free cash flow*" row's values are
    # interleaved with the conversion row's, so the fuser refuses
    # the fuse — the unfused pair is faithful, not residue.
    lines = [
        "Free cash flow*",
        "FCF* Conversion-b)",
        "$6.3 - $6.8 billion",
        ">100%",
    ]
    assert _residue(lines) == []
    assert _is_interleaved_label_refusal(lines, 1)
    # A plain label + value with no marked prev line is still residue.
    assert _residue(["Operating profit", "$7.8 - $8.2 billion"]) == [
        "unfused split row: 'Operating profit' / '$7.8 - $8.2 billion'"
    ]
    assert not _is_interleaved_label_refusal(
        ["Operating profit", "$7.8 - $8.2 billion"], 0
    )
    # A marked prev line that is a header does not count as
    # interleaving (a column header, not a row label).
    assert not _is_interleaved_label_refusal(
        ["2025 guidance*", "FCF* Conversion-b)"], 1
    )


def test_value_unit_run_counts():
    assert _value_unit_run(["$2,264", "$923", "$1,344"], 0) == 3
    assert _value_unit_run(["$2,264", "$923", "$1,344", "$2,309", "$2,398"], 0) == 5
    # A dash-led line continues the previous unit, it is not a new one.
    assert _value_unit_run(["$1.25", "- $1.30", "$5.85"], 0) == 2
    # A non-value line ends the run.
    assert _value_unit_run(["$2,264", "Y/Y Growth (%): 11% / 9%"], 0) == 1


def test_residue_five_plus_value_units():
    # SKYD's shape: six consecutive value lines after the label —
    # the fuser refuses at five, so the row is unfusable by design.
    lines = [
        "Direct-to-Consumer",
        "$2,264",
        "$923",
        "$1,344",
        "$2,309",
        "$2,398",
        "$2,474",
        "Y/Y Growth (%): 11% / 9%",
    ]
    assert _residue(lines) == []
    # Four units still fuse, so a four-value row is still residue.
    assert _residue(["Studios", "1,135", "2,060", "1,283", "1,314"]) == [
        "unfused split row: 'Studios' / '1,135'"
    ]


def test_skyd_2026_06_30_fuses_studios_not_direct_to_consumer():
    html = (CACHE / "SKYD_2026-06-30.html").read_text(encoding="utf-8")
    g = extract_management_guidance(html)
    assert g is not None
    assert "Studios: 1,135 / 2,060 / 1,283 / 1,314" in g
    # The six-value row stays unfused by design — and the probe no
    # longer flags it.
    assert "Direct-to-Consumer" in g
    assert "$2,264" in g
    assert _residue([ln for ln in g.splitlines() if ln.strip()]) == []


def test_el_2025_12_31_keeps_unaudited_label():
    html = (CACHE / "EL_2025-12-31.html").read_text(encoding="utf-8")
    g = extract_management_guidance(html)
    assert g is not None
    assert "(Unaudited)" in g
    assert "Restructuring and other charges(2): 1.03 - 1.07 1.06" in g
    assert _residue([ln for ln in g.splitlines() if ln.strip()]) == []


def test_elv_2024_12_31_keeps_unaudited_label():
    html = (CACHE / "ELV_2024-12-31.html").read_text(encoding="utf-8")
    g = extract_management_guidance(html)
    assert g is not None
    assert "(Unaudited)" in g
    assert "Amortization of other intangibles3: $2.57" in g
    assert _residue([ln for ln in g.splitlines() if ln.strip()]) == []


def test_elv_2025_12_31_keeps_unaudited_label():
    html = (CACHE / "ELV_2025-12-31.html").read_text(encoding="utf-8")
    g = extract_management_guidance(html)
    assert g is not None
    assert "(Unaudited)" in g
    assert "Premium Revenue: $164.6 billion" in g
    assert _residue([ln for ln in g.splitlines() if ln.strip()]) == []


# --- Gates ------------------------------------------------------------

_EL_STORED = """OUTLOOK FOR FISCAL 2026 FULL YEAR
Reconciliation between GAAP and Non-GAAP - Net Sales Growth
(Unaudited)
Twelve Months Ending
June 30, 2026(1)
As Reported - GAAP 3% - 5%
Restructuring and other charges(2)
1.03 - 1.07 1.06
Organic, Non-GAAP 1% - 3%"""

_EL_NEW = """OUTLOOK FOR FISCAL 2026 FULL YEAR
Reconciliation between GAAP and Non-GAAP - Net Sales Growth
(Unaudited)
Twelve Months Ending
June 30, 2026(1)
As Reported - GAAP 3% - 5%
Restructuring and other charges(2): 1.03 - 1.07 1.06
Organic, Non-GAAP 1% - 3%"""


def test_gate_a_el_shape():
    # The Estée Lauder shape: pure fusing under a kept "(Unaudited)"
    # table label — figures equal, diff is the fuse itself.
    assert _residue([ln for ln in _EL_NEW.splitlines() if ln.strip()]) == []
    assert _gate_a_passes(_EL_STORED, _EL_NEW)


_GE_STORED = """Financial outlook:

GE Aerospace is raising its 2025 guidance and 2028 outlook:

2025 guidance

2028 outlook

Prior guide

As of April 22, 2025

Investor Update

As of July 17, 2025

Prior outlook

As of March 7, 2024

Investor Update

As of July 17, 2025

Adjusted revenue* growth

Low-double-digits

Mid-teens

High-single-digit CAGR ‘25-‘28

Double-digit CAGR '24-'28

Operating profit*

$7.8 - $8.2 billion

$8.2 - $8.5 billion

~$10 billion

~$11.5 billion

Adjusted EPS*

$5.10 - $5.45

$5.60 - $5.80

Not given ~$8.40

Free cash flow*

FCF* Conversion -b)

$6.3 - $6.8 billion

>100%"""

_GE_NEW = """Financial outlook:

GE Aerospace is raising its 2025 guidance and 2028 outlook:

2025 guidance

2028 outlook

Prior guide

As of April 22, 2025

Investor Update

As of July 17, 2025

Prior outlook

As of March 7, 2024

Investor Update

As of July 17, 2025

Adjusted revenue* growth

Low-double-digits

Mid-teens

High-single-digit CAGR ‘25-‘28

Double-digit CAGR '24-'28

Operating profit*: $7.8 - $8.2 billion / $8.2 - $8.5 billion / ~$10 billion / ~$11.5 billion

Adjusted EPS*: $5.10 - $5.45 / $5.60 - $5.80

Not given ~$8.40

Free cash flow*

FCF* Conversion-b)

$6.3 - $6.8 billion

>100%

$6.5 - $6.9 billion

>100%

~100%

~$8.5 billion

~100%

* Non-GAAP Financial Measure"""


def test_gate_f_ge_shape():
    # The GE Aerospace shape: the new extraction adds the remaining
    # table columns (interleaved FCF/conversion values) plus the "*"
    # legend line, and drops the two letter-dash footnote definitions.
    # The added lines are all guidance-shaped, the section is anchored
    # by the shared fused Operating profit row, and the only removed
    # line is a spacing re-render of a kept label.
    assert _residue([ln for ln in _GE_NEW.splitlines() if ln.strip()]) == []
    assert _gate_f_passes(_GE_STORED, _GE_NEW)


def test_gate_f_ge_refuses_different_vintage():
    # The same shape, but the new text drops a real guidance value
    # the stored row has (the Operating profit row's figures change)
    # — no shared fused row anchors it.
    new = _GE_NEW.replace(
        "Operating profit*: $7.8 - $8.2 billion / $8.2 - $8.5 billion / "
        "~$10 billion / ~$11.5 billion",
        "Operating profit*: $9.8 - $10.2 billion / $10.2 - $10.5 billion / "
        "~$12 billion / ~$13.5 billion",
    )
    assert not _gate_f_passes(_GE_STORED, new)
