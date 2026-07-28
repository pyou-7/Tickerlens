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

---

## What's In-Flight

- [ ] Nothing yet; begin with the company-universe and ingestion design.

---

## Open Questions

- [ ] Define the incremental refresh cadence and batching strategy for the all-company universe.
- [ ] Decide the initial watchlist persistence shape for a single user.
- [ ] Confirm whether Range/Compare or ZIP download should follow search/watchlist work.

---

## Gotchas & Surprises

- SEC CIK remains the canonical key; ticker and company name are searchable labels.
- Bulk EDGAR work must preserve the configured User-Agent, ≤10 requests/second throttling, and raw-response cache.
- Segment revenue remains deferred because `companyfacts` does not expose the required dimensional facts.

---

## XBRL / EDGAR Edge Cases Found This Phase

None yet.

---

## Decisions Made This Phase

| Decision | Captured in DECISIONS.md? |
|---|---|
| None yet | — |

---

## Next Agent Instructions

1. Read `CLAUDE.md`, `docs/PRD_Tickerlens.md`, and `docs/ARCHITECTURE.md`.
2. Read `docs/PROJECT_STATUS.md` and PRD §4.10 before designing company search.
3. Start with a bounded company-universe/ingestion design that preserves CIK as canonical.
4. Do not start Phase 4+ AI, calendar/alerts, or news work.
