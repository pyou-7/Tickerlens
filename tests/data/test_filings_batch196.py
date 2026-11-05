"""Batch 196: bare-word guidance headings with a footnote digit, and the
stale stored-guidance repair.

The batch-193 anchor rejected a bare guidance word with an attached
footnote digit ("OUTLOOK2" — Cigna's outlook heading, OUTLOOK<sup>2</sup>
in the HTML), so CI's 2024-12-31, 2025-03-31 and 2025-09-30 quarters
extracted None while every other CI quarter served guidance. A census
of the 1,699-exhibit cache finds exactly six bare-word+digit guidance
headings; the only ones that can become the anchor are CI's three
(OUTLOOK2 is the section heading, followed by outlook prose + metrics
table). CRM's Guidance5 column headers and EMR's "Guidance 2026" both
sit after an earlier real heading, so they never anchor.

The repair (scripts/batch196_repair.py) replaces stored guidance rows
the batch-193 extractor left serving pre-193 over-collected text
(results narrative, segment prose, call notices, footnote legends —
up to ~3,800 chars of next-section content after 2 guidance bullets),
under a structural tail-drop gate: a dropped stored paragraph must
sit at/after the first next-section heading in the stored text, or
match a known junk shape; a dropped paragraph matching a guidance
heading blocks the repair (a second guidance section — merge work,
not a tail drop). FSLR's "Volume Sold 18GW to 20GW" row is the
gate-correct skip that proves the gate: a genuine guidance table row
the collector drops (its unit metric carries no $/%), so the row is
not repaired.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_guidance_heading,
    extract_management_guidance,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _live(ticker_period: str) -> str:
    html = open(
        os.path.join(CACHE, f"{ticker_period}.html"), encoding="utf-8"
    ).read()
    out = extract_management_guidance(html)
    assert out is not None, f"{ticker_period} extracted None"
    return out


# --- unit: bare-word + footnote digit is a heading ------------------------


def test_outlook2_is_a_heading():
    assert _is_guidance_heading("OUTLOOK2")


def test_guidance5_is_a_heading_when_it_is_the_only_anchor():
    # Batch 193 treated a bare word + digit as a table cell. The census
    # (see module docstring) shows a bare-word+digit line can only anchor
    # when no earlier guidance heading exists — i.e. when it IS the
    # section heading — so the anchor test accepts it.
    assert _is_guidance_heading("Guidance5")


def test_compound_heading_with_digit_still_a_heading():
    assert _is_guidance_heading("Financial Guidance1")
    assert _is_guidance_heading("2025 OUTLOOK2")


# --- live: CI's three dead quarters serve guidance again -------------------


def test_ci_2024_q4_outlook2_served():
    out = _live("CI_2024-12-31")
    assert out.startswith("OUTLOOK2")
    assert "at least $29.50 per share" in out
    assert "Consolidated Results" not in out


def test_ci_2025_q1_outlook2_served():
    out = _live("CI_2025-03-31")
    assert out.startswith("OUTLOOK2")
    assert "is $29.60 per share" in out


def test_ci_2025_q3_outlook2_served():
    out = _live("CI_2025-09-30")
    assert out.startswith("OUTLOOK2")
    assert "at least $29.60 per share" in out
    assert "at least $7,200" in out  # Evernorth adjusted income table row
    # Known wart (carried forward, not a batch-196 regression): the
    # stored text also carries the call notice, and the live text
    # carries its dial-in tail — the notice is embedded mid-paragraph
    # after a long URL, past the 120-char guard batch 193 added for
    # Biogen's FX line, so the call-notice break never fires here.


# --- live: the table-header cases do not move ------------------------------


def test_crm_guidance5_column_header_does_not_reanchor():
    # CRM_2024-10-31's Guidance5 lines are table column headers inside
    # the guidance section; the extractor still anchors on the earlier
    # "Guidance" heading and the extraction is unchanged.
    out = _live("CRM_2024-10-31")
    assert out.startswith("Guidance")
    assert "$9.90 - $10.10 Billion" in out


def test_emr_guidance_2026_does_not_reanchor():
    out = _live("EMR_2025-09-30")
    assert out.startswith("2026 Outlook")
    assert "~$2.2B" in out


# --- live: the repaired rows serve tight guidance, not results prose -------


def test_apd_guidance_is_just_the_two_bullets():
    out = _live("APD_2025-09-30")
    assert "Fiscal 2026 full-year adjusted EPS guidance* of $12.85 to $13.15" in out
    assert "Expect fiscal year 2026 capital expenditures* of approximately $4 billion" in out
    assert "Consolidated Results" not in out
    assert "LEHIGH VALLEY" not in out
    assert len(out) < 400
