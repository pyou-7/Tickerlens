"""Batch 199: First Solar guidance gaps — the rule-line follower, the
intro-sentence anchor, the wrapped figure line, and the "1." footnote key.

Four defects, one ticker's guidance section:

1. The guidance table's last row ("Volume Sold 15.6GW to 16.3GW") was
   dropped: the horizontal rule after it matched the dash-led bullet
   branch of _is_guidance_section_end_follower, so the row read as a
   next-section heading. A rule line never opens a section, so the
   follower advance now skips it.
2. Interim releases introduce the table with a prose sentence ("Our
   2024 guidance has been updated as follows:") and no heading, so 9
   of 11 cached FSLR quarters extracted None. The intro sentence now
   anchors the section.
3. A wrapped table value on its own line ("$520M") is all-caps by
   construction and broke collection mid-table. A line with no
   two-letter word is never a heading.
4. The 2026 footnote defs use a "1." key ("1.Assumes ...",
   "3.Adjusted EBITDA reflects ...") which _is_bare_numbered_footnote
   never matched (the period between the key and the word). The key
   may now carry a period; the capital-after-number guard is
   unchanged, so decimal-led figures still never open a block.
5. A dividend declaration ("Quarterly Dividend", "Dividend
   Declaration" — COR, EXPE) ends the section: its follower paragraph
   carries "$0.48 per share", so the $-less follower test never fired
   on it and the declaration was collected as guidance.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_bare_numbered_footnote,
    _is_guidance_heading,
    _is_guidance_next_section_heading,
    _is_guidance_section_end_follower,
    extract_management_guidance,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _guidance_lines(name: str) -> list[str]:
    g = extract_management_guidance(_load(name))
    assert g is not None
    return [ln.strip() for ln in g.split("\n") if ln.strip()]


# --- Fix 1: the rule line is not a section-opening bullet -------------


def test_rule_line_is_not_a_follower():
    lines = [
        "Volume Sold 15.6GW to 16.3GW",
        "——————————",
        "(1)Includes $40 million to $60 million of ramp costs.",
    ]
    assert not _is_guidance_section_end_follower(lines, 0)


def test_rule_line_skipped_to_real_prose_follower():
    # Heading candidate, rule, then genuine next-section prose: still
    # a section end (the rule is skipped, the prose decides).
    lines = [
        "News and Highlights",
        "——————————",
        "First Solar announced today that it has signed a definitive agreement to acquire a manufacturing facility in Ohio.",
    ]
    assert _is_guidance_section_end_follower(lines, 0)


def test_volume_sold_row_served_2023():
    lines = _guidance_lines("FSLR_2023-12-31.html")
    assert "Volume Sold 15.6GW to 16.3GW" in lines
    assert "Net Sales $4.4B to $4.6B" in lines
    # The footnote definitions after the rule are skipped, not served.
    assert not any(ln.startswith("(1)Includes") for ln in lines)
    assert any("forward-looking statements" in ln for ln in lines)


def test_volume_sold_row_served_2024():
    lines = _guidance_lines("FSLR_2024-12-31.html")
    assert "Volume Sold 18GW to 20GW" in lines


# --- Fix 2: the guidance-intro sentence anchors the section ----------


def test_intro_sentence_is_a_guidance_heading():
    assert _is_guidance_heading("Our 2024 guidance has been updated as follows:")
    assert _is_guidance_heading(
        "Our 2024 guidance remains unchanged. The complete 2024 guidance is as follows:"
    )
    assert _is_guidance_heading(
        "Our 2026 guidance remains unchanged and is summarized below:"
    )
    assert _is_guidance_heading("Our updated 2026 guidance is summarized below:")


def test_intro_sentence_negatives():
    # No "as follows" / "summarized below" closing: never an anchor.
    assert not _is_guidance_heading("Our 2024 guidance was strong.")
    assert not _is_guidance_heading("Our 2024 guidance remains unchanged.")
    # Year must follow "Our" (optionally "updated"/"revised").
    assert not _is_guidance_heading("Our guidance for 2025 is as follows:")
    assert not _is_guidance_heading("We updated our 2024 guidance as follows:")


def test_intro_quarters_now_serve():
    for name in [
        "FSLR_2024-03-31.html",
        "FSLR_2024-06-30.html",
        "FSLR_2024-09-30.html",
        "FSLR_2025-03-31.html",
        "FSLR_2025-09-30.html",
        "FSLR_2026-03-31.html",
        "FSLR_2026-06-30.html",
        "FSLR_2026-09-30.html",
    ]:
        lines = _guidance_lines(name)
        assert any("Net Sales" in ln for ln in lines), name
        assert any("$" in ln for ln in lines), name


def test_intro_quarter_serves_prior_current_table():
    lines = _guidance_lines("FSLR_2024-03-31.html")
    assert lines[0] == "Our 2024 guidance has been updated as follows:"
    assert "Net Sales (1) $4.4B to $4.6B Unchanged" in lines


# --- Fix 3: a lone wrapped figure line is not a heading ---------------


def test_wrapped_figure_line_does_not_break_collection():
    lines = _guidance_lines("FSLR_2025-06-30.html")
    assert "$520M" in lines
    assert "Operating Income (4)" in lines
    assert "Volume Sold (1)" in lines
    assert "15.5GW to 19.3GW 16.7GW to 19.3GW" in lines


def test_all_caps_heading_still_breaks():
    # A real all-caps heading (two-letter word present) still ends the
    # section when the section already has signal — exercised through
    # the collector, since _is_guidance_next_section_heading itself
    # never fires on all-caps lines (the collector has its own
    # all-caps branch).
    html = (
        "<div>2025 Guidance</div>"
        "<div>Net Sales $5.3B to $5.8B</div>"
        "<div>Gross Margin $2.45B to $2.75B</div>"
        "<div>Operating Income $1.95B to $2.30B</div>"
        "<div>Earnings per Diluted Share $17.00 to $20.00</div>"
        "<div>CONFERENCE CALL DETAILS</div>"
        "<div>First Solar has scheduled a conference call for today.</div>"
    )
    g = extract_management_guidance(html)
    assert g is not None
    assert "Net Sales $5.3B to $5.8B" in g
    assert "CONFERENCE CALL DETAILS" not in g
    assert "scheduled a conference call" not in g


def test_all_caps_heading_still_breaks_live():
    # FSLR 2025-06-30's served guidance ends at the safe-harbor
    # paragraph; the all-caps "Conference Call Details" heading after
    # it is not collected.
    lines = _guidance_lines("FSLR_2025-06-30.html")
    assert not any("Conference Call Details" in ln for ln in lines)


# --- Fix 4: the "N." footnote key opens a footnote-def block ---------


def test_bare_numbered_footnote_with_period_key():
    assert _is_bare_numbered_footnote(
        "1.Assumes $2.10 billion to $2.19 billion of Section 45X tax credits."
    )
    assert _is_bare_numbered_footnote(
        "1. Adjustment item resides in the Corporate & Other reportable segment."
    )
    assert _is_bare_numbered_footnote(
        "3.Adjusted EBITDA reflects addbacks of approximately $217 million."
    )


def test_bare_numbered_footnote_period_key_negatives():
    # A decimal-led figure is not a footnote key.
    assert not _is_bare_numbered_footnote(
        "1.5 million shares are included in the diluted count."
    )
    assert not _is_bare_numbered_footnote("1.25 billion in revenue.")
    # A wrapped bullet continuation stays a continuation.
    assert not _is_bare_numbered_footnote("12 of them in Texas.")
    # A company name never opens a block.
    assert not _is_bare_numbered_footnote("3M reports quarterly results.")


def test_2026_footnote_defs_not_served():
    lines = _guidance_lines("FSLR_2026-03-31.html")
    assert not any(ln.startswith("1.Assumes") for ln in lines)
    assert not any(ln.startswith("3.Adjusted EBITDA reflects") for ln in lines)
    assert not any(ln.startswith("4.Defined as") for ln in lines)
    # The cadence sentence after the defs is genuine guidance prose.
    assert any("we anticipate our module sales" in ln for ln in lines)
    assert "Volume Sold 17.0GW to 18.2GW Unchanged" in lines


def test_2025_guidance_unchanged():
    # The already-correct Q4 release serves byte-identical guidance.
    lines = _guidance_lines("FSLR_2025-12-31.html")
    assert "Volume Sold 17.0GW to 18.2GW" in lines
    assert "Net Sales $4.9B to $5.2B" in lines


# --- Fix 5: a dividend declaration ends the guidance section ----------


def test_dividend_declaration_ends_section():
    lines = [
        "2026 Guidance",
        "Net Sales $5.3B to $5.8B",
        "Dividend Declaration",
        "The Company's Board of Directors declared a quarterly cash dividend of $0.60 per common share.",
    ]
    assert _is_guidance_next_section_heading(lines, 2)
    lines[2] = "Quarterly Dividend"
    assert _is_guidance_next_section_heading(lines, 2)
    # A dividend-policy sub-heading is not a declaration.
    lines[2] = "Dividend Policy"
    assert not _is_guidance_next_section_heading(lines, 2)


def test_dividend_tail_gone_cor_expe():
    for name in ["COR_2026-06-30.html", "EXPE_2025-12-31.html", "EXPE_2026-03-31.html"]:
        lines = _guidance_lines(name)
        assert not any("Dividend" in ln for ln in lines), name
        assert not any("declared a quarterly" in ln for ln in lines), name
    # ...while the rescued table rows survive.
    assert "Adjusted free cash flow ~$3.0B $3.0B" in _guidance_lines("COR_2026-06-30.html")
    assert "Gross bookings $34.6 - $35.2B" in _guidance_lines("EXPE_2025-12-31.html")
