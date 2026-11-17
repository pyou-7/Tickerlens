"""Batch 266 probe 2: measure the BNY competition.

For BNY_2024-09-30 (representative of all 8): the leading-bullet block,
every anchored Highlights-section candidate with its anchor, line count,
figure-line count and (financial?, count) score, and where the stored
lede+CEO-commentary shape sits relative to the winner. Also checks the
same competition shape holds for the other 7 quarters (winner anchor and
score, stored shape markers).
"""
import sqlite3
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _extract_highlights_sections_anchored,
    _financial_line_count,
    _html_to_text,
    _leading_bullet_block,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def _score(content: list[str]) -> tuple[int, int]:
    count = _financial_line_count(content)
    density = count / max(len(content), 1)
    return (1, count) if (count >= 2 and density >= 0.4) else (0, 0)


def _body_lines(pe: str) -> list[str]:
    html = open(f"{CACHE}/BNY_{pe}.html", encoding="utf-8").read()
    lines = [ln.strip() for ln in _html_to_text(html).split("\n") if ln.strip()]
    hi = next(i for i, ln in enumerate(lines) if ln.startswith("BNY Reports"))
    return lines[hi + 1 :]


def main() -> None:
    con = sqlite3.connect(DB)
    pe = "2024-09-30"
    body = _body_lines(pe)
    print(f"--- BNY_{pe} competition ---")
    leading = _leading_bullet_block(body)
    print(f"leading block: {None if leading is None else len(leading)} lines, "
          f"score {_score(leading) if leading else '-'}")
    if leading:
        for ln in leading[:6]:
            print(f"  L: {ln[:100]}")
    for anchor, content, idx, tail in _extract_highlights_sections_anchored(body):
        print(f"anchor {anchor!r}: {len(content)} lines, "
              f"figures {_financial_line_count(content)}, score {_score(content)}, "
              f"tail {len(tail)}")
        for ln in content[:4]:
            print(f"  S: {ln[:100]}")
    # Where does the stored CEO-commentary prose sit in the body?
    for i, ln in enumerate(body):
        if ln == "CEO COMMENTARY":
            print(f"CEO COMMENTARY heading at body line {i}; next 3 lines:")
            for ln2 in body[i + 1 : i + 4]:
                print(f"  Q: {ln2[:110]}")
            break
    print("--- all 8 quarters: winner anchor + stored shape ---")
    for (pe2, stored) in con.execute(
        "SELECT q.period_end, q.press_release_highlights FROM quarterly_financials q "
        "JOIN companies c ON c.cik = q.cik WHERE c.ticker = 'BNY' ORDER BY q.period_end"
    ).fetchall():
        live = extract_press_release_highlights(
            open(f"{CACHE}/BNY_{pe2}.html", encoding="utf-8").read()
        )
        body2 = _body_lines(pe2)
        cands = _extract_highlights_sections_anchored(body2)
        win = max(
            [(None, _leading_bullet_block(body2) or [], None, [])] + cands,
            key=lambda c: _score(c[1]),
        ) if cands or _leading_bullet_block(body2) else None
        print(f"  BNY_{pe2}: stored lede+quote={'CEO COMMENTARY' in (stored or '')} "
              f"live lines={len((live or '').splitlines())} "
              f"winner anchor={win[0]!r} winner figures={_financial_line_count(win[1])} "
              f"live has 'Results'={'Results' in (live or '')} "
              f"live has 'CEO'={'CEO' in (live or '')}")
    con.close()


if __name__ == "__main__":
    main()
