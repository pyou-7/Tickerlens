"""Batch 265 probe: the CINF x2 carry-forward (Q3 2024 + Q3 2025).

Stored rows are the lede shape (headline + "today reported:" + 5 bullets:
net income, operating income, increase, book value, value creation ratio).
Live extraction is the section shape (Insurance Operations bullets +
Investment bullets + CEO quote). The other 7 CINF quarters already store
the section shape (stored == live), so the Q3 rows are stale snapshots of
the pre-batch-222 extractor, when the section was rejected as a financial
table because the CEO quote's $/% lines pushed data_rows to 4 (see the
batch-222 snapshot comment in _extract_highlights_sections_anchored).

This probe measures the competition directly: the leading-bullet block
(5 lede bullets) vs the winning section candidate, scored by absolute
figure-line count (batch 102/261 rule), and checks the other 7 quarters
are stored == live.
"""
import os
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _financial_line_count,
    _html_to_text,
    _leading_bullet_block,
    _extract_highlights_section,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def _body_lines(pe: str) -> list[str]:
    html = open(f"{CACHE}/CINF_{pe}.html", encoding="utf-8").read()
    lines = [ln.strip() for ln in _html_to_text(html).split("\n") if ln.strip()]
    hi = next(
        i for i, ln in enumerate(lines) if ln.startswith("Cincinnati Financial Reports")
    )
    return lines[hi + 1 :]


def _score(content: list[str]) -> tuple[int, int]:
    count = _financial_line_count(content)
    density = count / max(len(content), 1)
    return (1, count) if (count >= 2 and density >= 0.4) else (0, 0)


def main() -> None:
    con = sqlite3.connect(DB)
    for pe in ("2024-09-30", "2025-09-30"):
        body = _body_lines(pe)
        leading = _leading_bullet_block(body) or []
        section = _extract_highlights_section(body) or []
        live = extract_press_release_highlights(
            open(f"{CACHE}/CINF_{pe}.html", encoding="utf-8").read()
        )
        stored = con.execute(
            "SELECT q.press_release_highlights FROM quarterly_financials q "
            "JOIN companies c ON c.cik = q.cik "
            "WHERE c.ticker = 'CINF' AND q.period_end = ?",
            (pe,),
        ).fetchone()[0]
        print(f"--- CINF_{pe} ---")
        print(f"leading block: {len(leading)} lines, "
              f"figure lines {_financial_line_count(leading)}, score {_score(leading)}")
        print(f"  first: {leading[0][:100] if leading else '-'}")
        print(f"section cand: {len(section)} lines, "
              f"figure lines {_financial_line_count(section)}, score {_score(section)}")
        print(f"  first: {section[0][:100] if section else '-'}")
        print(f"  quote lines in section: "
              f"{sum(1 for ln in section if 'commented' in ln or ln.startswith(chr(8220)))}")
        print(f"live == section candidate: {live == chr(10).join(['Cincinnati Financial Reports ' + ('Third-Quarter 2024 Results' if pe == '2024-09-30' else 'Third-Quarter 2025 Results'), ''] + section) if live else False}")
        print(f"stored is lede shape: {'today reported:' in (stored or '')}")
        print(f"live starts with section bullet: {(live or '').splitlines()[2][:80] if live and len(live.splitlines()) > 2 else '-'}")
        print(f"stored len {len(stored or '')} live len {len(live or '')}")
    print("--- other CINF quarters: stored == live? ---")
    for (pe, stored) in con.execute(
        "SELECT q.period_end, q.press_release_highlights FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik WHERE c.ticker = 'CINF' "
        "AND q.period_end NOT IN ('2024-09-30', '2025-09-30') ORDER BY q.period_end"
    ).fetchall():
        live = extract_press_release_highlights(
            open(f"{CACHE}/CINF_{pe}.html", encoding="utf-8").read()
        )
        print(f"  {pe}: {'SAME' if stored == live else 'DIFF'} "
              f"(stored {len(stored or '')}, live {len(live or '')})")
    con.close()


if __name__ == "__main__":
    main()
