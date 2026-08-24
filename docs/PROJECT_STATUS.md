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
  - 60 tests currently passing

---

## What's next (concrete Phase 3 tasks)

1. Build the all-company CIK/ticker/name universe and an incremental ingest workflow.
2. Implement global ticker/company-name search using the PRD §4.10 combobox pattern.
3. Add the single-user watchlist and pinned-company home state.
4. Add Time Slicer Range and Compare modes.
5. Implement the PRD §4.8 ZIP export workflow; keep the Phase 2 print/PDF action as the lightweight single-period option.
6. *(deferred)* pin Python to exactly 3.12 in `pyproject.toml requires-python` (currently `>=3.12`).

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
