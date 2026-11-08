"""Batch 212: guidance extraction — highlights-teaser anchor rejection,
wrapped-prose section ends, "- more -" page markers, Akamai intro
anchors, Dollar General "Financial Guidance" headings.

Two defects, one item (guidance correctness), attested across the cache:

1. Teaser anchor (batch-200 carry-forward "GPC teaser-anchor
   selection"): the anchor scan takes the FIRST guidance-heading
   candidate, but a highlights-area teaser can precede the real
   section — GPC 2024-12-31's bare "2025 Outlook" heading above 3
   teaser bullets (the real "2025 Outlook" table is ~30 lines on),
   AKAM 2023-09-30's highlights bullet "Guidance increased for
   full-year revenue ...", DG's headline fragment "Financial Guidance
   for Fiscal Year 2024", CSCO's wrapped-bullet fragment "guidance
   range". The fix (_is_guidance_teaser_anchor): a heading candidate
   is a teaser when the release dateline follows within 50 lines —
   the body has not started yet. The window is 50: farthest attested
   teaser CSCO 2025-07-26 at 40 lines, nearest true anchor with a
   (false) dateline after it FIS 2024-09-30 at 72 lines. The dateline
   test is _DATELINE_LEAD_RE plus the city-only shape ("ATLANTA -
   Genuine Parts Company ... announced today ..."), surveyed at 86
   lines in-cache, all genuine datelines.

2. Post-table bleed: after the outlook table the collector ran into
   the next sections up to the 4000-char cap — GPC's "Plan to
   Separate ...", "Non-GAAP Information" and "Comparable Sales"
   (3 quarters), FDX's "Corporate Overview" (+ contacts), SKYD's
   "Capital Structure & Capital Allocation" and "Our Proposal to
   Acquire Warner Bros. Discovery". The section-end follower test
   never fired because the followers are wrapped prose (long
   unterminated first lines, or mega-line paragraphs) or terminated
   sentences carrying sparse figures. The fix generalizes the
   batch-203 tagline branch to any wrapped-prose follower (the run
   now joins the follower itself, so a mega-line continuation's
   lowercase start no longer fails the uppercase test), lets a
   terminated follower carry sparse figures, and guards the new
   relaxation with a lead-value test (a table value row leads with
   its value — first $/% token at index < 4 — while prose buries
   figures later). The "- more -" / "-MORE-" page-marker variants
   are also skipped in the guidance paths (they were collected as
   content and one killed the follower run).

3. Anchor recognition (same item — AKAM/DG went to None once the
   teaser was skipped): Akamai's combined heading+intro line
   ("Financial guidance: The Company reports the following financial
   guidance for the fourth quarter and full-year 2023:", 114-116
   chars) now anchors via _GUIDANCE_INTRO_RE, "financial" joins the
   heading regex's intervening words ("Fiscal Year 2024 Financial
   Guidance"), and a heading wrapped across two lines ("Fiscal" /
   "Year 2024 Financial Guidance and Store Growth Outlook") anchors
   via the joined form in _guidance_anchor_text.

Blast (blast212/g_new3 vs g_old, 1,699 exhibits): 119 diffs, 0 lost
anchors, 55 rescues (None -> real guidance: AKAM/DG/APP/BIIB/CART/DD/
DRI/ENPH), 55 shorter (post-table bleed cut), 64 longer (rescues +
fuller tables/anchors). 45 stored rows repaired, DB-verified 45/45.
The first blast (g_new) had 122 diffs; the blast arbitrated three
false breaks that the guards then fixed — DAL's "Approx. 2.2x" ratio
value (now a value-token guard on the heading candidate), DUOL's
"Adjusted EBITDA" guidance-commentary sub-heading (now a
first-sentence guidance/call-notice guard on the follower), and BIIB's
highlights-area intro-statement anchor (now a colon+figure/signal
guard on the heading) — plus GE's "2026 GUIDANCE: 2026 OPERATING
PROFIT (NON-GAAP)" label-after-colon heading, which the first colon
guard wrongly rejected and the refined guard keeps.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _MORE_MARKER_RE,
    _guidance_anchor_text,
    _html_to_text,
    _is_guidance_heading,
    _is_guidance_next_section_heading,
    _is_guidance_section_end_follower,
    _is_guidance_teaser_anchor,
    extract_management_guidance,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _lines(html: str) -> list[str]:
    return [ln.strip() for ln in _html_to_text(html).split("\n") if ln.strip()]


def _extract(body_lines):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_management_guidance(f"<html><body>{body}</body></html>")


def _filler(n: int) -> list[str]:
    return [f"Ordinary release prose line number {k} about the quarter." for k in range(n)]


# --- teaser anchor: unit -----------------------------------------------

GPC_DATELINE = (
    "ATLANTA - Genuine Parts Company (NYSE: GPC), a leading global service "
    "provider of automotive and industrial replacement parts and value-added "
    "solutions, announced today its results for the fourth quarter ended "
    "December 31, 2024."
)


def test_teaser_anchor_gpc_shape():
    lines = [
        "2025 Outlook",
        "• Revenue Growth of 2% to 4%",
        "• Adjusted Diluted EPS of $7.75 to $8.25",
        "• Dividend Increase of 3%",
        GPC_DATELINE,
    ]
    assert _is_guidance_teaser_anchor(lines, 0) is True


def test_teaser_anchor_city_only_dateline_variants():
    # The city-only dateline shape: all-caps city + dash + the
    # announced-today / today-reported phrase. Surveyed at 86 lines
    # in-cache, all genuine datelines.
    for dateline in [
        "DUBLIN - February 2, 2024 - Aon plc (NYSE: AON) today reported results for the quarter.",
        "PALO ALTO – November 8, 2023 – AppLovin Corporation (NASDAQ: APP) today announced financial results.",
        "NEW YORK - Consolidated Edison, Inc. (Con Edison) (NYSE: ED) today reported 2024 first quarter net income.",
        "HOUSTON – January 23, 2024 – Halliburton Company (NYSE: HAL) announced today net income of $661 million.",
    ]:
        lines = ["2025 Outlook", "• Revenue Growth of 2% to 4%", dateline]
        assert _is_guidance_teaser_anchor(lines, 0) is True


def test_teaser_anchor_csco_shape():
    # The wrapped-bullet fragment sits ~27-40 lines above the dateline
    # (News Summary bullets in between); the real "Guidance" heading is
    # ~120 lines later.
    lines = ["guidance range"] + _filler(27) + [
        "SAN JOSE, Calif. — November 13, 2024 — Cisco today reported first quarter results."
    ]
    assert _is_guidance_teaser_anchor(lines, 0) is True
    lines40 = ["guidance range"] + _filler(40) + [
        "SAN JOSE, Calif. — August 13, 2025 — Cisco today reported fourth quarter results."
    ]
    assert _is_guidance_teaser_anchor(lines40, 0) is True


def test_teaser_anchor_true_anchor_with_false_dateline_after():
    # FIS: the real "Full-Year 2024 Outlook" heading, with a false
    # dateline match ("Exhibit I Supplemental Financial Information of
    # Worldpay Holdco, LLC - Unaudited ...") 72 lines later — outside
    # the 50-line window, so the anchor stands.
    lines = ["Full-Year 2024 Outlook"] + _filler(72) + [
        "Exhibit I Supplemental Financial Information of Worldpay Holdco, LLC - Unaudited for the three months ended September 30, 2024"
    ]
    assert _is_guidance_teaser_anchor(lines, 0) is False


def test_teaser_anchor_no_dateline_after():
    lines = [
        "2025 Outlook",
        "In consideration of several factors, the company is establishing full-year 2025 guidance.",
        "Total sales growth 2% to 4%",
        "Free cash flow $800 million to $1.0 billion",
    ]
    assert _is_guidance_teaser_anchor(lines, 0) is False


# --- teaser anchor: synthetic end-to-end -------------------------------

TEASER_RELEASE = [
    "Genuine Parts Company",
    "Reports Fourth Quarter and Full-Year 2024 Results",
    "Fourth Quarter 2024 Highlights",
    "• Sales of $5.8 billion",
    "2025 Outlook",
    "• Revenue Growth of 2% to 4%",
    "• Adjusted Diluted EPS of $7.75 to $8.25",
    GPC_DATELINE,
    "“We delivered a solid quarter,” said Will Stengel, President and Chief Executive Officer.",
    "Fourth Quarter 2024 Results",
    "Sales were $5.8 billion, a 3.3% increase compared to $5.6 billion in the same period of the prior year.",
    "2025 Outlook",
    "In consideration of several factors, the company is establishing full-year 2025 guidance.",
    "Year Ended 12/31/2025",
    "Total sales growth 2% to 4%",
    "Diluted earnings per share $6.95 to $7.45",
    "Free cash flow $800 million to $1.0 billion",
    "Non-GAAP Information",
    "This release contains certain financial information not derived in accordance with United States generally accepted accounting principles.",
]


def test_teaser_release_anchors_on_real_section():
    g = _extract(TEASER_RELEASE)
    assert g is not None
    assert g.split("\n\n")[0] == "2025 Outlook"
    assert "Total sales growth 2% to 4%" in g
    assert "Free cash flow $800 million to $1.0 billion" in g
    assert "ATLANTA" not in g
    assert "Revenue Growth of 2% to 4%" not in g
    assert "Non-GAAP Information" not in g


# --- teaser anchor: real exhibits --------------------------------------

def test_real_gpc_2024_12_31_anchors_on_real_outlook_table():
    g = extract_management_guidance(_load("GPC_2024-12-31.html"))
    assert g is not None
    assert g.split("\n\n")[0] == "2025 Outlook"
    assert "Total sales growth 2% to 4%" in g
    assert "Free cash flow $800 million to $1.0 billion" in g
    assert "ATLANTA" not in g
    assert "Fourth Quarter 2024 Results" not in g


def test_real_csco_anchors_on_guidance_section():
    for name, quarter in [
        ("CSCO_2024-10-26.html", "second quarter of fiscal 2025"),
        ("CSCO_2025-01-25.html", "third quarter of fiscal 2025"),
        ("CSCO_2025-07-26.html", "first quarter of fiscal 2026"),
    ]:
        g = extract_management_guidance(_load(name))
        assert g is not None, name
        assert g.split("\n\n")[0] == "Guidance", name
        assert f"Cisco estimates the following results for the {quarter}" in g, name
        assert "guidance range" not in g.split("\n\n")[0], name


def test_real_akam_shape_b_anchors_on_intro_line():
    g = extract_management_guidance(_load("AKAM_2023-09-30.html"))
    assert g is not None
    assert g.startswith(
        "Financial guidance: The Company reports the following financial guidance"
    )
    assert "CAMBRIDGE" not in g
    assert "We are very pleased" not in g


def test_real_dg_anchors_on_financial_guidance_section():
    g = extract_management_guidance(_load("DG_2024-08-02.html"))
    assert g is not None
    assert g.split("\n\n")[0] == "Fiscal Year 2024 Financial Guidance"
    assert "and Store Growth Outlook" in g
    assert "GOODLETTSVILLE" not in g


def test_real_dg_wrapped_heading_anchors_joined():
    for name in ["DG_2024-11-01.html", "DG_2026-07-31.html"]:
        g = extract_management_guidance(_load(name))
        assert g is not None, name
        assert g.split("\n\n")[0].endswith(
            "Financial Guidance and Store Growth Outlook"
        ), name


# --- anchor recognition: unit ------------------------------------------

def test_akam_intro_line_anchors_despite_length():
    intro = (
        "Financial guidance: The Company reports the following financial "
        "guidance for the fourth quarter and full-year 2023:"
    )
    assert len(intro) > 90
    assert _is_guidance_heading(intro) is True


def test_akam_intro_without_trailing_colon_does_not_anchor():
    # No trailing colon: a claim about guidance, not an announcement
    # of the guidance that follows.
    ln = (
        "Financial guidance: The Company reports the following financial "
        "guidance was strong and beat expectations for the full year."
    )
    assert len(ln) > 90
    assert _is_guidance_heading(ln) is False


def test_financial_intervening_word_heading():
    assert _is_guidance_heading("Fiscal Year 2024 Financial Guidance") is True
    assert (
        _is_guidance_heading(
            "Fiscal Year 2024 Financial Guidance and Store Growth Outlook"
        )
        is True
    )
    assert _is_guidance_heading("Fiscal Year 2024 Financial Results") is False


def test_wrapped_anchor_text_joins_fragments():
    lines = [
        "Fiscal",
        "Year 2024 Financial Guidance and Store Growth Outlook",
        "The Company is updating its financial guidance.",
    ]
    assert _guidance_anchor_text(lines, 0) == (
        "Fiscal Year 2024 Financial Guidance and Store Growth Outlook"
    )
    assert _guidance_anchor_text(lines, 1) is None
    assert (
        _guidance_anchor_text(
            ["Fiscal Year 2024 Financial Guidance", "and Store Growth Outlook"], 0
        )
        == "Fiscal Year 2024 Financial Guidance"
    )


def test_wrapped_anchor_text_prose_is_none():
    lines = [
        "The Company is updating its financial guidance provided on August 29, 2024.",
        "The updated guidance includes the negative impact of the hurricanes.",
    ]
    assert _guidance_anchor_text(lines, 0) is None


# --- section-end follower: unit -----------------------------------------

def _heading_lines(heading: str, follower: list[str]) -> tuple[list[str], int]:
    lines = ["2025 Outlook", "Total sales growth 2% to 4%", heading] + follower
    return lines, 2


def test_follower_non_gaap_mega_line():
    # GPC's non-GAAP prose is flattened into mega-lines: the follower
    # is a 700-char unterminated first line and the run line is its
    # wrapped continuation (lowercase start) — the joined run must be
    # read from the follower, not the continuation alone.
    follower = [
        "This release contains certain financial information not derived in accordance with United States (“U.S.”) generally accepted accounting principles (“GAAP”). These items include adjusted net income, adjusted diluted net income per common share, adjusted gross profit and free cash flow. The company believes that the presentation of adjusted net income, adjusted diluted net income per common share, adjusted gross profit, adjusted selling, administrative and other expenses and free cash flow, when considered together with the corresponding GAAP financial measures and the reconciliations to those measures, provide meaningful",
        "supplemental information to both management and investors that is indicative of the company’s core operations.",
    ]
    lines, j = _heading_lines("Non-GAAP Information", follower)
    assert _is_guidance_next_section_heading(lines, j) is True


def test_follower_corporate_overview_with_more_marker():
    # FDX: the wrapped prose run crosses a "- more -" page marker and
    # a bare page number before terminating — both are skipped in-run.
    # The follower is the real 482-char mega-line (first line of the
    # Corporate Overview paragraph, unterminated at its end) — a
    # column-wrapped ~110-char first line does NOT fire (batch 212:
    # the 60-149 middle is where a guidance section's own sub-headings
    # live, e.g. COIN's commentary sub-headings at 97-126 chars).
    follower = [
        "FedEx Corp. (NYSE: FDX) provides customers and businesses worldwide with a broad portfolio of transportation, e-commerce and business services. With annual revenue of $89 billion, the company offers integrated business solutions utilizing its flexible, efficient, and intelligent global network. Consistently ranked among the world's most admired and trusted employers, FedEx inspires its more than 500,000 employees to remain focused on safety, the highest ethical and professional",
        "- more -",
        "3",
        "standards and the needs of their customers and communities. FedEx is committed to connecting people and possibilities.",
    ]
    lines, j = _heading_lines("Corporate Overview", follower)
    assert _is_guidance_next_section_heading(lines, j) is True


def test_follower_skyd_capital_structure_terminated_figures():
    # SKYD: the follower is a terminated sentence carrying sparse
    # figures (first figure at token 5) — prose, not a table row.
    follower = [
        "We ended the quarter with $3.3 billion in cash and cash equivalents and $13.7 billion in gross debt. We continue to expect to achieve investment grade debt metrics by the end of 2027."
    ]
    lines, j = _heading_lines("Capital Structure & Capital Allocation", follower)
    assert _is_guidance_next_section_heading(lines, j) is True


def test_follower_table_value_row_does_not_end_section():
    # FDX's flattened table: a label ("Diluted EPS") followed by its
    # value line — the first figure sits at token 2, so the lead-value
    # guard refuses the break even though the line is terminated and
    # figure-sparse.
    follower = [
        "(Continuing Operations) $35.30 to $35.90 Compared to the prior forecast of $16.55 to $17.75 per diluted share."
    ]
    lines, j = _heading_lines("Diluted EPS", follower)
    assert _is_guidance_next_section_heading(lines, j) is False
    follower2 = ["Revenue Growth ~12% YoY Compared to the prior forecast of ~11%."]
    lines2, j2 = _heading_lines("Additional Details & Exclusions", follower2)
    assert _is_guidance_next_section_heading(lines2, j2) is False


def test_follower_section_end_helper_direct():
    # The follower helper itself: a wrapped-prose run terminates, a
    # table-row run is killed by the guards.
    lines = ["2025 Outlook", "Total sales growth 2% to 4%", "Comparable Sales"] + [
        "Comparable sales is a key metric that refers to period-over-period comparisons of the company’s net sales excluding the impact of acquisitions, foreign currency and other.",
        "The company’s calculation of comparable sales is computed using total business days for the period and is inclusive of sales from company-owned stores.",
    ]
    assert _is_guidance_section_end_follower(lines, 2) is True
    table_lines = ["2025 Outlook", "Total sales growth 2% to 4%", "Diluted EPS"] + [
        "(Continuing Operations) $35.30 to $35.90 Compared to the prior forecast."
    ]
    assert _is_guidance_section_end_follower(table_lines, 2) is False


# --- "- more -" marker ---------------------------------------------------

def test_more_marker_variants():
    assert _MORE_MARKER_RE.match("-more-")
    assert _MORE_MARKER_RE.match("- more -")
    assert _MORE_MARKER_RE.match("-MORE-")
    assert _MORE_MARKER_RE.match("-  More  -")
    assert not _MORE_MARKER_RE.match("more")
    assert not _MORE_MARKER_RE.match("-- more --")
    assert not _MORE_MARKER_RE.match("- moreover -")


def test_more_marker_skipped_in_guidance_collection():
    g = _extract(
        [
            "2025 Outlook",
            "Total sales growth 2% to 4%",
            "Free cash flow $800 million to $1.0 billion",
            "- more -",
            "Diluted earnings per share $6.95 to $7.45",
            "Adjusted diluted earnings per share $7.75 to $8.25",
            "Effective tax rate Approximately 24%",
        ]
    )
    assert g is not None
    assert "- more -" not in g
    assert "Diluted earnings per share $6.95 to $7.45" in g


# --- section-end follower: real exhibits ---------------------------------

def test_real_gpc_bleed_ends_at_table():
    for name in ["GPC_2025-06-30.html", "GPC_2025-09-30.html", "GPC_2025-12-31.html"]:
        g = extract_management_guidance(_load(name))
        assert g is not None, name
        assert "Non-GAAP Information" not in g, name
        assert "Free cash flow" in g, name
        assert len(g) < 4000, name
    g = extract_management_guidance(_load("GPC_2025-12-31.html"))
    assert "Plan to Separate Automotive and Industrial Businesses" not in g


def test_real_fdx_bleed_ends_before_corporate_overview():
    g = extract_management_guidance(_load("FDX_2025-08-31.html"))
    assert g is not None
    assert "Corporate Overview" not in g
    assert "Media Contact" not in g
    assert "Caitlin Maier" not in g
    assert "- more -" not in g
    g2 = extract_management_guidance(_load("FDX_2026-09-30.html"))
    assert g2 is not None
    assert "Diluted EPS" in g2
    assert "$35.30 to $35.90" in g2
    assert len(g2) > 1000


def test_real_skyd_bleed_ends_before_capital_structure():
    g = extract_management_guidance(_load("SKYD_2025-12-31.html"), max_chars=100000)
    assert g is not None
    assert "Capital Structure & Capital Allocation" not in g
    assert "Our Proposal to Acquire Warner Bros. Discovery" not in g
    assert "Our medium-term financial goals are to transition" in g


# --- blast-212 false breaks (found by the cache blast, fixed here) ------


def test_biib_intro_statement_is_not_a_heading():
    # Blast: Biogen's highlights-area intro-statement ("Full year 2025
    # financial guidance: Non-GAAP diluted EPS expected between $15.25
    # and $16.25") matches the heading regex as a prefix once
    # "financial" joined the intervening words — anchoring on it
    # collects the CEO quote and the results tables instead of the
    # guidance section. A colon followed by prose is a statement, not
    # a heading. The real section heading ("Full Year 2025 Guidance")
    # has no ": ".
    assert _is_guidance_heading(
        "Full year 2025 financial guidance: Non-GAAP diluted EPS expected between $15.25 and $16.25"
    ) is False
    assert _is_guidance_heading("Full Year 2025 Guidance") is True
    assert _is_guidance_heading("Fiscal Year 2024 Financial Guidance") is True
    assert _is_guidance_heading("Full-year 2026 guidance:") is True
    g = extract_management_guidance(_load("BIIB_2024-12-31.html"))
    assert g is not None
    assert "Full Year 2025 Guidance" in g
    assert "Financial Highlights" not in g
    assert "Christopher A. Viehbacher said" not in g


def test_dal_ratio_value_is_not_a_section_heading():
    # Blast: DAL's Gross Leverage value ("Approx. 2.2x", the last row
    # of its guidance table) was classified as a next-section heading
    # — the $/% check misses a bare ratio — cutting the value and the
    # fuel-assumption sentence off the extraction.
    lines, j = _heading_lines("Approx. 2.2x", [
        "Guidance for the December quarter assumes fuel at the forward curve as of October 2, 2026, and includes a refinery benefit of approximately $0.40 per gallon. This results in a projected all-in fuel price for the quarter of approximately $4.25 per gallon."
    ])
    assert _is_guidance_next_section_heading(lines, j) is False
    g = extract_management_guidance(_load("DAL_2026-09-30.html"))
    assert g is not None
    assert "Approx. 2.2x" in g
    assert "Guidance for the December quarter assumes fuel" in g


def test_duol_ebitda_commentary_is_not_a_section_end():
    # Blast: Duolingo's outlook commentary sub-heading "Adjusted
    # EBITDA" was cut — its follower ("... raising our full-year
    # Adjusted EBITDA margin guidance to 28.75% ...") is a terminated
    # prose sentence carrying sparse figures, so the terminated
    # follower test fired. A follower that talks about guidance is
    # guidance commentary, not a new section's prose.
    follower = [
        "Based on strong year-to-date top line growth and continued cost discipline, we’re raising our full-year Adjusted EBITDA margin guidance to 28.75% at the midpoint, representing an expansion of about 310 basis points versus last year."
    ]
    lines, j = _heading_lines("Adjusted EBITDA", follower)
    assert _is_guidance_next_section_heading(lines, j) is False
    g = extract_management_guidance(_load("DUOL_2025-06-30.html"))
    assert g is not None
    assert "Adjusted EBITDA" in g
    assert "we’re raising our full-year Adjusted EBITDA margin guidance" in g


def test_ge_guidance_label_after_colon_is_a_heading():
    # Blast follow-up: the BIIB colon guard first rejected ANY ": ",
    # which killed GE's anchor — "2026 GUIDANCE: 2026 OPERATING PROFIT
    # (NON-GAAP)" is a heading + label, not a statement. The guard now
    # only rejects a colon followed by a figure or a signal verb.
    assert _is_guidance_heading("2026 GUIDANCE: 2026 OPERATING PROFIT (NON-GAAP)") is True
    assert _is_guidance_heading(
        "Full year 2025 financial guidance: Non-GAAP diluted EPS expected between $15.25 and $16.25"
    ) is False
    g = extract_management_guidance(_load("GE_2026-09-30.html"))
    assert g is not None
    assert "2026 GUIDANCE" in g
    assert "Caution Concerning Forward Looking Statements:" not in g
