"""Batch 275 probe: quantify the batch231 norm() cross-line glue defect.

The footnote-key rule `([,.])\\s+(\\d)` runs on the whole string, so
\\s matches a newline and glues a line ending in "." or "," to a
digit-starting next line. Compare old norm vs a fixed per-line variant
across every stored row + its live extraction, and count:
  - rows where the two norms differ at all
  - rows where old norm glued lines (a normed line containing what the
    fixed norm keeps as two separate lines)
Also check the trademark rule `\\s+([®™©])` for the same cross-line
class: a line ending followed by a ®/™/©-starting next line.
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import norm as norm_old
from tickerlens.data import filings as F

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"


def norm_fixed(s: str) -> str:
    # Same as norm_old except the footnote-key rule is per-line (literal
    # space only) instead of whole-string with \s.
    s = re.sub(r"(?m)^(\s*[•◦▪■●–—‣·○◆▸►])(?!\s)", r"\1 ", s)
    s = re.sub(r"\s+([®™©])", r"\1", s)
    s = re.sub(r"([A-Z][A-Za-z]*) +(TM)(?![A-Za-z])", r"\1\2", s)
    s = re.sub(r"•(?!\s)", "• ", s)
    lines = [ln.rstrip() for ln in s.split("\n")]
    out: list[str] = []
    for ln in lines:
        ln = re.sub(r" +([,.])", r"\1", ln)
        ln = re.sub(r" +([)\]])", r"\1", ln)
        ln = re.sub(r"(\b\d{4}) --(?= |$)", r"\1--", ln)
        ln = re.sub(r"(\d) +(st|nd|rd|th)\b", r"\1\2", ln)
        ln = re.sub(r"([,.]) +(\d)(?= |$)", r"\1\2", ln)
        ln = re.sub(r"([A-Za-z%]) +(\d)(?= |,(?!\s*\d{4})|$)", r"\1\2", ln)
        if ln == "" and out and out[-1] == "":
            continue
        out.append(ln)
    return "\n".join(out).strip()


def glued_lines(old: str, fixed: str) -> list[str]:
    """Old-normed lines that span two fixed-normed lines (i.e. glued)."""
    fl = fixed.split("\n")
    glued = []
    for ln in old.split("\n"):
        # a glued line contains a fixed line as a strict prefix followed
        # by more content that starts a second fixed line
        for i, f in enumerate(fl):
            if ln.startswith(f) and len(ln) > len(f) and i + 1 < len(fl):
                rest = ln[len(f):]
                if rest.startswith(fl[i + 1][:20]) or fl[i + 1].startswith(rest[:20]):
                    glued.append(ln)
                    break
    return glued


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    print(f"stored rows: {len(rows)}")
    diff_stored = diff_live = 0
    glue_stored = glue_live = 0
    glue_examples = []
    tm_cross = 0
    tm_examples = []
    for t, pe, stored in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        for label, text in (("stored", stored),):
            if norm_old(text) != norm_fixed(text):
                diff_stored += 1
                g = glued_lines(norm_old(text), norm_fixed(text))
                if g:
                    glue_stored += 1
                    if len(glue_examples) < 5:
                        glue_examples.append((key, label, g[0][:160]))
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        live = F.extract_press_release_highlights(html)
        if live is None:
            continue
        if norm_old(live) != norm_fixed(live):
            diff_live += 1
            g = glued_lines(norm_old(live), norm_fixed(live))
            if g:
                glue_live += 1
                if len(glue_examples) < 10:
                    glue_examples.append((key, "live", g[0][:160]))
        # trademark cross-line check on raw live text
        for m in re.finditer(r"\n\s*[®™©]", live):
            tm_cross += 1
            if len(tm_examples) < 5:
                tm_examples.append((key, live[max(0, m.start() - 60):m.start() + 20].replace("\n", " / ")))
    print(f"rows where norm differs (stored): {diff_stored}")
    print(f"rows where norm differs (live):   {diff_live}")
    print(f"rows with glued lines (stored):   {glue_stored}")
    print(f"rows with glued lines (live):     {glue_live}")
    print(f"trademark cross-line hits in live text: {tm_cross}")
    for key, label, ex in glue_examples:
        print(f"  GLUE {key} [{label}]: ...{ex}...")
    for key, ex in tm_examples:
        print(f"  TM-CROSS {key}: ...{ex}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
