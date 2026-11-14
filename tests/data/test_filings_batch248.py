"""Batch 248 regression tests.

Gate S7 (scripts/batch248_repair.py): the spacing-only swap. A stored
highlights row whose only difference from the live extraction is
spacing — a stray space inside a word (\"Re cent\", \"M acquarie\",
\"JD Powe r\", \"Strategi c\"), a space inside curly quotes (\"See “
Reconciliation ...\"), a spaced slash (\"Y /Y\"), a space before a
closing paren (\"IBX® )\") — may be re-synced to the live text.

The safety property is `spacing_equivalent`: the two lines share
the same non-space character sequence AND the same digit runs, and
differ only by spaces. The digit-run condition is load-bearing — it
is what keeps \"10 0\" vs \"100\" (a figure change, not spacing) from
ever passing. The gate is symmetric: every live line must also be
in stored, spacing-equivalent to a stored line, or S3 residue, so
live cannot add content under the spacing cover. The full-cache
census re-syncs exactly the 15 probe rows (SKIP-loss 183 -> 168)
and moves no other cohort.
"""
import sys

sys.path.insert(0, "scripts")

from batch248_repair import spacing_equivalent, sweep_gate_s7

_HEADLINE = "Applied Digital Reports Fiscal Second Quarter 2025 Results"
_BULLET = "• Revenues: $63.9 million, up 51% from the prior year period"
# Stored boilerplate carries the seed-era spaces inside the quotes;
# live has them glued. Same words, same figures, spacing only.
_BOILER_STORED = (
    "Adjusted EBITDA, Adjusted Operating Loss, Adjusted Net Loss, and "
    "Adjusted Net Loss per Diluted Share are non-GAAP measures. A "
    "reconciliation of each of these Non-GAAP Measures to the most "
    "directly comparable financial measure presented in accordance with "
    "accounting principles generally accepted in the United States "
    "(“GAAP”) is set forth below. See “ Reconciliation of GAAP to "
    "Non-GAAP Measures. ”"
)
_BOILER_LIVE = _BOILER_STORED.replace("“ Reconciliation", "“Reconciliation").replace(
    'Measures. ”', 'Measures.”'
)
_HEADING_STORED = "Re cent Operational Highlights"
_HEADING_LIVE = "Recent Operational Highlights"
_OPS_BULLET = (
    "• Applied Digital Corporation entered today into a $5.0 billion "
    "perpetual preferred equity financing facility, with investment "
    "vehicles of funds managed by Macquarie Asset Management (“MAM”)."
)


def _stored() -> str:
    return "\n".join(
        [_HEADLINE, _BULLET, _BOILER_STORED, _HEADING_STORED, _OPS_BULLET]
    )


def _live() -> str:
    return "\n".join(
        [_HEADLINE, _BULLET, _BOILER_LIVE, _HEADING_LIVE, _OPS_BULLET]
    )


def test_spacing_equivalent_split_words() -> None:
    assert spacing_equivalent("Re cent Operational Highlights", "Recent Operational Highlights")
    assert spacing_equivalent("M acquarie Promissory Note", "Macquarie Promissory Note")
    assert spacing_equivalent("ranked #1 in the JD Powe r 2026", "ranked #1 in the JD Power 2026")
    assert spacing_equivalent("Strategi c Highlights", "Strategic Highlights")
    assert spacing_equivalent("Cash and Cash Equivalen ts was $4.32 billion",
                               "Cash and Cash Equivalents was $4.32 billion")
    assert spacing_equivalent("fractionation volumes wer e up 12%",
                               "fractionation volumes were up 12%")


def test_spacing_equivalent_quote_slash_paren() -> None:
    assert spacing_equivalent(
        'See “ Reconciliation of GAAP to Non-GAAP Measures. ”',
        'See “Reconciliation of GAAP to Non-GAAP Measures.”',
    )
    assert spacing_equivalent("helping customers succeed. ”", "helping customers succeed.”")
    assert spacing_equivalent("Slightly Below 10% Y /Y", "Slightly Below 10% Y/Y")
    assert spacing_equivalent("Business Exchange™ (IBX® ) data centers",
                               "Business Exchange™ (IBX®) data centers")


def test_spacing_equivalent_refuses_digit_run_merge() -> None:
    # "10 0" vs "100" share a non-space sequence but not digit runs:
    # a space between two digits is a figure change, never spacing.
    assert not spacing_equivalent("Net loss: $10 0 million", "Net loss: $100 million")
    assert not spacing_equivalent("up 5 1% from the prior year", "up 51% from the prior year")
    assert not spacing_equivalent("Q1 FY2 6 results", "Q1 FY26 results")


def test_spacing_equivalent_refuses_content_change() -> None:
    assert not spacing_equivalent("Revenues: $63.9 million", "Revenues: $64.9 million")
    assert not spacing_equivalent("Revenues: $63.9 million", "Revenues: $63.9 billion")
    assert not spacing_equivalent("Net loss: $138.7 million", "Net loss: $138.7 million, up 51%")
    assert not spacing_equivalent("Recent Operational Highlights", "Recent Highlights")
    # Known boundary, stated honestly: "a ward" vs "award" share a
    # non-space sequence, so the check passes on characters alone.
    # The digit-run guard is the figure protection; a word-boundary
    # merge without digits is not a figure, and the gate's other
    # conditions (headline alignment, dateline, symmetric coverage)
    # are what keep such a line from blessing a swap on its own.
    assert spacing_equivalent("a ward for excellence", "award for excellence")


def test_gate_s7_repairs_apld_shape() -> None:
    assert sweep_gate_s7(_stored(), _live()) is None


def test_gate_s7_refuses_digit_run_merge() -> None:
    # "$10 0 million" vs "$100 million": the space sits between two
    # digits, so the digit runs differ and no rescue applies. (A
    # "$63 .9" shape would not test the guard — norm already
    # collapses a space before a period — so the test uses a
    # space between digits, which norm leaves alone.)
    stored = _stored() + "\n• Net loss: $10 0 million"
    live = _live() + "\n• Net loss: $100 million"
    assert sweep_gate_s7(stored, live) == "loss"


def test_gate_s7_refuses_live_added_bullet() -> None:
    live = _live() + "\n• New pipeline of $2.0 billion announced today"
    assert sweep_gate_s7(_stored(), live) == "added-content"


def test_gate_s7_refuses_dropped_content() -> None:
    live = "\n".join([_HEADLINE, _BULLET, _BOILER_LIVE, _HEADING_LIVE])
    assert sweep_gate_s7(_stored(), live) == "loss"
