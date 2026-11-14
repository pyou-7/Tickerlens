"""Batch 227: the wrap-fragment tail class — stored/live highlights ending
mid-sentence on a wrapped continuation (General Mills' "market share
trends", Nasdaq's "Annualized Recurring Revenue (ARR)4 of", Goldman's
"...during the second quarter of", Kroger's comma tails, Coinbase's
"...than any other company;" after a terminated sentence in the same
line, Genuine Parts' "...comparable sales. Segment", Berkshire's
impairment label under "Net earnings includes:", BlackRock's row label
glued to its " - Consolidated sponsored investment products" qualifier).

The fix lives in the final cleanup only (_clean_highlights_result): a
wrap-fragment drop (comma/semicolon end, dangling function word, open
quote, short lowercase noun phrase continuing an already-unfinished
line), a truncate-at-last-terminator for a fragment that follows a
terminated sentence in the same tail line, a colon-intro list-item
label rule, and a " - <qualifier>" strip in the row-label predicate.
Bullets without terminal periods are the house style (AGNC's ◦
sub-bullets, AIG's ■ bullets, Palantir's ◦ bullets, WTW's "Adjusted
Operating Margin was ...") and are never touched. The first blast
caught two false positives of the first cut — Cisco's "consecutive
quarter" (a wrapped bullet completion, not a cut) and Estee Lauder's
"Affirms Fiscal 2027 Outlook ... 3% to 5%;" (a ";" separating headline
items, not a sentence cut) — and both are now pinned as guards: the
short-fragment branch requires the previous line to already end
unfinished, and a ";" after a headline verb is never a cut.

Live pins run the extractor against the real cached exhibits; the unit
pins cover each new shape and its guards directly.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _clean_highlights_result,
    _is_trailing_list_item_label,
    _is_trailing_row_label,
    _is_trailing_wrap_fragment,
    _truncate_trailing_fragment,
    extract_management_guidance,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _last(hl: str) -> str:
    lines = [ln for ln in hl.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


# --- live pins: the wrap fragments are gone, the content stays -------


def test_gis_wrap_fragment_dropped() -> None:
    hl = extract_press_release_highlights(_read("GIS_2024-11-24.html"))
    assert hl is not None
    assert "market share trends" not in hl
    assert "to fund improved volume and" not in hl
    assert _last(hl).endswith("in the second half")


def test_gpc_truncated_at_terminator() -> None:
    hl = extract_press_release_highlights(_read("GPC_2025-12-31.html"))
    assert hl is not None
    assert _last(hl).endswith("comparable sales.")
    assert "Segment" not in _last(hl)


def test_coin_truncated_at_terminator() -> None:
    hl = extract_press_release_highlights(_read("COIN_2025-12-31.html"))
    assert hl is not None
    assert _last(hl).endswith("on that transition.")
    assert "Our customers trust us" not in hl


def test_brkb_list_item_cascade() -> None:
    hl = extract_press_release_highlights(_read("BRK.B_2025-12-31.html"))
    assert hl is not None
    assert "Other-than-temporary impairment" not in hl
    assert "Net earnings includes:" not in hl
    assert "Net earnings attributable to Berkshire shareholders" not in hl
    assert _last(hl).endswith("per share amounts).")


def test_blk_qualifier_row_label_dropped() -> None:
    hl = extract_press_release_highlights(_read("BLK_2025-12-31.html"))
    assert hl is not None
    assert "Consolidated sponsored investment products" not in hl
    assert "attributable TO noncontrolling interests" not in hl
    assert "HPS and Preqin Transactions" in hl


# --- live guard pins: genuine content tails survive -------------------


def test_csco_wrapped_bullet_completion_kept() -> None:
    # The first cut dropped this wrapped bullet's second line; the
    # previous-line-unfinished gate keeps it: the line above ends
    # "fifth", so "consecutive quarter" completes the bullet.
    hl = extract_press_release_highlights(_read("CSCO_2025-10-25.html"))
    assert hl is not None
    assert _last(hl) == "consecutive quarter"
    assert "Product orders up 13%" in hl


def test_el_headline_semicolon_kept() -> None:
    # The ";" separates headline items (the next line is another
    # headline, "Raises Outlook ..."), not a sentence cut.
    # Batch 252: the "Raises Outlook ..." %-range guidance line is
    # now served budget-free (it was eaten as a data row before), so
    # the dateline paragraph fits too and the semicolon line is no
    # longer last — the property pinned here is that it is still
    # present, uncut, as a headline item.
    hl = extract_press_release_highlights(_read("EL_2026-06-30.html"))
    assert hl is not None
    assert "Affirms Fiscal 2027 Outlook" in hl
    assert "of Organic Net Sales Growth of 3% to 5%;" in hl
    assert "Raises Outlook on Adjusted Operating Margin to 12.7% to 13.5%" in hl
    assert _last(hl).endswith(
        "today reported its financial results for its fiscal year ended June 30, 2026."
    )


def test_agnc_sub_bullet_kept() -> None:
    hl = extract_press_release_highlights(_read("AGNC_2025-09-30.html"))
    assert hl is not None
    assert "Comprised of $0.36 dividends per common share" in hl


def test_acn_complete_clause_kept() -> None:
    hl = extract_press_release_highlights(_read("ACN_2024-11-30.html"))
    assert hl is not None
    assert "GAAP EPS of $3.59" in hl


def test_dg_wrapped_headline_kept() -> None:
    hl = extract_press_release_highlights(_read("DG_2026-05-01.html"))
    assert hl is not None
    assert "of Directors Declares Quarterly Cash Dividend of $0.59 per share" in hl


def test_dal_wrapped_bullet_kept() -> None:
    hl = extract_press_release_highlights(_read("DAL_2024-12-31.html"))
    assert hl is not None
    assert "options to European destinations for Minneapolis customers" in hl


def test_awk_long_continuation_kept() -> None:
    hl = extract_press_release_highlights(_read("AWK_2025-09-30.html"))
    assert hl is not None
    assert "share of incremental interest income" in hl


def test_cart_footnote_digit_kept() -> None:
    hl = extract_press_release_highlights(_read("CART_2025-09-30.html"))
    assert hl is not None
    assert _last(hl).endswith("operational performance. 10")


def test_pltr_sub_bullet_kept() -> None:
    hl = extract_press_release_highlights(_read("PLTR_2024-12-31.html"))
    assert hl is not None
    assert "$165 million of net income" in hl


def test_adbe_guidance_range_kept() -> None:
    # Batch 229: the EPS guidance range no longer serves as a
    # highlight — the "Financial Targets" table it came from is
    # guidance, and the section collector now ends at that heading.
    # The range still exists, in the guidance extraction (Adobe's
    # "Financial Targets" section is now a recognized guidance
    # heading, so guidance extracts instead of returning None).
    hl = extract_press_release_highlights(_read("ADBE_2025-05-30.html"))
    assert hl is not None
    assert "Earnings per share GAAP: $4.00 to $4.05" not in hl
    gd = extract_management_guidance(_read("ADBE_2025-05-30.html"))
    assert gd is not None
    assert "Earnings per share GAAP: $4.00 to $4.05" in gd


def test_akam_footnote_asterisk_kept() -> None:
    hl = extract_press_release_highlights(_read("AKAM_2024-09-30.html"))
    assert hl is not None
    assert _last(hl).endswith("foreign exchange.*")


def test_aig_dagger_bullet_kept() -> None:
    hl = extract_press_release_highlights(_read("AIG_2025-09-30.html"))
    assert hl is not None
    assert "or 1% on a comparable basis" in hl


# --- unit pins: the wrap-fragment predicate and its guards ------------


def test_wrap_fragment_comma_and_semicolon() -> None:
    assert _is_trailing_wrap_fragment(
        "Our teams kept driving value for customers, improving execution in our stores,"
    )
    assert _is_trailing_wrap_fragment(
        "Our customers trust us to store more crypto than any other company;"
    )
    # A ";" after a headline verb separates headline items.
    assert not _is_trailing_wrap_fragment(
        "Affirms Fiscal 2027 Outlook of Organic Net Sales Growth of 3% to 5%;"
    )
    assert not _is_trailing_wrap_fragment(
        "Raises Outlook on Adjusted Operating Margin to 12.7% to 13.5%;"
    )


def test_wrap_fragment_dangling_word() -> None:
    assert _is_trailing_wrap_fragment(
        "Annualized Recurring Revenue (ARR)4 of"
    )
    assert _is_trailing_wrap_fragment(
        "Book value per common share increased by 1.6% during the second quarter of"
    )
    assert _is_trailing_wrap_fragment(
        "Reiterating expectations for full-year total revenue of $9.61 billion at the midpoint, including"
    )
    assert _is_trailing_wrap_fragment("After adjusting the results to exclude the")
    # A trailing figure is the object of its "of": not a dangle.
    assert not _is_trailing_wrap_fragment(
        "Return on equity (ROE) of 7.2% and Core Operating ROE* of 11.7%"
    )
    assert not _is_trailing_wrap_fragment(
        "GAAP EPS of $3.59, an increase of 16%, and an increase of 10% over adjusted EPS reported in first quarter fiscal 2024"
    )


def test_wrap_fragment_open_quote() -> None:
    assert _is_trailing_wrap_fragment(
        "“I joined Kroger because I believe it represents the best opportunity"
    )
    assert not _is_trailing_wrap_fragment(
        "“We are pleased with our first-quarter EPS performance,” said Todd Vasos."
    )


def test_wrap_fragment_short_lowercase_gated() -> None:
    # GIS: the previous line ends on a dangling "and", so the fragment
    # is a cut.
    assert _is_trailing_wrap_fragment(
        "market share trends",
        "Company updates full-year fiscal 2025 outlook to reflect increased investment to fund improved volume and",
    )
    # Cisco: the previous line ends "fifth", so the fragment completes
    # the bullet and stays.
    assert not _is_trailing_wrap_fragment(
        "consecutive quarter",
        "Product orders up 13% year over year, with double-digit growth in Networking product orders for the fifth",
    )
    # A figure-carrying or long lowercase continuation is a complete
    # item, not a fragment.
    assert not _is_trailing_wrap_fragment(
        "of Directors Declares Quarterly Cash Dividend of $0.59 per share",
        "Board",
    )
    assert not _is_trailing_wrap_fragment(
        "share of incremental interest income from the amended Homeowner Services Group (HOS) note",
        "Initiating 2025 earnings per share guidance range of $5.65 to $5.75, which includes $0.10 per share of",
    )


def test_wrap_fragment_terminated_and_bullets_kept() -> None:
    assert not _is_trailing_wrap_fragment(
        "Second-quarter results included certain timing benefits that are expected to reverse in the second half"
    )
    assert not _is_trailing_wrap_fragment(
        "• GAAP earnings per share of $0.91 increased 86% over prior year"
    )
    assert not _is_trailing_wrap_fragment(
        "◦ Comprised of $0.36 dividends per common share and $0.47 increase in tangible net book value per common share"
    )


# --- unit pins: truncate at the last terminator ------------------------


def test_truncate_semicolon_and_label_fragments() -> None:
    assert (
        _truncate_trailing_fragment(
            "positioned to capitalize on that transition. Our customers trust us to store more crypto than any other company;"
        )
        == "positioned to capitalize on that transition."
    )
    assert (
        _truncate_trailing_fragment(
            "were $1.5 billion, up 6.4% from the same period in 2024. The improvement is attributable to a 5.1% favorable impact of foreign currency and a 2.2% benefit from acquisitions, partially offset by a 0.9% decrease in comparable sales. Segment"
        ).endswith("comparable sales.")
    )
    assert (
        _truncate_trailing_fragment(
            "progress we are making. Our teams kept driving value for customers, improving execution in our stores,"
        )
        == "progress we are making."
    )
    assert (
        _truncate_trailing_fragment(
            "customers and shareholders. While the"
        )
        == "customers and shareholders."
    )


def test_truncate_keeps_complete_fragments() -> None:
    # A complete clause after the terminator stays.
    assert (
        _truncate_trailing_fragment("Revenue grew 5%. Net income was $1B")
        is None
    )
    # An imperative-led fragment is a complete sentence.
    assert (
        _truncate_trailing_fragment("We expect growth. See page 5 for details")
        is None
    )
    # A verb-carrying fragment stays ("remains" is a finite verb, and
    # the fragment is 3 words, over the 2-word no-verb bound).
    assert (
        _truncate_trailing_fragment("We raised guidance. Outlook remains strong")
        is None
    )
    # Abbreviation dots are never split points.
    assert (
        _truncate_trailing_fragment("U.S. sales grew 5% in the quarter") is None
    )
    assert (
        _truncate_trailing_fragment(
            "Acme Inc. Revenue grew 5% in the quarter"
        )
        is None
    )
    # A headline-verb ";" fragment is a headline item, not a cut.
    assert (
        _truncate_trailing_fragment(
            "Revenue grew 5%. Affirms Fiscal 2027 Outlook of 3% to 5%;"
        )
        is None
    )
    # Bullets are never truncated.
    assert (
        _truncate_trailing_fragment(
            "• Revenue grew 5%. Net income"
        )
        is None
    )


# --- unit pins: colon-intro list-item labels ---------------------------


def test_list_item_label_brkb() -> None:
    assert _is_trailing_list_item_label(
        "Other-than-temporary impairment of investments in Kraft Heinz and in Occidental",
        "Net earnings includes:",
    )
    # A guidance line under an intro carries figures: kept.
    assert not _is_trailing_list_item_label(
        "Revenue growth of 5% to 7% in fiscal 2026",
        "Outlook:",
    )
    # A short verbless line under an intro is a bullet fragment, not
    # a label.
    assert not _is_trailing_list_item_label(
        "Higher volumes in all segments",
        "Key drivers:",
    )
    # A label with a verb is content.
    assert not _is_trailing_list_item_label(
        "Impairment of investments in Kraft Heinz reduced fourth quarter earnings",
        "Net earnings includes:",
    )
    # No colon intro, no label.
    assert not _is_trailing_list_item_label(
        "Other-than-temporary impairment of investments in Kraft Heinz and in Occidental",
        "Net earnings attributable to Berkshire shareholders",
    )


# --- unit pins: row-label qualifier strip ------------------------------


def test_row_label_qualifier_strip() -> None:
    assert _is_trailing_row_label(
        "SUMMARY OF NONOPERATING INCOME (expense), less net income (loss) attributable TO noncontrolling interests - Consolidated sponsored investment products"
    )
    assert _is_trailing_row_label(
        "Net earnings attributable to Berkshire shareholders - Continuing operations"
    )
    # A qualifier carrying digits is not stripped.
    assert not _is_trailing_row_label(
        "Net earnings attributable to Berkshire shareholders - 2025 results"
    )
    # A heading with a " - " period suffix is not a row label.
    assert not _is_trailing_row_label(
        "Financial Comparisons - Third-Quarter Continuing Operations"
    )


# --- integration: the trim in _clean_highlights_result -----------------


def test_clean_highlights_wrap_fragment_cascade() -> None:
    body = (
        "Acme Reports Record Third Quarter 2025 Results and Raises Full Year Outlook Today\n\n"
        "• Revenue grew 12% to $5.2 billion in the quarter, with strong demand across all segments and continued momentum in the core business.\n"
        "• Adjusted earnings per share of $1.84 beat expectations, driven by margin expansion and disciplined cost management across the company.\n"
        "Company updates full-year fiscal 2025 outlook to reflect increased investment to fund improved volume and\n"
        "market share trends\n"
    )
    out = _clean_highlights_result(body)
    assert "market share trends" not in out
    assert "to fund improved volume and" not in out
    assert out.endswith("disciplined cost management across the company.")


def test_clean_highlights_truncate_keeps_content() -> None:
    body = (
        "Acme Reports Record Third Quarter 2025 Results and Raises Full Year Outlook Today\n\n"
        "• Revenue grew 12% to $5.2 billion in the quarter, with strong demand across all segments and continued momentum in the core business.\n"
        "As regulatory clarity emerges, we believe crypto will update all financial services, and Coinbase is well positioned to capitalize on that transition. Our customers trust us to store more crypto than any other company;\n"
    )
    out = _clean_highlights_result(body)
    assert out.endswith("on that transition.")
    assert "Our customers trust us" not in out
    assert "Revenue grew 12%" in out


def test_clean_highlights_wrap_floor_kept() -> None:
    # Below the 200-char floor the trim is refused entirely: a wart
    # is better than dropping the row (the batch-153 floor rule).
    body = "Short Headline\n\n• One short bullet.\nAnnualized Recurring Revenue (ARR)4 of\n"
    assert _clean_highlights_result(body) == body.strip()
