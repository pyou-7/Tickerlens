# Phase 2 — Single-Company Browsing UI

Archived at completion on 2026-07-27. Durable architecture and decisions were promoted to `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `CLAUDE.md`, and `docs/AGENT_HANDOFF.md`.

## Phase Goal

Deliver a usable Overview and Time Slicer detail experience for one company, with quarterly/yearly single-period selection.

## Completed

- Company Overview with metadata, description, latest-quarter KPIs, YoY changes, and TTM snapshot.
- Time Slicer with quarterly/yearly selectors and HTMX period swaps.
- Revenue/EPS trend chart and YoY/QoQ hero KPIs.
- Income Statement, Cash Flow, and Balance Sheet tabs.
- Collapsible press-release, guidance, transcript, and risk-factor sections with explicit missing-data states.
- Per-quarter 8-K ex-99 press-release extraction and latest-10-K risk-factor extraction.
- Sticky per-period browser print/PDF action with a dated “As of” footer.
- 56 passing tests at closeout.

## Deferred

- Range and Compare modes, company search, watchlist, and ZIP download moved to Phase 3.
- Revenue breakdown remains deferred past Phase 3 because SEC `companyfacts` lacks reliable dimensional segment data.
- Guidance and transcript content sources remain unresolved; the UI intentionally shows “Not available for this period.”

## Decisions

- Browser print is the Phase 2 single-period PDF path; server-side ZIP generation remains Phase 3.
- Period selectors stay on the detail view only.
