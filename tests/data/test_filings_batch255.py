"""Batch 255 regression tests.

Gate S12 (scripts/batch255_repair.py): S4 with the
stored-truncation rescue in the loss check. The shape: a stored
line the seeder truncated mid-sentence (trailing "…") whose full
text live carries — the stored line minus "…" is a strict prefix
of a live line that is strictly longer. CEG x3 (the "Nuclear
Operations" bullet / capacity-factor line cut at "…", live
carries it to its end plus one genuine "Natural Gas, Oil, and
Renewables Operations" bullet) and EQIX x2 (the same shape, once
the batch-255 norm fix glues the spaced "TM" trademark marker —
"Exchange TM" vs live "ExchangeTM" — and the space before a
closing bracket — "(IBX® )" vs "(IBX®)"). The full-cache blast
moves exactly those 5 rows (SKIP-loss 148 -> 143) and moves no
other cohort. DASH 2025-06-30 stays loss by design: its other
lost line runs the reverse direction (live's line is a prefix of
stored's — live drops the cohort-definition tail), and F x6 is
the same reverse direction throughout.
"""
import sys

sys.path.insert(0, "scripts")

from batch231_repair import norm
from batch255_repair import _is_truncated_prefix_of_live, sweep_gate_s12

# --- CEG shape: real truncated / full "Nuclear Operations" pair ---
_HEADLINE_CEG = "CONSTELLATION REPORTS SECOND QUARTER 2025 RESULTS"
_DATELINE_CEG = (
    "Baltimore, August 7, 2025-- Constellation Energy Corporation "
    "(Nasdaq: CEG) today reported its financial results for the "
    "second quarter of 2025."
)
_TOP_CEG = (
    "• GAAP Net Income of $0.38 per share and Adjusted (non-GAAP) "
    "Operating Earnings of $2.14 per share for the first quarter of 2025"
)
_NUCLEAR_TRUNC = (
    "• Nuclear Operations: Our nuclear fleet, including our owned output "
    "from the Salem and South Texas Project (STP) Generating Stations, "
    "produced 45,170 gigawatt-hours (GWhs) in the second quarter of "
    "2025, compared with 45,314 GWhs in the second quarter of 2024. "
    "Excluding Salem and STP, our nuclear plants at ownership achieved "
    "a 94.8% capacity factor for the second quarter of 2025, compared "
    "with 95.4% for the second quarter…"
)
_NUCLEAR_FULL = (
    "• Nuclear Operations: Our nuclear fleet, including our owned output "
    "from the Salem and South Texas Project (STP) Generating Stations, "
    "produced 45,170 gigawatt-hours (GWhs) in the second quarter of "
    "2025, compared with 45,314 GWhs in the second quarter of 2024. "
    "Excluding Salem and STP, our nuclear plants at ownership achieved "
    "a 94.8% capacity factor for the second quarter of 2025, compared "
    "with 95.4% for the second quarter of 2024. There were 41 planned "
    "refueling outage days in the second quarter of 2025 and 49 in the "
    "second quarter of 2024 for sites we operate. There were 22 "
    "non-refueling outage days in the second quarter of 2025 and three "
    "in the second quarter of 2024 for sites we operate."
)
_GAS_CEG = (
    "• Natural Gas, Oil, and Renewables Operations: The dispatch match "
    "rate for our gas and pumped storage fleet was 98.3% in the second "
    "quarter of 2025, compared with 98.0% in the second quarter of 2024."
)

_STORED_CEG = "\n".join(
    [_HEADLINE_CEG, _DATELINE_CEG, _TOP_CEG, _NUCLEAR_TRUNC]
)
_LIVE_CEG = "\n".join(
    [_HEADLINE_CEG, _DATELINE_CEG, _TOP_CEG, _NUCLEAR_FULL, _GAS_CEG]
)

# --- EQIX shape: real TM-spacing + truncated pair ---
_HEADLINE_EQIX = (
    "EQUINIX REPORTS STRONG FOURTH-QUARTER AND FULL-YEAR 2024 RESULTS"
)
_DATELINE_EQIX = (
    "Redwood City, February 12, 2025-- Equinix, Inc. (Nasdaq: EQIX) "
    "today reported results for the fourth quarter and full year ended "
    "December 31, 2024."
)
_AI_STORED = (
    "◦ In December, Equinix announced a private AI solution that enables "
    "businesses to train AI models in scalable, cost-efficient public "
    "and private clouds, while ensuring enhanced control, security and "
    "low-latency deployment on-premises. Utilizing the Dell AI Factory "
    "with NVIDIA, Equinix International Business Exchange TM (IBX® ) "
    "data centers provide a portfolio of products, solutions and "
    "services in a neutral, cloud-adjacent platform, allowing customers "
    "to securely connect to public clouds, colocation facilities, and "
    "their own private cloud and on-premises infrastructure."
)
_AI_LIVE = _AI_STORED.replace(
    "Exchange TM (IBX® )", "ExchangeTM (IBX®)"
)
_PUE_TRUNC = (
    "◦ In 2024, Equinix’s best-in-class operations team improved the "
    "company’s power usage effectiveness (PUE) by more than 6%, aiding "
    "customers in greening their digital supply chain. The company also "
    "achieved the highest-ranking score of the CDP’s prestigious "
    "“Climate Change A List” for the third consecutive year, and…"
)
_PUE_FULL = (
    "◦ In 2024, Equinix’s best-in-class operations team improved the "
    "company’s power usage effectiveness (PUE) by more than 6%, aiding "
    "customers in greening their digital supply chain. The company also "
    "achieved the highest-ranking score of the CDP’s prestigious "
    "“Climate Change A List” for the third consecutive year, and "
    "received its first MSCI “AAA-rating.”"
)
_GREEN_BOND = (
    "◦ In Q4, Equinix issued an additional €1.15 billion in green bonds "
    "bringing its total to approximately $6.9 billion, making it a top "
    "five U.S. issuer in the investment-grade green bond market."
)

_STORED_EQIX = "\n".join(
    [_HEADLINE_EQIX, _DATELINE_EQIX, _AI_STORED, _PUE_TRUNC]
)
_LIVE_EQIX = "\n".join(
    [_HEADLINE_EQIX, _DATELINE_EQIX, _AI_LIVE, _PUE_FULL, _GREEN_BOND]
)


def test_s12_passes_on_the_ceg_nuclear_bullet_shape() -> None:
    assert sweep_gate_s12(_STORED_CEG, _LIVE_CEG) is None


def test_s12_passes_on_the_eqix_tm_shape() -> None:
    # The TM line equalizes only through the batch-255 norm fix
    # ("Exchange TM (IBX® )" -> "ExchangeTM (IBX®)"); the truncated
    # PUE line is rescued by the S12 prefix check.
    assert norm(_AI_STORED) == norm(_AI_LIVE)
    assert sweep_gate_s12(_STORED_EQIX, _LIVE_EQIX) is None


def test_truncated_prefix_detector_is_exact() -> None:
    live_norm = [norm(_NUCLEAR_FULL)]
    assert _is_truncated_prefix_of_live(_NUCLEAR_TRUNC, live_norm)
    # A complete line (no "…") is never a truncation, even when it
    # prefixes a longer live line.
    assert not _is_truncated_prefix_of_live(_NUCLEAR_FULL, live_norm)
    # A short "…" line is a heading or label, not truncated prose.
    assert not _is_truncated_prefix_of_live(
        "• Short line…", ["• Short line continues here"]
    )
    # A live continuation that changes a figure is not the same text.
    changed = _NUCLEAR_FULL.replace("45,170", "45,171")
    assert not _is_truncated_prefix_of_live(
        _NUCLEAR_TRUNC, [norm(changed)]
    )
    # The prefix must be strict: a live line equal to the base is
    # not a continuation.
    assert not _is_truncated_prefix_of_live(
        _NUCLEAR_TRUNC, [norm(_NUCLEAR_TRUNC.rstrip("…").rstrip())]
    )


def test_s12_still_refuses_a_dropped_bullet() -> None:
    # Live drops the top bullet entirely: real content loss, not a
    # truncation — the gate must refuse.
    live = "\n".join(
        [_HEADLINE_CEG, _DATELINE_CEG, _NUCLEAR_FULL, _GAS_CEG]
    )
    assert sweep_gate_s12(_STORED_CEG, live) == "loss"


def test_s12_still_refuses_a_changed_figure() -> None:
    # The live continuation changes 45,170 to 45,171 GWhs: the
    # stored base is not a prefix of it, so the rescue cannot fire.
    live = _LIVE_CEG.replace("45,170", "45,171")
    assert sweep_gate_s12(_STORED_CEG, live) == "loss"


def test_s12_still_refuses_the_reverse_direction() -> None:
    # DASH / F shape: live's line is a prefix of stored's — live
    # truncates the paragraph and drops the cohort-definition tail.
    # That is a genuine loss, not a stored truncation.
    approach_full = (
        "Our approach to building DoorDash is relatively simple in "
        "concept, but as our business expands in scale and scope, we "
        "must continue to elevate our capabilities in order to maintain "
        "our high standards of execution across a broader surface area. "
        "Our team executed well in the first half of 2025 and we are "
        "excited by the opportunities to continue building through the "
        "rest of the year and beyond. For any given measurement period, "
        "a new DoorDash consumer cohort consists of consumers who placed "
        "their first order on the DoorDash Marketplace during that period."
    )
    approach_short = approach_full.split("For any given")[0].strip()
    stored = "\n".join(
        [_HEADLINE_CEG, _DATELINE_CEG, approach_full, _TOP_CEG]
    )
    live = "\n".join(
        [_HEADLINE_CEG, _DATELINE_CEG, approach_short, _TOP_CEG]
    )
    assert sweep_gate_s12(stored, live) == "loss"


def test_s12_still_refuses_an_added_table_row() -> None:
    # Live adds a table row under the bullets: the addition is
    # policed by S4's added-table check, not waved through.
    live = _LIVE_CEG + "\nTotal revenues $5,800 $5,600 3%"
    assert sweep_gate_s12(_STORED_CEG, live) == "added-table"


def test_s12_still_refuses_a_dangling_tail() -> None:
    # Live ends on a dangling heading: S4's tail check still fires.
    live = _LIVE_CEG + "\nOutlook:"
    assert sweep_gate_s12(_STORED_CEG, live) == "tail"


def test_norm_tm_trademark_spacing() -> None:
    # The seed-era extractor spaced the ASCII "TM" marker; the
    # current one emits it glued. norm canonicalizes both to glued.
    assert norm("Exchange TM (IBX") == "ExchangeTM (IBX"
    assert norm("Intelligence TM to further") == "IntelligenceTM to further"
    assert norm("Schwab Crypto TM , providing") == "Schwab CryptoTM, providing"
    assert norm("Teen Investor TM Account") == "Teen InvestorTM Account"
    # A standalone word "TM" is never glued to the previous word:
    # the capitalized-preceding-word anchor keeps "TM Forum" and
    # "TM mode" intact.
    assert norm("the TM Forum announced") == "the TM Forum announced"
    assert norm("TM mode is enabled") == "TM mode is enabled"
    # Figures still differ after norm: spacing-only, never content.
    assert norm("Net income $5.3B TM") != norm("Net income $5.4B TM")


def test_norm_closing_bracket_spacing() -> None:
    # A space before a closing bracket is spacing-only, like the
    # batch-242 space-before-comma/period rule.
    assert norm("Value (IBX® ) rose") == "Value (IBX®) rose"
    assert norm("Net income $5.3B )") != norm("Net income $5.4B )")
