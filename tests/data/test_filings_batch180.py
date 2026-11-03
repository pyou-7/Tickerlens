"""Batch 180: the "% change" footnote glued onto a quote attribution.

Visa flattens its summary-table footnote, the table's period header and
the CEO-quote attribution onto one lede line (7 non-Q4 quarters):

    % change is calculated over the comparable prior-year period. Q3 2024
    Ryan McInerney, Chief Executive Officer, Visa, commented on the results:

The line is table residue: the footnote and the period header are the
table's own text, and the attribution without its quote is a dangling
fragment. It only reaches the lede because batch 178 freed the budget
(the bare-units line above it is now skipped) — the stored rows predate
that and are clean, so live is currently WORSE than stored for these
quarters. Fix: _is_lede_footnote_attribution, wired into
_is_lede_table_line before the termination gate. Dropping the line frees
the budget for the quote itself, which follows the table.

The pin is behavioral: on stashed old code the predicate does not exist
(collection error) and the end-to-end test serves the defect line.

Companion fix in the same class: _is_lede_colon_heading's
quote-attribution veto covered "said"/"says" only, so a bare
"commented on the results:" attribution was classified as a colon
heading and dropped, orphaning the quote it introduces ("noted"/"added"
were already vetoed via _LEDE_COLON_VERB_RE). Batch 180 adds
"commented"/"comments" to the veto.
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_lede_colon_heading,
    _is_lede_footnote_attribution,
    _is_lede_table_line,
    extract_press_release_highlights,
)

V_DEFECT = (
    "% change is calculated over the comparable prior-year period. "
    "Q3 2024 Ryan McInerney, Chief Executive Officer, Visa, "
    "commented on the results:"
)
V_ATTRIBUTION = (
    "Ryan McInerney, Chief Executive Officer, Visa, "
    "commented on the results:"
)
V_FOOTNOTE = "% change is calculated over the comparable prior-year period."


def test_footnote_attribution_attested_v_line():
    assert _is_lede_footnote_attribution(V_DEFECT)
    assert _is_lede_table_line(V_DEFECT)


def test_footnote_attribution_verb_variants():
    # The attribution verb may be said/noted/added, with or without
    # "on the results".
    assert _is_lede_footnote_attribution(
        "% change is calculated over the comparable prior-year period. "
        "Q1 2025 Jane Doe, Chief Executive Officer, Acme, said:"
    )
    assert _is_lede_footnote_attribution(
        "% change is calculated over the comparable prior-year period. "
        "Q2 2025 Jane Doe, Chief Financial Officer, Acme, noted:"
    )


def test_footnote_attribution_bare_halves_are_not_residue():
    # A bare attribution is a legitimate quote intro (the colon-heading
    # veto protects "... said:" lines) — it is served, not dropped.
    assert not _is_lede_footnote_attribution(V_ATTRIBUTION)
    assert not _is_lede_table_line(V_ATTRIBUTION)
    # The colon-heading veto covers "commented" too (batch 180): a bare
    # "commented on the results:" attribution is never a heading.
    assert not _is_lede_colon_heading(V_ATTRIBUTION)
    assert not _is_lede_colon_heading(
        "Jane Doe, Chief Executive Officer, Acme, commented:"
    )
    # ... while a verb-less colon line is still a heading.
    assert _is_lede_colon_heading("Financial Results for the Quarter:")
    # A bare footnote line is a footnote-definition block, not this
    # predicate's class.
    assert not _is_lede_footnote_attribution(V_FOOTNOTE)
    # Prose that merely mentions the calculation, with no attribution
    # tail, is not residue either.
    assert not _is_lede_footnote_attribution(
        "The % change is calculated over the comparable prior-year "
        "period and was 10% for the quarter."
    )


def _extract(body_lines):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


def test_visa_style_release_drops_defect_line_and_serves_quote():
    out = _extract(
        [
            "Visa Reports Fiscal Third Quarter 2024 Results",
            "San Francisco, CA, July 23, 2024 – Visa (NYSE: V)",
            "•GAAP net income of $4.9B or $2.40 per share and non-GAAP net income of $4.9B or $2.42 per share",
            "•Net revenue of $8.9B, an increase of 10% on a nominal and constant-dollar basis",
            "•Growth in payments volume, cross-border volume and processed transactions remained relatively stable",
            "•Share repurchases and dividends of $5.8B",
            "Income Statement Summary",
            "In billions, except percentages and per share data.",
            V_DEFECT,
            "USD % Change",
            "Net Revenue",
            "$8.9 10%",
            "GAAP Net Income",
            "$4.9 17%",
            "“Visa delivered strong results in the third quarter, with net revenue growth of 10%, GAAP EPS growth of 20% and non-GAAP EPS growth of 12%. Our key business drivers were relatively stable.”",
            "GAAP Earnings Per Share",
            "$2.40 20%",
        ]
    )
    assert out is not None
    assert "% change is calculated" not in out
    assert "commented on the results" not in out
    # The freed budget serves the quote the attribution pointed at.
    assert "Visa delivered strong results in the third quarter" in out
    # The headline, dateline and all four bullets stay.
    assert "Visa Reports Fiscal Third Quarter 2024 Results" in out
    assert "San Francisco, CA, July 23, 2024" in out
    assert "GAAP net income of $4.9B or $2.40 per share" in out
    assert "Net revenue of $8.9B, an increase of 10%" in out
    assert "Growth in payments volume" in out
    assert "Share repurchases and dividends of $5.8B" in out


def test_bare_attribution_still_serves_quote_intro():
    # Longer synthetic: the extractor needs >=800 chars of text.
    out = _extract(
        [
            "Visa Reports Fiscal Third Quarter 2024 Results",
            "San Francisco, CA, July 23, 2024 – Visa (NYSE: V)",
            "•GAAP net income of $4.9B or $2.40 per share and non-GAAP net income of $4.9B or $2.42 per share",
            "•Net revenue of $8.9B, an increase of 10% on a nominal and constant-dollar basis",
            "•Growth in payments volume, cross-border volume and processed transactions remained relatively stable",
            "•Share repurchases and dividends of $5.8B",
            V_ATTRIBUTION,
            "“Visa delivered strong results in the third quarter, with net revenue growth of 10%, GAAP EPS growth of 20% and non-GAAP EPS growth of 12%. Our key business drivers were relatively stable, with payments volume up 7%, cross-border volume up 14% and processed transactions up 10%. During the quarter, we expanded our partnerships with many clients around the world.”",
        ]
    )
    assert out is not None
    assert "commented on the results" in out
    assert "Visa delivered strong results in the third quarter" in out
