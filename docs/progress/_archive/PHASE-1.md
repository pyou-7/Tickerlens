# Phase 1 — Data Flowing for One Company

> **EPHEMERAL FILE.** Run `/phase-complete` before archiving.
> Distill durable content into `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, and `CLAUDE.md` first.

---

## Phase Goal

Turn Phase 0 notebook findings into reusable application code and persist company + quarterly financial data locally. One company (AAPL) end-to-end: EDGAR fetch → XBRL extract → SQLite upsert → FastAPI overview page.

---

## What's Done

- **`src/tickerlens/data/edgar.py`** — SEC JSON client; rate-limit (≤10 req/sec); disk cache under `.edgar_cache/`; CIK normalization; ticker→CIK lookup; submissions + companyfacts endpoints.
- **`src/tickerlens/data/xbrl.py`** — Concept-mapping layer; revenue tag fallback chain; quarterly metric extraction; YTD cash-flow un-cumulation; Q4 derivation from FY − 9M; period join anchored on `end` date.
- **`src/tickerlens/data/sic.py`** — SIC code → simplified sector bucket mapping.
- **`src/tickerlens/data/wikipedia.py`** — Company description via Wikipedia API; graceful fallback if under 50 words.
- **`src/tickerlens/data/yahoo.py`** — Last price and market cap via yfinance.
- **`src/tickerlens/models/company.py`** — `Company` model; CIK as PK (String(10)).
- **`src/tickerlens/models/quarterly_financial.py`** — `QuarterlyFinancial` model; unique constraint on `(cik, period_end)`.
- **`src/tickerlens/models/database.py`** — `get_engine`, `get_session`, `create_tables` helpers.
- **`alembic/versions/89c6a34083be_*.py`** — Initial schema migration.
- **`alembic/versions/44892912880c_*.py`** — Add `description`, `last_price`, `market_cap` columns to `companies`.
- **`src/tickerlens/services/financials.py`** — `FinancialsService`: `fetch_and_persist`, `enrich_company`, `get_overview`; SQLite upsert via `INSERT … ON CONFLICT DO UPDATE`.
- **`src/tickerlens/services/ir_download.py`** — Filing discovery, FY labeling, 8-K matching for earnings download.
- **`src/tickerlens/routes/company.py`** — FastAPI routes: `GET /`, `GET /company/{ticker}`, `POST /company/{ticker}/refresh`.
- **`src/tickerlens/main.py`** — FastAPI app; static files and templates mounted.
- **`src/tickerlens/templates/`** — `base.html`, `index.html`, `company/overview.html`, `partials/`.
- **`tests/data/test_xbrl.py`** — 4 focused XBRL tests: fiscal-year inference, tag fallback, YTD un-cumulation, period-end join.
- **`tests/services/test_financials.py`** — 12 tests for `_pct_change`, `_compute_ttm`, `_compute_yoy`, `get_overview`, `fetch_and_persist`.
- **`scripts/download_earnings.py`** — Generalized earnings download CLI (Chrome headless PDF).
- Python pinned to 3.12.4 (`.python-version`).

---

## What's In-Flight

- Nothing blocking. Phase 1 is complete.

---

## Open Questions

- None blocking Phase 2.
- Deferred: pin Python to exactly 3.12 in `pyproject.toml requires-python` (currently `>=3.12`).

---

## Gotchas & Surprises

- **AVGO fiscal year ends in November** — the FY labeling algorithm in `ir_download.py` handles non-December FY ends correctly (uses period end date, not calendar year).
- **Chrome headless PDF** — must be at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` on macOS. Hardcoded path in `scripts/download_earnings.py`. Not portable to Linux without adjustment.
- **`archive.sec.gov` rate limiting** is separate from the `data.sec.gov` throttler. Raw HTML downloads need ~150ms spacing independently.
- **Duplicate facts in `companyfacts`** — same quarter can appear once from 10-Q and once restated in 10-K. Always deduplicate by taking the latest `filed` date per `(fy, fp)` pair.
- **`_upsert_company` does NOT upsert `description`, `last_price`, `market_cap`** — those are written by `enrich_company` separately to avoid overwriting enrichment data on every refresh.

---

## XBRL / EDGAR Edge Cases Found This Phase

- JNJ duplicate-label regression: comparative facts in 10-K carry prior-year `fy/fp` labels — period-end join is the fix. Covered in `test_recent_quarterly_financials_joins_by_end_date_not_label`.
- AVGO has no separate Q4 10-Q; Q4 derived from FY annual minus 9M YTD (standard pattern, already handled in `xbrl.py`).

---

## Decisions Made This Phase

| Decision | Captured in DECISIONS.md? |
|---|---|
| Chrome headless over WeasyPrint for EDGAR HTML → PDF | ☑ |
| `ir_download.py` in services/ + CLI in scripts/ split | ☑ |
| Period join anchored on `end` date (not `fy/fp`) | ☑ (from Phase 0 carry-over) |

---

## Next Agent Instructions

You are starting Phase 2: single-company browsing UI.

1. Read `CLAUDE.md` and `docs/ARCHITECTURE.md` for project conventions.
2. Read `docs/PRD_Tickerlens.md` Section 4.1 (Overview View) and 4.2 (Time Slicer) — these define the UI spec.
3. Read `docs/PROJECT_STATUS.md` for current open tasks.
4. The FastAPI routes and templates already exist as stubs (`routes/company.py`, `templates/company/overview.html`). Enhance them to match the PRD Overview View spec.
5. Do NOT touch the EDGAR/XBRL data layer unless a bug is found. Do NOT add Phase 3+ features (search, watchlist, AI analysis, alerts).
6. Run `uv run uvicorn tickerlens.main:app --reload` to start the dev server.
