"""Batch 242 repair: the highlights sweep, gate S4 — the 82
SKIP-first-diff rows from the batch 231/232 source-verified
stale-row sweep (as re-censused by batch 241).

The batch-242 probe decomposes the 82 into:

  stored-leading chrome (the live extraction never carries it, so
      the first-line relation fails even though the bullets match):
    bare release-date line -- AGNC x8 ("October 21, 2024" over the
        headline + bullets), NFLX x2 (date + "Fellow shareholders,"
        salutation over the letter bullets). Two AGNC rows stay
        blocked: 2024-12-31 / 2025-12-31 carry DIFFERENT figures
        live ($0.84 / $1.74 comprehensive income vs stored
        $(0.11) / $0.89) — a genuinely different exhibit, so the
        offset match below fails and the loss check would too.
    contact block -- ECL x8 ("Andrew Hedberg (651) 250-2185" over
        the bullets), AWK x1 (role lines + bare phone over the
        bullets), EL x1 ("Investors: Rainey Mancini" / "Media: Jill
        Marvin" over the headline).
    masthead -- GD x8 ("11011 Sunset Hills Road" / "Reston,
        Virginia 20190 News" / "www.gd.com" over the headline).
  headline wrap / prefix (stored headline is the live headline
      split or truncated; the bullets match):
    two-line join -- DGX x4 early ("... Financial Results;" /
        "Updates Guidance for Full Year 2024" == the live headline
        line), DKS x4. DGX 2024-09-30 + 2025-03-31 stay blocked: the
        stored row ends on a CEO quote the live extraction drops.
        DGX 2025-09-30 and later stay blocked: strategic bullets
        (Corewell JV, Fresenius assets) live does not carry.
    prefix -- DD x1, EQIX x1, ET x3, DRI x3 (13-line live rows:
        2025-05-25, 2026-05-31, 2026-08-30). DRI's 7-line-live rows
        stay blocked: the stored same-restaurant-sales table + a
        repurchase bullet live drops. DRI's footnote-key spacing
        ("sales 1" vs "sales1") is a batch-242 norm fix, not a gate
        change.
  single-line flattening -- CTVA x8: the stored row is ONE line,
      headline + bullets joined with " • ". Splitting on the bullet
      glyph recovers the lines; two adjacent parts re-join with
      " – " where the live extraction fuses them (the bullet whose
      text runs through the dateline into the lede; "Cash provided
      by operating activities – continuing operations ..."). The
      2025-09-30 and later rows also gain the live separation
      bullets (real highlights content the seed-era extraction never
      reached) — bullets/prose, never table rows.
  spacing-only -- BKNG x1 ("3 rd Quarter" vs "3rd Quarter", a
      batch-242 norm fix) + NFLX 2024-09-30 ("Couple , Nobody" vs
      "Couple, Nobody", a batch-242 norm fix). NFLX 2025-06-30 stays
      blocked: a different bullet selection (content bullets live
      does not carry).

Gate S4 is gate S3 with the entry condition replaced: before the
first-line relation, stored-leading chrome lines are stripped (bare
date, shareholder-letter salutation, contact block, masthead) and
the stored row is aligned to the live headline — EQ / SUFFIX as
before, plus JOIN (first two stored lines join to the live
headline), PREFIX (stored first line is a prefix of the live
headline), OFFSET (stored first line is live's line 1 or 2 — the
stored row never carried the live headline lines), and the
single-line-flattening split. Every other gate-S3 condition is
unchanged: the dateline-presence check, the loss check over every
stored line, live table fraction, added-table, tail, fragment. The
loss check is what keeps the still-blocked rows blocked — a
different exhibit's bullets carry different figures, and a dropped
quote / repurchase bullet / strategic bullet is a real loss.

Still blocked by design (NOT repaired here): AMT x8 (stored is a
flattened highlights table, live is bullets — a stored-shape
question, plus the live text still opens on an orphaned contact
role line, "Senior Vice President, Investor Relations and FP&A",
which the extractor's contact-block skip does not drop — extractor
follow-up); APO x8 (stored is a flattened earnings table, live is
a lede); COIN x1 (stored is slide-deck junk, live is a slide deck);
CSCO x3 (stored is body prose, live is bullets); the AGNC x2
figure-mismatch rows; DGX x2 quote rows + x4 strategic-bullet rows;
DRI x5 7-line-live rows; NFLX 2025-06-30; plus the 192 SKIP-loss
rows and the standing list from batch 241.

Usage: DRY_RUN=1 .venv/bin/python scripts/batch242_repair.py
       .venv/bin/python scripts/batch242_repair.py
"""
import os
import re
import sqlite3
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from batch231_repair import (
    first_line_relation,
    hard_table,
    has_dateline_table_shape,
    is_residue,
    non_empty,
    norm,
)
from batch241_repair import _is_dateline_sentence, is_residue_s3
from tickerlens.data.filings import (
    _BULLET_LEAD_RE,
    extract_press_release_highlights,
)

CACHE = "/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast_html"
DB = "tickerlens.db"
DRY = os.environ.get("DRY_RUN") == "1"

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|"
    "October|November|December"
)
_BARE_DATE_RE = re.compile(rf"^(?:{_MONTHS})\s+\d{{1,2}},\s+\d{{4}}$")
_SALUTATION_RE = re.compile(
    r"^(?:Fellow shareholders|Dear shareholders|Dear fellow shareholders),?$",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"\(\d{3}\)\s*\d{3}[- ]\d{4}|\b\d{3}[-.]\d{3}[-.]\d{4}\b"
)
_ROLE_KEYWORDS = (
    "Investor Relations",
    "Investor",
    "Communications",
    "External Affairs",
    "Vice President",
    "President",
    "Chief ",
    "Director",
    "Manager",
    "Treasurer",
    "Secretary",
    "Media Relations",
)
_HEADLINE_WORDS = ("Reports", "Results", "Announces", "Earnings")
_STREET_SUFFIX_RE = re.compile(
    r"^\d{1,6}\s+\S.*\s(?:Road|Street|St\.?|Avenue|Ave\.?|Drive|Dr\.?"
    r"|Boulevard|Blvd\.?|Lane|Ln\.?|Way|Parkway|Pkwy\.?|Court|Ct\.?)$"
)
_ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")
_WEBSITE_RE = re.compile(r"^(?:www\.|https?://)\S+$")
_BULLET_SPLIT_RE = re.compile(r"\s+[•◦▪■●–—‣·○◆▸►]\s+")
_BULLET_STRIP_RE = re.compile(r"^[•◦▪■●–—‣·○◆▸►]\s+")


def _is_bare_date_line(ln: str) -> bool:
    """A bare release-date line ("October 21, 2024") — the live
    extraction starts at the headline, so the date is chrome. The
    full-line anchor keeps a dated dateline sentence out (it
    carries a dash + prose after the date)."""
    return bool(_BARE_DATE_RE.match(ln.strip()))


def _is_salutation_line(ln: str) -> bool:
    """A shareholder-letter salutation ("Fellow shareholders,") —
    the live extraction starts at the bullets."""
    return bool(_SALUTATION_RE.match(ln.strip()))


def _is_role_line(ln: str) -> bool:
    """A bare contact role line ("Vice President, Investor
    Relations" / "Executive Vice President, Communications and
    External Affairs") — no digits, no bullet, short, and it names
    a role. A headline word ("Reports"/"Results"/...) excludes a
    headline that happens to name a role."""
    s = ln.strip()
    if not s or len(s.split()) > 8:
        return False
    if re.search(r"\d", s):
        return False
    if _BULLET_LEAD_RE.match(s):
        return False
    if any(w in s for w in _HEADLINE_WORDS):
        return False
    return any(k in s for k in _ROLE_KEYWORDS)


def _is_contact_line(ln: str) -> bool:
    """A contact-block line: an "Investors:"/"Media:" label, a name
    + phone line ("Andrew Hedberg (651) 250-2185"), a bare phone
    ("856-955-4163"), or a bare role line. Bullet-led lines are
    never contact lines."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if re.match(r"(?:Investors|Media)\s*:", s):
        return True
    if _PHONE_RE.search(s):
        return True
    return _is_role_line(s)


def _is_masthead_line(ln: str) -> bool:
    """A release-masthead line: a street address ("11011 Sunset
    Hills Road"), a city/state/ZIP line ("Reston, Virginia 20190
    News"), or a website ("www.gd.com"). The ZIP rule needs a short
    figure-free line (a bullet carrying a ZIP is content, and a
    figure-bearing line is never masthead)."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if _STREET_SUFFIX_RE.match(s):
        return True
    if _WEBSITE_RE.match(s):
        return True
    if _ZIP_RE.search(s) and len(s.split()) <= 8 and not re.search(r"[$%]", s):
        return True
    return False


def _strip_leading_chrome(lines: list[str]) -> list[str]:
    """Drop stored-leading chrome lines (bare date, salutation,
    contact block, masthead), in sequence, until the first line is
    content. Only the front is stripped — a contact block later in
    the text is content the gate must still account for."""
    out = list(lines)
    while out and (
        _is_bare_date_line(out[0])
        or _is_salutation_line(out[0])
        or _is_contact_line(out[0])
        or _is_masthead_line(out[0])
    ):
        out.pop(0)
    return out


def _align_headline(
    s_lines: list[str], l_lines: list[str]
) -> tuple[list[str], str | None]:
    """Align the stored first line(s) to the live headline. Returns
    the effective stored lines plus the relation, or None when no
    alignment exists. JOIN is tried before PREFIX: a two-line
    headline wrap ("... Financial Results;" / "Updates Guidance
    ...") is also a prefix of the live headline, but only JOIN
    consumes the continuation line — PREFIX alone would leave it
    for the loss check to (correctly) reject."""
    if not s_lines or not l_lines:
        return s_lines, None
    s, l = s_lines[0], l_lines[0]
    if s == l:
        return s_lines, "EQ"
    rel = first_line_relation(s_lines, l_lines)
    if rel in ("STORED-SUFFIX", "LIVE-SUFFIX"):
        return s_lines, rel
    if (
        len(s_lines) >= 2
        and len(s) >= 20
        and not _BULLET_LEAD_RE.match(s_lines[1])
        and norm(s_lines[0] + " " + s_lines[1]) == norm(l)
    ):
        return [l] + s_lines[2:], "JOIN"
    if len(s) >= 20 and l.startswith(s):
        return [l] + s_lines[1:], "PREFIX"
    if s in l_lines[1:3]:
        return s_lines, "OFFSET"
    return s_lines, None


def _split_flattened(s_lines: list[str], l_lines: list[str]) -> list[str]:
    """Seed-era single-line flattening (Corteva): one stored line
    holding the headline + bullets joined with " • ". Splits it
    into effective lines (headline + "• "-prefixed bullet parts),
    re-joining adjacent parts the live extraction fuses with a dash
    (a bullet whose text runs through the dateline into the lede;
    "Cash provided by operating activities – continuing operations
    ..."). Applies only when the split headline equals the live
    headline; the dash join is verified against the live lines, so
    a wrong split can only fail the loss check, never fabricate a
    match."""
    if len(s_lines) != 1:
        return s_lines
    parts = [p.strip() for p in _BULLET_SPLIT_RE.split(s_lines[0]) if p.strip()]
    if len(parts) < 3 or norm(parts[0]) != norm(l_lines[0]):
        return s_lines
    live_set = {norm(x) for x in l_lines}
    live_bare = {norm(_BULLET_STRIP_RE.sub("", x)) for x in l_lines}
    merged: list[str] = []
    i = 0
    while i < len(parts):
        if i + 1 < len(parts):
            joined = None
            for dash in (" – ", " — ", " - "):
                cand = parts[i] + dash + parts[i + 1]
                if norm(cand) in live_bare or norm("• " + cand) in live_set:
                    joined = cand
                    break
            if joined is not None:
                merged.append(joined)
                i += 2
                continue
        merged.append(parts[i])
        i += 1
    return [merged[0]] + ["• " + p for p in merged[1:]]


def sweep_gate_s4(stored: str, live: str) -> str | None:
    """Gate S4: gate S3 with the S4 entry condition (chrome strip +
    headline alignment + single-line split). Every other gate-S3
    condition is unchanged.

    Batch 260: two policing fixes. (1) The added-table scan strips
    leading chrome from the live lines too — the gate already strips
    it from stored, so a leading contact line whose phone number
    matches _is_lede_data_row (EIX: "Investor Relations: Sam Ramraj,
    (626) 302-2540") counted as live-only table material even though
    stored carries the same line. The strip is front-only, so a
    contact line added mid-text still trips added-table. (2) The
    fragment refusal is exempted when live's second line equals
    stored's second line post-alignment — a lowercase second line
    both sides share is a headline continuation (BRO: "including
    total revenues ..."), not a live-only fragment."""
    s_lines = non_empty(stored)
    l_lines = non_empty(live)
    s_lines = _split_flattened(s_lines, l_lines)
    s_lines = _strip_leading_chrome(s_lines)
    s_lines, relation = _align_headline(s_lines, l_lines)
    if relation is None:
        return "first-diff"
    live_set = set(l_lines)
    live_has_dateline = any(_is_dateline_sentence(x) for x in l_lines)
    s_datelines = [x for x in s_lines if _is_dateline_sentence(x)]
    if not live_has_dateline:
        s_datelines = []
    live_norm_set = {norm(x) for x in l_lines}
    if not all(norm(d) in live_norm_set for d in s_datelines):
        return "dateline-mismatch"
    for i, x in enumerate(s_lines):
        nxt = s_lines[i + 1] if i + 1 < len(s_lines) else ""
        if x not in live_set and not is_residue_s3(x, nxt, live_set):
            return "loss"
    lfrac = sum(1 for x in l_lines if is_residue(x)) / max(len(l_lines), 1)
    if lfrac >= 0.4 or has_dateline_table_shape(l_lines):
        return "live-table"
    s_set = set(s_lines)
    scan_lines = _strip_leading_chrome(l_lines)
    if any(hard_table(x) for x in scan_lines if x not in s_set):
        return "added-table"
    last = l_lines[-1] if l_lines else ""
    if last not in s_set and (
        is_residue(last) or last.rstrip().endswith(":")
    ):
        return "tail"
    if len(l_lines) > 1 and l_lines[1][:1].islower():
        if len(s_lines) > 1 and l_lines[1] == s_lines[1]:
            pass
        else:
            return "fragment"
    return None


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.press_release_highlights, q.cik "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "WHERE q.press_release_highlights IS NOT NULL "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    counts: dict[str, int] = {}
    repaired: list[str] = []
    skip_lists: dict[str, list[str]] = {}
    for t, pe, stored, cik in rows:
        key = f"{t}_{pe}"
        path = f"{CACHE}/{key}.html"
        if not os.path.exists(path):
            counts["SKIP-nocache"] = counts.get("SKIP-nocache", 0) + 1
            continue
        html = open(path, encoding="utf-8").read()
        live = extract_press_release_highlights(html)
        if live is None:
            counts["SKIP-live-none"] = counts.get("SKIP-live-none", 0) + 1
            continue
        if norm(stored) == norm(live):
            counts["B"] = counts.get("B", 0) + 1
        else:
            reason = sweep_gate_s4(stored, live)
            if reason is None:
                counts["S4"] = counts.get("S4", 0) + 1
                repaired.append(key)
                if not DRY:
                    con.execute(
                        "UPDATE quarterly_financials "
                        "SET press_release_highlights = ? "
                        "WHERE cik = ? AND period_end = ?",
                        (live, cik, pe),
                    )
                print(f"    S4 {key} {len(stored)}->{len(live)}")
            else:
                rk = f"SKIP-{reason}"
                counts[rk] = counts.get(rk, 0) + 1
                skip_lists.setdefault(rk, []).append(key)
    if not DRY:
        con.commit()
    print(f"\nDRY_RUN={DRY} counts: {counts}")
    print(f"highlights repaired (S4): {len(repaired)}")
    for rk in sorted(skip_lists):
        keys = skip_lists[rk]
        if rk in ("SKIP-first-diff", "SKIP-loss"):
            print(f"  {rk} ({len(keys)}): {', '.join(keys)}")
        else:
            print(f"  {rk} ({len(keys)})")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
