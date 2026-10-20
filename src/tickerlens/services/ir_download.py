"""
Investor-Relations download service.

Discovers the last N quarterly earnings filings for any US public company and
returns structured metadata (EarningsPeriod) ready for PDF conversion.

Key signals used from EDGAR:
  - form="10-Q"/"10-K"   → defines the quarters
  - form="8-K", items contains "2.02" → earnings press release (universal SEC standard)
  - reportDate            → period end date (no filename parsing needed)
  - primaryDocument       → main HTM filename

Fiscal-year label algorithm:
  1. Each 10-K anchors a FY: fy = report_date.year (works for all US companies).
  2. Each 10-Q is assigned to the nearest following 10-K's FY.
  3. If no 10-K follows (most recent quarters), FY = prior 10-K year + 1.
  4. Quarter number (Q1/Q2/Q3) = ordinal position within the same FY group.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from tickerlens.data.edgar import EdgarClient, normalize_cik, predecessor_ciks

logger = logging.getLogger(__name__)


# ── public types ─────────────────────────────────────────────────────────────

@dataclass
class EarningsPeriod:
    quarter_label: str    # "Q2 FY2025"
    fiscal_year: str      # "FY2025"
    fp: str              # "Q1" | "Q2" | "Q3" | "Q4" (annual = "Q4")
    fy: int              # 2025
    period_end: date
    sec_form: str         # "10-Q" or "10-K"
    sec_accession: str    # "0001730168-25-000064"
    sec_doc: str         # "avgo-20250504.htm"  — main filing document
    er_accession: str | None  # 8-K accession, if found
    er_doc: str | None        # ex-99 exhibit filename, if found
    sec_cik: str | None = None  # CIK whose submissions feed listed the 10-Q/10-K
    er_cik: str | None = None   # CIK whose submissions feed listed the matched 8-K


# ── public API ────────────────────────────────────────────────────────────────

def _merge_filings_recent(
    base: dict[str, Any], extra: dict[str, Any]
) -> dict[str, Any]:
    """Concatenate a paginated older-submissions ``recent`` block onto the base.

    The submissions buckets share the parallel-array schema (form,
    accessionNumber, reportDate, filingDate, primaryDocument, items, ...);
    concatenation preserves per-filing alignment. Batch 97: lets
    discover_earnings_filings see 10-Q/10-Ks older than the top-level
    ``recent`` bucket for high-volume filers.
    """
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, list) and isinstance(merged.get(key), list):
            merged[key] = merged[key] + value
    return merged


def _submissions_sources(
    ticker: str, edgar_client: EdgarClient, cik: str
) -> list[tuple[str, dict]]:
    """(cik, source-state) for the ticker's CIK plus predecessor CIKs.

    Batch 99: the source state holds the source's recent block, its bucket
    list, and the pagination cursor — discover_earnings_filings pages each
    source's buckets independently. Predecessor fetches are best-effort: a
    failure is logged and skipped, so a dead old-CIK feed never breaks
    discovery for the current CIK.
    """
    sources = [(cik, edgar_client.submissions(cik))]
    for pred in predecessor_ciks(cik):
        try:
            sources.append((pred, edgar_client.submissions(pred)))
        except Exception:
            logger.warning(
                "Predecessor submissions fetch failed for %s (%s)",
                pred,
                ticker,
                exc_info=True,
            )
    return [
        (
            src_cik,
            {
                "filings_raw": subs["filings"]["recent"],
                "bucket_names": [
                    f["name"] for f in subs["filings"].get("files", [])
                ],
                "bucket_i": 0,
            },
        )
        for src_cik, subs in sources
    ]


def discover_earnings_filings(
    ticker: str,
    edgar_client: EdgarClient,
    n_quarters: int = 4,
    oldest_period_end: date | None = None,
) -> list[EarningsPeriod]:
    """
    Return the last n_quarters EarningsPeriod objects for a ticker, oldest first.

    When ``oldest_period_end`` is given (the oldest stored quarter needing
    enrichment), pagination continues past n_quarters until the filings cover
    it, and the selection extends to include it. Batch 97: the stored 8-quarter
    window can lag submissions (EDGAR companyfacts delay) — e.g. V's stored
    rows end 2026-03-31 while submissions already have the 2026-06-30 10-Q,
    so the latest-8 filings start at 2024-09-30 and the stored 2024-06-30
    quarter (the 9th filing) would never match an 8-K.

    Batch 99: merges the predecessor-CIK submissions feeds (see
    _CIK_SUCCESSIONS in data/edgar.py) — SEC moves a ticker to a new CIK on
    a reorganization (XOM -> 0002115436) and the new CIK's feed starts at
    the succession, so pre-succession earnings 8-Ks live only under the old
    CIK. Each extracted filing carries its source CIK (the archives path
    its documents live under); accession collisions between the feeds (the
    same filing attributed to both CIKs, e.g. XOM's Q2-2026 10-Q) dedupe to
    the current CIK's copy.

    Raises KeyError if the ticker is not found in EDGAR.
    """
    cik = edgar_client.cik_for_ticker(ticker)
    sources = _submissions_sources(ticker, edgar_client, cik)

    def extract_all() -> tuple[list[dict], list[dict], list[dict]]:
        """Merge per-CIK extractions.

        Within one source the merged recent+bucket arrays concatenate exactly
        as before (a CIK's buckets are disjoint from its recent block). Across
        sources, accessions are deduped — sources are ordered
        current-CIK-first, so on a collision (the same filing attributed to
        both CIKs, e.g. XOM's Q2-2026 10-Q) the current CIK's copy wins and
        its src_cik points at the live archives path.
        """
        sec, ers, others = [], [], []
        seen_sec, seen_er, seen_other = set(), set(), set()  # accessions claimed by earlier sources
        for src_cik, state in sources:
            src_sec = _extract_sec_filings(state["filings_raw"], src_cik=src_cik)
            src_er = _extract_er_8ks(state["filings_raw"], src_cik=src_cik)
            src_other = _extract_other_8ks(state["filings_raw"], src_cik=src_cik)
            new_sec = [f for f in src_sec if f["accession"] not in seen_sec]
            new_er = [e for e in src_er if e["accession"] not in seen_er]
            new_other = [e for e in src_other if e["accession"] not in seen_other]
            seen_sec.update(f["accession"] for f in new_sec)
            seen_er.update(e["accession"] for e in new_er)
            seen_other.update(e["accession"] for e in new_other)
            sec.extend(new_sec)
            ers.extend(new_er)
            others.extend(new_other)
        return sec, ers, others

    sec_filings, er_8ks, other_8ks = extract_all()
    # Batch 97: the top-level "recent" bucket may cover fewer than n_quarters
    # of 10-Q/10-K for high-volume filers (BAC's recent holds 3 10-Q + 1
    # 10-K) — older quarters then never matched an earnings 8-K and their
    # highlights could never backfill. Page through the older-submissions
    # buckets (001 = next-older after recent) until we have enough 10-Q/10-K.
    # The 8-Ks contemporary with those older quarters ride along in the same
    # buckets, so _extract_er_8ks sees them too. Cached by fetch_json, so the
    # extra requests are one-time-ish per CIK. Batch 99: each source CIK
    # pages its own bucket list.
    while True:
        sec_ok = len(sec_filings) >= n_quarters
        oldest_ok = (
            oldest_period_end is None
            or not sec_filings
            or min(f["report_date"] for f in sec_filings) <= oldest_period_end
        )
        # Batch 97: the 8-K for the oldest needed quarter can sit in an older
        # bucket than its 10-Q (MS's Oct-2024 8-K vs its Nov-2024 10-Q) —
        # keep paging until the 8-Ks reach the oldest period's 8-K window.
        er_ok = (
            oldest_period_end is None
            or not er_8ks
            or min(er["filing_date"] for er in er_8ks)
            <= oldest_period_end + timedelta(days=7)
        )
        next_src = next(
            (s for s in sources if s[1]["bucket_i"] < len(s[1]["bucket_names"])),
            None,
        )
        if (sec_ok and oldest_ok and er_ok) or next_src is None:
            break
        src_cik, state = next_src
        try:
            # NB: a bucket file's top level IS the "recent"-shaped block
            # (no "filings" wrapper).
            older = edgar_client.submissions_bucket(
                src_cik, state["bucket_names"][state["bucket_i"]]
            )
            state["filings_raw"] = _merge_filings_recent(state["filings_raw"], older)
            sec_filings, er_8ks, other_8ks = extract_all()
        except Exception:
            logger.warning(
                "Older-submissions bucket %s unreadable for %s (%s)",
                state["bucket_names"][state["bucket_i"]],
                ticker,
                src_cik,
                exc_info=True,
            )
            break
        state["bucket_i"] += 1

    # Take the most recent n_quarters 10-Q/10-K sorted by period end,
    # extended down to oldest_period_end when the stored window lags
    # submissions (batch 97).
    sec_filings.sort(key=lambda x: x["report_date"], reverse=True)
    if oldest_period_end is not None:
        n_take = n_quarters
        while (
            n_take < len(sec_filings)
            and sec_filings[n_take - 1]["report_date"] > oldest_period_end
        ):
            n_take += 1
        selected = sec_filings[:n_take]
    else:
        selected = sec_filings[:n_quarters]

    # Assign FY and quarter labels using the anchor algorithm
    _assign_fy_and_quarter(selected)

    # Match each filing with its earnings-release 8-K
    for filing in selected:
        matched = _match_8k(filing, er_8ks)
        if matched:
            er_doc = _find_ex99_doc(cik, matched, edgar_client)
            filing["er_accession"] = matched["accession"]
            filing["er_doc"] = er_doc
            # Batch 99: the 8-K's own source CIK — its filing index and
            # exhibits live under that CIK's archives path, not necessarily
            # the ticker's current CIK.
            filing["er_src_cik"] = matched.get("src_cik")
        else:
            # Batch 101: no 2.02 candidate — try the guarded non-2.02
            # fallback (9.01-only / 8.01+9.01 / 2.01+9.01 earnings 8-Ks).
            # A 2.02 match always wins; the fallback only fills quarters
            # the primary path could never match.
            fb = _match_8k_non202_fallback(
                filing, other_8ks, ticker, cik, edgar_client
            )
            if fb is not None:
                fb_match, fb_doc = fb
                filing["er_accession"] = fb_match["accession"]
                filing["er_doc"] = fb_doc
                filing["er_src_cik"] = fb_match.get("src_cik")
            else:
                filing["er_accession"] = None
                filing["er_doc"] = None
                filing["er_src_cik"] = None

    # Build result objects, sorted oldest-first
    selected.sort(key=lambda x: x["report_date"])
    return [_to_period(f, cik) for f in selected]


# ── filing discovery helpers ──────────────────────────────────────────────────

def _extract_sec_filings(
    filings_raw: dict[str, Any], src_cik: str | None = None
) -> list[dict]:
    """10-Q/10-K filings from a submissions block, tagged with ``src_cik``.

    Batch 99: the tag records which CIK's feed the filing came from — its
    documents live under that CIK's archives path.
    """
    forms = filings_raw["form"]
    accessions = filings_raw["accessionNumber"]
    report_dates = filings_raw["reportDate"]
    filing_dates = filings_raw["filingDate"]
    primary_docs = filings_raw["primaryDocument"]

    results = []
    for i, form in enumerate(forms):
        if form in ("10-Q", "10-K") and report_dates[i]:
            results.append({
                "form": form,
                "accession": accessions[i],
                "report_date": date.fromisoformat(report_dates[i]),
                "filing_date": date.fromisoformat(filing_dates[i]),
                "primary_doc": primary_docs[i],
                "src_cik": src_cik,
            })
    return results


def _extract_er_8ks(
    filings_raw: dict[str, Any], src_cik: str | None = None
) -> list[dict]:
    """All 8-Ks containing item 2.02 (earnings release), tagged with ``src_cik``.

    Batch 99: the tag records which CIK's feed the 8-K came from — its
    filing index and exhibits live under that CIK's archives path.
    """
    forms = filings_raw["form"]
    accessions = filings_raw["accessionNumber"]
    filing_dates = filings_raw["filingDate"]
    items_list = filings_raw["items"]
    primary_docs = filings_raw["primaryDocument"]

    results = []
    for i, form in enumerate(forms):
        if form == "8-K" and "2.02" in (items_list[i] or ""):
            results.append({
                "accession": accessions[i],
                "filing_date": date.fromisoformat(filing_dates[i]),
                # Batch 97: the lone-exhibit fallback needs the primary doc
                # name (to exclude it) and the exact items string (2.02-only
                # guard).
                "primary_doc": primary_docs[i],
                "items": items_list[i] or "",
                "src_cik": src_cik,
            })
    return results


def _extract_other_8ks(
    filings_raw: dict[str, Any], src_cik: str | None = None
) -> list[dict]:
    """8-Ks that furnish exhibits (9.01) but do NOT carry Item 2.02.

    Batch 101: some filers furnish the earnings release without Item 2.02 —
    Citi and Mettler-Toledo file 9.01-only, Colgate files 8.01+9.01, GE
    Vernova files 2.01+9.01. These are never preferred over a 2.02 match;
    they feed only the guarded _match_8k_non202_fallback, which additionally
    requires a release-looking exhibit in the filing index. The 9.01
    requirement bounds the candidate set to 8-Ks that actually furnish
    exhibits (an exhibit-less 8-K cannot carry the release; embedded-in-
    primary-doc releases remain a documented limitation).
    """
    forms = filings_raw["form"]
    accessions = filings_raw["accessionNumber"]
    filing_dates = filings_raw["filingDate"]
    items_list = filings_raw["items"]
    primary_docs = filings_raw["primaryDocument"]

    results = []
    for i, form in enumerate(forms):
        items = items_list[i] or ""
        if form == "8-K" and "2.02" not in items and "9.01" in items:
            results.append({
                "accession": accessions[i],
                "filing_date": date.fromisoformat(filing_dates[i]),
                "primary_doc": primary_docs[i],
                "items": items,
                "src_cik": src_cik,
            })
    return results


# ── FY / quarter labeling ─────────────────────────────────────────────────────

def _assign_fy_and_quarter(filings: list[dict]) -> None:
    """
    Mutates each filing dict to add 'fy' (int) and 'fp' (str) keys.

    Algorithm:
      - Sort by report_date ascending for processing.
      - Each 10-K anchors fy = report_date.year.
      - Each 10-Q inherits the fy of the next 10-K that comes after it.
        If no 10-K follows, fy = prior 10-K year + 1.
      - Quarter number = ordinal count within each fy group.
    """
    by_date = sorted(filings, key=lambda x: x["report_date"])

    # Pass 1: assign fy
    for i, f in enumerate(by_date):
        if f["form"] == "10-K":
            f["fy"] = f["report_date"].year
        else:
            next_10k = next((x for x in by_date[i + 1:] if x["form"] == "10-K"), None)
            if next_10k:
                f["fy"] = next_10k["report_date"].year
            else:
                prev_10k = next((x for x in reversed(by_date[:i]) if x["form"] == "10-K"), None)
                f["fy"] = (prev_10k["fy"] + 1) if prev_10k else f["report_date"].year

    # Pass 2: assign quarter numbers within each fy
    fy_groups: dict[int, list[dict]] = {}
    for f in by_date:
        fy_groups.setdefault(f["fy"], []).append(f)

    for fy, group in fy_groups.items():
        ordered = sorted(group, key=lambda x: x["report_date"])
        # Index of the annual filing: quarters dated before it count BACK from
        # Q4. A window that starts mid-cycle (e.g. NVDA's Q3 FY2025 10-Q, whose
        # fy group opens with the 10-Q, not Q1) was previously mislabeled Q1.
        k10 = next((i for i, f in enumerate(ordered) if f["form"] == "10-K"), None)
        q_count = 0
        for i, f in enumerate(ordered):
            if f["form"] == "10-K":
                f["fp"] = "Q4"  # annual covers Q4
            elif k10 is not None and i < k10:
                f["fp"] = f"Q{4 - (k10 - i)}"
            else:
                # No annual filing in this group (leading partial year of a new
                # fy): quarters run forward from Q1 as before.
                q_count += 1
                f["fp"] = f"Q{q_count}"


# ── 8-K matching ──────────────────────────────────────────────────────────────

def _match_8k(filing: dict, er_8ks: list[dict]) -> dict | None:
    """
    Find the earnings-release 8-K that corresponds to a 10-Q/10-K.

    The earnings release is furnished (Item 2.02) after the quarter ends and
    before the 10-Q/10-K is filed — but the lag to the formal filing varies
    (10-Ks routinely trail earnings by 4+ weeks, and some 10-Qs by 3+), so
    anchoring on the filing date with a tight window systematically missed
    annual periods. Anchor on the period end instead: candidates are Item
    2.02 8-Ks filed after the report date and within 60 days; the one nearest
    the formal filing date wins.

    Two guards keep later/earlier 2.02 furnishings out (batch 97):
    - Filed AFTER the 10-Q/10-K: not the earnings release (PNC furnished a
      2.02 investor-conference 8-K on 2025-11-07, four days after its 11-03
      10-Q — "nearest" picked the conference over the 10-15 earnings 8-K).
    - Filed within 7 days of period end: too early for earnings (the books
      aren't closed) — Tesla furnishes production/deliveries under 2.02 two
      days after quarter end, ahead of the real earnings 8-K three weeks
      later.
    """
    report = filing["report_date"]
    filed = filing["filing_date"]
    candidates = [
        er for er in er_8ks
        if 7 <= (er["filing_date"] - report).days <= 60
        and er["filing_date"] <= filed
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda er: abs((filed - er["filing_date"]).days),
    )


def _exhibit_matches_period(
    doc: str, ticker: str, report: date, filing_date: date
) -> bool:
    """Does the exhibit filename look like it belongs to this quarter?

    Batch 101: the non-2.02 fallback's only semantic signal is the exhibit
    name, so a bare ex99-style hit is not enough — a 9.01 8-K furnishing an
    unrelated ex99 (Citi's Trust Preferred Securities 8-K,
    d240560dex991.htm) must not become the quarter's earnings release. The
    filename must reference the period: the 8-K's filing date as YYYYMMDD
    (Citi's c-20240712xex99d1.htm), a quarter token for the period's quarter
    and year (Colgate's q32024pressreleasetables.htm, MTD's
    ex-991mtd8xkq42024.htm, GEV's gevpressrelease2q25.htm), or the company
    ticker (len >= 2 — a single letter like Citi's "c" is noise).
    """
    stem = doc.lower()
    if filing_date.strftime("%Y%m%d") in stem:
        return True
    yy = report.strftime("%y")
    yyyy = report.strftime("%Y")
    q = (report.month - 1) // 3 + 1
    for tok in (
        f"q{q}{yyyy}", f"q{q}{yy}", f"q{q}-{yyyy}", f"q{q}-{yy}",
        f"{q}q{yy}", f"{q}q{yyyy}", f"{yyyy}q{q}", f"fy{yy}q{q}",
    ):
        if tok in stem:
            return True
    t = ticker.lower()
    if len(t) >= 2 and t in stem:
        return True
    return False


def _match_8k_non202_fallback(
    filing: dict,
    other_8ks: list[dict],
    ticker: str,
    cik: str,
    edgar_client: EdgarClient,
) -> tuple[dict, str] | None:
    """Guarded fallback for earnings 8-Ks filed without Item 2.02.

    Batch 101: Citi/Mettler-Toledo file 9.01-only earnings 8-Ks, Colgate
    files 8.01+9.01, GE Vernova files 2.01+9.01 — the 2.02 gate in
    _extract_er_8ks misses all of them. Only runs when _match_8k found no
    2.02 candidate. Candidates keep the batch-97 guards (filed 7–60 days
    after period end, not after the formal filing; nearest to the filing
    wins) and additionally must carry a release-looking exhibit in their
    filing index — _pick_release_doc, deliberately WITHOUT the
    _lone_exhibit_fallback, so a lone non-release exhibit (an underwriting
    agreement, a segment recast) can never promote an arbitrary 9.01 8-K
    into the earnings release — whose filename must also reference the
    period (_exhibit_matches_period: filing date, quarter token, or ticker),
    so an unrelated ex99 (Citi's Trust Preferred Securities 8-K) cannot win
    on name shape alone. Best-effort: an unreadable filing index
    skips that candidate; total failure returns None.

    Returns (matched_8k, exhibit_filename), or None.
    """
    report = filing["report_date"]
    filed = filing["filing_date"]
    candidates = [
        er for er in other_8ks
        if 7 <= (er["filing_date"] - report).days <= 60
        and er["filing_date"] <= filed
    ]
    candidates.sort(key=lambda er: abs((filed - er["filing_date"]).days))
    for cand in candidates:
        url = edgar_client.filing_index_url(cand.get("src_cik") or cik, cand["accession"])
        try:
            html = edgar_client.fetch_text(url)
        except Exception:
            continue
        if not isinstance(html, str):
            continue
        links = re.findall(r'href="([^"]+\.htm[l]?)"', html, re.IGNORECASE)
        doc = _pick_release_doc(links)
        if doc is not None and _exhibit_matches_period(
            doc, ticker, report, cand["filing_date"]
        ):
            logger.info(
                "Non-2.02 earnings 8-K fallback matched %s (%s) for %s %s",
                cand["accession"], cand["items"], cik, report,
            )
            return cand, doc
    return None


# ── ex-99 exhibit discovery ───────────────────────────────────────────────────

def _pick_release_doc(links: list[str]) -> str | None:
    """Pick the earnings-release exhibit filename from 8-K filing-index links.

    Pure (no network) so it can be unit-tested. Priority order:
      1. ex99-style names (ex99, ex-99, ex991, EX-99.1, exx99, exh99) —
         AAPL/MSFT/PLUG style, Mastercard's doubled-x
         "ma06302026-exx991xearnings.htm", EOG's "exh99-1" convention;
         a bare "991" exhibit suffix (AMD's q22026991.htm = Q2 2026 99.1),
         "991" as an infix before a quarter marker or separator (Realty
         Income's o-991q22026.htm), or "991" leading a letter run (United
         Health's a991unherq42025.htm — the 99.1 release; its q42025er992.htm
         99.2 supplement is deliberately NOT matched).
      2. Press-release naming: *pressrelease*, *earningsrelease* (or the
         truncated *earningsrele* Starbucks uses), digit/separator-suffixed
         forms (Carnival, Travelers), explicit "earnings 8-K exhibit"
         (Accenture) or bare "8-K exhibit" (ACN's fy24q4plc8-kexhibit.htm),
         "earnings news release" (Corteva), shareholder-letter releases
         (Affirm/Coinbase/Duolingo, incl. "shareholderlett" truncation),
         "share"/"shar"/"sha" truncations with a quarter/fy/ordinal guard
         (CART's cartfourthquarter2025sha.htm), "sales and earnings" (Lilly),
         "financial highlights" (PNC), headline-style "X reports ..."
         (McCormick, incl. truncated mkcreportsstrongfi.htm), "er doc"
         (Southwest), bare "er"+quarter (ServiceNow), *-pr/_pr suffixes,
         "pr" with trailing junk plus a date/quarter guard (EQIX's
         eqix-033125xpr8k.htm / eqix-093024xpruploadhyperl.htm), or a
         quarter-style stem ending in "pr" (NVDA's q2fy27pr.htm).
      3. Weaker signals: "earnings" adjacent to a quarter/fy marker
         (Snowflake's fy2027q2earnings.htm; Corteva's reversed "4qx2024"
         marker), truncated "earn"+quarter (GPC's gpc-earnq22026.htm),
         month+year+"release" (Crown Castle's may2026release.htm),
         "announces"+month (Delta's deltaairlinesannouncessept.htm), bare
         "reports" (McCormick's truncated headline names — "annual" excluded).
    Within a tier, a "supplement"/"schedules" exhibit (tables/appendix
    material, e.g. JPMorgan's *erfex992supplement.htm, Corteva's
    *enrschedules.htm) loses to the narrative release (e.g.
    *exhibit991narrative.htm) — the supplement has no guidance section
    or executive quotes to extract.
    Returns the bare filename, or None when nothing looks like a release.
    """
    candidates = [
        lnk.split("/")[-1]
        for lnk in links
        if not lnk.startswith("http")
        and not lnk.startswith("/cgi")
        and lnk.split("/")[-1].lower() != "index.htm"
        and not re.match(r"^R\d+\.htm[l]?$", lnk.split("/")[-1], re.IGNORECASE)
    ]

    def _rank(name: str) -> tuple[int, int] | None:
        stem = re.sub(r"\.html?$", "", name, flags=re.IGNORECASE)
        base: int | None = None
        # ex99 / ex-99 / ex991 / EX-99.1 / exx99 / exh99 (Mastercard's
        # doubled-x "exx991xearnings" convention, e.g.
        # ma06302026-exx991xearnings.htm; EOG's exh99-1...htm), a bare "991"
        # exhibit suffix (AMD's q22026991.htm = Q2 2026 99.1), "991" as an
        # infix before a quarter marker or separator (Realty Income's
        # o-991q22026.htm = 99.1, Q2 2026), or "991" leading a letter run
        # (United Health's a991unherq42025.htm — the 99.1 release; the
        # lookahead's digit exclusion keeps doc9912final.htm unmatched, and
        # 99.2 supplements like q42025er992.htm deliberately never match).
        # The (?!\d|\.\d) guard keeps 99.2/99.3+ supplements (BAC's
        # bac-09302026ex993.htm, MET's ex992qfsq325.htm) out of tier 0 — the
        # 99.1 release is the press release; higher numbers are supplements.
        # The "01" alternative covers the undotted 99.1 form (Cadence's
        # cdns07222024ex9901.htm); "02"/"03" still fail the guard. The guard
        # allows the "." of the file extension (".htm") but not ".2"/".3".
        if re.search(r"ex(?:hibit|h)?x?[^a-z0-9]?99(\.1|1|01)?(?!\d|\.\d)", name, re.IGNORECASE) or re.search(
            r"991(?=q\d|[-_]|$|[a-z])", stem, re.IGNORECASE
        ):
            base = 0
        # Press-release naming (tier 1):
        # *pressrelease* / *earningsrelease* (or the truncated *earningsrele* /
        # *earningsrelea* Starbucks and Amgen use), including digit- or
        # separator-suffixed forms (Carnival's a20263qearningsrelease8-k.htm,
        # Travelers' a991pressrelease93026.htm); explicit "earnings 8-K
        # exhibit" naming (Accenture's q4fy26earnings8-kexhibit.htm) or a bare
        # "8-K exhibit" (ACN's older fy24q4plc8-kexhibit.htm — an 8-K exhibit
        # in an Item 2.02 filing is the furnished release); "earnings
        # news release" (Corteva's a2q_2026xearningsxnewsxr.htm); shareholder
        # letters that ARE the release (Affirm's affirmfq426shareholderle.htm
        # and afrm-q225shareholderlett.htm, Coinbase's
        # q425shareholderletter.htm, Duolingo's q2fy26duolingo6-30x26share.htm
        # and q4fy25duolingo12-31x25shar.htm — beats the ...xpres.htm deck);
        # "share"/"shar"/"sha" truncations (CART's cartfourthquarter2025sha.htm
        # — the quarter/fy/ordinal guard keeps lookalikes out);
        # "sales and earnings" (Lilly's q226lillysalesandearningsp.htm);
        # "financial highlights" (PNC's q32026financialhighlightsa.htm —
        # beats the ...financialsupplement.htm tables); headline-style "X
        # reports ..." (McCormick's mkcreportssolidthirdquar.htm); "er doc"
        # (Southwest's er-6302026xerdoc.htm); bare "er"+quarter (ServiceNow's
        # erq2fy26.htm); "pr" with trailing junk plus a date/quarter guard
        # (EQIX's eqix-033125xpr8k.htm / eqix-093024xpruploadhyperl.htm — the
        # separator before "pr" keeps "express"/"improper" out).
        elif (
            re.search(r"(press|earnings)[-_ ]?rele[a-z]*(?=$|[-_.\d])", stem, re.IGNORECASE)
            or re.search(r"(press|earnings)[-_ ]?8[-_ ]?k", stem, re.IGNORECASE)
            or re.search(r"8[-_ ]?k[-_ ]?exhibit", stem, re.IGNORECASE)
            or re.search(r"earnings[-_x]?news", stem, re.IGNORECASE)
            or re.search(r"shareholder(?:le(?:t(?:t(?:er?)?)?)?)?(?=$|[-_.])", stem, re.IGNORECASE)
            or (
                # "share"/"shar"/"sha" truncations (CART's
                # cartfourthquarter2025sha.htm) — the quarter/fy/ordinal guard
                # keeps lookalikes like "sharkweek" out.
                re.search(r"sha(?:re?)?$", stem, re.IGNORECASE)
                and re.search(r"(q[1-4]|fy\d|first|second|third|fourth)", stem, re.IGNORECASE)
            )
            or re.search(r"sales[-_ ]?and[-_ ]?earnings", stem, re.IGNORECASE)
            or re.search(r"financial[-_ ]?highlights", stem, re.IGNORECASE)
            or (
                re.search(r"reports", stem, re.IGNORECASE)
                and re.search(
                    r"(quarter|first|second|third|fourth|fiscal|q[1-4])",
                    stem,
                    re.IGNORECASE,
                )
            )
            or re.search(r"(^|[-_x.])erdoc(ument)?($|[-_.])", stem, re.IGNORECASE)
            or re.search(r"(^|[-_])erq[1-4]", stem, re.IGNORECASE)
            or re.search(r"(^|[-_])pr([-_.]|$)", stem, re.IGNORECASE)
            or (
                re.search(r"(^|[-_x.])pr", stem, re.IGNORECASE)
                and re.search(r"(q[1-4]|fy\d|\d{6})", stem, re.IGNORECASE)
            )
        ):
            base = 1
        # Quarter-style stem ending in "pr" with a digit (year/fy marker),
        # e.g. q2fy27pr — excludes lookalikes like proper.htm / super.htm.
        elif re.search(r"pr$", stem, re.IGNORECASE) and re.search(r"\d", stem):
            base = 2
        # "earnings" adjacent to a quarter/fy marker (Snowflake's
        # fy2027q2earnings.htm, Newmont's newmontq42025earningsand20.htm;
        # Corteva's reversed "4qx2024" marker in final_4qx2024xearningsxn.htm).
        elif re.search(
            r"(q[1-4]|[1-4]q|fy\d).{0,12}earnings|earnings.{0,12}(q[1-4]|[1-4]q|fy\d)",
            stem,
            re.IGNORECASE,
        ):
            base = 2
        # Truncated "earn"+quarter (GPC's gpc-earnq22026.htm — the left
        # boundary keeps "learn..."/"earned..." out).
        elif re.search(r"(^|[-_x.])earn[-_x]?(q[1-4]|fy\d)", stem, re.IGNORECASE):
            base = 2
        # Month+year+"release" (Crown Castle's may2026release.htm — the
        # proforma doc in the same index carries no "release").
        elif re.search(
            r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\d{4}rele[a-z]*(?=$|[-_.])",
            stem,
            re.IGNORECASE,
        ):
            base = 2
        # "announces"+month (Delta's deltaairlinesannouncessept.htm /
        # ...announcesjune.htm / ...announcesmarc.htm / ...announcesdece.htm).
        elif re.search(
            r"announces(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
            stem,
            re.IGNORECASE,
        ):
            base = 2
        # Bare headline-style "reports" (McCormick's truncated
        # mccormickreportsstrongfi.htm / ...strong20.htm / ...strong2024.htm —
        # the quarter word didn't survive truncation; "annual" excluded so
        # annual-report exhibits can never match).
        elif re.search(r"reports", stem, re.IGNORECASE) and not re.search(
            r"annual", stem, re.IGNORECASE
        ):
            base = 2
        if base is None:
            return None
        penalty = (
            1
            if re.search(r"supplement|schedules", stem, re.IGNORECASE)
            else 0
        )
        return (base, penalty)

    ranked = [(rank, name) for name in candidates if (rank := _rank(name)) is not None]
    if not ranked:
        return None
    return min(ranked, key=lambda item: item[0])[1]


def _is_filing_doc_href(href: str) -> bool:
    """True for hrefs pointing at actual filing documents (not SEC chrome).

    Filing docs live under /Archives/edgar/data/ (absolute hrefs) or are
    relative (older indexes); the nav chrome (search, about, eeoinfo,
    privacy, index.htm) always uses absolute non-/Archives/ paths.
    """
    return "/Archives/edgar/data/" in href or (
        not href.startswith(("/", "http")) and "://" not in href
    )


def _lone_exhibit_fallback(
    links: list[str], primary_doc: str | None, items: str | None
) -> str | None:
    """Last-resort exhibit pick for earnings 8-Ks (batch 97).

    Some filers name the furnished release with no recognizable convention:
    Tesla's bare "exhibit.htm", PNC's "a2025_11x07xbaabxvf.htm", Halliburton's
    Workiva-default "livemastererdocument.htm", Union Pacific's
    "ex_713315.htm". In an 8-K led by Item 2.02, a single non-primary exhibit
    IS the furnished release — 2.02 exists to furnish it — so when
    _pick_release_doc finds nothing and exactly one filing document (besides
    the primary 8-K doc) is present, return it.

    The 2.02-first guard is the safety: most earnings 8-Ks carry 9.01 (and
    often 7.01) alongside 2.02, so "exactly 2.02" would almost never fire;
    but an 8-K led by another item (e.g. 5.02 with an employment-agreement
    exhibit and an incidental embedded 2.02 release) must never be guessed.
    Pure (no network) for unit tests.
    """
    first_item = (items or "").split(",")[0].strip()
    if first_item != "2.02":
        return None
    docs = []
    for href in links:
        if not _is_filing_doc_href(href):
            continue
        name = href.split("/")[-1]
        low = name.lower()
        if low == "index.htm":
            continue
        if low.endswith("-index.html") or low.endswith("-index-headers.html"):
            continue
        if re.match(r"^R\d+\.htm[l]?$", name, re.IGNORECASE):
            continue
        if primary_doc and low == primary_doc.lower():
            continue
        docs.append(name)
    if len(docs) == 1:
        return docs[0]
    return None


def _find_ex99_doc(
    cik: str, matched_8k: dict, edgar_client: EdgarClient
) -> str | None:
    """
    Fetch the 8-K filing index and return the earnings-release exhibit filename.

    Returns None if no release-looking file is found (some companies embed the
    press release directly in the primary 8-K document).
    """
    accession = matched_8k["accession"]
    # Batch 99: the filing index lives under the 8-K's own source CIK
    # (predecessor-CIK 8-Ks are not under the ticker's current CIK).
    url = edgar_client.filing_index_url(matched_8k.get("src_cik") or cik, accession)
    try:
        html = edgar_client.fetch_text(url)
    except Exception:
        return None

    # Look for links that indicate an exhibit 99 file or press-release doc.
    links = re.findall(r'href="([^"]+\.htm[l]?)"', html, re.IGNORECASE)
    doc = _pick_release_doc(links)
    if doc is None:
        doc = _lone_exhibit_fallback(
            links, matched_8k.get("primary_doc"), matched_8k.get("items")
        )
    return doc


# ── result builder ────────────────────────────────────────────────────────────

def _to_period(f: dict, cik: str) -> EarningsPeriod:
    fy = f["fy"]
    fp = f["fp"]
    # Determine which URL to use for the earnings release document.
    # er_doc is the exhibit filename (None when no release-looking exhibit
    # was found); full URL constructed by the caller from the 8-K accession.
    # Releases embedded directly in the primary 8-K document are not handled.
    return EarningsPeriod(
        quarter_label=f"{fp} FY{fy}",
        fiscal_year=f"FY{fy}",
        fp=fp,
        fy=fy,
        period_end=f["report_date"],
        sec_form=f["form"],
        sec_accession=f["accession"],
        sec_doc=f["primary_doc"],
        er_accession=f.get("er_accession"),
        er_doc=f.get("er_doc"),
        # Batch 99: source CIKs for the archives paths of the 10-Q/10-K doc
        # and the 8-K exhibit — a predecessor-CIK filing's documents live
        # under the predecessor CIK, not the ticker's current CIK.
        sec_cik=f.get("src_cik"),
        er_cik=f.get("er_src_cik"),
    )


# ── URL construction helpers (used by the CLI) ────────────────────────────────

def sec_doc_url(cik: str, period: EarningsPeriod) -> str:
    """Full EDGAR URL for the 10-Q/10-K main document."""
    # Batch 99: the document lives under the CIK whose submissions feed
    # listed it — a predecessor-CIK filing's accession embeds the old CIK.
    cik_num = str(int(normalize_cik(period.sec_cik or cik)))
    acc_clean = period.sec_accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/{period.sec_doc}"


def er_doc_url(cik: str, period: EarningsPeriod) -> str | None:
    """Full EDGAR URL for the earnings release exhibit, or None."""
    if not period.er_accession or not period.er_doc:
        return None
    # Batch 99: the exhibit lives under the CIK whose submissions feed
    # listed the 8-K — a predecessor-CIK 8-K's accession embeds the old CIK.
    cik_num = str(int(normalize_cik(period.er_cik or cik)))
    acc_clean = period.er_accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/{period.er_doc}"
