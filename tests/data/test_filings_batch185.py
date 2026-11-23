"""Batch 185 regression tests: orphaned flattened-table labels (BRO).

Brown & Brown flattens its reconciliation tables one cell per line, so a
row's label (\"Diluted net income per share\", \"Change in estimated
acquisition earn-out payables\") survives _drop_table_fragment_runs — its
$-value rows drop as a fragment run, but the 5-6-word label is too long
for the heading fold (4 words) and too lowercase-led for the table-header
predicate — and the lede loop then collects it as its last budget lines
(7 quarters, 2024-03-31 through 2025-09-30). Skipping the label alone
does not fix it: the next table's labels would fill the budget instead,
so the loop now enters table mode on a flattened label directly below a
table header block, and skips table residue until real prose (a
terminated sentence or a bullet) resumes. A break would be wrong — a
quote or paragraph after the table (CSX) is still collected; the v1
break lost AAPL/AXP/CCI/COF/CSX/EL/FDX content (blast 185).
"""
from tickerlens.data.filings import (
    _is_lede_flat_table_label,
    _is_lede_nongaap_section_heading,
    _is_lede_table_mode_residue,
    _is_lone_bullet_marker,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

_BRO_LABELS = (
    "Diluted net income per share",
    "Change in estimated acquisition earn-out payables",
)

_PERIOD_HEADER = "Nine Months Ended September 30,"


def test_flat_table_label_matches_bro_labels_below_period_header() -> None:
    for ln in _BRO_LABELS:
        assert _is_lede_flat_table_label(ln, _PERIOD_HEADER), ln


def test_flat_table_label_rejects_label_after_label() -> None:
    # A wrapped sub-headline looks exactly like a run of labels (Apple:
    # "Services revenue reaches new all-time high" below "June quarter
    # records for Revenue and EPS"), so a label-shaped previous line
    # never qualifies — the v1 label-run branch dropped real
    # sub-headlines and pulled tail boilerplate into the budget slot.
    assert not _is_lede_flat_table_label(
        "Change in estimated acquisition earn-out payables",
        "Diluted net income per share",
    )
    assert not _is_lede_flat_table_label(
        "Services revenue reaches new all-time high",
        "June quarter records for Revenue and EPS",
    )
    assert not _is_lede_flat_table_label(
        "to Reflect Incremental External Headwinds",
        "Delivered First Quarter Expectations but Lowering Full-Year Outlook",
    )


def test_flat_table_label_matches_below_table_header_and_units() -> None:
    assert _is_lede_flat_table_label(
        "Diluted net income per share", "Diluted Net Income Per Share - Adjusted"
    )
    assert _is_lede_flat_table_label(
        "Change in estimated acquisition earn-out payables",
        "(in millions, unaudited)",
    )
    assert _is_lede_flat_table_label(
        "Diluted net income per share", "Reconciliation of Commissions and Fees"
    )


def test_flat_table_label_rejects_prose_and_fragments() -> None:
    # Terminated prose, figure-carrying lines, bullets, and quote
    # attributions are never labels — even directly below a header.
    for ln in (
        "Net income attributable to the Company was $227 million.",
        "Diluted net income per share of $0.68",
        "• Total revenues of $1.7 billion, increasing 30.4%",
        "J. Powell Brown, president and chief executive officer of the "
        "Company, noted,",
        "Q2 ORGANIC SALES AND ADJUSTED EPS EXCEED OUTLOOK",
        "Diluted Net Income Per Share - Adjusted",
    ):
        assert not _is_lede_flat_table_label(ln, _PERIOD_HEADER), ln


def test_flat_table_label_rejects_prose_previous_line() -> None:
    # A label-shaped line below narrative prose is a wrapped fragment,
    # not a table row — the previous-line requirement is the guard.
    for ln in _BRO_LABELS:
        assert not _is_lede_flat_table_label(
            ln,
            "Revenues for the third quarter of 2025 under GAAP were "
            "$1.6 billion, increasing 35.4%.",
        )
        assert not _is_lede_flat_table_label(ln, "")
        # A long table label is not label-shaped itself (13+ words), so
        # it cannot anchor the next label either.
        assert not _is_lede_flat_table_label(
            ln,
            "Effect of foreign exchange rate changes on cash and cash "
            "equivalents inclusive of fiduciary cash",
        )


def test_flat_table_label_rejects_wrong_shapes() -> None:
    # One word is a fragment, thirteen words is prose; a mid-line
    # sentence boundary is prose too.
    assert not _is_lede_flat_table_label("Revenues", _PERIOD_HEADER)
    assert not _is_lede_flat_table_label(
        "Effect of foreign exchange rate changes on cash and cash "
        "equivalents inclusive of fiduciary cash",
        _PERIOD_HEADER,
    )
    assert not _is_lede_flat_table_label(
        "Net income rose. Diluted EPS followed",
        _PERIOD_HEADER,
    )


def test_bro_lede_breaks_at_flat_table_label() -> None:
    # Verbatim BRO Q3 2025 shape (headline, dateline, two prose
    # paragraphs, CEO quote, recon tables flattened one cell per line):
    # the lede must end at the quote — the orphaned labels and the
    # tables after them are never served.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Brown & Brown, Inc. announces third quarter 2025 results, "
            "including total revenues of $1.6 billion, an increase of "
            "35.4%; Organic Revenue growth of 3.5%; diluted net income "
            "per share of $0.68; and Diluted Net Income Per Share - "
            "Adjusted of $1.05",
            "DAYTONA BEACH, Fla., October 27, 2025 - Brown & Brown, Inc. "
            "(NYSE:BRO) (the \"Company\") announced its unaudited "
            "financial results for the third quarter of 2025.",
            "Revenues for the third quarter of 2025 under U.S. generally "
            "accepted accounting principles (\"GAAP\") were $1.6 billion, "
            "increasing $420 million, or 35.4%, compared to the third "
            "quarter of the prior year, with commissions and fees "
            "increasing by 34.2% and Organic Revenue increasing by 3.5%.",
            "Revenues for the nine months ended September 30, 2025 under "
            "GAAP were $4.3 billion, increasing $673 million, or 18.6%, "
            "as compared to the same period in 2024.",
            "J. Powell Brown, president and chief executive officer of "
            "the Company, noted, “We are very excited to welcome over "
            "5,000 new teammates to our organization in the third "
            "quarter.”",
            "1",
            "Reconciliation of Commissions and Fees",
            "to Organic Revenue",
            "(in millions, unaudited)",
            "Three Months Ended September 30,",
            "Nine Months Ended September 30,",
            "Commissions and fees",
            "$",
            "1,550",
            "$",
            "1,155",
            "See information regarding non-GAAP measures presented later "
            "in this press release.",
            "Reconciliation of Diluted Net Income Per Share to",
            "Diluted Net Income Per Share - Adjusted",
            "(unaudited)",
            "Three Months Ended September 30,",
            "Change",
            "Nine Months Ended September 30,",
            "Diluted net income per share",
            "$",
            "0.68",
            "$",
            "0.81",
            "Change in estimated acquisition earn-out payables",
            "0.02",
            "(0.02",
            "Diluted Net Income Per Share - Adjusted",
            "$",
            "1.05",
            "See information regarding non-GAAP measures presented later "
            "in this press release.",
            "Brown & Brown, Inc.",
            "Consolidated Statements of Income",
            "(in millions, except per share data; unaudited)",
            "Change in estimated acquisition earn-out payables",
            "Net income before non-controlling interests",
            "Net income attributable to the Company",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0].startswith(
        "Brown & Brown, Inc. announces third quarter 2025 results"
    )
    assert "We are very excited to welcome over 5,000 new teammates" in hl
    # No orphaned label, no recon heading, no table title survives.
    assert "Diluted net income per share\n" not in hl
    assert "Change in estimated acquisition earn-out payables" not in hl
    assert "Reconciliation of Diluted Net Income Per Share" not in hl
    assert "Consolidated Statements of Income" not in hl
    assert "Net income attributable to the Company" not in hl


def test_table_mode_residue_shape() -> None:
    # A flattened multi-column row joined with "respectively" is
    # terminated but is not prose — it is table residue in table mode
    # (BRO 2024-03-31: the balance-sheet row leaked into the
    # highlights once the orphaned labels stopped filling the budget).
    assert _is_lede_table_mode_residue(
        "Treasury stock, at cost 20 shares at 2024, 20 shares at 2023, "
        "respectively."
    )
    # ... but a plain narrative sentence ending in "respectively."
    # with no year is still prose and ends table mode.
    assert not _is_lede_table_mode_residue(
        "Revenue and earnings per share grew 12% and 8%, respectively."
    )
    # Inside a table region, an unterminated or colon-ended line is
    # another table row, however long (a wrapped balance-sheet row, a
    # cash-flow label); a "Note:" line is a footnote even when
    # terminated. Terminated prose and bullets are narrative, never
    # residue — they are what ends table mode.
    for ln in (
        "Diluted net income per share",
        "Change in estimated acquisition earn-out payables",
        "Effect of foreign exchange rate changes on cash and cash "
        "equivalents inclusive of fiduciary cash",
        "Common stock, par value $0.10 per share; authorized 560 shares",
        "Net earnings includes:",
        "Cash flows from operating activities:",
        "Brown & Brown, Inc.",
        "Note: Per share amounts for the Class B shares are 1/1,500th "
        "of those shown for the Class A shares.",
    ):
        assert _is_lede_table_mode_residue(ln), ln
    for ln in (
        "Volume totaled 1.61 million units for the quarter, up 1%.",
        "All comparisons below are for the second quarter of 2025 "
        "compared with the first quarter of 2025 unless otherwise noted.",
        "•Total net revenue increased 25 percent to $12.5 billion.",
        "“This quarter’s operational performance reflects the dedication "
        "of our workforce.”",
    ):
        assert not _is_lede_table_mode_residue(ln), ln


def test_lone_em_dash_is_a_marker() -> None:
    # A lone "—" is an empty table cell / flattened bullet marker, not
    # content: _BULLET_LEAD_RE already treats it as a bullet marker,
    # but _is_lone_bullet_marker missed it (it covered "–" since batch
    # 140) so the dash was collected as a lede line — and clearing
    # table mode, letting the next table's labels in (BRO, blast 185).
    assert _is_lone_bullet_marker("—")
    assert _is_lone_bullet_marker("–")
    assert not _is_lone_bullet_marker("— Total revenues")


def test_nongaap_section_heading_shape() -> None:
    assert _is_lede_nongaap_section_heading("Non-GAAP Financial Measures")
    assert _is_lede_nongaap_section_heading("Non-GAAP Financial Measures:")
    assert not _is_lede_nongaap_section_heading(
        "Reconciliation of Non-GAAP Financial Measures"
    )
    assert not _is_lede_nongaap_section_heading(
        "The non-GAAP financial measures discussed below exclude charges."
    )


def test_supplement_packet_stays_none() -> None:
    # EOG shape: a supplement packet (TOC + financial-statement tables
    # + non-GAAP definitions, no release headline). The old code
    # returned None because the TOC entries filled the 6-line budget
    # and the result stayed under 200 chars; table mode must not turn
    # that honest None into served definitions boilerplate. The exhibit
    # headers mirror the real packet, so "Table of Contents" is picked
    # as the (junk) headline exactly as in the live exhibit.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99",
            "2",
            "exh99-1050224.htm",
            "EX-99",
            "EXHIBIT 99.1",
            "Table of Contents",
            "First Quarter 2024",
            "Supplemental Financial and Operating Data Page",
            "Income Statements 12",
            "Wellhead Volumes and Prices 13",
            "Balance Sheets 14",
            "Cash Flow Statements 15",
            "Non-GAAP Financial Measures 16",
            "Adjusted Net Income 17",
            "11",
            "Income Statements",
            "In millions of USD, except share data (in millions) and "
            "per share data (Unaudited)",
            "2023 2024",
            "Operating Revenues and Other",
            "Crude Oil and Condensate 3,182 3,252 3,717 3,597 13,748",
            "Natural Gas Liquids 490 409 501 484 1,884",
            "(A) Effective January 1, 2024, EOG combined Transportation "
            "Costs and Gathering and Processing Costs into a single line "
            "item for presentation purposes in the financial statements.",
            "Operating Expenses",
            "Lease and Well 359 348 369 378 1,454",
            "15",
            "Non-GAAP Financial Measures",
            "To supplement the presentation of its financial results "
            "prepared in accordance with generally accepted accounting "
            "principles, EOG's quarterly releases contain certain "
            "financial measures that are not prepared in accordance "
            "with GAAP.",
            "EOG believes that the non-GAAP measures presented, when "
            "viewed in combination with its financial results prepared "
            "in accordance with GAAP, provide a more complete "
            "understanding of the factors affecting performance.",
        )
    )
    assert hl is None


def test_prose_after_table_is_still_collected() -> None:
    # CSX shape: a recon table sits between the results paragraph and
    # the CEO quote + volume paragraph. Table mode must not swallow
    # the prose that follows the table.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "CSX ANNOUNCES THIRD QUARTER 2025 RESULTS",
            "JACKSONVILLE, Fla. – October 16, 2025 – CSX Corp. (NASDAQ: "
            "CSX) today announced third quarter operating income of "
            "$1.09 billion and net earnings of $694 million, or $0.37 "
            "per share.",
            "In the quarter, adjusted operating income and adjusted "
            "earnings per share included $35 million and $0.01, "
            "respectively, in corporate restructuring, severance, and "
            "advisory expenses.",
            "Reconciliation of Operating Income to Adjusted Operating Income",
            "(in millions, unaudited)",
            "Three Months Ended September 30,",
            "Nine Months Ended September 30,",
            "Operating income",
            "$",
            "1,090",
            "$",
            "1,350",
            "Restructuring charges",
            "35",
            "12",
            "See information regarding non-GAAP measures presented later "
            "in this press release.",
            "“This quarter’s operational performance reflects the "
            "dedication of our workforce and our commitment to running "
            "the best railroad in North America,” said President and "
            "Chief Executive Officer Steve Angel.",
            "Volume totaled 1.61 million units for the quarter, up 1% "
            "compared to third quarter 2024 and up 2% sequentially.",
        )
    )
    assert hl is not None
    assert "In the quarter, adjusted operating income" in hl
    assert "This quarter’s operational performance reflects" in hl
    assert "Volume totaled 1.61 million units" in hl
    assert "Operating income\n" not in hl
    assert "Restructuring charges" not in hl


def test_table_before_narrative_still_serves_bullets() -> None:
    # The skip branch: a table ahead of the narrative (dateline only,
    # 1 content line) must not break the lede — the bullets below the
    # table are the content.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "ACME REPORTS THIRD QUARTER 2025 RESULTS",
            "DAYTONA BEACH, Fla., October 27, 2025 - Acme, Inc. "
            "(NYSE:ACME) announced its unaudited financial results for "
            "the third quarter of 2025.",
            "Reconciliation of Diluted Net Income Per Share to",
            "Diluted Net Income Per Share - Adjusted",
            "(unaudited)",
            "Three Months Ended September 30,",
            "Change",
            "Nine Months Ended September 30,",
            "Diluted net income per share",
            "$",
            "0.68",
            "$",
            "0.81",
            "Change in estimated acquisition earn-out payables",
            "0.02",
            "(0.02",
            "•Total revenues of $1.7 billion, increasing 30.4%",
            "•Net income attributable to the Company of $288 million",
            "•Diluted net income per share of $0.68",
        )
    )
    assert hl is not None
    assert "Total revenues of $1.7 billion" in hl
    assert "Net income attributable to the Company of $288 million" in hl
    assert "Change in estimated acquisition earn-out payables" not in hl
    assert "Diluted net income per share\n" not in hl


def test_prose_after_residue_only_table_stays_none() -> None:
    # Batch 126 guard, pinned here for the table_seen gate: a TOC-only
    # packet enters table mode on its supplement title, skips its TOC
    # entries as residue, and must NOT serve the prose that follows —
    # no real table row was ever seen, so the prose is filler after a
    # TOC, not narrative after a table.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Table of Contents",
            "Third Quarter 2024",
            "Supplemental Financial and Operating Data Page",
            "Income Statements 13",
            "Balance Sheets 15",
            "Some filler prose paragraph that is terminated and would be "
            "collected if the gate did not break.",
        )
    )
    assert hl is None


def test_prose_after_real_table_rows_is_collected() -> None:
    # Positive side of the table_seen gate: the same flat-label entry,
    # but a real table row (the units line) is seen in mode before the
    # prose — so the prose is narrative after a table and is collected
    # even though no content was collected before the table.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "ACME REPORTS THIRD QUARTER 2025 RESULTS",
            "Three Months Ended September 30,",
            "Diluted net income per share",
            "(in millions, unaudited)",
            "The Company reported record quarterly revenue of $1.2 "
            "billion, up 12% year over year.",
            "Net income rose 18% to $288 million.",
        )
    )
    assert hl is not None
    assert "record quarterly revenue of $1.2 billion" in hl
    assert "Net income rose 18%" in hl
    assert "Diluted net income per share\n" not in hl
