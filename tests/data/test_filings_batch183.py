"""Batch 183: a $-to-$ guidance range is a statement, never a table row —
and a guidance-range sub-headline never consumes lede budget.

The batch-178 guard exempted $-to-$ ranges only in the 81-120-char band
of _is_lede_data_row, so short ranges still classified as data rows: GPC's
55-char "Reaffirms 2026 Outlook for Adjusted EPS of $7.50 to $8.00"
sub-headline was dropped from the live lede (stored rows kept it only
because they were extracted before the budget changes). Worse, merely
un-dropping it traded the sub-headline for a real paragraph — the 6-line
budget starved AXP's results dateline, BBY's CEO quote and GPC's adjusted
net income paragraph. So the fix has two halves: the predicate exemption
is hoisted to every $-carrying branch (as a STATEMENT — >=4 alphabetic
words, so Moody's bare "$10.40 to $11.00" outlook-table fragment stays a
data row), and a range statement served in the pre-body zone never
consumes a budget line.
"""
from tickerlens.data.filings import (
    _is_lede_data_row,
    _is_lede_dollar_range_statement,
    extract_press_release_highlights,
)

GPC_RANGE = "Reaffirms 2026 Outlook for Adjusted EPS of $7.50 to $8.00"
AXP_RANGE = (
    "FY 2025 GUIDANCE FOR REVENUE GROWTH OF 8% TO 10% AND "
    "EPS OF $15.00 TO $15.50"
)
BBY_RANGE = "Expects FY25 Non-GAAP Diluted EPS of $5.75 to $6.20"
COR_RANGE = (
    "Adjusted Diluted EPS Guidance Range Raised to $13.25 to $13.50 "
    "for Fiscal 2024"
)
GPC_NARROWS = (
    "Narrows 2026 Outlook for Adjusted EPS to $7.50 to $7.75 "
    "from $7.50 to $8.00"
)


def test_range_statement_predicate():
    # Attested guidance-range sub-headlines are statements.
    for ln in (GPC_RANGE, AXP_RANGE, BBY_RANGE, COR_RANGE, GPC_NARROWS):
        assert _is_lede_dollar_range_statement(ln), ln
    # A bare range fragment has no subject words — not a statement.
    assert not _is_lede_dollar_range_statement("$10.40 to $11.00")
    # A dense short range ("EPS $7.50 to $8.00", one word) is ambiguous
    # enough to stay a table row — no attested case needs it served.
    assert not _is_lede_dollar_range_statement("EPS $7.50 to $8.00")
    # No range at all.
    assert not _is_lede_dollar_range_statement(
        "Restructuring / Related Costs ~$0.06 ~$0.20"
    )


def test_range_statement_is_not_a_data_row():
    for ln in (GPC_RANGE, AXP_RANGE, BBY_RANGE, COR_RANGE, GPC_NARROWS):
        assert not _is_lede_data_row(ln), ln
    # The 81-120 band keeps its batch-178 behavior.
    assert not _is_lede_data_row(
        "FULL-YEAR 2024 GUIDANCE FOR REVENUE GROWTH OF 9% TO 11% AND "
        "EPS OF $12.65 TO $13.15"
    )


def test_bare_range_fragment_still_a_data_row():
    assert _is_lede_data_row("$10.40 to $11.00")
    assert _is_lede_data_row("EPS $7.50 to $8.00")


def test_real_short_rows_still_data_rows():
    assert _is_lede_data_row("Restructuring / Related Costs ~$0.06 ~$0.20")
    assert _is_lede_data_row(
        "Fair value of accruing debt and other income producing "
        "securities(5) $ 24,831 $ 23,643"
    )
    assert _is_lede_data_row(
        "Net income (loss) per share—diluted $0.65 $(3,903) N/A $0.55 $0.10"
    )
    assert _is_lede_data_row(
        "Diluted Net Earnings Per Common Share $ .44 $ .91 (52) %"
    )


def _extract(body_lines):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


def test_gpc_style_range_subheadline_is_free():
    # The GPC 2026-06-30 shape: headline, range sub-headline, second
    # sub-headline, dateline, quote, sales, net income, adjusted net
    # income — 6 counted lines after the free range line, so nothing
    # starves.
    out = _extract(
        [
            "Genuine Parts Company Reports Second Quarter 2026 Results",
            GPC_RANGE,
            "Updates Select Elements of 2026 Outlook",
            "ATLANTA -- Genuine Parts Company (NYSE: GPC), a leading global "
            "service provider of automotive and industrial replacement parts "
            "and value-added solutions, announced today its results for the "
            "second quarter ended June 30, 2026.",
            "“The GPC team delivered solid second quarter results, driven "
            "by continued sales growth and disciplined execution across our "
            "businesses,” said Will Stengel, Chairman and Chief Executive "
            "Officer. “Our teams performed well despite a dynamic global "
            "environment.”",
            "Sales were $6.5 billion, a 6.0% increase compared to $6.2 "
            "billion in the same period of the prior year. The improvement "
            "is attributable to a 3.4% increase in comparable sales, a net "
            "1.4% favorable impact of foreign currency and a 1.2% benefit "
            "from acquisitions.",
            "Net income was $228 million, or $1.65 per diluted earnings "
            "per share. This compares to net income of $255 million, or "
            "$1.83 per diluted share in the prior year period.",
            "Adjusted net income was $296 million, or $2.15 per diluted "
            "earnings per share. Adjusted net income excludes $69 million "
            "of after-tax adjustments, or $0.50 per diluted share, which "
            "relates to costs associated with the company's global "
            "restructuring initiative.",
        ]
    )
    assert out is not None
    assert GPC_RANGE in out
    assert "Updates Select Elements of 2026 Outlook" in out
    assert "Sales were $6.5 billion" in out
    assert "Net income was $228 million" in out
    # The freed budget line serves the final paragraph too.
    assert "Adjusted net income was $296 million" in out


def test_range_statement_past_dateline_is_not_free():
    # The same range line AFTER the dateline, with the budget already
    # full, is body prose under the hard cap — it does not jump the
    # queue past six complete paragraphs.
    out = _extract(
        [
            "Acme Reports Third Quarter Results",
            "ATLANTA -- Acme Corp (NYSE: ACME), a leading global service "
            "provider of automotive and industrial replacement parts and "
            "value-added solutions, announced today its results for the "
            "third quarter ended September 30, 2026.",
            "Sales were $6.5 billion, a 6.0% increase compared to $6.2 "
            "billion in the same period of the prior year. The improvement "
            "is attributable to a 3.4% increase in comparable sales and a "
            "net 1.4% favorable impact of foreign currency.",
            "Net income was $228 million, or $1.65 per diluted earnings "
            "per share. This compares to net income of $255 million, or "
            "$1.83 per diluted share in the prior year period.",
            "Adjusted net income was $296 million, or $2.15 per diluted "
            "earnings per share. Adjusted net income excludes $69 million "
            "of after-tax adjustments, or $0.50 per diluted share.",
            "“The team delivered solid results, driven by continued sales "
            "growth and disciplined execution across our businesses,” said "
            "the Chief Executive Officer. “Our teams performed well despite "
            "a dynamic global environment.”",
            "Cash flow from operations was $400 million, up 10 percent "
            "from the prior year period, driven by stronger earnings and "
            "improved working capital management across the business.",
            GPC_RANGE,
        ]
    )
    assert out is not None
    assert GPC_RANGE not in out
    assert "Cash flow from operations was $400 million" in out


def test_bare_range_fragment_never_served():
    # Moody's 2024-03-31 shape: the outlook table flattens "$10.40 to
    # $11.00" onto its own line between the dateline and the CEO quote.
    out = _extract(
        [
            "MOODY'S CORPORATION REPORTS RESULTS FOR FIRST QUARTER 2024",
            "NEW YORK, NY - May 2, 2024 - Moody's Corporation (NYSE: MCO), "
            "a leading global provider of credit ratings, research and "
            "risk analysis, today announced results for the first quarter "
            "of 2024, and updated select metrics within its outlook for "
            "full year 2024.",
            "$10.40 to $11.00",
            "“Our strong first quarter financial performance is a testament "
            "to the unique power of our franchise, delivering tremendous "
            "operating leverage as issuance markets rebound,” said the "
            "Chief Executive Officer.",
            "Revenue increased 21% from the prior-year period, driven by "
            "strong issuance across multiple asset classes and continued "
            "demand for the company's KYC solutions and industry-leading "
            "data. Moody's Investors Service revenue grew 35%, fueled by "
            "improved market conditions and opportunistic activity.",
        ]
    )
    assert out is not None
    assert "$10.40 to $11.00" not in out
    assert "Our strong first quarter financial performance" in out
    assert "Revenue increased 21%" in out
