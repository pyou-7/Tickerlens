"""Batch 211: the Highlights collector's _CONFERENCE_CALL_NOTICE_RE
tail-match hazard — a content-aware discriminator for the call notice.

Batch-193 carry-forward (also batch 194/195/196/197/198/199/200/201/
202/203/204/205/206/207/208/209/210): the bare regex fires on any line
that mentions "conference call" before "webcast" / "replay", so a
genuine content sentence whose tail only points AT the call is treated
as a notice — dropped from the lede, or ending the Highlights section.
Biogen's FX-assumption line (12 quarters in-cache: "Other modeling
considerations will be provided on the conference call and webcast.")
is the attested shape; the guidance collector already keeps it via its
batch-193 120-char line guard, but the Highlights paths used the bare
regex with no guard at all.

Fix (extract_press_release_highlights, via _is_call_notice): the
regex must match AND the match must not be a call pointer — content
"provided / discussed on the conference call". The pointer preposition
("on the / its / our conference call") is the discriminator: a notice
ANNOUNCES the call ("will host / hold / discuss ... during ... a
conference call", "a webcast of the ... conference call to be held",
"Text of the conference call's prepared remarks ...") — it never says
content will be provided ON it.

The alternatives were tested against all 1,699 cached exhibits and
rejected: a 120-char sentence-start guard cannot separate Biogen
(match 63 chars into its short pointer sentence) from CSCO's notice
sentence (18 chars in), and a scheduling-verb test cannot separate
Biogen from the CSCO/FDX notices (no host verb in either). The pointer
shape occurs in exactly the 12 Biogen lines and nowhere else.

Blast (blast211/h_new vs h_old, 1,699 exhibits): 0 diffs — the hazard
is latent for highlights output (Biogen's pointer lines sit in the
guidance section, never in a Highlights window) and no attested notice
is lost. No stored rows to repair.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _html_to_text,
    _is_call_notice,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _find_line(html: str, needle: str) -> str:
    for ln in _html_to_text(html).splitlines():
        if needle in ln:
            return ln
    raise AssertionError(f"line containing {needle!r} not found")


def _extract(body_lines):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


# --- unit: the pointer exemption --------------------------------------------

BIIB_FX_2024 = (
    "This guidance also assumes that foreign exchange rates as of "
    "February 9, 2024, will remain in effect for the remainder of the "
    "year, net of hedging activities. Other modeling considerations "
    "will be provided on the conference call and webcast."
)
BIIB_FX_2025 = (
    "Unless expressly stated above, this financial guidance does not "
    "include any impact from potential acquisitions or business "
    "development transactions or pending and future litigation or any "
    "impact of potential healthcare reform, as all are hard to predict. "
    "Some other financial considerations will be provided on the "
    "conference call and webcast."
)
DHI_POINTER = (
    "The Company plans to also provide guidance for the second quarter "
    "on its conference call today and the webcast will be available."
)


def test_pointer_sentences_are_not_notices():
    assert not _is_call_notice(BIIB_FX_2024)
    assert not _is_call_notice(BIIB_FX_2025)
    assert not _is_call_notice(DHI_POINTER)


def test_notice_sentences_stay_notices():
    # Danaher: long lead-in, match 132+ chars in — the sentence-start
    # guard alone would miss it; the pointer test keeps it a notice.
    assert _is_call_notice(
        "Danaher will discuss its fourth quarter results and financial "
        "guidance for the first quarter and full year 2024 during its "
        "quarterly investor conference call today starting at 8:00 a.m. "
        "ET. The call and an accompanying slide presentation will be "
        "webcast on the \u201cInvestors\u201d section of Danaher\u2019s website."
    )
    # Disney: "will host a conference call ... via a live Webcast".
    assert _is_call_notice(
        "In conjunction with this release, The Walt Disney Company will "
        "post prepared management remarks (Executive Commentary) at "
        "www.disney.com/investors and will host a conference call today, "
        "November 14, 2024, at 8:30 AM EST/5:30 AM PST via a live "
        "Webcast. To access the Webcast go to www.disney.com/investors."
    )
    # BlackRock: "will host a teleconference call" with a long subject.
    assert _is_call_notice(
        "Chairman and Chief Executive Officer, Laurence D. Fink, "
        "President, Robert S. Kapito, and Chief Financial Officer, "
        "Martin S. Small, will host a teleconference call for investors "
        "and analysts on Friday, October 11, 2024 at 7:30 a.m. (Eastern "
        "Time). Members of the public who are interested in "
        "participating in the teleconference should dial (786) 460-7166. "
        "The webcast will be available."
    )
    # Domino's: notice shares the line with the 10-Q filing sentence.
    assert _is_call_notice(
        "The Company will file its Quarterly Report on Form 10-Q today. "
        "As previously announced, Domino\u2019s Pizza, Inc. will hold a "
        "conference call today at 8:30 a.m. (Eastern) to review its "
        "first quarter 2024 financial results. The webcast is available "
        "at ir.dominos.com and will be archived for one year."
    )
    # Gallagher: dateline + results sentence + notice on one line.
    assert _is_call_notice(
        "ROLLING MEADOWS, IL, April 30, 2026 \u2014 Arthur J. Gallagher "
        "& Co. (NYSE: AJG) today reported its financial results for the "
        "quarter ended March 31, 2026. Management will host a webcast "
        "conference call to discuss these results on Thursday, April 30, "
        "2026 at 5:15 p.m. ET/4:15 p.m. CT. To listen to the call, visit "
        "our website."
    )
    # Cisco: prepared-remarks text — no host verb, notice by content.
    assert _is_call_notice(
        "Visuals designed to guide participants through the call, will "
        "be available at 1:30 p.m. Pacific Time, May 15, 2024. Text of "
        "the conference call\u2019s prepared remarks will be available "
        "within 24 hours of completion of the call. The webcast will be "
        "posted on our website."
    )
    # Emerson (batch 166): "will discuss ... during an investor
    # conference call" + webcast/replay.
    assert _is_call_notice(
        "Today, beginning at 7:30 a.m. Central Time / 8:30 a.m. Eastern "
        "Time, Emerson management will discuss the fourth quarter and "
        "fiscal year 2025 results during an investor conference call. "
        "Participants can access a live webcast available at "
        "https://ir.emerson.com at the time of the call. A replay of the "
        "call will be available for 90 days."
    )
    # Equinix: "will discuss ... in its quarterly conference call" +
    # simultaneous live webcast.
    assert _is_call_notice(
        "Equinix will discuss its quarterly results for the period ended "
        "September 30, 2025, along with its future outlook, in its "
        "quarterly conference call on Wednesday, October 29, 2025, at "
        "5:30 p.m. ET (2:30 p.m. PT). A simultaneous live webcast of the "
        "call will be available on the company\u2019s Investor Relations "
        "website."
    )
    # FedEx: "a webcast of the earnings release conference call to be
    # held" — logistics, no host verb.
    assert _is_call_notice(
        "Additional information and operating data are contained in the "
        "company\u2019s annual report, Form 10-K, Form 10-Qs, Form 8-Ks "
        "and Statistical Books. These materials, as well as a webcast of "
        "the earnings release conference call to be held at 5:30 p.m. "
        "EDT on September 18, are available on the company\u2019s website "
        "at investors.fedex.com. A replay of the conference call webcast "
        "will be posted on our website following the call."
    )
    # Instacart / Ford / Affirm / Corteva / Coinbase: call-details
    # blocks inside flattened single-line paragraphs.
    assert _is_call_notice(
        "Live Conference Call Instacart management will host a "
        "conference call to discuss the company's results at 5:00 a.m. "
        "Pacific Time (8:00 a.m. Eastern Time) on Monday, November 10. "
        "To access a live webcast of the conference call, please visit "
        "our Investor Relations website."
    )
    assert _is_call_notice(
        "Conference Call Details At 5:00 p.m. ET today, Ford and Ford "
        "Credit management will hold a conference call to discuss these "
        "financial results. For the webcast, click here. It will be "
        "available for replay for approximately one week."
    )
    assert _is_call_notice(
        "Conference Call Affirm will host a conference call and webcast "
        "to discuss first fiscal quarter 2026 financial results on "
        "November 6, 2025, at 2:00 pm PT. The conference call will be "
        "webcast live from the Company\u2019s investor relations website."
    )
    assert _is_call_notice(
        "Second Quarter Conference Call The Company will host a live "
        "webcast of its second quarter 2025 earnings conference call "
        "with investors to discuss its results and outlook tomorrow, "
        "August 7, 2025, at 9:00 a.m. ET. A replay of the webcast will "
        "also be available."
    )
    assert _is_call_notice(
        "Webcast Information We will host a conference call to discuss "
        "the results for the first quarter of 2026 on May 7, 2026 at "
        "2:30 pm PT. A replay of the webcast will be available."
    )


def test_non_notice_lines():
    # Bare "conference call" mention in real prose, no webcast/replay.
    assert not _is_call_notice(
        "On the conference call, management said the quarter tracked "
        "ahead of plan and raised the outlook."
    )
    # AppLovin heading: plural "Conference Calls", no notice.
    assert not _is_call_notice("Webcast and Conference Calls")
    # A webcast mention without the call is not a notice either.
    assert not _is_call_notice(
        "A replay of the webcast will be available for 90 days."
    )


# --- real exhibits: the attested shapes --------------------------------------

def test_real_biib_pointer_lines_are_not_notices():
    for period in ("2023-12-31", "2025-09-30", "2026-09-30"):
        ln = _find_line(
            _load(f"BIIB_{period}.html"),
            "will be provided on the conference call",
        )
        assert not _is_call_notice(ln), period


def test_real_notice_lines_stay_notices():
    cases = [
        ("DHR_2025-09-26.html", "will discuss its third quarter results"),
        ("DIS_2025-09-27.html", "will host a conference call today"),
        ("BLK_2025-09-30.html", "will host a teleconference call"),
        ("EMR_2025-09-30.html", "will discuss the fourth quarter"),
        ("EQIX_2025-09-30.html", "will discuss its quarterly results"),
        ("FDX_2025-08-31.html", "webcast of the earnings release conference call"),
        ("CSCO_2025-07-26.html", "conference call\u2019s prepared remarks"),
        ("DPZ_2025-09-07.html", "will hold a conference call today"),
        ("CART_2025-09-30.html", "will host a conference call to discuss"),
        ("F_2025-09-30.html", "will hold a conference call to discuss"),
    ]
    for name, needle in cases:
        ln = _find_line(_load(name), needle)
        assert _is_call_notice(ln), name


# --- end to end: the lede keeps a pointer, skips a notice --------------------

def test_lede_keeps_pointer_sentence_skips_notice():
    out = _extract(
        [
            "Acme Corp. Reports Third Quarter 2025 Results",
            "AUSTIN, Texas \u2013 November 5, 2025 \u2013 Acme Corp. (NASDAQ: ACME) "
            "today announced third quarter operating income of $1.09 billion "
            "and net earnings of $694 million, or $0.37 per share.",
            "In the quarter, adjusted operating income and adjusted earnings "
            "per share included $35 million and $0.01, respectively, in "
            "corporate restructuring, severance, and advisory expenses.",
            "Other modeling considerations will be provided on the "
            "conference call and webcast.",
            "Management will host a conference call today at 8:30 a.m. "
            "ET. A replay of the webcast will be available for 90 days.",
            "Volume totaled 1.61 million units for the quarter, up 1% "
            "compared to third quarter 2024 and up 2% sequentially. "
            "Revenue totaled $3.59 billion for the quarter, decreasing 1% "
            "year-over-year.",
        ]
    )
    assert out is not None
    assert "Other modeling considerations will be provided" in out
    assert "Management will host a conference call" not in out
    assert "Volume totaled 1.61 million units" in out
