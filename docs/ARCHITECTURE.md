# Tickerlens — Architecture

Living document. Update when a design decision changes the system model.
For the *why* behind decisions, see `docs/DECISIONS.md`.

---

## Overview

Tickerlens is a single-user research tool for analyzing US public companies.
It extracts earnings data from SEC EDGAR, stores it locally, and produces AI-driven
factor signals (Invest / Swing / Watch / Avoid) with reasoning.

Stack: Python 3.12, FastAPI, Jinja2, HTMX, Alpine.js, Tailwind (CDN), Plotly,
SQLite → Postgres, SQLAlchemy 2.0, Alembic, httpx, Pydantic v2, APScheduler,
Anthropic Claude SDK. Managed with `uv`.

---

## Layer Diagram

```
Browser
  │  HTML (full page or HTMX fragment)
  ▼
routes/          FastAPI route handlers — return HTML only, no JSON
  │  calls
  ▼
services/        Business logic — orchestrates data/ and models/
  │  calls
  ├─► data/      External data clients (EDGAR, Wikipedia, Yahoo, Finnhub, NAICS)
  └─► models/    SQLAlchemy models (CIK is the canonical company key)
```

**Rules enforced across all layers:**
- Routes never query the DB directly.
- Services never make HTTP calls (those live in `data/`).
- All XBRL tag resolution goes through `data/xbrl.py`'s concept-mapping table.
- No raw EDGAR HTTP calls outside `data/edgar.py`.

---

## Key Files

| File | Role |
|---|---|
| `src/tickerlens/data/edgar.py` | SEC JSON client; throttler (≤10 req/sec); disk cache; CIK helpers |
| `src/tickerlens/data/filings.py` | Best-effort narrative extraction from 10-K and 8-K exhibit HTML |
| `src/tickerlens/data/xbrl.py` | Concept-mapping layer; quarterly metric extraction; YTD un-cumulation; latest-tag prioritization |
| `src/tickerlens/services/financials.py` | Financial persistence, enrichment, overview, and detail-view service boundary |
| `src/tickerlens/services/search.py` | SEC universe indexing, multi-tier ranking, and search query execution |
| `src/tickerlens/services/watchlist.py` | Watchlist card generation, pin/toggle/remove logic, and auto-ingest |
| `src/tickerlens/services/ir_download.py` | Earnings filing discovery and 8-K ex-99 matching |
| `src/tickerlens/models/` | SQLAlchemy 2.0 models (Company, QuarterlyFinancial, WatchlistItem); CIK is the FK |
| `src/tickerlens/ai/` | Rules-based scoring + LLM calls (Claude SDK) |
| `src/tickerlens/jobs/` | APScheduler background tasks |
| `src/tickerlens/routes/` | FastAPI handlers; return Jinja2 HTML or HTMX fragments, with JSON APIs for search/price history |
| `src/tickerlens/routes/search.py` | JSON search suggestions endpoint (`GET /api/search`) |
| `src/tickerlens/routes/watchlist.py` | Pin, toggle, and dashboard HTMX endpoints (`/watchlist`) |
| `src/tickerlens/templates/` | Jinja2 templates; `partials/` for HTMX fragments |


---

## Key Design Decisions

### CIK as canonical company key
SEC CIK (zero-padded 10-digit string) is the primary/foreign key for all company data.
Ticker is a display label stored in a column; it can change or be reused by another company.

### XBRL concept-mapping layer
US GAAP revenue has multiple tag names across companies and years (`SalesRevenueNet`,
`RevenueFromContractWithCustomerExcludingAssessedTax`, etc.). All resolution goes through
`data/xbrl.py` so metrics are comparable across companies and years.

### Period joins anchored on `end` date
Quarterly facts are joined by the period `end` date, not the `fy/fp` XBRL label.
Comparative facts in amended filings can carry misleading fiscal labels.

### Cash-flow YTD un-cumulation
Q2 and Q3 10-Q cash-flow items are often cumulative YTD. `data/xbrl.py` un-cumulates them
into standalone quarterly values (Q2_standalone = H1 − Q1, etc.).

### Q4 derivation
Apple (and many filers) don't file a 10-Q for Q4. Q4 income-statement values are derived:
Q4 = FY_annual (10-K) − Q3_YTD.

### HTMX-first frontend
Routes return HTML. JSON endpoints are only added when explicitly needed.

### Single-period PDF export
The Phase 2 detail view uses the browser print dialog for a lightweight per-period PDF.
Print-only CSS removes app controls, adds company/period context, and includes the required
dated “As of” footer. Multi-document ZIP generation remains a separate Phase 3 workflow.

### Lazy-loaded stock price history
The detail page loads adjusted Yahoo price history after the financial page renders. A validated
JSON endpoint (`GET /company/{ticker}/price-history`) routes through `FinancialsService` to
`data/yahoo.py`; range changes fetch only the selected window. This keeps unreliable market-data
requests out of the initial EDGAR-backed page path and separate from quarterly financial state.

### Dynamic concept-tag selection by latest end date
Companies migrate XBRL concept tags over years (e.g. NVDA moving to `Revenues`, AMZN moving to
`PaymentsToAcquireProductiveAssets`). `data/xbrl.py` prioritizes candidate tags whose facts cover
the latest period `end` date, preventing lock-in to stale historical facts.

### Universal balance sheet liabilities fallback
For companies that omit a single `Liabilities` tag or stop reporting `LiabilitiesNoncurrent`
(e.g., ORCL, AMZN), `data/xbrl.py` derives liabilities using the fundamental identity:
`Liabilities = Total Assets - Stockholders' Equity`, blended with reported liabilities.

### Global universe combobox search (PRD §4.10)
`CompanySearchService` maintains an in-memory index of SEC public companies, loaded once from
EDGAR's ticker file and enriched with market caps. A multi-tiered ranking algorithm (exact ticker,
prefix ticker, prefix company name, word prefix, substring) powers instant suggestions via
`GET /api/search` with Alpine.js keyboard navigation (`Cmd+K`, `↑`/`↓`/`Enter`/`Esc`).

### Watchlist & Pinned Dashboard (PRD §4.2 / §4.6)
Tracked companies are persisted in `watchlist_items` with CIK as the canonical foreign key.
`WatchlistService` aggregates latest quarterly fundamentals (revenue, net income, EPS, FCF) and YoY
trajectories. The home page renders a responsive card grid with 1-click pin/unpin toggling via HTMX,
and company overview/detail headers provide instant pin toggles.

---

## Data Flow — Fetch and Persist One Company

```
EdgarClient.fetch_companyfacts(cik)
  └─► xbrl.extract_quarterly_metrics(facts)
        └─► services/financials.fetch_and_persist(cik)
              └─► DB: upsert Company + QuarterlyFinancials rows
```

---

## External Dependencies

| Service | Purpose | Rate limit |
|---|---|---|
| SEC EDGAR `data.sec.gov` | Company facts, submissions, filings | ≤10 req/sec (enforced in `edgar.py`) |
| SEC EDGAR `archive.sec.gov` | Filing HTML/PDF downloads | ~150ms spacing |
| Wikipedia | Company metadata fallback | polite crawl |
| Yahoo Finance | Latest quote, market cap, and adjusted price history | unofficial API |
| Finnhub (free tier) | Supplemental data | per-plan limits |
| Anthropic Claude API | AI factor signals | per-account limits |

---

## Phase Roadmap (current: Phase 3)

- **Phase 0** Setup + EDGAR exploration ✅
- **Phase 1** Data flowing for one company ✅
- **Phase 2** Single-company browsing UI ✅
- **Phase 3** Scale to all US public companies + watchlist + downloads ← current
- **Phase 4** Earnings calendar + alerts
- **Phase 5** AI analysis
- **Phase 6** News feed
