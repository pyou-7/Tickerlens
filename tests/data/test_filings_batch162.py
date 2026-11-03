"""Batch 162 regression tests: bare numbered footnotes ("1) See Table A ...")
no longer leak into the lede.

The batch-161 follow-up named numbered-footnote lines: Sempra numbers
its reconciliation-table footnote "1) See Table A for information
regarding non-GAAP financial measures." and Datadog its M&A-costs
footnote "1) The three months ended June 30, 2025 are adjusted for M&A
transaction costs ...". Neither matches the parenthesized footnote rule
("(1) ...") or the definition-verb rule ("1 Defined as ..."), so the
line is collected as lede prose — in SRE Q3 2024 / Q1 2025 / Q2 2025 it
sits mid-lede between the "following table" paragraph and the next real
prose paragraph, and in DDOG Q2 2025 the same way. The fix adds a bare
numbered-footnote rule ("^\\d{1,3}\\)\\s") plugged into the lede-loop
skip, the table-line predicate (so the tail trim can start on it), and
the headline skip (a footnote definition ahead of the headline is never
the headline, the batch-104 hazard in its bare form).
"""

from tickerlens.data.filings import (
    _LEDE_FOOTNOTE_NUM_RE,
    _is_lede_table_line,
    extract_press_release_highlights,
)


def _bare_release_html(*lines: str) -> str:
    body = "".join(f"<p>{ln}</p>" for ln in lines)
    return f"<html><body>{body}</body></html>"


def test_numbered_footnote_regex_positives() -> None:
    # Batch 162: the two attested shapes, plus multi-digit keys.
    assert _LEDE_FOOTNOTE_NUM_RE.match(
        "1) See Table A for information regarding non-GAAP financial measures."
    )
    assert _LEDE_FOOTNOTE_NUM_RE.match(
        "1) The three months ended June 30, 2025 are adjusted for M&A "
        "transaction costs of $1.4 million."
    )
    assert _LEDE_FOOTNOTE_NUM_RE.match("12) Excludes stock-based compensation.")
    assert _LEDE_FOOTNOTE_NUM_RE.match("2) Represents net new annual contract value.")


def test_numbered_footnote_regex_negatives() -> None:
    # A year-led or quarter-led headline is not a footnote (the batch-104
    # guards), nor is a numeric-opening prose sentence, a dot-numbered
    # list item, or the parenthesized form (a different rule owns it).
    assert not _LEDE_FOOTNOTE_NUM_RE.match("2025 outlook raised")
    assert not _LEDE_FOOTNOTE_NUM_RE.match("1Q26 record quarter")
    assert not _LEDE_FOOTNOTE_NUM_RE.match("1 billion in buybacks")
    assert not _LEDE_FOOTNOTE_NUM_RE.match("2024 was a record year for growth.")
    assert not _LEDE_FOOTNOTE_NUM_RE.match("1. See Table A for more information.")
    assert not _LEDE_FOOTNOTE_NUM_RE.match("(1) See Table A for more information.")
    assert not _LEDE_FOOTNOTE_NUM_RE.match("Table 1) Summary of results.")


def test_numbered_footnote_is_table_line_despite_termination() -> None:
    # Batch 162: a numbered footnote is a terminated sentence, so it
    # passes the termination gate that would otherwise clear it — the
    # rule sits before that gate, like the table-intro sentence (156).
    assert _is_lede_table_line(
        "1) See Table A for information regarding non-GAAP financial measures."
    )
    assert _is_lede_table_line(
        "1) The three months ended June 30, 2025 are adjusted for M&A "
        "transaction costs of $1.4 million."
    )
    # A terminated prose sentence with no footnote marker is not.
    assert not _is_lede_table_line(
        "We remain focused on executing our business plan."
    )


def test_sre_shaped_lede_drops_footnote_keeps_prose_after_it() -> None:
    # Batch 162: SRE Q3 2024's shape — the footnote sits between the
    # "following table" paragraph and the CPUC paragraph. The footnote
    # must not consume a lede slot, and the prose after it must still
    # be collected (it was the paragraph the batch-161 repair gained).
    html = _bare_release_html(
        "Sempra Reports Third-Quarter 2024",
        "SAN DIEGO, Nov. 6, 2024 -- Sempra (NYSE: SRE) today reported "
        "third-quarter 2024 earnings, prepared in accordance with "
        "generally accepted accounting principles (GAAP), of $638 million, "
        "or $1.00 per diluted share, compared to third-quarter 2023 GAAP "
        "earnings of $721 million, or $1.14 per diluted share.",
        "The reported financial results reflect certain significant items "
        "as described on an after-tax basis in the following table of GAAP "
        "earnings, reconciled to adjusted earnings, for the third quarter "
        "and first nine months of 2024 and 2023.",
        "1) See Table A for information regarding non-GAAP financial measures.",
        "Last month, the CPUC issued a proposed decision on the general "
        "rate cases for Sempra California's utilities, which center on "
        "improving safety and reliability in alignment with California's "
        "clean energy goals while stabilizing energy bills.",
    )
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "See Table A" not in result
    assert "1) See Table A" not in result
    assert "CPUC issued a proposed decision" in result
    assert "following table of GAAP earnings" in result


def test_ddog_shaped_long_footnote_dropped() -> None:
    # Batch 162: DDOG Q2 2025's shape — a long M&A-costs footnote
    # definition is footnote prose, not a highlight, however long.
    html = _bare_release_html(
        "Datadog Reports Second Quarter 2025 Results",
        "NEW YORK, Aug. 7, 2025 -- Datadog, Inc. (NASDAQ: DDOG) today "
        "announced financial results for its second quarter ended June 30, "
        "2025, with revenue of $826 million, an increase of 28% year over year.",
        "1) The three months ended June 30, 2025 are adjusted for M&A "
        "transaction costs of $1.4 million, and these adjustments are "
        "applied prospectively, as these costs relate to acquisitions "
        "completed during the period.",
        "We delivered strong second quarter results with revenue growth "
        "of 28% year over year, driven by broad-based demand across our "
        "platform and continued momentum with larger customers.",
        "Our platform now serves more than 28,000 customers, including "
        "over 3,400 customers with annual run-rate revenue of $100,000 or "
        "more, and we continue to see durable expansion as customers adopt "
        "additional products across observability, security, and AI.",
    )
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "M&A transaction costs" not in result
    assert "revenue growth of 28%" in result


def test_numbered_footnote_never_becomes_headline() -> None:
    # Batch 162: a footnote definition sitting ahead of the real headline
    # (the batch-104 hazard in its bare numbered form) must not be picked.
    html = _bare_release_html(
        "1) See Table A for information regarding non-GAAP financial measures.",
        "Sempra Reports Third-Quarter 2024",
        "SAN DIEGO, Nov. 6, 2024 -- Sempra (NYSE: SRE) today reported "
        "third-quarter 2024 earnings of $638 million, or $1.00 per diluted "
        "share, compared to third-quarter 2023 GAAP earnings of $721 million, "
        "or $1.14 per diluted share, in a strong quarter for the company.",
        "We are pleased with our operational and financial results for the "
        "third quarter and remain focused on executing our business plan "
        "for growth across our utilities and infrastructure businesses.",
        "Sempra's GAAP earnings for the first nine months of 2024 were "
        "$2.152 billion, or $3.38 per diluted share, compared with GAAP "
        "earnings of $2.293 billion, or $3.63 per diluted share, in the "
        "first nine months of 2023, reflecting solid execution across "
        "the company's regulated utilities and infrastructure portfolio.",
    )
    result = extract_press_release_highlights(html)
    assert result is not None
    assert result.startswith("Sempra Reports Third-Quarter 2024")
    assert "See Table A" not in result


def test_section_footnote_lines_dropped_between_bullets() -> None:
    # Batch 162: DDOG Q2 2025's shape — the section collector is the one
    # collection path with no footnote handling, so the M&A-costs footnote
    # sits between the section bullets. Footnote lines drop after
    # qualification (the batch-140 lone-marker pattern), so the floor and
    # the cap see the same lines as before; the bullets on both sides
    # survive. The parenthesized form drops too — one hazard class.
    html = _bare_release_html(
        "Datadog Announces Second Quarter 2025 Financial Results",
        "NEW YORK, Aug. 7, 2025 -- Datadog, Inc. (NASDAQ: DDOG) today "
        "announced financial results for its second quarter ended June 30, "
        "2025, with revenue of $827 million, an increase of 28% year over year.",
        "Second Quarter Highlights:",
        "•Revenue was $827 million, an increase of 28% year-over-year.",
        "•GAAP operating loss was $(36) million; GAAP operating margin was (4)%.",
        "•Non-GAAP operating income was $164 million; non-GAAP operating "
        "margin was 20%. (1)",
        "1) The three months ended June 30, 2025 are adjusted for M&A "
        "transaction costs of $1.4 million, and these adjustments are "
        "applied prospectively, as these costs were not material to the "
        "consolidated results of operations in the prior periods.",
        "(2) Free cash flow is defined as net cash provided by operating "
        "activities less purchases of property and equipment.",
        "•Operating cash flow was $200 million, with free cash flow of $165 million.",
        "•Cash, cash equivalents, and marketable securities were $3.9 "
        "billion as of June 30, 2025.",
    )
    result = extract_press_release_highlights(html)
    assert result is not None
    assert "M&A transaction costs" not in result
    assert "Free cash flow is defined as" not in result
    assert "Revenue was $827 million" in result
    assert "Operating cash flow was $200 million" in result
    assert "Cash, cash equivalents, and marketable securities" in result


def test_section_footnote_helper() -> None:
    # Batch 162: the three footnote forms drop from sections; a real
    # bullet (even one carrying a trailing "(1)" marker) is not a footnote.
    from tickerlens.data.filings import _is_section_footnote_line

    assert _is_section_footnote_line(
        "1) See Table A for information regarding non-GAAP financial measures."
    )
    assert _is_section_footnote_line(
        "(1) During the year ended December 31, 2025, the company ..."
    )
    assert _is_section_footnote_line("1 Defined as remaining performance obligation.")
    assert _is_section_footnote_line("*Non-GAAP Financial Measure")
    assert not _is_section_footnote_line(
        "•Non-GAAP operating margin was 20%. (1)"
    )
    assert not _is_section_footnote_line(
        "•Revenue was $827 million, an increase of 28% year-over-year."
    )
    assert not _is_section_footnote_line("Second Quarter Highlights:")
