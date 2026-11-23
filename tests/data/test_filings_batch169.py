"""Batch 169 regression tests: shareholder-letter salutation skip.

A shareholder letter opens "Fellow shareholders," / "Dear Shareholders,"
after the date — a greeting, never highlights. It is served three ways
today:

1. As the HEADLINE (NFLX): the headline loop picks the first short line
   it reaches, so the salutation becomes the headline and the date is
   lost to the admin skip.
2. As lede content (COIN Q3 FY2025, SKYD): the salutation sits between
   the date and the prose, or after a bullet mid-body.
3. As a leading-bullet continuation (AXON): the salutation follows the
   last bullet and the block appends it as a wrap.
"""
from tickerlens.data.filings import (
    _salutation_block_len,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def _letter_html(*lines: str) -> str:
    # Like _contact_release_html but without its 1600-char lorem filler:
    # the section path joins its lines into one paragraph, and a filler
    # that long trips the page-line guard (first paragraph > 1000 chars
    # with no headline returns None). The verbatim bullets below keep
    # the document over the 800-char floor on their own.
    body = "".join(f"<p>{ln}</p>" for ln in lines)
    return f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"


def test_salutation_block_len_shapes() -> None:
    assert _salutation_block_len(["Fellow shareholders,"], 0) == 1
    assert _salutation_block_len(["Fellow shareholders"], 0) == 1
    assert _salutation_block_len(["Dear Shareholders,"], 0) == 1
    assert _salutation_block_len(["Fellow Affirm Shareholders,"], 0) == 1
    assert _salutation_block_len(["Fellow shareholders."], 0) == 1
    # Split-line flattening (COIN Q3 FY2025): "Fellow" / "Shareholders,".
    assert _salutation_block_len(["Fellow", "Shareholders,"], 0) == 2
    assert _salutation_block_len(["Dear", "Shareholders,"], 0) == 2
    # A bare "Fellow" whose next line is prose is not a salutation.
    assert _salutation_block_len(["Fellow", "Q3 was strong."], 0) == 0
    # An inline salutation is a sentence, not a line: dropping it would
    # eat the prose with it (Instacart/Affirm's flattened form).
    assert (
        _salutation_block_len(
            ["Dear Shareholders, This is my first letter to you."], 0
        )
        == 0
    )
    # Prose that mentions shareholders is never a salutation.
    assert (
        _salutation_block_len(["Shareholders approved the merger."], 0)
        == 0
    )
    assert (
        _salutation_block_len(
            ["Fellow shareholders approved the buyback."], 0
        )
        == 0
    )
    assert _salutation_block_len(["Q3 was a strong quarter."], 0) == 0


def test_nflx_salutation_is_not_the_headline() -> None:
    # The NFLX Q3 FY2025 head in miniature: exhibit markers, date,
    # salutation, bullets. The letter has no headline — the live text
    # must open with the first bullet, not with the salutation.
    hl = extract_press_release_highlights(
        _letter_html(
            "EX-99.1",
            "Exhibit 99.1",
            "October 21, 2025",
            "Fellow shareholders,",
            "•Revenue in Q3 grew 17%, in-line with our forecast. Operating "
            "margin of 28% was below our guidance of 31.5% due to an "
            "expense related to an ongoing dispute with Brazilian tax "
            "authorities that was not in our forecast. Absent this expense, "
            "we would have exceeded our Q3'25 operating margin forecast. We "
            "don’t expect this matter to have a material impact on future "
            "results.",
            "•Engagement remains healthy. We hit our highest quarterly "
            "view share ever in the US and UK, which has grown 15% and "
            "22%, respectively since Q4’22, according to Nielsen and Barb.",
            "•In Q3, we made further progress against our 2025 priorities:",
            "◦We delivered a great slate including Wednesday S2, Bon "
            "Appétit, Your Majesty from South Korea, and Happy Gilmore 2, "
            "while KPop Demon Hunters became our most popular film ever.",
        )
    )
    assert hl is not None
    # Batch 198: live bullets are spaced after the glyph ("• Net ...").
    assert hl.split("\n\n")[0].startswith("• Revenue in Q3 grew 17%")
    assert "Fellow shareholders" not in hl
    assert "October 21, 2025" not in hl


def test_axon_salutation_drops_from_bullet_block() -> None:
    # The AXON Q4 FY2025 head in miniature: real headline, bullets,
    # salutation, prose. The salutation must not survive as a bullet
    # continuation; the headline and the prose stay.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Axon reports Q4 2025 revenue of $797 million, up 39% year "
            "over year",
            "•Software & Services revenue grows 40% to $343 million",
            "•Net income of $3 million supports non-GAAP net income of "
            "$178 million",
            "Fellow shareholders,",
            "Axon completed another record year in pursuit of our mission "
            "to protect life.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0].startswith(
        "Axon reports Q4 2025 revenue of $797 million"
    )
    assert "Fellow shareholders" not in hl
    assert "Software & Services revenue grows 40%" in hl
    assert "Axon completed another record year" in hl


def test_coin_split_salutation_drops_from_bullet_block() -> None:
    # The split salutation after bullets (COIN Q3 FY2025's "Fellow" /
    # "Shareholders," shape, here after the leading bullets so the lede's
    # heading-fragment rule cannot hide it): the leading-bullet block
    # would append both lines as a wrap continuation of the last bullet.
    # The salutation must not survive; the headline, the bullets, and
    # the prose stay.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Acme Reports Third Quarter 2025 Results",
            "•Revenue grew 17% year over year to $1.2 billion.",
            "•Operating margin of 28% was below our guidance of 31.5%.",
            "Fellow",
            "Shareholders,",
            "Q3 was a strong quarter for Acme. We drove solid financial "
            "results.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Acme Reports Third Quarter 2025 Results"
    assert "Fellow" not in hl
    assert "Shareholders," not in hl
    assert "Revenue grew 17%" in hl
    assert "Q3 was a strong quarter for Acme" in hl


def test_salutation_inside_highlights_section_drops() -> None:
    # A salutation between section bullets is dropped by the section
    # collector's post-qualification filter, like a footnote block.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Acme Reports Third Quarter 2025 Results",
            "Highlights",
            "•Revenue grew 17% year over year to $1.2 billion.",
            "Fellow shareholders,",
            "•Operating margin of 28% was below our guidance.",
        )
    )
    assert hl is not None
    assert "Fellow shareholders" not in hl
    assert "Revenue grew 17%" in hl
    assert "Operating margin of 28%" in hl


def test_headlineless_bullet_list_is_not_a_page_line() -> None:
    # Batch 169, guard refinement: the page-line guard bounds the
    # longest LINE, not the paragraph. An NFLX-style letter (date /
    # salutation / bullets, no headline) whose bullet list totals over
    # 1000 chars must still extract — the section path joins the list
    # with "\n", so the old paragraph-length test read it as one page
    # line and returned None (NFLX Q3 FY2024: 1385 chars, no line over
    # 350). A single line over 1000 chars still trips the guard (the
    # batch-163 dateline-less page-line test covers that shape).
    hl = extract_press_release_highlights(
        _letter_html(
            "EX-99.1",
            "Exhibit 99.1",
            "October 17, 2024",
            "Fellow shareholders,",
            "•In Q3, revenue grew 15% year over year and operating margin "
            "was 30% vs. 22% last year. For 2024, we expect revenue growth "
            "of 15% (the high end of our 14% to 15% range), and operating "
            "margin of 27% (vs 26% previously).",
            "•We’ve delivered a string of hits this quarter, including new "
            "series like The Perfect Couple, Nobody Wants This, and "
            "Monsters, alongside returning favorites that kept members "
            "watching all quarter long.",
            "•Engagement, our best proxy for member happiness, remains "
            "healthy. Through the first three quarters of 2024, viewing "
            "per membership is up year over year in every region.",
            "•We continue to build our advertising business and improve "
            "our offering for advertisers. Ads membership grew 35% "
            "quarter over quarter in the markets where ads are available.",
            "•We’ve delivered on our plan to reaccelerate our business, "
            "and we’re excited to finish the year strong with our Q4 "
            "slate and a growing advertising business.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0].startswith("• In Q3, revenue grew 15%")
    assert "Fellow shareholders" not in hl
    assert "We’ve delivered a string of hits" in hl
    assert "finish the year strong" in hl
