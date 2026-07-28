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
- `quarterly_financials` stores core KPIs, balance-sheet values, and per-quarter press-release text/source.

### Services and routes

- `services/financials.py` — fetch/persist, company enrichment, press-release enrichment, overview context, and detail context.
- `services/ir_download.py` — earnings filing discovery, fiscal labeling, and 8-K ex-99 matching.
- `routes/company.py` — home, overview, detail, HTMX detail fragment, and refresh handlers.
- The refresh route performs financial, company, and press-release enrichment. First-visit auto-fetch stays lighter and does not fetch press releases.

### User interface

- Overview: company header/description, latest-quarter KPIs with YoY, TTM snapshot, and link to detail.
- Detail: quarterly/yearly single-period selectors, HTMX swaps, Plotly Revenue/EPS trend, YoY/QoQ hero KPIs, and Income/Cash Flow/Balance Sheet tabs.
- Disclosures: per-quarter press-release text, latest-company risk factors, and explicit unavailable states for guidance/transcripts.
- Sticky Download PDF action: invokes browser print for the selected period, uses print-specific styling, and includes the required dated “As of” footer.
- Full Range/Compare and ZIP export are deliberately Phase 3 work.

### Tests and migrations

- 56 tests pass at Phase 2 closeout.
- Focused coverage exists for XBRL edge cases, filing extraction, financial calculations, persistence, balance sheets, QoQ gaps, and press-release enrichment.
- Latest migration: `6b81522c5e05_add_press_release_columns_to_quarterly_*.py`.

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

1. Design the all-company CIK/ticker/name universe and incremental ingestion workflow.
2. Implement PRD §4.10 global company search using the specified combobox pattern.
3. Add the single-user watchlist/pinned-company state.
4. Add Time Slicer Range and Compare modes.
5. Add the PRD §4.8 ZIP download workflow.

## Guardrails

- Follow `docs/PRD_Tickerlens.md`; record scope changes before implementing them.
- Preserve SEC User-Agent, throttling, and caching rules during bulk ingestion.
- Keep routes → services → data/models separation.
- Do not start Phase 4+ AI, calendar/alerts, or news features.
- Do not commit `.env`, caches, the virtual environment, generated output, or the local database.
- Run focused tests and `/review` before significant commits.
