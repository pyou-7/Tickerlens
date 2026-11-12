"""Batch 238 probe: the FDX labeled-value footnote false positive.

Batch 237 carried FDX 2026-05-31 forward: the live guidance extraction
drops the "(ETR) ~23% Prior to CY 2026 additional MTM adjustments ..."
row because _LEDE_FOOTNOTE_RE matches the parenthesized label "(ETR)"
and _opens_footnote_def treats the line as a footnote definition.
The repair-side guard (batch 237, _is_labeled_value_line in
batch236_repair.py) already refuses to credit such a line as chrome;
this batch moves the guard into the extractor itself.

This probe:
  1. Reproduces the drop on the cached FDX 2026-05-31 exhibit.
  2. Surveys the whole exhibit cache for the labeled-value shape
     ^\\([A-Z]{2,}\\) followed by a value-like token, so the fix's
     population is bounded before the opener changes.

Usage: .venv/bin/python scripts/batch238_probe.py
"""
import os
import re
import sys

sys.path.insert(0, "src")

from tickerlens.data.filings import (
    _is_paren_prose_continuation,
    _opens_footnote_def,
    extract_management_guidance,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"

# A value-like token right after the parenthesized label: starts with
# $ or (, "~$" / "≈$", or ends with % — the repair-side predicate's
# conditions (batch 237).
_VALUE_TOK_RE = re.compile(r"^(?:\$|\(|~\$|≈\$|\S+%)")
_LABEL_RE = re.compile(r"^\(([A-Za-z]{2,})\)\s*(\S+)")


def is_labeled_value(ln: str) -> bool:
    m = _LABEL_RE.match(ln.strip())
    if not m:
        return False
    return bool(_VALUE_TOK_RE.match(m.group(2)))


def main() -> None:
    html = open(os.path.join(CACHE, "FDX_2026-05-31.html"), encoding="utf-8").read()
    g = extract_management_guidance(html)
    line = (
        "(ETR) ~23% Prior to CY 2026 additional MTM adjustments for "
        "retirement plan accounting, and adjustments related to MTM "
        "accounting for the FedEx Freight investment and utilization "
        "of the FedEx Freight spin-off dividend."
    )
    print("FDX 2026-05-31 live extraction keeps the (ETR) row:",
          line[:40] in (g or ""))
    print("  _opens_footnote_def(line):", _opens_footnote_def(line))
    print("  _is_paren_prose_continuation(line):",
          _is_paren_prose_continuation(line))
    print("  probe labeled-value predicate:", is_labeled_value(line))
    print("  stored row has it: yes (batch 237 diagnosis)")
    print()

    # Cache-wide survey of the labeled-value shape in raw exhibit text.
    hits: dict[str, list[str]] = {}
    for name in sorted(os.listdir(CACHE)):
        if not name.endswith(".html"):
            continue
        text = open(os.path.join(CACHE, name), encoding="utf-8",
                    errors="replace").read()
        # Strip tags crudely: lines of visible text.
        import html as _html
        from html.parser import HTMLParser

        class _Strip(HTMLParser):
            def __init__(self):
                super().__init__()
                self.lines: list[str] = []
                self._buf = ""

            def handle_data(self, data):
                self._buf += data

            def handle_endtag(self, tag):
                if tag in ("p", "div", "tr", "li", "br", "h1", "h2", "h3"):
                    if self._buf.strip():
                        self.lines.append(self._buf.strip())
                    self._buf = ""

        p = _Strip()
        try:
            p.feed(text)
        except Exception:
            continue
        for ln in p.lines:
            if is_labeled_value(ln):
                hits.setdefault(name, []).append(ln.strip()[:120])
    print(f"labeled-value shape in raw text: {len(hits)} exhibits")
    for name, lines in sorted(hits.items()):
        for ln in lines:
            print(f"  {name}: {ln}")


if __name__ == "__main__":
    main()
