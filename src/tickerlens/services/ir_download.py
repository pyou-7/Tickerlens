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

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from tickerlens.data.edgar import EdgarClient, normalize_cik


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


# ── public API ────────────────────────────────────────────────────────────────

def discover_earnings_filings(
    ticker: str,
    edgar_client: EdgarClient,
    n_quarters: int = 4,
) -> list[EarningsPeriod]:
    """
    Return the last n_quarters EarningsPeriod objects for a ticker, oldest first.

    Raises KeyError if the ticker is not found in EDGAR.
    """
    cik = edgar_client.cik_for_ticker(ticker)
    subs = edgar_client.submissions(cik)
    filings_raw = subs["filings"]["recent"]

    sec_filings = _extract_sec_filings(filings_raw)
    er_8ks = _extract_er_8ks(filings_raw)

    # Take the most recent n_quarters 10-Q/10-K sorted by period end
    sec_filings.sort(key=lambda x: x["report_date"], reverse=True)
    selected = sec_filings[:n_quarters]

    # Assign FY and quarter labels using the anchor algorithm
    _assign_fy_and_quarter(selected)

    # Match each filing with its earnings-release 8-K
    for filing in selected:
        matched = _match_8k(filing, er_8ks)
        if matched:
            er_doc = _find_ex99_doc(cik, matched["accession"], edgar_client)
            filing["er_accession"] = matched["accession"]
            filing["er_doc"] = er_doc
        else:
            filing["er_accession"] = None
            filing["er_doc"] = None

    # Build result objects, sorted oldest-first
    selected.sort(key=lambda x: x["report_date"])
    return [_to_period(f, cik) for f in selected]


# ── filing discovery helpers ──────────────────────────────────────────────────

def _extract_sec_filings(filings_raw: dict[str, Any]) -> list[dict]:
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
            })
    return results


def _extract_er_8ks(filings_raw: dict[str, Any]) -> list[dict]:
    """Return all 8-Ks that contain item 2.02 (earnings release)."""
    forms = filings_raw["form"]
    accessions = filings_raw["accessionNumber"]
    filing_dates = filings_raw["filingDate"]
    items_list = filings_raw["items"]

    results = []
    for i, form in enumerate(forms):
        if form == "8-K" and "2.02" in (items_list[i] or ""):
            results.append({
                "accession": accessions[i],
                "filing_date": date.fromisoformat(filing_dates[i]),
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
    the formal filing date wins (a quarter has exactly one earnings release,
    so ties are pathological).
    """
    report = filing["report_date"]
    candidates = [
        er for er in er_8ks
        if 0 <= (er["filing_date"] - report).days <= 60
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda er: abs((filing["filing_date"] - er["filing_date"]).days),
    )


# ── ex-99 exhibit discovery ───────────────────────────────────────────────────

def _pick_release_doc(links: list[str]) -> str | None:
    """Pick the earnings-release exhibit filename from 8-K filing-index links.

    Pure (no network) so it can be unit-tested. Priority order:
      1. ex99-style names (ex99, ex-99, ex991, EX-99.1) — AAPL/MSFT/PLUG style.
      2. Press-release naming: *pressrelease*, *earningsrelease*, *-pr/_pr
         suffixes, or a quarter-style stem ending in "pr" (NVDA's q2fy27pr.htm).
    Within a tier, a "supplement" exhibit (tables/appendix material, e.g.
    JPMorgan's *erfex992supplement.htm) loses to the narrative release
    (e.g. *exhibit991narrative.htm) — the supplement has no guidance section
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
        if re.search(r"ex(hibit)?[^a-z0-9]?99", name, re.IGNORECASE):
            base = 0
        elif re.search(r"(press|earnings)[-_]?release", stem, re.IGNORECASE):
            base = 1
        elif re.search(r"(^|[-_])pr([-_.]|$)", stem, re.IGNORECASE):
            base = 1
        # Quarter-style stem ending in "pr" with a digit (year/fy marker),
        # e.g. q2fy27pr — excludes lookalikes like proper.htm / super.htm.
        elif re.search(r"pr$", stem, re.IGNORECASE) and re.search(r"\d", stem):
            base = 2
        if base is None:
            return None
        penalty = 1 if "supplement" in stem.lower() else 0
        return (base, penalty)

    ranked = [(rank, name) for name in candidates if (rank := _rank(name)) is not None]
    if not ranked:
        return None
    return min(ranked, key=lambda item: item[0])[1]


def _find_ex99_doc(cik: str, accession: str, edgar_client: EdgarClient) -> str | None:
    """
    Fetch the 8-K filing index and return the earnings-release exhibit filename.

    Returns None if no release-looking file is found (some companies embed the
    press release directly in the primary 8-K document).
    """
    url = edgar_client.filing_index_url(cik, accession)
    try:
        html = edgar_client.fetch_text(url)
    except Exception:
        return None

    # Look for links that indicate an exhibit 99 file or press-release doc.
    links = re.findall(r'href="([^"]+\.htm[l]?)"', html, re.IGNORECASE)
    return _pick_release_doc(links)


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
    )


# ── URL construction helpers (used by the CLI) ────────────────────────────────

def sec_doc_url(cik: str, period: EarningsPeriod) -> str:
    """Full EDGAR URL for the 10-Q/10-K main document."""
    cik_num = str(int(normalize_cik(cik)))
    acc_clean = period.sec_accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/{period.sec_doc}"


def er_doc_url(cik: str, period: EarningsPeriod) -> str | None:
    """Full EDGAR URL for the earnings release exhibit, or None."""
    if not period.er_accession or not period.er_doc:
        return None
    cik_num = str(int(normalize_cik(cik)))
    acc_clean = period.er_accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/{period.er_doc}"
