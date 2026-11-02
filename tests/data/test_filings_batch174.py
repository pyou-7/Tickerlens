"""Batch 174: bare period-fragment lines ("Three Months", "Six Months",
"Ended", "Year Ended", "Full Year") break the leading-bullet block and
the Highlights section collector, the same way a period/date header
already does. The lede loop already drops them via _is_lede_table_line;
the bullet block and the section collector break only on the strong
heading shapes, so a fragment rode along as a bullet continuation
(BlackRock: the "SUMMARY OF NONOPERATING INCOME" table's header follows
the expense bullets, and the fragments tail the stored rows).

Also in this batch (repair script only, validated by dry/write runs, not
unit tests): the batch-173 audit cohort repair continues — contact-block
lines are defect lines for the preservation gates, and the stored
headline is the first real stored paragraph (AWK/PHM stored rows open
with the contact block, not the headline).
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _extract_highlights_sections,
    _is_bare_period_fragment,
    _leading_bullet_block,
    extract_press_release_highlights,
)


def test_bare_period_fragment_matches():
    assert _is_bare_period_fragment("Three Months")
    assert _is_bare_period_fragment("Six Months")
    assert _is_bare_period_fragment("Ended")
    assert _is_bare_period_fragment("Year Ended")
    assert _is_bare_period_fragment("Full Year")
    assert _is_bare_period_fragment("Three Months Ended")
    assert _is_bare_period_fragment("Nine Months")
    assert _is_bare_period_fragment("Twelve Months")


def test_bare_period_fragment_guards():
    # Prose with a month name / digits is a date header or narrative,
    # never a bare fragment.
    assert not _is_bare_period_fragment(
        "Three months ended September 30, 2025, revenue grew 5%."
    )
    assert not _is_bare_period_fragment("Three Months Ended September 30,")
    assert not _is_bare_period_fragment("Full Year 2025 Actual")
    assert not _is_bare_period_fragment("Fourth Quarter 2024")
    # A bullet never qualifies — its text is a highlight, not a header.
    assert not _is_bare_period_fragment("\u2022Three months ended strong.")
    # A real prose word breaks it.
    assert not _is_bare_period_fragment("Three months later, we returned")
    assert not _is_bare_period_fragment("Year ended with record sales.")
    assert not _is_bare_period_fragment("Ended the quarter with $1.2 billion")


def _extract(body_lines):
    body = "".join(f"<p>{ln}</p>" for ln in body_lines)
    return extract_press_release_highlights(
        f"<html><body>{body}<h2>About Acme</h2><p>Boilerplate.</p></body></html>"
    )


def test_leading_bullet_block_breaks_on_fragment():
    # BlackRock shape: expense bullets, then the nonoperating-income
    # table's title and its flattened period header.
    out = _extract([
        "BlackRock Reports Full Year 2024 Diluted EPS of $42.01, or $43.61 as adjusted",
        "\u2022Employee compensation and benefits expense increased $382 million "
        "from the fourth quarter of 2023 and $307 million from the third quarter "
        "of 2024, reflecting higher incentive compensation and headcount growth.",
        "\u2022Sales, asset and account expense increased $141 million from the "
        "fourth quarter of 2023 and $34 million from the third quarter of 2024, "
        "driven by higher distribution and servicing costs.",
        "\u2022General and administration expense increased $7 million from the "
        "fourth quarter of 2023 and $34 million from the third quarter of 2024, "
        "as technology spending rose across the platform.",
        "SUMMARY OF NONOPERATING INCOME (expense), less net income (loss) "
        "attributable TO noncontrolling interests",
        "Three Months",
        "Three Months",
        "Ended",
        "December 31, 2024",
    ])
    assert out is not None
    assert "Employee compensation and benefits expense increased $382 million" in out
    assert "Sales, asset and account expense increased $141 million" in out
    assert "General and administration expense increased $7 million" in out
    assert "Three Months" not in out
    assert "December 31, 2024" not in out


def test_leading_bullet_block_direct():
    lines = [
        "\u2022Employee compensation and benefits expense increased $382 million "
        "from the fourth quarter of 2023.",
        "\u2022Sales, asset and account expense increased $141 million from the "
        "fourth quarter of 2023.",
        "Three Months",
        "Three Months",
        "\u2022This bullet sits after the table header and must not be served.",
    ]
    block = _leading_bullet_block(lines)
    assert block is not None
    assert len(block) == 2
    assert all("Three Months" not in ln for ln in block)
    assert "This bullet sits after" not in "\n".join(block)


def test_highlights_section_breaks_on_fragment():
    sections = _extract_highlights_sections([
        "Third Quarter Highlights",
        "\u2022Revenue grew 12% year-over-year to $4.1 billion, driven by "
        "strong demand across all segments and regions.",
        "\u2022Adjusted operating margin expanded 150 basis points to 28.4%, "
        "reflecting disciplined cost management and mix.",
        "Three Months",
        "Ended",
        "December 31, 2025",
        "Revenue $4,100 $3,700",
    ])
    assert sections
    joined = "\n".join(sections[0])
    assert "Revenue grew 12%" in joined
    assert "Adjusted operating margin expanded" in joined
    assert "Three Months" not in joined
    assert "Revenue $4,100" not in joined
