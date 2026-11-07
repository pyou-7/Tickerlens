"""Batch 206: page-footer furniture lines in the guidance collector.

Batch 205 carry-forward: CCI's stored guidance rows carry "The pathway
to possible." / "CrownCastle.com" furniture lines (2 lines per
occurrence, 11 occurrences across 8 stored rows). CCI prints a page
footer on every page of its releases — tagline, bare domain, "News
Release continued: Page N" — and the OUTLOOK section spans pages, so
footers fall mid-table inside the collected guidance. The "News Release
continued" line was already skipped by _ADMIN_LINE_RE (its "news
release" prefix); the tagline and the domain were not.

Fix (extract_management_guidance, in-loop skips so the 30-line budget
is spent only on kept lines — the batch-193 lesson): a bare-domain line
(_BARE_DOMAIN_RE: a line that IS a domain, nothing else) is skipped
like an admin line, and a short terminated sentence-case line
immediately before a bare domain is skipped as the footer tagline. The
lookahead keeps the tagline skip narrow — a genuine short guidance
sentence is skipped only when the very next line is a bare domain, the
footer signature — and figure lines ($/%/digits) and title-case lines
never match, so a table row or a heading before a domain pointer
survives. Prose that merely mentions a domain ("available at
www.crowncastle.com") never matches the no-spaces domain shape.

Blast (blast206/g_new vs blast205/g_new, 1,699 exhibits): 12 diffs, 0
None-flips — all CCI. 8 pure furniture drops (the tagline + domain
pairs removed, guidance content untouched); 4 completions — the freed
budget slots let the collector reach the rest of the outlook table
(2023-09-30: AFFO rows + reconciliation bullets; 2024-12-31 and
2025-12-31: the AFFO row; 2026-06-30: FFO/AFFO rows, discretionary-capex
row and 8 outlook bullets) instead of truncating mid-table. The 4
pre-seeding quarters (2023-09-30, 2023-12-31, 2024-03-31, 2024-06-30)
have no stored rows; the fix serves them on next refresh. Repair: 8
stored CCI rows repaired (11 furniture pairs removed); CCI 2026-09-30
has no cached exhibit, so it serves on refresh.
"""
import os
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import extract_management_guidance


def _bare_domain_re():
    # Local import: the regex is new in batch 206, so a module-level
    # import would break collection on stashed old code during the
    # behavioral pin check.
    from tickerlens.data.filings import _BARE_DOMAIN_RE

    return _BARE_DOMAIN_RE

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _guidance(name: str) -> str:
    g = extract_management_guidance(_load(name))
    assert g is not None
    return g


def _synthetic_doc(lines: list[str]) -> str:
    return "<html><body>" + "".join(f"<p>{ln}</p>" for ln in lines) + "</body></html>"


# --- Real exhibits: the CCI furniture cohort ---------------------------


def test_cci_2024_12_31_footer_pair_dropped_table_kept():
    g = _guidance("CCI_2024-12-31.html")
    assert "The pathway to possible." not in g
    assert "CrownCastle.com" not in g
    assert "$3,885 to $3,915" in g
    assert "AFFO" in g
    assert len(g.split("\n\n")) == 30


def test_cci_2025_03_31_footer_pair_dropped_mid_table():
    # The stored row carries the pair between the intro prose and the
    # outlook table header — the pair must go, the table must stay.
    g = _guidance("CCI_2025-03-31.html")
    assert "The pathway to possible." not in g
    assert "CrownCastle.com" not in g
    assert "$3,885 to $3,915" in g
    assert "(in millions, except per share amounts) Full Year 2025" in g
    assert len(g.split("\n\n")) == 37


def test_cci_2025_06_30_footer_pair_dropped():
    g = _guidance("CCI_2025-06-30.html")
    assert "The pathway to possible." not in g
    assert "CrownCastle.com" not in g
    assert "$10 million increase to site rental revenues" in g
    assert len(g.split("\n\n")) == 45


def test_cci_2025_09_30_footer_pair_dropped():
    g = _guidance("CCI_2025-09-30.html")
    assert "The pathway to possible." not in g
    assert "CrownCastle.com" not in g
    assert "$10 million increase to site rental revenues" in g
    assert len(g.split("\n\n")) == 42


def test_cci_2025_12_31_footer_pair_dropped():
    g = _guidance("CCI_2025-12-31.html")
    assert "The pathway to possible." not in g
    assert "CrownCastle.com" not in g
    assert "$65 million reduction in annualized run-rate operating costs" in g
    assert len(g.split("\n\n")) == 30


def test_cci_2026_03_31_two_footer_pairs_dropped():
    g = _guidance("CCI_2026-03-31.html")
    assert "The pathway to possible." not in g
    assert "CrownCastle.com" not in g
    assert "$40 million decrease in interest expense" in g
    assert len(g.split("\n\n")) == 40


def test_cci_2026_06_30_footer_pair_dropped():
    g = _guidance("CCI_2026-06-30.html")
    assert "The pathway to possible." not in g
    assert "CrownCastle.com" not in g
    assert "$5 million increase to site rental revenues" in g
    assert len(g.split("\n\n")) == 47


def test_cci_2024_09_30_stays_furniture_free():
    # Already clean before the fix (its stored row carries no furniture);
    # regression guard that the skips do not disturb it.
    g = _guidance("CCI_2024-09-30.html")
    assert "The pathway to possible." not in g
    assert "CrownCastle.com" not in g
    assert "$125 to $150 million asset write-down" in g
    assert len(g.split("\n\n")) == 37


# --- The bare-domain regex ----------------------------------------------


def test_bare_domain_regex_matches_domain_lines():
    for ln in (
        "CrownCastle.com",
        "CROWNCASTLE.COM",
        "www.crowncastle.com",
        "investor.example.net",
        "example.co",
        "site.io",
        "CrownCastle.com.",
    ):
        assert _bare_domain_re().match(ln), ln


def test_bare_domain_regex_rejects_prose_and_tickers():
    for ln in (
        "available at www.crowncastle.com",
        "Visit crowncastle.com for details.",
        "More information is posted at CrownCastle.com/investors",
        "BRK.B",
        "Q3 2024",
        "$3,885 to $3,915",
        "EPS.com?",
        "v1.2.3",
    ):
        assert not _bare_domain_re().match(ln), ln


# --- Synthetic docs: the skips and their guards ------------------------


def _footer_doc() -> list[str]:
    return [
        "Financial Outlook",
        "The following table sets forth our current full year 2025 Outlook, which remains unchanged from the previous outlook.",
        "The pathway to possible.",
        "CrownCastle.com",
        "(in millions, except per share amounts) Full Year 2025",
        "Site rental billings",
        "$3,885 to $3,915",
        "Adjusted EBITDA",
        "$2,755 to $2,805",
    ]


def test_synthetic_footer_pair_dropped_table_kept():
    g = extract_management_guidance(_synthetic_doc(_footer_doc()))
    assert g is not None
    assert "The pathway to possible." not in g
    assert "CrownCastle.com" not in g
    assert "$3,885 to $3,915" in g
    assert "$2,755 to $2,805" in g


def test_synthetic_domain_alone_dropped():
    doc = _synthetic_doc(
        [
            "Financial Outlook",
            "We expect full-year revenue of about $4.0 billion, up 8% year over year, with adjusted EBITDA margins near 40%.",
            "CrownCastle.com",
            "We also expect AFFO per share of $7.42 to $7.62 for the full year ahead.",
        ]
    )
    g = extract_management_guidance(doc)
    assert g is not None
    assert "CrownCastle.com" not in g
    assert "$4.0 billion" in g
    assert "$7.42 to $7.62" in g


def test_synthetic_short_sentence_without_domain_kept():
    # The tagline skip needs the domain lookahead: a short sentence with
    # no bare domain after it is genuine guidance and must survive.
    doc = _synthetic_doc(
        [
            "Financial Outlook",
            "We remain confident.",
            "We expect full-year revenue of about $4.0 billion, up 8% year over year, with adjusted EBITDA margins near 40%.",
            "We also expect AFFO per share of $7.42 to $7.62 for the full year ahead, reflecting continued leasing momentum.",
        ]
    )
    g = extract_management_guidance(doc)
    assert g is not None
    assert "We remain confident." in g


def test_synthetic_figure_sentence_before_domain_kept():
    # The $/%/digits guard: a figure-carrying sentence before a domain
    # line is guidance, not a tagline.
    doc = _synthetic_doc(
        [
            "Financial Outlook",
            "We expect revenue growth of 5% to 7% for the full year ahead.",
            "CrownCastle.com",
            "We also expect AFFO per share of $7.42 to $7.62 for the full year ahead, reflecting continued leasing momentum.",
        ]
    )
    g = extract_management_guidance(doc)
    assert g is not None
    assert "We expect revenue growth of 5% to 7%" in g
    assert "CrownCastle.com" not in g


def test_synthetic_title_case_line_before_domain_kept():
    # The title-case guard: a heading-shaped line before a domain pointer
    # is a heading, not a tagline.
    doc = _synthetic_doc(
        [
            "Financial Outlook",
            "We expect full-year revenue of about $4.0 billion, up 8% year over year, with adjusted EBITDA margins near 40%.",
            "Full Year Outlook",
            "CrownCastle.com",
            "We also expect AFFO per share of $7.42 to $7.62 for the full year ahead.",
        ]
    )
    g = extract_management_guidance(doc)
    assert g is not None
    assert "Full Year Outlook" in g
    assert "CrownCastle.com" not in g


def test_synthetic_prose_mentioning_domain_kept():
    # The no-spaces shape: prose that merely mentions a domain is content.
    doc = _synthetic_doc(
        [
            "Financial Outlook",
            "Additional information is available at www.crowncastle.com for investors seeking the full supplemental package.",
            "We expect full-year revenue of about $4.0 billion, up 8% year over year, with adjusted EBITDA margins near 40%.",
        ]
    )
    g = extract_management_guidance(doc)
    assert g is not None
    assert "www.crowncastle.com" in g
    assert "$4.0 billion" in g
