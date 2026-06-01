# Tickerlens

Personal research tool for analyzing US public companies from SEC EDGAR data.

Tickerlens is currently in Phase 1: turning the Phase 0 EDGAR/XBRL notebook findings into reusable application code. The product scope is intentionally personal-use only: no auth, payments, marketing, multi-user features, or commercial polish unless the project is later productized.

## Current State

- Phase 0 EDGAR feasibility passed for AAPL and JNJ.
- Self-built EDGAR parsing remains the chosen path.
- Core notebook logic now exists as reusable modules under `src/tickerlens/`.
- Current extraction target: recent quarterly Revenue, Net Income, EPS, and FCF from SEC `companyfacts`.
- Next build target: local persistence models and migrations for companies plus quarterly financials.

## Source Of Truth

- `docs/PRD_Tickerlens.md`: product requirements and scope boundaries.
- `docs/PROJECT_STATUS.md`: current phase, decisions, and next tasks.
- `docs/AGENT_HANDOFF.md`: short working context for Codex, Claude Code, Gemini, or any other agent.
- `CLAUDE.md`: coding conventions and critical rules.

Read `docs/PROJECT_STATUS.md` and `docs/AGENT_HANDOFF.md` before starting new work.

## Project Layout

```text
src/tickerlens/
  config.py              Pydantic settings
  data/
    edgar.py             SEC JSON client, cache, throttling, CIK helpers
    xbrl.py              XBRL concept mapping and quarterly metric extraction
  services/
    financials.py        Business service composing EDGAR + XBRL

tests/
  data/test_xbrl.py      Focused tests for the highest-risk XBRL logic

notebooks/
  01_edgar_first_look.ipynb
  02_edgar_generalization_jnj.ipynb
```

## Critical Rules

- CIK is the canonical company key. Ticker is only a label.
- Every SEC request must include the configured `EDGAR_USER_AGENT`.
- EDGAR calls must stay at or below 10 requests per second.
- Raw SEC responses are cached under `.edgar_cache/`, which is intentionally gitignored.
- Financial extraction must go through `data/xbrl.py` concept mapping.
- Routes, when added, should call services. Services should not perform raw HTTP except through `data/` clients.

## Setup

Create a local `.env` file:

```text
EDGAR_USER_AGENT=Tickerlens Personal <your-email@example.com>
```

Install dependencies:

```bash
uv sync
```

Run tests:

```bash
uv run pytest
```

Run a quick cached extraction sanity check after `.edgar_cache/` has AAPL/JNJ responses:

```bash
uv run python - <<'PY'
from tickerlens.data.edgar import EdgarClient
from tickerlens.services.financials import FinancialsService

service = FinancialsService(EdgarClient(cache_dir=".edgar_cache"))
for cik in ["0000320193", "0000200406"]:
    rows = service.recent_quarterly_financials(cik)
    print(cik, [(row.period, round(row.revenue or 0), round(row.free_cash_flow or 0)) for row in rows])
PY
```

## Current Limitations

- Python is currently pinned to 3.11 locally; the project plan says to move to 3.12 at the start of Phase 1.
- Persistence, FastAPI routes, templates, and migrations are not added yet.
- XBRL extraction is proven on AAPL and JNJ only; broaden coverage before scaling to all companies.
