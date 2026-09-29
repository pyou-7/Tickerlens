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
