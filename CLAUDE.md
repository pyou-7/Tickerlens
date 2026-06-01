# Tickerlens — Project Context for Claude Code

## What this is

Tickerlens is a personal research tool for analyzing US public companies. It extracts earnings data from SEC EDGAR, organizes it by quarter/year with a time slicer, and produces AI-driven factor signals (Invest / Swing / Watch / Avoid) with reasoning.

**Audience: just the founder.** No customers, no payments, no auth, no marketing. If commercial scope ever returns, the productization PRD is archived for revisit.

## Source of truth

- **`docs/PRD_Tickerlens.md`** — product requirements. This is the single source of truth for *what* to build.
- **`docs/PROJECT_STATUS.md`** — current build phase, recent decisions, next tasks. Read this at the start of every session.
- **`docs/AGENT_HANDOFF.md`** — concise current implementation notes for Codex, Claude Code, Gemini, and future agents.

If a request conflicts with the PRD, flag it before acting. If the PRD is silent, say so — don't invent.

## Stack (locked)

| Layer | Choice |
|---|---|
| Language | Python 3.12+ |
| Web framework | FastAPI |
| Templating | Jinja2 |
| Interactivity | HTMX + Alpine.js |
| Styling | Tailwind CSS (CDN, no build step) |
| Charts | Plotly |
| Database | SQLite (dev) → Postgres (later) |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| HTTP client | httpx |
| Validation | Pydantic v2 |
| Scheduler | APScheduler |
| AI | Anthropic Claude SDK |
| PDF | WeasyPrint |
| Deps | uv |

## Project layout

```
src/tickerlens/
  data/      external data clients (EDGAR, Wikipedia, Yahoo, Finnhub, NAICS)
  models/    SQLAlchemy models (CIK is canonical key)
  services/  business logic
  ai/        rules-based scoring + LLM calls
  pdf/       PDF + ZIP generation
  jobs/      APScheduler tasks
  routes/    FastAPI routes (return HTML, not JSON)
  templates/ Jinja2 templates (with partials/ for HTMX fragments)
  static/    CSS/JS/img
```

## Current implementation snapshot

- Phase 0 notebooks proved EDGAR `companyfacts` extraction for AAPL and JNJ.
- Reusable Phase 1 logic now lives in:
  - `src/tickerlens/data/edgar.py` — SEC client, cache, rate limit, CIK helpers
  - `src/tickerlens/data/xbrl.py` — concept mapping and quarterly metric extraction
  - `src/tickerlens/services/financials.py` — service boundary for financial extraction
- XBRL joins are anchored by period `end` date, not `fy/fp`, because comparative facts can carry misleading fiscal labels.
- The next build step is local persistence models and migrations for companies + quarterly financials.

## Conventions

- **CIK is canonical.** Ticker is a *label* that lives in a column, can change, can be reused. Every join key on a company is CIK.
- **Three-layer separation:** `routes/` → `services/` → `data/` + `models/`. Routes never query DB directly. Services never make HTTP calls (those live in `data/`).
- **HTMX-first frontend.** Routes return HTML (full pages or fragments). Use JSON endpoints only if explicitly needed.
- **Type hints everywhere.** All function signatures typed. Use Pydantic for any data crossing a boundary (HTTP, files, external APIs).
- **Tests focused, not exhaustive.** Mandatory tests for: `data/xbrl.py`, `ai/rules/*`, `services/financials.py`. Optional everywhere else.
- **Config via Pydantic Settings.** No string-typed env vars.
- **Errors are logged with context.** No silent except-passes.

## Critical rules — do not violate

1. **SEC User-Agent header is required.** Every EDGAR call must include `User-Agent: Tickerlens Personal <contact-email>`. SEC will IP-ban requests without it.
2. **Rate-limit EDGAR to ≤10 req/sec.** Build a throttler in `data/edgar.py`; do not bypass it.
3. **Cache raw filings to disk.** Re-parsing is cheap. Re-downloading is expensive and sometimes throttled.
4. **Never store API keys in code.** Only `.env` (gitignored). Never commit `.env`.
5. **PDF exports include "As of [date]" footer.** Restated financials can change historical values — users must know the snapshot date.
6. **Don't bypass the concept-mapping layer.** XBRL line items use inconsistent tags across companies (`us-gaap:Revenues` vs `us-gaap:SalesRevenueNet` vs `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`). Normalize through `data/xbrl.py`'s mapping table or financials will be inconsistent.

## How to run

```bash
uv sync                                              # install deps
uv run uvicorn tickerlens.main:app --reload          # dev server
uv run pytest                                        # tests
uv run alembic upgrade head                          # apply migrations
uv run alembic revision --autogenerate -m "..."      # create migration
```

## When helping me

1. **Default to following the PRD.** If a request conflicts, flag it and ask before acting.
2. **Respect the current phase.** Read `docs/PROJECT_STATUS.md` — don't build Phase 4 features when we're in Phase 1.
3. **Push back on critical rule violations.** Even if I ask for it.
4. **Use subagents for specialized work:**
   - `xbrl-specialist` for SEC/EDGAR/XBRL questions
   - `prd-guardian` before starting any new feature
   - `code-reviewer` before committing significant changes
5. **Keep functions small and testable.** XBRL parsing is the most bug-prone area in this codebase.
6. **Suggest tests** for changes to mandatory-test files; don't insist for everything else.
7. **Ask one question at a time** when clarifying. Don't drown me in lists.
