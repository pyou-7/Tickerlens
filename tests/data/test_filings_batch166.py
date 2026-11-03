"""Batch 166 regression tests: footnote-definition blocks skip as blocks.

Coinbase's letters carry a fourth footnote-definition shape the
single-line regexes never match: a numeric key + bare capitalized term,
the definition verb on the NEXT line ("1 Coinbase Total Trading Volume /
comprises Spot Trading Volume / and Derivatives Trading Volume."),
followed by chained bare-term definitions ("Spot Trading Volume is the
total / U.S. dollar equivalent value of spot ..."). And the single-line
shapes only ever dropped the key line — a wrapped definition's
continuation lines ("3 Trading Volume represents the / total US dollar
equivalent value of / ...") were served as lede/section content
whenever a path reached them. A fifth, bracketed, shape ("[1] Adjusted
EBITDA is a non-GAAP financial measure." / "measure.") sits ahead of
the prose in the Q2 FY2025 letter and starves its lede.

The fix adds _footnote_def_block_len: the key line plus its wrapped
continuations (while the definition is unterminated and the next line
is a plausible wrap) plus any chained definitions that follow a
terminated one. Only sentence termination ends a definition — there is
deliberately no completeness gate, because a wrapped line can look
complete ("[3] $USD resources is defined as cash and cash" carries a
5-word object, yet the definition wraps onto "equivalents and USDC
..."). A headline-shaped next line is never a plausible wrap, so GEV's
single-line legend never eats the headline that follows it. A
figure-dense continuation ("million and $687 million in pre-tax gains
...") is lowercase-led, so it consumes — it must never be treated as a
table line.
"""
from tickerlens.data.filings import (
    _footnote_def_block_len,
    _is_bare_term_def_opener,
    _opens_footnote_def,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def _coin_q4_2025_footnote_block() -> list[str]:
    # Verbatim lines 239-255 of the Q4 FY2025 shareholder letter
    # (q425shareholderletter.htm), then the lines that end the block.
    return [
        "3 Coinbase Total Trading Volume",
        "comprises Spot Trading Volume",
        "and Derivatives Trading Volume.",
        "Spot Trading Volume is the total",
        "U.S. dollar equivalent value of spot",
        "matched trades transacted",
        "between a buyer and seller",
        "through our platform, plus half of",
        "the value of trades that we routed",
        "off our platform for fulfillment,",
        "during the period of measurement.",
        "Derivatives Trading Volume is the",
        "total U.S. dollar equivalent value of",
        "the notional amount of derivatives",
        "trades transacted between a buyer",
        "and seller through our platform",
        "during the period of measurement.",
        # Second sentence of the same footnote ("Both measurements
        # represent the product ..."): the block stops here by design —
        # a capital-led sentence after a terminated definition is
        # indistinguishable from new prose. Documented limitation.
        "Both measurements represent the",
        # Wrapped-term key ("4 Coinbase Crypto Trading Volume / Market
        # Share is defined as ..."): the verb sits on the second line,
        # so the key never opens a block. Documented limitation.
        "4 Coinbase Crypto Trading Volume",
        "Market Share is defined as",
        # Body prose after the block.
        "2025 was a strong year for the crypto markets overall.",
    ]


def test_coin_q4_2025_block_consumes_seventeen_lines() -> None:
    lines = _coin_q4_2025_footnote_block()
    assert _footnote_def_block_len(lines, 0) == 17
    # The second sentence and the wrapped-term key do not extend it.
    assert _footnote_def_block_len(lines, 17) == 0
    assert _footnote_def_block_len(lines, 18) == 0


def test_complete_looking_key_line_still_wraps() -> None:
    # No completeness gate: "[3] $USD resources is defined as cash and
    # cash" carries a 5-word object, yet the definition wraps onto a
    # lowercase-led line — the wrap is decided by the NEXT line's shape,
    # not this line's. The whole [3]/[4]/[5] chain consumes as one block.
    lines = [
        "[3] $USD resources is defined as cash and cash",
        "equivalents and USDC (net of USDC loaned or",
        "pledged as collateral).",
        "[4] Assets under custody (\u201cAUC\u201d) is defined as the",
        "total US dollar equivalent value of USDC and crypto",
        "assets held separately on behalf of customers in",
        "digital wallets within our cold storage custody",
        "services, calculated based on the market price on the",
        "date of measurement.",
        "[5] Trading volume represents the total US dollar",
        "equivalent value of spot matched trades transacted",
        "between a buyer and seller through our platform",
        "during the period of measurement.",
        "Figures have been rounded for presentation purposes",
    ]
    assert _footnote_def_block_len(lines, 0) == 13


def test_bare_term_opener_predicate() -> None:
    assert _is_bare_term_def_opener("Spot Trading Volume is the total")
    assert _is_bare_term_def_opener("Derivatives Trading Volume is the")
    assert _is_bare_term_def_opener("Monthly Transacting User is defined as a consumer")
    # Figures are prose, not a definition opener.
    assert not _is_bare_term_def_opener("Total Trading Volume was $295 billion, up 24% Q/Q.")
    assert not _is_bare_term_def_opener("Consumer Trading Volume was $59 billion, up 37% Q/Q.")
    # One-word terms and lowercase-led lines are not openers.
    assert not _is_bare_term_def_opener("Revenue is expected to grow next year.")
    assert not _is_bare_term_def_opener("the value of trades that we routed")


def test_opens_footnote_def_predicates() -> None:
    # Fourth shape: term-only key + verb-led next line.
    assert _opens_footnote_def(
        "1 Coinbase Total Trading Volume", "comprises Spot Trading Volume"
    )
    assert _opens_footnote_def("3 Trading Volume", "represents the total")
    # The verb requirement is the guard: a numbered heading whose next
    # line is prose does not open a block.
    assert not _opens_footnote_def(
        "1 Fourth Quarter Highlights", "Revenue grew 12 percent."
    )
    assert not _opens_footnote_def("1 billion in buybacks announced", "next line")
    assert not _opens_footnote_def("2025 outlook raised on strong demand", "")
    assert not _opens_footnote_def("1Q26 record quarter for widgets", "")
    # Single-line shapes still open a block.
    assert _opens_footnote_def("1 Defined as remaining performance obligation (RPO)")
    assert _opens_footnote_def("1) See Table A for information regarding")
    assert _opens_footnote_def("(1) During the year ended December 31, 2024")
    assert _opens_footnote_def("*Non-GAAP Financial Measure")
    assert _opens_footnote_def("[1] Adjusted EBITDA is a non-GAAP financial measure.")


def test_call_notice_drops_from_lede() -> None:
    # Emerson's quarters end with a conference-call notice; once the
    # footnotes are dropped it backfills the lede. The notice line is
    # never highlights — it must be skipped even inside the budget.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Emerson Reports Second Quarter 2026 Results",
            "Net sales were $4.4 billion, up 4 percent in the quarter.",
            "Earnings per share were $1.48, up 10 percent.",
            "Operating cash flow was $1.1 billion in the quarter.",
            "Free cash flow was $900 million in the quarter.",
            "1 Results are presented on a continuing operations basis.",
            "2 Underlying orders do not include AspenTech.",
            "Today, beginning at 3:30 p.m. Central Time / 4:30 p.m. Eastern Time, Emerson management will discuss the second quarter results during an investor conference call. Participants can access a live webcast available at https://ir.emerson.com at the time of the call. A replay of the call will be available for 90 days. Conference call slides will be posted in advance of the call on the company website.",
            "Orders were up 6 percent in the quarter.",
            "Underlying sales were up 3 percent in the quarter.",
        )
    )
    assert hl is not None
    assert "conference call" not in hl.lower()
    assert "Results are presented" not in hl
    assert "Underlying orders do not include" not in hl
    assert "Orders were up 6 percent in the quarter." in hl
    assert "Underlying sales were up 3 percent in the quarter." in hl


def test_paren_footnote_stays_headline_eligible() -> None:
    # Batch 126 asymmetry, preserved: the headline loop does not skip
    # paren lines — "(B)Crude oil ..." must still headline (and return
    # None via the end check), and "(2026) ACME CORP ..." must still be
    # picked as the headline. The block scanner takes include_paren
    # for this; the lede paths keep the default True.
    assert _footnote_def_block_len(
        ["(B)Crude oil and condensate volumes are from UAE operations."],
        0,
        include_paren=False,
    ) == 0
    assert _footnote_def_block_len(
        ["(2026) ACME CORP REPORTS THIRD QUARTER RESULTS"],
        0,
        include_paren=False,
    ) == 0
    # ...but the lede path still drops a paren footnote block.
    assert _footnote_def_block_len(
        ["(1) During the year ended December 31, 2024, the company",
         "recorded a charge."],
        0,
    ) == 2


def test_opens_footnote_def_term_verb_variant() -> None:
    # Sixth variant: key + term + definition verb on the same line.
    assert _opens_footnote_def("3 Trading Volume represents the")
    assert _opens_footnote_def("4 Crypto Asset Volatility represents")
    assert _opens_footnote_def("1 Spot Trading Volume is")
    assert _opens_footnote_def(
        "1 Spot Trading Volume is presented on a matched basis,"
    )
    # Mixed-case term + negated verb (Emerson's footnotes).
    assert _opens_footnote_def("2 Underlying orders do not include AspenTech.")
    assert _opens_footnote_def(
        "2 Underlying sales excludes the impact of currency translation."
    )
    assert _opens_footnote_def(
        "2 Underlying sales exclude the impact of currency translation."
    )
    # Bare "is"/"are" before prose is not a definition pointer.
    assert not _opens_footnote_def("1 Total Revenue is expected to grow")
    assert not _opens_footnote_def("1 million shares are included in the total")
    # A digit in the term still blocks.
    assert not _opens_footnote_def("1 Fourth Quarter 2025 Results are presented")


def test_us_dollar_lead_continuation_consumes() -> None:
    # The Q1 FY2025 [4] AUC definition wraps onto "US dollar
    # equivalent value of ..." (all-caps token, no periods).
    lines = [
        "[4] Assets under custody (AUC) is defined as the total",
        "US dollar equivalent value of USDC and crypto assets",
        "held separately on behalf of customers in digital",
        "wallets within our cold storage custody services,",
        "calculated based on the market price on the date of",
        "measurement. Average AUC is calculated as the",
        "average daily balance over the period.",
        "Figures have been rounded for presentation purposes",
    ]
    # The block runs through "average daily balance over the period."
    # (the second sentence starts mid-line on the termination line, so
    # its wrap is consumed too); the rounding-note line ends it.
    assert _footnote_def_block_len(lines, 0) == 7


def test_shape_one_wrapped_definition_consumes_continuations() -> None:
    # "3 Trading Volume represents the" wraps over 6 lines in the Q4
    # FY2024 letter; the old code dropped only the key line.
    lines = [
        "3 Trading Volume represents the",
        "total US dollar equivalent value of",
        "spot matched trades transacted",
        "between a buyer and seller",
        "through our platform during the",
        "period of measurement.",
        "Consumer Trading Volume was $221.0 billion, up 195% Y/Y.",
    ]
    assert _footnote_def_block_len(lines, 0) == 6


def test_bracketed_footnote_block_consumes_wrap() -> None:
    lines = [
        "[1] Adjusted EBITDA is a non-GAAP financial",
        "measure.",
        "[2] Adjusted Net Income is a non-GAAP financial",
        "measure that excludes $1.5 billion in pre-tax gains on",
        "strategic investments.",
        "Fellow Shareholders,",
    ]
    # "[1]" is 2 lines, "[2]" is 3 lines; the prose line ends the block.
    assert _footnote_def_block_len(lines, 0) == 5


def test_dollar_led_continuation_consumes() -> None:
    # The Q4 FY2024 [1] footnote wraps onto a "$"-led line ("$357
    # million and $514 million after reflecting the tax"); a "$"-led
    # line is a figure continuation, never a new sentence after an
    # unterminated definition.
    lines = [
        "[1] Q4 and full year 2024 net income included $476",
        "million and $687 million in pre-tax gains on our crypto",
        "asset investment portfolio, respectively, the vast",
        "majority of which were unrealized. These gains were",
        "$357 million and $514 million after reflecting the tax",
        "impact, respectively.",
        "[2] Adjusted EBITDA is a non-GAAP financial",
        "measure.",
    ]
    assert _footnote_def_block_len(lines, 0) == 8


def test_year_led_sentence_does_not_continue() -> None:
    # A digit-led line that opens a year-led sentence ("2025 was a
    # strong year ...") is new prose, not a wrap — the block stops.
    lines = [
        "[1] Q4 and full year 2024 net income included $476",
        "million and $687 million in pre-tax gains on our crypto",
        "asset investment portfolio, respectively, the vast",
        "majority of which were unrealized. These gains were",
        "$357 million and $514 million after reflecting the tax",
        "impact, respectively.",
        "2025 was a strong year for the crypto markets overall.",
    ]
    assert _footnote_def_block_len(lines, 0) == 6


def test_gev_single_line_legend_never_eats_headline() -> None:
    # The batch-104 guard: a complete single-line definition followed
    # by the real headline consumes exactly one line.
    lines = [
        "1 Defined as remaining performance obligation (RPO)",
        "Third Quarter 2025 Results",
        "Revenue grew 12 percent.",
    ]
    assert _footnote_def_block_len(lines, 0) == 1
    lines = [
        "1 Includes restructuring charges",
        "Third Quarter 2025 Results",
        "Revenue grew 12 percent.",
    ]
    assert _footnote_def_block_len(lines, 0) == 1


def test_coin_fourth_shape_drops_from_lede() -> None:
    # The batch-165 hazard, replayed with a comma tail (which IS a
    # wrap tail, unlike the semicolon): without the block skip, the
    # finish rule would pull the footnote block in as a "continuation"
    # of the comma-ended budget line.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Fourth Quarter and Full Year 2025",
            "2025 was a strong year for Coinbase, both operationally and financially.",
            "We executed consistently against our goals, delivering or outperforming",
            "our revenue and expense guidance every quarter.",
            "We successfully launched the Everything Exchange to the delight of our",
            "customers, drove growth and diversification of revenue, and extended",
            "our multi-year track record of profitability,",
            "1 Coinbase Total Trading Volume",
            "comprises Spot Trading Volume",
            "and Derivatives Trading Volume.",
            "Spot Trading Volume is the total",
            "U.S. dollar equivalent value of spot",
            "matched trades transacted",
            "between a buyer and seller",
            "through our platform, plus half of",
            "the value of trades that we routed",
            "off our platform for fulfillment,",
            "during the period of measurement.",
            "Fellow Shareholders, Q3 was a strong quarter for Coinbase.",
        )
    )
    assert hl is not None
    assert "Coinbase Total Trading Volume" not in hl
    assert "comprises Spot Trading Volume" not in hl
    assert "Spot Trading Volume is the total" not in hl
    assert "profitability," in hl
    # The comma-ended budget line IS a wrap tail, so the batch-165
    # finish rule appends the next real line after the skipped block —
    # the finish line is prose, not footnote material.
    assert "Fellow Shareholders, Q3 was a strong quarter for Coinbase." in hl


def test_bracketed_footnotes_drop_from_lede() -> None:
    # The Q2 FY2025 letter shape: bracketed footnotes sit ahead of the
    # prose and starve the lede. With the block skip, the prose serves.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Second Quarter 2025",
            "July 31, 2025",
            "[1] Adjusted EBITDA is a non-GAAP financial",
            "measure.",
            "[2] Adjusted Net Income is a non-GAAP financial",
            "measure that excludes $1.5 billion in pre-tax gains on",
            "strategic investments.",
            "Fellow Shareholders, Q2 was a strong quarter for Coinbase.",
            "We drove solid financial results, maintained focus on shipping",
            "innovative products, and continued building the foundation",
            "of the Everything Exchange.",
        )
    )
    assert hl is not None
    assert "Adjusted EBITDA" not in hl
    assert "Adjusted Net Income" not in hl
    assert "Fellow Shareholders, Q2 was a strong quarter for Coinbase." in hl
