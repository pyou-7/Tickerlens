# Phase 3 — Scale to All US Public Companies

> **EPHEMERAL FILE.** This file is the handoff for the next agent/session.
> Before deleting or archiving it, run `/phase-complete` to distill all durable
> content into `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, and `CLAUDE.md`.
> Only then move it to `docs/progress/_archive/`.

---

## Phase Goal

Expand the proven single-company experience into a searchable, watchlist-driven research tool covering US public companies, with Range/Compare analysis and ZIP downloads.

---

## What's Done

- [x] Phases 0–2 are complete.
- [x] Single-company EDGAR ingestion, persistence, enrichment, overview, and detail views are working.
- [x] Lightweight per-period PDF export exists; Phase 3 ZIP export remains separate.
- [x] Configurable financial trend chart and lazy-loaded adjusted stock-price chart.
- [x] All-company universe indexing and global combobox search (PRD §4.10) with keyboard navigation and Cmd+K shortcut.
- [x] Multi-company XBRL extraction hardening: dynamic latest-fact tag selection (handles historical concept deprecations like NVDA Revenues and AMZN Capex).
- [x] Full Cash Flow statement: Operating Cash Flow, Capex, and Free Cash Flow across models, migrations, calculations, UI tables, and trend chart.
- [x] Universal balance sheet total liabilities fallback (`Assets - StockholdersEquity`) eliminating missing liabilities.
- [x] Narrative extraction for Management Guidance and Executive Commentary alongside press releases and risk factors.
- [x] End-to-end automated validation suite across 10 diverse public companies (`AAPL`, `MSFT`, `ORCL`, `NVDA`, `TSLA`, `AMZN`, `GOOGL`, `INTC`, `MRVL`, `META`) — 100% pass.
- [x] Watchlist and pinned-company home dashboard (PRD §4.2 / §4.6) with SQLite persistence, pin buttons on company headers, and live home card grid with YoY badges.

---

## What's In-Flight

- [ ] Time Slicer Range and Compare modes (PRD §4.3 & §4.4).

---

## Open Questions

- [ ] Define the incremental refresh cadence and batching strategy for the all-company universe.
- [ ] Confirm whether Range/Compare or ZIP download should take precedence.


---

## Gotchas & Surprises

- SEC CIK remains the canonical key; ticker and company name are searchable labels.
- Bulk EDGAR work must preserve the configured User-Agent, ≤10 requests/second throttling, and raw-response cache.
- Segment revenue remains deferred because `companyfacts` does not expose the required dimensional facts.
- Tag deprecation across years requires dynamically picking tags by maximum `end` date rather than first-match.
- Major filers (ORCL, AMZN) omit explicit `Liabilities` tags; universal accounting identity solves it.

---

## XBRL / EDGAR Edge Cases Found This Phase

- **Tag evolution over time:** NVDA transitioned from `RevenueFromContractWithCustomerExcludingAssessedTax` (stopped 2022) to `Revenues` (runs to 2026). AMZN and NVDA capex transitioned from `PaymentsToAcquirePropertyPlantAndEquipment` to `PaymentsToAcquireProductiveAssets`. First-match tag picking locks into stale facts; tag selection must take the concept with the latest `end` date.
- **Missing Balance Sheet Liabilities:** Filers omitting single `Liabilities` tags or `LiabilitiesNoncurrent` (e.g. AMZN stopped reporting `LiabilitiesNoncurrent` in 2012). Solved via $\text{Liabilities} = \text{Assets} - \text{Equity}$.
- **Non-calendar fiscal years:** Early Jan FY filers need special-casing (`month == 1 and day <= 15`), while Jan–May FY filers (e.g. ORCL `0531`) must not duplicate or shift calendar years.
- **8-K exhibit naming variations:** Companies name press release exhibits differently (`a8-kex991`, `exhibit991.htm`, `meta-...xexhibit991.htm`, `googexhibit991q22026.htm`, `q2fy27pr.htm`). Exhibit matching must support general patterns without matching boilerplate index templates.

---

## Decisions Made This Phase

| Decision | Captured in DECISIONS.md? |
|---|---|
| Concept-tag selection prioritized by latest end date | Yes (2026-09-26) |
| Universal balance-sheet liabilities fallback via accounting identity | Yes (2026-09-26) |
| Addition of Operating Cash Flow, Capex, and Free Cash Flow | Yes (2026-09-26) |
| Guidance and Executive Commentary extraction from 8-K exhibits | Yes (2026-09-26) |
| PRD §4.10 all-company search and global combobox | Yes (2026-09-26) |
| Watchlist & Pinned Companies Dashboard (PRD §4.2 / §4.6) | Yes (2026-09-26) |

---

## Next Agent Instructions

1. Read `CLAUDE.md`, `docs/PRD_Tickerlens.md`, and `docs/ARCHITECTURE.md`.
2. Implement Time Slicer Range and Compare modes (PRD §4.3 & §4.4) to compare multi-quarter trajectories and peer companies on the trend chart.
3. Keep CIK as the canonical company key across all persistence.
4. Do not start Phase 4+ AI, calendar/alerts, or news work.


