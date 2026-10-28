"""Batch 142 regression tests: page markers glued to body lines are stripped,
and a "view online" trailer glued onto a bullet no longer drops the bullet.

UnitedHealth's page-image exhibits flatten each page into one line, so
page 2+ markers land mid-paragraph ("Page 2 of 16 business, with ..."),
ahead of a bullet ("Page 2 of 17 • Optum ..."), or ahead of prose — and
the outlook bullet carries a "To view this information in a different
format, including graphics, published on our website, click here:
<url>" trailer whose www. tripped _CONTACT_LINE_RE and dropped the whole
bullet (the earnings outlook) from the leading-bullet block, the section,
and the lede. Both are cleaned on body lines only, after headline
selection, so batch 141's headline-loop page-prefix guard is untouched.
"""

from tickerlens.data.filings import extract_press_release_highlights
from tests.data.test_filings import _contact_release_html

_HEADLINE = "UnitedHealth Group Reports First Quarter 2026 Results"
_REVENUE = "• First Quarter 2026 Revenues of $111.7 Billion Grew 2% Year-over-Year"
_EPS = "• Earnings of $6.90 Per Share and Adjusted Earnings of $7.23 Per Share"
_OUTLOOK = (
    "• Full Year 2026 Earnings Outlook Raised to Greater Than $17.35 Per Share; "
    "Adjusted Earnings of Greater Than $18.25 Per Share"
)
_TRAILER = (
    " To view this information in a different format, including graphics, "
    "published on our website, click here: "
    "https://www.unitedhealthgroup.com/content/dam/UHG/PDF/investors/2026/unh-q1-2026.pdf"
    " (April 21, 2026) UnitedHealth Group (NYSE: UNH) today reported first "
    "quarter 2026 results, said Stephen Hemsley, chief executive officer."
)
_REFOCUS = "• Refocusing the organization on U.S. health care, exiting non-U.S. businesses."


def test_outlook_bullet_with_view_online_trailer_survives() -> None:
    # Real UNH Q1 2026 shape: the outlook bullet glues the trailer, the URL,
    # and flattened following prose onto one line. The bullet survives; the
    # trailer, the URL, and the glued prose (dropped with the whole line
    # before) do not.
    hl = extract_press_release_highlights(
        _contact_release_html(
            _HEADLINE, _REVENUE, _EPS, _OUTLOOK + _TRAILER, _REFOCUS
        )
    )
    assert hl is not None
    assert "Full Year 2026 Earnings Outlook Raised to Greater Than $17.35" in hl
    assert "click here" not in hl
    assert "unitedhealthgroup.com" not in hl
    assert "Hemsley" not in hl


def test_trailer_only_line_is_still_contact_skipped() -> None:
    # A line that IS the trailer (no bullet prefix) keeps the old behavior:
    # the contact guard skips it, since stripping would leave nothing.
    hl = extract_press_release_highlights(
        _contact_release_html(
            _HEADLINE,
            _REVENUE,
            _TRAILER.strip(),
            _EPS,
        )
    )
    assert hl is not None
    assert "click here" not in hl
    assert "unitedhealthgroup.com" not in hl
    assert "First Quarter 2026 Revenues of $111.7 Billion" in hl
    assert "Earnings of $6.90 Per Share" in hl


def test_page_prefixed_continuation_line_is_stripped() -> None:
    # Real UNH Q1 2026 shape: a page-2 continuation line inside the bullet
    # block keeps its prose, minus the marker.
    hl = extract_press_release_highlights(
        _contact_release_html(
            _HEADLINE,
            _REFOCUS,
            "Page 2 of 16 business, with $400 million in net proceeds "
            "committed to the United Health Foundation, and more actions "
            "under way.",
            "• First quarter 2026 adjusted net earnings were $7.23 per share.",
        )
    )
    assert hl is not None
    assert "Page 2 of 16" not in hl
    assert "business, with $400 million in net proceeds" in hl


def test_page_prefixed_bullet_line_becomes_a_bullet() -> None:
    # Real UNH Q2 2026 shape: the marker sits ahead of a bullet marker.
    hl = extract_press_release_highlights(
        _contact_release_html(
            _HEADLINE,
            _REVENUE,
            "Page 2 of 17 • Optum supported more than 120 million consumers "
            "and generated revenues of $65.7 billion in the quarter.",
        )
    )
    assert hl is not None
    assert "Page 2 of 17" not in hl
    assert "Optum supported more than 120 million consumers" in hl


def test_prose_page_reference_without_of_number_is_untouched() -> None:
    # Deliberate boundary: only the full "Page N of M" form is stripped.
    # A prose sentence starting "Page 2 of the report ..." must never be
    # beheaded into "of the report ...".
    hl = extract_press_release_highlights(
        _contact_release_html(
            _HEADLINE,
            "Page 2 of the report discusses the company's segment results "
            "in detail, with additional commentary on margins and the "
            "outlook for the remainder of the year.",
        )
    )
    assert hl is not None
    assert "Page 2 of the report discusses the company's segment results" in hl


def test_bare_page_line_in_body_still_skipped() -> None:
    # A standalone page line carries no content, so the admin guard still
    # skips it; the body strip only fires when a remainder exists.
    hl = extract_press_release_highlights(
        _contact_release_html(
            _HEADLINE, _REVENUE, "Page 2 of 16", _EPS, _REFOCUS
        )
    )
    assert hl is not None
    assert "Page 2 of 16" not in hl
    assert "First Quarter 2026 Revenues of $111.7 Billion" in hl
    assert "Earnings of $6.90 Per Share" in hl
