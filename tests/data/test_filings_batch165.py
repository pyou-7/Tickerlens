"""Batch 165 regression tests: inline-bullet ledes finish the current item.

Skydance's Q2 FY2026 shareholder letter opens with a "Summary Points:"
bullet list whose markers are glued to the text ("•Q2 was our best
quarter ..."). The headline loop picks bullet 1 as the headline, the
"Summary Points:" heading sits before the headline so no Highlights
section is ever found, and the lede fallback serves the list — but the
batch-139 finish rule only fires for lone-marker ledes, so the 6-line
budget cut bullet 3 mid-sentence ("...and we're building our pipeline
across" with its two continuation lines dropped).

The fix adds a second trigger to the finish rule: a lede line that ends
grammatically unfinished (a wrap tail — trailing comma/semicolon/dash,
or a trailing conjunction/preposition/article/copula). A complete
statement does NOT trigger it, even without terminal punctuation: a
figure bullet ("•Share repurchases and dividends of $5.1B") and a
complete clause ("...up 181% and 148% year over year, respectively")
end the item, so the prose and tables that follow are never pulled in
as "continuation". A new bullet starting past the budget ends
collection at the boundary instead of starting an item that cannot
finish. A marker-less prose lede whose last line ends complete keeps
the old hard 6-line cap.
"""

from tickerlens.data.filings import (
    _LEDE_WRAP_TAIL_RE,
    _is_inline_bullet_start,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def test_wrap_tail_predicate() -> None:
    # Unfinished: the sentence continues on the next line.
    assert _LEDE_WRAP_TAIL_RE.search("...building our pipeline across")
    assert _LEDE_WRAP_TAIL_RE.search("...reports net income of $1.21 billion,")
    assert _LEDE_WRAP_TAIL_RE.search("...net income of $1.21 billion, up 14 percent and")
    assert _LEDE_WRAP_TAIL_RE.search("...revenue grew 10%, including")
    assert _LEDE_WRAP_TAIL_RE.search("...full-year EPS guidance is")
    assert _LEDE_WRAP_TAIL_RE.search("...net income was $1.21 billion, up 14 percent, or")
    # Complete: a figure bullet, a complete clause, a table header, a
    # terminated sentence — none of these is a wrap.
    assert not _LEDE_WRAP_TAIL_RE.search("•Share repurchases and dividends of $5.1B")
    assert not _LEDE_WRAP_TAIL_RE.search("•Diluted earnings per share was $0.78")
    assert not _LEDE_WRAP_TAIL_RE.search(
        "•Full-year FY27 EPS guidance of $24.37, up 181% year over year, respectively"
    )
    assert not _LEDE_WRAP_TAIL_RE.search(
        "(millions, except percentages and per share data) 2026 2025 Change"
    )
    assert not _LEDE_WRAP_TAIL_RE.search("Net income was $1.21 billion.")
    assert not _LEDE_WRAP_TAIL_RE.search("Revenue was up")
    # A semicolon separates clauses — it is not a wrap tail (Coinbase's
    # letter ends a paragraph with one before its footnote block).
    assert not _LEDE_WRAP_TAIL_RE.search(
        "...store more crypto than any other company;"
    )


def test_inline_bullet_start_predicate() -> None:
    assert _is_inline_bullet_start("•Q2 was our best quarter for retention.")
    assert _is_inline_bullet_start("• Q2 was our best quarter for retention.")
    assert _is_inline_bullet_start("● Net income was $2.32 billion.")
    assert _is_inline_bullet_start("- Revenue grew 12 percent.")
    assert _is_inline_bullet_start("* Revenue grew 12 percent.")
    assert _is_inline_bullet_start("· Net income was $2.32 billion.")
    assert _is_inline_bullet_start("○ Global P&C net premiums written.")
    assert _is_inline_bullet_start("▪ Net income was $2.32 billion.")
    assert _is_inline_bullet_start("– Site rental revenues grew.")
    # A lone marker is a separator, not a bullet start.
    assert not _is_inline_bullet_start("•")
    assert not _is_inline_bullet_start("-")
    assert not _is_inline_bullet_start("*")
    # Prose and table values are not bullet starts.
    assert not _is_inline_bullet_start("Net income was $2.32 billion.")
    assert not _is_inline_bullet_start("-$1,234")
    assert not _is_inline_bullet_start("1 Non-GAAP measures are detailed.")
    assert not _is_inline_bullet_start("")


def _skyd_q2_2026_html() -> str:
    # Real Q2 FY2026 "Summary Points" shape (ex99_q226.htm): the
    # headline is bullet 1, bullets wrap across lines, markers are
    # glued to the text. Bullet 4+ are present so a runaway finish
    # rule would be visible.
    return _contact_release_html(
        "EX-99",
        "Summary Points:",
        "•One year in, we’re proud of the great progress: including nearly doubling our theatrical slate",
        "from 8 to 15 films in 2026 and on track to release 15+ in 2027; 40 new or returning DTC series",
        "greenlit; and over 90 series and 800+ episodes expected from our TV studios in 2026.",
    # Batch 198: the fixture inputs stay glued (they exercise the
    # _html_to_text normalization), but the served output is spaced.
        "• Q2 was our best quarter for retention in Paramount+’s history, powered by Dutton Ranch, UFC,",
        "and the FIFA World Cup non-exclusively across six countries in Latin America, gaining ~2 million",
        "new Paramount+ subscribers in the quarter to reach 81.6 million worldwide.",
        "• Q2 film slate, led by Scary Movie, performed well, and we’re building our pipeline across",
        "Television Studios, Paramount Animation, and Skydance Sports for both first- and third-party",
        "distribution.",
        "•Our focus on creative execution and efficiency at TV Media is working: CBS held seven of the",
        "top 10 broadcast series in the most recent broadcast season, with an increase in profitability.",
    )


def test_skyd_q2_2026_bullet_three_completes() -> None:
    hl = extract_press_release_highlights(_skyd_q2_2026_html())
    assert hl is not None
    parts = hl.split("\n\n")
    assert parts[0] == (
        "One year in, we’re proud of the great progress: including "
        "nearly doubling our theatrical slate"
    )
    # Bullets 1-3 complete; bullet 4 never starts (it begins past the
    # budget, so the boundary rule ends collection instead).
    assert parts[1:] == [
        "from 8 to 15 films in 2026 and on track to release 15+ in 2027; 40 new or returning DTC series",
        "greenlit; and over 90 series and 800+ episodes expected from our TV studios in 2026.",
        "• Q2 was our best quarter for retention in Paramount+’s history, powered by Dutton Ranch, UFC,",
        "and the FIFA World Cup non-exclusively across six countries in Latin America, gaining ~2 million",
        "new Paramount+ subscribers in the quarter to reach 81.6 million worldwide.",
        "• Q2 film slate, led by Scary Movie, performed well, and we’re building our pipeline across",
        "Television Studios, Paramount Animation, and Skydance Sports for both first- and third-party",
        "distribution.",
    ]
    assert "Our focus on creative execution" not in hl
    assert not hl.rstrip().endswith("across")


def test_inline_bullet_at_budget_boundary_does_not_start() -> None:
    # Content reaches exactly 6 at the end of bullet 2; bullet 3's
    # first line must not appear — the boundary ends collection, no
    # dangling bullet start.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Acme Reports Third Quarter Results",
            "• Bullet one reports net income of $1.21 billion, up 14 percent.",
            "Bullet one continues with core operating income up 9 percent.",
            "Bullet one closes with a combined ratio of 87.2 percent.",
            "• Bullet two reports net premiums written of $4.8 billion, up 6 percent.",
            "Bullet two continues with book value per share of $142.18, up 11 percent.",
            "Bullet two closes with tangible book value up 13 percent.",
            "•Bullet three must not appear in the extracted highlights at all.",
            "Bullet three continues and must not appear either.",
        )
    )
    assert hl is not None
    parts = hl.split("\n\n")
    assert parts[0] == "Acme Reports Third Quarter Results"
    assert parts[1:] == [
        "• Bullet one reports net income of $1.21 billion, up 14 percent.",
        "Bullet one continues with core operating income up 9 percent.",
        "Bullet one closes with a combined ratio of 87.2 percent.",
        "• Bullet two reports net premiums written of $4.8 billion, up 6 percent.",
        "Bullet two continues with book value per share of $142.18, up 11 percent.",
        "Bullet two closes with tangible book value up 13 percent.",
    ]
    assert "Bullet three" not in hl


def test_inline_bullet_finishing_cap_bounds_long_wrapped_item() -> None:
    # The final bullet is one sentence wrapped across 7 fragment lines
    # (the attested shape — Skydance's bullets wrap mid-sentence, never
    # with terminal punctuation mid-item). Batch 165 capped the pull-in
    # at the first 4 continuation lines; batch 222's completion
    # allowance lets the unfinished item run to its close (all 7 lines,
    # ending terminated), so the highlights no longer end mid-bullet at
    # "tangible common equity of 18.2 percent annualized and". The cap
    # still bounds the pull-in (8 past the budget) and the next bullet
    # never starts.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Acme Reports Third Quarter Results",
            "• Alpha bullet opens with net income of $1.21 billion, up 14 percent.",
            "Alpha bullet continues with core operating income up 9 percent.",
            "Alpha bullet closes with a combined ratio of 87.2 percent.",
            "• Beta bullet opens with net premiums written of $4.8 billion.",
            "Beta bullet continues with commercial lines up 8 percent.",
            "• Gamma bullet opens with book value per share of $142.18 and",
            "tangible book value up 13 percent and ROE of 14.7 percent",
            "annualized and ROTE of 21.7 percent annualized and core",
            "operating ROE of 13.9 percent annualized and return on",
            "tangible common equity of 18.2 percent annualized and",
            "a CET1 ratio of 11.4 percent at quarter end with",
            "a supplementary leverage ratio of 7.1 percent and",
            "a liquidity coverage ratio of 132 percent at quarter end.",
            "•Delta bullet must not appear in the extracted highlights at all.",
        )
    )
    assert hl is not None
    parts = hl.split("\n\n")
    assert parts[1:] == [
        "• Alpha bullet opens with net income of $1.21 billion, up 14 percent.",
        "Alpha bullet continues with core operating income up 9 percent.",
        "Alpha bullet closes with a combined ratio of 87.2 percent.",
        "• Beta bullet opens with net premiums written of $4.8 billion.",
        "Beta bullet continues with commercial lines up 8 percent.",
        "• Gamma bullet opens with book value per share of $142.18 and",
        "tangible book value up 13 percent and ROE of 14.7 percent",
        "annualized and ROTE of 21.7 percent annualized and core",
        "operating ROE of 13.9 percent annualized and return on",
        "tangible common equity of 18.2 percent annualized and",
        "a CET1 ratio of 11.4 percent at quarter end with",
        "a supplementary leverage ratio of 7.1 percent and",
        "a liquidity coverage ratio of 132 percent at quarter end.",
    ]
    assert "Delta bullet" not in hl


def test_complete_figure_bullet_does_not_extend() -> None:
    # Visa/Nike/Dell shape: the 6th content line is a complete figure
    # bullet with no terminal punctuation. The table title and CEO quote
    # that follow are NOT continuations — the old extraction (bullet list
    # only) is exact.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "•Net revenue grew 10% in the first quarter, with payments volume up 9% and cross-border",
            "volume up 16% and processed transactions up 11% year over year.",
            "• GAAP EPS of $2.58, up 8% year over year",
            "• Non-GAAP EPS of $2.75, up 14% year over year",
            "• Payments volume up 9% year over year",
            "• Cross-border volume up 16% year over year",
            "• Share repurchases and dividends of $5.1B",
            "Income Statement Summary",
            "In billions, except percentages and per share data.",
            "Visa's strong first-quarter results reflected healthy spending during the holiday season.",
        )
    )
    assert hl is not None
    parts = hl.split("\n\n")
    assert parts[0] == (
        "Net revenue grew 10% in the first quarter, with payments volume "
        "up 9% and cross-border"
    )
    assert parts[1:] == [
        "volume up 16% and processed transactions up 11% year over year.",
        "• GAAP EPS of $2.58, up 8% year over year",
        "• Non-GAAP EPS of $2.75, up 14% year over year",
        "• Payments volume up 9% year over year",
        "• Cross-border volume up 16% year over year",
        "• Share repurchases and dividends of $5.1B",
    ]
    assert "Income Statement Summary" not in hl
    assert "healthy spending" not in hl


def test_prose_lede_finishes_a_wrapped_sentence() -> None:
    # Complement to batch 139's hard-cap test: when a prose lede's 6th
    # line ends mid-sentence (wrap tail), the sentence is finished
    # rather than cut — but the next sentence never starts.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Acme Reports Third Quarter Results",
            "Prose line one reports quarterly net income of $1.21 billion, up 14 percent.",
            "Prose line two reports core operating income of $1.18 billion, up 9 percent.",
            "Prose line three reports net premiums written of $4.8 billion, up 6 percent.",
            "Prose line four reports a combined ratio of 87.2 percent for the quarter.",
            "Prose line five reports book value per share of $142.18, up 11 percent.",
            "Prose line six reports tangible book value per share up 13 percent and",
            "adjusted book value per share up 15 percent for the quarter.",
            "Prose line eight must not appear in the extracted highlights at all.",
        )
    )
    assert hl is not None
    parts = hl.split("\n\n")
    assert parts[0] == "Acme Reports Third Quarter Results"
    assert parts[1:] == [
        "Prose line one reports quarterly net income of $1.21 billion, up 14 percent.",
        "Prose line two reports core operating income of $1.18 billion, up 9 percent.",
        "Prose line three reports net premiums written of $4.8 billion, up 6 percent.",
        "Prose line four reports a combined ratio of 87.2 percent for the quarter.",
        "Prose line five reports book value per share of $142.18, up 11 percent.",
        "Prose line six reports tangible book value per share up 13 percent and",
        "adjusted book value per share up 15 percent for the quarter.",
    ]
    assert "Prose line eight" not in hl
