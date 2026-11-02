"""Batch 176: a paren-led line can be a wrapped prose continuation,
not a footnote definition.

The paren footnote shape ("(1) ...", "(a) ...") is the loosest marker
— it also matches a parenthesized abbreviation that a wrapped sentence
breaks on. Three attested cases, all in the batch-174 audit remainder:
  - Arista: a bullet wraps mid-parenthetical ("... multi-planar
    leaf-spine design" / "(MRC) protocol, and segment routing over
    IPv6 (SRv6), aimed at maximizing AI cluster utilization and
    resilience.") — the section collector dropped the bullet's tail.
  - Plug: a bullet wraps on its abbreviation ("... improved by 25%
    quarter-over-quarter" / "(QoQ) and 46% year-over-year (YoY),
    driven by margin expansion ...").
  - Merck: a sentence wraps on its abbreviation ("... compared to
    intravenous" / "(IV) KEYTRUDA. Merck also announced the
    initiation of waveLINE-010 ...") — "(IV)" completes
    "intravenous (IV)".
Fix: _is_paren_prose_continuation — a paren-led line whose text after
the marker starts lowercase (a sentence resuming mid-flow) or whose
first sentence is a single word with a new sentence after it (a bare
term, not a definition) is prose, not a footnote definition. The
previous line is deliberately not consulted: a genuine definition can
follow an unterminated table row (Lilly's "(1) Tirzepatide is
marketed ..." follows the revenue table's last row).
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_paren_prose_continuation,
    _opens_footnote_def,
    extract_press_release_highlights,
)


def test_lowercase_lead_is_continuation():
    # Arista's wrapped bullet tail.
    assert _is_paren_prose_continuation(
        "(MRC) protocol, and segment routing over IPv6 (SRv6), aimed at maximizing AI cluster utilization and resilience."
    )
    assert not _opens_footnote_def(
        "(MRC) protocol, and segment routing over IPv6 (SRv6), aimed at maximizing AI cluster utilization and resilience.",
        "",
    )
    # Plug's wrapped bullet tail.
    assert _is_paren_prose_continuation(
        "(QoQ) and 46% year-over-year (YoY), driven by margin expansion and increased working capital"
    )
    assert not _opens_footnote_def(
        "(QoQ) and 46% year-over-year (YoY), driven by margin expansion and increased working capital",
        "",
    )


def test_single_word_first_sentence_is_continuation():
    # Merck's wrapped sentence: "(IV)" completes "intravenous (IV)",
    # and the line then starts a new sentence.
    assert _is_paren_prose_continuation(
        "(IV) KEYTRUDA. Merck also announced the initiation of waveLINE-010, a Phase 3 trial evaluating a combination regimen."
    )
    assert not _opens_footnote_def(
        "(IV) KEYTRUDA. Merck also announced the initiation of waveLINE-010, a Phase 3 trial evaluating a combination regimen.",
        "",
    )


def test_genuine_paren_definitions_still_open():
    # BlackRock's footnote pointers/definitions.
    assert not _is_paren_prose_continuation(
        "(1) See note (4) to the condensed consolidated statements of income and supplemental information on page 13 for more information on ACV."
    )
    assert _opens_footnote_def(
        "(1) See note (4) to the condensed consolidated statements of income and supplemental information on page 13 for more information on ACV.",
        "",
    )
    assert not _is_paren_prose_continuation(
        '(1) These expenses have been excluded from the Company\'s "as adjusted" financial results under the expense adjustments for acquisitions.'
    )
    assert _opens_footnote_def(
        '(1) These expenses have been excluded from the Company\'s "as adjusted" financial results under the expense adjustments for acquisitions.',
        "",
    )
    # CarMax's "(1) Comparisons ..." and Lilly's "(1) Tirzepatide ..."
    # both start capitalized with a multi-word first sentence.
    assert not _is_paren_prose_continuation(
        "(1) Comparisons to the prior year’s second quarter unless otherwise stated."
    )
    assert _opens_footnote_def(
        "(1) Comparisons to the prior year’s second quarter unless otherwise stated.",
        "",
    )
    assert not _is_paren_prose_continuation(
        "(1) Tirzepatide is marketed for obesity under the brand name Zepbound in Canada, Japan, and the United States."
    )
    assert _opens_footnote_def(
        "(1) Tirzepatide is marketed for obesity under the brand name Zepbound in Canada, Japan, and the United States.",
        "",
    )


def test_bare_marker_and_figure_fragment_still_open():
    # Centene's bare "(1)" marker line and Constellation's table
    # fragment "(210) (0.67)": no sentence after the marker (the
    # decimal point is not a sentence terminator), so neither fires.
    assert not _is_paren_prose_continuation("(1)")
    assert _opens_footnote_def("(1)", "")
    assert not _is_paren_prose_continuation("(210) (0.67)")
    assert _opens_footnote_def("(210) (0.67)", "")
    assert not _is_paren_prose_continuation("(5) (0.02)")
    assert _opens_footnote_def("(5) (0.02)", "")


def test_abbreviation_and_decimal_first_sentences_still_open():
    # "U.S." splits after one letter and "3.5" after a digit — neither
    # is a single-word first sentence.
    assert not _is_paren_prose_continuation(
        "(1) U.S. sales grew 5% year-over-year."
    )
    assert _opens_footnote_def("(1) U.S. sales grew 5% year-over-year.", "")
    assert not _is_paren_prose_continuation(
        "(1) 3.5 million shares were repurchased during the quarter."
    )
    assert _opens_footnote_def(
        "(1) 3.5 million shares were repurchased during the quarter.", ""
    )


def _extract(body_lines):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


def test_arista_style_release_keeps_wrapped_bullet_tail():
    # The (MRC) line is the wrapped tail of the "Arista detailed ..."
    # bullet; the leading-bullet block must serve it, not drop it as
    # a footnote definition.
    out = _extract(
        [
            "Arista Networks Reports Strong Second Quarter Results",
            "\u2022Revenue of $3.036 billion, an increase of 37.7% from the second quarter of 2025.",
            "\u2022Arista detailed new innovations for scale-up, scale-out, and scale-across AI fabrics \u2013 The company outlined techniques including multi-planar leaf-spine design",
            "(MRC) protocol, and segment routing over IPv6 (SRv6), aimed at maximizing AI cluster utilization and resilience.",
            "\u2022GAAP operating margin of 45.4% and non-GAAP operating margin of 49.9%.",
            "SANTA CLARA, Calif., July 28, 2026 - Arista Networks, Inc. (NYSE: ANET) today reported financial results for the second quarter of 2026. Revenue was $3.036 billion.",
            "Second-Quarter 2026 Results",
            "Financial Comparisons - Second-Quarter Operations",
            "(Dollars in millions, except per share amounts) Q2 2026 Q2 2025",
            "Revenue $3,036 $2,205",
        ]
    )
    assert out is not None
    assert "(MRC) protocol, and segment routing over IPv6 (SRv6)" in out
    assert "Arista detailed new innovations" in out


def test_merck_style_lede_keeps_wrapped_sentence_tail():
    # The "(IV) KEYTRUDA." line completes the dateline paragraph's
    # "compared to intravenous" and starts a new sentence on the same
    # line; the lede must serve it.
    out = _extract(
        [
            "Merck Announces First-Quarter 2025 Financial Results",
            "\u2022First-quarter sales of $15.5 billion, up 2% year-over-year.",
            "\u2022KEYTRUDA sales of $7.2 billion, up 4% year-over-year.",
            "RAHWAY, N.J., April 24, 2025 - Merck (NYSE: MRK) today announced first-quarter 2025 results. In the first quarter, Merck continued to advance its broad pipeline. In oncology, Merck presented pivotal data evaluating the subcutaneous administration of pembrolizumab. If approved, subcutaneous pembrolizumab has the potential to become a new treatment option that may increase access and save time needed for administration compared to intravenous",
            "(IV) KEYTRUDA. Merck also announced the initiation of waveLINE-010, a Phase 3 trial evaluating a combination regimen.",
            "First-Quarter 2025 Results",
            "(Dollars in millions, except per share amounts) Q1 2025 Q1 2024",
            "Sales $15,500 $15,200",
        ]
    )
    assert out is not None
    assert "(IV) KEYTRUDA. Merck also announced the initiation of waveLINE-010" in out


def test_leading_bullets_still_drop_genuine_paren_footnote():
    out = _extract(
        [
            "Arista Networks Reports Strong Second Quarter Results",
            "\u2022Revenue of $3.036 billion, an increase of 37.7% from the second quarter of 2025.",
            "\u2022Arista detailed new innovations for scale-up, scale-out, and scale-across AI fabrics \u2013 The company outlined techniques including multi-planar leaf-spine design",
            "(MRC) protocol, and segment routing over IPv6 (SRv6), aimed at maximizing AI cluster utilization and resilience.",
            "\u2022GAAP operating margin of 45.4% and non-GAAP operating margin of 49.9%.",
            "(1) Comparisons to the prior year\u2019s second quarter unless otherwise stated.",
            "SANTA CLARA, Calif., July 28, 2026 - Arista Networks, Inc. (NYSE: ANET) today reported financial results for the second quarter of 2026. Revenue was $3.036 billion.",
            "Second-Quarter 2026 Results",
            "Financial Comparisons - Second-Quarter Operations",
            "(Dollars in millions, except per share amounts) Q2 2026 Q2 2025",
            "Revenue $3,036 $2,205",
        ]
    )
    assert out is not None
    assert "(MRC) protocol, and segment routing over IPv6 (SRv6)" in out
    assert "Comparisons to the prior year" not in out
