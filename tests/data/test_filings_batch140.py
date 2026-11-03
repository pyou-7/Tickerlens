"""Batch 140 regression tests: lone bullet markers are never stored.

A DB-wide audit found two junk shapes in stored press-release
highlights, both from bullet lists flattened with the marker on its own
line:

- Lede path: a mid-lede marker became its own paragraph (42 rows:
  SPG/NUE/CB/CI/SNPS/SLB/GIS/KVUE/ON/NDAQ/VRSK/UNP). Batch 139 kept
  mid-lede markers as separators on the theory that they separate
  bullets in the rendered paragraphs — but paragraphs are already
  blank-line separated, so a lone marker paragraph renders as a junk
  glyph line and adds no separation. This batch supersedes that choice:
  markers are never appended to the lede (marker_seen is still set, so
  the batch-139 finish rule and budget behavior are unchanged).
- Section path: a marker became its own line inside a "\n"-joined
  section paragraph (50 rows, e.g. Nucor). The section collector now
  drops lone-marker lines AFTER qualification, so the 12-line cap and
  the 150-char floor see the same lines as before.
- Leading-bullet-block path: same flattening, same post-qualification
  filter — a doc opening with flattened bullets otherwise stores a
  glyph line per item.

Also covered: bare "Page N of M" paragraphs are already skipped by
_ADMIN_LINE_RE in both paths (MetLife's stored rows predate that rule);
the batch-140 repair drops them from stored rows, no code change.
"""

from tickerlens.data.filings import (
    _extract_highlights_sections,
    _is_lone_bullet_marker,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def test_lede_markers_are_not_stored_as_paragraphs() -> None:
    # This doc takes the leading-bullet-block path (bullets immediately
    # after the headline), so the items land in one "\n"-joined
    # paragraph; the assertion is path-agnostic: no lone-marker line
    # anywhere, and every item present.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Acme Reports Third Quarter Results",
            "•",
            "Bullet one reports net income of $1.21 billion, up 14 percent.",
            "•",
            "Bullet two reports net premiums written of $4.8 billion, up 6 percent.",
            "•",
            "Bullet three reports book value per share of $142.18, up 11 percent.",
        )
    )
    assert hl is not None
    assert "Bullet one reports net income of $1.21 billion" in hl
    assert "Bullet two reports net premiums written of $4.8 billion" in hl
    assert "Bullet three reports book value per share of $142.18" in hl
    assert not any(
        _is_lone_bullet_marker(ln) for part in hl.split("\n\n") for ln in part.split("\n")
    )


def test_lede_finish_rule_survives_marker_dropping() -> None:
    # Batch-139 boundary behavior, minus the separator paragraphs: the
    # marker at the budget boundary still ends collection, and bullet
    # four still never appears.
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Acme Reports Third Quarter Results",
            "•",
            "Bullet one reports net income of $1.21 billion, up 14 percent.",
            "Bullet one continues with core operating income up 9 percent.",
            "•",
            "Bullet two reports net premiums written of $4.8 billion, up 6 percent.",
            "Bullet two continues with a combined ratio of 87.2 percent.",
            "•",
            "Bullet three reports book value per share of $142.18, up 11 percent.",
            "Bullet three continues with tangible book value up 13 percent.",
            "•",
            "Bullet four must not appear in the extracted highlights at all.",
        )
    )
    assert hl is not None
    parts = hl.split("\n\n")
    assert "Bullet four must not appear" not in hl
    assert len(parts) == 7  # headline + 6 content lines, no markers
    assert not any(_is_lone_bullet_marker(p) for p in parts)


def test_section_path_markers_are_not_stored_as_lines() -> None:
    # Nucor shape: a "Highlights" section whose flattened bullets put
    # the marker on its own line.
    sections = _extract_highlights_sections(
        [
            "Third Quarter Highlights:",
            "•",
            "Consolidated net earnings attributable to Nucor stockholders of $249.9 million, or $1.05 per diluted share.",
            "•",
            "Adjusted net earnings attributable to Nucor stockholders of $353.0 million, or $1.49 per diluted share.",
            "•",
            "Net sales of $7.44 billion for the quarter ended September 30, 2024.",
        ]
    )
    assert sections
    flat = "\n".join(sections[0])
    assert "Consolidated net earnings" in flat
    assert "Adjusted net earnings" in flat
    assert "Net sales of $7.44 billion" in flat
    assert not any(_is_lone_bullet_marker(ln) for ln in sections[0])


def test_section_qualification_unchanged_by_marker_dropping() -> None:
    # A section that qualifies only with its markers counted toward the
    # 150-char floor still qualifies: filtering happens after the floor
    # check, so qualification is identical to pre-batch-140 behavior.
    sections = _extract_highlights_sections(
        [
            "Highlights:",
            "•",
            "Net income of $1.21 billion, up 14 percent, with core operating income of $1.18 billion, up 9 percent.",
            "•",
            "Net premiums written of $4.8 billion, up 6 percent, and a combined ratio of 87.2 percent for the quarter.",
        ]
    )
    assert sections
    assert len(sections[0]) == 2
    assert not any(_is_lone_bullet_marker(ln) for ln in sections[0])


def test_marker_glued_to_text_is_still_content() -> None:
    # Only a line that IS a marker is dropped; "• Net income ..." keeps
    # its text (the batch-115 headline-strip rule handles the headline).
    hl = extract_press_release_highlights(
        _contact_release_html(
            "Acme Reports Third Quarter Results",
            "• Net income was $1.21 billion, up 14 percent.",
            "• Net premiums written were $4.8 billion, up 6 percent.",
        )
    )
    assert hl is not None
    assert "Net income was $1.21 billion" in hl
    assert "Net premiums written were $4.8 billion" in hl


def test_black_square_and_en_dash_are_lone_markers() -> None:
    # The post-repair DB scan found two more glyphs standing alone that
    # the predicate missed: PNC's "▪" and Simon's "–" (the hyphen-minus
    # was covered, the en dash was not). Both are bullet glyphs, never
    # prose — and a glued "– Net income ..." line is still content.
    assert _is_lone_bullet_marker("▪")
    assert _is_lone_bullet_marker("–")
    assert not _is_lone_bullet_marker("– Net income was $1.21 billion.")
