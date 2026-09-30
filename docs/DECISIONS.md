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

---

## 2026-09-28 — Yearly YoY requires two complete 4-quarter years

**What:** `_build_yearly_period` now only computes the year-over-year % when both the selected year and the prior year have a full 4 quarters of XBRL rows; otherwise the YoY fields stay empty and render as "—".
**Why:** Defect hunt: with only 8 periods seeded, FY2024 had a single quarter (Q4), so FY2025's 4-quarter TTM revenue ($416.16B) was compared against one quarter ($94.9B) and rendered as **+338% YoY** — a nonsense number on the detail page and in the new CSV export. A partial-year comparison is apples-to-oranges; honest "—" beats a wrong number (same principle as the PRD's "Not available" UX).
**Alternatives considered:** Annualizing the partial year (rejected: fabricates precision); hiding the incomplete year from the selector (rejected: bigger product decision, the TTM itself is still useful).

---

## 2026-09-28 — Per-period CSV download (PRD §4.3 #7) instead of PDF/ZIP

**What:** Phase 2 task 6 done as a sticky per-period CSV export: `GET /company/{ticker}/detail/download` streams `{TICKER}_{PERIOD}.csv` (metric/value/yoy_pct/qoq_pct, raw numbers, `#`-comment metadata header) built by the pure function `services/financials.py::build_period_csv`; the button lives inside the HTMX-swapped partial so its href always matches the selected period.
**Why:** PRD specified a sticky Download button with no format; PROJECT_STATUS capped it at "a simple per-period action" with full ZIP deferred to Phase 3. CSV was chosen over PDF: no new dependencies, the numbers stay computable in a spreadsheet, and the values exactly match the on-screen tables (filing-derived XBRL).
**Alternatives considered:** PDF export (rejected: needs a PDF lib, numbers become uncomputable); XLSX (rejected: openpyxl dependency for marginal gain over CSV); full-history ZIP (rejected: explicitly Phase 3 scope).

---

## 2026-09-28 — Sanitize bracketed IPv6 literals out of no_proxy at import

**What:** New `data/proxy_env.py::sanitize_proxy_env()`, called from `data/__init__.py` on import; rewrites `[::1]`-style entries to bare `::1` in `no_proxy`/`NO_PROXY`.
**Why:** The runtime injects bracketed IPv6 literals into `no_proxy`. httpx 0.28.1's `get_environment_proxies()` doesn't recognize the bracketed form, builds an `all://*[...]` mount key, and `URLPattern` raises `InvalidURL` — escaping `httpx.Client()` construction itself, so a single bad env entry crashed *every* HTTP call in the process (EDGAR, Wikipedia). Batch 1 had only papered over this for Wikipedia by swallowing the exception; this fixes the root cause for all httpx users.
**Alternatives considered:** Passing explicit `proxy=` to every httpx call (rejected: invasive, easy to miss a call site); upgrading httpx (rejected: newer versions may still not handle bracketed literals, and the env is what's actually malformed).

---

## 2026-09-28 — Trust the original filing for period labels, not SEC's nominal year-end or comparative facts

**What:** `_choose_fact_for_end()` (in `data/xbrl.py`) no longer disambiguates duplicate facts for the same period end via `infer_fiscal_year(end, fiscalYearEnd)`. Instead: labels (`fy`, `fp`) come from the earliest-filed candidate (the original filing — authoritative for what the period is called) and the value from the latest-filed candidate (so restatements still win for numbers).
**Why:** Defect hunt with JNJ: each quarter appeared twice in the detail selector ("Q3 FY2025" ×2) and YoY matching was broken for the latest quarter. Root cause: the same quarter appears in several filings (original 10-Q + comparative columns in later 10-Qs/10-Ks), and comparative facts inherit the *later* filing's `fy` label. The old code trusted `infer_fiscal_year` to pick the right one, but SEC's nominal `fiscalYearEnd` for JNJ is "0103" while JNJ's own filings label the Dec-2025-ended year FY2025 — so the inference agreed with the wrong (comparative) fact and mislabeled four rows by a year. The filer's own original labels are ground truth; a nominal MMDD is not.
**Alternatives considered:** Keeping the infer filter and special-casing JNJ (rejected: whack-a-mole, the next 52/53-week filer breaks again); earliest-filed for both labels and values (rejected: would ignore genuine restated numbers from amendments).
**Verified:** JNJ re-seeded — 8 unique selector options, correct FY2024–FY2026 labels, YoY on overview now resolves (was silently missing); AAPL unaffected; suite at 89 passing.

---

## 2026-09-28 — XBRL tag selection prefers the freshest tag for the requested window (PLUG)

**What:** `concept_facts()` gained a `staleness_window` parameter; `quarterly_income_metric()` passes (70, 100) so candidate tags are ranked by their newest *standalone-quarter* fact, and tags more than 400 days behind the freshest candidate are skipped. Chain order remains the tie-break among fresh tags.
**Why:** Defect hunt with PLUG (small-cap edge case): the revenue chain's first tag had stale quarterly facts ending in 2020 (kept "alive" by one recent half-year fact), so PLUG seeded eight 2019–2020 rows labeled `FY` with no valid quarter labels. The later `Revenues` tag has current quarterly facts through 2026-06-30. Selecting by window freshness instead of first-nonempty-tag fixes it.
**Verified:** PLUG re-seeded — 8 current quarters (Q3 FY2024–Q2 FY2026), Strong Buy via sales fallback (+47.6%, fair P/S 5.3× on 10.6% TTM revenue growth); AAPL/JNJ tag choices unchanged.

---

## 2026-09-28 — Valuation history snapshots + "signal changed" indicator (PRD §4.11)

**What:** New `valuation_history` table (CIK, date, price, target, upside %, signal, method; unique on (cik, date)); `FinancialsService.record_valuation_snapshot()` upserts one row per company per day during `enrich_company`; `get_signal_change()` compares the latest snapshot against the most recent prior one; the Overview card renders an amber "Signal changed from X to Y since {date}" pill next to the badge when the signal flipped. Also added a lifespan handler calling `create_tables()` at startup — it was defined but never wired, so new tables would silently never be created.
**Why:** A returning user should see that the model's verdict *moved*, not just today's number — the card previously had no memory. Same-day refreshes update in place (no dupe rows); snapshot failures (no quarterly data) log and never break enrichment.
**Alternatives considered:** Storing snapshots only on signal flips (rejected: loses the price/target trail for future charts); comparing against the oldest snapshot (rejected: "changed since" should reflect the most recent verdict, not ancient history).
**Verified:** POST /company/AAPL/refresh wrote today's snapshot (Hold, $342.58→$348.40); flip pill renders with a seeded prior snapshot and disappears with a single snapshot; suite at 94 passing.

---

## 2026-09-28 — FCF-yield cross-check + guardrail honesty on the valuation card (PRD §4.11)

**What:** Two additions to `services/valuation.py`, both display-only (never change the signal): (1) an FCF-yield cross-check footnote — TTM free cash flow ÷ market cap vs a 4% hurdle, stating whether cash generation supports or tempers the signal, with honest handling of negative/missing FCF; (2) guardrail honesty — when the growth [2%, 40%] or multiple [8×–40× P/E / 1×–10× P/S] clamps bind, confidence is capped at Medium and the card names the bound (e.g. "growth −7.8% hit the 2% floor and fair P/E hit the 8× floor").
**Why:** Defect-hunt credibility issue: JNJ rendered "Strong Sell, High confidence, −74.6%" while the entire call rested on two clamp floors — High confidence overstated what the model knew. The math is unchanged (documented v1 methodology); what's fixed is the card no longer presenting guardrail-driven output with full confidence. The FCF footnote adds a cash-based second opinion retail investors understand.
**Alternatives considered:** Softening the signal itself when clamps bind (rejected: arbitrary, would obscure the model's actual output); changing the hurdle per sector (rejected: v1 keeps one documented number).
**Verified:** JNJ now "Strong Sell, Medium" with the guardrail note + "FCF yield 3.4% (below 4%) — supports the signal"; AAPL "Hold, Medium" (P/E hit the 40× cap); PLUG "Strong Buy" with "negative FCF — burning cash, tempers the signal". Suite at 104 passing.

---

## 2026-09-28 — Search/autocomplete combobox (PRD §4.10, Phase 3 slice 1)

**What:** `GET /api/search?q=` returns ranked JSON suggestions from SEC `company_tickers.json` (ticker, name, CIK; max 8); ranking is the pure function `services/search.py::search_companies` — exact ticker → ticker prefix → name prefix → name substring, ties alphabetical (no market caps in the source file). New vanilla-JS combobox (`static/js/search.js`, no new deps) on the home page (replaces the raw ticker field) and in the persistent nav header: 150 ms debounce, matched-substring `<mark>` highlighting, ↑/↓/Enter/Esc keyboard support, click-to-open, "No companies found for '…'" empty state. Cmd+K omitted (PRD says nice-to-have, not a blocker).
**Why:** First Phase 3 slice per the batch plan; the PRD spec was complete, so no new spec was needed. Vanilla JS over HTMX/Alpine: arrow-key navigation and active-row state are cleaner imperatively, and it keeps the page's existing Alpine usage untouched.
**Alternatives considered:** HTMX-driven dropdown (rejected: keyboard nav needs client state anyway); putting search behind a new router module (rejected: one endpoint — lives in `routes/company.py` next to the pages it serves).
**Gotcha:** `company_tickers.json` uses `title`, not `name`, for the company name — caught live when `q=tesla` returned nothing; entries cache is process-lifetime (file changes rarely; navigation resolves CIK live via `/company/{ticker}`).
**Verified:** live API (`t` → T/T-PA/T-PC/TAAG/… with AT&T exact-first; `aapl` → Apple Inc.; `tesla` → Tesla, Inc.); home + header inputs render, `search.js` serves 200, node --check clean; suite at 120 passing.

## 2026-09-28 — Watchlist first slice (PRD §4.6)

**What:** `watchlist` table (CIK PK + `added_at`), toggle button on the Overview header ("☆ Watch" ↔ "★ Watching"), home page pinned-companies section with price and valuation-signal badge. `POST /company/{ticker}/watch` and `POST /company/{ticker}/watch/remove`; HTMX swaps the button in place, plain form POST redirects when JS is off.
**Why:** PRD §4.6 promises unlimited watchlist with companies pinned to home by default; this is the minimal slice (pinning only, no notes/tags yet).
**Alternatives considered:** Single toggle endpoint with method override — rejected; two POST endpoints work with plain HTML forms (no JS) without method-override middleware. DELETE considered but plain forms can't send it.

## 2026-09-28 — Dedupe (fy, fp) labels at extraction (XOM defect)

**What:** `xbrl._dedupe_period_labels` runs at the end of `extract_recent_quarterly_financials`: when two period ends share an (fy, fp) label, the earlier end's year is walked back until the label is unique (latest end processed first, keeps its label).
**Why:** XOM's SEC CIK (0002115436) holds only one filing, so the 2025-06-30 comparative column inherited fy=2026 and duplicated the "Q2 FY2026" selector option. Batch 2's "earliest-filed fact is authoritative" rule can't help when the original filing isn't in the CIK's dataset — the earliest available fact IS the mislabeled comparative. A fiscal year has exactly one of each quarter, so a label collision always means the earlier end is the comparative.
**Alternatives considered:** Trusting `infer_fiscal_year` over fact labels — rejected; JNJ's nominal fiscalYearEnd ("0103") disagrees with its own filings' convention, so neither source is universally trustworthy. The uniqueness invariant holds regardless of convention.

## 2026-09-29 — CapEx tag fallback chain (NVDA defect, defect-hunt batch 5)

**What:** `CONCEPTS[Metric.CAPEX]` now tries `PaymentsToAcquirePropertyPlantAndEquipment` then `PaymentsToAcquireProductiveAssets`; the existing `_MAX_TAG_STALENESS_DAYS` rule picks the first tag whose newest quarterly fact is within 400 days of the freshest tag in the chain.
**Why:** NVDA abandoned the classic CapEx tag after 2020 (last fact 2020-07-26) and files "Purchases of property and equipment" under `PaymentsToAcquireProductiveAssets`. With a single-tag chain the stale tag was the only candidate, so all 8 NVDA quarters stored `free_cash_flow=None` — blank FCF everywhere and "Cross-check unavailable" on the valuation card. Freshness-wins preserves the classic tag for filers still using it (chain order = semantic preference when both are fresh).
**Verified:** 3 new unit tests (abandoned-tag fallback, fresh-tag chain order); NVDA re-seeded — 8/8 quarters now have FCF (Q2 FY2027 $21.4B = $24.077B opcf − $2.677B capex ✓) and the card shows "FCF yield 2.3% (below the 4% hurdle)"; suite at 127 passing.
**Not a defect (checked and left alone):** XOM's 2 quarters keep FCF=None — its CIK dataset holds a single 10-Q whose cash-flow facts are H1-YTD only, so no standalone quarter can be un-cumulated. Honest "—" is correct; the stored revenue values are true 90-day quarterly facts (tag `Revenues` files both).

## 2026-09-29 — Full-history ZIP download (PRD §4.8, first slice)

**What:** `GET /company/{ticker}/download/history.zip` streams `{TICKER}_history.zip` (synchronous, in-memory) containing one `{TICKER}/{TICKER}_{PERIOD}.csv` per stored quarter, namespaced so it unpacks into one folder. `build_period_csv(ctx)` was refactored into the pure `render_period_csv(name, ticker, period)` (per-period route is now a thin wrapper) plus `_period_csv_filename` shared by both downloads; new service method `get_history_zip_entries(ticker)` reuses `_build_quarterly_period` so each file's YoY/QoQ columns match the detail view. "Full history (ZIP)" outline button sits next to the sticky per-period CSV button (plain link, works without JS).
**Why:** PRD §4.8 promises organized ZIP downloads; this is the minimal useful slice — every stored period's numbers in one archive. CSV-only deliberately: PDF export and renamed original SEC PDFs are heavier lifts and stay future slices (the per-period route made the same call on 2026-09-28).
**Alternatives considered:** Streaming the ZIP from disk (rejected: tens of KB at personal scale, in-memory is simpler); including yearly aggregates (rejected: derivable from quarters; keep the archive one-file-per-stored-period).
**Gotcha:** inserting the new route above `@router.get("/api/search")` ate that decorator (the edit replaced the decorator line) — `/api/search` 404'd until it was re-added. Lesson: when inserting above an existing decorated def, match on the `def` line too, not just the decorator.
**Verified:** 3 new tests (service entries + pure ZIP namespacing + route 200/404); live: AAPL ZIP has 8 files, `attachment; filename="AAPL_history.zip"`, first file headers match the per-period CSV format; suite at 131 passing.

## 2026-09-29 — Watchlist refresh-all quotes (PRD §4.6, slice 2)

**What:** `POST /watchlist/refresh` refreshes Yahoo quotes for every pinned company and re-renders the home pins (HTMX swap of the new `partials/watchlist.html`; plain-POST 303-redirects to `/`). Service method `refresh_watchlist_quotes()` is quote-only (no Wikipedia/risk-factor/press-release work), applies the never-wipe policy per ticker, records a valuation snapshot per company so quote-driven signal flips fire the change pill, and counts per-ticker failures instead of raising (returns `{"updated": n, "failed": m}`). The watchlist section was extracted from `index.html` into `partials/watchlist.html` so the HTMX path reuses the exact same markup — the partial carries the `id="watchlist-section"` wrapper so the `outerHTML` swap target survives.
**Why:** Pins go stale the moment they're rendered; without this the user had to open each company and hit refresh to keep home-screen prices current. Quote-only keeps it cheap (one Yahoo call per pin, no EDGAR work).
**Verified:** 4 new tests (service never-wipe + failure counting, route 303 plain / 200 HTMX partial); live: pinned NVDA, both POST paths return 303/200, pins partial renders with refreshed prices; suite at 135 passing.

## 2026-09-29 — Chart range window (PRD §4.2, range-mode first slice)

**What:** From/To quarter selectors in the detail-view slicer bound the Revenue & EPS trend chart only. `get_detail(chart_from=, chart_to=)` windows the chart arrays; KPI cards, tabbed tables, press-release highlights, and both downloads still follow the selected period. Unknown labels fall back to full history; an inverted range swaps instead of erroring. The selects live in `detail.html`'s slicer form (quarterly-only, hidden+disabled in yearly mode) and submit with the existing `hx-trigger="change"` HTMX form — no JS changes, since `renderTrendChart` reads the re-rendered `chart-data-json`. DetailContext gained `chart_range_options` (chronological) + `selected_chart_from/to` with defaults so existing constructions still work.
**Why:** PRD §4.2's range mode is a big feature; the chart window is the smallest slice that delivers real value (zoom into a sub-period as history grows) without touching the period model. Tables-across-a-range stays a future slice.
**Verified:** 5 new tests (windowing, inversion swap, full-history default, unknown-label fallback, route param pass-through); live: detail page renders both selects, partial with `chart_from=Q1 FY2025&chart_to=Q2 FY2025` returns exactly those 2 chart points; suite at 140 passing.

## 2026-09-29 — Defect hunt batch 6: press-release exhibit discovery generalized

**What:** `_find_ex99_doc()` in `services/ir_download.py` only matched `ex99`-style filenames in the 8-K filing index, so companies that name their earnings-release exhibits differently (NVDA's `q2fy27pr.htm`, no "ex99" anywhere) silently got zero press-release highlights — 7 of 11 seeded tickers (NVDA, META, GOOGL, TSLA, AMD, JNJ, RDDT) had 0/8 periods with highlights vs 8/8 for AAPL/MSFT/PLUG. Extracted the filename matching into a pure, unit-testable `_pick_release_doc(links)` with priority ranking: (1) `ex(hibit)?[^a-z0-9]?99` — also fixes a latent miss of `exhibit991`-style names the old `ex.?99` regex missed; (2) `*pressrelease*` / `*earningsrelease*`; (3) `-pr`/`_pr`-suffixed stems; (4) quarter-styled stems ending in `pr` that contain a digit (matches `q2fy27pr`, excludes `proper.htm`/`super.htm` lookalikes). Skips `index.htm` and `R1.htm`-style financial-report files. Also corrected a stale `_to_period` comment that promised a primary-8-K-document fallback that was never implemented.
**Why:** A shipped feature silently failing for most companies is worse than a loud failure — the "Not available" UX masked a real discovery bug. Pure-function extraction makes the heuristic testable without network.
**Verified:** 8 new unit tests in `tests/services/test_ir_download.py` (NVDA-style, ex99-classic, exhibit991, pressrelease, pr-suffix, lookalike exclusion, none-found, priority); live discovery finds all 8 NVDA `q*Nfy*pr.htm` exhibits via `discover_earnings_filings`. Backfill deferred: SEC Archives document fetches currently return 403 "Your Request Originates from an Undeclared Automated Tool" while index listings and the JSON API work — discovery is correct but downloads are blocked. Enrichment is best-effort and only fills NULL rows, so it self-heals on the next successful refresh. Suite at 148 passing.

## 2026-09-29 — Compare mode, first slice (PRD §4.2)

**What:** `GET /company/{ticker}/compare` — side-by-side comparison of two quarters as a metric × (A | B | Δ | Δ%) table covering all 5 KPIs + 4 balance-sheet items, with green/red ▲▼ Δ% badges matching the detail-view style. `FinancialsService.get_compare(ticker, period_a=, period_b=, preset=)` — A defaults to the latest quarter; B defaults to the YoY-ago quarter (same fiscal period, prior fiscal year); `preset=yoy|qoq` buttons pin B to YoY-ago / the immediately preceding quarter; explicit `period_b` labels give free-form compare. Unknown labels fall back to YoY-ago; with a single quarter of history B = A (zero deltas). New `CompareContext` / `CompareDeltas` / `MetricDelta` Pydantic models; `_compare_periods()` reuses `_pct_change` so None-handling matches the rest of the app. Template `company/compare.html` uses a plain GET form (no JS), and the detail page breadcrumb gained a "⇄ Compare periods" link. Same fetch-on-missing + friendly-404 pattern as the detail route.
**Why:** PRD §4.2's compare mode is the natural complement to the range-mode chart window shipped this morning; a standalone page keeps it isolated from the HTMX-swapped detail partial, and quarterly-only keeps slice 1 small (yearly compare stays future).
**Verified:** 9 new service tests (defaults, qoq preset, free-form, unknown-label fallbacks, None deltas, single-quarter, no-data 404, balance-sheet deltas); live: `/company/AAPL/compare` → Q3 FY2026 vs Q3 FY2025 ($109.42B vs $94.04B, Δ +$15.38B / +16.4% ▲), `?preset=qoq` → Q3 vs Q2 FY2026, free-form + bogus label falls back to YoY-ago; suite at 157 passing.

---

## 2026-09-29 — Bank revenue composite (NoninterestIncome + net interest income)

**What:** For finance SICs (6000–6299), quarterly revenue is extracted as the sum of `NoninterestIncome` + (`InterestIncomeExpenseNet` | `NetInterestIncome`) instead of the generic `Revenues` fallback chain; `sic` now flows from SEC submissions through `fetch_and_persist`/`recent_quarterly_financials` into `quarterly_income_metric`.
**Why:** Banks file quarterly revenue as two components while the generic `Revenues` chain often holds only annual facts (JPM's quarterly `Revenues` stops in 2014, WFC's in 2020, GS files none). Revenue is the canonical anchor, so every joined metric (net income, EPS) was pinned a decade stale — JPM seeded with 2013–2014 quarters. Verified the components sum exactly to quarterly `Revenues` where both exist (BAC 2026 Q1/Q2, diff 0), so the composite is semantically total net revenue, not an approximation.
**Alternatives considered:** Adding the components to the generic REVENUE chain as fallbacks (rejected: picking one component alone would halve reported revenue); deriving quarterly revenue from YTD `Revenues` facts (rejected: JPM doesn't file quarterly `Revenues` at all anymore, so there is nothing to uncumulate).

---

## 2026-09-29 — Unwatch from home via `?next=home`

**What:** Home-page watchlist pins get an "✕" remove button posting to `/company/{ticker}/watch/remove?next=home`; the same route re-renders the pins partial for HTMX or redirects to `/` for plain POST. Pin rows changed from a wrapping `<a>` to `<div>` + inner `<a>` + form.
**Why:** The only way to unwatch was the Overview-header toggle, forcing a trip to the company page. The `?next=home` query param keeps one route serving both contexts instead of adding a second endpoint.
**Alternatives considered:** A separate `/watchlist/remove` endpoint (rejected: duplicates the existing route's logic for no gain).

---

## 2026-09-29 — Yearly compare mode (PRD §4.2, slice 2)

**What:** `GET /company/{ticker}/compare?mode=yearly` compares two fiscal-year aggregates using the existing `_build_yearly_period` (4-quarter sums for flow metrics, year-end point-in-time for balance sheet) and `_compare_periods` deltas; Quarterly/Yearly mode tabs on the compare page, year selectors via plain GET form, quarter presets hidden in yearly mode. A defaults to latest fiscal year, B to prior year; unknown years fall back like the quarterly path.
**Why:** PRD §4.2 specifies compare across periods; slice 1 was quarterly-only. Yearly aggregates answer "was 2026 a better year than 2025" without mental quarterly math. Reuses the detail view's yearly semantics (including the complete-years-only YoY guard) so numbers stay consistent across pages.
**Alternatives considered:** A "5-year-ago" quarterly preset (rejected for now: only 8 quarters are seeded, so it would always fall back to the oldest available quarter — weak value until history depth grows).

---

## 2026-09-29 — Finance SICs prefer their own `Revenues` tag (absolute freshness)

**What:** For finance SICs (6000–6999), `quarterly_income_metric` first tries quarterly `Revenues` when its newest fact is within 400 days of *today* (absolute, not relative); banks with stale/missing quarterly `Revenues` fall through to the NoninterestIncome + net-interest-income composite; everything else falls back to the generic chain.
**Why:** MET seeded with $0.7B/quarter revenue — the generic chain prefers `RevenueFromContractWithCustomerExcludingAssessedTax`, which for insurers is a fee-income sub-component, while the filer's own `Revenues` ($19B total) sat later in the chain. A relative staleness check can't gate this: JPM files nothing else quarterly in the chain, so its 2014 `Revenues` would look "fresh" relative to itself — hence the absolute today-based check.
**Alternatives considered:** Reordering the generic chain to put `Revenues` first for all companies (rejected: the contract-tag preference is deliberate for operating companies — excludes assessed taxes; the finance-only gate keeps that behavior untouched).

---

## 2026-09-29 — Net-income fallback tags + 180-day abandonment threshold

**What:** `NET_INCOME` chain gains `NetIncomeLossAvailableToCommonStockholdersBasic` and `ProfitLoss` fallbacks; `_MAX_TAG_STALENESS_DAYS` tightened 400→180 (applies to both the relative chain check and the finance `Revenues` absolute check).
**Why:** Realty Income abandoned quarterly `NetIncomeLoss` after 2025-Q3 (273-day lag behind the replacement tag), leaving net income `None` for 2026 Q1/Q2 while EPS was present — the 400-day bar missed a real, recent abandonment. The relative rule compares tags from the *same* filer, so a slow filer is never penalized (all its tags lag together); a tag missing for two full filing cycles while a sibling stays current is abandonment by definition. False positives self-heal: chain order re-prefers the original tag the moment it's fresh again. MET/JPM/WFC re-verified unaffected.
**Alternatives considered:** Keeping 400 and adding a net-income-specific override (rejected: two thresholds for the same concept invites drift; 180 is defensible for both uses — a finance filer whose quarterly `Revenues` is 180+ days old is genuinely stale).

---

## 2026-09-29 — Total liabilities derived from the accounting identity when the tag is absent

**What:** When a filer reports no standalone `Liabilities` instant tag, missing total-liability instants are filled as Assets − StockholdersEquity from the same filing; only ends where both components exist are filled, and an explicitly filed value is never overwritten (`setdefault`).
**Why:** Eli Lilly never files a `Liabilities` tag (only `LiabilitiesAndStockholdersEquity` + `StockholdersEquity`), so the balance-sheet tab and compare table showed "—" for Total Liabilities. The identity is exact, not an estimate — verified 108.4B = 142.3 − 33.9 on live LLY data. Follows the existing "derive rather than drop" precedent (`_derive_q4_income`).
**Alternatives considered:** Leaving "—" per the missing-data UX (rejected: the number is exactly recoverable, and the balance-sheet tab is misleading without it); adding a `LiabilitiesAndStockholdersEquity`-minus-equity tag fallback (rejected: needs arithmetic anyway, and the identity version is tag-agnostic).

---

## 2026-09-29 — Compare 5-year-ago preset shipped with oldest-available fallback

**What:** The PRD §4.2 preset trio (YoY, QoQ, 5-year-ago) is now complete: `preset=5y` sets B to the same quarter five fiscal years back, else the oldest available quarter (maximum span — the 3-year history depth rarely holds the exact quarter), else A itself. The B label always shows the real period so the button never misleads.
**Why:** Revisits the 2026-09-29 yearly-compare decision, which deferred the 5y preset as "weak value until history depth grows." On reflection, the oldest-available fallback still answers the user's real question ("how far has this come?") with the best span on hand, and costs one branch in the existing B-resolution chain. If history depth ever grows past 5 years, the exact-quarter path activates with no further changes.
**Alternatives considered:** Falling back to YoY when the exact quarter is missing (rejected: less informative than the full available span for the same click).

---

## 2026-09-29 — Compare-view ZIP download (PRD §4.8, second slice)

**What:** `GET /company/{ticker}/compare/download` mirrors the compare page's parameters and returns `{TICKER}_compare.zip` containing `{TICKER}/{TICKER}_{A}.csv`, `{TICKER}/{TICKER}_{B}.csv` (reusing `render_period_csv`) and `{TICKER}/{TICKER}_compare_summary.csv` (metric × period_a | period_b | delta | delta_pct); "⇓ Compare (ZIP)" plain-link button in the compare controls so it works without JS. Unknown ticker → 404, bad preset → 422 (FastAPI Literal validation).
**Why:** PRD §4.8 specifies Single Quarter, Single Year, Range, and Compare ZIP structures; slice 1 was the full-history ZIP. The compare ZIP closes the loop for the compare view — the archive matches exactly what's on screen because it reuses `get_compare` with the same parameters.
**Alternatives considered:** A single summary-only CSV (rejected: the per-period CSVs carry the yoy/qoq columns and metadata headers analysts need; the archive is still tens of KB).

---

## 2026-09-29 — Instant-fact staleness check now sees instant facts

**What:** `_newest_in_window` counted only facts with a `start` date; with a `None` window it now counts all facts, including instant (point-in-time) balance-sheet facts.
**Why:** Balance-sheet tag selection always passed `instant=True` with no window, so the 180-day tag-abandonment rule silently never engaged for balance-sheet metrics — the first tag always won even when abandoned years ago (UNH `StockholdersEquity` ended 2015, PG `CashAndCashEquivalentsAtCarryingValue` ended 2019), blanking Total Equity and Cash & Equivalents for all quarters.
**Alternatives considered:** Per-metric windows for instant facts (rejected: the `None` window already means "any duration"; the old behavior was simply a bug).

---

## 2026-09-29 — Per-quarter diluted→basic EPS fallback instead of chain extension

**What:** `extract_recent_quarterly_financials` now fills ends missing `EarningsPerShareBasic` with that quarter's `EarningsPerShareDiluted` value (labeled EPS_BASIC, source tag preserved), rather than extending the EPS_BASIC fallback chain.
**Why:** Goldman Sachs still files basic EPS most quarters but its Q2 2026 10-Q filed diluted only; whole-chain selection correctly keeps basic preferred (94 days < 180-day abandonment threshold), so extending the chain would not have filled the single missing quarter. Basic wins wherever present; diluted fills only gaps (they differ by fractions of a percent).
**Alternatives considered:** Extending the EPS_BASIC chain with `EarningsPerShareDiluted` (rejected: would not fix the single-quarter gap and could mislabel when basic exists).

---

## 2026-09-29 — Range ZIP mirrors the chart window; window logic extracted

**What:** New `GET /company/{ticker}/download/range.zip?chart_from=&chart_to=` (PRD §4.8 third slice): per-quarter CSVs for the resolved chart window + a `metric × quarters` summary CSV. The label-resolution logic (unknown-label fallback, inverted-range swap) was extracted into `_chart_window()` shared by `get_detail` and the ZIP builder.
**Why:** The archive must match what's on the chart; duplicating the resolution rules would let them drift.
**Alternatives considered:** Duplicating the index math in the ZIP method (rejected: drift risk).

---

## 2026-09-29 — Watchlist notes: parsed form body, no new dependency

**What:** `POST /company/{ticker}/watch/note` parses the urlencoded body with `urllib.parse` instead of FastAPI's `Form(...)`.
**Why:** `Form` requires `python-multipart`, which is not in the project's dependency set; adding a dependency for one form field is heavier than parsing the urlencoded body HTML/HTMX forms send by default.
**Alternatives considered:** Adding python-multipart to pyproject (rejected: heavier footprint for a single field).

---

## 2026-09-29 — LLY CapEx tag: third CAPEX fallback tag

**What:** Added `PaymentsToAcquireOtherPropertyPlantAndEquipment` to the CAPEX fallback chain in `xbrl.py`.
**Why:** Eli Lilly never filed `PaymentsToAcquirePropertyPlantAndEquipment` and abandoned `PaymentsToAcquireProductiveAssets` in 2022 — its CapEx lives under this third tag, so FCF showed "—" for all 8 quarters. The existing freshness rule (relative staleness ≤180d) picks the right tag per filer without hardcoding, the same pattern as the NVDA fix.
**Alternatives considered:** A per-filer tag override table (rejected: the chain + freshness rule already generalizes).

---

## 2026-09-29 — 52/53-week 9M YTD window floor unified at 240 days

**What:** Both YTD 9-month windows (`quarterly_cash_flow_metric` used 255d, `_derive_q4_income` used 250d) now use a 240-day floor.
**Why:** Costco's 36-week 9M fact is 251 days — it passed the Q4-derivation window but failed the quarterlyization window, so COST's Q3 FCF silently showed None. The two windows were inconsistent; 240 covers 52/53-week filers without touching the H1 (≤200d) or full-year (≥340d) bands.
**Alternatives considered:** Per-filer duration calibration (rejected: overkill; the window just needed to not exclude real 9M facts).

---

## 2026-09-29 — Balance-sheet identity derivation extended to missing equity

**What:** `_derive_missing_liabilities` generalized to `_derive_missing_balance_sheet`: a missing Liabilities *or* Equity instant is derived from Assets = Liabilities + Equity (same filing, both components present, explicit filings never overwritten); Assets is never derived.
**Why:** Visa files no standalone equity tag (Assets + Liabilities only), mirroring the LLY liabilities case from batch 9. Deriving assets instead would fabricate the anchor the identity is checked against.
**Alternatives considered:** Extending the EQUITY tag chain (rejected: no other tag exists in Visa's companyfacts; the identity is exact).

---

## 2026-09-29 — Single-year ZIP download (PRD §4.8, fourth slice)

**What:** `GET /company/{ticker}/download/year.zip?year=` → `{TICKER}_year_FY{YEAR}.zip` with one per-quarter CSV per fiscal year + a `metric × quarters` summary CSV (reusing the per-period renderer and the range-summary renderer); unknown year falls back to the latest stored fiscal year; "⇓ Year (ZIP)" button in the detail view's yearly mode.
**Why:** PRD §4.8 named Single-Year ZIPs as the remaining future slice after history/compare/range. The button's href is Alpine-bound to the live year select so the archive always matches the chosen year (a static render-time href would go stale after HTMX re-selects the year).
**Alternatives considered:** Including the fiscal-year aggregate CSV in the archive (rejected: the per-quarter CSVs already carry YoY; keeps the archive parallel to the range ZIP).

---

## 2026-09-30 — "Also trades as" sibling-ticker header link (PRD §4.9 edge case)

**What:** `sibling_tickers(cik, exclude_ticker, entries)` in `services/search.py` (pure, unit-tested) finds other SEC-listed tickers sharing the same CIK from the cached `company_tickers.json` entries; `FinancialsService.get_sibling_tickers(ticker)` wraps it best-effort (never raises, empty list hides the hint); Overview/Detail/Compare headers render "Also trades as: GOOG" linking to the sibling class page.
**Why:** PRD §4.9 requires an "Also trades as" link for multiple share classes (GOOGL/GOOG). The SEC ticker list is already parsed and cached for search, so the lookup costs nothing and stays consistent with how the app resolves tickers.
**Alternatives considered:** Resolving siblings per request from the EDGAR API (rejected: the parsed list is already cached per process; a network lookup would add latency for zero freshness gain).

---

## 2026-09-30 — Q4 EPS derived from net income and implied share counts (defect-hunt round 12)

**What:** `_derive_q4_income` no longer un-cumulates per-share values by subtraction (FY_EPS − 9M_EPS); for `EPS_BASIC`/`EPS_DILUTED` it derives Q4 EPS as Q4 net income over the implied Q4 share count — `(12·FY_avg − 9·9M_avg)/3` where each average is implied from the filed NI/EPS pair. Falls back to precision-rounded subtraction when NI facts are missing or any input is zero/non-positive.
**Why:** The annual and 9M EPS figures divide by different share counts, so subtraction misstates Q4 — DUOL's FY2025 Q4 rendered diluted $0.94 above basic $0.88 (arithmetically impossible; a huge Q3 tax benefit moved the denominators). The implied-shares method restores the ranking ($0.90 basic > $0.89 diluted) and the true economics.
**Alternatives considered:** Reading Q4 EPS from the 10-K (doesn't exist — no standalone Q4 fact is filed); deriving from weighted-share facts (Duolingo files none in companyfacts; the NI/EPS-implied route needs no new tags); clamping diluted ≤ basic (hides the error instead of fixing it). Residual sub-cent ranking flips can remain when the filing's own cent-rounding moves implied shares (UBER FY2024 Q4: $3.2944 vs $3.2972) — documented as a limitation, not papered over.

---

## 2026-09-30 — FCF suppressed for all finance-SIC filers (defect-hunt round 12)

**What:** `extract_recent_quarterly_financials` now stores FCF as NULL for finance SICs (6000–6999), instead of only when no CapEx tag is filed.
**Why:** For lenders, operating cash flow is dominated by balance-sheet flows (loan originations, deposits), so OpCF − CapEx is a misleading number, not a conservative one. Banks/insurers/REITs already rendered "—" because they file no CapEx tag; SoFi (SIC 6199) files one and showed −$3.99B on the KPI card, inconsistent with its peers (BAC/JPM/WFC/MET/O all "—"). The valuation card's FCF-yield cross-check already handles missing FCF honestly.
**Alternatives considered:** Leaving the honest-but-meaningless number (rejected: the label "Free Cash Flow" implies an operating-company concept; the codebase already treats it as not-meaningful for this sector).

---

## 2026-09-30 — Unknown-ticker 404 suggests close matches (PRD §4.9)

**What:** The 404 handler now runs the unknown ticker through the same `search_companies` ranking the search box uses and renders up to 5 "Did you mean" links on the 404 page; lookup is best-effort and never breaks the plain 404.
**Why:** PRD §4.9/§4.10: an unknown ticker (typo, or a retired ticker like FB) must never be a dead end. Reuses the existing ranker — no new matching logic, no new dependency.
**Alternatives considered:** Resolving retired tickers to their successors (needs historical ticker data SEC doesn't publish in company_tickers.json — out of scope); client-side suggestion fetch (more moving parts for the same result).

---

## 2026-09-30 — Filer-mislabeled 10-K Q4 stubs relabeled Q4 (batch 9)

**What:** `xbrl._merge_standalone_with_q4()` relabels a quarterly-duration fact carrying fp="FY" to "Q4" when a derived Q4 row exists for the same end; the filer's own stub fact supersedes the derived duplicate. Applied in all three revenue paths (generic income metrics, `_finance_total_revenue`, `_bank_quarterly_revenue`).
**Why:** ABBV's 10-K tags its 91-day Q4 Revenues stub fp="FY" (verified against raw SEC JSON — the filer's label, not our transform). The phantom FY row stole a slot in the 8-quarter slice (ABBV and AMT seeded 7 quarters) and collided on (cik, period_end) at upsert; in the bank composite it would additionally have been *summed* with the derived Q4, roughly doubling the quarter.
**Alternatives considered:** Filtering fp="FY" rows out of the anchor slice (simpler, but discards the filer's authoritative value in favor of the FY−9M derivation); overriding labels by duration inside `_choose_fact_for_end` (broader blast radius — that function's "labels come from filings" contract is load-bearing for the JNJ/XOM fixes).

---

## 2026-09-30 — Total-equity chain prefers the including-NCI tag (batch 9)

**What:** `Metric.TOTAL_EQUITY` chain order swapped to `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` first, parent-only `StockholdersEquity` as fallback.
**Why:** "Total Equity" on the balance sheet includes noncontrolling interests — it is the tag that satisfies Assets = Liabilities + Equity. NEE files both tags fresh through 2026-03-31; parent-only left a $10.3B identity gap (154.79 + 55.22 ≠ 221.42), the total-equity tag closes it exactly (154.79 + 66.63 = 221.42). The UNH staleness fallback (parent-only abandoned 2015) still works unchanged.
**Alternatives considered:** Keeping parent-only first (rejected: breaks the accounting identity for any filer with material NCI); deriving equity from Assets − Liabilities everywhere (rejected: explicit filings must never be overwritten — batch 11 rule).

---

## 2026-09-30 — Range tables render when the chart window narrows (batch 9, PRD §4.2 slice 2)

**What:** When the detail view's From/To selectors narrow the chart window to 2+ quarters, the tabbed Income/Cash Flow/Balance tables switch from the single-selected-period view to a metric × quarters grid (`DetailContext.range_table`); full-history and one-quarter windows keep the period view with YoY/QoQ columns.
**Why:** Slice 1 bound only the trend chart, leaving the tables on the selected period — the range selection felt half-applied. The window itself is the comparison, so the grid shows raw values with no change columns; KPI cards, press-release highlights, and downloads still follow the selected period (unchanged contract from slice 1).
**Alternatives considered:** A separate "range mode" toggle (rejected: the From/To selectors already are the range affordance — a second control would desync); always showing the grid even for a 1-quarter window (rejected: degenerate single-column table is strictly worse than the period view it would replace).

### 2026-09-30 — Watchlist tags (PRD §4.6, fifth slice)
**What:** Comma-separated `tags` column on `watchlist` + Alembic migration; `POST /company/{ticker}/watch/tags` (HTMX partial swap / plain-POST redirect / 404 when unwatched); tag chips + inline editor on Overview while watching; chips under home-page pin names.
**Why:** Completes the PRD §4.6 "No notes/tags yet" deferral — §4.6 is now fully built (pinning, refresh-all, unwatch, notes, tags). Tags stay simple on purpose: max 5 × 20 chars, normalized server-side (dedupe case-insensitive), no tag filtering/search — grouping at a glance is the use case, not taxonomy management.
