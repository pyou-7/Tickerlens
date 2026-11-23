"""Batch 249 probe 2: the PLTR pre-section quote shape.

For each PLTR row, dump the extractor's body lines around the
winning Highlights anchor: the 6 lines before the anchor and the
first 3 section lines. The question: does an executive-quote run
sit immediately before the section heading (after the dateline),
and is it one line per quarter?

Also prints, for every cached exhibit in the blast cache, whether a
quote run immediately precedes any Highlights anchor — the blast
surface of a section-prepend rule.

Usage: .venv/bin/python scripts/batch249_probe2.py > /tmp/batch249_dump2.txt
"""
import os
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from tickerlens.data.filings import (
    _HIGHLIGHTS_SECTION_ANCHOR_RE,
    _html_to_text,
    _is_executive_quote_line,
    _is_quote_pull_dateline,
    _split_bullet_runs,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"


def body_lines(html: str) -> list[str]:
    text = _html_to_text(html)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    return _split_bullet_runs(lines)


def main() -> int:
    for key in ("PLTR_2024-09-30", "PLTR_2025-06-30", "PLTR_2025-09-30"):
        html = open(f"{CACHE}/{key}.html", encoding="utf-8").read()
        lines = body_lines(html)
        print(f"\n{'=' * 100}\n{key} ({len(lines)} body lines)")
        for i, ln in enumerate(lines):
            if _HIGHLIGHTS_SECTION_ANCHOR_RE.search(ln) and len(ln) <= 120:
                print(f"  ANCHOR at {i}: {ln[:160]}")
                for j in range(max(0, i - 6), min(len(lines), i + 3)):
                    mark = ">>>" if j == i else "   "
                    q = "QUOTE" if _is_executive_quote_line(lines[j]) else ""
                    d = "DATELINE" if _is_quote_pull_dateline(lines[j]) else ""
                    print(f"  {mark} [{j:03d}] {q}{d} {lines[j][:200]}")
                break

    # Blast surface: every cached exhibit, any anchor with a quote run
    # immediately before it.
    hits: list[str] = []
    for name in sorted(os.listdir(CACHE)):
        if not name.endswith(".html"):
            continue
        key = name[:-5]
        try:
            html = open(f"{CACHE}/{name}", encoding="utf-8").read()
        except OSError:
            continue
        lines = body_lines(html)
        for i, ln in enumerate(lines):
            if _HIGHLIGHTS_SECTION_ANCHOR_RE.search(ln) and len(ln) <= 120:
                # Walk backwards from the line before the anchor.
                j = i - 1
                run = 0
                while j >= 0 and run < 3 and _is_executive_quote_line(lines[j]):
                    run += 1
                    j -= 1
                if run:
                    before = lines[j] if j >= 0 else ""
                    hits.append(
                        f"{key} anchor={i} quote_run={run} "
                        f"before_is_dateline={_is_quote_pull_dateline(before)} "
                        f"before={before[:90]!r}"
                    )
                break  # first anchor only, like the section scan's order
    print(f"\n\nANCHOR-PRECEDED-BY-QUOTE EXHIBITS: {len(hits)}")
    for h in hits:
        print(f"  {h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
