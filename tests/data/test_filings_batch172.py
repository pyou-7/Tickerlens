"""Batch 172 regression tests: Business Wire datelines.

Amazon's releases open with a Business Wire dateline — "SEATTLE—(BUSINESS
WIRE) October 31, 2024—Amazon.com, Inc. ..." — which has no "CITY, ST"
comma, so _DATELINE_LEAD_RE never matched it. Two consequences: the
dateline sentence broke _leading_bullet_block (first body line isn't a
bullet, so the section path returned None) and the lede fallback spent one
of its 6 budget lines on the dateline, serving headline + dateline + 5 of
the 13 metric bullets (837 chars) for AMZN Q3 FY2024 instead of the full
metric block. FICO ("BOZEMAN, Mont.--(BUSINESS WIRE)--..."), Dollar
General ("GOODLETTSVILLE, Tenn.--(BUSINESS WIRE)--..."), Palantir
("DENVER— (BUSINESS WIRE) — ...") and DoorDash ("SAN
FRANCISCO—(BUSINESS WIRE)—...") use the same wire form with different
separators and an optional date.
"""

from tickerlens.data.filings import (
    _DATELINE_LEAD_RE,
    _leading_bullet_block,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

_WIRE_DATELINES = [
    # Amazon: city + em-dash + wire + space + date + em-dash + lead.
    "SEATTLE—(BUSINESS WIRE) October 31, 2024—Amazon.com, Inc. (NASDAQ: AMZN) "
    "today announced financial results for its third quarter ended September 30, 2024.",
    # FICO: city + ", Mont." + double hyphen + wire + double hyphen + date + lead.
    "BOZEMAN, Mont.--(BUSINESS WIRE)--October 30, 2024--FICO (NYSE:FICO), a "
    "global analytics software leader, today announced results.",
    # Dollar General: city + ", Tenn." + double hyphen + wire + double hyphen + lead (no date).
    "GOODLETTSVILLE, Tenn.--(BUSINESS WIRE)--Dollar General Corporation "
    "(NYSE: DG) today reported financial results.",
    # Palantir: city + spaced em-dash + wire + spaced em-dash + lead (no date).
    "DENVER— (BUSINESS WIRE) — Palantir Technologies Inc. (NASDAQ:PLTR) today "
    "announced financial results.",
    # DoorDash: city + em-dash + wire + em-dash + lead (no date).
    "SAN FRANCISCO—(BUSINESS WIRE)—DoorDash, Inc. (NASDAQ: DASH) today "
    "announced its financial results.",
]

_NOT_DATELINES = [
    # Prose mention of the wire service, not a dateline.
    "The company issued a release via BUSINESS WIRE today.",
    # Lowercase-led city is not a dateline.
    "seattle—(BUSINESS WIRE) October 31, 2024—Amazon announced.",
    # A headline never matches.
    "AMAZON.COM ANNOUNCES THIRD QUARTER RESULTS",
    # Digit-led line never matches.
    "Q4 2024—(BUSINESS WIRE) October 31, 2024—Acme announced.",
    # Wire tag mid-sentence, not at the line start after a city.
    "Results were announced (BUSINESS WIRE) October 31, 2024.",
    # Bare wire tag with nothing after it is a credit line, not a dateline.
    "SEATTLE—(BUSINESS WIRE)",
]


def test_business_wire_dateline_forms_match() -> None:
    for ln in _WIRE_DATELINES:
        assert _DATELINE_LEAD_RE.match(ln), ln


def test_business_wire_dateline_negatives() -> None:
    for ln in _NOT_DATELINES:
        assert not _DATELINE_LEAD_RE.match(ln), ln


def test_business_wire_dateline_before_bullets_still_leading_block() -> None:
    # AMZN Q3 FY2024 shape: the dateline sentence sits between the headline
    # and the 13 metric bullets; the block must still be found, dateline-free.
    lines = [
        "SEATTLE—(BUSINESS WIRE) October 31, 2024—Amazon.com, Inc. (NASDAQ: AMZN) "
        "today announced financial results for its third quarter ended September 30, 2024.",
        "•Net sales increased 11% to $158.9 billion in the third quarter.",
        "•North America segment sales increased 9% year-over-year to $95.5 billion.",
        "•International segment sales increased 12% year-over-year to $35.9 billion.",
        "•AWS segment sales increased 19% year-over-year to $27.5 billion.",
        "•Operating income increased to $17.4 billion in the third quarter.",
    ]
    block = _leading_bullet_block(lines)
    assert block is not None
    assert len(block) == 5
    assert all(b.startswith("•") for b in block)
    assert not any("BUSINESS WIRE" in b for b in block)


def test_business_wire_release_serves_full_metric_block() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "AMAZON.COM ANNOUNCES THIRD QUARTER RESULTS",
            "SEATTLE—(BUSINESS WIRE) October 31, 2024—Amazon.com, Inc. (NASDAQ: AMZN) "
            "today announced financial results for its third quarter ended September 30, 2024.",
            "•Net sales increased 11% to $158.9 billion in the third quarter.",
            "•North America segment sales increased 9% year-over-year to $95.5 billion.",
            "•International segment sales increased 12% year-over-year to $35.9 billion.",
            "•AWS segment sales increased 19% year-over-year to $27.5 billion.",
            "•Operating income increased to $17.4 billion in the third quarter.",
            "•Net income increased to $15.3 billion in the third quarter, or $1.43 per diluted share.",
            "“As we get into the holiday season, we’re excited,” said Andy Jassy, Amazon President & CEO.",
            "Some other highlights since the company’s last earnings announcement include that Amazon:",
            "•Held its annual Prime Big Deal Days shopping event, with record sales.",
        )
    )
    assert hl is not None
    assert "BUSINESS WIRE" not in hl
    # Batch 198: live bullets are spaced after the glyph ("• Net ...").
    assert hl.count("• Net sales") == 1
    assert "• Operating income increased" in hl
    assert "• Net income increased" in hl
    # The financial block wins the batch-102 ranking over the later business
    # bullets, so the Prime bullet is not in the live result (the stored row
    # keeps it — the backfill only fills blanks).
    assert "Prime Big Deal Days" not in hl


def test_period_label_between_dateline_and_bullets_still_leading_block() -> None:
    # AMZN Q4 FY2024 shape: a bare "Fourth Quarter 2024" period label sits
    # between the Business Wire dateline and the metric bullets; the block
    # must still be found (the lede loop already drops the label via
    # _is_lede_table_line, but _leading_bullet_block broke on it).
    lines = [
        "SEATTLE—(BUSINESS WIRE) February 6, 2025—Amazon.com, Inc. (NASDAQ: AMZN) "
        "today announced financial results for its fourth quarter ended December 31, 2024.",
        "Fourth Quarter 2024",
        "•Net sales increased 10% to $187.8 billion in the fourth quarter.",
        "•North America segment sales increased 10% year-over-year to $115.6 billion.",
        "•AWS segment sales increased 19% year-over-year to $28.8 billion.",
    ]
    block = _leading_bullet_block(lines)
    assert block is not None
    assert len(block) == 3
    assert all(b.startswith("•") for b in block)
    assert not any("BUSINESS WIRE" in b for b in block)
    assert not any("Fourth Quarter" in b for b in block)


def test_period_label_end_to_end_q4() -> None:
    # End to end on the AMZN Q4 FY2024 shape: headline + full metric block,
    # no dateline, no period label.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "AMAZON.COM ANNOUNCES FOURTH QUARTER RESULTS",
            "SEATTLE—(BUSINESS WIRE) February 6, 2025—Amazon.com, Inc. (NASDAQ: AMZN) "
            "today announced financial results for its fourth quarter ended December 31, 2024.",
            "Fourth Quarter 2024",
            "•Net sales increased 10% to $187.8 billion in the fourth quarter.",
            "•North America segment sales increased 10% year-over-year to $115.6 billion.",
            "•AWS segment sales increased 19% year-over-year to $28.8 billion.",
            "•Operating income increased to $21.2 billion in the fourth quarter.",
        )
    )
    assert hl is not None
    assert "BUSINESS WIRE" not in hl
    assert "Fourth Quarter 2024" not in hl
    assert "• Net sales increased" in hl
    assert "• Operating income increased" in hl
