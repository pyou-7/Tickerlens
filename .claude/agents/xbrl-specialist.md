# XBRL Specialist — Knowledge Base

Domain expert for SEC EDGAR APIs, XBRL data structures, and financial
data extraction from US public company filings.

## Cash flow statement quirks

### Cumulative YTD reporting
Cash flow items in 10-Qs may be reported as **year-to-date cumulative
totals**, not standalone quarterly values. Apple confirmed this pattern;
it is common across US filers.

**How to detect:** Check whether `Q2 OperatingCashFlow` looks like
Q1+Q2 (cumulative) or just Q2 (standalone). Period length is the signal:
- Q1 standalone: ~90 days (start = fiscal year start)
- H1 cumulative: ~181 days (start = fiscal year start)
- 9M cumulative: ~272 days (start = fiscal year start)
- FY: ~363 days (from 10-K)

**How to fix:** Un-cumulate by subtracting prior YTD from current:
- Q2_standalone = H1 − Q1
- Q3_standalone = 9M − H1
- Q4_standalone = FY − 9M

**Income statement items** (Revenue, Net Income, EPS) are typically
reported as standalone quarters and need no un-cumulation. Always
verify period length before assuming.

### CapEx tag
`PaymentsToAcquirePropertyPlantAndEquipment` is reported as a positive
number (it's a cash outflow tagged as a "payment"). FCF = OpCF − CapEx;
subtract directly, do not negate first.

## Revenue tag migration (ASC 606)
Post-2019: `RevenueFromContractWithCustomerExcludingAssessedTax`
Pre-2019: `SalesRevenueNet`
Apple uses the post-ASC 606 tag exclusively for recent filings.

## EPS units
EPS facts are under `"units": {"USD/shares": [...]}`, not `"USD"`.

## Duplicate facts per period
The same quarter may appear multiple times in `companyfacts` — once
from the original 10-Q and once from the 10-K (which restates/confirms
the quarter). Always deduplicate by taking the latest `filed` date per
`(fy, fp)` pair.

## Q4 not filed in a 10-Q
Apple does not file a 10-Q for Q4. Q4 income statement values must be
derived: Q4 = FY_annual (from 10-K) − Q3_YTD.

## `frame` field is unreliable
Do not use the `frame` field (e.g. `CY2024Q1`) as a primary filter.
It is absent from recently filed documents. Use `fp`, `fy`, `form`,
and period-length instead.
