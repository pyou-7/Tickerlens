"""Batch 192 repair: replace the stored highlights rows the batch-192
extractor improves, under the batch-183 gates.

Targets (3 stored rows): the APD quarters whose live extraction changes
under batch 192 and that have stored rows. The full-cache blast (1,699
exhibits) shows 4 diffs, 1,695 byte-identical, 0 content losses — all
footnote-definition removals plus the freed-budget prose they let in:
APD 2023-12-31 ("#Earnings ..." out, the "For the quarter, on a
non-GAAP basis ..." paragraph in), APD 2025-06-30 ("#Per share ..." out,
the "Third quarter sales ..." paragraph in), APD 2026-03-31 ("# Per
share ..." and "* Certain results ..." out), AXP 2023-12-31 ("# -
Denotes ..." out, the "Consolidated expenses ..." paragraph in). APD
2023-12-31 and AXP 2023-12-31 have no stored rows, so they need no
repair — live extraction serves them correctly already. APD 2024-12-31's
stored row (3,486 chars) is far fuller than its live extraction (310
chars: the "Q1 FY25 (comparisons versus prior year):" financial bullets
are not picked — a section-pick gap, carried forward), so the gates are
expected to skip it on preservation. APD 2026-03-31's live text ends on
"-more-" + the next-section heading, so the gates are expected to skip
it on the "-more-" residue — that marker is its own batch.

No gate change for batch 192: the "#" footnote lines are defect lines
via _opens_footnote_def (the new _FOOTNOTE_DEF_RE shape), and the "*"
line is a defect line via _is_lede_table_line (_LEDE_FOOTNOTE_GLYPH_RE
matches spaced "*"). The freed-budget paragraphs are prose, not
residue — no new residue marker trips on them. Note the stored APD
2026-03-31 tail line "Fiscal…" is NOT excluded by any gate: it ends in
"…" so it reads as terminated and fails the table-line predicate — the
repair skips that quarter on preservation ("live drops stored line:
'Fiscal…'") as well as on the "-more-" residue, both gate-correct. The
"-more-" batch will need a truncated-tail exemption for the "Fiscal…"
line (a truncated prefix of the live full heading) before that row can
be repaired.

Live is re-fetched inside this script, so no gate rests on blast output
alone; where a blast file exists the live text must also be
byte-identical to it. Run against the batch-192 extractor.

Run dry:  .venv/bin/python scripts/batch192_repair.py
Run write: .venv/bin/python scripts/batch192_repair.py --write

Gates (adapted from batch 157/159/161/162/164/165/166/167/168/170/176/177/178/179/182/183):
  - live extraction succeeds and its source label equals the stored one
  - live >= 200 chars and differs from stored
  - headline: live keeps the stored headline verbatim — batch 174: the
    stored headline is the first REAL stored paragraph, skipping leading
    residue paragraphs (date line, contact block, salutation), since
    AWK/PHM stored rows open with the contact block, not the headline.
    Batch 179: the live headline may also be the stored headline joined
    with its immediate next paragraph (CPB's wrapped headline, split
    across two paragraphs by the old extractor) — accepted only when
    that next paragraph is itself real content, not a defect line.
  - stored-core preservation, line-level: every stored line that is
    NOT a defect line (footnote definition, bare role line, symbol
    legend, "Key Points:" heading, batch-177 colon heading /
    table-header / long-caps heading, batch-178 title line /
    year-caps section heading / lede table line, batch-179 contact
    line (email / URL / PR|IR Contact: lead) / lede summary sub-head)
    must survive in live (first-60-char check on the flattened text).
    The defect lines are the repair itself — they are excluded, exactly
    as batch 169 excluded the salutation/date lines. Plus the batch-170
    paragraph gate. Batch 174: contact-block lines (bare phone,
    "Investors:"/"Media:" lead, long role line) are defect lines too —
    the live extractor already drops them, so the gates must not
    mistake them for content.
  - live carries no salutation, no conference-call notice, and no
    blocking table/rounding/footnote residue (same residue check as
    batch 170), plus the batch-177 exposed-leak guards: a title line
    (_is_trailing_heading — the freed budget lets the loop reach the
    exhibit's own title, e.g. COF's "Capital One ... Earnings"), a
    $-carrying table row up to 120 chars (ARCC/COF recon rows sit
    above the extractor's 80-char $-figures cap), and a spaced-decimal
    $ row ("$ .44" — EL). Batch 181: the bare-numbered-footnote cap
    rose 500 -> 1000, so the two long footnotes the batch-180 gates
    noted as surviving tails (MCO 2024-12-31 fn3, AXP 2025-06-30 fn1)
    are now dropped by the extractor and the note is obsolete; a
    footnote above 1000 chars still survives as a tail and, being a
    terminated sentence, does not block. Batch 179: a bullet wrap
    continuation (the line after an unterminated bullet line, e.g.
    GEV's "125 GW by year-end 2026") is not residue — the residue
    scan skips it.
  - Batch 181: the single-value guidance rows, the table headers
    (EBITA/EPS, "GAAP Revenue"), and the lone $ cell are defect
    lines via _is_lede_table_line (Fixes 2, 5, 7), so they are
    excluded from stored-core preservation exactly like the
    batch-178 table lines.
"""
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "src")

from sqlalchemy import select

from tickerlens.data.filings import (
    _ADMIN_LINE_RE,
    _BULLET_LEAD_RE,
    _LEDE_BARE_UNITS_DOLLARS_RE,
    _LEDE_HEADLINE_VERB_RE,
    _LEDE_SYMBOL_LEGEND_RE,
    _ROLE_ANCHOR_WORDS,
    _ROLE_TITLE_WORDS,
    _is_bare_period_fragment,
    _is_bare_role_line,
    _opens_footnote_def,
    _CONFERENCE_CALL_NOTICE_RE,
    _CONTACT_LINE_RE,
    _DATELINE_LEAD_RE,
    _FOOTNOTE_DEF_RE,
    _HEADING_SMALL_WORDS,
    _LEDE_FIGURE_RE,
    _LEDE_FOOTNOTE_NUM_RE,
    _LEDE_FOOTNOTE_RE,
    _RULE_LINE_RE,
    _TABLE_INTRO_RE,
    _TABLE_UNITS_RE,
    _TABLE_WORD_UNITS_RE,
    _TRAILING_TABLE_INTRO_RE,
    _is_lede_call_announcement,
    _is_lede_data_row,
    _is_lede_dollar_range_statement,
    _is_lede_date_header,
    _is_lede_period_header,
    _is_lede_recon_heading,
    _is_lede_recon_row,
    _is_lede_report_pointer,
    _is_lede_segment_heading,
    _is_lede_split_units_continuation,
    _is_lede_summary_results_title,
    _is_lede_table_line,
    _is_lede_colon_heading,
    _is_lede_heading_fragment,
    _is_lede_table_header,
    _is_lede_title_line,
    _is_lede_webcast_continuation,
    _is_recon_heading_wrap,
    _is_sentence_terminated,
    _is_trailing_heading,
    _looks_like_table_cell,
)
from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.services.financials import FinancialsService
from tickerlens.services.ir_download import discover_earnings_filings

WRITE = "--write" in sys.argv
ONLY_TICKERS = None
for _arg in sys.argv[1:]:
    if _arg.startswith("--tickers="):
        ONLY_TICKERS = set(_arg.split("=", 1)[1].split(","))

TARGETS = [
    # The 3 exhibits whose live changes under batch 192 (blast192:
    # 4 diffs, 0 content losses) and that have stored rows. The gates
    # decide; do not override them.
    ("APD", "2024-12-31"),
    ("APD", "2025-06-30"),
    ("APD", "2026-03-31"),
]
# Live must open with a bullet (NFLX: no headline) or keep the stored
# headline verbatim (AXON/SKYD/COIN).
BULLET_OPENERS = set()  # every batch-173 target keeps its headline

PROSE_OPENER = {}

BLAST_DIR = Path("/home/hatch/workspace/goals/tickerlens-app-build/hidden_files/blast192/new")  # batch-192 blast (post-fix extractor, 1,699 exhibits; persistent — /tmp is wiped)

RESIDUE_MARKERS = [
    "Change % Change",
    "Three Months Ended",
    "2025 2026 % Change",
    "(dollars in millions",
    "Current Compared to Previous Outlook",
    "NM = not meaningful",
    "Consolidated Highlights",
    "Figures have been rounded",
    "sum precisely due to rounding",
    "Based on the closing price",
    "Class A common stock",
    "Monthly Transacting User",
    "non-GAAP financial measure",
    "is defined as a consumer who",
    "Adjusted EBITDA is a non-GAAP",
    "These losses were",
    "after reflecting the tax impact",
    "pre-tax losses on our crypto",
    "USDC (net of",
    "pledged as collateral",
    "For additional financial information",
    # Batch-169 defect markers: the salutation must not survive.
    # (Batch 170: the live text now also carries the full "◦" sub-bullet
    # list — those lines are bullets, never residue.)
    "Fellow shareholders",
    "Fellow Shareholders",
    "Dear Shareholders",
    # Batch-182 defect markers: a recon heading, a report pointer or
    # a "See information" pointer surviving in live is not clean.
    "Reconciliation of Commissions",
    "Operating Earnings Reconciliation",
    "Reconciliation of GAAP to Non-GAAP",
    "See information regarding non-GAAP",
    "is contained in the CSX",
    "should be read in conjunction with",
    # Batch-188 defect markers: the two AJG 2026 table header lines,
    # the ED attachment pointer, the AJG recon-table pointer prefix,
    # and the safe-harbor intro phrase. The pointer prefix is the
    # "See ..." form only — the "Investors ... should read carefully
    # the section entitled ... beginning on page 9" cross-reference
    # is real prose and must not trip the gate. Verified against the
    # blast188d new extracts: none of the 1 target carries any of
    # these in live.
    "Summary of Financial Results",
    "Net Earnings (Loss) EBITDAC",
    "See Attachment",
    "See \u201cInformation Regarding Non-GAAP Measures\u201d beginning",
    "forward-looking statements",
]

# Batch 183: the "non-GAAP financial measure" marker only counts as a
# footnote definition ("Adjusted EBITDA is a non-GAAP financial
# measure ..."), not as a phrase inside real prose (see the marker
# loop in live_residue_lines).
_NON_GAAP_DEF_RE = re.compile(
    r"\b(?:is|are)\s+(?:a\s+)?non-GAAP financial measures?\b"
)


def norm(s: str) -> str:
    """Whitespace + punctuation + footnote-spacing normalization, applied
    identically to stored and live text before comparison. Batch 170:
    also strips the space after "(" and before ")" — the stored rows
    were flattened with spaced footnote markers ("( Adolescence 1 )")
    while the current flattening attaches them ("(Adolescence1)"), so
    without this the preservation gate mistakes a flattening artifact
    for dropped content (NFLX 2025-03-31). Same class as the existing
    letter-digit join."""
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"([A-Za-z])\s+(\d)(?![0-9])", r"\1\2", s)
    # Batch 182: also attach the trademark marks — the stored AXP
    # 2026-03-31 row flattens "Experiences ™" (spaced) while the
    # current flattening attaches it ("Experiences™"), and the
    # 60-char preservation check trips on exactly that one character.
    # Same class as the batch-170 letter-digit join.
    s = re.sub(r"\s+([™®©])", r"\1", s)
    return s


def _is_figure_dense_unterminated(ln: str) -> bool:
    """$-less percent/data rows: unterminated, 2+ figures, >=40% tokens."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s):
        return False
    if _is_sentence_terminated(s):
        return False
    figs = _LEDE_FIGURE_RE.findall(s)
    toks = s.split()
    return len(figs) >= 2 and len(figs) / max(len(toks), 1) >= 0.4


def _dollar_row(ln: str) -> bool:
    """Unterminated non-bullet line carrying >=2 $ figures (a guidance /
    table row whose label words keep it under the 40% density bar).
    Batch 183: a guidance-range STATEMENT is content, never a row —
    it carries 2 $ figures and is short, so without the exemption the
    residue scan would refuse every repair that serves one."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s) or _is_sentence_terminated(s):
        return False
    if _is_lede_dollar_range_statement(s):
        return False
    return len(re.findall(r"\$\s?[\d(]", s)) >= 2 and len(s) <= 80


def _is_subheadline_zone_line(ln: str) -> bool:
    """True for a line that continues the sub-headline run after the
    headline: short (<=10 words), unterminated, capital-led (or a small
    word / number), never bullet-led. Batch 183, repair-script-only:
    FDX's sub-headlines run several lines deep ("Updates Full-Year
    Fiscal 2024 Earnings Outlook and" / "Confirms Full-Year Fiscal
    2024 Adjusted Earnings Outlook"), and a wrapped first line ends
    in "and", so the heading-shape test (which needs a section end
    word) ends the zone too early. Figures do NOT end the zone: a
    metric sub-headline ("EARNINGS PER SHARE OF $3.64 INCREASED 9%",
    "Completed $500 Million Share Repurchases During Quarter") is
    still a sub-headline, and the guidance line after it is too. What
    ends the zone is sentence case: a results fragment ("Net sales
    of $19.9 billion decreased 1 percent ...", "Operating profit of
    $3.4 billion essentially matched year-ago") carries lowercase
    words, as does every dateline, prose paragraph and table row —
    while a metric sub-headline is all-caps or capital-led throughout.
    A table row of an all-caps label plus $ values would also qualify,
    but rows sit past the dateline, where the zone has already ended
    on the terminated dateline."""
    s = ln.strip()
    if not s or _BULLET_LEAD_RE.match(s) or s[:1] in "▪■·○◦◾":
        return False
    if _is_sentence_terminated(s):
        return False
    words = s.split()
    if not words or len(words) > 10:
        return False
    for w in words:
        clean = w.strip(",;:")
        if not clean:
            return False
        # A $ figure ("$3.64") starts with "$", not a digit — strip
        # the currency mark before the digit test.
        stripped = clean.lstrip("$")
        if stripped and stripped[0].isdigit():
            continue
        if clean in _HEADING_SMALL_WORDS:
            continue
        if clean[0].isupper():
            continue
        return False
    return True


def live_residue_lines(live: str) -> tuple[list[str], list[str]]:
    """(blocking residue lines, tolerated table-intro lines)"""
    raw = [ln.strip() for ln in live.splitlines()]
    lines = [ln for ln in raw if ln]
    # Filtered-index -> raw-index, so a wrap continuation can be told
    # from the raw line directly above it even across blank lines.
    raw_pos = [i for i, ln in enumerate(raw) if ln]
    blocking, tolerated = [], []
    # Batch 183: the sub-headline zone — the prefix of consecutive
    # sub-headline lines right after the headline (a zone line, or a
    # non-bullet range statement). A heading inside this prefix
    # introduces the body; a heading past it is a section heading or
    # an exhibit title. Bullet-led range lines do NOT continue the
    # zone (a ◦ guidance bullet is content, so a heading after it is
    # mid-body).
    _zone_end = 1
    while _zone_end < len(lines) and (
        _is_subheadline_zone_line(lines[_zone_end])
        or (
            _is_lede_dollar_range_statement(lines[_zone_end])
            and not _BULLET_LEAD_RE.match(lines[_zone_end])
            and lines[_zone_end][:1] not in "▪■·○◦◾"
        )
    ):
        _zone_end += 1
    for idx, s in enumerate(lines):
        if idx == 0:
            continue  # the headline: gated verbatim against the stored
            # headline above (or bullet-opener for NFLX); a quarter
            # title scores as a table line — the residue scan covers
            # the body. Batch 167.
        if _BULLET_LEAD_RE.match(s) or s[:1] in "▪■·○":
            continue
        # Batch 179: a bullet's wrapped continuation ("125 GW by
        # year-end 2026" under GEV's "...reaching at least" bullet) is
        # not a standalone line — the figure-density scan below would
        # otherwise flag it as a data row. The previous RAW line must
        # be an unterminated bullet line (a blank line in between means
        # a new paragraph, not a wrap).
        _prev_raw = raw[raw_pos[idx] - 1] if raw_pos[idx] > 0 else ""
        if _BULLET_LEAD_RE.match(_prev_raw) and not _is_sentence_terminated(_prev_raw):
            continue
        if _TRAILING_TABLE_INTRO_RE.match(s):
            tolerated.append(s)
            continue
        if _RULE_LINE_RE.match(s):
            blocking.append(s)
            continue
        if _CONFERENCE_CALL_NOTICE_RE.search(s):
            blocking.append(s)
            continue
        # Batch 182: a recon heading, a report pointer, a split call
        # announcement or its webcast continuation, a segment heading,
        # a split-units continuation, a bare units line or a recon
        # heading wrap surviving in live is not a clean repair target
        # — the freed budget lets the loop reach lines the old
        # extraction never served, exactly as batch 177's guards.
        if (
            _is_lede_recon_heading(s)
            or _is_lede_report_pointer(s)
            or _is_lede_call_announcement(s)
            or _is_lede_webcast_continuation(s)
            or _is_lede_segment_heading(s)
            or _is_lede_split_units_continuation(s)
            or _LEDE_BARE_UNITS_DOLLARS_RE.match(s)
            or _is_recon_heading_wrap(s)
        ):
            blocking.append(s)
            continue
        # Batch 177 exposed-leak guards (repair-script-only): the
        # freed lede budget lets the loop reach lines the old
        # extraction never served — an exhibit title line ("Capital
        # One ... Earnings", "2025 First Quarter Results"), a
        # $-carrying recon-table row above the extractor's 80-char
        # $-figures cap (ARCC/COF, 83-84 chars), and a spaced-decimal
        # $ row ("$ .44" — EL). A live text carrying one is not a
        # clean repair target, even when the stored row shares the
        # wart: the repair must not write new residue.
        # Batch 183: the title check is position-aware — a
        # heading-shaped line in the SUB-HEADLINE ZONE (the prefix of
        # consecutive sub-headline lines right after the headline: no
        # content yet) with a following line introduces the body
        # (GPC's "Updates Select Elements of 2026 Outlook", AWK's
        # "AFFIRMS ... GUIDANCE"), so it is not residue. Anywhere else it still blocks: a
        # section heading mid-body ("Financial Targets", "Company
        # Highlights", DLR's "Financial Results" after its bullets,
        # GIS's "Fourth Quarter Highlights" after its results
        # fragments), a repeated headline (Danaher's, Edison's,
        # American's "X Reports ... Results" — headline-shaped even
        # in the sub-headline zone, since the tagline was picked as
        # the headline and the real headline rides as a body line),
        # or the exhibit title served at the end of the lede (COF's
        # "Capital One ... Earnings", the last line). The zone is a
        # PREFIX, not "before the first terminated line": AWK's and
        # GIS's fragment-ledes carry no terminated line at all, so a
        # terminated-after requirement wrongly kept flagging AWK's
        # AFFIRMS sub-headlines — and a terminated-before requirement
        # wrongly exempted GIS's heading, which follows four results
        # fragments. The first version of this rule only required
        # terminated prose AFTER the line, which wrongly exempted
        # every mid-body section heading.
        _before_body = idx < _zone_end
        _has_following = idx + 1 < len(lines)
        _is_repeat_headline = norm(s) == norm(lines[0]) or (
            re.search(r"\breports\b", s, re.IGNORECASE)
            and s.rstrip().lower().endswith("results")
        )
        if _is_trailing_heading(s) and (
            not _before_body or not _has_following or _is_repeat_headline
        ):
            blocking.append(s)
            continue
        if (
            not _is_sentence_terminated(s)
            and len(s) <= 120
            and not _is_lede_dollar_range_statement(s)
            and len(re.findall(r"\$\s?[\d(]", s)) >= 2
        ):
            blocking.append(s)
            continue
        if re.search(r"\$\s+\.\d", s):
            blocking.append(s)
            continue
        if (
            _is_lede_period_header(s)
            or _is_lede_date_header(s)
            or _TABLE_UNITS_RE.match(s)
            or _TABLE_WORD_UNITS_RE.match(s)
            or _is_lede_data_row(s)
            or _is_lede_recon_row(s)
            or _LEDE_FOOTNOTE_NUM_RE.match(s)
            or _is_figure_dense_unterminated(s)
            or _dollar_row(s)
        ):
            blocking.append(s)
            continue
        for marker in RESIDUE_MARKERS:
            if marker not in s:
                continue
            if (
                marker == "non-GAAP financial measure"
                and not _NON_GAAP_DEF_RE.search(s)
            ):
                # Batch 183: the phrase also appears inside real prose
                # ("...related to non-GAAP financial measures,
                # including adjustments..." — COR; "...adjusted in the
                # non-GAAP financial measures discussed below" — APD).
                # Only a definition ("Adjusted EBITDA is a non-GAAP
                # financial measure ...") is residue.
                continue
            blocking.append(s)
            break
        else:
            if _is_lede_table_line(s) or _looks_like_table_cell(s):
                nxt = lines[idx + 1] if idx + 1 < len(lines) else ""
                nxt2 = lines[idx + 2] if idx + 2 < len(lines) else ""
                follows_content = (
                    _BULLET_LEAD_RE.match(nxt)
                    or _is_sentence_terminated(nxt)
                    or _BULLET_LEAD_RE.match(nxt2)
                    or _is_sentence_terminated(nxt2)
                )
                if not follows_content:
                    blocking.append(s)
    return blocking, tolerated


def salutation_lines(live: str) -> list[str]:
    """Standalone salutation lines that must never survive in live text."""
    out = []
    for ln in live.splitlines():
        s = ln.strip()
        if s.lower() in ("fellow", "dear", "shareholders,"):
            out.append(s)
        elif "fellow shareholders" in s.lower():
            out.append(s)
    return out


_DATE_PARA_RE = re.compile(r"^[A-Z][a-z]+ \d{1,2}, \d{4}$")


def _core_key(s: str) -> str:
    """Paragraph key for the preservation check: bullet marker and
    whitespace stripped, so "• In 2024 ..." (stored) matches
    "•In 2024 ..." (live)."""
    s = re.sub(r"^[•\-*·◦▪■○]\s*", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()


def stored_core_preserved(
    stored: str, live: str, live_headline: str = ""
) -> str | None:
    """First stored paragraph whose core does not survive in live, or
    None when the live text preserves every stored paragraph.

    The salutation and the date line are the defect, not content — they
    are excluded. Everything else (headline, bullets, prose) must
    survive: a repair that trades real highlights for a two-word
    greeting removal is a bad trade. Batch 170 fixes the truncation
    this gate caught: the leading-bullet block now treats "◦" as a
    bullet start, so the full list is served and the stored bullets
    all survive.
    """
    live_flat = norm(live)
    paras = [p.strip() for p in stored.split("\n\n")]
    _first_real = _first_real_index(paras, live_headline)
    for p_idx, p in enumerate(paras):
        if not p:
            continue
        if _DATE_PARA_RE.match(p):
            continue
        if p.rstrip(",.").lower() in _SALUTATIONS:
            continue
        _prev_para = paras[p_idx - 1] if p_idx > 0 else ""
        _nxt_para = paras[p_idx + 1] if p_idx + 1 < len(paras) else ""
        if _is_summary_subhead_at(paras, p_idx, _first_real):
            # Batch 179: the GEV lede summary — the paragraph right
            # after the real headline, before the "Highlights:" colon
            # heading — is the repair itself, not content.
            continue
        if _is_defect_line(p, _prev_para, _nxt_para):
            # Batch 173: a single-line defect paragraph ("Key Points:",
            # a bare role line) is the repair itself, not content —
            # the batch-170 gate has no defect exclusion, so without
            # this every DIS/MCO row trips on its own defect line.
            continue
        key = _core_key(p)
        if not key:
            continue
        if norm(key)[:60] not in live_flat:
            return p[:60]
    return None


# Batch 174 gate extension — contact-block lines. Some stored rows open
# with the release's contact block instead of the headline (American
# Water: "Vice President, Investor Relations" / a 7-word role line /
# a bare phone number; PulteGroup: "Investors: Jim Zeumer" + phone).
# The live extractor already skips the contact block (its headline loop
# drops _CONTACT_LINE_RE / _ADMIN_LINE_RE lines), so the repair must
# treat those lines as droppable residue, exactly as batch 169 treats
# salutations. Three shapes, all attested in the AWK/PHM cohort:
_CONTACT_LEAD_RE = re.compile(r"^(Investors|Media):\s", re.IGNORECASE)
_PHONE_ONLY_RE = re.compile(r"^(\+\d{1,3}[-. ]?)?(\(\d{3}\)\s*|\d{3}[-. ])\d{3}[-. ]\d{4}$")
# _ROLE_TITLE_WORDS caps at 6 words and lacks the comms vocabulary, so
# "Executive Vice President, Communications and External Affairs"
# (7 words) is not a bare role line — the relaxed form below adds the
# three missing words and the word-count headroom, keeping the anchor
# requirement and the no-terminal-period shape (a role line never ends
# a sentence). Repair-script-only: the extractor is unchanged.
_CONTACT_ROLE_EXTRA = frozenset({"communications", "external", "affairs"})


def _is_contact_block_line(ln: str) -> bool:
    """True for a contact-block line: a bare phone number, an
    "Investors:"/"Media:" lead, or a (possibly long) bare role line.
    Batch 179: also any line the extractor's own _CONTACT_LINE_RE
    matches — AIG's "www.aig.com Quentin McMillan (Investors):
    quentin.mcmillan@aig.com" (email + URL) and CMG's "PR Contact:
    Laurie Schalow" / "IR Contact: Cindy Olsen, CFA" (the batch-179
    extractor fix). The extractor already drops these from live, so
    the gates must not mistake them for content."""
    s = ln.strip()
    if not s:
        return False
    if _CONTACT_LINE_RE.search(s):
        return True
    if _PHONE_ONLY_RE.match(s):
        return True
    if _CONTACT_LEAD_RE.match(s):
        return True
    if s.endswith("."):
        return False
    words = [w.strip(",.").lower() for w in s.split()]
    if not 2 <= len(words) <= 10:
        return False
    vocab = _ROLE_TITLE_WORDS | _CONTACT_ROLE_EXTRA
    return all(w in vocab for w in words) and any(
        w in _ROLE_ANCHOR_WORDS for w in words
    )


def _stored_real_headline(
    stored: str, live_headline: str = ""
) -> tuple[str, str]:
    """First stored paragraph that is not itself residue (date line,
    salutation, defect line, contact-block line) — the release's real
    headline, which the live headline must match verbatim — plus the
    next paragraph, for the wrapped-headline join (batch 179: CPB's
    headline is split across two paragraphs by the old extractor).
    Falls back to the first paragraph when every paragraph is residue."""
    paras = [p.strip() for p in stored.split("\n\n") if p.strip()]
    _first_real = _first_real_index(paras, live_headline)
    if _first_real is not None:
        _nxt = (
            paras[_first_real + 1]
            if _first_real + 1 < len(paras)
            else ""
        )
        return norm(paras[_first_real]), norm(_nxt)
    first = paras[0] if paras else ""
    return norm(first), ""


def _is_year_caps_section_heading(ln: str) -> bool:
    """Year-carrying all-caps section heading (batch 178, repair-
    script-only): ARCC's "JUNE 30, 2025 FINANCIAL RESULTS" and EL's
    "FISCAL 2025 THIRD QUARTER SELECT FINANCIAL RESULTS
    (unaudited)1,2" — 5-8 words, all caps, carrying digits (the year),
    no headline verb, no $/%. Parentheticals are stripped before the
    caps test (EL's "(unaudited)1,2" is lowercase and would otherwise
    fail it). The live extractor drops these headings, so the
    preservation gates must not mistake them for content. A real
    highlight never looks like this."""
    s = ln.strip()
    if not s or "$" in s or "%" in s:
        return False
    if not re.search(r"\d", s):
        return False
    s = re.sub(r"\([^)]*\)", "", s).strip()
    words = s.split()
    if not 5 <= len(words) <= 8:
        return False
    if s != s.upper():
        return False
    if _LEDE_HEADLINE_VERB_RE.search(s):
        return False
    return True


_SALUTATIONS = frozenset(
    {
        "fellow shareholders",
        "fellow",
        "shareholders",
        "dear shareholders",
        "fellow affirm shareholders",
    }
)


def _first_real_index(items: list[str], live_headline: str = "") -> int | None:
    """Index of the first paragraph/line that is real content — not a
    date line, salutation, defect line or contact-block line. The
    defect check is context-aware (prev/next neighbours). The exact
    live-headline anchor (batch 179 round 3): a paragraph that joins
    with its neighbour into the live headline IS the headline's first
    half, even when the fragment predicate calls it a heading
    fragment — the round-2 heuristic (fragment half + year in the
    join) falsely exempted CHD's "UPDATES FULL YEAR OUTLOOK", whose
    neighbour merely happened to be the year-carrying section title
    "2025 First Quarter Results". Exact equality with the live
    headline cannot misfire that way."""
    for i, it in enumerate(items):
        if _DATE_PARA_RE.match(it):
            continue
        if it.rstrip(",.").lower() in _SALUTATIONS:
            continue
        prev = items[i - 1] if i > 0 else ""
        nxt = items[i + 1] if i + 1 < len(items) else ""
        if live_headline and (
            norm(it) == live_headline
            or (nxt and norm(it + " " + nxt) == live_headline)
        ):
            return i
        if _is_defect_line(it, prev, nxt) or _is_contact_block_line(it):
            continue
        return i
    return None


def _is_summary_subhead_at(items: list[str], idx: int, first_real: int | None) -> bool:
    """True for a lede summary sub-headline (batch 179, repair-script-
    only): GEV's release summary line ("Solid 3Q'24 results with
    double-digit orders and continued revenue growth, along with
    substantial cash flow") sits immediately after the real headline
    and before the "X Quarter YYYY Highlights:" colon heading — the
    heading block the live extractor drops as a whole, serving the
    same facts in the bullets, the CEO quote and the dateline prose.
    Position is the discriminator the first version lacked: it matched
    any unterminated figure-free line before a colon heading, which
    included AIG's real headline ("AIG Reports Outstanding Fourth
    Quarter and Full Year 2024 Results" sits before "Fourth Quarter
    2024:"). A summary is, by construction, the paragraph right after
    the first real paragraph; anything else is preserved as content.
    Shape: unterminated, $-free, %-free, 6-25 words, next item a
    colon-heading defect line."""
    if first_real is None or idx != first_real + 1:
        return False
    s = items[idx]
    nxt = items[idx + 1] if idx + 1 < len(items) else ""
    if not s or not nxt:
        return False
    if _BULLET_LEAD_RE.match(s):
        return False
    if _is_sentence_terminated(s):
        return False
    if "$" in s or "%" in s:
        return False
    if not 6 <= len(s.split()) <= 25:
        return False
    return _is_lede_colon_heading(nxt)


# Batch 186: the orphaned flattened-table labels the batch-186
# extractor drops (AJG's summary-table column headers flatten one
# cell per line — "3rd Q 25" / "9 Mths 25" — and the labels below
# them survived as the last lede lines). As standalone stored
# paragraphs/lines they are the repair itself, not content — excluded
# from preservation exactly as batch 173 excluded salutations.
# "Risk Management, as adjusted *" is the third label the blast
# drops (table-mode residue once the first label enters the mode).
_BATCH186_ORPHAN_LABELS = frozenset(
    {
        "Net losses (gains) on divestitures",
        "Net (gains) losses on divestitures",
        "Net (gains) on divestitures",
        "Effective income tax rate impact",
        "Risk Management, as adjusted *",
    }
)

# Batch 188: orphaned summary-table header fragments the extractor's
# own _is_lede_table_header cannot classify (precedent: batch 186).
# "Percentage Inc/(Dec) Nine Months Ended" (AXP Q3 2024) carries no
# metric token and no qualifier/repeat, so the column-header predicate
# never fires on it; "Change % Change" (CCI Q4 2024) is vetoed by the
# predicate's % guard. Both are unambiguously column headers of the
# summary tables — the live extractor drops them — and the stored rows
# carry them as paragraphs. Exact-match only: no real prose is ever
# exactly one of these lines.
_BATCH188_TABLE_HEADER_FRAGMENTS = frozenset(
    {
        "Percentage Inc/(Dec) Nine Months Ended",
        "Change % Change",
    }
)


def _is_defect_line(ln: str, prev: str = "", nxt: str = "") -> bool:
    """A stored line the repair itself removes: a footnote-definition
    line (pointer or bare-numbered), a bare quote-attribution role
    line, a symbol legend, or the "Key Points:" heading. Batch 173.
    Batch 174 adds contact-block lines (phone, "Investors:" lead,
    long role line) — the live extractor already drops them, so the
    preservation gates must not mistake them for content. Batch 177
    adds the heading / table-header classes: a colon-ended list-intro
    or section heading, a summary-table column-header line, and a
    long all-caps table-title fragment. Batch 178 adds the title-line
    class (the extractor's own _is_lede_title_line — COF's "Capital
    One ... Earnings"), the year-carrying all-caps section heading,
    and any lede table line: the stored COF rows' residue paragraphs
    (the "(Dollars in millions, except per share data) Pre-Tax" units
    paragraph and the "Discover integration expenses $ 110 $ 0.22"
    recon row) are table lines, and the paragraph gate has no
    table-line exclusion of its own — without this the gate trips on
    the repair itself. Bullets and prose are never table lines, so
    no real content is excluded. Batch 186 adds the orphaned AJG
    flattened-table labels (see _BATCH186_ORPHAN_LABELS): the blast
    drops them from the live extraction, and any stored row carrying
    them is repaired by dropping them. Batch 188 adds the AJG
    summary-results table title: the stored AJG rows carry it and
    the live text drops it."""
    s = ln.strip()
    if not s:
        return False
    if s in _BATCH186_ORPHAN_LABELS:
        return True
    if s in _BATCH188_TABLE_HEADER_FRAGMENTS:
        return True
    # Batch 188: a release-admin line ("CON EDISON REPORTS 2025 FIRST
    # QUARTER EARNINGS page 2" — the page-2 header the old extractor
    # collected as content; the batch-188 admin fix drops it) is
    # never content. _ADMIN_LINE_RE also covers the "For Immediate
    # Release" / EX-99 / EXHIBIT banners.
    if _ADMIN_LINE_RE.match(s):
        return True
    if _is_lede_colon_heading(s):
        return True
    if _is_lede_table_header(s):
        return True
    # Batch 188: the AJG summary-results table title ("Summary of
    # Financial Results - First Quarter") is the repair itself — the
    # stored AJG rows carry it as a paragraph and the batch-188 live
    # text drops it. No older predicate catches it (not a table
    # header, title line or table line — verified line by line).
    if _is_lede_summary_results_title(s):
        return True
    # Batch 182: the recon heading, the report pointer, the split call
    # announcement and its webcast continuation, the segment heading
    # and the recon-heading wrap are the repair itself — no older
    # predicate catches them (verified line by line on the CSX/AXP
    # stored rows: the recon heading is not a table line, title line
    # or heading fragment; the pointers are long terminated sentences).
    if _is_lede_recon_heading(s):
        return True
    if _is_lede_report_pointer(s):
        return True
    if _is_lede_call_announcement(s):
        return True
    if _is_lede_webcast_continuation(s):
        return True
    if _is_lede_segment_heading(s):
        return True
    if _is_recon_heading_wrap(s):
        return True
    if _is_lede_heading_fragment(s):
        return True
    if _is_lede_title_line(s):
        return True
    if _is_year_caps_section_heading(s):
        return True
    if _is_lede_table_line(s):
        return True
    if _opens_footnote_def(s, ""):
        return True
    if _is_bare_role_line(s):
        return True
    if _is_contact_block_line(s):
        return True
    if _is_bare_period_fragment(s):
        # Batch 174: a bare period-fragment line ("Three Months",
        # "Six Months") is table-header residue — the live extractor
        # now breaks the bullet block on it, so the stored fragment
        # must not trip preservation. ("Ended"/"Year Ended" are
        # already excluded via _is_lede_table_line in the gates below.)
        return True
    if _LEDE_SYMBOL_LEGEND_RE.match(s):
        return True
    if s.rstrip().lower() in ("key points:", "key points"):
        return True
    return False


def stored_lines_preserved(
    stored: str, live: str, live_headline: str = ""
) -> str | None:
    """First stored non-defect line whose core does not survive in
    live, or None. Line-level strengthening of the batch-170 paragraph
    gate: these stored rows are one big body paragraph (lines joined
    with single newlines), so the paragraph gate only checks the
    body's first 60 chars — a repair that dropped a middle bullet
    would pass it. Every non-defect line's first 60 chars must appear
    in the flattened live text. Defect lines are excluded (they are
    the repair); the date line and salutations are excluded as before.
    """
    live_flat = norm(live)
    _lines = [ln.strip() for ln in stored.split("\n") if ln.strip()]
    _first_real = _first_real_index(_lines, live_headline)
    for _li, p in enumerate(_lines):
        if _DATE_PARA_RE.match(p):
            continue
        if p.rstrip(",.").lower() in _SALUTATIONS:
            continue
        _prev_line = _lines[_li - 1] if _li > 0 else ""
        _nxt_line = _lines[_li + 1] if _li + 1 < len(_lines) else ""
        if _is_summary_subhead_at(_lines, _li, _first_real):
            continue
        if _is_defect_line(p, _prev_line, _nxt_line):
            continue
        if _RULE_LINE_RE.match(p):
            continue  # rule-line divider — residue, never content
        if "conference call" in p.lower() or "webcast" in p.lower():
            continue  # conference-call / webcast notice (CSX: the notice
            # runs two lines — "…will conduct a conference call…" then
            # "In conjunction with the call, a live webcast will be…")
            # — residue the live text drops; the residue scan
            # separately blocks a live text that still carries one
        if p.lower().startswith("this earnings announcement"):
            continue  # third line of the same CSX notice block ("This
            # earnings announcement, as well as additional detailed
            # financial information, is contained in…") — boilerplate
            # availability, never a highlight. startswith (not
            # substring) so a bullet merely mentioning the phrase
            # still has to survive.
        if _is_lede_table_line(p):
            continue  # the extractor's own table-line predicate (a bare
            # heading like Carnival's "Guidance") — not content. Bullets
            # never match it, so a dropped bullet still trips the gate.
        key = _core_key(p)
        if not key:
            continue
        if norm(key)[:60] not in live_flat:
            return p[:60]
    return None


db = get_session()
svc = FinancialsService()
repaired = []
skipped = []


def fetch_live(ticker, cik, pe):
    """Return (live, src) or (None, None) with a printed skip reason."""
    try:
        periods = discover_earnings_filings(
            ticker, svc.edgar_client, n_quarters=10,
            oldest_period_end=date.fromisoformat(pe),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{ticker} {pe} DISCOVER FAILED: {type(exc).__name__} {exc}")
        return None, None, "discover failed"
    by_pe = {str(p.period_end): p for p in periods}
    period = by_pe.get(pe)
    if period is None:
        print(f"{ticker} {pe} SKIP: period not discovered")
        return None, None, "not discovered"
    try:
        live, src, _, _, _, _ = svc._fetch_press_release_disclosures(cik, period)
    except Exception as exc:  # noqa: BLE001
        print(f"{ticker} {pe} EXTRACT FAILED: {type(exc).__name__} {exc}")
        return None, None, "extract failed"
    return live, src, None


def load_row(ticker, pe):
    cik = db.execute(
        select(Company.cik).where(Company.ticker == ticker)).scalar_one()
    qrow = db.execute(
        select(QuarterlyFinancial).where(
            QuarterlyFinancial.cik == cik,
            QuarterlyFinancial.period_end == date.fromisoformat(pe),
        )).scalar_one_or_none()
    return cik, qrow


for ticker, pe in TARGETS:
    if ONLY_TICKERS is not None and ticker not in ONLY_TICKERS:
        continue
    cik, qrow = load_row(ticker, pe)
    if qrow is None or not qrow.press_release_highlights:
        print(f"{ticker} {pe} SKIP: no stored highlights row")
        skipped.append((ticker, pe, "no stored highlights row"))
        continue
    stored = qrow.press_release_highlights or ""
    live, src, err = fetch_live(ticker, cik, pe)
    if err:
        skipped.append((ticker, pe, err))
        continue
    # Batch 174: the stored first paragraph may itself be residue (a
    # contact block or a date line — AWK/PHM); the live headline must
    # match the first REAL stored paragraph, not the residue.
    # Batch 179 round 3: the live headline is computed before the
    # stored-headline lookup so the exact join anchor can find a
    # wrapped headline's first half.
    _live_headline = norm(live.split("\n\n")[0]) if live else ""
    stored_headline, stored_headline_next = _stored_real_headline(
        stored, _live_headline
    )
    problems = []
    if live is None:
        problems.append("live is None")
    else:
        if src != qrow.press_release_source:
            problems.append(f"source mismatch live={src!r} stored={qrow.press_release_source!r}")
        if len(live) < 200:
            problems.append(f"live too short ({len(live)})")
        if live == stored:
            problems.append("live == stored (nothing to repair)")
        live_headline = _live_headline
        if ticker in BULLET_OPENERS:
            if not live_headline.startswith("•"):
                problems.append(
                    f"live does not open with a bullet: {live_headline[:70]!r}"
                )
        elif live_headline != stored_headline and (
            # Batch 179: CPB's wrapped headline — the old extractor
            # split it across two paragraphs ("...RESULTS;" /
            # "PROVIDES FULL-YEAR ... GUIDANCE"); the live extractor
            # joins them. Accept only on exact equality: the join IS
            # the live headline, so no separate defect check on the
            # next paragraph is needed (round 3 — the round-2
            # defect check wrongly blocked CMG 2025-12-31's second
            # half, a title line by the extractor's own predicate).
            not stored_headline_next
            or live_headline != norm(stored_headline + " " + stored_headline_next)
        ):
            problems.append(
                f"headline mismatch live={live_headline[:70]!r} "
                f"stored={stored_headline[:70]!r}"
            )
        opener = PROSE_OPENER.get(pe) if ticker == "COIN" else None
        if opener:
            body_parts = [
                p.strip() for p in live.split("\n\n")[1:] if p.strip()
            ]
            if not body_parts or opener not in body_parts[0]:
                problems.append(
                    f"live body does not open with prose opener: "
                    f"{opener[:70]!r}"
                )
        for s in salutation_lines(live):
            problems.append(f"live salutation survives: {s[:70]!r}")
        missing = stored_core_preserved(stored, live, live_headline)
        if missing:
            problems.append(
                f"live drops stored content: {missing[:70]!r}"
            )
        missing_line = stored_lines_preserved(stored, live, live_headline)
        if missing_line:
            problems.append(
                f"live drops stored line: {missing_line[:70]!r}"
            )
        blocking, tolerated = live_residue_lines(live)
        for ln in blocking:
            problems.append(f"live residue: {ln[:70]!r}")
        if tolerated:
            print(f"{ticker} {pe} NOTE: live carries tolerated table-intro: "
                  f"{tolerated[0][:70]!r}")
        blast_file = BLAST_DIR / f"{ticker}_{pe}.txt"
        if blast_file.exists():
            blast_text = blast_file.read_text(encoding="utf-8")
            if live != blast_text:
                problems.append(
                    f"live != blast ({len(live)} vs {len(blast_text)} chars)"
                )
        else:
            print(f"{ticker} {pe} NOTE: no blast file (outside 8-quarter "
                  f"window) — gates rest on the live re-fetch alone")
    if problems:
        print(f"{ticker} {pe} SKIP: " + "; ".join(problems))
        skipped.append((ticker, pe, "; ".join(problems)))
        continue
    if WRITE:
        qrow.press_release_highlights = live
        db.commit()
    repaired.append((ticker, pe, len(stored), len(live)))
    print(f"{ticker} {pe} {'REPAIRED' if WRITE else 'WOULD REPAIR'} "
          f"stored={len(stored)} live={len(live)}")

print(f"\n{'repaired' if WRITE else 'would repair'} {len(repaired)}/{len(TARGETS) if ONLY_TICKERS is None else sum(1 for t, _ in TARGETS if t in ONLY_TICKERS)} rows")
for ticker, pe, old_len, new_len in repaired:
    print(f"  {ticker} {pe}: {old_len} -> {new_len}")
print(f"skipped {len(skipped)}")
for ticker, pe, why in skipped:
    print(f"  {ticker} {pe}: {why[:130]}")

if WRITE:
    print("\nverify:")
    for ticker, pe, _, _ in repaired:
        _, qrow = load_row(ticker, pe)
        print(f"  {ticker} {pe}: db len={len(qrow.press_release_highlights or '')} "
              f"first={(qrow.press_release_highlights or '').splitlines()[0][:70]!r}")
