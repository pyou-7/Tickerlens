from tickerlens.data.edgar import EdgarClient, normalize_cik
from tickerlens.data.xbrl import QuarterlyFinancials, extract_recent_quarterly_financials


class FinancialsService:
    """Financial statement extraction service."""

    def __init__(self, edgar_client: EdgarClient | None = None) -> None:
        self.edgar_client = edgar_client or EdgarClient()

    def recent_quarterly_financials(
        self,
        cik: str | int,
        periods: int = 4,
    ) -> list[QuarterlyFinancials]:
        normalized_cik = normalize_cik(cik)
        submissions = self.edgar_client.submissions(normalized_cik)
        companyfacts = self.edgar_client.companyfacts(normalized_cik)
        return extract_recent_quarterly_financials(
            companyfacts,
            fiscal_year_end=submissions.get("fiscalYearEnd"),
            periods=periods,
        )
