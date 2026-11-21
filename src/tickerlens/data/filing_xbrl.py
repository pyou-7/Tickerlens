"""Per-filing inline-XBRL fallback for filings SEC's companyfacts hasn't ingested.

Batch 293: SEC's companyfacts aggregation can lag a filing by months — 11
filers (AEP/C/D/DLR/DUK/ETR/NEE/PLD/PPL/SO/SRE) had filed Q2+Q3 2026 10-Qs
with zero facts in the feed, leaving their pages 2-3 quarters stale behind
an honesty note (batch 82). The filings themselves carry full inline XBRL,
so when a recent 10-Q/10-K accession is absent from companyfacts we parse
the primary document's ``ix:nonFraction`` facts into companyfacts shape and
merge them in; the existing extractor then runs unchanged.

Parity rules with companyfacts:
- us-gaap concepts only; dimensional facts (segment/scenario members) are
  skipped — companyfacts carries consolidated facts only.
- ``fy``/``fp`` come from the filing's dei DocumentFiscalYearFocus /
  DocumentFiscalPeriodFocus, exactly as SEC labels companyfacts facts
  (comparative columns inherit the filing's focus; the extractor's
  earliest-filed-labels rule sorts them out). A filing without dei focus
  tags abstains — unlabeled facts would raise in the extractor.
- Units normalize to companyfacts spellings (``USD``, ``USD/shares``,
  ``shares``, ``pure``).
"""

from __future__ import annotations

import html as _html
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_PFX = r"(?:[A-Za-z_][\w.-]*:)?"
_CONTEXT_RE = re.compile(
    rf"<{_PFX}context\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</{_PFX}context>",
    re.S,
)
_UNIT_RE = re.compile(
    rf"<{_PFX}unit\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</{_PFX}unit>",
    re.S,
)
_MEASURE_RE = re.compile(rf"<{_PFX}measure[^>]*>([^<]+)</{_PFX}measure>")
_FACT_RE = re.compile(
    r"<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>", re.S
)
_ATTR_RE = re.compile(r'([\w:.-]+)="([^"]*)"')
_TAG_RE = re.compile(r"<[^>]+>")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _dei_focus(html_text: str, name: str) -> str | None:
    # The value may be wrapped in styled markup on the cover page
    # (<span ...>2026</span>) or nested ix elements (D/PLD filings), so
    # capture up to the closing tag and strip inner tags.
    m = re.search(
        rf'name="dei:{name}"[^>]*>(.*?)</ix:nonNumeric>', html_text, re.S
    )
    if not m:
        return None
    text = _html.unescape(_TAG_RE.sub("", m.group(1))).strip()
    return text or None


def _parse_contexts(html_text: str) -> dict[str, tuple[str | None, str] | None]:
    """context id -> (start|None, end) for consolidated contexts, else None."""
    contexts: dict[str, tuple[str | None, str] | None] = {}
    for cid, body in _CONTEXT_RE.findall(html_text):
        if "explicitMember" in body or "typedMember" in body:
            contexts[cid] = None  # dimensional — companyfacts parity: skip
            continue
        instant = re.search(rf"<{_PFX}instant[^>]*>([^<]+)</{_PFX}instant>", body)
        if instant:
            m = _DATE_RE.search(instant.group(1))
            contexts[cid] = (None, m.group(0)) if m else None
            continue
        start = re.search(rf"<{_PFX}startDate[^>]*>([^<]+)</{_PFX}startDate>", body)
        end = re.search(rf"<{_PFX}endDate[^>]*>([^<]+)</{_PFX}endDate>", body)
        if start and end:
            ms, me = _DATE_RE.search(start.group(1)), _DATE_RE.search(end.group(1))
            contexts[cid] = (ms.group(0), me.group(0)) if ms and me else None
        else:
            contexts[cid] = None
    return contexts


def _normalize_measure(measure: str) -> str:
    local = measure.strip().rsplit(":", 1)[-1]
    return local


def _parse_units(html_text: str) -> dict[str, str]:
    units: dict[str, str] = {}
    for uid, body in _UNIT_RE.findall(html_text):
        measures = [_normalize_measure(m) for m in _MEASURE_RE.findall(body)]
        if not measures:
            continue
        if "divide" in body and len(measures) >= 2:
            units[uid] = f"{measures[0]}/{measures[1]}"
        else:
            units[uid] = measures[0]
    return units


def _parse_value(text: str, fmt: str | None) -> float | None:
    """Parse an inline-XBRL displayed number; None when unparseable."""
    if fmt and "fixed-zero" in fmt:
        return 0.0
    t = text.strip()
    if t in ("", "-", "—", "–", "−"):
        return None
    parenthesized = t.startswith("(") and t.endswith(")")
    if parenthesized:
        t = t[1:-1].strip()
    t = t.replace("\xa0", "").replace("\u2009", "").replace(" ", "")
    if fmt and "num-comma-decimal" in fmt:
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    try:
        value = float(t)
    except ValueError:
        return None
    if parenthesized:
        value = -abs(value)
    return value


def parse_inline_xbrl(
    html_text: str, *, form: str, filed: str, accn: str
) -> dict[str, Any]:
    """Parse a filing's inline XBRL into companyfacts' us-gaap inner shape.

    Returns ``{tag: {"units": {unit: [fact, ...]}}}`` where each fact is a
    companyfacts-style dict (``end``, ``val``, ``filed``, ``form``, ``accn``,
    ``fy``, ``fp``, plus ``start`` for duration facts). Returns ``{}`` when
    the filing carries no dei fiscal focus (facts would be unlabeled).
    """
    fy_text = _dei_focus(html_text, "DocumentFiscalYearFocus")
    fp_text = _dei_focus(html_text, "DocumentFiscalPeriodFocus")
    if not fy_text or not fp_text:
        return {}
    try:
        fy = int(fy_text)
    except ValueError:
        return {}
    fp = fp_text.upper()
    if fp not in ("Q1", "Q2", "Q3", "Q4", "FY"):
        return {}

    contexts = _parse_contexts(html_text)
    units = _parse_units(html_text)

    out: dict[str, Any] = {}
    seen: set[tuple[str, str, str | None, str, float]] = set()
    for attrs_raw, inner in _FACT_RE.findall(html_text):
        attrs = dict(_ATTR_RE.findall(attrs_raw))
        name = attrs.get("name", "")
        if not name.startswith("us-gaap:"):
            continue
        if attrs.get("nil") == "true" or attrs.get("xsi:nil") == "true":
            continue
        if "continuedAt" in attrs:
            continue  # value split across elements — abstain
        ctx = contexts.get(attrs.get("contextRef", ""))
        if ctx is None:
            continue
        unit = units.get(attrs.get("unitRef", ""))
        if unit is None:
            continue
        text = _html.unescape(_TAG_RE.sub("", inner))
        value = _parse_value(text, attrs.get("format"))
        if value is None:
            continue
        try:
            scale = int(attrs.get("scale", "0"))
        except ValueError:
            continue
        value = value * (10.0**scale)
        if attrs.get("sign") == "-":
            value = -abs(value)
        start, end = ctx
        tag = name.split(":", 1)[1]
        key = (tag, unit, start, end, value)
        if key in seen:
            continue
        seen.add(key)
        fact: dict[str, Any] = {
            "end": end,
            "val": value,
            "filed": filed,
            "form": form,
            "accn": accn,
            "fy": fy,
            "fp": fp,
        }
        if start is not None:
            fact["start"] = start
        out.setdefault(tag, {"units": {}})["units"].setdefault(unit, []).append(fact)
    return out


def merge_filing_facts(companyfacts: dict[str, Any], filing_facts: dict[str, Any]) -> None:
    """Append per-filing facts into a companyfacts dict in place."""
    us_gaap = companyfacts.setdefault("facts", {}).setdefault("us-gaap", {})
    for tag, tag_data in filing_facts.items():
        dest_units = us_gaap.setdefault(tag, {"units": {}})["units"]
        for unit, items in tag_data.get("units", {}).items():
            dest_units.setdefault(unit, []).extend(items)


def companyfacts_accns(companyfacts: dict[str, Any]) -> set[str]:
    """All accession numbers already present in a companyfacts dict."""
    accns: set[str] = set()
    for tag_data in (companyfacts.get("facts") or {}).get("us-gaap", {}).values():
        for items in (tag_data.get("units") or {}).values():
            for item in items:
                accn = item.get("accn")
                if accn:
                    accns.add(accn)
    return accns
