"""Batch 219: parenthesized letter <sup> footnote keys get spaces in
_html_to_text.

Batch 218 spaced digit-only keys ("Financial Guidance1" -> "Financial
Guidance 1") and left letter keys untouched. A parenthesized letter
key ("(a)", "(b)") is a footnote key exactly like "(1)" — it glues
the same way ("Net ACL build / (release)(a)", "RoTCE(c)") and spaces
the same way. Multi-key runs in one sup ("(a)(b)", "(b)(c)(d)(e)(f)(g)")
normalize to space-joined keys, like consecutive digit sups.

Still glued, deliberately: ordinals ("20th", "53rd" — word parts),
trademarks ("SM", "TM", "®", "©" — typographically attached to the
brand), the "○" table glyph, a "." sup, empty sups, and sups carrying
prose ("(a) Represents ..."). Bare letter keys do not occur in the
cache (census: 0), so only the parenthesized shape is handled.

Census of the 1,699-exhibit cache: 4,290 digit-key sups (batch 218),
547 paren-letter singles, 52 multi-letter runs (all in Citi tables),
35 ordinals, 158 SM/TM/® (+147 "&reg;" entities), 22 "○", 126 empty,
1 "."; zero bare letter keys, zero mixed digit/letter runs.

Also in this batch: the entity-strip in _sup_key_marker gains
&#8195; (em space) and &#8201; (thin space), so CB's "(1)&#8195;&#8201;"
digit key reads as a key and spaces (1 corpus occurrence).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import _html_to_text

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def test_letter_key_spaced_after_word():
    assert _html_to_text(
        "<div>Net ACL build / (release)<sup>(a)</sup></div>"
    ) == "Net ACL build / (release) (a)"
    assert _html_to_text("<div>RoTCE<sup>(c)</sup></div>") == "RoTCE (c)"
    assert _html_to_text("<div>Other provisions<sup>(b)</sup> end</div>") == (
        "Other provisions (b) end"
    )


def test_letter_key_spaced_before_word_and_after_digit():
    # Line-leading key: no space before, one after.
    assert _html_to_text("<div><sup>(a)</sup>Represents the change</div>") == (
        "(a) Represents the change"
    )
    # A paren key after a digit spaces like a paren digit key.
    assert _html_to_text(
        "<div>May 10, 2025<sup>(a)</sup>Sales per store</div>"
    ) == "May 10, 2025 (a) Sales per store"


def test_multi_key_runs_normalize():
    assert _html_to_text("<div>word<sup>(a)(b)</sup> end</div>") == (
        "word (a) (b) end"
    )
    assert _html_to_text("<div>word<sup>(b)(c)(d)</sup> end</div>") == (
        "word (b) (c) (d) end"
    )
    assert _html_to_text("<div>word<sup>(a) (b)</sup> end</div>") == (
        "word (a) (b) end"
    )
    assert _html_to_text("<div>word<sup>(1)(2)</sup> end</div>") == (
        "word (1) (2) end"
    )
    # Consecutive letter sups space apart, like digit sups.
    assert _html_to_text("<div>word<sup>(a)</sup><sup>(b)</sup> end</div>") == (
        "word (a) (b) end"
    )


def test_ordinals_trademarks_glyphs_stay_glued():
    assert _html_to_text("<div>20<sup>th</sup> consecutive quarter</div>") == (
        "20th consecutive quarter"
    )
    assert _html_to_text("<div>53<sup>rd</sup> week of operations</div>") == (
        "53rd week of operations"
    )
    assert _html_to_text("<div>Chubb<sup>SM</sup> are trademarks</div>") == (
        "ChubbSM are trademarks"
    )
    assert _html_to_text("<div>Brand<sup>&reg;</sup> shoes</div>") == (
        "Brand® shoes"
    )
    assert _html_to_text("<div>Flowing<sup>&reg;</sup> by providing</div>") == (
        "Flowing® by providing"
    )


def test_non_key_sups_unchanged():
    # A "." sup is punctuation; an empty sup is a no-op; a sup
    # carrying prose is not a key at all.
    assert _html_to_text("<div>November 19, 2022<sup>.</sup></div>") == (
        "November 19, 2022."
    )
    assert _html_to_text("<div>GAAP Diluted EPS<sup></sup></div>") == (
        "GAAP Diluted EPS"
    )
    assert _html_to_text(
        "<div><sup>(a) Represents the change</sup></div>"
    ) == "(a) Represents the change"
    # Mixed digit/letter runs are ambiguous: left unchanged.
    assert _html_to_text("<div>word<sup>(1)(a)</sup> end</div>") == (
        "word(1)(a) end"
    )


def test_em_space_digit_key_spaced():
    # CB's "(1)&#8195;&#8201;" digit key: the whitespace entities are
    # stripped, so the batch-218 digit path fires.
    assert _html_to_text(
        "<div>2023 includes a<sup>(1)&#8195;&#8201;</sup>change</div>"
    ) == "2023 includes a (1) change"


def test_citi_letter_keys_spaced_live():
    # Citi's tables carry (a)/(b)/(c) footnote keys in sups. The
    # guidance/highlights blast is 0-diff (tables never reach those
    # extractors), but the flattened text itself spaces them: 85 spaced
    # letter keys in C_2024-12-31, zero glued.
    import re

    t = _html_to_text(_read("C_2024-12-31.html"))
    assert len(re.findall(r" \([a-z]\)", t)) == 85
    assert not re.search(r"[A-Za-z0-9]\([a-z]\)", t)
    assert "RoTCE (d)" in t
    assert "revenues (a)" in t
    assert "RoTCE(d)" not in t
