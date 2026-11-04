"""Batch 189: abbreviated bare role lines (CEO/CFO/COO) are role lines.

Arthur J. Gallagher wraps its CEO-quote attribution as "said J. Patrick
Gallagher, Jr.," / "Chairman and CEO." — the tail is a bare role line,
but "CEO" was not role vocabulary, so the tail consumed the last lede
budget line and the finish rule read it as a complete item, orphaning
the quote body ("Our two-pronged revenue growth strategy ... drove
double-digit top line growth for the 20th straight quarter") that
follows it. AJG Q4 FY2025 is the only cached quarter shaped this way;
the full-cache survey finds only 4 distinct lines newly matching, all
bare role lines.
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_bare_role_line,
    extract_press_release_highlights,
)


def test_bare_role_line_abbreviations():
    # The AJG Q4 FY2025 attribution tail and its siblings.
    assert _is_bare_role_line("Chairman and CEO.")
    assert _is_bare_role_line("President and CEO.")
    assert _is_bare_role_line("CHAIR AND CEO")
    assert _is_bare_role_line("CEO and Co-Founder")
    assert _is_bare_role_line("Chief Financial Officer")  # batch 173 pin
    assert _is_bare_role_line("President and Chief Executive Officer")
    # A lone abbreviation is not a line (2-word floor), and prose that
    # merely mentions a role still fails on the non-role words.
    assert not _is_bare_role_line("CEO")
    assert not _is_bare_role_line("Our CEO said the quarter was strong.")
    assert not _is_bare_role_line("John Smith, CEO")
    assert not _is_bare_role_line("CEO transition announced today.")
    assert not _is_bare_role_line("CEO pay ratio disclosure")


def _extract(body_lines):
    # Like batch 173's _extract: verbatim lines, no lorem filler.
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


def test_lede_serves_ajg_q4_quote_body_past_abbreviated_role_tail():
    # AJG Q4 FY2025, verbatim lede shape (table block omitted — it is
    # skipped without consuming budget either way): the dateline, the
    # CFO-commentary pointer, the non-GAAP pointer and the tax-recon
    # pointer fill four budget lines, the quote opener is the fifth,
    # and the wrapped "Chairman and CEO." tail must not be the sixth.
    out = _extract([
        "ARTHUR J. GALLAGHER & CO. ANNOUNCES FOURTH QUARTER AND FULL YEAR 2025 FINANCIAL RESULTS",
        "ROLLING MEADOWS, IL, January 29, 2026 \u2014 Arthur J. Gallagher & Co. (NYSE: AJG) today reported its financial results for the quarter ended December 31, 2025.",
        "\u201cCFO Commentary\u201d and \u201cSupplemental Quarterly Data,\u201d which may also be referenced during the call, please visit ajg.com/IR. These documents contain both GAAP and non-GAAP measures.",
        "Investors and other users of this information should read carefully the section entitled \u201cInformation Regarding Non-GAAP Measures\u201d beginning on page 9.",
        "taxes is shown on pages 14 and 15.",
        "\u201cWe had an excellent fourth quarter and a terrific 2025!\u201d said J. Patrick Gallagher, Jr.,",
        "Chairman and CEO.",
        "\u201cOur two-pronged revenue growth strategy, that\u2019s organic and M&A, drove",
        "double-digit top line growth for the 20th straight quarter. Fourth quarter revenue growth for our combined Brokerage and Risk Management segments was in excess of 20%.",
    ])
    assert out is not None
    assert "Chairman and CEO." not in out
    assert "We had an excellent fourth quarter and a terrific 2025!" in out
    assert "Our two-pronged revenue growth strategy" in out
    assert "double-digit top line growth for the 20th straight quarter" in out
    assert "in excess of 20%" in out
