"""Batch 170 regression tests: "◦" sub-bullets in the leading-bullet block.

Netflix nests "◦" (white bullet, U+25E6) sub-bullets under "•" items in
its shareholder letters. The leading-bullet block's item-close rule
treated a terminated "◦" line followed by another "◦" line as the end
of the block — the "◦" line was appended as a wrap continuation of the
"•" item, ended with terminal punctuation, and the next line was not a
"•"/"-"/"*" start, so the block broke there and every bullet after the
first sub-bullet was lost (NFLX Q4 FY2024 live was 204 chars: one "•"
item + one "◦" line; the stored row is 801 chars). "◦" is now a bullet
start in the block, so a sub-bullet opens its own item and the block
keeps collecting.
"""
from tickerlens.data.filings import (
    _current_leading_item_text,
    _leading_bullet_block,
    extract_press_release_highlights,
)
from tests.data.test_filings_batch169 import _letter_html


def test_nflx_circle_sub_bullets_do_not_truncate_block() -> None:
    # The NFLX Q4 FY2024 head in miniature: date, salutation, a "•"
    # item with two "◦" sub-bullets, two more "•" items (one with three
    # "◦" subs), and a closing "•" item. On old code the live text was
    # the first "•" item + the first "◦" line (204 chars); the whole
    # list must now be served, salutation still dropped (batch 169).
    hl = extract_press_release_highlights(
        _letter_html(
            "EX-99.1",
            "Exhibit 99.1",
            "January 21, 2025",
            "Fellow shareholders,",
            "•In 2024, we executed on our plan to reaccelerate growth.",
            "◦For the year, revenue grew 16% and operating margin expanded "
            "six points to 27%. Operating income exceeded $10B for the "
            "first time in our history.",
            "◦In Q4, revenue increased 16% year over year, helped by 19M "
            "paid net adds, while operating income rose 52% year over "
            "year. We finished 2024 with 302M memberships.",
            "•Our Q4 slate outperformed even our high expectations: Squid "
            "Game season 2 is on track to become one of our most watched "
            "original series seasons, Carry-On joined our all-time Top 10 "
            "films list, the Jake Paul vs. Mike Tyson fight became the "
            "most-streamed sporting event ever and on Christmas Day we "
            "delivered the two most-streamed NFL games in history.",
            "•Our priorities for 2025 are to:",
            "◦Improve our core business with more series and films our "
            "members love, an enhanced product experience and growth of "
            "our ads business;",
            "◦Further develop newer initiatives such as live programming "
            "and games;",
            "◦Sustain healthy growth - we now forecast 2025 revenue of "
            "$43.5-$44.5B (+$0.5B vs. prior forecast, despite the "
            "strengthening of the US dollar) and an operating margin of "
            "29%, up one point from our prior forecast.",
            "•We maintain a leadership position in engagement, revenue "
            "and profit. We’re focused on improving all aspects of our "
            "service and, combined with the return in 2025 of our biggest "
            "shows (Squid Game, Wednesday and Stranger Things), we’re "
            "optimistic heading into the new year.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0].startswith(
        "•In 2024, we executed on our plan to reaccelerate growth."
    )
    assert "Fellow shareholders" not in hl
    assert "For the year, revenue grew 16%" in hl
    assert "In Q4, revenue increased 16% year over year" in hl
    assert "Our Q4 slate outperformed even our high expectations" in hl
    assert "Our priorities for 2025 are to:" in hl
    assert "Improve our core business with more series and films" in hl
    assert "Further develop newer initiatives" in hl
    assert "Sustain healthy growth - we now forecast 2025 revenue" in hl
    assert "We maintain a leadership position in engagement" in hl


def test_leading_bullet_block_circle_lines() -> None:
    # Unit level: the block keeps collecting past "◦" lines. The
    # closing prose line is appended by the pre-existing item-close
    # rule (append-then-break) and the block ends there — the line
    # after it is never collected.
    block = _leading_bullet_block(
        [
            "•First bullet with figures of $1.2 billion and revenue up "
            "13% year over year.",
            "◦Sub-bullet one with figures of $100 million and margin up "
            "six points to 27%.",
            "◦Sub-bullet two with figures of $200 million and 19M paid "
            "net adds in the quarter.",
            "•Second bullet with figures of $3.4 billion and operating "
            "income up 52% year over year.",
            "Prose after the block starts here and runs on for a while.",
        ]
    )
    assert block is not None
    assert len(block) == 5
    assert block[1].startswith("◦Sub-bullet one")
    assert block[3].startswith("•Second bullet")
    assert block[4].startswith("Prose after the block")

    closed = _leading_bullet_block(
        [
            "•First bullet with figures of $1.2 billion and revenue up "
            "13% year over year.",
            "◦Sub-bullet one with figures of $100 million and margin up "
            "six points to 27%.",
            "Prose after the block starts here and runs on for a while.",
            "More prose follows the dateline paragraph after the block.",
        ]
    )
    assert closed is not None
    assert len(closed) == 3
    assert closed[2].startswith("Prose after the block")
    assert "More prose follows" not in "\n".join(closed)

    # A block that opens on a "◦" line (its "•" parent was skipped
    # upstream) still collects — a sub-bullet is a bullet, not prose.
    opens_on_circle = _leading_bullet_block(
        [
            "◦Sub-bullet one with figures of $100 million and margin up "
            "six points to 27% for the year.",
            "•Second bullet with figures of $3.4 billion and operating "
            "income up 52% year over year.",
        ]
    )
    assert opens_on_circle is not None
    assert len(opens_on_circle) == 2


def test_current_item_starts_at_circle_bullet() -> None:
    # The open-quote check judges the current item, not the whole
    # block: a "◦" line starts a new item, so an earlier item's quote
    # state must not leak across it.
    assert _current_leading_item_text(
        ["•Item one.", "◦Sub item.", "wrap line."]
    ) == "◦Sub item.\nwrap line."
    assert _current_leading_item_text(
        ["•Item one.", "◦Sub item.", "•Item two."]
    ) == "•Item two."
