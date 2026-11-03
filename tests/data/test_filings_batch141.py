"""Batch 141 regression tests: a page marker glued to the headline is stripped.

UnitedHealth's page-image exhibits flatten page 1 into one bullet-run line,
and _split_bullet_runs leaves the marker on the first piece — "Page 1 of 16
UnitedHealth Group Reports First Quarter 2026 Results" — because the
bare-page admin guard is $-anchored and never fires when headline text
follows the marker. The headline loop now strips a leading "Page N of M" /
"Page N" prefix when the (wrap-joined) remainder is headline-shaped; the
strip is refused when the remainder is not headline-shaped, so a bare
fragment remainder keeps exactly the old behavior (see the last test).
"""

from tickerlens.data.filings import extract_press_release_highlights
from tests.data.test_filings import _contact_release_html

_UNH_BULLETS = (
    " • First Quarter 2026 Revenues of $111.7 Billion Grew 2% Year-over-Year"
    " • Earnings of $6.90 Per Share and Adjusted Earnings of $7.23 Per Share"
    " • Full Year 2026 Earnings Outlook Raised to Greater Than $17.35 Per Share"
    " • Optum Revenues Grew 4% Year-over-Year to $65.7 Billion in the Quarter"
)


def test_page_prefixed_bullet_run_headline_is_stripped() -> None:
    # Real UNH Q1 2026 shape: the page-1 line exceeds the 300-char headline
    # cap, so _split_bullet_runs splits it and the headline loop sees the
    # marker-glued first piece.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Page 1 of 16 UnitedHealth Group Reports First Quarter 2026 Results"
            + _UNH_BULLETS
        )
    )
    assert hl is not None
    assert (
        hl.split("\n\n")[0]
        == "UnitedHealth Group Reports First Quarter 2026 Results"
    )
    assert "Page 1 of 16" not in hl
    assert "First Quarter 2026 Revenues of $111.7 Billion" in hl
    assert "Earnings of $6.90 Per Share" in hl


def test_page_prefixed_plain_headline_is_stripped() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Page 1 of 16 UnitedHealth Group Reports First Quarter 2026 Results",
            "UnitedHealth Group (NYSE: UNH) today reported first quarter 2026 "
            "results, with performance supported by actions taken over the "
            "last several quarters, and the board authorized a new share "
            "repurchase program.",
        )
    )
    assert hl is not None
    assert (
        hl.split("\n\n")[0]
        == "UnitedHealth Group Reports First Quarter 2026 Results"
    )


def test_page_prefixed_wrapped_headline_joins() -> None:
    # The remainder may itself be a wrapped-headline fragment: strip first,
    # then join, so the joined result (not the fragment) is shape-checked.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Page 1 of 21 UnitedHealth Group Reports",
            "2025 Results and Issues 2026 Outlook",
            "UnitedHealth Group (NYSE: UNH) today reported full year 2025 "
            "results, with revenues growing strongly across both operating "
            "segments during the fourth quarter.",
        )
    )
    assert hl is not None
    assert (
        hl.split("\n\n")[0]
        == "UnitedHealth Group Reports 2025 Results and Issues 2026 Outlook"
    )
    assert "Page 1 of 21" not in hl


def test_page_prefix_without_of_is_stripped() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Page 3 UnitedHealth Group Reports Third Quarter 2026 Results",
            "UnitedHealth Group (NYSE: UNH) today reported third quarter 2026 "
            "results, with performance supported by actions taken over the "
            "last several quarters.",
        )
    )
    assert hl is not None
    assert (
        hl.split("\n\n")[0]
        == "UnitedHealth Group Reports Third Quarter 2026 Results"
    )


def test_page_prefix_match_is_case_insensitive() -> None:
    hl = extract_press_release_highlights(
        _contact_release_html(
            "page 1 of 16 UnitedHealth Group Reports First Quarter 2026 Results",
            "UnitedHealth Group (NYSE: UNH) today reported first quarter 2026 "
            "results, with performance supported by actions taken over the "
            "last several quarters.",
        )
    )
    assert hl is not None
    assert (
        hl.split("\n\n")[0]
        == "UnitedHealth Group Reports First Quarter 2026 Results"
    )


def test_bare_page_line_still_skipped_by_admin_guard() -> None:
    # The pre-existing shape (MetLife): a standalone page line carries no
    # headline text, so the $-anchored admin guard skips it and the real
    # headline follows. The new branch never sees it.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Page 1 of 26",
            "MetLife Announces Full Year and 4Q 2025 Results",
            "NEW YORK, February 5, 2025 - MetLife, Inc. (NYSE: MET) today "
            "announced its full year and fourth quarter 2025 results, with "
            "adjusted earnings up 10 percent year over year.",
        )
    )
    assert hl is not None
    assert (
        hl.split("\n\n")[0] == "MetLife Announces Full Year and 4Q 2025 Results"
    )


def test_page_prefixed_fragment_without_continuation_falls_through() -> None:
    # Deliberate boundary: a 3-word fragment remainder with no continuation
    # line is not headline-shaped, so the strip is refused and the old pick
    # (whole line, prefix included) stands — a fragment headline would be
    # worse than a prefixed complete one, and the next line is body prose,
    # not a headline continuation.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Page 1 of 21 UnitedHealth Group Reports",
            "UnitedHealth Group (NYSE: UNH) today reported full year 2025 "
            "results, with revenues growing strongly across both operating "
            "segments during the fourth quarter.",
        )
    )
    assert hl is not None
    assert hl.split("\n\n")[0] == "Page 1 of 21 UnitedHealth Group Reports"
