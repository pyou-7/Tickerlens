"""Batch 213: management-guidance 4000-char cap raised to 8000.

The batch-212 carry-forward: AMT/CHD/CLX guidance sections run to the
4000-char cap and are stored truncated mid-table / mid-sentence, with a
trailing "…". Survey over all 1,699 cached exhibits
(scripts/batch213_survey.py): 26 sections exceed 4000 chars uncapped,
max 7614 (CCI 2023-09-30, ends at its natural close), p99 5741, none
over 8000 — and 134 of 1307 stored rows end with the truncation "…".
The 30-line budget + 20-line lookahead (batch 204) is the runaway
bound; the char cap only needs to cover the longest genuine section,
so the default moves 4000 -> 8000.

Residual, by design: ABNB's sections still end mid-sentence at ~6135
chars — that is the LINE budget cutting a 30+ line section with no
break in the lookahead window, not the char cap.
"""

import os

from tickerlens.data.filings import extract_management_guidance

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def _load(name: str) -> str:
    with open(os.path.join(CACHE, name), encoding="utf-8") as fh:
        return fh.read()


def _extract(body_lines, **kwargs):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_management_guidance(f"<html><body>{body}</body></html>", **kwargs)


def _guidance_lines(n_lines: int, chars_per_line: int) -> list[str]:
    """Genuine-looking outlook prose lines of ~chars_per_line each."""
    lines = ["Fiscal Year 2026 Outlook"]
    for k in range(n_lines):
        # A wrapped outlook sentence carrying $ figures — long prose,
        # never a heading, call notice, or footnote shape.
        sentence = (
            f"The company expects full year 2026 net sales of ${k + 10}.5 "
            f"billion, with adjusted diluted earnings per share between "
            f"${k + 4}.10 and ${k + 4}.90, reflecting continued momentum in "
            f"the core business and disciplined cost management across "
            f"all operating segments during the fiscal year."
        )
        # Pad / trim to the target length without breaking the sentence.
        while len(sentence) < chars_per_line:
            sentence += " The outlook assumes steady demand and stable input costs."
        lines.append(sentence[:chars_per_line].rsplit(" ", 1)[0] + ".")
    lines.append("Conference Call Details")
    return lines


# --- synthetic: the cap no longer truncates a genuine long section ---


def test_default_cap_keeps_5000_char_section_whole():
    lines = _guidance_lines(20, 250)
    result = _extract(lines)
    assert result is not None
    assert len(result) > 4000
    assert not result.endswith("…")
    assert "Conference Call Details" not in result
    assert "adjusted diluted earnings per share" in result


def test_explicit_4000_cap_still_truncates():
    # The parameter is honored: an explicit 4000 cap reproduces the
    # old stored truncation on the same section.
    lines = _guidance_lines(20, 250)
    result = _extract(lines, max_chars=4000)
    assert result is not None
    assert result.endswith("…")
    assert len(result) <= 4001
    whole = _extract(lines)
    assert whole.startswith(result[:-1].rstrip())


def test_section_over_8000_still_truncates_at_word_boundary():
    lines = _guidance_lines(25, 350)
    result = _extract(lines)
    assert result is not None
    assert result.endswith("…")
    assert len(result) <= 8001
    assert len(result) > 7000
    # Truncation lands on a word boundary, never mid-word.
    assert result[-2] != " " and " " in result[-30:]


# --- real exhibits: the named truncated sections now complete ---------


def test_amt_2026_q1_completes_capex_table():
    out = extract_management_guidance(_load("AMT_2026-03-31.html"))
    assert out is not None
    assert len(out) == 4198
    assert not out.endswith("…")
    assert out.endswith("Total $ 1,800 to $ 1,910\n\n_______________")
    old = extract_management_guidance(_load("AMT_2026-03-31.html"), max_chars=4000)
    assert out.startswith(old[:-1].rstrip())


def test_clx_2026_q3_completes_adjusted_eps_table():
    out = extract_management_guidance(_load("CLX_2026-03-31.html"))
    assert out is not None
    assert len(out) == 6079
    assert not out.endswith("…")
    assert out.endswith("$ 0.90 $ (0.90) $ (0.90)")
    old = extract_management_guidance(_load("CLX_2026-03-31.html"), max_chars=4000)
    assert out.startswith(old[:-1].rstrip())


def test_chd_2025_q3_completes_quote_and_footnote_pointer():
    out = extract_management_guidance(_load("CHD_2025-09-30.html"))
    assert out is not None
    assert len(out) == 4144
    assert not out.endswith("…")
    assert out.endswith(
        "See non-GAAP reconciliations included at the end of this release."
    )
    old = extract_management_guidance(_load("CHD_2025-09-30.html"), max_chars=4000)
    assert out.startswith(old[:-1].rstrip())


def test_cci_2023_q3_longest_genuine_section_completes():
    # Longest genuine section in the 1,699-exhibit cache: 7614 chars,
    # ending at its natural close.
    out = extract_management_guidance(_load("CCI_2023-09-30.html"))
    assert out is not None
    assert len(out) == 7614
    assert not out.endswith("…")
    assert out.endswith(
        "Additional information is available in Crown Castle's quarterly "
        "Supplemental Information Package posted in the Investors section "
        "of our website."
    )


def test_abnb_line_budget_residual_documented():
    # ABNB's section is 6135 chars uncapped but still ends mid-sentence:
    # the 30-line budget (batch 204) cuts it, not the char cap. The cap
    # raise recovers ~2,100 chars of genuine regional commentary; the
    # line-budget cut is by design and stays.
    out = extract_management_guidance(_load("ABNB_2025-12-31.html"))
    assert out is not None
    assert len(out) == 6135
    assert not out.endswith("…")
    assert out.endswith("we")
