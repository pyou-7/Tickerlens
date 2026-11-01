"""Batch 164 regression tests: bare-numbered footnote definitions in
copula-pointer shape are never headline or lede material.

Skydance's Q2 FY2026 shareholder letter (`ex99_q226.htm`) opens with the
footnote line "1 Non-GAAP measures are detailed in the Supplemental
Disclosures at the end of this letter." — no closing paren, so the
batch-162 bare-numbered rule (`^\\d{1,3}\\)\\s`) never saw it, and no
definition verb, so the batch-104 rule never saw it either. The headline
loop picked it as the headline. The fix extends `_FOOTNOTE_DEF_RE` with a
numeric-key + defined-term + copula + definition-pointer alternative
("are detailed / is defined / is calculated / are reconciled / are set
forth / is described"), which the headline loop, the lede filter, the
section filter, and `_is_section_footnote_line` all already consult. The
same hazard class in `_leading_bullet_block` — a footnote line swallowed
as a bullet continuation — is closed in the same batch (no attested case
there; the batch-163 follow-up names the path).

The participle list is deliberately definition-pointer only: "are
included / provided / presented / discussed" stay OUT, because a wrapped
bullet continuation can legitimately read "1 million shares are included
in ..." — those verbs are prose, not footnote pointers, and the negative
tests pin that exclusion.
"""

from tickerlens.data.filings import (
    _FOOTNOTE_DEF_RE,
    _leading_bullet_block,
    extract_press_release_highlights,
)


def _bare_release_html(*lines: str) -> str:
    body = "".join(f"<p>{ln}</p>" for ln in lines)
    return f"<html><body>{body}</body></html>"


# Real Q2 FY2026 exhibit head (SKYD `ex99_q226.htm`, fetched 2026-10-31):
# exhibit header lines, the footnote line, page number, date, the
# "Summary Points:" heading, then the bullets (first three, verbatim).
SKYD_Q2_2026_LINES = [
    "EX-99",
    "2",
    "ex99_q226.htm",
    "EX-99",
    "Exhibit 99",
    "1 Non-GAAP measures are detailed in the Supplemental Disclosures at the end of this letter.",
    "2",
    "August 4, 2026",
    "Summary Points:",
    "•One year in, we’re proud of the great progress: including nearly doubling our theatrical slate",
    "from 8 to 15 films in 2026 and on track to release 15+ in 2027; 40 new or returning DTC series",
    "greenlit; and over 90 series and 800+ episodes expected from our TV studios in 2026.",
    "•Q2 was our best quarter for retention in Paramount+’s history, powered by Dutton Ranch, UFC,",
    "and the FIFA World Cup non-exclusively across six countries in Latin America, gaining ~2 million",
    "new Paramount+ subscribers in the quarter to reach 81.6 million worldwide.",
    "•Q2 film slate, led by Scary Movie, performed well, and we’re building our pipeline across",
    "Television Studios, Paramount Animation, and Skydance Sports for both first- and third-party",
    "distribution.",
]


def test_skyd_q2_2026_footnote_line_is_not_the_headline() -> None:
    # Batch 164: the stored row opened with the footnote line as its
    # headline. Now the first bullet (stripped, batch-115 lead-bullet
    # headline) leads, the footnote line is gone, and the bullets serve.
    result = extract_press_release_highlights(
        _bare_release_html(*SKYD_Q2_2026_LINES)
    )
    assert result is not None
    headline, _, body = result.partition("\n\n")
    assert headline == (
        "One year in, we’re proud of the great progress: including nearly "
        "doubling our theatrical slate"
    )
    assert "Non-GAAP measures are detailed" not in result
    assert "Summary Points:" not in result
    assert "Q2 was our best quarter for retention" in body
    assert "Q2 film slate, led by Scary Movie" in body


def test_footnote_def_copula_pointer_positives() -> None:
    # The attested shape plus its sibling participles.
    assert _FOOTNOTE_DEF_RE.match(
        "1 Non-GAAP measures are detailed in the Supplemental Disclosures "
        "at the end of this letter."
    )
    assert _FOOTNOTE_DEF_RE.match(
        "1 Adjusted EBITDA is defined as net income adjusted for "
        "stock-based compensation."
    )
    assert _FOOTNOTE_DEF_RE.match(
        "2 Free cash flow is calculated as operating cash flow less "
        "capital expenditures."
    )
    assert _FOOTNOTE_DEF_RE.match(
        "3 Non-GAAP measures are reconciled to the most directly "
        "comparable GAAP measures below."
    )
    assert _FOOTNOTE_DEF_RE.match(
        "1 Operating income is described in Note 2 to the financial statements."
    )
    assert _FOOTNOTE_DEF_RE.match(
        "2 Segment results are set forth in the tables below."
    )
    # The pre-existing shapes still match (batch 104/162 regression pins).
    assert _FOOTNOTE_DEF_RE.match(
        "1 Defined as remaining performance obligation (RPO)"
    )
    assert _FOOTNOTE_DEF_RE.match("*Non-GAAP Financial Measure")


def test_footnote_def_copula_pointer_negatives() -> None:
    # Real headlines and real prose must never match: a 4-digit year, a
    # quarter-prefixed headline, a number with no definition pointer, and
    # the deliberately excluded prose verbs ("are included" is a wrapped
    # bullet continuation, not a footnote pointer).
    assert not _FOOTNOTE_DEF_RE.match("2025 outlook raised")
    assert not _FOOTNOTE_DEF_RE.match("1Q26 record quarter")
    assert not _FOOTNOTE_DEF_RE.match("1 billion in buybacks")
    assert not _FOOTNOTE_DEF_RE.match(
        "1 million shares are included in the diluted count."
    )
    assert not _FOOTNOTE_DEF_RE.match(
        "2 new films are presented at the festival this fall."
    )
    assert not _FOOTNOTE_DEF_RE.match(
        "Q1 revenue of $7.3 billion grew 2% year-over-year."
    )


def test_footnote_def_mega_line_never_matches() -> None:
    # Batch 164 (blast catch): a Workiva page-flattened mega-line opens
    # with a bare number and contains a footnote-pointer phrase a
    # thousand chars in ("... are reconciled to the comparable GAAP
    # measure ...") — the unbounded copula form matched the whole page
    # and the lede dropped it, killing the batch-163 SHOP salvage. The
    # 300-char line bound keeps the guard to single-sentence footnote
    # definitions; the SHOP Q3 2024 end-to-end test in
    # test_filings_batch163.py is the other half of this pin.
    mega = (
        "1 Internet, Everywhere - November 12, 2024 - Shopify Inc. "
        "(NYSE, TSX: SHOP), a leading commerce technology company "
        "announced today financial results for the quarter ended "
        "September 30, 2024. (1) See notes below for definitions of "
        "GMV, MRR and additional information on Free Cash Flow and "
        "Free Cash Flow margin, which are non-GAAP financial measures "
        "and are reconciled to the comparable GAAP measure in the "
        "Condensed Consolidated Statement of Cash Flows. " + "x" * 1200
    )
    assert len(mega) > 1000
    assert not _FOOTNOTE_DEF_RE.match(mega)


def test_leading_bullet_block_skips_footnote_line() -> None:
    # Batch 164: a footnote-definition line sitting between leading
    # bullets is table residue, not a continuation of the bullet above it.
    block = _leading_bullet_block(
        [
            "•Revenue grew 5% year-over-year to $1.2 billion, ahead of our guidance range.",
            "1 Non-GAAP measures are detailed in the Supplemental Disclosures.",
            "•Adjusted EBITDA rose 10% to $300 million, with margins expanding 200 basis points.",
            "•Free cash flow was $150 million, up from $110 million a year ago.",
        ]
    )
    assert block is not None
    assert len(block) == 3
    assert "Non-GAAP" not in "\n".join(block)
    assert block[0].startswith("•Revenue grew")
    assert block[1].startswith("•Adjusted EBITDA")
    assert block[2].startswith("•Free cash flow")


def test_leading_bullet_block_keeps_number_led_continuation() -> None:
    # The mirror negative: a wrapped continuation starting with a small
    # number and a prose verb ("are included" — deliberately outside the
    # participle list) is still a continuation, not a footnote.
    block = _leading_bullet_block(
        [
            "•The buyback retired shares during the quarter",
            "1 million shares are included in the diluted count.",
            "•Revenue grew 5% year-over-year to $1.2 billion, ahead of our guidance range.",
        ]
    )
    assert block is not None
    assert "1 million shares are included in the diluted count." in "\n".join(block)
