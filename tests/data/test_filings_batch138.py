"""Batch 138 regression tests: lede-budget junk lines (Chubb Q4 2024).

Chubb's Q4 2024 exhibit flattens its bullet list as a lone "QUARTER"
section-heading tail followed by lone "●" markers, one per bullet. The
lede fallback spent two of its six lines on that junk — the heading
fragment and the leading marker — so the live body showed bullet 1 plus
a dangling "●" and cut bullet 2 mid-item, while the stored row (from an
older extraction) held both bullets complete.

The fix skips two shapes in the lede loop only: a lone all-caps word
(a section-heading tail — "QUARTER" from "Fourth Quarter", "YEAR" from
"Full Year" — never narrative prose) and a leading lone bullet marker
(a marker before any collected line carries no content; the bullet's
text follows on the next lines). Mid-lede markers are kept: they are
the only separators between bullets in the rendered paragraphs.
"""

from tickerlens.data.filings import (
    _is_lede_heading_fragment,
    _is_lone_bullet_marker,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def _cb_q4_2024_html() -> str:
    # Real Q4 2024 lede shape (exhibit 99.1): heading tail, lone markers,
    # two wrapped bullets. The masthead block is omitted: the test is
    # about the lede loop, not the masthead skips.
    return _contact_release_html(
        "Chubb Reports Fourth Quarter Results",
        "QUARTER",
        "●",
        "Net income and core operating income were $2.58 billion and $2.45 billion, or a record",
        "$3.05 billion and $3.00 billion on a pre-tax basis, respectively.",
        "●",
        "Global P&C net premiums written were up 6.7%, with commercial insurance up 6.4%",
        "and consumer insurance up 7.5%.",
        "●",
        "P&C underwriting income was a record $1.58 billion, up 3.8%.",
    )


def test_cb_q4_2024_lede_skips_heading_tail_and_leading_marker() -> None:
    hl = extract_press_release_highlights(_cb_q4_2024_html())
    assert hl is not None
    body = hl.split("\n\n", 1)[1]
    # No heading fragment and no leading marker in the body.
    assert not body.startswith("QUARTER")
    assert "QUARTER" not in body
    assert not body.startswith("●")
    # Both bullets complete: the budget now holds 6 content lines.
    assert "Net income and core operating income were $2.58 billion" in body
    assert "on a pre-tax basis, respectively." in body
    assert "Global P&C net premiums written were up 6.7%" in body
    assert "and consumer insurance up 7.5%." in body
    # The mid-lede marker separating the bullets is NOT kept: batch
    # 140 supersedes batch 138's keep-as-separator choice — paragraphs
    # are already blank-line separated, so a lone marker paragraph
    # renders as a junk glyph line.
    assert "\n\n●\n\n" not in body


def test_mid_lede_heading_fragment_skipped() -> None:
    # The full-year section's "YEAR" tail sits mid-lede (after the
    # quarter bullets); it must not consume a lede slot either.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Chubb Reports Fourth Quarter Results",
            "●",
            "Net income was $2.58 billion, up 20.1%, and core operating income was $2.45 billion.",
            "YEAR",
            "●",
            "Net income was a record $9.27 billion, up 2.7%, and core operating income was $9.20 billion.",
        )
    )
    assert hl is not None
    body = hl.split("\n\n", 1)[1]
    assert "YEAR" not in body
    assert "Net income was a record $9.27 billion" in body


def test_heading_fragment_guard_negatives() -> None:
    # Multi-word lines, mixed-case words, and digit-only lines are never
    # fragments — the rule is a single all-caps word only. A bare quarter
    # label ("Q4") is a fragment too: it is a section label, never prose.
    assert not _is_lede_heading_fragment("Fourth Quarter")
    assert not _is_lede_heading_fragment("Quarter")
    assert not _is_lede_heading_fragment("2024")
    assert _is_lede_heading_fragment("Q4")
    assert _is_lede_heading_fragment("QUARTER")
    assert _is_lede_heading_fragment("YEAR")


def test_lone_bullet_marker_guard_negatives() -> None:
    assert _is_lone_bullet_marker("●")
    assert _is_lone_bullet_marker("•")
    assert _is_lone_bullet_marker("-")
    assert _is_lone_bullet_marker("*")
    # A marker with text is content, not a lone marker.
    assert not _is_lone_bullet_marker("● Net income was $2.58 billion.")
    assert not _is_lone_bullet_marker("Net income was $2.58 billion.")


def test_leading_marker_kept_when_body_is_not_lede() -> None:
    # A document whose body starts with a lone marker but whose first
    # content line is a heading (not the lede path) is unaffected: the
    # skip lives in the lede loop only. Here the release has a Highlights
    # heading, so the section path runs and the marker never reaches the
    # lede loop at all.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Acme Reports Third Quarter Results",
            "Highlights",
            "●",
            "Revenue grew 10% year over year to $1.2 billion.",
            "Net income was $300 million, up 5%.",
        )
    )
    assert hl is not None
    assert "Revenue grew 10%" in hl
