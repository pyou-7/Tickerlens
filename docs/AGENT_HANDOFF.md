# Agent Handoff

This project is built iteratively across Codex, Claude Code, Gemini, and the founder. Keep this file current when changing architecture, phase, or important assumptions.

## Current Phase

**Phase 3: scale to all US public companies.**

Phases 0–2 are complete. One-company data flows end to end from EDGAR fetch through XBRL normalization and SQLite persistence to the FastAPI Overview and Time Slicer pages.

## What Exists Now

### Data and persistence

- `data/edgar.py` — SEC JSON client with required User-Agent, disk cache, ≤10/sec throttling, CIK helpers, submissions, and companyfacts.
- `data/xbrl.py` — concept mapping, quarterly extraction, cash-flow YTD un-cumulation, Q4 derivation, and period-end joins.
- `data/filings.py` — best-effort 10-K risk-factor and 8-K ex-99 text extraction.
- `data/sic.py`, `data/wikipedia.py`, `data/yahoo.py` — sector, description, price, and market-cap enrichment.
- `models/` — `Company` and `QuarterlyFinancial`, with CIK as the company key and Alembic-managed schema.
- `quarterly_financials` stores core KPIs, balance-sheet values, operating cash flow, capex, guidance, executive commentary, and per-quarter press-release text/source.
- `watchlist_items` stores pinned status, notes, and display order with CIK as foreign key.

### Services and routes

- `services/financials.py` — fetch/persist, company enrichment, press-release enrichment, overview context, and detail context.
- `services/search.py` — SEC universe indexing, multi-tier ranking (exact ticker, prefix ticker, prefix company, word prefix, contains), market-cap tie breaking, and search query execution.
- `services/watchlist.py` — watchlist card generation, pin/toggle/remove logic, and auto-ingest for watched tickers.
- `services/comparison.py` — multi-company peer benchmarking, ratio/margin calculations, outperformer leaderboard, and chronological Plotly multi-trace dataset generation.
- `services/ir_download.py` — earnings filing discovery, fiscal labeling, and 8-K ex-99 matching.
- `routes/company.py` — home, overview, detail, HTMX detail fragment, and refresh handlers.
- `routes/search.py` — `GET /api/search` JSON suggestions endpoint.
- `routes/watchlist.py` — `POST /watchlist/pin/{ticker}`, `POST /watchlist/toggle/{ticker}`, `DELETE /watchlist/{ticker}`, and `GET /watchlist/dashboard`.
- `routes/comparison.py` — `GET /compare` full-page view and `GET /compare/chart` HTMX fragment.
- The refresh route performs financial, company, and press-release enrichment. First-visit auto-fetch stays lighter and does not fetch press releases.

### User interface

- Home page: centered hero search combobox with ranked suggestions, debounced input, keyboard navigation, and responsive Pinned Companies Dashboard card grid & dense table view toggle with `localStorage` persistence, showing live stock prices, latest quarters, Revenue/Net Income/EPS/FCF with YoY badges, and 1-click quick-pin empty state.
- Global navigation: persistent compact search combobox in header on all pages with `Cmd+K` / `Ctrl+K` shortcut, top HTMX progress bar, and persistent Compare Mode link.
- Company Overview and Detail headers: Pin/Watchlist toggle button (`partials/watchlist_button.html`) that swaps state via HTMX without full-page reloads.
- Time Slicer Compare Mode (`company/compare.html` and `partials/compare_chart.html`): side-by-side benchmarking of 2–5 peer companies with dynamic peer chips, presets (Semiconductors, Big Tech, Cloud, AI), multi-trace Plotly chart for 7 normalized metrics (Revenue YoY, Net Margin %, FCF Margin %, Revenue, FCF, Net Income, Diluted EPS), and 5-category financial matrix with leader badges.
- Overview: company header/description, latest-quarter KPIs with YoY, TTM snapshot, and link to detail.
- Detail: quarterly/yearly single-period selectors, HTMX swaps, a configurable one-metric Plotly trend, YoY/QoQ hero KPIs, and Income/Cash Flow/Balance Sheet tabs with `tabular-nums` formatting and FCF highlights.
- A separate stock-price chart lazy-loads adjusted Yahoo history from `GET /company/{ticker}/price-history` and supports Today through Max ranges without blocking initial detail-page rendering.
- The trend selector covers Revenue, Net Income, OCF, Capex, FCF, EPS Basic/Diluted, Assets, Liabilities, Equity, and Cash. Its x values are unique period-end dates; month/year labels are display-only.
- Disclosures: per-quarter press-release text, management guidance, executive commentary, latest-company risk factors, and explicit unavailable states for transcripts.
- Sticky Download PDF action: invokes browser print for the selected period, uses print-specific styling, and includes the required dated “As of” footer.
- Full Range mode and ZIP export are Phase 3 tasks.

### Tests and migrations

- 89 tests pass currently (56 at Phase 2 closeout, 4 Yahoo history tests, 7 search service unit tests, 4 search route/template tests, 2 filings tests, 2 watchlist service tests, 6 watchlist route tests, 5 comparison service unit tests, 3 comparison route tests).
- Focused coverage exists for XBRL edge cases, filing extraction, financial calculations, persistence, balance sheets, QoQ gaps, press-release enrichment, search ranking, watchlist management, and peer comparison.
- Latest migration: `cf9ad233f7f8_create_watchlist_items_table.py`.


## Findings To Preserve

- CIK is canonical; ticker is a mutable search/display label.
- Join XBRL metrics by period `end`, not `fy/fp`.
- EPS units are `USD/shares`.
- Q2/Q3 cash flows are often cumulative YTD and must be un-cumulated.
- Q4 commonly requires FY minus nine-month YTD derivation.
- Instant balance-sheet facts have `end` but no `start`; do not pass them through duration extraction.
- Stored enrichment is only overwritten on successful extraction so transient network failures do not erase good data.
- Segment/geography revenue is not available reliably from `companyfacts`; raw XBRL dimensional parsing is deferred past Phase 3.

## Next Recommended Work

1. Add Time Slicer Range and Compare modes (PRD §4.3 & §4.4).
2. Add the PRD §4.8 ZIP download workflow.
3. Build batch ingestion/refresh tooling for universe watchlist coverage.


## Guardrails

- Follow `docs/PRD_Tickerlens.md`; record scope changes before implementing them.
- Preserve SEC User-Agent, throttling, and caching rules during bulk ingestion.
- Keep routes → services → data/models separation.
- Do not start Phase 4+ AI, calendar/alerts, or news features.
- Do not commit `.env`, caches, the virtual environment, generated output, or the local database.
- Run focused tests and `/review` before significant commits.
