"""Batch 208: results-led Guidance/Outlook headings end the guidance section.

Batch 207 carry-forward: GE 2025-09-30's stale stored guidance row —
a 17-line truncation of the guidance table — with a segment-guidance
bleed tail in live: the extraction runs past the table into the next
section, "Results & Guidance by Reporting Segment", and serves its
intro line too.

Fix (_is_guidance_next_section_heading, via _GUIDANCE_RESULTS_LED_RE):
a heading that LEADS with a results noun ("Results"/"Revenue") and
mentions Guidance/Outlook after "&"/"and" is the segment-results
section, not a guidance section — the same exemption the batch-202
_GUIDANCE_NARRATIVE_OUTLOOK_RE gives "Revenue Environment and
Outlook". The connector is the discriminator: "Results, Reaffirms
2025 Adjusted EPS Outlook" (comma + verb) and "Results and Provides
Fiscal 2026 Outlook" (verb after "and") never match, and prose with a
guidance mention fails on the lead word or the connector. The
title-case + section-end-follower + has-signal gates still apply, so
a stray match still needs a real new section after real guidance.

Blast (blast208/g_new vs g_old, 1,699 exhibits): 4 diffs, 0
None-flips — all GE, each a pure tail cut of the segment-results
heading + intro line. Repair: GE 2025-09-30's stored row (17 lines)
is completed to the live extraction (55 lines); the other three GE
quarters have no stored rows and serve on refresh.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _GUIDANCE_RESULTS_LED_RE,
    _is_guidance_next_section_heading,
    extract_management_guidance,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


_FOLLOWER = (
    "The following discussions and variance explanations are intended to "
    "reflect management\u2019s view of the relevant comparisons of financial results."
)


def _is_next(heading: str) -> bool:
    return _is_guidance_next_section_heading(["x", heading, _FOLLOWER], 1)


# The three attested GE shapes (full-cache survey: 5 occurrences).
def test_results_ampersand_guidance_is_next_section():
    assert _is_next("Results & Guidance by Reporting Segment") is True


def test_results_and_guidance_is_next_section():
    assert _is_next("Results and Guidance by Reporting Segment") is True


def test_results_and_outlook_is_next_section():
    assert _is_next("Results and Outlook by Reporting Segment") is True


def test_results_led_regex_matches_attested_shapes():
    assert _GUIDANCE_RESULTS_LED_RE.match("Results & Guidance by Reporting Segment")
    assert _GUIDANCE_RESULTS_LED_RE.match("Results and Guidance by Reporting Segment")
    assert _GUIDANCE_RESULTS_LED_RE.match("Results and Outlook by Reporting Segment")
    assert _GUIDANCE_RESULTS_LED_RE.match("Revenue & Guidance by Segment")


def test_results_led_regex_rejects_headlines_and_prose():
    # Headline shapes: comma + verb, verb after "and".
    assert not _GUIDANCE_RESULTS_LED_RE.match(
        "Results, Reaffirms 2025 Adjusted EPS Outlook"
    )
    assert not _GUIDANCE_RESULTS_LED_RE.match(
        "Results and Provides Fiscal 2026 Outlook"
    )
    # Prose: wrong lead word after the results noun, or no connector.
    assert not _GUIDANCE_RESULTS_LED_RE.match(
        "Revenue of $43.1 billion to $43.7 billion, which compares to prior guidance"
    )
    assert not _GUIDANCE_RESULTS_LED_RE.match(
        "Results in top half of guidance range for 8th consecutive year"
    )
    # A genuine guidance heading leads with Guidance/Outlook, not Results.
    assert not _GUIDANCE_RESULTS_LED_RE.match("Guidance and Outlook")


# Guard pins: genuine guidance headings are still NOT next-section
# headings (no-change behavior — these pass on old code too).
def test_genuine_guidance_headings_are_not_next_section():
    assert _is_next("Guidance and Outlook") is False
    assert _is_next("2025 Outlook") is False
    assert _is_next("Financial Outlook") is False


def test_headline_shapes_are_not_next_section():
    assert _is_next("Results, Reaffirms 2025 Adjusted EPS Outlook") is False
    assert _is_next("Results and Provides Fiscal 2026 Outlook") is False
    assert (
        _is_next("Results in top half of guidance range for 8th consecutive year")
        is False
    )


def test_batch202_narrative_outlook_unchanged():
    # The DAL shape the batch-202 regex already exempts still breaks.
    assert _is_next("Revenue Environment and Outlook") is True


# Real-exhibit pin: GE 2025-09-30 serves the full guidance table and
# stops at the segment-results heading (fails on old code: the bleed
# tail "Results & Guidance by Reporting Segment" + intro is present).
def test_ge_2025_09_30_guidance_stops_at_segment_results():
    text = extract_management_guidance(_load("GE_2025-09-30.html"))
    assert text is not None
    assert "Results & Guidance by Reporting Segment" not in text
    assert "The following discussions and variance explanations" not in text
    assert "Segment guidance included below." in text
    assert "Adjusted EPS* $4.60 $5.60 - $5.80 $6.00 - $6.20" in text
    assert text.rstrip().endswith("(a \u2013 FCF* conversion: FCF* / adjusted net income*")
    assert len(text.split("\n")) == 55
