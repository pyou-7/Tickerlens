"""Batch 198: line-leading bullet glyphs get a space after them in
_html_to_text (\"•Net sales...\" -> \"• Net sales...\").

A bullet in its own inline element glues to its item text when the
tags are stripped; the stored rows from the older extractor already
carry the spaced form, and the served guidance/highlights cards render
the glued form on ~1,400 of the 1,699 cached exhibits.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _html_to_text,
    extract_management_guidance,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _bullet_html(glyph_entity: str, text: str) -> str:
    return (
        f"<div><font>{glyph_entity}</font>"
        f"<font>{text}</font></div>"
    )


def test_bullet_glyph_spaced_after_font_split():
    # &#8226; in its own <font>, text in the next: the classic DECK shape.
    assert _html_to_text(_bullet_html("&#8226;", "Net sales are expected.")) == (
        "• Net sales are expected."
    )


def test_all_bullet_glyphs_spaced():
    cases = {
        "&#8226;": "•",  # bullet
        "&#9679;": "●",  # black circle
        "&#9675;": "○",  # white circle
        "&#9702;": "◦",  # white bullet
        "&#9642;": "▪",  # black small square
        "&#9632;": "■",  # black square
        "&#183;": "·",  # middle dot
    }
    for entity, glyph in cases.items():
        got = _html_to_text(_bullet_html(entity, "Item text."))
        assert got == f"{glyph} Item text.", (entity, got)


def test_white_bullet_spaced():
    # U+25E6 WHITE BULLET, the DIS/DECK guidance sub-bullet.
    assert _html_to_text(_bullet_html("&#9702;", "HOKA up.")) == "◦ HOKA up."


def test_dash_bullet_spaced_only_before_letter():
    assert _html_to_text(_bullet_html("&#8211;", "Sales grew.")) == "– Sales grew."
    # A dash before a digit or "$" is a table negative, not a bullet.
    assert _html_to_text(_bullet_html("&#8211;", "$5 down.")) == "–$5 down."
    assert _html_to_text(_bullet_html("&#8211;", "123 units.")) == "–123 units."


def test_midline_bullet_untouched_and_already_spaced_untouched():
    assert _html_to_text("<div>Mid &#8226; inline stays.</div>") == (
        "Mid • inline stays."
    )
    assert _html_to_text(_bullet_html("&#8226;", " Already spaced.")) == (
        "• Already spaced."
    )


def test_first_line_bullet_spaced_despite_opening_tag_space():
    # The opening <div> becomes a leading space, stripped only after the
    # bullet regexes — the first line's bullet must still be spaced.
    html = (
        "<div><font>&#8226;</font><font>First line.</font></div>"
        "<div><font>&#8226;</font><font>Second line.</font></div>"
    )
    assert _html_to_text(html) == "• First line.\n• Second line."


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def test_deck_guidance_bullets_spaced_live():
    g = extract_management_guidance(_read("DECK_2025-09-30.html"))
    assert g is not None
    assert "◦ HOKA is expected to increase by a low-teens percentage" in g
    assert "◦ UGG is expected to increase by a low-to-mid-single-digit" in g
    assert "• Net sales are expected to be approximately $5.35 billion." in g
    assert "◦HOKA" not in g and "•Net" not in g


def test_dis_guidance_bullets_spaced_live():
    g = extract_management_guidance(_read("DIS_2025-12-27.html"))
    assert g is not None
    assert "• Q2 Fiscal 2026:" in g
    assert "◦ Entertainment:" in g
    assert "▪ Segment OI comparable to Q2 fiscal 2025" in g
    assert "•Q2" not in g and "◦Entertainment" not in g


def test_highlights_bullet_spaced_live():
    hl = extract_press_release_highlights(_read("AAL_2023-12-31.html"))
    assert hl is not None
    assert "• Record full-year revenue of approximately $53 billion." in hl
    assert "•Record" not in hl
