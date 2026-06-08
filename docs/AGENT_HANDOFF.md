# Agent Handoff

This project is being built iteratively across Codex, Claude Code, Gemini, and the founder. Keep this file current when changing architecture, phase, or important assumptions.

## Current Phase

Phase 2: single-company browsing UI.

Phase 1 is complete. Data flows end-to-end for one company: EDGAR fetch → XBRL extract → SQLite upsert → FastAPI overview page. All Phase 1 files are committed.

## What Exists Now

### Data layer (`src/tickerlens/data/`)

- **`edgar.py`** — SEC JSON client. Requires `EDGAR_USER_AGENT` env var. Caches raw JSON by URL hash under `.edgar_cache/`. Throttles uncached requests to ≤10/sec. Provides CIK normalization, ticker lookup, submissions, and companyfacts.
- **`xbrl.py`** — Central concept-mapping layer. Extracts recent quarterly Revenue, Net Income, EPS Basic, EPS Diluted, and FCF. Handles revenue tag fallback chain (post- and pre-ASC 606). Un-cumulates cash-flow YTD facts into standalone quarters. Derives Q4 from FY − 9M. Joins metrics by period `end` date (not `fy/fp` label).
- **`sic.py`** — Maps SIC codes to simplified sector buckets for the UI.
- **`wikipedia.py`** — Fetches company description via Wikipedia API; graceful fallback if result is under 50 words.
- **`yahoo.py`** — Last price and market cap via yfinance.

### Models layer (`src/tickerlens/models/`)

- **`company.py`** — `Company` model; CIK (String(10)) as PK; ticker is a display label, not a join key.
- **`quarterly_financial.py`** — `QuarterlyFinancial` model; unique constraint on `(cik, period_end)`.
- **`database.py`** — `get_engine`, `get_session`, `create_tables` helpers.
- **`base.py`** — `DeclarativeBase`.

### Services layer (`src/tickerlens/services/`)

- **`financials.py`** — `FinancialsService`: `fetch_and_persist` (EDGAR→XBRL→SQLite), `enrich_company` (Wikipedia + Yahoo enrichment), `get_overview` (returns `CompanyOverview` Pydantic model for the Overview page). Upserts via `INSERT … ON CONFLICT DO UPDATE`.
- **`ir_download.py`** — Filing discovery, FY labeling, 8-K matching for earnings PDF download. Companion to `scripts/download_earnings.py`.

### Routes layer (`src/tickerlens/routes/`)

- **`company.py`** — `GET /` (home), `GET /company/{ticker}` (overview page), `POST /company/{ticker}/refresh` (re-fetch + re-enrich).

### App entry

- **`src/tickerlens/main.py`** — FastAPI app; mounts `/static` and `templates/`.

### Templates (`src/tickerlens/templates/`)

- `base.html`, `index.html`, `company/overview.html`, `partials/` — Jinja2 templates. Phase 2 will flesh out `company/overview.html` to match PRD Section 4.1.

### Scripts

- **`scripts/download_earnings.py`** — Generalized earnings download CLI. Usage: `uv run python scripts/download_earnings.py TICKER [--periods 4]`. Downloads 8-K ex99 and 10-Q/10-K as PDFs via Chrome headless.

### Tests (`tests/`)

- **`tests/data/test_xbrl.py`** — 4 focused XBRL tests: fiscal-year inference, tag fallback, YTD un-cumulation, period-end join (JNJ regression).
- **`tests/services/test_financials.py`** — 12 tests for `_pct_change`, `_compute_ttm`, `_compute_yoy`, `get_overview`, and `fetch_and_persist` using in-memory SQLite.

### Migrations (`alembic/versions/`)

- `89c6a34083be_*` — Initial `companies` + `quarterly_financials` schema.
- `44892912880c_*` — Add `description`, `last_price`, `market_cap` columns to `companies`.

## Phase 1 Findings To Preserve

- AAPL and JNJ both work through SEC `companyfacts`.
- Revenue tag for recent filers is `RevenueFromContractWithCustomerExcludingAssessedTax`; fallback chain handles pre-ASC 606.
- EPS unit is `USD/shares`, not `USD`.
- CapEx is `PaymentsToAcquirePropertyPlantAndEquipment` (positive outflow value); FCF = OpCF − CapEx.
- Cash-flow Q2/Q3 facts are often cumulative YTD — un-cumulated in `xbrl.py`.
- Do not rely on XBRL `frame` field; it's absent from recent filings.
- Do not join by `fy/fp` alone; use `end` date as the stable period key.
- `_upsert_company` does NOT overwrite `description`, `last_price`, `market_cap` — those are owned by `enrich_company` to avoid clobbering enrichment data on every refresh.

## Next Recommended Work (Phase 2)

1. Flesh out `templates/company/overview.html` to match PRD Section 4.1 (Overview View):
   - Company header (name, ticker, market cap, sector, last price)
   - Company description
   - Latest quarter KPI cards (Revenue, EPS, Net Income, FCF) with YoY change indicators
   - TTM snapshot
   - "View detailed periods" button (navigates to time slicer)
2. Add the time slicer detail view (PRD Section 4.2–4.3): quarterly/yearly selectors, single/range/compare modes.
3. Add a Plotly chart for revenue + EPS trends.
4. Keep Phase 2 UI-focused. Do NOT add search, watchlist, AI analysis, earnings calendar, or news feed yet.

## Guardrails

- Follow the PRD in `docs/PRD_Tickerlens.md`.
- Keep Phase 2 focused on the single-company UI. Do not jump to Phase 3+ features.
- Do not commit `.env`, `.edgar_cache/`, `.venv/`, `.uv-cache/`, `.pytest_cache/`, generated CSVs, or notebook checkpoints.
- If a new XBRL edge case is found, add it to `.claude/agents/xbrl-specialist.md` and cover it with a focused test.
- Run `/review` before committing significant changes. Run `/phase-complete` when Phase 2 is done.
