"""Batch 238: the labeled-value footnote false positive — FedEx's
"(ETR) ~23% ..." guidance row.

The fix is in the extractor (src/tickerlens/data/filings.py):
_is_labeled_value_line recognizes a line that opens with a
parenthesized all-caps abbreviation label followed immediately by a
value figure, and _opens_footnote_def no longer treats such a line as
a footnote definition — so the guidance collector and
_clean_guidance_footnotes keep the row instead of dropping it as a
footnote block. Batch 237's repair-side guard already refused to
credit such a line as chrome; this moves the guard into the extractor
with the label narrowed to an all-caps abbreviation (2+ letters).

Blast over all 1,699 cached exhibits (guidance + highlights): exactly
2 guidance diffs — FDX 2026-05-31 and FDX 2026-09-30, each gaining
only its (ETR) row — and 0 highlights diffs. The repair re-syncs the
two FDX stored rows (2026-05-31 under gate D, 2026-09-30 under the
new gate E: the only added lines are labeled-value lines).

All pins are synthetic except the two live FDX pins, which run the
real extractor over the frozen cached exhibits — the suite reads no
database.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from tickerlens.data.filings import (  # noqa: E402
    _is_labeled_value_line,
    _opens_footnote_def,
    extract_management_guidance,
)

CACHE = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html")

ETR_LINE = (
    "(ETR) ~23% Prior to CY 2026 additional MTM adjustments for "
    "retirement plan accounting, and adjustments related to MTM "
    "accounting for the FedEx Freight investment and utilization of "
    "the FedEx Freight spin-off dividend."
)


def test_labeled_value_etl_line():
    assert _is_labeled_value_line(ETR_LINE)
    assert not _opens_footnote_def(ETR_LINE)


def test_labeled_value_variants():
    # $ figure, parenthesized negative, bare % figure after the label.
    assert _is_labeled_value_line("(EPS) $16.55 to $17.75 Prior to adjustments.")
    assert _is_labeled_value_line("(FCF) ($0.50) - ($0.10) Guidance range.")
    assert _is_labeled_value_line("(EBITDA) 23% Compared to the prior forecast.")
    assert _is_labeled_value_line("(ETR) ~$16.55 Prior to adjustments.")
    for ln in (
        "(EPS) $16.55 to $17.75 Prior to adjustments.",
        "(FCF) ($0.50) - ($0.10) Guidance range.",
        "(EBITDA) 23% Compared to the prior forecast.",
    ):
        assert not _opens_footnote_def(ln)


def test_labeled_value_requires_all_caps_label():
    # Mixed-case labels are table-header residue, not labeled values.
    assert not _is_labeled_value_line("(Unaudited)(Unaudited)")
    assert not _is_labeled_value_line("(Loss) Attributable to noncontrolling interests")
    assert _opens_footnote_def("(Unaudited)(Unaudited)")
    assert _opens_footnote_def("(Loss) Attributable to noncontrolling interests")


def test_labeled_value_requires_value_token():
    # An all-caps label followed by prose is not a labeled value — the
    # paren shape still opens a footnote block there.
    assert not _is_labeled_value_line("(ETR) Prior to adjustments, the rate holds.")
    assert _opens_footnote_def("(ETR) Prior to adjustments, the rate holds.")
    # A bare number after the label is not value-shaped either (the
    # repair-side predicate's conditions, mirrored exactly).
    assert not _is_labeled_value_line("(EPS) 16.55 per share.")


def test_numeric_and_single_letter_keys_still_open_footnotes():
    assert _opens_footnote_def("(1) Non-GAAP measures are defined as adjusted results.")
    assert _opens_footnote_def("(a) Represents the impact of restructuring charges.")
    assert not _is_labeled_value_line("(1) $5.00 per share is the target.")
    assert not _is_labeled_value_line("(a) $5 million of charges were recorded.")


def test_paren_prose_continuations_unchanged():
    # Batch 176 shapes: still not footnote definitions, still not
    # labeled values.
    assert not _opens_footnote_def("(MRC) protocol, and segment routing over IPv6 (SRv6) ...")
    assert not _is_labeled_value_line("(MRC) protocol, and segment routing over IPv6 (SRv6) ...")
    assert not _opens_footnote_def("(IV) KEYTRUDA. Merck also announced results.")
    assert not _is_labeled_value_line("(IV) KEYTRUDA. Merck also announced results.")


def test_fdx_2026_05_31_keeps_etr_row():
    html = (CACHE / "FDX_2026-05-31.html").read_text(encoding="utf-8")
    g = extract_management_guidance(html)
    assert g is not None
    assert "(ETR) ~23% Prior to CY 2026 additional MTM adjustments" in g
    # The sibling split rows survive too.
    assert "(Continuing Operations) $16.55 to $17.75" in g
    assert "(Continuing Operations) $16.90 to $18.10" in g


def test_fdx_2026_09_30_keeps_etr_row():
    html = (CACHE / "FDX_2026-09-30.html").read_text(encoding="utf-8")
    g = extract_management_guidance(html)
    assert g is not None
    assert "(ETR) ~22.5% Compared to the prior forecast of ~23%." in g
