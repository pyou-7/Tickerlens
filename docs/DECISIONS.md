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

## 2026-10-03 — Rate-aware valuation guardrail (batch 12)

**What:** `compute_valuation()` accepts `ten_year_yield_pct` (default 4.5% benchmark); fair P/E is capped at `100 / (yield × 0.6)` so the implied earnings yield stays ≥60% of the 10-year Treasury. Binding cap adds a reasoning note and caps confidence at Medium, mirroring the existing guardrail contract. PEG path only; sales fallback untouched.
**Why:** The PEG model was rate-blind: at a 5.3% 10-year (24-year high), a 40x fair P/E implies a 2.5% earnings yield — less than half risk-free — yet could still print Strong Buy. The cap only bites in high-rate regimes (at 2% yields the 83x cap sits above the 40x clamp, guardrail dormant).
**Alternatives considered:** Full parity with risk-free (rejected: growth equities deserve latitude vs risk-free; would kill all growth multiples); DCF with discount rate (rejected: v1 stays an explainable heuristic per PRD §4.11); live yield feed (deferred: parameter is wired, service layer still passes default).

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

### 2026-09-30 — Range-mode hero KPIs (PRD §4.2, slice 3)
**What:** When the detail view's From/To selectors narrow the chart window to 2+ quarters (same condition as the range tables), the hero KPI cards aggregate over the window — nullable sums per metric, TTM convention (EPS diluted summed, not averaged) — and the YoY/QoQ toggle is replaced by a "vs prior NQ" caption comparing against the preceding equal-length window. `RangeKPIData` on `DetailContext`; `kpi_card` macro takes an optional caption.
**Why:** PRD §4.2's range mode previously changed the chart and tables but left the KPI cards showing the selected single period — inconsistent. Change vs a *preceding equal-length window* (not YoY) because the window itself is the comparison basis; a partial prior window (start of history) uses whatever quarters exist and blanks the change when none exist. Full-history and one-quarter windows keep the period cards.

### 2026-09-30 — Cross-company compare (PRD §4.2, new mode)
**What:** `GET /company/{ticker}/vs/{other}` — latest reported quarter side by side: revenue, net income, EPS diluted, FCF (each with its own YoY badge), share price, market cap, valuation signal badge, implied upside. "⇄ Compare" peer-ticker form on the Overview page; swap form on the vs page (both Alpine-driven, no extra JS). Either side fetched on first visit when not stored; 404 when unloadable.
**Why:** Retail investors constantly ask "KO or PEP?" — this answers it with filing-derived numbers plus the valuation signal. Deliberately neutral presentation (no winner highlighting): the signal badge is the model's verdict, the table is just data. A note appears when the two latest quarters don't align (different fiscal calendars) rather than silently comparing mismatched periods.

---

## 2026-09-30 — Frontend Design Overhaul: Light/Dark/System Theme Engine, Zero-FOUC, and High-Density Financial UI

**What:** Comprehensive frontend redesign across all templates (`base.html`, `index.html`, `overview.html`, `detail.html`, `detail_data.html`, `compare.html`, `vs.html`, `404.html`) and static assets. Added a zero-FOUC inline theme detector in `<head>`, a 3-way segmented theme switcher (`light` | `dark` | `system`) persisted in `localStorage`, Inter + JetBrains Mono typography with global `tabular-nums` financial alignment, dynamic theme-reactive Plotly charts via custom `theme-changed` events, and card-grid vs dense-table view switching on the home dashboard.
**Why:** The initial UI was hardcoded to dark mode styles and lacked consistent spacing, responsive contrasts, and modern visual polish expected of premium financial intelligence platforms (Linear/Vercel/Stripe standards). Tables and KPI cards now seamlessly support both crisp light mode and high-contrast dark mode with high data density.
**Alternatives considered:** CSS-only `@media (prefers-color-scheme)` without user toggle (rejected: users strongly prefer manual toggle override capability); full SPA migration with React/Vue (rejected: HTMX + Jinja2 architecture remains fast, simple, and dependency-free).

---

## 2026-09-30 — Interactive Microinteractions & AI Company UI Components

**What:** Added interactive components modeled on Linear, Vercel, and Perplexity: global notification toast system (`showToast()`), global keyboard shortcut dialog (`?`), one-click ticker copy buttons with clipboard feedback, real-time client-side watchlist search filtering & tag pill filtering, visual valuation upside progress meter with collapsible methodology accordion, visual head-to-head proportion bars in company compare (`vs.html`), and one-click "Copy Table (TSV)" for exporting financial statements straight to Excel/Google Sheets.
**Why:** Modern AI tools communicate state and feedback immediately. Microinteractions (like toasts on copy, visual proportion gauges, and live search filtering) eliminate UI friction and make dense financial data intuitive and enjoyable to explore.
**Alternatives considered:** External toast/modal libraries (rejected: lightweight Alpine.js declarative bindings keep bundle zero-dependency).

---

## 2026-09-30 — Home Page Redesign: Unified Command Search Bar, Market Benchmarks Pulse, and Feature Bento Grid

**What:** Redesigned the home page (`index.html`, `partials/watchlist.html`, `base.html`, `search.js`):
1. Removed duplicate header search bar on the home page via `{% block nav_search %}`, replacing it with a live SEC EDGAR primary source status pill so the hero search bar serves as the undivided command center.
2. Rebuilt the hero search bar with clean flexbox alignment, normal-case placeholder (fixing the truncated uppercase bug), docked `⌘K` keyboard badge, and instant dropdown.
3. Replaced the empty watchlist state with a rich "Market Leaders & Benchmarks" section displaying live normalized fundamental cards (NVDA, AAPL, MSFT, AMZN, GOOGL, TSLA) with 1-click "☆ Pin" HTMX actions (`?next=home`).
4. Added an interactive 3-card Feature Highlights Bento Grid (Normalized SEC XBRL, Rules-Based Valuation, Time Slicer & Peer Compare) and quick keyboard hints bar.
**Why:** First impressions matter. The previous home page had conflicting duplicate search bars, broken uppercase placeholder text, and a desolate dashed empty box when the watchlist was empty. The redesigned page delivers immediate visual polish, instant market utility, and effortless onboarding.
**Alternatives considered:** Redirecting to a default company like AAPL on empty watchlist (rejected: home page is the canonical dashboard; live benchmarks provide immediate utility while preserving personal dashboard curation).

---

## 2026-09-30 — Popular Stocks Bar: 10 Most Traded US Equities with Ticker + Up/Down %

**What:** Replaced redundant ticker name pills (`NVDA · NVIDIA`, `AAPL · Apple`) with the top 10 most actively traded US public companies (`NVDA`, `TSLA`, `AAPL`, `AMD`, `AMZN`, `MSFT`, `META`, `GOOGL`, `PLTR`, `NFLX`), displaying clean ticker symbols paired with color-coded up/down percentages (`+X.X%` / `-X.X%`). Balanced in a max-width flex wrapper to prevent single-item orphans across all viewport widths. Added `PopularStock` model and `FinancialsService.get_popular_stocks()`.
**Why:** Displaying both ticker and company name introduced redundant information ("duplicating the stock ticker twice"). Modern financial terminals communicate market momentum cleanly with symbol plus price change percentage.
**Alternatives considered:** Showing dollar prices (rejected: percentage changes communicate relative daily momentum better and take up less horizontal space).


## 2026-09-30 — Stock-split EPS rescaling (defect-hunt round 15)

**What:** `_detect_split_events()` / `_merge_duplicate_events()` / `_split_adjust_facts()` in `data/xbrl.py` rescale pre-split per-share facts to the latest filing's share basis before series construction; duplicate observations of one split (10-K + 10-Q restatements) merge so facts rescale exactly once; ambiguous facts (never restated, e.g. NFLX's Q3-2025) are classified by neighbor-consistency against certain-basis quarters.
**Why:** NFLX's 10-for-1 split left mixed-basis EPS — restated 0.72 beside pre-split 5.4 — producing a bogus −87% trend and a −13.58 derived Q4 from mixed NI/EPS pairs in the share-implied derivation. Detection needs 2 corroborating (start,end) durations at a split ratio (3% tolerance) so a lone accounting correction can't trigger it; the split date is never estimated, only relative order (filed-before vs filed-after the restating filing) plus neighbor checks.

## 2026-09-30 — Mobile bottom-sheet period selector (PRD §4.2)

**What:** Below `md`, the detail-view slicer panel becomes a fixed bottom sheet (compact "Period" button opens, Apply/Escape/backdrop dismiss); the closed state is pure CSS (`translateY(105%)` under a 767px media query), Alpine only toggles `.open`.
**Why:** PRD §4.2 specified the bottom sheet but it was never built; the CSS-first closed state avoids a flash of the open sheet on mobile before Alpine initializes, and keeps desktop markup identical (one shared form, no duplicated inputs to drift).

## 2026-09-30 — Berkshire ticker normalization + IFRS filer error (defect-hunt round 15b)

**What:** `cik_for_ticker` falls back to hyphenated SEC forms (`BRK.B`→`BRK-B`); search normalizes `./`→`-` for ticker comparisons only; `_chain_candidates` raises `UnsupportedFilerError` naming actual taxonomies when `us-gaap` is absent (TSM → ifrs-full).
**Why:** `BRK.B` 404'd despite being trivially resolvable — the most common ticker-format mismatch on the web. Foreign private issuers died with bare `KeyError: 'us-gaap'`; IFRS tag-mapping is out of scope (US public companies per PRD), so a clear "not supported" beats a cryptic key.

## 2026-10-03 — Popular bar: live day-change % instead of hardcoded seed (defect-hunt round 16)

**What:** `FinancialsService.get_popular_stocks()` now serves the live session day-change percent from Yahoo Finance through a new thread-safe TTL `QuoteCache` in `data/yahoo.py` (5-minute TTL, injectable fetch/clock for tests). The previously hardcoded percents (frozen at 2026-09-30) are demoted to a static fallback seed. The render path is non-blocking: `peeked_day_change_pct()` reads only fresh cache entries, and `warm_change_pct_cache()` refreshes stale entries in a single background daemon thread (serialized by a module lock; a fresh-but-None entry counts as fresh so repeated Yahoo failures don't spawn fetch storms). `get_popular_stocks()` never raises — any failure falls back to the seed.
**Why:** Round-16 defect hunt found the "Popular" bar presenting week-old day-change numbers as live market data (NVDA showed +3.1%; live was +1.34%). Backend-only fix — the template already handles `change_pct is not none`, so no template change (Gemini owns UI; nothing to re-verify visually). Serving the seed on a cold first load keeps the home page instant; the next render (seconds later) picks up live values.
**Hunt non-findings (recorded, not fixed — data-source limits):** XOM yields only 2 rows because SEC companyfacts holds just the Q2-2026 10-Q (honest output; sparse-window YoY/QoQ guards already render "—"); AMT's Q4-2025 derived revenue ($2,737.5M) exactly equals Q1-2026 ($2,737.5M) — verified against raw facts as a genuine arithmetic coincidence, not a labeling bug; NEE is missing Q2-2026 in companyfacts (10-Q filed 2026-07-24, SEC processing lag). DIS's FYE-1003 labels verified correct (FY2026 Q1 end 2025-12-27).

## 2026-10-03 — Yahoo quote caching + timeout hardening (batch 14, performance & robustness)

**What:** (1) `FinancialsService.refresh_watchlist_quotes()` now reads quotes through the batch-13 `QuoteCache` (5-minute TTL), so rapid repeat clicks on the home refresh button don't re-hit Yahoo; the per-ticker never-wipe / count-don't-raise policy is unchanged. (2) `data/yahoo.py::_fetch_info()` wraps every `yf.Ticker(ticker).info` read in a shared 4-worker thread pool with a 15-second hard timeout — yfinance sets no socket timeout of its own, so a stalled connection previously blocked the caller indefinitely (enrichment, refresh, background warmer). Executor-shutdown `RuntimeError` (background warmer outliving process teardown) converts to `TimeoutError`, keeping the never-raise contracts of `get_quote` / `get_day_change_pct` / cache entry points and silencing teardown tracebacks.
**Why:** Measured route timings on :8123 show the app is already fast (home 0.26s cold / 0.07s warm, search 0.006s warm, overview 0.08s, detail 0.03s) — the batch-13 background-warmer design adds zero render latency, so batch 14's wins are correctness-under-failure rather than shaving milliseconds: every Yahoo read is now bounded, and repeated refreshes are deduped. Hardening audit: EDGAR already has a 30s timeout, Wikipedia 10s with None-on-error, SEC `fetch_json` never caches a malformed body (`.json()` raises before the cache write), and first-visit company fetches degrade to the friendly 404 page on any exception. No template changes (Gemini owns UI).

## 2026-10-05 — Latest news on the company overview page (user feature request)

**What:** New "Latest News" section on `/company/{ticker}` showing the 6 freshest headlines with source badge, relative age, and external link. Backed by `services/news.py`: Google News RSS (`{ticker} stock` query), thread-safe 30-minute TTL `NewsCache`, and a `GET /company/{ticker}/news` route rendering `partials/news.html`. The section lazy-loads via HTMX (`hx-trigger="load"`) so a slow news feed never blocks the page; every layer never-raises (fetch failure → stale cache → empty-state message, never a 500).
**Why:** User asked for "the latest news for those companies" after Gemini finished. Yahoo Finance's per-ticker RSS is bot-blocked from our servers (returns the "Will be right back" page), so Google News RSS is the source — free, keyless, verified working from this VM (100 items for AAPL). 30-minute TTL fits news cadence (slower than quotes). Design matches Gemini's card language (indigo source badges, dark-mode aware).

## 2026-10-05 — Startup schema migration fixes Gemini's missing-column 500s

**What:** `models/database.py::ensure_schema()` runs in the app lifespan after `create_tables()`: inspects each known table and `ALTER TABLE … ADD COLUMN` for any model column missing from the actual DB. Never raises.
**Why:** Gemini's disclosures commit added 4 columns to `quarterly_financials` with no migration, so every existing database (including this dev server and the user's local app) 500'd on all company pages after pulling. `create_all` only creates missing tables, not columns. This generic migration covers future column additions too, and is covered by `tests/test_schema_migration.py` (drop-then-restore + idempotency).

## 2026-10-05 — Batch 15: Gemini integration audit — Yahoo symbol normalization + honest cap tier

**What:** (1) `data/yahoo.py::yahoo_symbol()` normalizes display tickers to Yahoo's symbol format (`.` → `-`) inside `_fetch_info`, so `BRK.B` quotes as `BRK-B`; `data/calendar.py::fetch_earnings_calendar` uses the same normalizer (it had the identical flaw). (2) `services/ai_analysis.py::_determine_cap_tier` returns `"Unknown"` instead of `"Mid-Cap"` when market cap is missing — the old default rendered Berkshire Hathaway as Mid-Cap in the AI briefing because its quote was blank. (3) Data fix: backfilled BRK.B's market cap ($1.08T) via `enrich_company`.
**Why:** Batch-11's ticker normalization fixed SEC resolution for `BRK.B` but the Yahoo quote path still passed the dotted form to yfinance, which returns an empty `info` dict — silently blanking price AND market cap downstream (overview header, valuation, AI tier). The audit also verified Gemini's AI analysis, peers, calendar, tearsheet, and 8-K disclosure wiring against real data (AAPL/XOM/BRK.B/NEE): all render correctly; disclosure extraction is fill-on-missing by design, so existing rows without guidance/transcripts are expected until re-enrichment.
**Tests:** `yahoo_symbol` normalization, `_fetch_info` uses the Yahoo symbol (mocked yfinance), `_determine_cap_tier(None)` → Unknown. 311 green.

## 2026-10-05 — Batch 16: home-page hang on cold earnings-calendar cache (performance fix)

**What:** `get_upcoming_earnings()` fetched all 52 tracked tickers' Yahoo calendars *sequentially* (10s timeout each → up to ~9 minutes) on the home-page render path. `/` hung >2 min on a cold cache this run. New `get_cached_upcoming_earnings()`: peek-only calendar reads (`CalendarCache.peek`/`event_fresh`, never fetch) + `warm_earnings_cache()` background daemon warmer (module-lock serialized, never raises — mirrors the batch-13 popular-bar pattern). Home now serves `[:4]` of dated events from cache (0.19s cold) and the strip populates on the next render; the `/calendar` page keeps the blocking variant (fast on warm cache). Shared `_earnings_companies`/`_build_earnings_events` helpers dedupe the two readers.
**Why:** The landing page is the worst possible place for an unbounded sequential network fan-out. Live-verified: `/` 200 in 0.19s cold, earnings strip populated within ~70s (PEP 2026-10-08, DPZ/GS 2026-10-13); `/calendar`, `/company/AAPL`, `/company/BRK.B`, `/api/search` all 200 and fast.
**Tests:** 8 new (peek cold/fresh/stale, event_fresh, warmer background-populates + never-raises, service cached-never-fetches / cached-serves / blocking-still-fetches). Suite at 319 green.

## 2026-10-05 — Automatic quote refresh & in-memory peek to prevent lagging stock prices

**What:** (1) Company overview, detail, tearsheet, and head-to-head comparison routes now invoke `FinancialsService.refresh_company_quote(ticker)`, which queries Yahoo Finance through the 5-minute TTL `QuoteCache` (`cached_quote`) and persists the updated `last_price` and `market_cap` directly into SQLite (`Company` table). (2) `FinancialsService` methods (`get_overview`, `get_valuation`, `get_detail`, `get_watchlist`, `get_benchmarks`, `get_comparison`) now check `peeked_quote(ticker)`: fresh in-memory quotes take priority over stored values, with seamless fallback to `Company.last_price`. (3) Added `warm_quote_cache()` and `warm_tracked_quotes()` to prewarm tracked tickers in the background without blocking render paths. (4) Backfilled current market quotes for all 15 existing database companies (e.g. APLD updated from stale June 2026 $40.95 to live $24.70).
**Why:** User reported APLD displaying $40.95 instead of its live ~$24.70. Root cause: company quotes were only fetched during initial ingestion (`enrich_company`), and never refreshed during read/view workflows unless manually triggered via `/company/{ticker}/refresh`. As a result, stored prices drifted months behind reality, distorting valuation models, implied upside percentages, and AI briefing theses. The new architecture guarantees quotes remain within the 5-minute TTL while preserving offline test determinism (tests use DB defaults without network calls) and never-wipe reliability on network timeout.
**Tests:** 6 new tests across `test_yahoo_cache.py`, `test_financials.py`, and `test_company_routes.py` (quote_fresh, peek_quote, background warmer, quote refresh persistence, failure never-wipe, route integration). Suite at 325 green.

## 2026-10-05 — Batch 17: quote-refresh integration audit (3 defects fixed)

**What:** Audit of the new automatic-quote-refresh commit (b9e03d7) found and fixed three defects. (1) **Cache-key normalization:** batch 15's `yahoo_symbol()` normalized only the Yahoo *request*, not the cache *key* — `BRK.B` and `BRK-B` occupied two `QuoteCache` entries, causing duplicate Yahoo fetches (each with a 15s timeout risk) and peek misses depending on which spelling the caller used. New `_cache_key()` in `data/yahoo.py` normalizes all six cache methods (quote + day-change). (2) **Write amplification in `refresh_company_quote`:** every overview/detail/vs/tearsheet page view did an EDGAR `_resolve_cik` (disk re-read + JSON parse + linear scan of `company_tickers.json`), opened a DB session, and committed a write transaction even when the quote was fresh and unchanged. New fast path returns the fresh peeked snapshot immediately; the slow path commits only when `last_price`/`market_cap` actually changed. Safe because every display path already prefers the peeked quote over the DB value. (3) **Discard-and-recompute in routes:** overview/detail/tearsheet computed `get_overview`/`get_detail`/`get_valuation`, threw the result away, then recomputed after refresh — roughly doubling the XBRL/DB work per request. Routes now refresh first (never raises) and compute once; 404 semantics unchanged.
**Why:** The feature was correct in intent (prices were lagging months behind) but its first implementation doubled per-request work and took a write lock on every page view — the kind of thing that degrades under the background warmers' concurrent commits.
**Tests:** 5 new (quote/change cache key normalization incl. single-fetch assertion; fast-path skips CIK lookup; no commit when unchanged; overview computes exactly once). Suite at 330 green. Live: 7/7 checks on :8123 (home, overview, detail, tearsheet, vs, BRK.B overview, invalid-ticker 404); warm overview 0.21s.

## 2026-10-06 — Batch 18: 8-K disclosure integration audit (5 defects fixed)

**What:** Audited Gemini's 8-K guidance/transcript extraction feature (shipped 2026-10-05) against real data for NVDA/TSLA/JPM/AAPL/MSFT. The feature's pipeline (discovery → exhibit pick → extraction) was sound, but five integration defects left most tickers showing "Not available for this period": (1) `get_detail` now lazily backfills missing disclosures for tickers first fetched before the feature shipped (`enrich_company` only runs on first fetch) — best-effort/never-raises, commits only when it owns the session, short-circuits once filled; (2) `_match_8k` re-anchored from the 10-Q/10-K filing date (21-day window) to the period end (first Item 2.02 8-K within 60 days) — the old rule systematically missed annual periods since 10-Ks lag earnings by 4+ weeks (JPM: 2/4 → 4/4 matched); (3) `_pick_release_doc` now penalizes "supplement" exhibits so JPMorgan's narrative release wins over the 3.3MB tables supplement (which had yielded table-of-contents "highlights" and no guidance/quotes); (4) `_QUOTE_RE` extended to speaker-first attribution (`Dimon, Chairman and CEO, commented [on the financial results]: "…"`) — the old quote-first-only pattern missed JPM's format entirely; (5) `_assign_fy_and_quarter` counts quarters back from the group's 10-K (Q4) instead of forward from Q1, fixing mislabeled source strings for non-calendar fiscal years (NVDA 2024-10-27 was "Q1 FY2025", now "Q3 FY2025"). Enrichment refill is per-field never-overwrite (a test caught the first version clobbering existing highlights when refilling guidance).
**Why:** The feature was the headline of Gemini's final commit set, but on real data it was a dead feature for most of the DB: guidance 0/5 and transcript 0/5 tickers populated. Each defect was verified against live SEC filings before fixing (JPM's actual 8-K index, NVDA's real outlook text). Banks genuinely don't publish guidance sections, so JPM's guidance=None is correct output, not a miss.
**Tests:** 14 new (backfill fills + never-raises on discovery failure; partial refill without overwrite; full-row short-circuit; 3 quarter-label cases; 4 8-K matcher cases; 2 exhibit-picker supplement cases; 2 speaker-first quote cases). Suite at 344 green. Live on :8123: 6/6 routes 200 (JPM/NVDA/AAPL detail, AAPL overview/vs/tearsheet); NVDA detail renders the real $108.0B revenue outlook, JPM detail renders Dimon's Q2 quote.
**Follow-ups (not this batch):** JPM's 4 oldest quarters are undiscoverable — SEC submissions "recent" window only covers ~1yr for heavy filers (26k filings); would need the archived `files` arrays. TSLA 2/3 periods have no ex-99 (release embedded in primary 8-K doc — not handled, by design). AI-analysis Unknown-tier copy ("a Unknown filer prioritizing insufficient market data") still needs a copy fix.

## 2026-10-06 — Batch 19: AI-briefing Unknown-tier copy fix (batch-18 follow-up)

**What:** `_determine_cap_tier` returns a `None` focus for the "Unknown" tier; the AI briefing's executive summary and theses branch on it. Unknown now reads "No size tier is assigned — market capitalization data is insufficient." (summary) and "Market capitalization data is unavailable, so no size-tier emphasis is assigned — the score stands on fundamentals alone." (theses). Previously both slots interpolated "Unknown" + "Insufficient market data" into copy that assumed a known tier, producing "Evaluated as a Unknown filer prioritizing insufficient market data."
**Why:** Batch 15 made the tier honest ("Unknown" instead of a wrong "Mid-Cap"), but the copy strings were written for tiers that have an investment emphasis — a size tier of "Unknown" has no emphasis, so interpolating it into that sentence frame produced nonsense copy whenever a quote was missing (PYPL/LMT/ZTS in the DB had no market cap before the auto-refresh filled PYPL's live). The badge `cap_tier` still shows "Unknown" — honest, no change needed there.
**Tests:** `_determine_cap_tier` Unknown → `("Unknown", None)` + known-tier focus intact; `generate_ai_analysis` with `market_cap=None` renders the honest copy and none of the old broken phrasing, plus a known-tier (NVDA) regression of the original phrasing. Suite at 346 green. Live on :8123: 5/5 checks 200 (PYPL overview shows the refreshed Large-Cap briefing, DUOL overview renders the fixed "Evaluated as a Mid-Cap filer…" phrasing, AAPL overview/tearsheet, BRK.B overview).

## 2026-10-06 — Batch 20: Peer Intelligence coverage-gap fix (no visual change)

**What:** Audited Gemini's "Sector Peers" row (`get_peers_for_company`, chips on Overview/Detail headers linking to `/vs/`) against all 55 stored companies. 12 of the 24 sampled had zero peers and the row silently vanished for them. Root causes: (1) the curated map covered ~30 tech/finance/health tickers but no energy/industrial/defense/insurance/telecom/media flagships; (2) the SIC-prefix fallback table had only 10 industries; (3) same-SIC DB matching requires exact 4-digit SIC, too narrow for e.g. HD (5211 retail, no exact-SIC peers stored). Fix in `services/peers.py`: 13 new curated flagship entries (XOM, CAT, LMT, BRK.B, T, DIS, NFLX, HD, PG, NKE, DPZ, PLUG); prefix table expanded from 10 to ~35 industry prefixes; matching now longest-prefix-first so specific prefixes beat general ones (283 pharma > 28 chemicals, 596 e-shopping > 59 retail, 367 semis > 36 electronics). Dedupe/self-exclusion/limit ordering unchanged; curated still wins over prefix (BRK.B test asserts its curated list, not the 63 insurance list).
**Why:** A feature advertised as "automated peer group" rendering nothing for Exxon, Lockheed Martin, Berkshire, Disney, Nike, etc. made it look broken/empty for exactly the tickers a user would check first. The fix is data-only (curated lists + prefix tables), no template or styling change, so no screenshot was needed per the UI rule.
**Tests:** 6 new (new flagship curated entries + self-exclusion; uncurated-ticker prefix fallback; longest-prefix-first on 283/367 vs 28/36; insurance/telecom prefixes; curated-beats-prefix precedence; limit/dedupe). Suite at 352 green. Live on :8123: 4/4 overview checks 200 (XOM, BRK.B, LMT, DIS); peer chips render on all (e.g. LMT → RTX/NOC/GD/BA/HII — previously absent; BRK.B → AIG/MET/CB/TRV/PGR with MET marked stored). DB-wide: 0 zero-peer tickers remaining (was 12+). LMT's first load was 9.26s — cold Yahoo quote fetch, not the peers change (zero new network calls; warm rerun 0.15s).

## 2026-10-06 — Batch 21: FY-label collision arbitration + unsupported-filer message (defect hunt)

**What:** Fresh-ticker hunt on ORCL (May year-end), MU, MRNA, SPG (REIT), F, and ASML (20-F/EUR). Found two defects. (1) `_dedupe_period_labels` in `data/xbrl.py` resolved (fy, fp) collisions by trusting the *later* end's label ("its original filing is the trustworthy source") — but a filer's newest filing can itself mislabel the current quarter's fy: Oracle's Sep-2026 10-Q tags Q1 FY2027 as fy=2026 (colliding with the correctly labeled Q1 FY2026), and Salesforce's Jan 10-K tags Q4 FY2026 as fy=2025 (colliding with Q4 FY2025). The old rule walked the *correct* rows back — ORCL's Q1 FY2026 rendered "FY2025 Q1", CRM's Q4 FY2025 rendered "FY2024 Q4". Fix: sequence-consistency arbitration — on collision, if the earlier end's claim matches the quarter-sequence expectation from its predecessor, it keeps the label and the later end is relabeled to its own expectation; only when there is no sequence context (first row, or a gap) does the legacy later-keeps/earlier-walks-back rule apply. Rows without a collision are never touched. (2) ASML hard-failed `fetch_and_persist` with a bare `KeyError: 'No XBRL facts found for metric revenue'` (EUR-only revenue facts rejected by the USD unit filter; 20-F forms rejected by the 10-Q/10-K form filter) and the company routes rendered "Could not fetch data for ASML: 'No XBRL facts found for metric revenue'". `extract_recent_quarterly_financials` now raises `UnsupportedFilerError` with a plain-language reason naming the blockers ("This company reports in EUR; files 20-F, 20-F/A instead of 10-Q/10-K — Tickerlens covers US-GAAP filers reporting in USD with quarterly 10-Q/10-K filings."), and the overview/vs/tearsheet first-visit paths render that message without the generic prefix (detail/compare already render `str(exc)` alone).
**Why:** Wrong FY labels are user-visible in the Time Slicer selectors and detail tables — a user comparing "FY2025 Q1" to "FY2026 Q1" on Oracle would be looking at the wrong quarters. The legacy rule was written for the opposite failure mode (stale comparative columns inheriting a later filing's fy, as in XOM's new-CIK history); the hunt showed filers mislabel in both directions, so the arbiter is now the quarter sequence, which is the one invariant a fiscal year can't violate. Full 20-F/EUR support (annual-only facts, FX conversion) is out of scope; an honest "not covered" message is the correct fix for now.
**Tests:** 6 new — ORCL-style Q1 mislabel arbitration, CRM-style Q4 mislabel arbitration, gap-is-not-repaired (XOM-style sparse history untouched), no-sequence-context legacy walk-back (existing XOM comparative test still passes), ASML-style EUR/20-F companyfacts → `UnsupportedFilerError` naming EUR and 20-F, generic-reason fallback. Suite at 358 green. Live on :8123: ORCL + CRM re-seeded from SEC — all 8 quarters sequence-consistent (ORCL: 2025-08-31 → Q1 FY2026, 2026-08-31 → Q1 FY2027; CRM: 2025-01-31 → Q4 FY2025, 2026-01-31 → Q4 FY2026); /company/{ORCL,CRM,MU} + detail pages 200 with corrected labels; /company/ASML → 404 with the plain-language message. No template change (backend-only). MU's $1045 quote verified against Finnhub/market data — the memory-supercycle price is real, not a quote defect.

## 2026-10-06 — Batch 22: Tearsheet integration audit (no defects found)

**What:** Audited Gemini's institutional tearsheet (`GET /company/{ticker}/tearsheet`, `templates/company/tearsheet.html`) against real data: AAPL, BRK.B, XOM, NVDA, plus a fresh first-visit fetch (IBM, seeded live from SEC in 24.6s) and edge cases (ASML unsupported filer, ZZZZZ unknown ticker).
**Verdict:** No defects. First-visit path works (full 8-quarter matrix, AI briefing, real Item 1A risk factors for IBM); 404s clean; sparse histories (XOM, 2 quarters under the new CIK) degrade gracefully; genuine SEC data gaps render "—" correctly rather than erroring — BRK.B's `EarningsPerShareDiluted` tag genuinely absent from companyfacts since ~2013 (basic EPS stops there too; Berkshire stopped filing per-share EPS in XBRL), and XOM's FCF is not computable because its cash-flow facts are 6-month YTD durations with no Q1 to difference against (correct quarterly accounting, not a bug). Batch-18 NVDA 8-K guidance ($108.0B Q3 FY2027 outlook) renders in the disclosure digest. XOM's "Manufacturing" sector label is the SIC-division mapping (29xx petroleum refining is SIC Division D) — consistent with the rest of the app, not a defect.
**Why no change:** An audit batch that finds nothing must say so rather than invent work; no code or template change was made, so no screenshot and no commit. Suite stays at 358 green.

## 2026-10-06 — Batch 23: earnings-calendar display ticker, cache-key normalization, parallel cold fetch

**What:** Audited the earnings-calendar path (`data/calendar.py` + `FinancialsService` calendar methods + `templates/calendar.html`) against live Yahoo data for all 58 DB companies. Three defects fixed: (1) the Yahoo-normalized ticker ("BRK-B") leaked into display on `/calendar` and the home "Imminent Earnings Catalysts" strip — `_build_earnings_events` now renders the DB canonical ticker ("BRK.B"); (2) `CalendarCache` keys now go through `yahoo_symbol()` so dotted/hyphenated spellings share one entry (closes the calendar half of the batch-17 QuoteCache key-normalization fix); (3) new `CalendarCache.prefetch()` (6-worker concurrent, never-raises) is called by `get_upcoming_earnings` before the serial `get` loop and by the background warmer — cold `/calendar` went from ~17s to ~4s for 58 tickers (measured server-side). Sort order is now upcoming-soonest → reported (most-recent first) → TBD, since the old date-ascending sort led with already-reported events on a page titled "Earnings Calendar".
**Why:** The ticker-form leak was user-visible on exactly the flagships a user checks first (Berkshire); the cache-key split would have doubled Yahoo fetch volume for every dotted ticker once dotted spellings enter the cache from multiple paths; and a ~17s cold render on the dedicated calendar page was the same class of hang batch 16 fixed on the home page.
**Tests:** 6 new — cache shares one entry across "BRK.B"/"BRK-B" (+ peek/fresh spelling-insensitive), prefetch completes 4 slow fetches in <0.9s, prefetch never raises on a failing fetch fn, `_build_earnings_events` renders the DB ticker and marks watchlist, sort key orders upcoming → reported → TBD. Suite at 364 green. Live: `/calendar` 200 (BRK.B ×3, BRK-B ×0), home strip 200, watchlist filter 200.
**Follow-ups (not this batch):** none pending — calendar path is clean.

## 2026-10-07 — Batch 24: Latest News integration audit (2 defects fixed)

**What:** Audited the Latest News feature (Google News RSS, 30-min TTL, shipped 2026-10-05) against live data for AAPL, BRK.B, T, F, and ZZZZZ. Two defects fixed, both in `services/news.py`. (1) **fix** ambiguous-ticker queries — the query was always `"<TICKER> stock"`, which mis-resolves single-letter tickers: "T stock" returned Japanese 6098.T results, CNN/Yahoo quote pages, and unfilled `symbol__` placeholder headlines. The news route now does a cheap never-raises DB lookup for the stored company name and `get_company_news(ticker, company_name=...)` builds `"<name> stock"` ("AT&T Inc. stock" → real AT&T headlines); bare-ticker fallback retained when the name is unknown. Cache is still keyed by canonical ticker (case-insensitive); the query is what flows into the fetch. (2) **fix** quote-page artifact filter — RSS entries that are quote pages rather than news (`Yahoo "Stock Price, News, Quote & History"`, `CNN "Stock Quote Price and Forecast"`, `symbol__` unfilled templates) are dropped at parse time.
**Why:** The Latest News section sits on the company overview — the most-visited page — and for AT&T it showed a literal placeholder headline plus a Japanese recruit company: user-visible junk on a flagship tickers a user would check first. Name-based search is strictly better for ambiguous tickers and roughly equivalent otherwise (verified BRK.B/AAPL still relevant).
**Tests:** 5 new (`_build_query` name preference + blank/None fallback; artifact filtering on a junk-headline fixture; cache query passthrough + case-insensitive key + no refetch; updated stale-cache/fake-fetch signatures for the new `(query, limit)` fetch shape). Suite at 367 green. Live on :8123 (restarted to pick up the change): `/company/{T,F,BRK.B,AAPL}/news` all 200, relevant headlines, zero junk markers.
**No template change** (backend-only; the partial renders the same).

## 2026-10-07 — Batch 25: AI fundamental-analysis integration audit (4 defects fixed)

**What:** Audited the AI fundamental-analysis engine (`services/ai_analysis.py`, Gemini's PRD §4.4 roadmap item) against live data for all 58 DB companies — the first full integration audit of this engine (batch 19 only touched its Unknown-tier copy). Four defects fixed, all backend-only: (1) **fix** sector-aware solvency — the industrial assets/liabilities ladder scored every bank 40/100 solvency at ~1.08x (deposit-funded balance sheets read as distress), dragging bank composites down ~5 points and flipping MET's signal to Avoid (46) on a healthy insurer. New `_solvency_score(ratio, sector)` gives financials (banking/securities/insurance) and REITs calibrated ladders; industrials keep the original ladder; the 40-point floor still catches genuinely thin sheets (<1.03x for banks, <1.2x for industrials). (2) **fix** Strong Sell divergence note — the briefing rendered "Watch" next to the valuation card's Strong Sell (e.g. TSLA 66/100 vs −97.6% model target) with no acknowledgment; a "Valuation check" thesis now reconciles them explicitly. Deliberately a copy-level fix, not a signal-map redesign — the map's fundamentals-first weighting is Gemini's PRD §4.4 design, and changing it would be a methodology change, not a defect fix. (3) **fix** missing YoY → neutral 50 growth (was 55 via the flat-growth ladder). (4) **fix** sector-aware revenue-thesis copy for financials. Verified live on :8123 (`/company/{JPM,TSLA,MET,AAPL}` all 200; JPM briefing shows the financial copy + 87/100; MET flipped Avoid→Watch with the divergence note; AAPL unchanged with no note).
**Why:** The solvency miscalibration was the highest-impact defect: it systematically understated every financial company's fundamental score and produced a wrong signal (Avoid) for MET. The divergence note fixes a user-visible contradiction between the two recommendations on the same page without redesigning either model.
**Tests:** 6 new (`_solvency_score` sector ladders; bank solvency + financial thesis copy; REIT partial credit; divergence note fires on Strong Sell + Watch with exact copy; no note when Avoid or bullish; missing-YoY neutral growth). Suite at 373 green.
**Follow-ups (not this batch):** the valuation model itself emits extreme targets for some tickers (F +641%, T +357% via the sales/peg clamps) — documented heuristic territory, not an AI-engine defect; left untouched. The pending 10Y-yield wiring offer (valuation benchmark 4.5% vs live ~5.3%) still awaits the user's word.

## 2026-10-07 — Batch 26: valuation sales-fallback margin anchor (1 defect fixed)

**What:** Audited the valuation model's extreme targets (batch-25 follow-up: F +641%, T +357%) against live data for all 58 DB companies. One defect fixed, in `services/valuation.py`. The sales fallback (`fair P/S = 0.5 × TTM revenue growth %`, clamped [1×, 10×]) was margin-blind: it valued loss-making Ford at 1.9× sales on 3.8% revenue growth while Ford's own margin profile trades at ~0.3× — fabricating a Strong Buy with +641% implied upside. The same curve emitted a Strong Buy for loss-making PLUG (+47.6%) and clamp-driven Strong Sells for MRNA/INTC/SNOW/NET/RBLX (−53% to −97%, all sitting on the 1× floor or 10× cap rather than data). The fallback is now margin-anchored via the accounting identity P/S = P/E × net margin: fair P/S = (PEG-implied fair P/E on the same curve as the primary path — growth clamp, [8×, 40×] P/E clamp, batch-12 rate guardrail) × TTM net margin, sanity-capped at 10× P/S with no lower floor. When TTM net margin is not positive there is nothing to anchor the multiple to, so the model returns Watch/unavailable ("No positive TTM earnings, and no positive TTM net margin to anchor a sales multiple — a target price would be a guess, not a model") instead of a target. `compute_valuation` gains a `ttm_net_income` input (wired from `FinancialsService.get_valuation`); PRD §4.11 fallback line updated. Post-fix live audit: F/PLUG/MRNA/INTC/SNOW/NET/RBLX → Watch; BRK.B → Strong Sell −36.6% (fair 1.8×, anchored on ~22% investment-driven margin — direction preserved, multiple now data-driven); V → Strong Sell −37.4% (fair 10× = rate-guarded ~37× P/E × ~55% margin, capped). Verified live on :8123: `/company/F` 200 renders Watch with the anchor copy. No template change (backend-only).
**Why:** A valuation card that says Strong Buy +641% on a company losing $6.1B TTM is worse than no signal — it is an actively misleading headline on the most-visited page. The old curve was calibrated for healthy-margin growers and had no link to the company's own profitability; the identity P/S = P/E × margin is the minimal principled anchor and keeps the fallback for exactly the companies it is meant for (positive-margin, unusable-earnings cases such as turnarounds). The PEG-path extremes (BAC +193%, GS +161%, SPG +160%, T +357%) were audited and deliberately left: all have the rate guardrail binding with Medium confidence and the guardrail note rendered — the model working as designed on unusual-but-real inputs (T's 71% EPS growth is a real TTM-over-TTM figure on a one-off-depressed base quarter). Making the PEG curve sector-aware would be a methodology redesign, not a defect fix.
**Tests:** 5 new (Ford-style loss-maker with negative margin → Watch; zero margin → Watch; margin-anchored identity math 10% × 15× → 1.5× P/S; positive-EPS/no-growth turnaround still gets a sales target; 10× P/S cap + rate-guardrail note on the sales path). One existing sales test rewritten for the new behavior. Suite at 377 green.
**Follow-ups (not this batch):** PEG-path sector calibration (e.g. banks at 37× fair P/E) remains heuristic territory; the live-10Y-yield wiring offer still awaits the user's word.

## 2026-10-07 — Batch 27: honest floor-multiple copy for flat/declining EPS growth (fresh-ticker hunt round 3)

**What:** Seeded 6 new tickers live from SEC (COIN, RIVN, HOOD, UBER, PLTR, O): 8 quarters each, sequence-consistent FY labels, no XBRL defects. The hunt surfaced one user-visible defect on the flagship valuation card. **fix** (`services/valuation.py`): the PEG-path reasoning bullet claimed "A PEG of 1.5 on that growth implies a fair P/E of 8.0×" for companies with EPS growth below the 2% floor — 13 of 64 DB companies (UBER −23.6%, DIS −24.2%, TSLA −35.7%, PFE −59.5%, UNH −32.6%, META −3.8%, JNJ −7.8%, NKE −3.4%, HD −2.9%, SOFI −2.1%, MET −11.4%, PG +1.7%, SHOP −17.3%). PEG is undefined for flat/declining earnings; the 8× came from the distressed-earnings floor (`_MIN_PE`), not from 1.5 × growth. The card now says "Earnings are declining (−23.6% YoY), so no growth premium applies — valued at the 8.0× floor multiple for declining earnings (current P/E is 15.0×)" (and an "essentially flat" variant for 0–2% growth). Methodology unchanged: the 8× floor is the deliberate batch-12 distressed multiple, the "hit the 2% floor" guardrail note still renders, confidence still caps at Medium.
**Why:** A retail investor reading "A PEG of 1.5 on −23.6% growth implies 8.0×" can do the arithmetic and see it doesn't check out — the flagship card must not make false math claims, even when a footnote elsewhere names the clamp. This is a copy defect, not a methodology dispute: the floor heuristic stays, the sentence telling the user *why* 8× is now true.
**Tests:** 3 new (negative growth → honest "declining" copy, no "on that growth implies", floor note still present; flat 1.7% → "essentially flat" copy; positive 20% → unchanged PEG copy). Existing `test_guardrail_caps_confidence_and_names_bound` (the JNJ negative-growth case) still passes unchanged. Suite at 380 green.
**Follow-ups (not this batch):** PEG-path sector calibration remains heuristic territory; the live-10Y-yield wiring offer still awaits the user's word. The sales fallback has no equivalent false claim (its bullet states the fair P/E number, not a PEG implication) — left alone.

## 2026-10-07 — Batch 28: peer-map validity audit (13 peer tickers fixed)

**What:** Audited every ticker in Gemini's peer maps (`_CURATED_PEERS` + `_SIC_PREFIX_PEERS` in `services/peers.py`, PRD §4.2 Peer Intelligence) against the live SEC `company_tickers.json` (221 unique tickers, fetched 2026-10-07) — the first validity audit of this feature (batch 20 only covered zero-peer gaps). Found 13 bad entries in three classes, all fixed with verified replacements:
- **Dead (7, → 404 on click):** DFS (delisted, Capital One acquisition), EA (delisted, take-private), GPS (not in SEC file — Gap is listed as GAP), GRUB (delisted, Wonder acquisition), LC (LendingClub unresolvable in SEC file), SKX (delisted, 3G take-private), SQ (Block changed ticker to XYZ).
- **Wrong company (2, worse than 404 — silently compares against the wrong business):** BYD → BOYD GAMING CORP (casino operator) in TSLA's peers — the EV maker trades OTC as BYDDY, not SEC-listed; PARA → Banzai International (ticker reassigned after the Paramount Skydance merger) in DIS/NFLX curated + 781/784/799 fallbacks.
- **Wrong register (1):** EDTK → Skillful Craftsman Education Technology Ltd (Chinese micro-cap) as a Duolingo peer.
Replacements, all verified resolvable in the live SEC file *and* live-verified as fetchable US-GAAP filers via `/company/{t}/vs/{peer}` (200): TSLA BYD→(dropped — NIO, the listed EV maker, files 20-F in CNY and is unsupported, so TSLA keeps its 4 US peers), DUOL EDTK→LOPE, UBER GRUB→CART, SOFI LC→COF (NU, first tried, files 20-F), RBLX EA→APP, NKE SKX→SHOO (BIRK, first tried, files 20-F), DIS/NFLX PARA→PSKY; fallbacks 61 DFS→ALLY, 73 SQ→XYZ, 56 GPS→GAP, 30 SKX→WWW, 781/784/799 PARA→PSKY + EA→ROKU. The NIO/BIRK/NU misses were caught by actually hitting the vs route before committing — SEC-resolvable ≠ app-fetchable, and the audit now checks both.
**Why:** Peer chips sit on the company overview (most-visited page) and link straight into the compare route. Seven were dead 404 links; two silently compared Tesla against a casino company and Disney/Netflix against a micro-cap marketing firm. The maps are hand-curated data with no test coverage against reality, so they rotted as M&A and ticker changes accumulated.
**Tests:** 3 new (`_KNOWN_BAD_PEERS` blocklist asserting none of the 10 bad tickers appear in any map — guards future rot; curated replacement assertions for all 8; SIC-fallback replacement assertions for all 5). Suite at 383 green. Live on :8123 (restarted): 8/8 overview pages 200 (`/company/{TSLA,DIS,UBER,DUOL,SOFI,NKE,RBLX,NFLX}`), zero bad peer links site-wide, `/company/{DIS,UBER,RBLX,DUOL,NKE,SOFI}/vs/{PSKY,CART,APP,LOPE,SHOO,COF}` all 200. No template change (backend data-only).
**Follow-ups (not this batch):** peer maps remain hand-curated — consider a scheduled re-validation of the blocklist test against the live SEC file (it currently runs against a static list). PEG-path sector calibration + live-10Y-yield wiring still await the user's word.

## 2026-10-07 — Batch 30: tearsheet divergence callout (1 defect fixed)

**What:** Audited Gemini's institutional tearsheet (`/company/{ticker}/tearsheet`, PRD §4.8/§5.5) against live data for TSLA/JPM/UBER/F/AAPL/NVDA — the first integration audit of this route (prior batches only smoke-checked 200s). One defect fixed, in `templates/company/tearsheet.html`. The batch-25 "Valuation check" divergence thesis is appended 5th in `ai_analysis.theses` (after the price-target thesis), but the tearsheet renders only `theses[:3]` — so the printed tearsheet showed the AI signal Watch 66/100 next to the Valuation Verdict Strong Sell −97.7% with no reconciliation, reproducing in print the exact contradiction batch 25 fixed on the overview page (fires on TSLA and UBER). The note now renders as a highlighted "Valuation × Fundamentals" amber callout directly beneath the Market & Valuation Overview Bar, and is excluded from the Key Theses list loop to avoid duplication; tickers without a divergence render byte-identical pages.
**Why:** A printable "institutional" research artifact that silently shows two contradictory recommendations with no explanation is a trust defect, not a design choice — and the fix is presentation-only (the sentence already exists in the backend; the template was dropping it). Placed under the valuation verdict rather than in the AI section because it is a valuation-card reconciliation, not an AI thesis.
**Tests:** 2 new route-level tests (`_tearsheet_client` stub service): callout renders exactly once with the divergence note present; no callout and no "Valuation check:" text when absent. Suite at 391 green. Screenshot gate: styled before/after screenshots of `/company/TSLA/tearsheet` compared — amber callout visible under the valuation bar, all other sections pixel-unchanged.
**Follow-ups (not this batch):** PEG-path sector calibration remains heuristic territory; the live-10Y-yield wiring offer still awaits the user's word.

**What:** Audited batch 29's `refresh_financials_if_stale()` (wired into every overview/detail/tearsheet route) against live data. One defect fixed, in `services/financials.py` + `models/company.py`. The refresh trigger compared the latest 10-Q/10-K *filing date* against the max *period end* in the DB — but a filing date always postdates its period end, so the condition was vacuous; the only effective guard was the in-memory `processed` state, lost on every restart. After each deploy/restart, the first page view of every tracked company ran a full redundant XBRL re-pull (verified live: fresh-process call returned True for AAPL with nothing new filed). New persisted `companies.xbrl_filings_processed` column (nullable String(10); `ensure_schema()` auto-migrates existing DBs at startup): `fetch_and_persist` records the latest quarterly filing date from its already-fetched submissions feed (never wiped when the feed has no quarterly forms), and the refresh now fires only when EDGAR shows a filing newer than the marker. Pre-marker legacy rows get one heuristic pass against max period_end, then are marked — self-healing, no backfill script.
**Why:** The auto-refresh runs on every company page view; a trigger that re-pulls after every restart is a silent latency/cost defect on the hottest path, and the vacuous comparison meant the "staleness" logic could never actually distinguish fresh from stale across restarts. Persisting the marker makes the check correct by construction; keeping the in-memory TTL state unchanged preserves the 6h EDGAR politeness bound.
**Tests:** 4 new tests in `tests/services/test_financials.py`: redundant-pull regression (real AAPL shape — 10-Q filed 2026-07-31, period ended 2026-06-27, marker set → no pull), genuine-new-filing trigger (marker older → refresh runs), `fetch_and_persist` records the marker, and a form-less submissions feed doesn't wipe it. Suite at 395 green. Live-verified on :8123 as documented in the PROJECT_STATUS row.
**Follow-ups (not this batch):** PEG-path sector calibration remains heuristic territory; the live-10Y-yield wiring offer still awaits the user's word.

---

## 2026-10-08 — vs route now triggers filings auto-refresh (batch 32)

**What:** `GET /company/{ticker}/vs/{other}` now calls `refresh_financials_if_stale()` for both tickers before building the comparison — the same never-raises, 6h-TTL-guarded call the overview/detail/tearsheet routes already make.
**Why:** Auditing the vs page against live data surfaced stale pre-batch-8 rows: GS (SIC 6211) rendered Free Cash Flow $5.60B and UNH (SIC 6324) $10.25B on the vs page while every other surface rendered "—" — the batch-8 finance-SIC FCF suppression only applies at seed time, and these rows were seeded before it. Both self-healed the moment their overview pages were viewed during the audit (batch-31's one-time legacy re-pull NULLed the FCF and set the markers), but the vs route had no such path and would have served stale rows indefinitely.
**Alternatives considered:** A startup backfill NULLing finance-SIC FCF was considered but rejected — the batch-31 auto-refresh already self-heals stale rows on view; the gap was only that the vs route never triggered it. No data migration needed.
**Tests:** 1 new route test (`test_company_vs_refreshes_filings_for_both_tickers`) asserting the vs endpoint refreshes both tickers' filings. Suite at 396 green. Live on :8123: `/company/{AAPL/vs/MSFT,JPM/vs/GS,UNH/vs/MET}` 200 with "—" FCF for all finance sides, `/company/{AAPL,GS/detail}` 200, zero server errors.
**Follow-ups (not this batch):** None — vs-mode audit found no other defects (404s, fiscal-calendar note, same-ticker 50/50 bars, swap toolbar all verified).

---

## 2026-10-08 — Batch 33: partnership equity mapping + honest sales-path copy (fresh-ticker hunt round 4)

**What:** Seeded ET, DUK, UNP, GE live from SEC (8 quarters each, sequence-consistent FY labels, no XBRL defects on the three corporates). Two defects fixed.
**fix** (`data/xbrl.py`): partnership-structure filers report equity as `PartnersCapital`, not `StockholdersEquity` — ET's `TOTAL_EQUITY` chain had no such tag, so `total_equity` stored None for all 8 quarters and `total_liabilities` blanked for the newest quarter (ET files no standalone `Liabilities` tag at all; the `_derive_missing_balance_sheet` identity Assets = Liabilities + Equity needs equity). The chain now includes `PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest` and `PartnersCapital` in total-then-parent order, mirroring the corporate pair; the existing chain gap-fill supplies the newest quarter (ET abandoned the corporate tag after 2026-03-31). Verified identical values where the tags overlap (45.344B / 49.010B / 49.737B), so no value changes on overlapping ends — gap-fill only adds the missing 2026-06-30 end ($50.522B; derived liabilities $97.646B = 148.168 − 50.522).
**fix** (`services/valuation.py`): the sales-path rationale bullet "No positive TTM earnings — valuing on sales instead (less reliable)" is false for every company that reaches that path — the path is guarded by a positive TTM net margin, so TTM earnings are necessarily positive; what is missing is per-share EPS data to anchor a P/E multiple (ET is an MLP that files no XBRL EPS facts at all, verified across all companyfacts namespaces). The bullet now reads "No per-share earnings to anchor a P/E multiple — valuing on sales instead (less reliable)." Methodology unchanged.
**Why:** Same defect class as batch 27's false PEG-math claim — the flagship valuation card must not make false statements, even when the numbers are right. And a blank equity column on every quarter of a $72B company is a data-coverage defect, not a styling choice; partnership filers (MLPs/LLCs) are a recurring filer class, not a one-off.
**Alternatives considered:** Deriving equity from Assets − Liabilities was considered but rejected — ET files no standalone `Liabilities` tag either, so both sides were missing; mapping the actual filed concept is exact, derivation is the fallback. Restricting the new tags to partnership SICs was considered but rejected — the chain's freshness/gap-fill rules already make the tags inert for filers that never report them (verified: existing equity tests unchanged).
**Tests:** 3 new (PartnersCapital-only filer maps; ET's real tag-switch shape gap-fills the newest quarter; sales-path copy never claims "No positive TTM earnings"). Suite at 399 green.
**Follow-ups (not this batch):** ET's sales-path Strong Buy +175.8% (fair P/S 1.8× on 4.9% margin × rate-capped 37× fair P/E, revenue-growth-driven) is heuristic territory per batch-25/26 — Medium confidence with the rate note and FCF-yield cross-check disclosing the drivers; sector-aware PEG/sales calibration would be a methodology redesign. PEG-path sector calibration + live-10Y-yield wiring still await the user's word.

## 2026-10-08 — Batch 34: home-page audit, same-day earnings pill fix

**What:** Audited the home landing page against live data (marquee, earnings strip, calendar, benchmarks, watchlist pin/unpin, search). Found + fixed 1 defect.
**fix** (`src/tickerlens/templates/index.html`): the "Imminent Earnings Catalysts" strip rendered "In 0d" when `days_until == 0` (PEP reporting today), while `/calendar` already renders a rose pulsing "Today!" pill for the same case — the strip simply lacked the zero-day branch. Mirrored the calendar's zero-day case verbatim (rose pill, "Today!"); the `≤7`/`>7` branches keep their abbreviated "In Nd" form.
**Why:** "In 0d" reads as broken copy on the landing page; the canonical rendering already existed on /calendar, so consistency demanded the same pill. Template change is a one-branch copy fix (verified strictly better via styled before/after screenshots), not a redesign.
**Alternatives considered:** Changing the copy to "Today" without the pill styling was considered but rejected — matching /calendar keeps one visual language for the countdown across pages. Normalizing in the service (e.g. a `pill_text` field) was considered but rejected — both pages render the same underlying `days_until`; the divergence was purely template-level.
**Tests:** 1 new route test with stubbed `EarningsEvent`s (`days_until=0` → "Today!" present and "In 0d" absent; `days_until=5` → "In 5d" retained). Suite at 400 green. Live: 5/5 routes 200, zero "In 0d" on home, styled strip screenshots compared.
**Follow-ups (not this batch):** The audit was otherwise clean — marquee day-changes are live on all 10 tickers, calendar/strip agree, pin/unpin round-trips. PEG-path sector calibration + live-10Y-yield wiring still await the user's word.

---

## 2026-10-08 — Batch 35: mislabeled Q4 stub (fp="Q1") doubled BNY revenue on the bank composite

**What:** Fresh-ticker hunt round 5 seeded BNY (custodian bank, SIC 6022), KMI (pipeline), LIN (industrial gases) — all clean (8 quarters, consistent labels). It surfaced one defect.
**fix** (`data/xbrl.py` `_merge_standalone_with_q4`): BNY's 2024 10-K tags its 92-day Q4 standalone stubs fp="Q1" — a filer data-entry error (verified in raw SEC companyfacts JSON). The round-13 guard only relabeled stubs tagged fp="FY" (ABBV), so BNY's stub kept fp="Q1" and failed to supersede the annual−9M derived Q4. On the bank-revenue path (`NoninterestIncome` + `InterestIncomeExpenseNet` summed by period end) both copies were summed: Q4 2024 revenue stored as $9.694B — exactly 2× the filed $4.847B — and the merged composite item inherited the stub's "Q1" label, so the live page showed "Q1 FY2024". The guard is now `pm.fp != "Q4"` (was `== "FY"`): a 70–100-day fact is quarterly by duration, and when a derived Q4 exists for the same end (annual + 9M facts present for that fiscal year) the fact is economically the Q4 stub whatever fp the filer typed. The filer's own stub value remains authoritative; only the label is corrected and the derived duplicate dropped.
**Why:** A 2× revenue error on a rendered company page is the highest-severity class this loop hunts — it feeds growth rates, the valuation model, and the AI briefing. The pre-existing docstring already named this exact doubling hazard for the FY case; BNY proved the mislabeling comes in other fp flavors.
**Alternatives considered:** Relabeling purely by end-date == fiscal year-end (without requiring a derivable Q4) was considered but rejected — without the annual/9M anchor we can't be certain a quarterly fact ending on FY-end is the Q4 stub rather than a genuine stub period. Keeping the FY-only guard and adding a Q1 special case was considered but rejected — the general rule covers all mislabel flavors with one condition.
**Blast radius:** DB-wide scan for fp="Q1" rows ending in December found only BNY (AAPL/DIS/V December-Q1 rows are legitimate September-FY filers). BNY re-seeded post-fix: Q4 FY2024 $4.847B, all 8 labels sequence-consistent.
**Tests:** 2 new (`test_mislabeled_q4_stub_relabeled_from_q1` — generic path; `test_mislabeled_q4_stub_not_doubled_on_bank_composite` — BNY's exact shape through the 6022 composite: 4_847_000_000, fp Q4). Both fail on the pre-fix guard, pass after. Suite at 402 green.
**Live:** 6/6 on :8123 — `/company/{BNY,BNY/detail,KMI,LIN}` 200, `/company/NLY` 404 via the honest unsupported-filer path, `/` 200. Detail page renders "Q4 FY2024" (7×) with zero "Q1 FY2024".
**Follow-ups (not this batch):** NLY (mortgage REIT, SIC 6798) is genuinely outside revenue coverage — its top line is net interest income (`InterestIncomeExpenseNet`, 305 quarterly facts) and the bank composite only serves SIC 6000–6299. Mapping mREIT revenue is new filer-class coverage, not a defect fix. PEG-path sector calibration + live-10Y-yield wiring still await the user's word.

---

## 2026-10-08 — Batch 36: mREIT revenue coverage (SIC 6798) + non-operating-earnings valuation guard

**What:** Closed the batch-35 follow-up — NLY (mortgage REIT) was 404ing on the honest unsupported-filer path because no revenue concept covered it. Two fixes shipped.
**fix** (`data/xbrl.py`): new `_mreit_quarterly_revenue()` — mortgage REITs (SIC 6798) file no quarterly `Revenues` and no `NoninterestIncome`; their top line is net interest income (NLY: 85 quarterly `InterestIncomeExpenseNet` facts, newest 2026-06-30; AGNC: 77). The composite runs the same tag-selection, standalone-quarter extraction, and Q4-from-annual derivation as a regular income metric, with `NetInterestIncome` as the fallback tag. Dispatch in `quarterly_income_metric` is now `_finance_total_revenue` → bank composite (6000–6299) → mREIT composite (6798) → generic chain. Precedence is the safety mechanism: equity REITs sharing SIC 6798 (SPG/O/AMT all file current quarterly `Revenues`) take the finance preference exactly as before, and a 6798 filer with no NII facts returns [] and falls to the generic chain unchanged.
**fix** (`services/valuation.py`): seeding NLY exposed a fabricated **Strong Buy +734%** ($18.27 → $152.37) on the PEG path. Root cause: mREITs book unrealized portfolio gains/losses through net income, so NLY's TTM net income ($2.95B) is 186% of its TTM net interest income ($1.58B) — a PEG growth multiple on that EPS values mark-to-market noise, not operating earnings. New guard at the top of `compute_valuation` (applies to PEG and sales paths): TTM net margin > 100% returns Watch/unavailable with honest copy ("TTM net income is 186% of TTM revenue — earnings exceed the top line, so they are dominated by non-operating items…"). This mirrors the batch-26 non-positive-margin guard — both directions of margin absurdity mean no multiple applies.
**Why:** Batch 35 explicitly logged mREIT mapping as the next coverage item, and shipping NLY with a known-false +734% target would have repeated the exact fabrication class batches 26/27 retired. A margin above 100% is impossible for operating earnings, so the guard is principled, not a special case.
**Alternatives considered:** Leaving the +734% as "documented heuristic territory" per the batch-25/26 PEG-path precedent was considered but rejected — those were aggressive-but-defensible growth multiples; a multiple on earnings that exceed revenue is not defensible. Extending the batch-25 Strong-Sell divergence thesis to the Strong-Buy direction was considered but rejected — the divergence note reconciles two honest signals; here the valuation signal itself was fabricated, so the fix belongs in the model.
**Blast radius:** DB-wide scan: NLY is the only one of 78 tickers with TTM net margin > 100%. All five 6798 tickers verified: NLY/AGNC take the new path (AGNC auto-seeded on first visit; Q2'26 $305.0M matches the filed fact), SPG/O/AMT take `_finance_total_revenue` unchanged. NLY's Q3 2024 NII ($13.4M) verified against raw SEC JSON — a real bad quarter, not an artifact. FCF stays suppressed for finance SICs (NLY FCF None, correct).
**Tests:** 5 new in `tests/data/test_xbrl.py` (mREIT composite values, `Revenues` precedence for equity REITs, generic-chain fallback without NII facts, Q4 derivation via annual−9M, `_is_mreit_sic` boundaries) + 3 new in `tests/services/test_valuation.py` (PEG-path guard, sales-path guard, strictly->100% boundary). Suite at 410 green. `git diff --check` clean.
**Live:** 6/6 on :8123 after restart — `/company/{NLY,NLY/detail,NLY/tearsheet,AGNC,AMT,SPG}` all 200; NLY overview renders Watch with the honest copy and zero "Strong Buy"; detail labels sequence-consistent (FY2024 Q3 … FY2026 Q2).
**Follow-ups (not this batch):** PEG-path sector calibration + live-10Y-yield wiring still await the user's word.

---

## 2026-10-09 — Batch 37: EDGAR cache TTL + processed-filing marker (auto-refresh hardening)

**What:** Freshness audit of all 78 tracked tickers vs live EDGAR found 6 with filed-but-unstored quarters (V, KO, NEE, PYPL, F, DUK — all Q2 2026). The missing data is an SEC-side companyfacts ingest gap (verified against the live uncached API; the filings' XBRL exists), not an app defect — but the audit exposed two app defects that would have made the gap permanent.
**fix** (`data/edgar.py`): the EDGAR disk cache never expired. `fetch_json`/`fetch_text` returned the cached file forever once written, so the batch-31 auto-refresh was silently broken two ways: the trigger (`submissions()`) could go blind to new filings, and a triggered pull (`companyfacts()`) re-extracted the same stale snapshot — a refresh could never land a new quarter. Added `cache_ttl_seconds` (default 6h, matching `_FILINGS_CHECK_TTL`) enforced via file mtime, plus `fresh=True` kwargs on `submissions()`/`companyfacts()`.
**fix** (`services/financials.py`): `fetch_and_persist` set `xbrl_filings_processed` to the latest quarterly *filing date* even when that filing's quarter wasn't extracted (companyfacts lag). DUK's marker sat at 2026-08-04 — its Q2 10-Q's filing date — while stored data ended 2026-03-31, so `latest > marker` could never fire again: the quarter would be skipped until Q3's filing. New `_processed_filing_marker()` advances the marker only to filings whose `reportDate` quarter is present in the extracted rows (missing `reportDate` keeps the old behavior since the live feed always provides one); deliberate pulls now read live EDGAR (`fresh=True`). Remediation: DUK's persisted marker reset 2026-08-04 → 2026-05-05.
**Why:** The user's standing expectation is that new earnings land in the app on their own. Both defects violated it silently — no error, no log, just permanently stale quarters. The fix makes the refresh self-healing: unprocessed filings retry every 6h until SEC ingests them (verified live: V's marker went NULL → 2026-04-29, the latest *processed* filing, not the unprocessed 2026-07-29).
**Alternatives considered:** Deleting the disk cache entirely was considered but rejected — the TTL preserves SEC-friendly request reduction for the frequent lightweight checks while deliberate pulls go live. A new DB column recording the processed quarter end was considered but rejected — the `reportDate`-based computation needs no schema change and degrades gracefully (missing reportDate = old behavior). Forcing `fresh=True` only on companyfacts (not submissions) was considered but rejected — the trigger's decision and the pull's data must come from the same live snapshot.
**Blast radius:** All 78 tickers re-audited post-fix: only the 6 SEC-gapped tickers lag, and all 6 now retry correctly. Markers for correct tickers (AAPL 2026-07-31, NVDA 2026-08-26, APLD 2026-10-07, …) unchanged by the new computation. Amendment behavior unchanged (10-Q/A shares its quarter's reportDate, so it still advances the marker exactly as before).
**Tests:** 4 new in `tests/data/test_edgar.py` (fresh-cache hit without HTTP, stale-cache refetch after TTL, `fresh=True` bypass for both endpoints) + 3 new in `tests/services/test_financials.py` (DUK-shape marker regression, refire loop end-to-end, pull uses `fresh=True`). Suite at 417 green. `git diff --check` clean.
**Live:** 6/6 on :8123 after restart — `/company/V` and `/company/DUK` 200 with refresh firing correctly, `/company/{AAPL,AAPL/detail,NLY/tearsheet,AAPL/vs/MSFT}` 200 with markers unchanged.
**Follow-ups (not this batch):** The 6 lagging quarters will land automatically once SEC ingests them (retry loop verified). PEG-path sector calibration + live-10Y-yield wiring still await the user's word.

---

## 2026-10-09 — Batch 38: BDC revenue coverage (fresh-ticker hunt round 6)

**What:** Seeded 6 new tickers live from SEC — UAL, TGT, KMB, NUE, HAL all clean (8 quarters, sequence-consistent FY labels, A=L+E holds, sane values). ARCC (BDC) previously 404'd on the honest unsupported-filer path (batch 33 follow-up).
**fix** (`data/xbrl.py`): new `_bdc_quarterly_revenue()` — BDCs report no SIC and file no `Revenues`; their top line is `GrossInvestmentIncomeOperating` (ARCC: $768M framed standalone Q2'26). Tag-detected rather than SIC-dispatched: the fallback fires only when the generic revenue chain raises KeyError, so `Revenues`/`SalesRevenueNet` filers always win; returns [] without the tag so the unsupported-filer path survives. Precedence is the safety mechanism — a filer with standard revenue facts never sees this code. ARCC now seeds 8 quarters with Q2'26 gross investment income $768.0M and consistent labels.
**Why:** Batch 33 logged ARCC's 404 as the next coverage item (same lineage as batch 35→36's NLY). The unsupported-filer page is honest, but a $20B filer class deserves the same treatment mREITs got. The generic-chain-failure gate makes the blast radius zero for all existing companies by construction.
**Alternatives considered:** SIC-dispatch like the mREIT composite was considered but rejected — ARCC's SEC submissions carry a blank SIC, so a SIC gate could never fire. Reusing `_finance_total_revenue` was considered but rejected — BDCs have no `Revenues` facts at all; the tag is the actual filed top line.
**Blast radius:** Zero — the composite runs only after the generic chain fails, so no existing company can resolve differently. ARCC's valuation card audited: declining-earnings 8× floor math is honest with batch-27 copy (no fabrication; AI divergence thesis reconciles the Watch). Round-6 extremes (NUE +88.7%, HAL −70.3%, KMB −51.9%) all name their guardrails with Medium confidence — heuristic territory, untouched. HAL's $18M Q3'25 net income verified against raw SEC facts (true standalone quarter; $694M is the 9-month YTD context) — the app picked the correct fact.
**Tests:** 5 new in `tests/data/test_xbrl.py` (ARCC-shape composite values, `Revenues` precedence, `SalesRevenueNet` precedence, KeyError preserved without the tag, Q4-from-annual derivation). Suite at 422 green. `git diff --check` clean.
**Live:** 6/6 on :8123 — `/company/{ARCC,UAL,TGT,KMB,NUE,HAL}` all 200; ARCC overview renders Q2 FY2026 $768.00M revenue, honest valuation card. No template change (backend-only).
**Follow-ups (not this batch):** PEG-path sector calibration + live-10Y-yield wiring still await the user's word.

---

## 2026-10-09 — Batch 39: yearly-mode partial-year disclosure (detail/compare time-slicer audit)

**What:** Integration audit of the detail page (yearly mode, range slicing, HTMX `/detail/data` partial, per-period CSV + history ZIP downloads) and the compare page (YoY/QoQ/5y presets, yearly mode, compare CSV/ZIP) against live data.
**fix:** Yearly mode silently presented partial fiscal years as full-year figures. The stored-history depth (8 quarters) means 81 of 84 DB companies have fewer than 4 quarters in their latest fiscal year, and the hero KPI cards summed whatever was stored under a bare "FY2026" label — ARCC's "FY2026 Revenue $1.53B" was a 2-quarter sum, and the compare page rendered FY2026 $364.36B vs FY2025 $416.16B with a −12.4% decline badge while FY2026 holds only 3 quarters. New `PeriodData.quarters_count` (1 for quarterly periods, N for yearly) drives the disclosure: the detail heading gains an amber "— partial year, N of 4 quarters reported" note, compare column headers gain a "partial — N of 4 quarters" sub-note, and both CSV renderers gain a `# Period note` comment row. The pre-existing YoY suppression for incomplete year pairs is unchanged (badges still render "—"); this completes the honesty story the guard started. Also corrected the stale `PeriodData.period_end` docstring.
**Why:** The loop's standing honesty bar (batch-27 PEG copy, batch-33 sales-path copy): a number presented as an annual figure that covers 2–3 quarters is a fabrication by omission. The disclosure is additive copy, not a behavior change — all stored values and aggregates are untouched.
**Alternatives considered:** Refusing to render partial years (hiding data) was considered but rejected — the disclosure preserves the user's access to the newest quarters while making the incompleteness explicit, matching the loop's disclose-don't-hide posture. Putting the note only in the detail h2 (not compare/CSV) was considered but rejected — the compare page's −12.4% badge was the most misleading surface of the three.
**Blast radius:** Additive only — `quarters_count` defaults to 0, and the note conditions require yearly mode + 1–3 quarters, so no existing full-year or quarterly view changes. CSV consumers see one new comment row (`#`-prefixed, ignored by parsers) only for partial years.
**Tests:** 3 new in `tests/services/test_financials.py` (yearly count 2/4, quarterly count 1, CSV note rows present/absent) + 5 new in `tests/test_company_routes.py` (detail note renders for partial / absent for full year, compare header note per-side, compare-CSV note rows); 1 existing MagicMock fixture updated to provide the new int field. Suite at 430 green. `git diff --check` clean.
**Live:** 10/10 on :8123 after restart — ARCC/AAPL yearly detail (notes for 2Q/3Q years, none for AAPL FY2025), ARCC/AAPL yearly compare (per-side notes), per-period + compare CSV/ZIP downloads all 200 with note rows. Styled before/after screenshots compared per screenshot gate (amber notes visible; layout otherwise identical). Backend sums unchanged; template changes are targeted honesty fixes, not a redesign (Gemini still owns UI).
**Follow-ups (not this batch):** PEG-path sector calibration + live-10Y-yield wiring still await the user's word. The 6 SEC-gapped Q2-2026 quarters (V/KO/NEE/PYPL/F/DUK) still haven't been ingested by SEC companyfacts — the batch-37 retry loop is live and behaving (markers correct, no permanent skips).

---

## 2026-10-09 — Batch 40: honest floor copy when the 8× P/E floor binds on positive growth (fresh-ticker hunt round 7)

**What:** Seeded 6 new tickers live from SEC (MPLX, DHI, AWK, CB, DLR, RTX) — all 8 quarters, sequence-consistent FY labels, A=L+E holds, values sane; no new uncovered filer class. The hunt surfaced one copy defect.
**fix** (`services/valuation.py`): batch 27 fixed the false "A PEG of 1.5 on that growth implies a fair P/E of 8.0×" for flat/declining earnings, but the same false implication still rendered for *positive* growth in the 2%–5.33% band, where 1.5×growth < 8 and the `_MIN_PE` floor (not the PEG math) drives the multiple. AWK (+4.0% growth) rendered "implies a fair P/E of 8.0×" when the PEG math implies 6.0× — a Strong Sell −64.2% on a false premise. New branch: when `raw_pe < _MIN_PE` and no rate guardrail binds, the primary bullet now reads "A PEG of 1.5 on 4.0% growth implies a fair P/E of 6.0× — below the 8× floor for low-growth earnings, so valued at the floor instead"; the guardrail note below still names the binding floor; target math untouched (fair_pe already reflected the floor). When the rate guardrail also binds, the old line stands (guardrail + rate notes disclose both drivers). DB-wide scan: 3 of 89 valued tickers affected (AWK 4.0%, DPZ 2.4%, WMT 3.7%) — all Strong Sell cards with the false claim, now honest.
**Why:** The loop's standing honesty bar (batches 27, 33, 39): a multiple presented as a PEG implication that the PEG math doesn't produce is a fabrication by omission, even when a separate footnote names the floor — the footnote doesn't retract the false implication. Copy-only fix, zero behavior change.
**Alternatives considered:** Deleting the `_MIN_PE` floor (letting 1.5×4% = 6× P/E print) was considered but rejected — the floor is deliberate batch-12 methodology; this batch fixes only the description, not the methodology. Extending the fix to the 40× cap band (e.g. CB's "implies 37.0×" on 36.3% growth) was considered but rejected — the cap cases already have explicit guardrail + rate notes in the bullets disclosing both drivers, matching the batch-26 precedent; sector-aware PEG calibration remains a methodology redesign awaiting the user's word, not a defect fix.
**Blast radius:** Copy-only. Only the PEG-path else-branch line changes, and only when the floor binds with positive growth (3 tickers: AWK/DPZ/WMT). Targets, signals, confidence, and all other bands unchanged (verified: 5.5% keeps the PEG line at High, batch-27 declining/flat variants byte-identical, rate-bind keeps the old line).
**Tests:** 3 new in `tests/services/test_valuation.py` (floor-band honest copy + unchanged target + guardrail note intact; just-above-floor 5.5% keeps original copy at High confidence; floor+rate-bind keeps old copy with both notes). Suite at 433 green. `git diff --check` clean.
**Live:** 7/7 on :8123 after restart — `/company/{AWK,DPZ,WMT}` render the new floor copy with zero occurrences of the false claim; `/company/{CB,RTX,AAPL,NLY}` + DLR detail 200 with copy unchanged. Round-7 audit notes: DLR's Q2'25 $1.032B net income spike verified as the true filed standalone quarter (SEC facts: 2025-04-01→2025-06-30, $1,032,156,000 — a genuine one-time gain, not a derivation defect); its PEG target sits on documented heuristic territory per batch-25/26 precedent (guardrail notes disclose the 40× caps; Medium). MPLX (no XBRL EPS facts, like ET) renders the batch-33 sales-path copy honestly. DHI's non-calendar FY (Sep year-end) labels verified sequence-consistent.
**Follow-ups (not this batch):** PEG-path sector calibration + live-10Y-yield wiring still await the user's word. The 6 SEC-gapped Q2-2026 quarters (V/KO/NEE/PYPL/F/DUK) still haven't been ingested by SEC companyfacts (verified live 2026-10-09: V's newest revenue fact still filed 2026-04-29) — the batch-37 retry loop is live and behaving (markers correct, no permanent skips).

---

## 2026-10-09 — Batch 41: honest AI-briefing revenue copy for flat and declining quarters

**What:** Re-audited the AI fundamental-analysis briefings (`generate_ai_analysis`, Gemini's PRD §4.4 feature, batch-25) for the 12 newest DB tickers (ARCC, UAL, TGT, KMB, NUE, HAL, MPLX, DHI, AWK, CB, DLR, RTX) against live data. The rest of the briefings (divergence notes, Unknown-tier copy, sector-aware tails) behaved; the hunt surfaced one defect class in the revenue thesis.
**fix** (`services/ai_analysis.py`): the revenue thesis had a single template — `f"Top-line revenue grew {rev_yoy:+.1f}% YoY ... {_revenue_thesis_tail(...)}"` — with no branch for flat or declining revenue. DHI (true YoY +0.015%) rendered "grew +0.0% YoY in Q3 FY2026, reflecting healthy demand across commercial segments" (a fabricated demand narrative from noise, and the wrong register for a homebuilder), and COIN rendered "grew −18.5% YoY in Q2 FY2026, reflecting balance-sheet growth and fee-income momentum" (a decline narrated as growth with "momentum" attached). New `_FLAT_REVENUE_PCT = 2.0` band (mirrors the batch-27 valuation copy's 0–2% "essentially flat" band): |rev| < 2% → "Top-line revenue was essentially flat YoY ... with no demand signal either way this quarter" (no tail — neither "healthy demand" nor "momentum" is warranted from noise); positive → original line unchanged; decline → "Top-line revenue declined X.X% YoY ... " plus new `_revenue_decline_tail()` (financials: "a softer quarter for balance-sheet growth and fee income"; else "signaling soft demand in its end markets this quarter" — the batch-25 register principle applied symmetrically). Exactly-0 keeps the existing no-thesis behavior (batch-25 missing-YoY test untouched).
**Why:** The loop's standing honesty bar (batches 25, 27, 33, 39, 40): a verb ("grew") the number contradicts and a demand narrative the data doesn't support are fabrications by omission. Copy-only fix, zero behavior change.
**Alternatives considered:** Extending the honest-copy treatment to mild-but-positive bands (e.g. +2.5% "healthy demand") was considered but rejected — +2.5% is genuine growth and the claim is a mild stretch, not a contradiction; the batch redraws the line only where verb and number disagree. Touching the growth ladder's 55 flat-growth rung was rejected — the rung is deliberate methodology, and the score is honest as a score; only the narrative was false.
**Blast radius:** Copy-only. 4 of 90 DB tickers change briefing text (DHI/UNH/KMB flat, COIN decline); scores, signals, targets, confidence all untouched (verified: DHI Watch 61 etc. byte-identical except the thesis line; growth-thesis regression test asserts AAPL-style lines are unchanged).
**Tests:** 4 new in `tests/services/test_ai_analysis.py` (flat narrative on the DHI +0.015% shape + growth-score untouched; 1.99%→flat / 2.0%→growth band boundary; decline copy for both sector tails; growth regression byte-identical). Suite at 437 green. `git diff --check` clean.
**Live:** 5/5 on :8123 after restart — `/company/{DHI,UNH,KMB,COIN,AAPL}` all 200: the three flat quarters render "essentially flat ... no demand signal either way", COIN renders "declined 18.5% ... a softer quarter for balance-sheet growth and fee income", AAPL's "+16.4% ... healthy demand" unchanged, zero occurrences of the old false claims anywhere.
**Follow-ups (not this batch):** DLR's trailing-margin thesis ("21.7% demonstrates operational leverage and pricing discipline") is arguably generic for a REIT whose TTM includes the verified Q2'25 $1.032B one-time gain — the metric is a true TTM number and the batch-36 >100% guard doesn't trip, so it's noted but not changed; a one-off-aware margin narrative would be methodology redesign. PEG-path sector calibration + live-10Y-yield wiring still await the user's word. The 6 SEC-gapped Q2-2026 quarters (V/KO/NEE/PYPL/F/DUK) — the batch-37 retry loop is live and behaving.

## 2026-10-09 — Batch 42: honest AI-briefing EPS thesis (fresh-ticker hunt round 8)

**What:** Audited `generate_ai_analysis` briefings for 15 round-8 tickers (BNY, AGNC, NLY, APLD, APP, CART, DUOL, HOOD, LOPE, RDDT, SHOO, SOFI, RIVN, SHOP, ARCC) against live data. All 8 stored quarters present, balance identities hold, values sane — no XBRL defects this round. The hunt surfaced one defect class in the briefing narrative itself: there was no earnings thesis at all.

**fix** (`services/ai_analysis.py`): DUOL's "Invest 92" briefing narrated +18.3% revenue growth and a 35.9% margin while diluted EPS fell 27.5% YoY with zero disclosure; ARCC's "operational leverage and pricing discipline" line sat next to a 53.8% EPS decline. New sign-aware EPS thesis mirroring the batch-41 revenue structure: |eps| < 2% → "essentially flat YoY ... no earnings-momentum signal either way this quarter"; positive → "grew +X% YoY"; decline → "declined X% YoY". Two honesty guards the raw pct needs (it divides by |prior|, so a smaller loss or a tiny base both render as positive "growth"): (1) loss-making quarters — positive renders "improved ... though the latest quarter remained loss-making on a per-share basis" (a shrinking loss is not growth) and declines name it ("declined 1071.4% ... with the latest quarter loss-making on a per-share basis", the APLD shape); (2) |eps| >= 200% base-effect artifacts qualify as "rose +3433.3% ... amplified by a small prior-year base" (NLY, MU +1368%, INTC −222%) instead of a bare "grew" that reads as hypergrowth. Missing EPS YoY (None) emits no line — unknown, not flat (batch-25 principle). The 200% qualifier threshold was calibrated from a DB-wide magnitude scan (13 of 90 tickers at |eps_yoy| ≥ 200%: ABBV, AGNC, AMZN, APLD, F, GOOGL, INTC, MU, NET, NKE, NLY, PLTR); ABBV/AMZN/GOOGL/NKE/PLTR/F in the +200–425% band with positive current EPS now get the base-effect qualifier too, which is the honest read.

**Why:** The loop's standing honesty bar (batches 25, 27, 33, 39, 40, 41): a briefing that narrates only the positives while the earnings line collapses is a fabrication by omission. Copy-only fix, zero behavior change.

**Alternatives considered:** Extending the margin thesis with a YoY counterweight (ARCC's "pricing discipline" next to a 53.8% NI decline still jars slightly) was rejected — the margin line is a trailing-level statement and the new EPS line now discloses the decline beside it; two fixes for one observation is scope creep. Using net-income YoY instead of EPS was rejected — EPS is the per-share investor metric and `_pct_change` gives it clean sign semantics.

**Blast radius:** Copy-only. 13 of 90 DB tickers change briefing text (the ≥200% band) plus every ticker with non-trivial EPS YoY now gains one honest thesis line; scores, signals, targets, confidence all untouched (verified: DUOL Invest 92, ARCC Watch 62 byte-identical except the new thesis line).

## 2026-10-10 — Batch 43: earnings-calendar audit + fresh-ticker hunt round 9 (no defects)

**What:** (1) Audited Gemini's `/calendar` (PRD §4.5) against live Yahoo data: 90 tracked tickers render events; sampled DPZ/GS/JPM/BNY/NFLX/APLD — every date, EPS consensus, and revenue estimate matches Yahoo's current feed, countdown pills correct (six tickers on 2026-10-13, BNY 10-15, NFLX 10-20), and PEP's 2026-10-08 (reported 2 days ago) correctly renders the "Reported" pill. Two scares resolved as Yahoo-side volatility, not app defects: APLD flipped 2026-10-08 → 2027-01-06 between fetches minutes apart (earnings just reported; Yahoo updating), and GS's EPS average read 13.80 then 13.18 on consecutive direct fetches while the app rendered 13.18 — the app renders whatever Yahoo currently returns. (2) Seeded AIG, D, CSX, AMGN, MDLZ, GEV live from SEC: 8 quarters each, FY labels sequence-consistent (Q3 FY2024 → Q2 FY2026), A=L+E holds on all, values sane; D/MDLZ only reach Q1 FY2026 (their Q2 10-Qs filed 2026-07-31/07-28 aren't ingested by companyfacts yet — markers correctly at 2026-05-01/2026-04-28, retry loop engaged). (3) Valuation extremes on the new tickers audited and left as documented heuristic territory: CSX Strong Sell −69.1% (High; 1.5×5.7%=8.5× math honest, FCF-yield cross-check supports), D Strong Buy +103.1% (Medium; 40× cap and rate-guardrail notes both disclosed), MDLZ Strong Sell −73.2% (batch-27 declining-earnings 8× floor copy), AIG Strong Sell −43.2%, AMGN Strong Buy +43.7%, GEV Buy +28.7%. (4) Batches 41/42 briefing honesty verified on the new data: AIG renders "essentially flat ... no demand signal either way" (−0.1% revenue) beside "EPS declined 10.1%", D discloses its 10.4% EPS decline next to the Strong Buy, and AIG's Strong Sell-vs-Watch divergence note fires.

**Why:** The loop's alternation calls for a fresh-ticker hunt this batch; the calendar had not been audited against live data since batch 16's perf fix (batch 34 only spot-checked home/calendar agreement). The SEC-gapped Q2-2026 re-check (V/KO/NEE/PYPL/F/DUK still un-ingested) confirms the batch-37 retry machinery keeps working: KO's page view this run fired the refresh end-to-end (marker NULL → 2026-04-30, the latest *processed* filing; 8 quarters unchanged).

**Alternatives considered:** None — no defect found, so no fix. The D +103.1% and CSX −69.1% extremes were audited against the batch-25/26 precedent (PEG-path extremes with disclosed guardrails and Medium/High confidence are methodology, not fabrication) and left untouched.

**Blast radius:** Zero code changes. DB gained 48 quarter-rows (6 tickers × 8, local-only, untracked). 0 new tests; suite 444 green.

**Audit lesson (own miss, caught by verification):** two false alarms this batch, both from sloppy probes, not app defects — (1) querying only the legacy `us-gaap:Revenues` tag made V/AAPL companyfacts look stale to 2020/2018; both filers migrated to `RevenueFromContractWithCustomerExcludingAssessedTax` (current through 2026-04-29/2026-07-31). Always check the tag family the extraction chain actually uses. (2) `fetch_and_persist` returns rows oldest-first; printing `rows[0]` as "latest" briefly suggested 2024 data — the stored rows were current.

---

## 2026-10-10 — Batch 44: thin-ticker backfill, PSKY→SKYD rename, middle-gap refresh fix

**What:** A DB-wide quarter-count audit (all 96 tickers) found 5 with fewer than 8 stored quarters and NULL `xbrl_filings_processed` markers: XOM (2), LMT (4), PYPL (4), ZTS (4), PSKY (6). Live re-extraction showed SEC already held 8 quarters for LMT/ZTS/PYPL — the app just never backfilled them. Three defects fixed:

1. **Ticker change (PSKY → SKYD).** SEC's company_tickers.json now maps CIK 0002041610 to "Skydance Corp", NYSE: SKYD — Paramount Skydance re-tickered. The DB row still said PSKY and 5 peer-map references (DIS/NFLX curated + SIC 781/784/799 fallbacks) pointed at the dead ticker, rendering peer chips that link to a 404. Renamed the DB row, all peer references, and the 3 peer tests; a 96-ticker CIK-vs-SEC sweep confirmed PSKY was the only mismatch. `/company/PSKY` now 404s cleanly ("Unknown ticker"); DIS peer chips render SKYD.
2. **Seeding default (`services/financials.py`).** `fetch_and_persist` defaulted to `periods=4` while every route seeds with 8 — ad-hoc seeds that omitted the argument silently left thin tickers with NULL markers. Default is now 8 (all routes/tests pass it explicitly, so zero behavior change elsewhere) with a signature regression test.
3. **Middle-gap refresh blindness (`services/financials.py`).** The batch-37 marker tracks only the latest *processed* filing, so a 10-Q/10-K *older* than the marker whose XBRL facts SEC never ingested could never refire: SKYD's merger-era Q3'25 10-Q (filed 2025-11-10, report 2025-09-30) sat behind marker 2026-08-04 permanently. New `_has_unprocessed_quarter_in_window()` runs when the marker path says fresh: it scans the already-fetched submissions feed for a quarterly filing no newer than the marker whose reportDate falls inside the stored window but has no stored quarter. Window-bounded (filings older than the extraction window are legitimately unstored — no false positives, covered by test), amendments share their quarter's reportDate so they can't false-positive, and a filing newer than the marker stays the `latest > marker` path's responsibility. On a gap the refresh refires (6h TTL, never-raises) and rejoins the batch-37 retry loop until SEC ingests the facts.

**Why:** The loop's standing data-integrity bar: a dead ticker in the peer map is a broken link on DIS/NFLX pages, half-window tickers degrade every YoY comparison and the valuation card, and a refresh that can never fire is a silent permanent data hole. The XOM case (2 quarters) was verified SEC-side — companyfacts for "ExxonMobil Holdings Corp" genuinely holds 4 revenue facts — and documented as such rather than "fixed".

**Alternatives considered:** Capping the marker at the oldest unprocessed filing was rejected — for the newest-quarter gap (PYPL's un-ingested Q2'26 10-Q) that would set marker = latest filing and *break* the batch-37 retry loop. A per-filing processed-set column was rejected as schema churn for one middle quarter; the feed-scan check reuses data already in hand.

**Blast radius:** Marker semantics unchanged for the common path (latest processed filing); the new check only *adds* refires, gated by the existing 6h TTL. 8 new tests (1 default-periods, 1 renamed-ticker peer guard, 4 helper unit, 2 end-to-end fire/no-fire). Suite at 452 green. `git diff --check` clean.

**Live:** 7/7 on :8123 after restart — `/company/{SKYD,DIS,ZTS,PYPL,XOM,LMT}` 200, `/company/PSKY` → clean 404. SKYD's page view refired the refresh end-to-end (rows re-upserted, still 6 quarters — SEC hasn't ingested the Q3'25 10-Q; retry loop armed). LMT/ZTS/PYPL backfilled to 8 quarters with markers set; PYPL's marker correctly held at 2026-05-05 (Q2'26 10-Q still un-ingested). DIS renders SKYD peer chips ×3, PSKY ×0.

**Follow-ups (not this batch):** PEG-path sector calibration + live-10Y-yield wiring still await the user's word. SEC-gapped quarters (V/KO/NEE/PYPL/F/DUK Q2-2026 + SKYD Q3-2025) remain on the 6h retry loop.

## 2026-10-10 — Batch 45: fresh-ticker hunt round 10 + cap-side valuation-copy honesty (1 defect class)

**What:** (1) Seeded CVX, NOW, SCHW, TMO, DE, PANW live from SEC (round 10): 8 quarters each, FY labels sequence-consistent including off-cycle fiscal years (DE FY2024Q4→FY2026Q3, PANW FY2025Q1→FY2026Q4, TMO Saturday period-ends), A=L+E on all 48 quarters, values sane. Valuation extremes on the new tickers audited: CVX Strong Buy +82.2% (Medium; PEG math 51.8× → 40× cap → 37.0× rate cap, all notes disclosed), SCHW Strong Buy +110.5% (Medium; growth clamped at 40%, same chain), NOW/TMO/DE Strong Sell −68% (High/High/Medium; straight PEG math 12.6×/11.3×/8× floor, honest), PANW Strong Sell −99.0% (Medium; 8× floor on ~$0.52 TTM EPS, disclosed per batch-26 precedent). Batches 41/42 briefing honesty holds on the new data (PANW's loss-making EPS-decline disclosure, CVX's base-effect qualifier). (2) **fix** cap-side mirror of the batch-40 floor honesty fix in `services/valuation.py`: the PEG-path primary bullet attributed the guarded multiple to the PEG math whenever the 40× cap or rate guardrail bound — 41 of 102 DB companies rendered the false claim (DB-wide `get_valuation` scan). The bullet now states the raw PEG-implied multiple and names the binding driver(s); the rate-only band (24.7%–26.67% growth at 4.5% 10Y) and the batch-40-punted floor+rate chain (needs >20.8% 10Y, unreachable at the default benchmark) are honest too. Same class on the sales path: V's "51.7% × 21.6× implies a fair P/S of 10.0×" (identity gives 11.2×) now names the 10× cap. (3) Two seed anomalies verified against raw companyfacts as genuine filed data, not extraction defects: CVX's Q2'26 $70.06B revenue / $12.07B NI jump (Hess acquisition closed Jul 2025; the unframed $118.66B/$14.28B facts are 6-month YTD duplicates — the framed quarter facts are correctly selected) and PANW's Q3/Q4 FY2026 net losses (unframed $589M/$0.79 are 9-month YTD; framed -$177M/-$0.22 are the true quarter facts). CART/COST audit-scan flags re-verified as rounding-level (5.95%→8.925→8.9×), not defects.

**Why:** The loop's alternation calls for a fresh-ticker hunt; the round-10 seeds surfaced the cap-side copy defect when CVX's bullet was read against the batch-40 principle ("never claim 'a PEG of 1.5 on that growth implies' a multiple the PEG math doesn't produce"). Batch 40 explicitly punted the rate-bound case ("the old copy stands"); this batch completes the honesty class — a false mathematical implication in the primary bullet is a defect even when the guardrail/rate notes disclose the drivers, because the headline claim is what most readers read. The CVX/SCHW Strong Buy extremes were deliberately left as documented heuristic territory (batch-25/26 precedent) — only the copy changed.

**Alternatives considered:** Leaving the cap side as batch 40 did ("notes disclose both drivers") was rejected — the same reasoning would have left the AWK floor falsehood in place, and 41 affected companies is too broad for a headline falsehood. Restricting the fix to cap-only (leaving the rate-only band) was rejected — the band's "implies 37.0×" is equally false against PEG math implying e.g. 38.5×.

**Blast radius:** Copy-only: target math, signals, confidence tiers, scores untouched. `test_floor_plus_rate_cap_keeps_old_copy` rewritten to assert the honest floor+rate chain (deliberate supersession of the batch-40 punt); 7 new tests (cap-only, cap+rate, growth-clamped, rate-only band, unclamped regression, sales-cap, sales no-cap regression). Suite at 459 green (452 + 7). `git diff --check` clean.

**Live:** 8/8 on :8123 after restart — `/company/{CVX,NOW,SCHW,TMO,DE,PANW}` 200 + `/company/{CVX,SCHW,V,COF}` re-rendered with the new honest bullets and byte-identical targets. DB-wide re-scan: 0 remaining false-implication bullets across 102 tickers.

**Follow-ups (not this batch):** PEG-path sector calibration + live-10Y-yield wiring still await the user's word. SEC-gapped quarters (V/KO/NEE/PYPL/F/DUK Q2-2026 + SKYD Q3-2025) remain on the 6h retry loop. PANW's two loss-making quarters are genuine filed data — no retry needed; its briefing now discloses them per batch-42.

---

## 2026-10-10 — Batch 46: AI-briefing margin-thesis register fix (1 defect class)

**What:** Audited `generate_ai_analysis` briefings for the 17 newest-seed tickers (rounds 9–10: CVX, NOW, SCHW, TMO, DE, PANW, SKYD, LMT, ZTS, PYPL, XOM, AIG, D, CSX, AMGN, MDLZ, GEV) — no fabrication patterns (grew -X%, flat-demand narratives, missing disclosures) remain; the batch-41/42/45 honesty fixes hold across all 17. Found the batch-41 register fix's margin-side twin: the net-margin thesis template hard-coded industrial-register copy ("Trailing net margin of X.X% demonstrates operational leverage and pricing discipline") for every sector. A bank's margin is net interest spreads + fee income; an insurer's is underwriting — "pricing discipline" is a fabrication of the wrong business model (same class as batch-41's "soft demand in end markets"). DB-wide `get_ai_analysis` scan: all 7 financial-sector tickers rendered it (JPM 32.6%, BNY 29.5%, MET 4.6%, SCHW 38.8%, AIG 11.1%, NLY 186.4%, COIN). New `_margin_thesis_tail()` in `services/ai_analysis.py` uses the same sector keys as the batch-41 revenue tails ("bank", "securit", "insurance", "financ") → "demonstrating spread discipline and fee-income efficiency."; every other sector byte-identical. Note the audit's own miss-catching: the pre-written scan script initially flagged only AIG (its FIN-REGISTER regex covered only the newly-seeded set), and a second manual sweep over the older financials (JPM/BNY/MET/COIN) found the class was DB-wide — the script ran before the fix's blast radius was fully known, so the DECISIONS entry records the true scope.

**Why:** One-branch register fix continues the honesty program (batches 41/42/45): a thesis line that misdescribes how a company makes money is a defect even when the number is right. NLY's 186.4% margin is a computed TTM value (mark-to-market swings on a levered mortgage REIT), not an extraction error — the fix deliberately does not qualify extreme margins beyond register-correctness; adding a "volatile mark-to-market" qualifier would be editorializing beyond the data. Kept the financial phrasing generic ("spread discipline and fee-income efficiency") rather than bank-vs-insurer splits — the register question is operational-vs-financial, not sub-sector.

**Alternatives considered:** Splitting bank ("net interest margin discipline") vs insurer ("underwriting discipline") vs broker ("fee-income efficiency") was rejected — three registers for the same one-line close is over-engineering, and the generic financial line is register-correct for all three. Mirroring the revenue fix exactly (separate tail helper, same key set) keeps the audit surface minimal and grep-able.

**Blast radius:** Copy-only: theses text for 7 of 102 tickers; scores (growth/profit/solvency/valuation ladders), composite, signals, confidence, targets, all other theses, risks, and executive summary untouched. 2 new tests (all four financial sector spellings; industrial byte-identical regression). Suite at 461 green (459 + 2). `git diff --check` clean.

**Live:** Restarted :8123 for the new code (the earlier `pkill -f` pattern matched my own shell — server restarted cleanly after; noted so a future run doesn't repeat the self-kill). `/company/JPM` renders the new line; `/company/AAPL` keeps the old line — 2/2 green. No template change (backend-only), so no screenshot per the gate rules.

**Follow-ups (not this batch):** PEG-path sector calibration + live-10Y-yield wiring still await the user's word. SEC-gapped quarters (V/KO/NEE/PYPL/F/DUK Q2-2026 + SKYD Q3-2025) remain on the 6h retry loop.

---
