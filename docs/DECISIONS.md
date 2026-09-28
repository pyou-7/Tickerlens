# Tickerlens — Architectural Decisions

Append-only log. Add a new `##` section for every infra or architectural decision.
Do NOT edit or delete past entries — they record the WHY at the time of the decision.
Git history has the WHAT; this file has the reasoning.

Format:
```
## YYYY-MM-DD — <short title>

**What:** One sentence on what changed or was decided.
**Why:** The motivation — constraint, tradeoff, incident, or requirement.
**Alternatives considered:** What else was evaluated, or "None recorded."
```

---

## 2026-05-27 — Personal-use scope only

**What:** Productization scope removed; Tickerlens is a single-user research tool for the founder.
**Why:** Reduces complexity dramatically — no auth, no payments, no customer support — and lets the tool prove its value before any commercial commitment.
**Alternatives considered:** SaaS from day one (rejected: too much non-product work before value is demonstrated).

---

## 2026-05-27 — Stack locked

**What:** FastAPI + HTMX + Jinja2 + Tailwind (CDN) + SQLite→Postgres + SQLAlchemy 2.0 + Alembic + Anthropic Claude SDK.
**Why:** HTMX-first keeps the frontend simple without a JS build step. SQLite is sufficient for a single-user tool and trivially migrates to Postgres. `uv` for fast, reproducible dep management.
**Alternatives considered:** Django (heavier), Next.js (overkill for single-user), raw SQL (no migration story).

---

## 2026-05-27 — CIK as canonical company key

**What:** SEC CIK (zero-padded 10-digit string) is the primary/foreign key for all company joins.
**Why:** Tickers can change and be reused by different companies. CIK is permanent and issued by the SEC.
**Alternatives considered:** Ticker as primary key (rejected: changes and is reused), CUSIP (not freely available from EDGAR).

---

## 2026-05-31 — Self-built EDGAR parsing over paid API

**What:** Continue building EDGAR extraction in-house rather than switching to a paid data provider (FMP, Finnhub paid).
**Why:** Phase 0 proved AAPL and JNJ work cleanly through `companyfacts`. The concept-mapping layer in `data/xbrl.py` makes tag differences manageable. Paid APIs introduce cost and external dependency.
**Alternatives considered:** Financial Modeling Prep (FMP), Finnhub paid tier — both rejected for cost and lock-in reasons.

---

## 2026-05-31 — Period joins anchored on `end` date, not `fy/fp`

**What:** Quarterly financial metrics are joined by period `end` date, not by XBRL `fy/fp` label.
**Why:** Comparative facts in amended filings can carry misleading fiscal labels. The `end` date is stable across amendments.
**Alternatives considered:** `fy/fp` label join (rejected: caused mismatches with JNJ comparative facts).

---

## 2026-06-07 — Earnings download via Chrome headless PDF conversion

**What:** Added `services/ir_download.py` and `scripts/download_earnings.py` for downloading quarterly earnings materials (8-K ex99, 10-Q, 10-K) from EDGAR and converting to PDF via Chrome headless.
**Why:** WeasyPrint can't faithfully render EDGAR HTML with inline XBRL. Chrome produces well-formatted, paginated PDFs (85–153 pages for typical 10-Q/10-K). The download is a research workflow, not a core app feature, so it lives in `scripts/` with supporting service logic in `services/ir_download.py`.
**Alternatives considered:** WeasyPrint (rejected: poor EDGAR HTML rendering); pdfkit/wkhtmltopdf (rejected: unmaintained, same rendering issues); paid IR data services (rejected: cost, violates free-data strategy).

---

## 2026-06-07 — Pre-push Claude code review system

**What:** Added `.githooks/pre-commit` (Claude diff review), `.claude/agents/code-reviewer.md` (read-only reviewer agent), `.claude/commands/review.md` (/review slash command), docs/ARCHITECTURE.md, docs/DECISIONS.md, and docs/progress/ directory.
**Why:** Catch EDGAR/XBRL regressions, security issues, and undocumented infra changes before they reach git history. Keep the WHY of architectural decisions out of commit messages (which are ephemeral) and into a durable append-only log.
**Alternatives considered:** Manual review discipline (rejected: too easy to skip); GitHub Actions CI review (rejected: no remote CI yet, and hook runs locally at commit time without needing a push).

---

## 2026-07-01 — Balance-sheet columns on `quarterly_financials`

**What:** Migration `017aee7df1c1` adds `total_assets`, `total_liabilities`, `total_equity`, and `cash_and_equivalents` (all `Float`, nullable) to `quarterly_financials`. These are instant (point-in-time) XBRL facts extracted via the new `balance_sheet_metric()` in `data/xbrl.py`, which calls `concept_facts(instant=True)` to accept facts that carry an `end` but no `start`. `PeriodData` now carries `balance_sheet`, `balance_sheet_yoy`, and `balance_sheet_qoq`; for yearly granularity `balance_sheet_qoq` is always `None` and the value is the year's last quarter (point-in-time, not summed).
**Why:** The detail-view Balance Sheet tab was a stub. Balance-sheet items are instantaneous, so they cannot flow through the duration-based income/cash-flow extraction path or be summed for TTM/yearly aggregates — they need their own extractor and join-by-end handling.
**Alternatives considered:** Reusing the duration extractors with a zero-length window (rejected: instant facts have no `start`, so duration filters drop them); deriving liabilities as assets − equity when the `Liabilities` tag is absent (deferred: adds cross-metric coupling; revisit if a target filer omits the tag).

---

## 2026-07-04 — Risk Factors extraction pipeline

**What:** Added `data/filings.py`, a new `data/`-layer module that locates the latest 10-K primary document from an EDGAR submissions payload and best-effort extracts Item 1A "Risk Factors" as plain text (regex boundaries + HTML stripping). Two columns — `risk_factors` (Text) and `risk_factors_source` (String 64) — were added to `companies` in migration `d1f5704c5e60`. Extraction runs inside `enrich_company` as a best-effort step: any failure is logged and returns `(None, None)`, never raising, and only overwrites stored values on success so a transient network error cannot wipe a good value.
**Why:** The detail view's collapsible Risk Factors section (PRD §4.3 #6) needs narrative text, which is absent from the structured `companyfacts` API and lives only in the primary filing HTML. Isolating the fragile HTML parsing in `data/` keeps it testable and lets the UI degrade to "Not available for this period" whenever extraction is uncertain.
**Alternatives considered:** Parsing on every page render (rejected: re-parsing a ~1.5 MB 10-K per HTMX swap is wasteful — persist once on enrichment instead); a full HTML parser dependency like BeautifulSoup (deferred: regex stripping is sufficient for section extraction and avoids a new dependency). Known limitation: `latest_annual_filing` scans only `filings.recent`, not the paginated `filings.files` pages, matching the existing `most_recent_10q` behavior. The 8,000-char cap is hardcoded; may move to config if the future AI layer needs more context.

---

## 2026-09-27 — Press-release highlights stored per-period on QuarterlyFinancial

**What:** "Press release highlights" (PRD §4.3 #6) is extracted from the period's matched 8-K ex-99 exhibit and stored per quarter on `quarterly_financials` (`press_release_highlights` TEXT + `press_release_source` VARCHAR(64)), populated during `enrich_company`, shown for the *selected* period in the detail view (yearly mode uses the year's Q4 row, else the year's latest quarter).
**Why:** The detail view is a time slicer — a company-level "latest release" value would show the wrong quarter's release when viewing older periods. Matching uses `period_end` date (the project's stable period key), not FY/FP labels, because `ir_download`'s FY labeling is a separate system from the XBRL-derived one.
**Alternatives considered:** Company-level column like `risk_factors` (rejected: wrong content for non-latest periods); fetching live in `get_detail` (rejected: adds EDGAR latency to every HTMX period swap; enrichment already owns expensive narrative fetches and everything is disk-cached after first fetch); new `press_releases` table (rejected: two nullable columns on the existing per-period table is simpler and follows the `risk_factors` column pattern).

---

## 2026-09-27 — Press-release extraction: headline + highlights section, lede fallback

**What:** `data/filings.py::extract_press_release_highlights` returns the release headline plus an explicit "Highlights" section when one exists; otherwise the opening paragraphs (the lede, which in earnings releases summarizes the quarter). Boilerplate ("About …", forward-looking statements, contacts) is excluded; returns None below a minimum length so stubs never render.
**Why:** Earnings-release HTML varies wildly across filers (same fragility as Item 1A extraction); graceful-None keeps the PRD's "Not available for this period" UX honest. The lede fallback matters because many releases have no explicit highlights section.
**Alternatives considered:** LLM summarization (rejected: adds API cost/latency to enrichment; heuristic extraction is sufficient for v1); full release text (rejected: too long for a collapsible, boilerplate-heavy).

---

## 2026-09-28 — Fiscal-year inference tolerates floating year-ends

**What:** `data/xbrl.py::infer_fiscal_year` now returns the year of the first nominal year-end on or after `period_end − 7 days`, replacing the old hard day-cutoff (`month <= 5 → end.year`, else compare MMDD). A 7-day grace constant `_FLOATING_YEAR_END_GRACE_DAYS` absorbs 52/53-week filers whose actual year-end floats a few days past SEC's fixed `fiscalYearEnd` MMDD.
**Why:** Live-testing the detail view on real AAPL data showed the quarter selector offering "Q4 FY2025" twice — Apple's 2024-09-28 year-end (nominal 0926, actual "last Saturday of September") was mislabeled FY2025. SEC's own companyfacts carries *duplicate* facts for that end date (`fy: 2024` from the original 10-K, `fy: 2025` re-stated a year later), and the wrong inference picked the wrong duplicate. The new rule preserves the end-year labeling convention (verified against Walmart: year ended 2025-01-31 → `fy: 2025`), which also corrected the old `month <= 5` branch that had encoded start-year labeling.
**Alternatives considered:** Preferring the earliest-filed duplicate on fy conflict (rejected as the primary fix: filing-order heuristics are fragile; the date-derived label is principled and already the filter's input — though the latest-filed fallback in `_choose_fact_for_end` stays, since balance-sheet *values* correctly want the latest restatement and a test pins that).

---

## 2026-09-28 — Valuation signal & target price (PRD §4.11)

**What:** Rules-based valuation card on the Overview page: PEG-implied P/E target price vs current Yahoo quote, with Strong Buy/Buy/Hold/Sell/Strong Sell signal, confidence, and reasoning bullets. New pure module `services/valuation.py`; `FinancialsService.get_valuation()` wires it to stored financials (no network on page view).
**Why:** Founder asked for an at-a-glance buy/sell signal for retail investors who won't read financials. PEG=1.5 heuristic chosen for explainability — every number on the card traces to a filing-derived input. Sales-based fallback covers unprofitable companies; insufficient-data state degrades to Watch instead of a fake number.
**Alternatives considered:** DCF (rejected for v1: too many assumptions, unauditable); analyst-price-target scraping (rejected: not a free source, licensing); deferring to Phase 5 AI analysis (rejected: founder wants the signal now, and this rules layer becomes an input to the later factor model).

---

## 2026-09-28 — Unknown tickers return a friendly 404 page (not a 500)

**What:** `services/financials.py::_resolve_cik` converts the EDGAR client's bare `KeyError` for unknown tickers into `CompanyNotFoundError` at all five ticker→CIK call sites; `main.py` gains a 404 exception handler rendering a new `templates/404.html` page ("Couldn't find that company" + back-to-search link). Live-verified: `/company/ZZZZ` and `/company/ZZZZ/detail` now return `404 text/html`.
**Why:** Defect hunt found `/company/ZZZZ` returning 500 Internal Server Error — the route's first-visit fetch fallback caught `CompanyNotFoundError` but the service raised an unconverted `KeyError`. A personal tool should degrade gracefully on typos, not 500.
**Alternatives considered:** Catching `KeyError` in the routes (rejected: leaks EDGAR-client internals into the HTTP layer; the service is the right boundary for error translation); leaving FastAPI's default JSON 404 (rejected: ugly for an HTML app).

---

## 2026-09-28 — Wikipedia enrichment swallows httpx.InvalidURL; quote failures never wipe price

**What:** (1) `data/wikipedia.py` network boundaries now also catch `httpx.InvalidURL`, which is NOT an `HTTPError` subclass — a malformed proxy/env config raised it out of `httpx.get`, escaping the module's documented None-on-error contract and 500-ing `POST /company/AAPL/refresh` via `enrich_company`. (2) `enrich_company` no longer overwrites `last_price`/`market_cap` when the fresh Yahoo quote comes back with `None` fields — extending the existing never-wipe-on-transient-failure policy already applied to risk factors and press-release highlights. A transient Yahoo timeout had wiped AAPL's stored price and degraded the valuation card to Watch.
**Why:** Defect hunt: refresh POST returned 500 in this environment; after fixing the crash, the refresh had still wiped the stored price (observed: valuation card showed "No current price available" after a successful refresh). Both are the same class of bug — transient network flakiness must not destroy good local state.
**Alternatives considered:** Letting InvalidURL propagate as a hard 500 (rejected: the module's contract promises graceful-None; proxy env config is outside user control); keeping unconditional price overwrite (rejected: violates the codebase's own never-wipe convention, and price is the single most visible field on the Overview).
