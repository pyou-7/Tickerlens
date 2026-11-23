"""Batch 209: conference-call host notice + call-in-numbers break ends
the guidance section; shared-line walk-back drops the dangling
availability fragment.

Batch 208 carry-forward: CI 2025-03-31's stored guidance row carries
the conference-call notice block ("Management will be hosting a
conference call ...", "The call-in numbers for the conference call
are as follows:", "Live Call", "Passcode: 05022025", "Replay", "It is
strongly suggested you dial in ..."). None of the batch-193 tests
catches it: the notice lines carry no "webcast"/"replay", so
_CONFERENCE_CALL_NOTICE_RE never fires.

Fix (extract_management_guidance break condition, via
_CALL_HOST_NOTICE_RE + _CALL_IN_NUMBERS_RE): "will host(ing) a
conference call" is the discriminator — a guidance sentence points
AT the call ("The Company plans to also provide guidance ... on its
conference call today" — DHI x11, kept; "... will be provided on the
conference call and webcast" — Biogen's FX line, kept) — it never
says the company will host one. "will host its calls" (GE
2023-12-31's earnings-call schedule line) never matches: no "a
conference call". The guard is sentence-aware
(_notice_starts_sentence): CI 2024-09-30's notice shares its line
with the preceding availability sentence, so the match starts ~180
chars into the line but 11 chars into its own sentence.

Walk-back: the notice sentence may share its line with the tail of
the preceding sentence, so breaking at the line leaves the kept text
ending mid-sentence ("This quarterly earnings", "... Investor
Relations section"). When the notice sentence does not start the
break line and the text before it ends with sentence punctuation,
unterminated kept lines are popped so the text ends at the last
complete sentence (the heading is never popped).

Blast (blast209/g_new vs blast208/g_new, 1,699 exhibits): 11 diffs, 0
None-flips — 8 pure tail cuts (CI x6 + COP x2, all with stored rows)
and 3 completions (CI 2023-12-31, 2024-03-31, 2024-06-30: the
batch-204 lookahead keeps the freed budget lines once the notice
break fires inside its window, so the table completes and the
disclaimer is served — pre-seeding quarters with no stored rows;
they serve on refresh). Repair: 8 stored rows (CI x6, COP x2).
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _CALL_HOST_NOTICE_RE,
    _CALL_IN_NUMBERS_RE,
    _notice_sentence_start,
    _notice_starts_sentence,
    extract_management_guidance,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


# The two attested host-notice verb forms.
def test_host_notice_regex_matches_attested_shapes():
    assert _CALL_HOST_NOTICE_RE.search(
        "Management will be hosting a conference call to review third "
        "quarter 2024 results and discuss full year 2024 outlook "
        "beginning today at 8:30 a.m. ET."
    )
    assert _CALL_HOST_NOTICE_RE.search(
        "ConocoPhillips will host a conference call today at noon "
        "Eastern time to discuss this announcement."
    )


def test_host_notice_regex_rejects_pointers_and_schedule():
    # DHI's guidance pointer: the call is where guidance will be
    # provided, not something the company will host.
    assert not _CALL_HOST_NOTICE_RE.search(
        "The Company plans to also provide guidance for its third "
        "quarter of fiscal 2024 on its conference call today."
    )
    # Biogen's FX line: a guidance sentence with a call pointer in
    # its tail.
    assert not _CALL_HOST_NOTICE_RE.search(
        "The full year 2025 outlook will be provided on the conference "
        "call and webcast."
    )
    # GE's earnings-call schedule line: "will host its calls", no
    # "a conference call".
    assert not _CALL_HOST_NOTICE_RE.search(
        "GE Aerospace will host its calls on April 23, July 23, and "
        "October 22."
    )
    # A bare "conference call" mention without the host verb.
    assert not _CALL_HOST_NOTICE_RE.search(
        "A replay of the conference call will be available for 90 days."
    )


def test_call_in_numbers_regex_matches_attested_shape():
    assert _CALL_IN_NUMBERS_RE.search(
        "The call-in numbers for the conference call are as follows:"
    )


def test_call_in_numbers_regex_rejects_plain_mentions():
    assert not _CALL_IN_NUMBERS_RE.search(
        "Call-in details are available on the investor relations website."
    )
    assert not _CALL_IN_NUMBERS_RE.search(
        "The conference call will begin at 8:30 a.m. ET."
    )


# Sentence-start guard: the match's own sentence, not the line.
def test_notice_sentence_start_is_line_start_for_line_initial_match():
    line = "Management will be hosting a conference call to review results."
    m = _CALL_HOST_NOTICE_RE.search(line)
    assert m is not None
    assert _notice_sentence_start(line, m) == 0
    assert _notice_starts_sentence(line, m) is True


def test_notice_sentence_start_skips_preceding_sentence():
    # CI 2024-09-30: the notice shares its line with the availability
    # sentence, so the match starts ~180 chars into the line but 11
    # chars into its own sentence.
    line = (
        "This quarterly earnings release and the Quarterly Financial "
        "Supplement are available on The Cigna Group's website in the "
        "Investor Relations section "
        "(https://investors.thecignagroup.com/overview/default.aspx). "
        "Management will be hosting a conference call to review third"
    )
    m = _CALL_HOST_NOTICE_RE.search(line)
    assert m is not None
    assert m.start() > 120  # the batch-193 line guard would block it
    assert _notice_sentence_start(line, m) == line.index("Management")
    assert _notice_starts_sentence(line, m) is True


def test_notice_sentence_guard_rejects_late_sentence_match():
    # A host clause buried 120+ chars into its own sentence never
    # breaks (same 120-char number as the batch-193 line guard).
    prefix = (
        "The outlook for the year, which management expects to discuss "
        "at length in the detailed guidance section below and in the "
    )
    assert len(prefix) > 120
    line = prefix + "will host a conference call to discuss the outlook."
    m = _CALL_HOST_NOTICE_RE.search(line)
    assert m is not None
    assert _notice_starts_sentence(line, m) is False


# Real-exhibit pins (fail on old code: the notice block is present).
def test_ci_2025_03_31_guidance_stops_at_call_notice():
    text = extract_management_guidance(_load("CI_2025-03-31.html"))
    assert text is not None
    assert "hosting a conference call" not in text
    assert "call-in numbers" not in text
    assert "Passcode:" not in text
    assert "dial in to the conference call" not in text
    assert "at least $29.60" in text
    assert text.rstrip().endswith(
        "Investors are urged to read the Cautionary Note Regarding "
        "Forward-Looking Statements included in this release. Management "
        "does not assume any obligation to update these estimates."
    )
    assert len(text) == 1152
    assert len(text.split("\n")) == 39


def test_ci_2025_09_30_walk_back_drops_availability_fragment():
    # The availability sentence wraps onto the notice line, so without
    # the walk-back the text would end with the dangling fragment
    # "This quarterly earnings".
    text = extract_management_guidance(_load("CI_2025-09-30.html"))
    assert text is not None
    assert "This quarterly earnings" not in text
    assert "hosting a conference call" not in text
    assert "call-in numbers" not in text
    assert "Passcode:" not in text
    # The disclaimer sentence wraps ("Investors are urged" / "to read
    # ..."), so pin the tail clause, not the full sentence.
    assert text.rstrip().endswith(
        "Management does not assume any obligation to update these estimates."
    )
    assert len(text) == 1117


def test_cop_2024_12_31_guidance_stops_at_host_notice():
    text = extract_management_guidance(_load("COP_2024-12-31.html"))
    assert text is not None
    assert "will host a conference call" not in text
    assert "Guidance excludes special items." in text
    assert text.rstrip().endswith(
        "Guidance for 2025 includes capital expenditures of approximately "
        "$12.9 billion, adjusted operating costs of $10.9 to $11.1 "
        "billion, DD&A of $11.3 to $11.5 billion and adjusted corporate "
        "segment net loss of approximately $1.1 billion. Guidance "
        "excludes special items."
    )
    assert len(text) == 599
    assert len(text.split("\n")) == 5


# Guard pins: no-change behavior — these pass on old code too.
def test_dhi_guidance_pointer_kept():
    text = extract_management_guidance(_load("DHI_2024-03-31.html"))
    assert text is not None
    assert (
        "The Company plans to also provide guidance for its third "
        "quarter of fiscal 2024 on its conference call today." in text
    )
    assert len(text) == 654


def test_ge_call_schedule_line_kept():
    text = extract_management_guidance(_load("GE_2023-12-31.html"))
    assert text is not None
    assert "will host its calls on April 23, July 23, and October 22" in text
    assert len(text) == 1192
