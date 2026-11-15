"""Batch 257 regression tests.

Two things, both found while probing the AMT seeding gap:

1. Census-methodology pin (scripts/batch257_probe.py). The probe's
   census must short-circuit on norm equality BEFORE running the
   gate chain, because gate S4's policing can trip on the live text
   itself even when stored and live are identical: a lowercase
   second line reads as "fragment" (AAPL 2024-09-28, BRK.B x6,
   BRO 2026-09-30, SKYD 2026-06-30) and a chrome-stripped contact
   line reads as "added-table" (EIX x8). The first draft of this
   batch's probe ran the chain on every row and reported a phantom
   19-row regression (in-sync 1055 -> 1037, loss 142 -> 161) that
   was purely the missing fast path — the stored rows, the cached
   exhibits and the extractor were all unchanged (old-vs-new
   extractor output byte-identical on all 19 rows). The fast path
   now lives inside classify() so the decision is in one place,
   and the two shapes below pin it: S4 refuses, classify still
   says in-sync.

2. S12 refusal pin (scripts/batch255_repair.py). AMT 2024-09-30
   stays loss: its stored row is seed-era truncated mid-sentence
   ("...operations in India ("ATC TIPL" or "") with no "..."
   marker, so S12's truncation-prefix rescue cannot bless it, and
   live adds genuine bullets plus dateline/quote prose. The gate
   must keep refusing that shape — re-syncing it would bless
   quote-prose loss as if it were a truncation swap.
"""
import sys

sys.path.insert(0, "scripts")

from batch242_repair import sweep_gate_s4
from batch255_repair import sweep_gate_s12
from batch257_probe import classify

_FRAG = (
    "ACME CORP REPORTS FOURTH QUARTER 2024 RESULTS\n"
    "in the fourth quarter, revenue grew 5% to $100 million\n"
    "● Total revenue grew 5% to $100 million\n"
    "● Net income increased 10% to $20 million\n"
)

_EIX = (
    "Investor Relations: Sam Ramraj, (626) 302-2540\n"
    "EDISON INTERNATIONAL REPORTS SECOND QUARTER 2024 RESULTS\n"
    "● Total revenue increased 3% to $500 million\n"
    "● Net income increased 8% to $90 million\n"
)

# Real AMT 2024-09-30 shape: stored truncated mid-quote (no "..."),
# live carries the full bullet list plus dateline and quote prose.
_STORED_AMT = (
    "AMERICAN TOWER CORPORATION REPORTS THIRD QUARTER 2024 FINANCIAL RESULTS\n"
    "On September 12, 2024, American Tower Corporation (the \u201cCompany\u201d "
    "or \u201cAmerican Tower\u201d) completed the sale of 100% of the equity "
    "interests in its operations in India (\u201cATC TIPL\u201d or \u201c\n"
    "CONSOLIDATED HIGHLIGHTS\n"
    "Third Quarter 2024(1)\n"
    "\u25cf Total revenue grew by less than 0.1% to $2,522 million\n"
    "\u25cf Total property revenue decreased 1.0% to $2,470 million\n"
    "\u25cf Net income decreased 235.2% to a net loss of $(780) million(2)(3)(4)\n"
)
_LIVE_AMT = (
    "AMERICAN TOWER CORPORATION REPORTS THIRD QUARTER 2024 FINANCIAL RESULTS\n"
    "Third Quarter 2024(1)\n"
    "\u25cf Total revenue grew by less than 0.1% to $2,522 million\n"
    "\u25cf Total property revenue decreased 1.0% to $2,470 million\n"
    "\u25cf Net income decreased 235.2% to a net loss of $(780) million(2)(3)(4)\n"
    "\u25cf Adjusted EBITDA decreased 0.9% to $1,687 million\n"
    "\u25cf Net income attributable to AMT common stockholders decreased "
    "235.0% to a net loss of $(792) million(2)(3)(4)\n"
    "\u25cf AFFO attributable to AMT common stockholders increased 2.6% "
    "to $1,237 million\n"
    "\u25cf AFFO attributable to AMT common stockholders, as adjusted, "
    "increased 3.3% to $1,181 million(5)\n"
    "Boston, Massachusetts \u2013 October 29, 2024: American Tower "
    "Corporation (NYSE: AMT) today reported financial results for the "
    "quarter ended September 30, 2024.\n"
)


def test_census_fast_path_fragment_shape_is_in_sync() -> None:
    # S4 refuses the pair on its own policing (live's second line
    # starts lowercase), but stored == live, so the census must say
    # in-sync, not loss.
    assert sweep_gate_s4(_FRAG, _FRAG) == "fragment"
    assert classify(_FRAG, _FRAG, "") == "in-sync"


def test_census_fast_path_added_table_shape_is_in_sync() -> None:
    # The leading contact line is stripped from stored as chrome and
    # then reads as an added table line in live — again S4 refuses a
    # pair that is identical.
    assert sweep_gate_s4(_EIX, _EIX) == "added-table"
    assert classify(_EIX, _EIX, "") == "in-sync"


def test_census_fast_path_does_not_bless_real_loss() -> None:
    # Control: a genuinely different pair still classifies loss —
    # the fast path only fires on norm equality.
    assert classify(_STORED_AMT, _LIVE_AMT, "") == "loss"


def test_s12_refuses_mid_quote_truncation_without_ellipsis() -> None:
    # The stored line is cut mid-sentence with no "..." marker, so it
    # is not an S12 truncation-prefix shape: no stored line ends with
    # "..." and prefixes a longer live line.
    assert sweep_gate_s12(_STORED_AMT, _LIVE_AMT) is not None
