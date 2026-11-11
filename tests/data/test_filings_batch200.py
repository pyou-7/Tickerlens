"""Batch 200: guidance section-end misses — colon-ended headings and
results-table period-header followers.

Two defects, one defect class (the section runs past its end):

1. A trailing colon counted as sentence termination in
   _is_guidance_next_section_heading, so a colon-ended heading label
   never read as a next-section heading: Cisco's "Editor's Notes:"
   (followed by conference-call logistics bullets), Disney's "Message
   From Our CEO:" (followed by the CEO quote), and GE's "Caution
   Concerning Forward Looking Statements:" (followed by safe-harbor
   risk prose) were all collected as guidance. A colon introduces the
   content that follows it; a colon-ended line is now a heading
   candidate, still gated on title case and the follower test. The
   follower test also accepts a quote-led line (the opening quote is
   not a cased character) and, for a colon-ended label, a quotation
   outright — the quote's first flattened line is a wrapped fragment,
   so the terminated-prose test never fires on Disney's Q2/Q3 FY2025
   CEO quotes.
2. A results-table period header ("Three months ended September 30")
   never counted as a section-end follower, so GE Vernova's outlook
   section ran past "Total Company Results" into its condensed
   results table. A period header after a heading now ends the
   section.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_guidance_next_section_heading,
    _is_guidance_section_end_follower,
    extract_management_guidance,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _guidance(name: str) -> str:
    g = extract_management_guidance(_load(name))
    assert g is not None
    return g


# --- Fix 1: colon-ended headings are heading candidates ---------------

CALL_BULLET = (
    "• Q4 fiscal year 2026 conference call to discuss Cisco's results along "
    "with its guidance will be held on Wednesday, August 12, 2026 at 1:30 p.m. "
    "Pacific Time."
)
CEO_QUOTE = (
    "“This was another year of great progress as we strengthened the company "
    "by leveraging the value of our creative and brand assets and continued "
    "to make meaningful progress in our direct-to-consumer businesses,” said "
    "Robert A. Iger, Chief Executive Officer, The Walt Disney Company."
)
SAFE_HARBOR = (
    "This release and certain of our public communications and filings we make "
    "with the U.S. Securities and Exchange Commission (SEC) may contain "
    "statements related to our expected financial performance."
)


def test_editors_notes_is_a_section_heading():
    lines = ["Editor's Notes:", CALL_BULLET]
    assert _is_guidance_next_section_heading(lines, 0)


def test_ceo_message_is_a_section_heading():
    lines = ["Message From Our CEO:", CEO_QUOTE]
    assert _is_guidance_next_section_heading(lines, 0)


def test_ceo_message_wrapped_quote_is_a_section_heading():
    # The quote's first flattened line is a wrapped fragment (no
    # terminal punctuation), so the terminated-prose follower test
    # never fires — the colon + opening-quote shape decides it.
    lines = [
        "Message From Our CEO:",
        "“Our performance in Q3 demonstrates the progress we’ve made against our four strategic priorities across our creative studios, streaming, sports, and",
    ]
    assert _is_guidance_next_section_heading(lines, 0)


def test_non_colon_heading_wrapped_quote_is_now_a_section_heading():
    # Batch 201 SUPERSEDES this pin: a wrapped quote follower after a
    # non-colon heading now ends the section (Carnival's "Financing
    # and Capital Activity" + CFO quote). The old expectation —
    # "a wrapped quote follower alone never ends the section" — held
    # only while the quote rule required a colon-ended heading.
    lines = [
        "Message From Our CEO",
        "“Our performance in Q3 demonstrates the progress we’ve made against our four strategic priorities across our creative studios, streaming, sports, and",
    ]
    assert _is_guidance_next_section_heading(lines, 0)


def test_caution_forward_looking_is_a_section_heading():
    lines = ["Caution Concerning Forward Looking Statements:", SAFE_HARBOR]
    assert _is_guidance_next_section_heading(lines, 0)


def test_guidance_word_colon_heading_still_exempt():
    # A guidance sub-heading that happens to end in a colon is still
    # guidance, not a section end.
    lines = ["Q1 FY 2026 Guidance (1):", "• Revenue: $14.65 billion to $14.85 billion"]
    assert not _is_guidance_next_section_heading(lines, 0)


def test_segment_guidance_colon_heading_still_exempt():
    lines = ["Segment guidance is:", "• Power: 19%-21% organic revenue* growth."]
    assert not _is_guidance_next_section_heading(lines, 0)


def test_sentence_fragment_colon_heading_still_exempt():
    # Not title-case: a prose fragment that ends in a colon.
    lines = [
        "We expect the following:",
        "Revenue of $14.65 billion to $14.85 billion for the first quarter.",
    ]
    assert not _is_guidance_next_section_heading(lines, 0)


def test_period_ended_sentence_still_not_a_heading():
    lines = [
        "Cisco announced today that it has signed a definitive agreement to acquire a manufacturing facility in Ohio.",
        "The transaction is expected to close in the fourth quarter.",
    ]
    assert not _is_guidance_next_section_heading(lines, 0)


def test_colon_table_label_with_figure_follower_still_not_a_heading():
    # A table-row label ending in a colon, followed by its figure line,
    # is table furniture, not a section end.
    lines = ["Revenue:", "$14.65 billion to $14.85 billion"]
    assert not _is_guidance_next_section_heading(lines, 0)


# --- Fix 2: results-table period headers end the section --------------


def test_period_header_is_a_follower():
    lines = ["Total Company Results", "Three months ended September 30"]
    assert _is_guidance_section_end_follower(lines, 0)


def test_doubled_period_header_is_a_follower():
    lines = [
        "Total Company Results",
        "Three months ended September 30 Nine months ended September 30",
    ]
    assert _is_guidance_section_end_follower(lines, 0)


def test_figure_line_is_not_a_period_header_follower():
    lines = ["Total Company Results", "Total revenues", "$12,642"]
    assert not _is_guidance_section_end_follower(lines, 0)


def test_total_company_results_is_a_section_heading():
    lines = ["Total Company Results", "Three months ended September 30"]
    assert _is_guidance_next_section_heading(lines, 0)


# --- Real-exhibit pins -------------------------------------------------


def test_csco_editors_notes_tail_cut():
    g = _guidance("CSCO_2026-07-25.html")
    assert "Editor's Notes:" not in g
    assert "conference call to discuss" not in g
    # Batch 233: the fused revenue row normalizes to "Label: values".
    assert "Revenue: $72.2 billion" in g


def test_dis_ceo_message_tail_cut():
    g = _guidance("DIS_2025-09-27.html")
    assert "Message From Our CEO:" not in g
    assert "This was another year of great progress" not in g
    assert "Double digit adjusted EPS" in g


def test_dis_ceo_message_wrapped_quote_tail_cut():
    # Q3 FY2025: the CEO quote's first line is a wrapped fragment, so
    # only the colon + opening-quote follower rule cuts it.
    g = _guidance("DIS_2024-06-29.html")
    assert "Message From Our CEO:" not in g
    assert "Our performance in Q3 demonstrates" not in g
    assert "Double digit" in g or "adjusted EPS" in g


def test_ge_safe_harbor_tail_cut():
    g = _guidance("GE_2026-09-30.html")
    assert "Caution Concerning Forward Looking Statements:" not in g
    assert "particular areas where risks" not in g
    assert "2026 GUIDANCE" in g


def test_gev_results_table_tail_cut():
    g = _guidance("GEV_2026-09-30.html")
    assert "Total Company Results" not in g
    assert "Total revenues" not in g
    assert "Segment guidance is:" in g
    assert "Power: 19%-21% organic revenue" in g
