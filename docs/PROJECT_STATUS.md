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

---

## What's next (concrete Phase 2 tasks)

1. ~~**Balance Sheet tab** in the detail view~~ *(done — instant-fact extraction for assets/liabilities/equity/cash, persisted, with YoY/QoQ; PR on `phase2/balance-sheet-tab`)*
2. **Revenue breakdown card** on the Overview (PRD §4.1 #5) — segment/geography auto-detect (tabbed if both exist, single if one, hidden if neither).
3. **Detail collapsible sections** (PRD §4.3 #6): press-release highlights, guidance, transcript excerpts, risk factors — "Not available for this period" when missing.
4. **Sticky Download button** in the detail view (PRD §4.3 #7).
5. **QoQ toggle** — make QoQ change indicators toggleable instead of always shown.
6. *(deferred)* pin Python to exactly 3.12 in `pyproject.toml requires-python` (currently `>=3.12`).

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
