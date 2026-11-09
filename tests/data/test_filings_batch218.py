"""Batch 218: digit-only <sup> footnote keys get spaces in _html_to_text.

The flattener strips inline tags with no join, so a footnote key in
<sup> glues to its neighbors ("Financial Guidance1", "1Non-GAAP" —
the batch-217 residual wart; the older extractor spaced both sides).
A digit key is never part of a split word, so _html_to_text now wraps
digit keys in \\x02 markers and resolves them to spaces once the
neighbors are visible in flattened text. Letter keys ("(a)", "th",
"SM") and "®" are untouched — same class, separate batch.

Census of the 1,699-exhibit cache: 4,097 digit-key sups; zero
unit-exponent shapes ("m²", "ft²") and zero digit-key-digit chains,
so a bare key after a digit is a footnote on a year/amount ("2022 3,"),
never an exponent. A bare key wedged between a digit and a letter is
left glued (the "10²cm" shape); the one attested digit-letter case is
parenthesized ("2025 (1) Sales"). A run-length guard was rejected:
DE tables carry bare keys after 2-digit runs ("23 12", a footnote on
a table value), so guarding on run length would corrupt them.
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


def _read(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def test_key_spaced_after_word():
    assert _html_to_text("<div>Financial Guidance<sup>1</sup></div>") == (
        "Financial Guidance 1"
    )
    assert _html_to_text("<div>OUTLOOK<sup>2</sup></div>") == "OUTLOOK 2"
    assert _html_to_text("<div>Rent expense<sup>(1)</sup></div>") == (
        "Rent expense (1)"
    )


def test_key_spaced_before_word():
    # Line-leading key: no space before, one after.
    assert _html_to_text("<div><sup>3</sup>Adjusted debt to EBITDAR</div>") == (
        "3 Adjusted debt to EBITDAR"
    )
    assert _html_to_text(
        "<div>May 10, 2025<sup>(1)</sup>Sales per average store</div>"
    ) == "May 10, 2025 (1) Sales per average store"


def test_key_on_year_and_amount():
    # A bare key after a digit is a footnote, not an exponent: the
    # space keeps "2022" + "3" from collapsing into "20223".
    assert _html_to_text(
        "<div>for the third quarter 2022<sup>3</sup>, which included</div>"
    ) == "for the third quarter 2022 3, which included"
    assert _html_to_text("<div>revenue<sup>(1)</sup>. At the same time</div>") == (
        "revenue (1). At the same time"
    )


def test_consecutive_keys_and_multi_keys():
    assert _html_to_text("<div>word<sup>1</sup><sup>2</sup> end</div>") == (
        "word 1 2 end"
    )
    assert _html_to_text("<div>word<sup>(1) (2)</sup> end</div>") == (
        "word (1) (2) end"
    )


def test_non_digit_sup_untouched():
    # Ordinals, ®/SM: the old glued form stands. Batch 219: a
    # parenthesized letter key is now a spaced footnote key, like (1).
    assert _html_to_text("<div>10<sup>th</sup> anniversary</div>") == (
        "10th anniversary"
    )
    assert _html_to_text("<div>Item 1<sup>(a)</sup> text</div>") == (
        "Item 1 (a) text"
    )
    assert _html_to_text("<div>Brand<sup>&reg;</sup> shoes</div>") == (
        "Brand® shoes"
    )


def test_exponent_wedge_and_span_split_untouched():
    # A bare key wedged between a digit and a letter stays glued.
    assert _html_to_text("<div>10<sup>2</sup>cm</div>") == "102cm"
    # DFIN span-splitting still joins with no space.
    assert _html_to_text("<div>RIS</span><span>K FACTORS</div>") == (
        "RISK FACTORS"
    )
    assert _html_to_text("<div>H<sub>2</sub>O</div>") == "H2O"


def test_dal_guidance_keys_spaced_live():
    g = extract_management_guidance(_read("DAL_2024-12-31.html"))
    assert g is not None
    assert "Financial Guidance 1" in g
    assert "1 Non-GAAP" in g
    assert "3 Adjusted debt to EBITDAR" in g
    assert "4 Introduced at November 2024 Investor Day" in g
    assert "Financial Guidance1" not in g and "1Non-GAAP" not in g
    # Batch 217's 922 chars + 8 spaces (footnote keys 1-4 and friends).
    assert len(g) == 930


def test_ci_guidance_heading_still_anchors_live():
    # CI's bare-word heading was "OUTLOOK2" in text; the anchor's
    # digit-strip path must still fire on the spaced form.
    g = extract_management_guidance(_read("CI_2024-12-31.html"))
    assert g is not None
    assert "OUTLOOK 2" in g
    assert "OUTLOOK2" not in g


def test_highlights_keys_spaced_live():
    hl = extract_press_release_highlights(_read("CI_2023-09-30.html"))
    assert hl is not None
    assert "for adjusted income from operations 1,2 increased" in hl
    assert "per share 2" in hl
    assert "operations1" not in hl
