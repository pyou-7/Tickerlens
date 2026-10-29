"""Batch 146: flattened summary-table mode for shareholder letters.

Airbnb's shareholder letter opens with a "Key Financial Measures" /
"Key Business Metrics" summary table that text extraction flattens into
run-on lines: group-header words split around the first metric's value
("Revenue Key Financial $3.6B Measures"), wrapped labels split around
their value ("Free Cash $1.3B Flow ("FCF")*"), and Q4 letters carry two
value columns (quarter + full year). The batch-94 metric mode needs a
"Highlights" heading line, which this table never has, so the standard
path served the flattened table as headline + prose. The flat-table mode
parses the value-delimited token stream into honest bullets instead.

The Q3/Q4 2024 letters are deliberately NOT covered: their table cells
interleave with narrative sentences, which fail the change-phrase
grammar, so those quarters keep the old behavior.
"""

from tickerlens.data.filings import extract_press_release_highlights

_BATCH146_BODY = """
<p>Over the first half of the year, we delivered some of our strongest
results in years, with momentum accelerating as we exceeded our outlook
across every key metric. Growth accelerated in our expansion markets and
in many of our largest core markets as well, reinforcing our confidence
that product innovation is driving demand across the business. We
rebuilt the company from the ground up to be AI-native, and it is showing
up in our results: faster iteration, better execution, and a pace of
innovation that is reshaping nearly every part of the business.</p>
<p>We continue to invest behind our growth initiatives while expanding
what we offer guests and hosts, from services and experiences to
boutique hotels, and we expect the momentum to carry into the second
half of the year as travel demand remains strong across regions.</p>
"""

_ABNB_Q2_2026_HTML = f"""<html><body>
<p>EX-99.1</p><p>2</p><p>d70413dex991.htm</p><p>EX-99.1</p>
<p>Q2 2026 Revenue Key Financial $3.6B Measures 17% Y/Y 13% Y/Y (ex-FX) Net</p>
<p>Income $816M 23% Net income margin Adjusted EBITDA* $1.3B 35% Adjusted EBITDA Margin Free Cash $1.3B Flow (“FCF”)* 35% FCF Margin Trailing Twelve Month $4.8B (“TTM”) FCF* 37% TTM FCF Margin Gross Booking Key Business $27.2B</p>
<p>Value (“GBV”) Metrics 16% Y/Y 15% Y/Y (ex-FX) Nights and 148.3M Seats Booked 10% Y/Y A reconciliation of non-GAAP financial measures to the most comparable GAAP measures is provided at the end of this letter. * 2</p>
<p>Q2 2026 Shareholder Letter Over the first half of 2026, we’ve delivered some of our strongest results in years.</p>
{_BATCH146_BODY}
</body></html>"""

_ABNB_Q4_2025_HTML = f"""<html><body>
<p>EX-99.1</p><p>2</p><p>d58192dex991.htm</p><p>EX-99.1 1</p>
<p>Q4 2025 Q4 2025 FY 2025 Revenue Key Financial $2.8B $12.2B Measures 12%</p>
<p>Y/Y 10% Y/Y 11% Y/Y (ex-FX) 10% Y/Y (ex-FX) Net Income $341M $2.5B 12% Net income margin 21% Net income margin Adjusted EBITDA* $786M $4.3B 28% Adjusted EBITDA Margin 35% Adjusted EBITDA Margin Free Cash $521M $4.6B Flow (“FCF”)* 19% FCF</p>
<p>Margin 38% FCF Margin Gross Booking Key Business $20.4B $91.3B Value (“GBV”) Metrics 16% Y/Y 12% Y/Y 13% Y/Y (ex-FX) 10% Y/Y (ex-FX) Nights and 121.9M 533.0M Seats Booked 10% Y/Y 8% Y/Y *A reconciliation of non-GAAP financial measures to the most comparable GAAP measures is provided at the end of this letter. 2</p>
<p>Q4 2025 Shareholder Letter Airbnb closed out 2025 with strong momentum.</p>
{_BATCH146_BODY}
</body></html>"""

# Q1 2025 shape: the FCF metric carries no change phrases, so the piece
# between its value and the next value has no % token — the split must
# come from the parenthetical instead.
_ABNB_Q1_2025_MIN_HTML = f"""<html><body>
<p>EX-99.1</p><p>2</p><p>d40594dex991.htm</p><p>EX-99.1</p>
<p>Q1 2025 Highlights Revenue Key Financial $2.3B Measures 6% Y/Y 8% Y/Y</p>
<p>(ex-FX) Net Income $154M 7% Net income margin Adjusted EBITDA* $417M 18% Adjusted EBITDA Margin Free Cash $1.8B Flow (“FCF”)* Trailing Twelve Month $4.4B (“TTM”) FCF* 39% TTM FCF Margin Gross Booking Key Business $24.5B Value</p>
<p>(“GBV”) Metrics 7% Y/Y 9% Y/Y (ex-FX) Nights and 143.1M Experiences Booked 8% Y/Y *A reconciliation of non-GAAP financial measures to the most comparable GAAP measures is provided at the end of this letter. 2</p>
<p>Q1 2025 Shareholder Letter We had a strong start to 2025.</p>
{_BATCH146_BODY}
</body></html>"""

# Q3 2024 shape: table cells interleaved with narrative sentences. The
# prose change phrase ("10% compared to Q3 2023...") must fail the whole
# parse, not emit a junk label.
_ABNB_Q3_2024_HTML = f"""<html><body>
<p>EX-99.1</p><p>2</p><p>d886752dex991.htm</p><p>EX-99.1</p>
<p>Exhibit 99.1</p>
<p>Q3 2024 Shareholder Letter</p>
<p>Key Financial Measures Q3 2024 Revenue $3.7B Q3 revenue of $3.7 billion increased 10% compared to Q3 2023 primarily driven by the</p>
<p>growth of nights stayed on the platform. 10% Y/Y 10% Y/Y (ex-FX) Net Income $1.4B We generated $1.4 billion of net income during Q3 2024 and delivered a 37% net income margin, demonstrating significant</p>
<p>profitability. 37% Net income margin Adjusted EBITDA* $2.0B Our Q3 Adjusted EBITDA of $2.0 billion represented a 52% Adjusted EBITDA Margin, demonstrating the strength of the business and 52% Adjusted EBITDA Margin broad cost discipline. 7% Y/Y</p>
<p>8% Y/Y (ex-FX) Free Cash Flow (“FCF”)* $1.1B We generated $1.1 billion of net cash provided by operating activities and $1.1 billion of FCF in Q3. Our trailing twelve months</p>
<p>(“TTM”) FCF 29% Q3 FCF Margin was $4.1 billion, representing a TTM FCF Margin of 38%. $4.1B 38% TTM FCF Margin Key Business Metrics Gross Booking Value (“GBV”) $20.1B Strong growth in Nights and Experiences Booked and a</p>
<p>modest increase in ADR drove $20.1 billion of GBV in Q3 2024. 10% Y/Y 10% Y/Y (ex-FX) Nights and Experiences Booked 122.8M In Q3 2024, Nights and Experiences Booked increased 8% compared to the prior</p>
<p>year, driven by continued growth in all regions. 8% Y/Y *A reconciliation of non-GAAP financial measures to the most comparable GAAP measures is provided at the end of this letter.</p>
<p>Q3 2024 Shareholder Letter Airbnb had a strong Q3.</p>
{_BATCH146_BODY}
</body></html>"""

# A plain press release (no shareholder-letter title) with the same table
# shape: the flat mode is gated on shareholder-letter detection, so it
# must not trigger here.
_NON_LETTER_HTML = f"""<html><body>
<p>EX-99.1</p>
<p>Acme Reports Second Quarter 2026 Results</p>
<p>Q2 2026 Revenue Key Financial $3.6B Measures 17% Y/Y 13% Y/Y (ex-FX) Net</p>
<p>Income $816M 23% Net income margin Adjusted EBITDA* $1.3B 35% Adjusted EBITDA Margin Free Cash $1.3B Flow (“FCF”)* 35% FCF Margin Trailing Twelve Month $4.8B (“TTM”) FCF* 37% TTM FCF Margin Gross Booking Key Business $27.2B</p>
<p>Value (“GBV”) Metrics 16% Y/Y 15% Y/Y (ex-FX) Nights and 148.3M Seats Booked 10% Y/Y A reconciliation of non-GAAP financial measures to the most comparable GAAP measures is provided at the end of this letter. * 2</p>
<p>Revenue grew 17% year-over-year to $3.6 billion in the second quarter.</p>
{_BATCH146_BODY}
</body></html>"""


def test_flat_summary_table_single_column() -> None:
    hl = extract_press_release_highlights(_ABNB_Q2_2026_HTML)
    assert hl is not None
    assert hl.startswith("Shareholder Letter Q2 2026")
    assert "- Revenue: $3.6B (17% Y/Y; 13% Y/Y (ex-FX))" in hl
    assert "- Net Income: $816M (23% Net income margin)" in hl
    assert "- Adjusted EBITDA: $1.3B (35% Adjusted EBITDA Margin)" in hl
    assert "- Free Cash Flow (“FCF”): $1.3B (35% FCF Margin)" in hl
    assert "- Trailing Twelve Month (“TTM”) FCF: $4.8B (37% TTM FCF Margin)" in hl
    assert "- Gross Booking Value (“GBV”): $27.2B (16% Y/Y; 15% Y/Y (ex-FX))" in hl
    assert "- Nights and Seats Booked: 148.3M (10% Y/Y)" in hl
    # No flattened-table residue in the served text.
    assert "Key Financial" not in hl
    assert "Key Business" not in hl
    assert "Measures" not in hl
    assert "reconciliation of non-GAAP" not in hl


def test_flat_summary_table_dual_column() -> None:
    hl = extract_press_release_highlights(_ABNB_Q4_2025_HTML)
    assert hl is not None
    assert hl.startswith("Shareholder Letter Q4 2025")
    # Dual-column header names the value order (quarter; full year).
    assert "Q4 2025; FY 2025" in hl
    assert "- Revenue: $2.8B; $12.2B (12% Y/Y; 10% Y/Y; 11% Y/Y (ex-FX); 10% Y/Y (ex-FX))" in hl
    assert "- Net Income: $341M; $2.5B (12% Net income margin; 21% Net income margin)" in hl
    assert "- Adjusted EBITDA: $786M; $4.3B (28% Adjusted EBITDA Margin; 35% Adjusted EBITDA Margin)" in hl
    assert "- Free Cash Flow (“FCF”): $521M; $4.6B (19% FCF Margin; 38% FCF Margin)" in hl
    assert "- Gross Booking Value (“GBV”): $20.4B; $91.3B (16% Y/Y; 12% Y/Y; 13% Y/Y (ex-FX); 10% Y/Y (ex-FX))" in hl
    assert "- Nights and Seats Booked: 121.9M; 533.0M (10% Y/Y; 8% Y/Y)" in hl


def test_flat_summary_table_metric_without_changes() -> None:
    hl = extract_press_release_highlights(_ABNB_Q1_2025_MIN_HTML)
    assert hl is not None
    assert hl.startswith("Shareholder Letter Q1 2025")
    assert "- Revenue: $2.3B (6% Y/Y; 8% Y/Y (ex-FX))" in hl
    # FCF has no change phrases: the no-% piece splits on the parenthetical.
    assert "- Free Cash Flow (“FCF”): $1.8B" in hl
    assert "- Trailing Twelve Month (“TTM”) FCF: $4.4B (39% TTM FCF Margin)" in hl
    assert "- Nights and Experiences Booked: 143.1M (8% Y/Y)" in hl


def test_flat_summary_table_rejects_prose_interleaved_table() -> None:
    # Q3 2024 shape: narrative sentences inside the table must fail the
    # parse, so no flat bullet is emitted (the standard path serves).
    hl = extract_press_release_highlights(_ABNB_Q3_2024_HTML)
    assert hl is not None
    assert "- Revenue: $3.7B" not in hl
    assert "- Net Income: $1.4B" not in hl
    assert "Q3 revenue of $3.7 billion increased" not in hl.split("\n")[0]


def test_flat_summary_table_requires_shareholder_letter() -> None:
    hl = extract_press_release_highlights(_NON_LETTER_HTML)
    assert hl is not None
    assert "- Revenue: $3.6B" not in hl
    assert "- Net Income: $816M" not in hl
