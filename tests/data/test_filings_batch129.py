"""Batch 129 regression tests: dated press-release document label.

Altria's exhibits head the release with a document label between the
exhibit header and the "Exhibit 99.1" marker:
"ALTRIA GROUP, INC. EARNINGS PRESS RELEASE, DATED OCTOBER 31, 2024"
(or the "PRESS RELEASE DATED" variant without "EARNINGS" and without
the comma). The label is short and headline-shaped, so the loop picked
it and all 8 MO quarters stored the label instead of the real headline
("ALTRIA REPORTS 2024 THIRD-QUARTER AND NINE-MONTHS RESULTS; ...").

The skip is deliberately narrow: the line must end with "DATED <full
month date>" — a genuine headline never does — and stay within 140
chars, so a prose sentence that happens to end with a dated release
reference is not swallowed.
"""

from tickerlens.data.filings import (
    _is_dated_press_release_label,
    extract_press_release_highlights,
)
from tests.data.test_filings import _contact_release_html


def _mo_q3_html(label: str = "ALTRIA GROUP, INC. EARNINGS PRESS RELEASE, DATED OCTOBER 31, 2024") -> str:
    return _contact_release_html(
        "EX-99.1",
        "2",
        "exhibit991erq32024.htm",
        label,
        "Exhibit 99.1",
        "ALTRIA REPORTS 2024 THIRD-QUARTER AND NINE-MONTHS RESULTS;",
        "REAFFIRMS 2024 FULL-YEAR EARNINGS GUIDANCE",
        "RICHMOND, Va. - October 31, 2024 - Altria Group, Inc. (NYSE: MO) today reports our 2024 third-quarter and nine-months business results.",
        "•Reported diluted EPS of $1.34",
        "•Net revenues of $6,259 million",
    )


def test_mo_q3_shaped_release_headline_is_real_headline() -> None:
    hl = extract_press_release_highlights(_mo_q3_html())
    assert hl is not None
    assert hl.split("\n\n")[0].startswith("ALTRIA REPORTS 2024 THIRD-QUARTER")
    assert "EARNINGS PRESS RELEASE, DATED" not in hl
    assert "REAFFIRMS 2024 FULL-YEAR EARNINGS GUIDANCE" in hl


def test_mo_q4_variant_label_is_skipped() -> None:
    hl = extract_press_release_highlights(
        _mo_q3_html("ALTRIA GROUP, INC. PRESS RELEASE DATED JANUARY 30, 2025")
    )
    assert hl is not None
    assert hl.split("\n\n")[0].startswith("ALTRIA REPORTS 2024 THIRD-QUARTER")
    assert "PRESS RELEASE DATED" not in hl


def test_is_dated_press_release_label_guards() -> None:
    assert _is_dated_press_release_label(
        "ALTRIA GROUP, INC. EARNINGS PRESS RELEASE, DATED OCTOBER 31, 2024"
    )
    assert _is_dated_press_release_label(
        "ALTRIA GROUP, INC. PRESS RELEASE DATED JANUARY 30, 2025"
    )
    # Abbreviated month is still a dated label.
    assert _is_dated_press_release_label(
        "ALTRIA GROUP, INC. EARNINGS PRESS RELEASE, DATED OCT. 31, 2024"
    )
    # No date: not a label (bare document label, handled elsewhere).
    assert not _is_dated_press_release_label(
        "ALTRIA GROUP, INC. EARNINGS PRESS RELEASE"
    )
    # "DATED" without a full date: not a label.
    assert not _is_dated_press_release_label(
        "ALTRIA GROUP, INC. EARNINGS PRESS RELEASE, DATED TODAY"
    )
    # A genuine results headline is never a dated label.
    assert not _is_dated_press_release_label(
        "JPMORGAN CHASE & CO. EARNINGS RELEASE - THIRD QUARTER 2024 RESULTS"
    )
    # A headline-shaped line that merely mentions a press release mid-line
    # (no dated-date ending) is untouched.
    assert not _is_dated_press_release_label(
        "COMPANY ANNOUNCES EARNINGS PRESS RELEASE FOR THE THIRD QUARTER"
    )
    # Over-long line: the 140-char bound keeps prose out.
    assert not _is_dated_press_release_label(
        "SOME VERY LONG COMPANY NAME, INC. EARNINGS PRESS RELEASE, DATED OCTOBER 31, 2024 "
        + "WITH ADDITIONAL DESCRIPTIVE WORDS ADDED TO PUSH IT PAST THE BOUND"
    )
