# September 27, 2026 — Reliability increment

Scope: repair the highest-priority findings from the project review. No commit or deployment requested; all changes remain local. No new dependencies or schema migration.

## Implemented

- Expiring SEC JSON cache, forced fresh submissions for scans and companyfacts for ingestion. Failed requests preserve existing cache files. Ticker identity maps remain persistently cached for offline browsing; immutable filing text remains cached.
- Durable pending-filing retries, including already-known accessions. Retried filings are not counted as new. Watchlist scans roll back failed sessions and report failed tickers instead of an all-current claim.
- Full-page Time Slicer GET selection preserves query state and synchronizes both ZIP links, PDF accessibility label, print header and filename. Alpine nextTick ensures disabled selectors settle before submission. Fragment endpoint retained.
- Fiscal-year ZIP filtering and validation errors for invalid/partial boundaries. Range ZIP contains quarterly rows for the selected fiscal years, not yearly aggregation.
- Calendar-date comparison default; aligned mode uses relative quarter lags and handles unequal peer history lengths. Actual fiscal labels/dates remain in hover text.
- Correct liabilities/equity display name; legacy internal ratio field retained. EPS surprise badges now identify EPS.
- Single-period ZIP links now filter to the selected quarter/year as well. Calling the export endpoint without boundaries still exports all history.
- Yearly views show available quarter counts and partial-year warnings. Yearly YoY is omitted for mismatched quarter coverage; annual span growth is omitted if either endpoint is partial.

## Validation

Automated and browser checks are recorded below after the final run. SEC network behavior is tested with deterministic HTTP mocks, not a claim that every live provider is healthy. Existing route tests still use local stored company data; isolate those fixtures in future work.

- Final suite: 120 tests passed; one pre-existing Starlette/httpx deprecation warning. `git diff --check` passed.
- Browser: compare opens with calendar ticks; switching to aligned mode renders 7 quarters ago through Latest. Liabilities-to-Equity label and definition are visible.
- Browser: ORCL Single → Range → Yearly changes query parameters, period headings, both ZIP links and PDF label together. Selecting FY2025 updates the range to FY2025–FY2026.
- Browser: partial coverage shows FY2025 4/4 and FY2026 3/4, with incomparable span growth omitted. EPS annotations identify EPS on quarterly charts.
- Browser download: `/Users/patrickyou/Downloads/ORCL_earnings_export.zip`; inspected CSV contains exactly seven rows, Q1–Q4 FY2025 and Q1–Q3 FY2026. No FY2023/FY2024 rows.
- Screenshot: `/private/tmp/tickerlens-reliability-verified.png`. Local preview left running on port 8765.
- Browser print dialog/PDF rendering and a successful live SEC network scan were not exercised. Print headings/filename are server-rendered from the same tested snapshot label. No claim of universal provider availability or exhaustive application correctness.

## Remaining work

Persistent last-success/last-error refresh health and stale badges; ticker-map refresh policy; watcher backoff/daemon liveness; denominator-aware growth presentation; deeper valuation, saved research views, benchmark returns, earnings inbox and revenue breakdowns. EPS matching remains best effort; original filing PDFs are not bundled in ZIPs. Full-page slicer navigation resets chart metric/price range to defaults; preserve these preferences in a future UX increment.
