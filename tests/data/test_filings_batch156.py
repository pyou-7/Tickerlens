"""Batch 156 regression tests: a table-headed "Highlights" section with
no bullets must not pre-empt the lede.

The batch-155 GOOGL Q4 hazard, closed generically: a "Financial
Highlights" section whose content is table scaffolding — a table-intro
sentence plus a period header, >=150 chars, no bullets, and invisible to
_looks_like_financial_table — used to win as the only section candidate
and serve the stub instead of the lede's real bullets. The section is
now rejected when it hits a table break with no bullet lines, and the
lede skips the section's residue (heading, intro sentence, doubled
period header, space-separated-$ data rows) so the bullets surface.
"""

from tickerlens.data.filings import (
    _extract_highlights_sections,
    _is_lede_data_row,
    _is_lede_date_header,
    _is_lede_table_line,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

_ACME_LINES = (
    "Acme Corp Reports Fourth Quarter and Full Year 2025 Results",
    "SPRINGFIELD, Ill. – February 10, 2026 – Acme Corp (NASDAQ: ACME) today "
    "announced financial results for the fourth quarter and full year 2025.",
    "Acme delivered record revenue in the quarter, driven by strength "
    "across all segments and continued momentum in its cloud business.",
    "Fourth Quarter 2025 Financial Highlights",
    "The following table summarizes selected financial information for the "
    "periods presented. All amounts are unaudited and should be read in "
    "conjunction with the condensed consolidated financial statements.",
    "Quarter Ended December 31, Year Ended December 31,",
    "(In millions, except per share data)",
    "Total revenue $ 5,200 $ 4,650 $ 19,800 $ 17,900",
    "Net income $ 1,400 $ 1,100 $ 5,100 $ 4,300",
    "•Revenue grew 12% to $5.2 billion in the fourth quarter, with "
    "full-year revenue up 11% to $19.8 billion.",
    "•Net income was $1.4 billion, or $2.10 per diluted share, in the "
    "fourth quarter.",
    "•Operating cash flow reached $2.0 billion in the quarter, up 18% "
    "year over year.",
)


def test_table_headed_section_without_bullets_is_rejected() -> None:
    # Batch 156: the section's collected lines are intro prose + period
    # header (>=150 chars, no bullets) and the collection breaks on the
    # units line — a table, not highlights, so no section candidate.
    assert _extract_highlights_sections(list(_ACME_LINES[3:9])) == []


def test_bulleted_table_headed_section_is_kept() -> None:
    # Positive control: the same shape with real bullets before the table
    # break is genuine highlights and must still be returned.
    lines = [
        "Fourth Quarter 2025 Financial Highlights",
        "•Revenue grew 12% to $5.2 billion in the fourth quarter.",
        "•Net income was $1.4 billion, or $2.10 per diluted share.",
        "•Operating cash flow reached $2.0 billion in the quarter.",
        "•Free cash flow was $1.8 billion, up 22% year over year.",
        "(In millions, except per share data)",
        "Total revenue $ 5,200 $ 4,650",
    ]
    sections = _extract_highlights_sections(lines)
    assert len(sections) == 1
    assert "•Revenue grew 12%" in "\n".join(sections[0])


def test_middle_dot_bullets_count_as_bullets() -> None:
    # Boundary: "·"-led bullets (Plug/Chubb flattening, batch 138/139)
    # count as bullets, so a "·"-bulleted section is never rejected for
    # lacking a "•"-style lead.
    lines = [
        "Fourth Quarter 2025 Financial Highlights",
        "· Revenue grew 12% to $5.2 billion in the fourth quarter.",
        "· Net income was $1.4 billion, or $2.10 per diluted share.",
        "· Operating cash flow reached $2.0 billion in the quarter.",
        "· Free cash flow was $1.8 billion, up 22% year over year.",
        "(In millions, except per share data)",
        "Total revenue $ 5,200 $ 4,650",
    ]
    assert len(_extract_highlights_sections(lines)) == 1


def test_table_intro_sentence_is_a_lede_table_line() -> None:
    # Batch 156: the table's own preamble is residue even though it is a
    # terminated sentence.
    assert _is_lede_table_line(
        "The following table summarizes selected financial information for "
        "the periods presented."
    )
    assert _is_lede_table_line(
        "The table below summarizes our consolidated results."
    )
    # "Sets forth" is genuine prose (Crown Castle Q1 2026) — the verb is
    # deliberately not generalized, and the blast caught the overreach.
    assert not _is_lede_table_line(
        "The following table sets forth Crown Castle's current full year "
        "2026 Outlook, which includes a $40 million decrease in interest "
        "expense."
    )
    # A prose sentence that merely mentions a table never matches.
    assert not _is_lede_table_line(
        "We raised the full-year outlook as shown in the table below for "
        "reference."
    )
    # Bullets are always content, even when they mention a table.
    assert not _is_lede_table_line(
        "•The following table summarizes our segment results."
    )


def test_doubled_period_header_is_a_lede_date_header() -> None:
    # Batch 156: "Quarter Ended December 31, Year Ended December 31," is
    # a date header — the "Year" token was missing from the date-token set.
    assert _is_lede_date_header(
        "Quarter Ended December 31, Year Ended December 31,"
    )
    assert _is_lede_date_header("Full Year Ended December 31,")
    # Prose that merely contains date words never qualifies: the
    # all-words-must-match guard still holds.
    assert not _is_lede_date_header(
        "For the year ended December 31, revenue grew 12%."
    )


def test_space_separated_dollar_data_row_is_a_data_row() -> None:
    # Batch 156: flattened tables write "$ 5,200" with the $ separated
    # from its figure — the old \$[\d(] gate never matched, so the row
    # rode the lede budget.
    assert _is_lede_data_row("Total revenue $ 5,200 $ 4,650 $ 19,800 $ 17,900")
    assert _is_lede_data_row("Revenues $ 86,310 $ 96,469 $ 307,394 $ 350,018")
    # A prose line carrying one spaced $ figure is figure-sparse and
    # never qualifies — the density rule is the guard.
    assert not _is_lede_data_row(
        "Revenue grew to $ 5.2 billion, up 12% year over year."
    )


def test_prose_first_release_serves_bullets_after_table() -> None:
    # Batch 156 end-to-end: headline + dateline + prose paragraph (which
    # defeats the leading bullet block) + a table-headed Highlights
    # section + the real bullets after the table. The stub must not win;
    # the lede serves the prose and the bullets, with no table residue.
    hl = extract_press_release_highlights(_contact_release_html(*_ACME_LINES))
    assert hl is not None
    assert hl.split("\n\n")[0] == (
        "Acme Corp Reports Fourth Quarter and Full Year 2025 Results"
    )
    assert "Acme delivered record revenue in the quarter" in hl
    assert "•Revenue grew 12% to $5.2 billion in the fourth quarter" in hl
    assert "•Net income was $1.4 billion, or $2.10 per diluted share" in hl
    assert "•Operating cash flow reached $2.0 billion" in hl
    assert "The following table summarizes" not in hl
    assert "Quarter Ended December 31" not in hl
    assert "Financial Highlights" not in hl
    assert "Total revenue $ 5,200" not in hl
