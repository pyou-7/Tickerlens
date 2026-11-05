"""Batch 158 regression tests: multi-line CEO quotes in the leading
bullet block.

Alphabet's Q2 FY2026 release opens its quote on the line after the last
bullet — "Sundar Pichai, CEO of Google and Alphabet, said: "Our AI
investments are redefining what's possible across every part of our
business." — and the quote runs three more lines before closing with
"globally."". The old item-close rule broke the block at the first
terminated line, so the stored highlights ended mid-quote. The rule now
keeps the item open while its quotation is unbalanced.
"""

from tickerlens.data.filings import (
    _current_leading_item_text,
    _item_has_open_quote,
    _leading_bullet_block,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html

_GOOGL_Q2_BULLETS = [
    "•Consolidated Alphabet revenues increased 24%, or 23% in constant "
    "currency, to $119.8 billion, reflecting strong performance across the "
    "business and our 12th consecutive quarter of double-digit revenue growth.",
    "•Google Services revenues increased 15% to $94.5 billion, led by 17% "
    "growth in Google Search & other, 15% in Google subscriptions, "
    "platforms, and devices, and 13% in YouTube ads.",
    "•Google Cloud saw a meaningful acceleration in growth as revenues "
    "increased 82% to $24.8 billion, led by an increase in Google Cloud "
    "Platform (GCP) across enterprise AI Solutions and enterprise AI "
    "Infrastructure, as well as core GCP services.",
    "•Consolidated Alphabet operating income increased 30% and operating "
    "margin expanded by 2 percentage points to 34%.",
    "•Other income reflected a net gain of $98.0 billion, primarily the "
    "result of net unrealized gains on our equity securities.",
    "•Net income available to common stockholders increased 298% and EPS "
    "increased 294% to $9.11.",
]
_GOOGL_Q2_QUOTE = [
    "Sundar Pichai, CEO of Google and Alphabet, said: “Our AI investments "
    "are redefining what’s possible across every part of our business.",
    "Q2 was an amazing quarter, with Alphabet revenues growing 24% "
    "year-over-year and Google Cloud revenues accelerating to 82% growth, "
    "driven by demand for AI infrastructure and AI solutions. It’s great to "
    "see wide adoption of Gemini Enterprise, with nearly 90% of the Fortune "
    "100 using it.",
    "We have exciting momentum across the board. Our popular AI features are "
    "driving Search query growth. Gemini models now process 22 billion API "
    "tokens per minute and the Gemini App has 950 million monthly active "
    "users. We are seeing strong demand for our security solutions, and our "
    "new Gemini 3.5 Flash Cyber delivers highly cost-efficient performance "
    "at the frontier. And month over month, people turn to YouTube for major "
    "world events, with over 1.7 billion unique viewers watching World "
    "Cup-related videos during the FIFA World Cup 2026TM.",
    "These outstanding results show that our differentiated, full stack "
    "approach to AI is delivering real, measurable value for consumers, "
    "customers, and our partners globally.”",
]


def test_item_has_open_quote_curly_and_straight() -> None:
    # Batch 158: curly quotes nest by depth, straight quotes toggle.
    assert not _item_has_open_quote("no quote here.")
    assert not _item_has_open_quote("CEO said: “Great quarter.”")
    assert _item_has_open_quote("CEO said: “Great quarter.")
    assert not _item_has_open_quote('CEO said: "Great quarter."')
    assert _item_has_open_quote('CEO said: "Great quarter.')
    # Mixed forms compose: a curly opener closed by a straight quote.
    assert not _item_has_open_quote('CEO said: “Great quarter."')
    # A closed quote in an earlier sentence does not keep the item open.
    assert not _item_has_open_quote(
        "“First sentence.” Second sentence ends here."
    )


def test_current_leading_item_text_is_last_item_only() -> None:
    # Batch 158: the quote state is judged on the current item, not the
    # whole block — an earlier item's closed quote must not keep a later
    # item open.
    bullets = [
        "•First item with a closed quote: “Done.”",
        "•Second item still open: “Not done.",
        "continuation line.",
    ]
    assert _current_leading_item_text(bullets) == (
        "•Second item still open: “Not done.\ncontinuation line."
    )
    assert _item_has_open_quote(_current_leading_item_text(bullets))


def test_multiline_quote_not_truncated_in_leading_block() -> None:
    # Batch 158: the GOOGL Q2 FY2026 shape — the quote opener ends with a
    # period inside the still-open quote, so the old rule broke the block
    # there. All four quote lines must be collected, and the block must
    # still end at the Highlights heading.
    block = _leading_bullet_block(
        [
            *_GOOGL_Q2_BULLETS,
            *_GOOGL_Q2_QUOTE,
            "Q2 2026 Financial Highlights (unaudited)",
            "The following table summarizes our consolidated financial "
            "results for the quarters ended June 30, 2025 and 2026.",
        ]
    )
    assert block is not None
    assert len(block) == 10  # 6 bullets + 4 quote lines
    assert block[-1].endswith("globally.”")
    assert "Financial Highlights" not in "\n".join(block)
    assert "The following table summarizes" not in "\n".join(block)


def test_quote_closed_on_same_line_still_closes_item() -> None:
    # Boundary: when the quote opens and closes on the same continuation
    # line, the item still closes there — the dateline prose after it is
    # not collected.
    block = _leading_bullet_block(
        [
            "•Revenues increased 12% to $96.5 billion.",
            "•Net income increased 28% and EPS increased 31% to $2.15.",
            "Sundar Pichai, CEO, said: “Q4 was a strong quarter.”",
            "MOUNTAIN VIEW, Calif. – February 4, 2025 – Alphabet Inc. today "
            "announced financial results.",
        ]
    )
    assert block is not None
    assert len(block) == 3
    assert "MOUNTAIN VIEW" not in "\n".join(block)


def test_straight_quote_multiline_kept_open() -> None:
    # Boundary: straight double quotes toggle, so a multi-line quote in
    # straight quotes is kept open the same way.
    block = _leading_bullet_block(
        [
            "•Revenues increased 12% to $96.5 billion.",
            'CEO said: "Our AI investments are redefining what is possible.',
            "Momentum is strong across every part of the business.",
            'We expect the growth to continue."',
            "Q4 2024 Financial Highlights",
        ]
    )
    assert block is not None
    assert len(block) == 4
    assert block[-1].endswith('continue."')
    assert "Financial Highlights" not in "\n".join(block)


def test_unclosed_quote_still_bounded_by_heading() -> None:
    # Boundary: a quote that never closes cannot run away — the Highlights
    # heading break above the item-close rule still ends the block, and the
    # 14-line cap bounds it even without a heading.
    block = _leading_bullet_block(
        [
            "•Revenues increased 12% to $96.5 billion.",
            "CEO said: “Our AI investments are redefining what is possible.",
            "Momentum is strong across every part of the business.",
            "We expect the growth to continue.",
            "Q4 2024 Financial Highlights",
            "The following table summarizes our results.",
        ]
    )
    assert block is not None
    assert len(block) == 4
    assert "Financial Highlights" not in "\n".join(block)


def test_googl_q2_shaped_release_serves_full_quote() -> None:
    # Batch 158 end-to-end: the shaped Q2 FY2026 release serves the whole
    # quote through the leading block, and the table section stays out.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "EX-99.1",
            "Exhibit 99.1",
            "July 23, 2026",
            "Alphabet Announces Second Quarter 2026 Results",
            "MOUNTAIN VIEW, Calif. – July 23, 2026 – Alphabet Inc. (NASDAQ: "
            "GOOG, GOOGL) today announced financial results for the quarter "
            "ended June 30, 2026.",
            *_GOOGL_Q2_BULLETS,
            *_GOOGL_Q2_QUOTE,
            "Q2 2026 Financial Highlights (unaudited)",
            "The following table summarizes our consolidated financial results "
            "for the quarters ended June 30, 2025 and 2026 (in millions, except "
            "for per share information and percentages).",
            "Quarter Ended June 30,",
            "2025 2026",
            "Revenues $ 96,428 $ 119,796",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Alphabet Announces Second Quarter 2026 Results"
    # Batch 198: live bullets are spaced after the glyph ("• Net ...").
    assert "• Consolidated Alphabet revenues increased 24%" in hl
    assert "• Net income available to common stockholders increased 298%" in hl
    assert "Sundar Pichai, CEO of Google and Alphabet, said:" in hl
    assert "across every part of our business." in hl
    assert "Gemini models now process 22 billion API tokens per minute" in hl
    assert "globally.”" in hl
    assert "The following table summarizes" not in hl
    assert "Quarter Ended June 30" not in hl
    assert "Revenues $ 96,428" not in hl
