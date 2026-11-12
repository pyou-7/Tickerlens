"""Batch 237: the header / footnote-drop / tail-furniture re-sync — 13
stored management_guidance rows re-synced to the batch-235 extraction
(AAL x3, DAL, ADSK, CHD x2, DPZ, GIS x2, META, MU, V).

Gate extensions, all in the repair gate (scripts/batch236_repair.py),
not the extractor — the live extraction was already clean for these
rows; only the stored rows were stale:
- Press-release header triple: a stored row that ends on (or is
  interrupted by) the release header — title line / dateline / "Page N",
  always in that order and consecutive — is now chrome. AAL x3.
- Def-continuation guard: a lowercase-starting line is never a table
  label (labels are capitalized metric noun phrases), so Delta's two
  footnote-def continuations ("for historical comparison figures",
  "impact of the CrowdStrike-caused outage in 2024") are chrome now.
- Tail furniture: a trailing removed run at/after a furniture opener
  (boilerplate marker or short non-guidance heading) whose lines carry
  no $ or % figure and are not value lines — webcast notices, company
  descriptions, safe harbors, Regulation G definitions, product
  highlights, corporate-news sections. CHD x2, GIS x2, ADSK, DPZ,
  META, MU, V.
- Glued footnote keys ("globe1:") now normalize like the spaced stored
  form ("globe 1 :") — Domino's.
- Labeled-value guard: a line opening with a non-numeric parenthesized
  label followed immediately by a value figure ("(ETR) ~23% ...") is
  NOT footnote chrome — FedEx's ETR row is dropped by the live
  extraction, and crediting it would delete the ~23% figure from the
  stored row. FDX stays skipped; fixing the opener is an extractor
  change for the next batch.

All pins are synthetic (stored, new) pairs reproducing each shape —
the suite reads no database — plus the repair dry-run as the live
verification of the 13 real rows.
"""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))


def _load_script(name: str):
    path = REPO / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rep = _load_script("batch236_repair")
fix = _load_script("batch237_repair")


def test_header_triple_is_chrome():
    lines = [
        "Total Revenue YoY: Up 7% - 9%",
        "Operating Margin: 6% - 8%",
        "American Airlines Reports Fourth-Quarter and Full-Year 2024 Financial Results",
        "Jan. 23, 2025",
        "Page 3",
    ]
    assert rep._chrome_flags(lines) == [False, False, True, True, True]


def test_header_triple_needs_all_three_lines():
    # Title + dateline without the page line is not a header run.
    lines = [
        "Total Revenue YoY: Up 7% - 9%",
        "American Airlines Reports Fourth-Quarter and Full-Year 2024 Financial Results",
        "Jan. 23, 2025",
    ]
    assert rep._chrome_flags(lines) == [False, False, False]
    # A dateline alone is not chrome either.
    assert rep._chrome_flags(["Jan. 23, 2025"]) == [False]


def test_header_gate_aal_shape():
    stored = (
        "Total Revenue YoY: Up 7% - 9%\n"
        "Operating Margin: 6% - 8%\n"
        "American Airlines Reports Fourth-Quarter and Full-Year 2024 Financial Results\n"
        "Jan. 23, 2025\n"
        "Page 3"
    )
    new = "Total Revenue YoY: Up 7% - 9%\nOperating Margin: 6% - 8%"
    assert rep._diff_explainable(stored, new) == []
    assert fix._gate_d_passes(stored, new)


def test_continuation_lowercase_prose_is_chrome():
    # Delta 2024-12-31: the two continuations the batch-236 guard
    # rejected because the table-label predicate reads lowercase prose
    # as a label.
    lines = [
        "Total Revenue YoY",
        "Up 7% - 9%",
        "1 Non-GAAP measures; Refer to Non-GAAP reconciliations",
        "for historical comparison figures",
        "2 Year-over-year EPS growth excludes the 45-cent",
        "impact of the CrowdStrike-caused outage in 2024",
        "3 Adjusted debt to EBITDAR",
    ]
    assert rep._chrome_flags(lines) == [
        False, False, True, True, True, True, True,
    ]


def test_labeled_value_line_is_not_chrome():
    assert rep._is_labeled_value_line(
        "(ETR) ~23% Prior to CY 2026 additional MTM adjustments"
    )
    assert rep._is_labeled_value_line("(Margin) 11% - 14% segment EBITDA margin")
    # A numeric footnote key with prose is a real def, not a value row.
    assert not rep._is_labeled_value_line(
        "(1) See GAAP to Non-GAAP reconciliation at the end of this document."
    )
    assert not rep._is_labeled_value_line("(Unaudited)")
    assert not rep._is_labeled_value_line("Total Revenue $5.25 billion")
    # ...and the gate does not credit the FedEx ETR line as chrome.
    assert rep._chrome_flags(
        ["(ETR) ~23% Prior to CY 2026 additional MTM adjustments"]
    ) == [False]


def test_labeled_value_row_stays_blocked():
    # FedEx shape: the ETR figure would be lost on re-sync, so gate D
    # must refuse — the figure sits in a line that is neither chrome
    # nor tail furniture.
    stored = (
        "Revenue growth: 3% - 5%\n"
        "(ETR) ~23% Prior to CY 2026 additional MTM adjustments\n"
        "Corporate Overview\n"
        "FedEx Corp. (NYSE: FDX) provides customers worldwide with transportation services."
    )
    new = "Revenue growth: 3% - 5%"
    assert rep._diff_explainable(stored, new) != []
    assert not fix._gate_d_passes(stored, new)


def test_tail_furniture_opener():
    assert rep._is_tail_furniture_opener("Government Investigations Closed")
    assert rep._is_tail_furniture_opener(
        "Establishment of New Class C Common Stock"
    )
    assert rep._is_tail_furniture_opener("Product Highlights")
    assert rep._is_tail_furniture_opener("Corporate Overview")
    assert rep._is_tail_furniture_opener(
        "Church & Dwight Co., Inc. (NYSE: CHD) will host a webcast to discuss results."
    )
    # A guidance heading can never open a furniture tail.
    assert not rep._is_tail_furniture_opener("Fiscal 2026 Outlook")
    assert not rep._is_tail_furniture_opener("Outlook")
    assert not rep._is_tail_furniture_opener("Total Revenue YoY: Up 7% - 9%")


def test_tail_furniture_gate_gis_shape():
    stored = (
        "Total Revenue YoY: Up 7% - 9%\n"
        "Operating Margin: 6% - 8%\n"
        "General Mills will issue pre-recorded management remarks today, March 19, 2025, at approximately 6:30 a.m.\n"
        "Central time (7:30 a.m. Eastern time) and will hold a live, webcasted question and answer session beginning at 8:00 a.m.\n"
        "made available at www.generalmills.com/investors."
    )
    new = "Total Revenue YoY: Up 7% - 9%\nOperating Margin: 6% - 8%"
    assert rep._diff_explainable(stored, new) == []
    assert fix._gate_d_passes(stored, new)


def test_tail_furniture_dollar_line_voids_tail():
    stored = (
        "Total Revenue YoY: Up 7% - 9%\n"
        "General Mills will issue pre-recorded management remarks today, March 19, 2025, at approximately 6:30 a.m.\n"
        "Revenue was $5.25 billion."
    )
    new = "Total Revenue YoY: Up 7% - 9%"
    assert not fix._gate_d_passes(stored, new)


def test_tail_furniture_must_be_a_suffix():
    # The same webcast notice mid-text (guidance follows it) is not a
    # tail — the run after the last kept line is empty.
    stored = (
        "Total Revenue YoY: Up 7% - 9%\n"
        "General Mills will issue pre-recorded management remarks today, March 19, 2025.\n"
        "Operating Margin: 6% - 8%"
    )
    new = (
        "Total Revenue YoY: Up 7% - 9%\n"
        "Operating Margin: 6% - 8%"
    )
    assert not fix._gate_d_passes(stored, new)


def test_glued_footnote_key_normalizes():
    assert rep._norm_words("globe1:") == "globe 1"
    stored = (
        "The Company now expects the following given the challenging "
        "macroeconomic environment 1 :\n"
        "Revenue: $1.00 - $1.10"
    )
    new = (
        "The Company now expects the following given the challenging "
        "macroeconomic environment1:\n"
        "Revenue: $1.00 - $1.10"
    )
    assert rep._diff_explainable(stored, new) == []


def test_gate_a_fuse_only_still_passes():
    stored = "Revenue\n$1.00 - $1.10"
    new = "Revenue: $1.00 - $1.10"
    assert fix._gate_a_passes(stored, new)


def test_visa_shape_near_identical_replace_plus_tail():
    # V 2024-09-30: the pointer line differs only by a space before the
    # final period; the webcast / Investor Day notices are the tail.
    stored = (
        "Financial Outlook\n"
        "The earnings presentation contains the financial outlook for fiscal first quarter and full-year 2025. "
        "The presentation and other related materials are available on the Visa Investor Relations website at investor.visa.com .\n"
        "Visa's executive management team will host a live audio webcast beginning at 5:00 p.m. Eastern Time today."
    )
    new = (
        "Financial Outlook\n"
        "The earnings presentation contains the financial outlook for fiscal first quarter and full-year 2025. "
        "The presentation and other related materials are available on the Visa Investor Relations website at investor.visa.com."
    )
    assert rep._diff_explainable(stored, new) == []
    assert fix._gate_d_passes(stored, new)
