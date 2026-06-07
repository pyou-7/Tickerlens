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
        q_count = 0
        for f in sorted(group, key=lambda x: x["report_date"]):
            if f["form"] == "10-K":
                f["fp"] = "Q4"  # annual covers Q4
            else:
                q_count += 1
                f["fp"] = f"Q{q_count}"


# ── 8-K matching ──────────────────────────────────────────────────────────────

def _match_8k(filing: dict, er_8ks: list[dict]) -> dict | None:
    """
    Find the earnings-release 8-K that corresponds to a 10-Q/10-K.

    The 8-K is typically filed 1–14 days before the 10-Q/10-K (companies
    announce results before the formal filing is ready).
    """
    candidates = [
        er for er in er_8ks
        if 0 <= (filing["filing_date"] - er["filing_date"]).days <= 21
    ]
    if not candidates:
        return None
    # Take the closest one
    return min(candidates, key=lambda er: abs((filing["filing_date"] - er["filing_date"]).days))


# ── ex-99 exhibit discovery ───────────────────────────────────────────────────

def _find_ex99_doc(cik: str, accession: str, edgar_client: EdgarClient) -> str | None:
    """
    Fetch the 8-K filing index and return the ex-99 exhibit filename.

    Returns None if no ex-99 file is found (some companies embed the press
    release directly in the primary 8-K document).
    """
    url = edgar_client.filing_index_url(cik, accession)
    try:
        html = edgar_client.fetch_text(url)
    except Exception:
        return None

    # Look for links that indicate an exhibit 99 file
    # Patterns: ex99, ex-99, ex991, EX-99.1, etc.
    links = re.findall(r'href="([^"]+\.htm[l]?)"', html, re.IGNORECASE)
    ex99_candidates = [
        lnk.split("/")[-1]
        for lnk in links
        if re.search(r'ex.?99', lnk, re.IGNORECASE)
        and not lnk.startswith("http")
        and not lnk.startswith("/cgi")
    ]
    return ex99_candidates[0] if ex99_candidates else None


# ── result builder ────────────────────────────────────────────────────────────

def _to_period(f: dict, cik: str) -> EarningsPeriod:
    fy = f["fy"]
    fp = f["fp"]
    # Determine which URL to use for the earnings release document
    # If we found an ex99 exhibit, use it; otherwise fall back to the 8-K primaryDocument
    # (er_doc is the filename only; full URL constructed by the caller from accession)
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
