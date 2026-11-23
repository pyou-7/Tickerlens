"""Batch 239: the split-currency guidance table — Simon Property
Group's guidance tables put the currency symbol and the amount in
separate cells ("$" / "6.67"), so the flattened text carries a lone
"$" line followed by a bare-decimal line. The guidance collector's
admin skip dropped the number as a "99.1" exhibit-version fragment
(_ADMIN_LINE_RE's ^\\d+\\.\\d+$ alternative), losing the table's
values, and the fuser never formed the row because a lone "$" is not
a value line.

The fix is in the extractor (src/tickerlens/data/filings.py):
_is_split_table_value keeps a bare-decimal line when the previous
collected line is a lone "$" or a guidance-table label; the
value-line predecessor was tried and reverted — Elevance's membership
table chains bare decimals after plain value lines ("1,025" /
"29.9"), and keeping those spends the 30-line collection budget and
drops the table's tail. _merge_split_currency_values fuses "$" +
"6.67" into a "$6.67" value line before the fuse loop; and a lone
"End" is now a droppable header token, so a wrapped "Low End" /
"High End" header drops whole instead of leaving orphan "End" lines
once the rows fuse.

Blast over all 1,699 cached exhibits (guidance + highlights): 8
guidance diffs, all pure-adds with 0 figures removed — SPG x7
(per-share ranges $6.47-$7.47 / $12.40-$13.30 restored, plus the
depreciation values 5.45 / 6.13) and ELV 2024-03-31 (reconciliation
values $1.93 / $1.35 / $0.75 / $0.03 / $3.15 restored); 0 highlights
diffs. The repair re-syncs the new-guidance rows under gates F (AMT
x3, CLX, SPG x5, MCO x2 — plus SPG 2024-12-31 and 2025-12-31, which
were in sync with the old extraction) and H (GEV x2).

All pins are synthetic except the live SPG pins, which run the real
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
    _clean_guidance_result,
    _is_guidance_header_token_line,
    _is_split_table_value,
    _merge_split_currency_values,
    extract_management_guidance,
)
from batch239_repair import (  # noqa: E402
    _gate_f_passes,
    _gate_h_passes,
    _is_fused_row_line,
    _is_values_tail,
)

CACHE = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html")


def test_split_table_value_after_dollar_cell():
    # The SPG shape: a lone "$" cell line proves the bare decimal
    # after it is a value, not a version fragment.
    assert _is_split_table_value("6.67", "$")
    assert _is_split_table_value("12.40", "$")


def test_split_table_value_after_label():
    # A label directly followed by a bare decimal is a value too.
    assert _is_split_table_value(
        "6.67", "Estimated net income attributable to common stockholders per diluted share"
    )
    # But a bare decimal after a plain value line is NOT kept — see
    # the docstring: Elevance's chained change-% decimals would spend
    # the collection budget and drop the table's tail.
    assert not _is_split_table_value("29.9", "1,025")
    assert not _is_split_table_value("6.92", "$6.67")


def test_split_table_value_rejects_version_fragment():
    # A bare "99.1" after prose, a heading, or an all-caps label is
    # still the version fragment — the guard never fires there.
    assert not _is_split_table_value("99.1", "The Company expects growth.")
    assert not _is_split_table_value("99.1", "EXHIBIT")
    assert not _is_split_table_value("99.1", "2025 Guidance")
    # And a non-decimal line is never a split value.
    assert not _is_split_table_value("Page 3", "$")
    assert not _is_split_table_value("2025", "$")


def test_merge_split_currency_values():
    assert _merge_split_currency_values(["$", "6.67", "$", "6.92"]) == [
        "$6.67",
        "$6.92",
    ]
    # Parenthesized negatives merge too.
    assert _merge_split_currency_values(["$", "(0.42)"]) == ["$(0.42)"]
    # Thousands-grouped amounts merge; bare years and page numbers
    # never do.
    assert _merge_split_currency_values(["$", "1,234"]) == ["$1,234"]
    assert _merge_split_currency_values(["$", "2025"]) == ["$", "2025"]
    assert _merge_split_currency_values(["$", "5"]) == ["$", "5"]
    # A "$" with no following number line passes through.
    assert _merge_split_currency_values(["Revenue", "$"]) == ["Revenue", "$"]


def test_clean_guidance_result_fuses_split_currency_rows():
    collected = [
        "2025 Guidance",
        "Low",
        "End",
        "High",
        "End",
        "Estimated net income attributable to common stockholders per diluted share",
        "$",
        "6.67",
        "$",
        "6.92",
        "Estimated Real Estate FFO per diluted share",
        "$",
        "12.40",
        "$",
        "12.65",
    ]
    out = _clean_guidance_result(collected)
    assert (
        "Estimated net income attributable to common stockholders per diluted share: $6.67 / $6.92"
        in out
    )
    assert "Estimated Real Estate FFO per diluted share: $12.40 / $12.65" in out
    # No orphan header or placeholder lines survive.
    assert "Low" not in out
    assert "End" not in out
    assert "$" not in out


def test_lone_end_is_droppable_header_token():
    assert _is_guidance_header_token_line("End")
    assert _is_guidance_header_token_line("end")
    # The batch-233 pins still hold.
    assert _is_guidance_header_token_line("Low")
    assert _is_guidance_header_token_line("Low End High End")
    assert not _is_guidance_header_token_line("Full Year 2024")
    assert not _is_guidance_header_token_line("2025")


def test_spg_2025_03_31_keeps_table_values():
    html = (CACHE / "SPG_2025-03-31.html").read_text(encoding="utf-8")
    g = extract_management_guidance(html)
    assert g is not None
    assert (
        "Estimated net income attributable to common stockholders per diluted share: $6.67 / $6.92"
        in g
    )
    assert "Estimated Real Estate FFO per diluted share: $12.40 / $12.65" in g
    assert "\n$\n" not in g
    # The preamble's FFO range still reads.
    assert "reaffirming its outlook for Real Estate FFO of\u2009 $12.40 to $12.65" in g


def test_spg_2025_06_30_keeps_table_values():
    html = (CACHE / "SPG_2025-06-30.html").read_text(encoding="utf-8")
    g = extract_management_guidance(html)
    assert g is not None
    assert (
        "Estimated net income attributable to common stockholders per diluted share: $6.63 / $6.83"
        in g
    )
    assert "Estimated Real Estate FFO per diluted share: $12.45 / $12.65" in g


def test_spg_2026_06_30_current_previous_columns():
    # The four-column current/previous table fuses all four units.
    html = (CACHE / "SPG_2026-06-30.html").read_text(encoding="utf-8")
    g = extract_management_guidance(html)
    assert g is not None
    assert (
        "Estimated net income attributable to common stockholders per diluted share: $6.47 / $7.47 / $6.61 / $6.76"
        in g
    )
    assert "Estimated Real Estate FFO per share: $13.20 / $13.30 / $13.10 / $13.25" in g


# --- Gate F: new-guidance-found -------------------------------------

def test_fused_row_line_shapes():
    # Colon-joined rows (the fuser's own output, which
    # _split_guidance_fused_row cannot re-split: the " / " joiner and
    # the "(2)" key break its value-line predicate) and bare rows
    # (a ">" qualifier, a verb-y label).
    assert _is_fused_row_line("Discretionary capital projects(2): $ 780 to $ 810")
    assert _is_fused_row_line(
        "Estimated net income attributable to common stockholders per diluted share: $6.67 / $6.92"
    )
    assert _is_fused_row_line("Total Tenant Billings Growth ~4.3% >7% ~5.5%")
    assert _is_fused_row_line("Start-up capital projects 65 to 85")
    assert _is_fused_row_line("Ground lease purchases: 125 to 145")
    # Not rows: prose, a bare label, a heading.
    assert not _is_fused_row_line(
        "The Company is raising the midpoints of its full year 2024 outlook."
    )
    assert not _is_fused_row_line("Total Property")
    assert not _is_fused_row_line("FULL YEAR 2024 OUTLOOK")


def test_values_tail_shapes():
    assert _is_values_tail("$6.67 / $6.92")
    assert _is_values_tail("~4.3% >7% ~5.5%")
    assert _is_values_tail("65 to 85")
    assert _is_values_tail("$ 780 to $ 810")
    assert not _is_values_tail("and segment guidance of:")
    assert not _is_values_tail("Per diluted share")


_AMT_STORED = """2024 Outlook (1) : ($ in millions, except per share amounts.)

Total property revenue (2)
$ 9,890 to $ 9,980 0.7%
Net income 1,992 to 2,072 48.6%
_______________
(1) 2024 outlook and the prior year period results for total property revenue.
(2) Includes U.S. & Canada segment property revenue of $5,245 million to $5,255 million."""

_AMT_NEW = """FULL YEAR 2024 OUTLOOK

The following full year 2024 estimates are based on a number of assumptions that management believes to be reasonable.

The Company is raising the midpoints of its full year 2024 outlook for total property revenue and Adjusted EBITDA by $15 million and $5 million, respectively.

2024 Outlook(1): ($ in millions, except per share amounts.)
Total property revenue(2): $ 9,890 to $ 9,980 0.7%
Net income: 1,992 to 2,072 48.6%
2024 Outlook for Total Tenant Billings Growth, at the midpoint, includes the following components(1)(2): (Totals may not add due to rounding.)
Organic Tenant Billings ~4.7% ~6% ~5%
Total Tenant Billings Growth ~4.7% >8% ~6%
Outlook for Capital Expenditures(1): ($ in millions, totals may not add due to rounding.)
Full Year 2024
Discretionary capital projects(2): $ 780 to $ 810
Ground lease purchases: 125 to 145
Start-up capital projects 65 to 85
Total: $ 1,500 to $ 1,610"""


def test_gate_f_amt_shape():
    # The American Tower shape: shared outlook table, added preamble
    # + Tenant Billings + Capex tables, removed footnote defs.
    assert _gate_f_passes(_AMT_STORED, _AMT_NEW)


def test_gate_f_refuses_different_vintage():
    # Same shape, but the new text drops a real guidance value the
    # stored row has (Net income 1,992 to 2,072) and adds an unrelated
    # table — no shared fused row anchors it.
    new = _AMT_NEW.replace(
        "Net income: 1,992 to 2,072 48.6%\n", ""
    ).replace(
        "Total property revenue(2): $ 9,890 to $ 9,980 0.7%\n",
        "Total property revenue(2): $ 9,000 to $ 9,100 0.7%\n",
    )
    assert not _gate_f_passes(_AMT_STORED, new)


_SPG_STUB_STORED = """Guidance Reconciliation

(1)
Includes reconciliation of consolidated net income to funds from operations."""

_SPG_STUB_NEW = """2025 Guidance

The Company’s estimates for net income attributable to common stockholders per diluted share and Real Estate FFO per diluted share for the year ending December 31, 2025 are included in the table below.

Estimated net income attributable to common stockholders per diluted share: $6.67 / $6.92

Estimated Real Estate FFO per diluted share: $12.40 / $12.65"""


def test_gate_f_stub_variant():
    # The Simon stub shape: the stored row is a figure-less stub,
    # the new text is the real guidance section from the same
    # exhibit.
    assert _gate_f_passes(_SPG_STUB_STORED, _SPG_STUB_NEW)


def test_gate_f_stub_refuses_removed_value():
    # A stub that somehow carries a value line must not re-sync
    # away — the stub variant only covers data-less removals.
    stored = _SPG_STUB_STORED + "\n\nNet income: 1,992 to 2,072 48.6%"
    assert not _gate_f_passes(stored, _SPG_STUB_NEW)


# --- Gate H: historical-results-table drop --------------------------

_GEV_STORED = """2025 financial guidance. ”

Guidance:

GE Vernova is reaffirming its 2025 financial guidance of revenue of $36-$37 billion, high-single digits adjusted EBITDA margin*, free cash flow* of $2.0-$2.5 billion, and segment guidance of:

• Power : Mid-single digit organic revenue* growth and 13%-14% segment EBITDA margin.
• Wind : Organic revenue* down mid-single digits and $200-$400 million of segment EBITDA losses.
Total Company Results

Three months ended December 31

Twelve months ended December 31

(Dollars in millions, except per share)

2024

2023

GAAP Metrics

Total revenues

$10,559

$10,045

Net income (loss)

$484

$205"""

_GEV_NEW = """Guidance:

GE Vernova is reaffirming its 2025 financial guidance of revenue of $36-$37 billion, high-single digits adjusted EBITDA margin*, free cash flow* of $2.0-$2.5 billion, and segment guidance of:

• Power: Mid-single digit organic revenue* growth and 13%-14% segment EBITDA margin.
• Wind: Organic revenue* down mid-single digits and $200-$400 million of segment EBITDA losses."""


def test_gate_h_gev_shape():
    # The GE Vernova shape: the stored row trails into a historical
    # results table; the new text keeps only the guidance.
    assert _gate_h_passes(_GEV_STORED, _GEV_NEW)


def test_gate_h_refuses_table_without_gaap_metrics():
    # The same trailing table, but without the GAAP Metrics line it
    # is not provably a historical-results table.
    stored = _GEV_STORED.replace("GAAP Metrics\n\n", "")
    assert not _gate_h_passes(stored, _GEV_NEW)


def test_gate_h_refuses_added_figure():
    # A pure remove that also adds a figure is not a table drop.
    new = _GEV_NEW + "\n\nExtra guidance: $99.99"
    assert not _gate_h_passes(_GEV_STORED, new)
