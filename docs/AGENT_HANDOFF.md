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
- `filing_events` stores discovered 10-Q, 10-K, and 8-K filings with CIK, form, filing date, accession number, and processing status.

### Services and routes

- `services/financials.py` — fetch/persist, company enrichment, press-release enrichment, overview context, detail context, and earnings surprises matching.
- `services/search.py` — SEC universe indexing, multi-tier ranking (exact ticker, prefix ticker, prefix company, word prefix, contains), market-cap tie breaking, and search query execution.
- `services/watchlist.py` — watchlist card generation, pin/toggle/remove logic, and auto-ingest for watched tickers.
- `services/comparison.py` — multi-company peer benchmarking, ratio/margin calculations, outperformer leaderboard, and chronological Plotly multi-trace dataset generation.
- `services/ingestion.py` — batch orchestration for single tickers, watchlists, DB universe, and curated tech leaders with rate limiting and progress callbacks.
- `services/filing_watcher.py` — automated polling service detecting new 10-Q/10-K/8-K filings via EDGAR submissions, automatic seeding of baseline filings, and automated background refresh triggers.
- `services/ir_download.py` — earnings filing discovery, fiscal labeling, and 8-K ex-99 matching.
- `routes/company.py` — home, overview, detail, HTMX detail fragment, refresh, and ZIP export handlers.
- `routes/search.py` — `GET /api/search` JSON suggestions endpoint.
- `routes/watchlist.py` — `POST /watchlist/pin/{ticker}`, `POST /watchlist/toggle/{ticker}`, `DELETE /watchlist/{ticker}`, and `GET /watchlist/dashboard`.
- `routes/watcher.py` — `POST /watcher/check` (HTMX scan trigger returning animated alert banner) and `GET /watcher/status` (JSON audit of recent filing events).
- `routes/comparison.py` — `GET /compare` full-page view and `GET /compare/chart` HTMX fragment.
- `scripts/poll_filings.py` — CLI daemon for automated SEC filing checks, single-run audits, and daemon mode.
- `scripts/refresh_universe.py` — CLI for batch universe updates, watchlist maintenance, dry-run inspection, and JSON output.
- The refresh route performs financial, company, and press-release enrichment. First-visit auto-fetch stays lighter and does not fetch press releases.

### User interface

- Home page: centered hero search combobox with ranked suggestions, debounced input, keyboard navigation, and responsive Pinned Companies Dashboard card grid & dense table view toggle with `localStorage` persistence, showing live stock prices, latest quarters, Revenue/Net Income/EPS/FCF with YoY badges, 1-click quick-pin empty state, and "⚡ Scan Filings" button with animated alert banner.
- Global navigation: persistent compact search combobox in header on all pages with `Cmd+K` / `Ctrl+K` shortcut, top HTMX progress bar, persistent Compare Mode link, and Dark/Light/System theme segmented controller.
- Theme System: Zero-FOUC inline script in `<head>`, persistent `localStorage` theme state, Tailwind `class` dark mode throughout all views, and `theme-changed` custom event bus that triggers Plotly canvas/palette recoloring.
- Company Overview and Detail headers: Pin/Watchlist toggle button (`partials/watchlist_button.html`) that swaps state via HTMX without full-page reloads.
- Time Slicer Compare Mode (`company/compare.html` and `partials/compare_chart.html`): side-by-side benchmarking of 2–5 peer companies with dynamic peer chips, presets (Semiconductors, Big Tech, Cloud, AI), search combobox in "Add Peer", multi-trace Plotly chart for 7 normalized metrics (Revenue YoY, Net Margin %, FCF Margin %, Revenue, FCF, Net Income, Diluted EPS), client-side Alpine controller (`compareChart()`) with sub-5ms metric switching, trace visibility toggles in the legend, "Aligned Quarters" vs "Calendar Dates" alignment switcher, and 5-category financial matrix with sticky headers and column hover highlighting.
- Overview: company header/description, latest-quarter KPIs with YoY, TTM snapshot, and link to detail.
- Detail: quarterly/yearly single-period selectors, HTMX swaps, a configurable one-metric Plotly trend, YoY/QoQ hero KPIs, and Income/Cash Flow/Balance Sheet tabs with `tabular-nums` formatting and FCF highlights.
- Chart Milestone Annotations: Plotly detail trend chart integrates historical earnings surprise badges (green `▲ +X.X%` beats, red `▼ -X.X%` misses), filing dates, and hover details, with a "✨ Milestones" toggle toolbar button.
- Time Slicer Range Mode: contiguous multi-quarter and multi-year slicing via `RangeSummary`, dynamic "From" and "To" selectors, Cumulative Revenue / Net Income / FCF Hero KPI cards with span growth and margins, and multi-period comparative statement columns with sticky metric headers and total summary columns.
- One-Click Earnings ZIP Export Archive: in-memory streaming ZIP generation (`GET /company/{ticker}/export-zip`) bundling complete financial statement CSVs, primary source disclosures (8-K releases, guidance, executive remarks), risk factors, and `README.txt`.
- A separate stock-price chart lazy-loads adjusted Yahoo history from `GET /company/{ticker}/price-history` and supports Today through Max ranges without blocking initial detail-page rendering.
- The trend selector covers Revenue, Net Income, OCF, Capex, FCF, EPS Basic/Diluted, Assets, Liabilities, Equity, and Cash. Its x values are unique period-end dates; month/year labels are display-only.
- Disclosures: per-quarter press-release text, management guidance, executive commentary, latest-company risk factors, and explicit unavailable states for transcripts.
- Sticky Action Pill: invokes browser print for PDF export and triggers one-click ZIP download archive.

### Tests and migrations

- 112 tests pass currently (100% pass rate, zero regressions across filings, xbrl, yahoo, search, financials, watchlist, comparison, routes, range mode, zip export, batch ingestion, and filing watcher).
- Comprehensive end-to-end automation scripts: `scripts/validate_range_and_zip.py`, `scripts/validate_compare_mode.py`, `scripts/validate_10_companies.py`, and `scripts/validate_watchlist_dashboard.py`.
- Latest migrations: `440259fd9128_create_filing_events_table.py` (filing events), `cf9ad233f7f8_create_watchlist_items_table.py` (watchlist items).


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

1. Advanced Export customization (custom CSV deltas, user-configurable metrics).
2. Additional peer presets and export formatting options.


## Guardrails

- Follow `docs/PRD_Tickerlens.md`; record scope changes before implementing them.
- Preserve SEC User-Agent, throttling, and caching rules during bulk ingestion.
- Keep routes → services → data/models separation.
- Do not start Phase 4+ AI, calendar/alerts, or news features.
- Do not commit `.env`, caches, the virtual environment, generated output, or the local database.
- Run focused tests and `/review` before significant commits.

