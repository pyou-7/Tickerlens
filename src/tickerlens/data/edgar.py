import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

from tickerlens.config import get_settings


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


class EdgarClient:
    """SEC EDGAR JSON client with required headers, cache, and throttling."""

    def __init__(
        self,
        user_agent: str | None = None,
        cache_dir: Path | str | None = None,
        min_request_interval_seconds: float = 0.1,
        http_client: httpx.Client | None = None,
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

    def fetch_json(self, url: str) -> dict[str, Any]:
        cache_file = self._cache_file(url)
        if cache_file.exists():
            return json.loads(cache_file.read_text())

        self._throttle()
        response = self._get(url)
        response.raise_for_status()
        self._last_request_at = time.monotonic()

        data = response.json()
        cache_file.write_text(json.dumps(data))
        return data

    def fetch_text(self, url: str) -> str:
        """Fetch a non-JSON URL (e.g. filing index HTML) with caching."""
        cache_file = self._cache_file(url).with_suffix(".html")
        if cache_file.exists():
            return cache_file.read_text()

        self._throttle()
        response = self._get(url)
        response.raise_for_status()
        self._last_request_at = time.monotonic()

        text = response.text
        cache_file.write_text(text)
        return text

    def filing_index_url(self, cik: str | int, accession: str) -> str:
        """Return the EDGAR archive index URL for a filing."""
        acc_clean = accession.replace("-", "")
        cik_num = str(int(normalize_cik(cik)))
        return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_clean}/"

    def company_tickers(self) -> dict[str, Any]:
        return self.fetch_json(SEC_TICKERS_URL)

    def cik_for_ticker(self, ticker: str) -> str:
        ticker_upper = ticker.upper()
        for item in self.company_tickers().values():
            if item["ticker"].upper() == ticker_upper:
                return normalize_cik(item["cik_str"])
        raise KeyError(f"Ticker not found in SEC company_tickers.json: {ticker}")

    def submissions(self, cik: str | int) -> dict[str, Any]:
        return self.fetch_json(SEC_SUBMISSIONS_URL.format(cik=normalize_cik(cik)))

    def companyfacts(self, cik: str | int) -> dict[str, Any]:
        return self.fetch_json(SEC_COMPANYFACTS_URL.format(cik=normalize_cik(cik)))

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


def most_recent_10q(submissions: dict[str, Any]) -> tuple[str, str]:
    recent = submissions["filings"]["recent"]
    for form, filing_date, accession in zip(
        recent["form"], recent["filingDate"], recent["accessionNumber"]
    ):
        if form == "10-Q":
            return filing_date, accession
    raise ValueError("No 10-Q filing found in SEC submissions response")
