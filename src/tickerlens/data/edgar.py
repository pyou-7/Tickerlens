import copy
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from tickerlens.config import get_settings

logger = logging.getLogger(__name__)


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_SUBMISSIONS_BUCKET_URL = "https://data.sec.gov/submissions/{bucket}"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


class EdgarClient:
    """SEC EDGAR JSON client with required headers, cache, and throttling."""

    # After a live fetch fails, skip re-attempting it for this long and serve
    # the stale disk cache directly. Batch 76: when the .edgar_cache snapshot
    # expired, every request blocked on a 30s proxy timeout in series (~10 min
    # stall) before 500ing; the cooldown keeps routes fast and never-raise.
    FAILURE_COOLDOWN_SECONDS = 5 * 60

    def __init__(
        self,
        user_agent: str | None = None,
        cache_dir: Path | str | None = None,
        min_request_interval_seconds: float = 0.1,
        http_client: httpx.Client | None = None,
        cache_ttl_seconds: float = 6 * 3600,
    ) -> None:
        settings = get_settings()
        self.user_agent = user_agent or settings.edgar_user_agent
        if not self.user_agent:
            raise ValueError("SEC EDGAR requests require a User-Agent header")

        self.cache_dir = Path(cache_dir or settings.edgar_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_request_interval_seconds = min_request_interval_seconds
        self._last_request_at = 0.0
        self._http_client = http_client
        # Disk cache TTL. A write-once cache used to freeze companyfacts and
        # submissions snapshots forever, which silently disabled the
        # auto-refresh: the freshness trigger went blind to new filings and a
        # triggered pull re-extracted the same stale snapshot. The default
        # matches the financials-service filings-check TTL so each check
        # performs at most one live fetch per endpoint per company.
        self.cache_ttl_seconds = cache_ttl_seconds
        # cache_file path -> monotonic timestamp of the last failed live fetch.
        self._fetch_failures: dict[str, float] = {}

    def _cache_is_fresh(
        self, cache_file: Path, max_age_seconds: float | None
    ) -> bool:
        if not cache_file.exists():
            return False
        ttl = self.cache_ttl_seconds if max_age_seconds is None else max_age_seconds
        return (time.time() - cache_file.stat().st_mtime) < ttl

    def _in_failure_cooldown(self, cache_file: Path) -> bool:
        """True when a recent live fetch for this cache file failed."""
        failed_at = self._fetch_failures.get(str(cache_file))
        return failed_at is not None and (
            time.monotonic() - failed_at < self.FAILURE_COOLDOWN_SECONDS
        )

    def _record_fetch_failure(self, cache_file: Path) -> None:
        self._fetch_failures[str(cache_file)] = time.monotonic()

    def _record_fetch_success(self, cache_file: Path) -> None:
        self._fetch_failures.pop(str(cache_file), None)

    def fetch_json(
        self, url: str, max_age_seconds: float | None = None
    ) -> dict[str, Any]:
        cache_file = self._cache_file(url)
        if self._cache_is_fresh(cache_file, max_age_seconds):
            return json.loads(cache_file.read_text())

        # Batch 76 (serve-stale-on-error): a stale on-disk snapshot is far
        # better than a 500. company_tickers.json in particular changes rarely
        # enough that a hours-old copy resolves CIKs just fine.
        if cache_file.exists() and self._in_failure_cooldown(cache_file):
            logger.warning(
                "SEC fetch for %s failed recently; serving stale cache", url
            )
            return json.loads(cache_file.read_text())

        try:
            self._throttle()
            response = self._get(url)
            response.raise_for_status()
            self._last_request_at = time.monotonic()

            data = response.json()
            cache_file.write_text(json.dumps(data))
            self._record_fetch_success(cache_file)
            return data
        except Exception:
            if cache_file.exists():
                logger.warning(
                    "SEC fetch for %s failed; serving stale cache",
                    url,
                    exc_info=True,
                )
                self._record_fetch_failure(cache_file)
                return json.loads(cache_file.read_text())
            self._record_fetch_failure(cache_file)
            raise

    def fetch_text(
        self, url: str, max_age_seconds: float | None = None
    ) -> str:
        """Fetch a non-JSON URL (e.g. filing index HTML) with caching."""
        cache_file = self._cache_file(url).with_suffix(".html")
        if self._cache_is_fresh(cache_file, max_age_seconds):
            return cache_file.read_text()

        # Same serve-stale-on-error contract as fetch_json (batch 76): filing
        # document URLs are immutable, so a stale copy is identical content.
        if cache_file.exists() and self._in_failure_cooldown(cache_file):
            logger.warning(
                "SEC fetch for %s failed recently; serving stale cache", url
            )
            return cache_file.read_text()

        try:
            self._throttle()
            response = self._get(url)
            response.raise_for_status()
            self._last_request_at = time.monotonic()

            text = response.text
            cache_file.write_text(text)
            self._record_fetch_success(cache_file)
            return text
        except Exception:
            if cache_file.exists():
                logger.warning(
                    "SEC fetch for %s failed; serving stale cache",
                    url,
                    exc_info=True,
                )
                self._record_fetch_failure(cache_file)
                return cache_file.read_text()
            self._record_fetch_failure(cache_file)
            raise

    def filing_index_url(self, cik: str | int, accession: str) -> str:
        """Return the EDGAR archive index URL for a filing."""
        acc_clean = accession.replace("-", "")
        cik_num = str(int(normalize_cik(cik)))
        return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/"

    def company_tickers(self) -> dict[str, Any]:
        return self.fetch_json(SEC_TICKERS_URL)

    def cik_for_ticker(self, ticker: str) -> str:
        ticker_upper = ticker.upper()
        tickers = self.company_tickers()
        for item in tickers.values():
            if item["ticker"].upper() == ticker_upper:
                return normalize_cik(item["cik_str"])
        # Berkshire-style: everyone types BRK.B / BRK/A, SEC lists BRK-B /
        # BRK-A (hyphen). Fall back to the hyphenated form before giving up.
        normalized = ticker_upper.replace(".", "-").replace("/", "-")
        if normalized != ticker_upper:
            for item in tickers.values():
                if item["ticker"].upper() == normalized:
                    return normalize_cik(item["cik_str"])
        raise KeyError(f"Ticker not found in SEC company_tickers.json: {ticker}")

    def submissions(self, cik: str | int, *, fresh: bool = False) -> dict[str, Any]:
        return self.fetch_json(
            SEC_SUBMISSIONS_URL.format(cik=normalize_cik(cik)),
            max_age_seconds=0 if fresh else None,
        )

    def submissions_bucket(
        self, cik: str | int, bucket_name: str, *, fresh: bool = False
    ) -> dict[str, Any]:
        """Fetch one paginated older-submissions file for a CIK.

        The top-level submissions JSON only covers the ``recent`` filings;
        older filings live in ``filings.files`` buckets named like
        ``CIK0000070858-submissions-001.json`` (001 = next-older after
        recent). Batch 97: discover_earnings_filings only read ``recent``,
        so high-volume filers (BAC/C/BLK — recent covers <4 quarters of
        10-Q/10-K) could never match earnings 8-Ks for older quarters.
        """
        return self.fetch_json(
            SEC_SUBMISSIONS_BUCKET_URL.format(bucket=bucket_name),
            max_age_seconds=0 if fresh else None,
        )

    def companyfacts(self, cik: str | int, *, fresh: bool = False) -> dict[str, Any]:
        return self.fetch_json(
            SEC_COMPANYFACTS_URL.format(cik=normalize_cik(cik)),
            max_age_seconds=0 if fresh else None,
        )

    def _cache_file(self, url: str) -> Path:
        key = hashlib.sha256(url.encode()).hexdigest()[:16]
        return self.cache_dir / f"{key}.json"

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_request_interval_seconds:
            time.sleep(self.min_request_interval_seconds - elapsed)

    def _get(self, url: str) -> httpx.Response:
        headers = {"User-Agent": self.user_agent}
        if self._http_client is not None:
            return self._http_client.get(url, headers=headers, timeout=30)
        return httpx.get(url, headers=headers, timeout=30)


def normalize_cik(cik: str | int) -> str:
    return str(cik).strip().zfill(10)


# Curated CIK successions (batch 98): new CIK -> predecessor CIK(s) whose
# companyfacts history continues under the new CIK. Entries are
# human-verified, never guessed (cf. the batch-58 DBA alias map): the XOM
# entry is proven by accession 0000034088-26-000093 (the Q2-2026 10-Q) being
# attributed to BOTH CIKs in their submissions feeds, and by the new CIK's
# Q2-2026 revenue ($116.0B) continuing the old CIK's consolidated run rate.
# Without the merge, XOM seeded only 2 quarters (the new CIK's facts hold
# just the latest 10-Q plus its comparative column).
_CIK_SUCCESSIONS: dict[str, tuple[str, ...]] = {
    "0002115436": ("0000034088",),  # XOM: EXXON MOBIL CORP -> ExxonMobil Holdings Corp
}


def predecessor_ciks(cik: str | int) -> tuple[str, ...]:
    """Predecessor CIKs whose companyfacts history continues under ``cik``."""
    return _CIK_SUCCESSIONS.get(normalize_cik(cik), ())


def companyfacts_with_predecessors(
    edgar_client: EdgarClient, cik: str | int, *, fresh: bool = False
) -> dict[str, Any]:
    """companyfacts for ``cik`` merged with predecessor-CIK histories.

    Module-level (not a client method) so callers can pass any client-like
    object — tests stub ``companyfacts`` on a MagicMock. SEC occasionally
    moves a ticker to a new CIK on a reorganization or rename (the ticker
    map then resolves to the new CIK), and the new CIK's companyfacts
    history starts at the succession — older quarters live only under the
    predecessor CIK. Merging the predecessor facts in lets the XBRL
    extractor see the full window; on a (start, end, accession) collision
    the two copies are the same filing's facts, so dedupe is value-neutral.
    Latest-filed-wins (per metric, already in xbrl.py) resolves same-period
    facts from different filings, so the merge is no different from an
    amended filing for the extractor.
    """
    cik = normalize_cik(cik)
    merged = edgar_client.companyfacts(cik, fresh=fresh)
    for pred in predecessor_ciks(cik):
        try:
            pred_facts = edgar_client.companyfacts(pred, fresh=fresh)
        except Exception:
            logger.warning(
                "predecessor companyfacts fetch failed for %s", pred, exc_info=True
            )
            continue
        merged = _merge_companyfacts(pred_facts, merged)
    return merged


def _merge_companyfacts(
    pred_facts: dict[str, Any], cur_facts: dict[str, Any]
) -> dict[str, Any]:
    """Union two companyfacts payloads, keeping ``cur_facts`` metadata.

    Facts merge at (namespace, concept, unit), deduped by (start, end,
    accession): the same filing's facts under both CIKs collapse to one
    copy, and facts unique to either CIK survive. The ``start`` leg of the
    key is load-bearing — one 10-Q files both the standalone-quarter fact
    and the YTD fact for the same period end (Q2 = 6M − Q1 derivation needs
    both), so an (end, accession) key would silently drop the YTD leg and
    kill every Q2/Q3 derivation. ``cur_facts``' top-level metadata (cik,
    entityName) is authoritative — it is the current filer. Neither input
    is mutated.
    """
    merged_facts: dict[str, Any] = copy.deepcopy(cur_facts.get("facts") or {})
    for ns, concepts in (pred_facts.get("facts") or {}).items():
        target_ns = merged_facts.setdefault(ns, {})
        for concept, payload in (concepts or {}).items():
            target = target_ns.setdefault(concept, {"units": {}})
            target_units = target.setdefault("units", {})
            for unit, facts in ((payload or {}).get("units") or {}).items():
                existing = target_units.setdefault(unit, [])
                seen = {
                    (f.get("start"), f.get("end"), f.get("accn")) for f in existing
                }
                for fact in facts or []:
                    key = (fact.get("start"), fact.get("end"), fact.get("accn"))
                    if key in seen:
                        continue
                    seen.add(key)
                    existing.append(copy.deepcopy(fact))
    out = dict(cur_facts)
    out["facts"] = merged_facts
    return out


def most_recent_10q(submissions: dict[str, Any]) -> tuple[str, str]:
    recent = submissions["filings"]["recent"]
    for form, filing_date, accession in zip(
        recent["form"], recent["filingDate"], recent["accessionNumber"]
    ):
        if form == "10-Q":
            return filing_date, accession
    raise ValueError("No 10-Q filing found in SEC submissions response")
