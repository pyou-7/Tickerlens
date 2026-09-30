# Agent Handoff

This project is being built iteratively across Codex, Claude Code, Gemini, and the founder. Keep this file current when changing architecture, phase, or important assumptions.

## Current Phase

Phase 2: single-company browsing UI.

Phase 1 is complete. Data flows end-to-end for one company: EDGAR fetch → XBRL extract → SQLite upsert → FastAPI overview page. All Phase 1 files are committed.

## What Exists Now

### Data layer (`src/tickerlens/data/`)

- **`edgar.py`** — SEC JSON client. Requires `EDGAR_USER_AGENT` env var. Caches raw JSON by URL hash under `.edgar_cache/`. Throttles uncached requests to ≤10/sec. Provides CIK normalization, ticker lookup, submissions, and companyfacts.
- **`xbrl.py`** — Central concept-mapping layer. Extracts recent quarterly Revenue, Net Income, EPS Basic, EPS Diluted, and FCF. Handles revenue tag fallback chain (post- and pre-ASC 606). Un-cumulates cash-flow YTD facts into standalone quarters; the 9M YTD window floor is 240 days (covers 52/53-week filers like Costco, whose 36-week 9M fact is 251 days). CAPEX fallback chain: `PaymentsToAcquirePropertyPlantAndEquipment` → `PaymentsToAcquireProductiveAssets` (NVDA) → `PaymentsToAcquireOtherPropertyPlantAndEquipment` (LLY files "Capital expenditures" under this tag; never filed the classic tag). Derives Q4 from FY − 9M. Joins metrics by period `end` date (not `fy/fp` label). Tag-abandonment rule: a tag whose newest fact lags the chain's freshest by >180 days is skipped (catches recent switches like O's `NetIncomeLoss`→common-stockholders tags). Missing total-liabilities *or* total-equity instants are derived from the accounting identity (Assets = Liabilities + Equity) when the filer reports no such tag (LLY liabilities, V equity); assets is never derived.
- **`sic.py`** — Maps SIC codes to simplified sector buckets for the UI.
- **`wikipedia.py`** — Fetches company description via Wikipedia API; graceful fallback if result is under 50 words.
- **`yahoo.py`** — Last price and market cap via yfinance.

### Models layer (`src/tickerlens/models/`)

- **`company.py`** — `Company` model; CIK (String(10)) as PK; ticker is a display label, not a join key.
- **`watchlist.py`** — `WatchlistEntry` model; CIK PK + `added_at` + nullable 280-char `note` (PRD §4.6, notes slice); home-screen pins.
- **`quarterly_financial.py`** — `QuarterlyFinancial` model; unique constraint on `(cik, period_end)`. Holds per-period `press_release_highlights` (Text) + `press_release_source` (String(64)), populated by `enrich_company` from the period's 8-K ex-99 exhibit (None = not available).
- **`database.py`** — `get_engine`, `get_session`, `create_tables` helpers.
- **`base.py`** — `DeclarativeBase`.

### Services layer (`src/tickerlens/services/`)

- **`financials.py`** — `FinancialsService`: `fetch_and_persist` (EDGAR→XBRL→SQLite), `enrich_company` (Wikipedia + Yahoo enrichment, plus Item 1A risk factors and per-period press-release highlights — both best-effort, never wipe good values on failure), `get_overview` (returns `CompanyOverview` Pydantic model for the Overview page), `get_detail` (returns `DetailContext` for the time slicer), `get_compare` (returns `CompareContext`: two `PeriodData`s + `CompareDeltas` for the compare page, PRD §4.2), `get_valuation` (valuation inputs from stored rows + quote, no network), `watch_ticker` / `unwatch_ticker` / `is_watching` / `get_watchlist` (watchlist CRUD + home-screen rows with live signals) + `set_watchlist_note` / `get_watchlist_note`; `get_sibling_tickers` ("Also trades as" share-class hint, PRD §4.9 — same-CIK tickers from the cached SEC ticker list, best-effort, never raises); `get_range_zip_entries` (range-view ZIP: per-quarter CSVs + metric × quarters summary, PRD §4.8 slice 3) using the shared `_chart_window()` resolver; `get_year_zip_entries` (single-year ZIP for a fiscal year, per-quarter CSVs + summary, PRD §4.8 slice 4; unknown year → latest fiscal year); `extract_recent_quarterly_financials` fills per-quarter basic-EPS gaps from diluted EPS (GS Q2 2026 case); `_newest_in_window` with a `None` window counts instant facts so the tag-abandonment rule engages for balance-sheet metrics (UNH equity / PG cash case); `_derive_missing_balance_sheet` fills a missing Liabilities *or* Equity instant from the accounting identity (LLY liabilities, V equity — assets never derived). Upserts via `INSERT … ON CONFLICT DO UPDATE`.
- **`valuation.py`** — Pure rules-based valuation (PRD §4.11): `compute_valuation()` → `ValuationSignal` (signal, target price, upside %, confidence, method, reasoning). PEG-implied P/E primary, sales-based fallback, Watch on insufficient data.
- **`ir_download.py`** — Filing discovery, FY labeling, 8-K matching for earnings PDF download. Companion to `scripts/download_earnings.py`. `_pick_release_doc()` (pure, tested) picks the earnings-release exhibit from an 8-K index: ex99-style first, then `*pressrelease*` / `*earningsrelease*` / `-pr`+`_pr` / digit-bearing `…pr` quarter stems (NVDA's `q2fy27pr.htm`), skipping `index.htm`/`R*.htm`.

### Routes layer (`src/tickerlens/routes/`)

- **`company.py`** — `GET /` (home, with watchlist pins), `GET /company/{ticker}` (overview page), `POST /company/{ticker}/refresh` (re-fetch + re-enrich), `GET /company/{ticker}/detail` (time slicer, chart range window via `chart_from`/`chart_to`), `GET /company/{ticker}/compare` (side-by-side two-quarter/two-year compare, PRD §4.2; `period_a`/`period_b` labels or `preset=yoy|qoq|5y`, YoY-ago default), `GET /company/{ticker}/compare/download` (compare-view ZIP: both periods' CSVs + summary CSV, PRD §4.8 slice 2), `GET /api/search` (autocomplete suggestions, PRD §4.10), `POST /watchlist/refresh` (refresh-all quotes, PRD §4.6), `POST /company/{ticker}/watch` + `POST /company/{ticker}/watch/remove` (watchlist toggle, PRD §4.6), `GET /company/{ticker}/detail/download` (per-period CSV, PRD §4.3 #7), `GET /company/{ticker}/download/history.zip` (full-history ZIP of per-period CSVs, PRD §4.8 slice 1), `GET /company/{ticker}/download/range.zip` (range-view ZIP mirroring `chart_from`/`chart_to`, PRD §4.8 slice 3), `GET /company/{ticker}/download/year.zip?year=` (single-year ZIP for a fiscal year, PRD §4.8 slice 4; "⇓ Year (ZIP)" button in the detail view's yearly mode, Alpine-bound href tracks the live year select), `POST /company/{ticker}/watch/note` (watchlist note save/clear, PRD §4.6).

### App entry

- **`src/tickerlens/main.py`** — FastAPI app; mounts `/static` and `templates/`.

### Templates (`src/tickerlens/templates/`)

- `base.html`, `index.html`, `company/overview.html`, `partials/` — Jinja2 templates. Phase 2 will flesh out `company/overview.html` to match PRD Section 4.1.

### Scripts

- **`scripts/download_earnings.py`** — Generalized earnings download CLI. Usage: `uv run python scripts/download_earnings.py TICKER [--periods 4]`. Downloads 8-K ex99 and 10-Q/10-K as PDFs via Chrome headless.

### Tests (`tests/`)

- **`tests/data/test_xbrl.py`** — 40 XBRL tests: fiscal-year inference, tag fallback chains (NVDA/LLY CapEx, MET revenue, O net income), YTD un-cumulation (incl. 52/53-week 9M window), period-end join (JNJ regression), instant-fact staleness (UNH/PG), accounting-identity derivation (LLY liabilities, V equity), diluted→basic EPS fallback (GS).
- **`tests/services/test_financials.py`** — 12 tests for `_pct_change`, `_compute_ttm`, `_compute_yoy`, `get_overview`, and `fetch_and_persist` using in-memory SQLite.

### Migrations (`alembic/versions/`)

- `89c6a34083be_*` — Initial `companies` + `quarterly_financials` schema.
- `44892912880c_*` — Add `description`, `last_price`, `market_cap` columns to `companies`.
- `017aee7df1c1_*` — Add balance-sheet columns to `quarterly_financials`.
- `d1f5704c5e60_*` — Add `risk_factors`, `risk_factors_source` columns to `companies`.
- `7a3e9c1f4b22_*` — Create `watchlist` table (CIK PK + `added_at`).
- `5f1c9a2b7d34_*` — Add nullable `note` (TEXT) to `watchlist`.
- `3049fff86581_*` — Add `press_release_highlights`, `press_release_source` columns to `quarterly_financials`.

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

> Status note (2026-09-27): items 1–3 below are done (see `docs/PROJECT_STATUS.md`
> for the current task list). The remaining Phase 2 work is the sticky Download
> button (PRD §4.3 #7) — keep it to a simple per-period PDF link or defer.

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
