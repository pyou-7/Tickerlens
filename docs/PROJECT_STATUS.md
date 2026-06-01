# Project Status

This file is a living document. Update it as decisions are made or phases shift.

---

## Current Phase

**Phase 1 — Data flowing for one company**

Goal: turn the Phase 0 notebook findings into reusable EDGAR/XBRL modules and local storage for one company.

---

## What's done

- PRD written and refined (`docs/PRD_Tickerlens.md` — v1.0 personal scope)
- Working context captured in `CLAUDE.md`, `README.md`, and `docs/AGENT_HANDOFF.md`
- Stack chosen and locked (see `CLAUDE.md`)
- Project structure planned
- Claude Code context configured (`CLAUDE.md` + `.claude/`)
- Phase 0 EDGAR feasibility passed with AAPL and JNJ notebooks
- Multi-agent handoff docs added (`README.md`, `docs/AGENT_HANDOFF.md`, `CLAUDE.md`)

---

## What's next (concrete tasks)

1. ~~Initialize the `uv` project skeleton~~ *(minimal setup done: .env, .gitignore, pyproject.toml, deps)*
2. ~~Create `notebooks/01_edgar_first_look.ipynb`~~ *(created; smoke test passing)*
3. ~~Pull Apple's most recent 10-Q from SEC EDGAR using the `companyfacts` API~~ *(done in `notebooks/01_edgar_first_look.ipynb`)*
4. ~~Extract Revenue, Net Income, EPS, FCF for the most recent 4 quarters~~ *(done for AAPL and JNJ)*
5. ~~Repeat for one company in a different sector (e.g., JNJ healthcare, JPM finance) — compare XBRL tagging differences~~ *(done in `notebooks/02_edgar_generalization_jnj.ipynb`)*
6. ~~**Decision gate:** is self-built EDGAR parsing tractable in a personal-time budget, or pivot to a paid API (FMP, Finnhub paid)?~~ *(continue self-built EDGAR into Phase 1)*
7. Pin Python to 3.12 at start of Phase 1 (currently 3.11.9 via Anaconda)
8. ~~Start Phase 1 project skeleton under `src/tickerlens/`, beginning with `data/edgar.py` and `data/xbrl.py`~~ *(done; reusable EDGAR client, XBRL mapper, financials service, and XBRL tests added)*
9. Add local persistence models and migrations for companies + quarterly financials

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
