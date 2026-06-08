# Tickerlens

Personal research tool for analyzing US public companies from SEC EDGAR data.

Tickerlens is a single-user tool — no auth, payments, marketing, or multi-user features. If it proves useful after daily use, the productization PRD is archived for revisit.

## Current State

**Phase 2 — Single-company browsing UI** (Phase 1 complete)

Phase 1 delivered end-to-end data flow for one company:
- SEC EDGAR client with rate limiting and disk cache
- XBRL extraction and concept-mapping (revenue tag fallback, YTD un-cumulation, Q4 derivation)
- SQLAlchemy models + Alembic migrations (Company + QuarterlyFinancials)
- Service layer: fetch_and_persist, enrich_company (Wikipedia + Yahoo), get_overview
- FastAPI routes + Jinja2 templates for the company overview page
- Focused tests for XBRL logic and the financials service

## Source Of Truth

- `docs/PRD_Tickerlens.md` — product requirements and scope boundaries
- `docs/PROJECT_STATUS.md` — current phase, decisions, and next tasks
- `docs/ARCHITECTURE.md` — living system description
- `docs/DECISIONS.md` — append-only log of architectural decisions and the WHY
- `docs/AGENT_HANDOFF.md` — concise current-state map for any agent
- `CLAUDE.md` — coding conventions and critical rules

Read `docs/PROJECT_STATUS.md` and `docs/AGENT_HANDOFF.md` before starting new work.

## Project Layout

```text
src/tickerlens/
  config.py              Pydantic settings (EDGAR_USER_AGENT, DATABASE_URL)
  main.py                FastAPI app entry
  data/
    edgar.py             SEC JSON client, cache, throttling, CIK helpers
    xbrl.py              XBRL concept mapping and quarterly metric extraction
    sic.py               SIC code → sector bucket mapping
    wikipedia.py         Company description via Wikipedia API
    yahoo.py             Last price and market cap via yfinance
  models/
    company.py           Company model (CIK as primary key)
    quarterly_financial.py  QuarterlyFinancial model
    database.py          Engine/session/create_tables helpers
  services/
    financials.py        Business service: fetch_and_persist, enrich, get_overview
    ir_download.py       Filing discovery and FY labeling for earnings downloads
  routes/
    company.py           FastAPI handlers (home, overview, refresh)
  templates/             Jinja2 templates (base, index, company/overview, partials)
  static/                CSS, JS, images

tests/
  data/test_xbrl.py      XBRL edge-case tests (fiscal-year inference, YTD un-cumulation)
  services/test_financials.py  Service-layer tests (TTM, YoY, upsert idempotency)

scripts/
  download_earnings.py   Earnings PDF download CLI (Chrome headless)

alembic/versions/        Database migrations
docs/
  PRD_Tickerlens.md      Product requirements
  PROJECT_STATUS.md      Phase tracker
  ARCHITECTURE.md        System architecture
  DECISIONS.md           Architectural decision log
  AGENT_HANDOFF.md       Agent-readable current state
  progress/              Per-phase handoff files (ephemeral)
```

## Critical Rules

- CIK is the canonical company key. Ticker is only a display label.
- Every SEC request must include the configured `EDGAR_USER_AGENT` header.
- EDGAR calls must stay at or below 10 requests per second.
- Raw SEC responses are cached under `.edgar_cache/` (gitignored).
- Financial extraction must go through `data/xbrl.py` concept mapping — never raw XBRL tags in services or routes.
- Routes call services. Services do not make HTTP calls (those live in `data/`).

## Setup

Copy `.env.example` to `.env` and fill in your email:

```bash
cp .env.example .env
# Edit .env: set EDGAR_USER_AGENT=Tickerlens Personal <your-email@example.com>
```

Install dependencies and apply migrations:

```bash
uv sync
uv run alembic upgrade head
```

Run the dev server:

```bash
uv run uvicorn tickerlens.main:app --reload
```

Run tests:

```bash
uv run pytest
```

Download earnings PDFs for a company:

```bash
uv run python scripts/download_earnings.py AAPL --periods 4
```

## Code Review

A pre-commit hook reviews staged changes with Claude before every commit:

```bash
git config core.hooksPath .githooks   # activate once
```

To run a manual review: `/review` in Claude Code.
To skip in an emergency: `SKIP_CLAUDE_REVIEW=1 git commit` or `git commit --no-verify`.
