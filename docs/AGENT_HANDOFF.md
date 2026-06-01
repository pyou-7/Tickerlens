# Agent Handoff

This project is being built iteratively across Codex, Claude Code, Gemini, and the founder. Keep this file current when changing architecture, phase, or important assumptions.

## Current Phase

Phase 1: data flowing for one company.

The immediate goal is to turn the Phase 0 notebook work into reusable application code and then persist company plus quarterly financial data locally.

## What Exists Now

- `src/tickerlens/data/edgar.py`
  - SEC JSON client.
  - Requires `EDGAR_USER_AGENT`.
  - Caches raw JSON responses by URL hash under `.edgar_cache/`.
  - Throttles uncached requests to at most 10/sec.
  - Provides CIK normalization, ticker lookup, submissions, and companyfacts access.

- `src/tickerlens/data/xbrl.py`
  - Central concept mapping layer.
  - Extracts recent quarterly Revenue, Net Income, EPS Basic, EPS Diluted, and FCF.
  - Handles standalone income-statement quarters.
  - Derives Q4 from annual minus 9M YTD when needed.
  - Un-cumulates cash-flow YTD facts into standalone quarters.
  - Joins metrics by period end date, not `fy/fp` label, because comparative facts can carry misleading fiscal labels.

- `src/tickerlens/services/financials.py`
  - Service layer that composes EDGAR and XBRL extraction.
  - This is the boundary future routes should call.

- `tests/data/test_xbrl.py`
  - Covers fiscal-year inference, revenue tag fallback, cash-flow YTD derivation, and the JNJ duplicate-label regression.

## Phase 0 Findings To Preserve

- AAPL and JNJ both work through SEC `companyfacts`.
- Recent revenue tag for both was `RevenueFromContractWithCustomerExcludingAssessedTax`.
- EPS unit is `USD/shares`, not `USD`.
- CapEx is reported as a positive outflow value under `PaymentsToAcquirePropertyPlantAndEquipment`; FCF is `Operating Cash Flow - CapEx`.
- Cash-flow Q2/Q3 facts are often cumulative YTD and must be un-cumulated.
- Do not rely on the XBRL `frame` field.
- Do not join metrics by `fy/fp` alone; use `end` date as the stable period key.

## Next Recommended Work

1. Pin Python to 3.12 and refresh `uv.lock`.
2. Add SQLAlchemy models for companies and quarterly financials using CIK as the canonical key.
3. Add Alembic migrations.
4. Add a service method to fetch, parse, and persist one company.
5. Keep tests focused around `data/xbrl.py` and `services/financials.py`.

## Guardrails

- Follow the PRD in `docs/PRD_Tickerlens.md`.
- Keep Phase 1 focused on data flow and local storage. Do not jump to UI, alerts, AI analysis, or news feed yet.
- Do not commit `.env`, `.edgar_cache/`, `.venv/`, `.uv-cache/`, `.pytest_cache/`, generated CSVs, or notebook checkpoints.
- If a new XBRL edge case is found, add it to this file and cover it with a focused test.
