# Project Status

This file is a living document. Update it as decisions are made or phases shift.

---

## Current Phase

**Phase 2 — Single-company browsing UI**

Goal: a usable Overview page and Time Slicer detail view for one company, single-period mode first. Range and Compare modes are deferred to Phase 3.

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
  - `tests/` — 36 passing (XBRL + financials service)
- **Phase 2 in progress:**
  - Overview page (PRD §4.1): header, description, latest-quarter KPI cards w/ YoY, TTM snapshot
  - Time Slicer detail view (PRD §4.3): quarterly/yearly selectors, HTMX swap, Plotly revenue+EPS trend, hero KPIs, tabbed Income/Cash Flow tables — single-period mode
  - Disclosures: Risk Factors (from 10-K Item 1A), Press release highlights (from 8-K ex-99 exhibit, per-period)
  - **Valuation signal (PRD §4.11, added 2026-09-28):** PEG-implied target price vs current quote with Strong Buy/Buy/Hold/Sell/Strong Sell signal on the Overview page — the retail-investor shortcut; precursor to Phase 5 AI analysis
- **Defect-hunt fixes (2026-09-28):** unknown ticker now renders a friendly 404 page instead of a 500 (`_resolve_cik` converts EDGAR `KeyError` → `CompanyNotFoundError`); Wikipedia enrichment tolerates `httpx.InvalidURL` so a broken proxy config no longer 500s refresh; transient Yahoo quote failures no longer wipe a stored `last_price`/`market_cap` (never-wipe policy, matching risk factors / press-release highlights); **batch 2:** bracketed IPv6 literals in `no_proxy` (injected by the runtime) crashed *every* `httpx.Client()` construction — fixed at the root via `data/proxy_env.py::sanitize_proxy_env()` on package import, instead of swallowing the exception per call site

---

## What's next (concrete Phase 2 tasks)

1. ~~**Balance Sheet tab** in the detail view~~ *(done — merged in PR #1)*
2. ~~**QoQ toggle** on the hero KPI row~~ *(done — merged in PR #2)*
3. ~~**Detail collapsible sections** with Risk Factors extraction~~ *(done — merged in PR #3; press release/guidance/transcript sections show "Not available" pending content sources)*
4. ~~**Press-release highlights content** for the collapsible section~~ *(done 2026-09-27 — extracted from the matched 8-K ex-99 exhibit via `services/ir_download.py` infra; stored per-period on `quarterly_financials`, populated during `enrich_company`, shown for the selected period)*
5. ~~**Valuation signal & target price** (PRD §4.11, added 2026-09-28)~~ *(done 2026-09-28 — `services/valuation.py` PEG-implied P/E target vs Yahoo quote, Strong Buy→Strong Sell signal card on Overview; sales-based fallback for unprofitable companies)*
6. ~~**Sticky Download button** in the detail view (PRD §4.3 #7)~~ *(done 2026-09-28 — sticky per-period CSV export inside the HTMX-swapped region; `GET /company/{ticker}/detail/download` → `{TICKER}_{PERIOD}.csv` with raw metric/value/yoy_pct/qoq_pct. Full-history ZIP stays Phase 3.)*
6. *(deferred)* pin Python to exactly 3.12 in `pyproject.toml requires-python` (currently `>=3.12`).

**Deferred (founder decision 2026-07-10):** Revenue breakdown card (PRD §4.1 #5) — segment revenue is NOT in the `companyfacts` API (verified 2026-07: no dimensional facts; geography tags are annual-only and missing for most filers). Requires a raw-XBRL dimension parser. **Deferred past Phase 2** — do NOT build; revisit after Phase 3. Phase 2 closes without it. Period selector stays detail-view-only (confirmed same date).

Do NOT build Range/Compare modes, search, watchlist, AI analysis, calendar, or news feed — those are Phase 3+.

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
| 2026-09-28 | Sticky per-period CSV download (PRD §4.3 #7) shipped: `GET /company/{ticker}/detail/download` streams `{TICKER}_{PERIOD}.csv`; button lives in the HTMX-swapped partial so it tracks the selected period; CSV chosen over PDF/XLSX (no new deps, numbers stay computable); full-history ZIP stays Phase 3 |
| 2026-09-28 | Defect hunt round 2: yearly-mode YoY now requires two complete 4-quarter years — fixes a bogus +338% YoY on FY2025 revenue (prior year had only 1 quarter seeded); incomplete comparisons render "—" |
| 2026-09-28 | Defect hunt round 1: unknown ticker → friendly 404 page (not 500); refresh POST no longer 500s on Wikipedia network/proxy failure (`httpx.InvalidURL` now swallowed per the module's None-on-error contract); transient Yahoo quote failures no longer wipe stored `last_price`/`market_cap` (extends the never-wipe policy). All HTTP-verified live; suite at 77 passing |
| 2026-09-28 | Valuation signal & target price (PRD §4.11) shipped: PEG-implied P/E target vs current quote, Strong Buy→Strong Sell signal card on Overview, sales-based fallback, Watch on insufficient data |
| 2026-09-27 | Press-release highlights (Phase 2 task 4) implemented: per-period storage on `quarterly_financials`, headline + highlights/lede extraction from 8-K ex-99, populated during `enrich_company`, shown for the selected period (yearly → Q4 row) |
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
- **Phase 2:** Single-company browsing UI (weeks 5–8)
- **Phase 3:** Scale to all US public companies + watchlist + downloads (weeks 9–14)
- **Phase 4:** Earnings calendar + alerts (weeks 15–18)
- **Phase 5:** AI analysis (weeks 19–24)
- **Phase 6:** News feed (weeks 25–28)

Each phase has explicit "done" criteria — don't jump ahead.
