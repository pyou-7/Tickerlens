# Project Status

This file is a living document. Update it as decisions are made or phases shift.

---

## Current Phase

**Phase 3 — Scale to all US public companies**

Goal: expand beyond one-company browsing with a company universe, global search, watchlist, Range/Compare modes, and ZIP downloads.

---

## What's done

- PRD written and refined (`docs/PRD_Tickerlens.md` — v1.0 personal scope)
- Working context captured in `CLAUDE.md`, `README.md`, and `docs/AGENT_HANDOFF.md`
- Stack chosen and locked (see `CLAUDE.md`)
- Claude Code context configured (`CLAUDE.md` + `.claude/`)
- Phase 0 EDGAR feasibility passed with AAPL and JNJ notebooks
- **Phase 1 complete** — data flows end-to-end for one company:
  - `data/edgar.py`, `data/xbrl.py`, `data/sic.py`, `data/wikipedia.py`, `data/yahoo.py`
  - `models/` (Company, QuarterlyFinancial) + Alembic migrations
  - `services/financials.py` (`fetch_and_persist`, `enrich_company`, `get_overview`, `get_detail`)
  - `tests/` — focused coverage for XBRL, filing extraction, and financials services
- **Phase 2 complete** — single-company browsing UI:
  - Overview page (PRD §4.1): header, description, latest-quarter KPI cards w/ YoY, TTM snapshot
  - Time Slicer detail view (PRD §4.3): quarterly/yearly selectors, HTMX swap, Plotly revenue+EPS trend, and YoY/QoQ KPIs
  - Income Statement, Cash Flow, and Balance Sheet tabs
  - Collapsible press-release highlights, guidance, transcript, and risk-factor sections with explicit missing-data states
  - Per-period sticky Download PDF action using the browser print dialog and a dated snapshot footer
  - 56 tests passing at Phase 2 closeout
- **Phase 3 in progress:**
  - Replaced the congested Revenue/EPS dual-axis chart with a configurable single-metric trend chart covering nine core performance, per-share, and balance-sheet metrics
  - Trend x-axis now uses unique period-end dates, preventing duplicate fiscal labels from collapsing separate quarters
  - Added a lazy-loaded adjusted stock-price chart with Today, 5D, 1M, 6M, YTD, 1Y, 3Y, 5Y, 10Y, and Max ranges
  - Implemented PRD §4.10 all-company universe indexing and global combobox search (`CompanySearchService`, `GET /api/search`, and Alpine.js combobox component in hero and persistent nav) with ranked matching, market-cap tie breaking, and keyboard shortcuts (`Cmd+K`, `↑`/`↓`/`Enter`/`Esc`)
  - **Financial Data & Universal Extraction Hardening:**
    - Corrected `infer_fiscal_year` for January-May fiscal year end filers (e.g. ORCL `0531`), preventing duplicate labels and chronological distortion.
    - Updated `concept_facts` tag selection to automatically pick the candidate tag with the most recent `end` date (e.g. NVDA transitioning to `Revenues` and AMZN/NVDA transitioning to `PaymentsToAcquireProductiveAssets`).
    - Added universal `TOTAL_LIABILITIES` fallback (`Assets - StockholdersEquity`) blended with `LiabilitiesCurrent + LiabilitiesNoncurrent`, eliminating missing balance sheet data.
    - Added `operating_cash_flow` and `capex` to schema, models, financial service, cash flow table, and trend chart.
    - Added regex extractors for `extract_guidance` and `extract_executive_commentary` from 8-K Ex-99 exhibits and wired them into detail disclosures alongside risk factors and press releases.
    - Broadened 8-K exhibit pattern matching in `ir_download.py` to support all filing conventions (`exhibit991`, `q2fy27pr`, `ex99_1`).
    - Added local caching and resilient fallback in `yahoo.py` and `wikipedia.py`.
    - Automated ingestion and validation across 10 US public companies: `AAPL`, `MSFT`, `ORCL`, `NVDA`, `TSLA`, `AMZN`, `GOOGL`, `INTC`, `MRVL`, `META` — 100% passed.
  - **Watchlist & Pinned Companies Dashboard (PRD §4.2 / §4.6):**
    - Created `WatchlistItem` model and migration `cf9ad233f7f8` with CIK foreign key.
    - Implemented `WatchlistService` (`services/watchlist.py`) and routes (`routes/watchlist.py`) for pin, toggle, delete, and dashboard queries.
    - Added interactive `partials/watchlist_button.html` to company overview and detail headers.
    - Built responsive home screen dashboard `partials/pinned_dashboard.html` with card grid showing live stock prices, latest quarters, Revenue, Net Income, EPS, and FCF with YoY badges, and 1-click quick-pin empty state.
    - Validated with automated E2E navigation test script (`scripts/validate_watchlist_dashboard.py`).
  - **Frontend Polish & Visual Typography:**
    - Integrated Inter (sans) and JetBrains Mono (mono) typography with Tailwind configuration.
    - Applied global `tabular-nums` for precise numeric and currency alignment across all financial statements and KPI cards.
    - Added an animated top progress bar (`#htmx-progress`) tracking asynchronous HTMX swaps.
    - Added high-density Table View alongside Card Grid View on the Home Dashboard with `localStorage` persistence.
    - Upgraded search combobox with styled `<kbd>⌘K</kbd>` keycap shortcut affordance.
  - **Time Slicer Compare Mode (PRD §4.2 / §4.4):**
    - Created `ComparisonService` (`services/comparison.py`) and routes (`routes/comparison.py`).
    - Built full-page comparison view (`company/compare.html`) and HTMX chart partial (`partials/compare_chart.html`).
    - Implemented multi-company Plotly overlay chart supporting Revenue Growth YoY %, Net Margin %, FCF Margin %, Revenue, Net Income, FCF, and Diluted EPS.
    - Designed 5-category side-by-side financial benchmarking matrix comparing Market & Valuation, YoY Growth, Profitability & Margins, Core Income/Cash Scale, and Balance Sheet & Liquidity with outperformer leader badges.
    - Added quick-preset groups: Semiconductors (`NVDA, INTC, MRVL`), Big Tech (`AAPL, MSFT, GOOGL, AMZN, META`), Enterprise Cloud (`MSFT, ORCL, AMZN`), AI Ecosystem (`NVDA, MSFT, GOOGL, MRVL`).
    - Added dynamic peer adder/remover pills supporting up to 5 concurrent peers.
    - Validated with E2E automation script `scripts/validate_compare_mode.py`.
  - 89 tests currently passing in test suite.

---

## What's next (concrete Phase 3 tasks)

1. Add Time Slicer Range mode (PRD §4.2 multi-quarter contiguous slicing).
2. Implement the PRD §4.8 ZIP export workflow; keep the Phase 2 print/PDF action as the lightweight single-period option.
3. Build batch ingestion/refresh tooling for universe watchlist coverage.
4. *(deferred)* pin Python to exactly 3.12 in `pyproject.toml requires-python` (currently `>=3.12`).

**Deferred (founder decision 2026-07-10):** Revenue breakdown card (PRD §4.1 #5) — segment revenue is NOT in the `companyfacts` API (verified 2026-07: no dimensional facts; geography tags are annual-only and missing for most filers). Requires a raw-XBRL dimension parser. **Deferred past Phase 2** — do NOT build; revisit after Phase 3. Phase 2 closes without it. Period selector stays detail-view-only (confirmed same date).

Do NOT build AI analysis, calendar/alerts, or the news feed — those remain Phase 4+.

---

## Open decisions

- Final tagline (3 candidates parked in PRD)
- Domain & trademark registration for "Tickerlens"
- Hosting (local Docker on home machine vs. Hetzner $5/mo vs. Vercel free)
- Whether to commercialize — explicitly deferred until tool proves useful

---

## Recent decisions (most recent first)

| Date | Decision |
|---|---|
| 2026-09-26 | Implemented Watchlist & Pinned Companies Dashboard (PRD §4.2 / §4.6) with SQLite persistence, header pin buttons, and home KPI card grid |
| 2026-09-26 | Implemented PRD §4.10 all-company universe indexing, multi-tier ranking, and Alpine.js combobox with `Cmd+K` global keyboard shortcut |

| 2026-09-26 | Added Management Guidance and Executive Commentary extraction from 8-K exhibits; broadened exhibit matching across varied filing conventions |
| 2026-09-26 | Added Operating Cash Flow and Capex to models, financial services, Cash Flow statement tab, and trend chart |
| 2026-09-26 | Implemented universal balance sheet total liabilities fallback (`Assets - StockholdersEquity`) blended with reported liabilities |
| 2026-09-26 | Updated `concept_facts` tag selection to prioritize candidate concept tags by latest period `end` date, solving XBRL tag migration over time |
| 2026-07-27 | Added a separate adjusted stock-price chart backed by a validated lazy-loaded Yahoo history endpoint; financial and market trends remain independent |
| 2026-07-27 | Replaced the Revenue/EPS dual-axis chart with a one-metric-at-a-time selector; use period-end dates for chronological chart positioning |
| 2026-07-27 | Closed Phase 2 after integrating press-release highlights and adding a per-period browser print/PDF action; advanced the project to Phase 3 |
| 2026-07-10 | Deferred the revenue breakdown card past Phase 2 because `companyfacts` lacks dimensional segment data; period selectors remain detail-only |
| 2026-06-29 | Reconciled `PROJECT_STATUS.md` with actual state: Phase 1 complete, Phase 2 (Overview + Time Slicer detail) in progress. Set up a daily scheduled cloud agent that picks one Phase 2 task and opens a PR for review |
| 2026-05-31 | Added `docs/AGENT_HANDOFF.md` as the concise current-state handoff for Codex, Claude Code, Gemini, and future agents |
| 2026-05-31 | Moved Phase 0 notebook logic into reusable modules: `data/edgar.py`, `data/xbrl.py`, and `services/financials.py`; XBRL joins are anchored by period end date |
| 2026-05-31 | Phase 0 EDGAR decision gate passed: AAPL and JNJ both work with `companyfacts`; continue self-built EDGAR into Phase 1, with explicit concept mapping and period-label handling |
| 2026-05-27 | Pivoted scope to personal-use only; productization PRD archived for possible future revival |
| 2026-05-27 | Stack locked: FastAPI + HTMX + Jinja2 + Tailwind + SQLite/Postgres |
| 2026-05-27 | Product name = Tickerlens (pending domain/TM check) |
| 2026-05-27 | Free-data strategy: EDGAR + Wikipedia + Yahoo + NAICS + Finnhub free tier |
| 2026-05-27 | AI analysis ships in v1.0 (not deferred — single-user, no need to gate behind paid tier) |
| 2026-05-27 | 3-year historical depth, 2 selectors (quarterly + yearly), 3 modes (single / range / compare) |
| 2026-05-27 | CIK as canonical company key (not ticker) |

---

## Phase roadmap (reference)

- **Phase 0:** Setup + EDGAR exploration (weeks 0–1)
- **Phase 1:** Data flowing for one company (weeks 1–4)
- **Phase 2:** Single-company browsing UI (weeks 5–8) — complete
- **Phase 3:** Scale to all US public companies + watchlist + downloads (weeks 9–14) — current
- **Phase 4:** Earnings calendar + alerts (weeks 15–18)
- **Phase 5:** AI analysis (weeks 19–24)
- **Phase 6:** News feed (weeks 25–28)

Each phase has explicit "done" criteria — don't jump ahead.
