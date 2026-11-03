"""Batch 168 regression tests: footnote second sentences + paren wrap tails.

Closes the batch-167 COIN Q3 FY2024 follow-ups in full. The stored Q3
FY2024 row is the title + rounding note + the [1] footnote itself, and
its live text served two footnote residues:

1. The [1] footnote's SECOND sentence ("These losses were $92 million
   / after reflecting the tax impact."). The flattening puts the
   sentence break on a line boundary, so the block stops at the first
   sentence's termination and the second sentence is served as lede.
   (Q4 FY2024's identical shape escapes only because its second
   sentence starts mid-line, "These gains were" sharing the termination
   line.) A capital-led sentence after a terminated definition is
   otherwise indistinguishable from new prose, so the guard is anaphora:
   the line must open with an anaphoric determiner (These/This/Those/
   That/Both/Such) whose noun appears in the definition just consumed.
2. The [3] definition's "USDC (" wrap tail ("USDC (net of USDC lent or
   / pledged as collateral)."). The 4-cap lead fails the 2-3-cap
   abbreviation branch of _is_plausible_continuation, so the block stops
   after "cash and cash equivalents and" and the tail is served.
"""
from tickerlens.data.filings import (
    _footnote_def_block_len,
    _is_plausible_continuation,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def _coin_q3_2024_footnote_block() -> list[str]:
    # Verbatim lines 9-20 of the Q3 FY2024 shareholder letter
    # (q324shareholderletter.htm), then the line that ends the block.
    return [
        "[1] Net income included $121 million",
        "in pre-tax losses on our crypto",
        "asset investment portfolio, the vast",
        "majority of which were unrealized.",
        "These losses were $92 million",
        "after reflecting the tax impact.",
        "[2] Adjusted EBITDA is a non-GAAP",
        "financial measure.",
        "[3] $USD resources is defined as",
        "cash and cash equivalents and",
        "USDC (net of USDC lent or",
        "pledged as collateral).",
        "For additional financial information",
    ]


def test_coin_q3_2024_footnote_block_consumes_twelve_lines() -> None:
    lines = _coin_q3_2024_footnote_block()
    assert _footnote_def_block_len(lines, 0) == 12
    # The referral sentence after the block is not a definition.
    assert _footnote_def_block_len(lines, 12) == 0


def test_anaphoric_second_sentence_needs_noun_in_definition() -> None:
    # "These results ..." after a definition that never says "results":
    # the block stops — real prose after the legend is never eaten.
    lines = [
        "[1] Net income included $121 million",
        "in pre-tax losses on our crypto",
        "asset investment portfolio, the vast",
        "majority of which were unrealized.",
        "These results demonstrate our progress.",
        "Q3 was a solid quarter for Coinbase.",
    ]
    assert _footnote_def_block_len(lines, 0) == 4
    # Plural mismatch is still a stop: "Both measurements" vs the
    # definition's singular "measurement" (Q4 FY2025 attested shape,
    # deliberately uncovered — the noun test is exact, not stemmed).
    # The bare-term definition chains from the keyed opener, as in the
    # real letter.
    lines = [
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
        "Both measurements represent the",
        "product of the quantity of assets",
    ]
    assert _footnote_def_block_len(lines, 0) == 11
    # A fresh-subject second sentence is still new prose.
    lines = [
        "[1] Adjusted EBITDA is a non-GAAP financial",
        "measure.",
        "Coinbase delivered strong Q4 results.",
    ]
    assert _footnote_def_block_len(lines, 0) == 2


def test_paren_abbreviation_tail_is_plausible_continuation() -> None:
    # The Q3 FY2024 [3] tail: 4-cap lead + lowercase parenthetical.
    assert _is_plausible_continuation("USDC (net of USDC lent or")
    assert _is_plausible_continuation("USDC (net of USDC loaned or")
    # A tail that terminates on its own line is still the same tail.
    assert _is_plausible_continuation(
        "USDC (net of USDC lent or pledged as collateral)."
    )
    # The figure-carrying variant stays out: digits are the guard.
    assert not _is_plausible_continuation(
        "USDC (net of USDC lent or pledged as collateral as of Dec. 31, 2024)."
    )
    # A paren opening with a capital is not a lowercase parenthetical.
    assert not _is_plausible_continuation("USDC (Net of USDC lent or")


def test_coin_q3_2024_end_to_end() -> None:
    # The full Q3 FY2024 head in miniature: title, date, short rounding
    # note, the [1]/[2]/[3] footnote block, the orphaned referral
    # sentence, then the letter prose. The stored row is the title +
    # rounding note + the [1] footnote itself; the live text must serve
    # the prose under the title with no footnote residue.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Third Quarter 2024",
            "October 30, 2024",
            "Note: Figures presented may not",
            "sum precisely due to rounding.",
            "[1] Net income included $121 million",
            "in pre-tax losses on our crypto",
            "asset investment portfolio, the vast",
            "majority of which were unrealized.",
            "These losses were $92 million",
            "after reflecting the tax impact.",
            "[2] Adjusted EBITDA is a non-GAAP",
            "financial measure.",
            "[3] $USD resources is defined as",
            "cash and cash equivalents and",
            "USDC (net of USDC lent or",
            "pledged as collateral).",
            "For additional financial information",
            "and a reconciliation between",
            "GAAP and non-GAAP results,",
            "please refer to the reconciliation of",
            "GAAP to Non-GAAP results table",
            "in this shareholder letter and our",
            "Q3’24 Form 10-Q filed with the",
            "SEC on October 30, 2024.",
            "Q3 was a solid quarter for Coinbase across our three priorities for 2024: driving revenue, crypto",
            "utility, and regulatory clarity.",
            "In Q3, we generated $1.2 billion in total revenue and $75 million in net income*. Q3 was our 7th",
            "consecutive quarter of positive Adjusted EBITDA, which was $449 million.",
        )
    )
    assert hl is not None
    assert hl.split("\n")[0] == "Third Quarter 2024"
    assert "Q3 was a solid quarter for Coinbase" in hl
    assert "These losses were" not in hl
    assert "after reflecting the tax impact" not in hl
    assert "pre-tax losses on our crypto" not in hl
    assert "USDC (net of USDC" not in hl
    assert "pledged as collateral" not in hl
    assert "Adjusted EBITDA is a non-GAAP" not in hl
    assert "sum precisely due to rounding" not in hl
    assert "For additional financial information" not in hl
