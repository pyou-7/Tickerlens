"""Batch 167 regression tests: rounding notes, asterisk notes, quarter titles.

Closes the batch-166 COIN follow-ups in full:

1. A rounding-note skip. Coinbase's shareholder letters carry a rounding
   boilerplate paragraph ahead of the letter prose — the long form
   ("Figures have been rounded for presentation purposes only. For
   additional financial information and a reconciliation between GAAP and
   non-GAAP results, please refer to the reconciliation of GAAP to
   Non-GAAP results table(s) in this shareholder letter and our Form
   10-K/10-Q filed with the SEC on <date>.") and the short form ("Note:
   Figures presented [above] may not sum precisely due to rounding.").
   Either form fills the lede when nothing else precedes the prose (Q4
   FY2024's whole stored body is the long form), and the long form's first
   line becomes the headline when the quarter title is skipped (Q1/Q2
   FY2025).
2. A spaced-glyph asterisk-note skip ("* Based on the closing price of
   Coinbase's Class A common stock on May 7, 2025 on the Nasdaq Global
   Stock Market."). The lede's table-line rule already drops the opener,
   but its wrapped continuations were served — "Coinbase's Class A common
   stock" opens Q1 FY2025's lede once the rounding note is skipped — and
   in the leading-bullet block the opener starts a bullet item.
3. A quarter-title headline fix. "First Quarter 2025" / "Second Quarter
   2025" were skipped twice over: as masthead residue (<=4 words + digit
   looks like a street / city-postal line, and the date line follows) and
   as a bare masthead name (the date + page number count as residue and
   the first footnote line — "[1] Adjusted EBITDA is a non-GAAP
   financial", unterminated, so headline-shaped — counts as the real
   headline). Q1 survived by luck: its "[1] This is a non-GAAP financial
   measure." ends with a period, so the bare-masthead lookahead returned
   None. Both skips now exclude quarter titles, so the title is picked
   as the headline — the same shape Q4's "Fourth Quarter and Full Year
   2024" already had.
"""
from tickerlens.data.filings import (
    _QUARTER_TITLE_RE,
    _asterisk_note_block_len,
    _is_inline_bullet_start,
    _looks_like_masthead_residue,
    _rounding_note_block_len,
    _salvage_page_line_lede,
    _skip_bare_masthead_name,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def test_rounding_note_regex() -> None:
    from tickerlens.data.filings import _ROUNDING_NOTE_RE

    # Long form, first line and whole.
    assert _ROUNDING_NOTE_RE.match(
        "Figures have been rounded for presentation purposes"
    )
    assert _ROUNDING_NOTE_RE.match(
        "Figures have been rounded for presentation purposes only."
    )
    # Short form, single line and wrapped.
    assert _ROUNDING_NOTE_RE.match(
        "Note: Figures presented may not sum precisely due to rounding."
    )
    assert _ROUNDING_NOTE_RE.match(
        "Note: Figures presented above may not sum precisely due to rounding."
    )
    assert _ROUNDING_NOTE_RE.match("Note: Figures presented may not")
    # The long form's second sentence standing alone (Q3 FY2024 carries
    # the short note plus the referral sentence, with no long-form first
    # sentence).
    assert _ROUNDING_NOTE_RE.match(
        "For additional financial information and a"
    )
    # Prose that merely mentions figures is not a rounding note.
    assert not _ROUNDING_NOTE_RE.match("Figures have been revised upward")
    assert not _ROUNDING_NOTE_RE.match(
        "The figures presented may not sum precisely due to rounding."
    )
    assert not _ROUNDING_NOTE_RE.match("Figures have been rounded down")


def test_rounding_note_long_form_consumes_six_lines() -> None:
    # Verbatim lines 28-33 of the Q4 FY2024 shareholder letter, then prose.
    lines = [
        "Figures have been rounded for presentation purposes",
        "only. For additional financial information and a",
        "reconciliation between GAAP and non-GAAP results,",
        "please refer to the reconciliation of GAAP to Non-",
        "GAAP results table in this shareholder letter and our",
        "Form 10-K filed with the SEC on February 13, 2025.",
        "Coinbase delivered strong Q4 and full year 2024 results, with",
    ]
    assert _rounding_note_block_len(lines, 0) == 6
    # The block stops at the terminating line: the prose after it is kept.
    assert _rounding_note_block_len(lines, 6) == 0


def test_rounding_note_orphaned_referral_sentence_consumes_eight_lines() -> None:
    # Verbatim lines 21-28 of the Q3 FY2024 shareholder letter, then prose:
    # the short note sits at the head of the letter and the long form's
    # referral sentence stands alone — the opener covers it, so the whole
    # paragraph drops instead of serving as lede content.
    lines = [
        "For additional financial information",
        "and a reconciliation between",
        "GAAP and non-GAAP results,",
        "please refer to the reconciliation of",
        "GAAP to Non-GAAP results table",
        "in this shareholder letter and our",
        "Q3’24 Form 10-Q filed with the",
        "SEC on October 30, 2024.",
        "Q3 was a solid quarter for Coinbase across our three priorities for 2024: driving revenue, crypto",
    ]
    assert _rounding_note_block_len(lines, 0) == 8
    assert _rounding_note_block_len(lines, 8) == 0


def test_rounding_note_short_form_wrapped_consumes_two_lines() -> None:
    lines = [
        "Note: Figures presented may not",
        "sum precisely due to rounding.",
        "Transaction Revenue",
        "2024 transaction revenue was $4.0 billion, up 162% Y/Y.",
    ]
    assert _rounding_note_block_len(lines, 0) == 2


def test_rounding_note_chain_covers_sentence_break_on_line_boundary() -> None:
    # The flattening may put the long form's sentence break on a line
    # boundary: the first sentence terminates on its own line, and the
    # second ("For additional financial information ...") follows. The
    # chain rule consumes the second sentence too; without it the
    # "For additional ..." lines would be served as lede content.
    lines = [
        "Figures have been rounded for presentation purposes only.",
        "For additional financial information and a",
        "reconciliation between GAAP and non-GAAP results,",
        "please refer to the reconciliation of GAAP to Non-GAAP results",
        "table in this shareholder letter and our Form 10-Q filed with",
        "the SEC on May 8, 2025.",
        "We delivered strong financial results in Q1.",
    ]
    assert _rounding_note_block_len(lines, 0) == 6
    assert _rounding_note_block_len(lines, 6) == 0


def test_asterisk_note_regex() -> None:
    from tickerlens.data.filings import _ASTERISK_NOTE_LEAD_RE

    # Attested note openers, spaced and attached.
    assert _ASTERISK_NOTE_LEAD_RE.match("* Based on the closing price of")
    assert _ASTERISK_NOTE_LEAD_RE.match("*Below reporting threshold of 10%.")
    assert _ASTERISK_NOTE_LEAD_RE.match(
        "*Net of USDC loaned or pledged as collateral."
    )
    assert _ASTERISK_NOTE_LEAD_RE.match(
        "*As of December 31, 2024, USDC excludes $169M of USDC loaned"
    )
    assert _ASTERISK_NOTE_LEAD_RE.match(
        "* Measures used in this release that are not based on accounting"
    )
    # A "*" bullet is not a note — the batch-165 bullet stays a bullet.
    assert not _ASTERISK_NOTE_LEAD_RE.match("* Revenue grew 12 percent.")
    assert _is_inline_bullet_start("* Revenue grew 12 percent.")
    # A bare glyph alone is not a note opener.
    assert not _ASTERISK_NOTE_LEAD_RE.match("*")
    # The attached-glyph footnote definition is the footnote rule's, not
    # this one.
    assert not _ASTERISK_NOTE_LEAD_RE.match("*Non-GAAP Financial Measure")
    # Known limitations, deliberately uncovered: the "During" form and the
    # quoted-term form are not served by any path today.
    assert not _ASTERISK_NOTE_LEAD_RE.match(
        "*During the first quarter of 2024, we revised our definition of"
    )
    assert not _ASTERISK_NOTE_LEAD_RE.match(
        "*‘Major’ stablecoins include all stablecoins with over"
    )


def test_asterisk_note_block_consumes_four_lines() -> None:
    # Verbatim lines 32-35 of the Q1 FY2025 shareholder letter, then prose.
    lines = [
        "* Based on the closing price of",
        "Coinbase’s Class A common stock",
        "on May 7, 2025 on the Nasdaq",
        "Global Stock Market.",
        "We delivered strong financial results in Q1, generating $2.0",
    ]
    assert _asterisk_note_block_len(lines, 0) == 4
    assert _asterisk_note_block_len(lines, 4) == 0


def test_asterisk_note_single_line_forms() -> None:
    assert (
        _asterisk_note_block_len(["*Below reporting threshold of 10%.",
                                   "Transaction Revenue"], 0)
        == 1
    )
    assert (
        _asterisk_note_block_len(
            ["*Net of USDC loaned or pledged as collateral.",
             "Note: Figures presented may not sum precisely due to rounding."],
            0,
        )
        == 1
    )


def test_quarter_title_regex() -> None:
    assert _QUARTER_TITLE_RE.match("First Quarter 2025")
    assert _QUARTER_TITLE_RE.match("Second Quarter 2025")
    assert _QUARTER_TITLE_RE.match("Third Quarter 2024")
    assert _QUARTER_TITLE_RE.match("Fourth Quarter and Full Year 2024")
    assert not _QUARTER_TITLE_RE.match("First Quarter 2025 Results")
    assert not _QUARTER_TITLE_RE.match("Q1 2025")
    assert not _QUARTER_TITLE_RE.match("Bärengasse 32")
    assert not _QUARTER_TITLE_RE.match("Second Quarter 2026 Earnings Results")


def test_quarter_title_not_masthead_residue() -> None:
    assert not _looks_like_masthead_residue("First Quarter 2025")
    assert not _looks_like_masthead_residue("Second Quarter 2025")
    assert not _looks_like_masthead_residue("Fourth Quarter and Full Year 2024")
    # Address lines still are residue.
    assert _looks_like_masthead_residue("Bärengasse 32")
    assert _looks_like_masthead_residue("Louisville, KY 40202")
    assert _looks_like_masthead_residue("100 First Stamford Place, Suite 700")


def test_quarter_title_not_bare_masthead_name() -> None:
    # Verbatim head of the Q2 FY2025 letter: the date + page number count
    # as residue and the unterminated "[1] Adjusted EBITDA is a non-GAAP
    # financial" counts as headline-shaped, so the old code skipped the
    # title as a bare masthead name and jumped to the footnote.
    lines = [
        "EX-99.1",
        "2",
        "q225shareholderletter.htm",
        "EX-99.1",
        "Second Quarter 2025",
        "July 31, 2025",
        "1",
        "[1] Adjusted EBITDA is a non-GAAP financial",
        "measure.",
        "[2] Adjusted Net Income is a non-GAAP financial",
        "measure that excludes $1.5 billion in pre-tax gains on",
        "strategic investments.",
    ]
    assert _skip_bare_masthead_name(lines, 4) is None


def _coin_q1_2025_head() -> list[str]:
    # Verbatim head of the Q1 FY2025 letter (lines 4-36), with the [3]-[6]
    # definitions abbreviated to their key lines — the block skip consumes
    # them the same way — then the letter prose.
    return [
        "First Quarter 2025",
        "May 8, 2025",
        "1",
        "[1] This is a non-GAAP financial measure.",
        "[2] $USD resources is defined as cash and cash",
        "equivalents and USDC (net of USDC loaned or",
        "pledged as collateral).",
        "[3] Trading volume represents the total US dollar",
        "equivalent value of spot matched trades transacted",
        "between a buyer and seller through our platform",
        "during the period of measurement.",
        "Figures have been rounded for presentation purposes",
        "only. For additional financial information and a",
        "reconciliation between GAAP and non-GAAP results,",
        "please refer to the reconciliation of GAAP to Non-",
        "GAAP results table in this shareholder letter and our",
        "Form 10-Q filed with the SEC on May 8, 2025.",
        "* Based on the closing price of",
        "Coinbase’s Class A common stock",
        "on May 7, 2025 on the Nasdaq",
        "Global Stock Market.",
        "We delivered strong financial results in Q1, generating $2.0 billion in total revenue, $66 million in net income,",
        "$527 million in Adjusted Net Income (excluding the tax-effected impact of crypto investment asset gains/",
        "losses), and $930 million in Adjusted EBITDA. Total transaction revenue was $1.3 billion and subscription and",
        "services revenue was nearly $700 million, driven by growth in stablecoin revenue and Coinbase One.",
    ]


def test_coin_q3_2024_orphaned_referral_sentence_drops() -> None:
    # The Q3 FY2024 shape in miniature: short note + orphaned referral
    # sentence + prose. The referral paragraph drops; the prose serves.
    # (The full Q3 FY2024 letter still leaks the [1] footnote's second
    # sentence and the [3] definition's "USDC (" wrap — separate follow-up
    # shapes, not covered here — so this test uses a clean head.)
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Third Quarter 2024",
            "October 30, 2024",
            "Note: Figures presented may not",
            "sum precisely due to rounding.",
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
    assert "For additional financial information" not in hl
    assert "sum precisely due to rounding" not in hl


def test_coin_q1_2025_end_to_end() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(*_coin_q1_2025_head())
    )
    assert hl is not None
    assert hl.split("\n")[0] == "First Quarter 2025"
    assert "We delivered strong financial results in Q1" in hl
    assert "$527 million in Adjusted Net Income" in hl
    assert "Figures have been rounded" not in hl
    assert "closing price" not in hl
    assert "Coinbase’s Class A common stock" not in hl
    assert "non-GAAP financial measure" not in hl


def test_coin_q2_2025_end_to_end() -> None:
    # The bare-masthead regression: without the quarter-title guard the
    # title is skipped, the footnote block is skipped, and the rounding
    # note becomes the headline.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Second Quarter 2025",
            "July 31, 2025",
            "1",
            "[1] Adjusted EBITDA is a non-GAAP financial",
            "measure.",
            "[2] Adjusted Net Income is a non-GAAP financial",
            "measure that excludes $1.5 billion in pre-tax gains on",
            "strategic investments.",
            "Figures have been rounded for presentation purposes",
            "only. For additional financial information and a",
            "reconciliation between GAAP and non-GAAP results,",
            "please refer to the reconciliation of GAAP to Non-",
            "GAAP results tables in this shareholder letter and our",
            "Form 10-Q filed with the SEC on July 31, 2025.",
            "We delivered solid financial results in Q2, generating $1.5 billion in total revenue, $1.4 billion in net income",
            "(which includes both a $1.5 billion gain on strategic investments and a $362 million gain on crypto investment",
            "assets), $33 million in Adjusted Net Income (which excludes both aforementioned items) and $512 million in",
            "Adjusted EBITDA. Transaction revenue was $764 million. Subscription and services revenue was $656 million,",
        )
    )
    assert hl is not None
    assert hl.split("\n")[0] == "Second Quarter 2025"
    assert "We delivered solid financial results in Q2" in hl
    assert "Figures have been rounded" not in hl
    assert "Adjusted EBITDA is a non-GAAP" not in hl


def test_coin_q4_2024_end_to_end() -> None:
    # The stored body was the rounding paragraph alone; the live
    # extraction now serves the letter prose under the title headline.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Fourth Quarter and Full Year 2024",
            "February 13, 2025",
            "1",
            "[1] Q4 and full year 2024 net income included $476",
            "million and $687 million in pre-tax gains on our crypto",
            "asset investment portfolio, respectively, the vast",
            "majority of which were unrealized. These gains were",
            "$357 million and $514 million after reflecting the tax",
            "impact, respectively.",
            "Figures have been rounded for presentation purposes",
            "only. For additional financial information and a",
            "reconciliation between GAAP and non-GAAP results,",
            "please refer to the reconciliation of GAAP to Non-",
            "GAAP results table in this shareholder letter and our",
            "Form 10-K filed with the SEC on February 13, 2025.",
            "Coinbase delivered strong Q4 and full year 2024 results, with full year revenue of $6.6 billion, net",
            "income of $2.6 billion, and Adjusted EBITDA of $3.3 billion. Zooming out, the last few months have",
            "demonstrated a sea change in the regulatory environment, unlocking new opportunities for",
            "Coinbase and the crypto industry.",
        )
    )
    assert hl is not None
    assert hl.split("\n")[0] == "Fourth Quarter and Full Year 2024"
    assert "Coinbase delivered strong Q4 and full year 2024 results" in hl
    assert "Figures have been rounded" not in hl
    assert "pre-tax gains on our crypto" not in hl


def test_star_bullets_still_serve() -> None:
    # The asterisk-note whitelist must not eat "*" bullets: a release
    # whose highlights are "*"-led items keeps them.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "ACME REPORTS THIRD QUARTER 2025 RESULTS",
            "October 30, 2025",
            "* Revenue grew 12 percent year over year to $410 million.",
            "* Net income was $1.2 billion, up 8 percent year over year.",
            "* Adjusted EBITDA margin expanded to 31 percent.",
            "* Free cash flow of $890 million funded a $500 million buyback.",
        )
    )
    assert hl is not None
    assert "Revenue grew 12 percent" in hl
    assert "Net income was $1.2 billion" in hl
    assert "Adjusted EBITDA margin expanded" in hl


def test_salvage_drops_rounding_note_sentence() -> None:
    salvaged = _salvage_page_line_lede(
        "OMAHA, May 2, 2026 - Acme Inc. announced first quarter results today. "
        "Figures have been rounded for presentation purposes only. "
        "Revenue grew 12 percent year over year to $410 million. "
        "Gross margin expanded to 31 percent as subscription solutions grew 26 percent. "
        "Note: Figures presented may not sum precisely due to rounding. "
        "Free cash flow of $890 million funded a $500 million buyback program."
    )
    assert salvaged is not None
    assert "Revenue grew 12 percent" in salvaged
    assert "Gross margin expanded" in salvaged
    assert "Free cash flow" in salvaged
    assert "Figures have been rounded" not in salvaged
    assert "sum precisely due to rounding" not in salvaged
