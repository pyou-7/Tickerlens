# Tickerlens — Architecture

Living document. Update when a design decision changes the system model.
For the *why* behind decisions, see `docs/DECISIONS.md`.

---

## Overview

Tickerlens is a single-user research tool for analyzing US public companies.
It extracts earnings data from SEC EDGAR, stores it locally, and produces AI-driven
factor signals (Invest / Swing / Watch / Avoid) with reasoning.

Stack: Python 3.12, FastAPI, Jinja2, HTMX, Alpine.js, Tailwind (CDN), Plotly,
SQLite → Postgres, SQLAlchemy 2.0, Alembic, httpx, Pydantic v2, APScheduler,
Anthropic Claude SDK. Managed with `uv`.

---

## Layer Diagram

```
Browser
  │  HTML (full page or HTMX fragment)
  ▼
routes/          FastAPI route handlers — return HTML only, no JSON
  │  calls
  ▼
services/        Business logic — orchestrates data/ and models/
  │  calls
  ├─► data/      External data clients (EDGAR, Wikipedia, Yahoo, Finnhub, NAICS)
  └─► models/    SQLAlchemy models (CIK is the canonical company key)
```

**Rules enforced across all layers:**
- Routes never query the DB directly.
- Services never make HTTP calls (those live in `data/`).
- All XBRL tag resolution goes through `data/xbrl.py`'s concept-mapping table.
- No raw EDGAR HTTP calls outside `data/edgar.py`.

---

## Key Files

| File | Role |
|---|---|
| `src/tickerlens/data/edgar.py` | SEC JSON client; throttler (≤10 req/sec); disk cache; CIK helpers |
| `src/tickerlens/data/xbrl.py` | Concept-mapping layer; quarterly metric extraction; YTD un-cumulation |
| `src/tickerlens/services/financials.py` | Service boundary for financial extraction (routes call this) |
| `src/tickerlens/models/` | SQLAlchemy 2.0 models; CIK is the FK on every company join |
| `src/tickerlens/ai/` | Rules-based scoring + LLM calls (Claude SDK) |
| `src/tickerlens/jobs/` | APScheduler background tasks |
| `src/tickerlens/routes/` | FastAPI handlers; return Jinja2 HTML or HTMX fragments |
| `src/tickerlens/templates/` | Jinja2 templates; `partials/` for HTMX fragments |

---

## Key Design Decisions

### CIK as canonical company key
SEC CIK (zero-padded 10-digit string) is the primary/foreign key for all company data.
Ticker is a display label stored in a column; it can change or be reused by another company.

### XBRL concept-mapping layer
US GAAP revenue has multiple tag names across companies and years (`SalesRevenueNet`,
`RevenueFromContractWithCustomerExcludingAssessedTax`, etc.). All resolution goes through
`data/xbrl.py` so metrics are comparable across companies and years.

### Period joins anchored on `end` date
Quarterly facts are joined by the period `end` date, not the `fy/fp` XBRL label.
Comparative facts in amended filings can carry misleading fiscal labels.

### Cash-flow YTD un-cumulation
Q2 and Q3 10-Q cash-flow items are often cumulative YTD. `data/xbrl.py` un-cumulates them
into standalone quarterly values (Q2_standalone = H1 − Q1, etc.).

### Q4 derivation
Apple (and many filers) don't file a 10-Q for Q4. Q4 income-statement values are derived:
Q4 = FY_annual (10-K) − Q3_YTD.

### HTMX-first frontend
Routes return HTML. JSON endpoints are only added when explicitly needed.

---

## Data Flow — Fetch and Persist One Company

```
EdgarClient.fetch_companyfacts(cik)
  └─► xbrl.extract_quarterly_metrics(facts)
        └─► services/financials.fetch_and_persist(cik)
              └─► DB: upsert Company + QuarterlyFinancials rows
```

---

## External Dependencies

| Service | Purpose | Rate limit |
|---|---|---|
| SEC EDGAR `data.sec.gov` | Company facts, submissions, filings | ≤10 req/sec (enforced in `edgar.py`) |
| SEC EDGAR `archive.sec.gov` | Filing HTML/PDF downloads | ~150ms spacing |
| Wikipedia | Company metadata fallback | polite crawl |
| Yahoo Finance | Price data | unofficial API |
| Finnhub (free tier) | Supplemental data | per-plan limits |
| Anthropic Claude API | AI factor signals | per-account limits |

---

## Phase Roadmap (current: Phase 1)

- **Phase 0** Setup + EDGAR exploration ✅
- **Phase 1** Data flowing for one company ✅
- **Phase 2** Single-company browsing UI ← current
- **Phase 3** Scale to all US public companies + watchlist + downloads
- **Phase 4** Earnings calendar + alerts
- **Phase 5** AI analysis
- **Phase 6** News feed
