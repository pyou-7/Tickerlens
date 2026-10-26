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

## 2026-10-20 — Batch 101: separator-less endnote markers + non-2.02 earnings 8-K fallback

**What:** Two disclosure-pipeline defect classes from the partial-cohort forensic round 2 (10 → 5). (1) `_LEDE_FOOTNOTE_RE` no longer requires `[\s.]` after the marker — EOG's supplement packet letters endnotes "(B)Production volumes ..." with no separator, and the old tail let 976 chars of footnote boilerplate get STORED as Q1 FY2026 highlights; the stored junk was cleared. (2) New `_extract_other_8ks` + `_match_8k_non202_fallback` in `services/ir_download.py`: earnings 8-Ks filed without Item 2.02 (Citi/MTD 9.01-only, Colgate 8.01+9.01, GE Vernova 2.01+9.01) now match when no 2.02 candidate exists — same 7–60d / ≤filing-date / nearest guards, plus a required `_pick_release_doc` hit (no lone-exhibit fallback) whose filename must reference the period (`_exhibit_matches_period`: filing-date YYYYMMDD, quarter token, or len≥2 ticker).

**Why:** The forensic classified every missing quarter in the 10-company partial cohort instead of re-sweeping blindly. Class 1 was actively harmful (junk stored as signal); class 2 was pure loss (real releases existed on EDGAR, unreachable). The `_exhibit_matches_period` guard is load-bearing, not belt-and-braces: the naive fallback matched Citi's Trust Preferred Securities 8-K (`d240560dex991.htm`) — ex99-shaped, in-window, nearer the 10-Q — and would have stored offering boilerplate as Q2 2024 highlights; the live Citi probe caught it pre-commit.

**Alternatives considered:** Extending `_extract_er_8ks` to include non-2.02 8-Ks directly (rejected — the 2.02 gate is the primary path's semantic signal; mixing the lists would let a 9.01-only 8-K outrank a real 2.02 match on the nearest-to-filing tiebreak); items-based exclusion of deal/governance 8-Ks (rejected — GE Vernova's real earnings 8-K carries 2.01, and AFRM's real one carries 5.02, so item exclusions are fragile; the exhibit-filename guard is the direct signal); clearing STZ's table-row highlights in the same pass (rejected — real headline + real figures, a separate quality wart, not junk); building the 6-K foreign-filer path for SHOP now (deferred — SHOP's Q3 2024 10-Q sits beyond EDGAR's recent-1000 window with no buckets to page, so 6-K matching needs its own design; stays a carried follow-up).

**Blast radius:** `data/filings.py` (one regex); `services/ir_download.py` (two new functions + triple return from `extract_all` + fallback branch that only fires when `_match_8k` returns None — previously-unmatched quarters only). 9 new tests (2 footnote incl. EOG-shaped packet → None; 7 fallback incl. 2.02-priority, window guards, Trust-Preferred rejection). Suite 865 green (856 + 9). `git diff --check` clean.

**Live:** Partial backfill sweep: C/CL/MTD/GEV each +1 → 8/8 with real releases (spot-checked headlines/figures); EOG Q1 junk cleared (honestly 0/8). LIN re-probed: Q3 2024 ex-99.1 is 14 JPG pages with no text layer — same image-only class as AFRM, structurally unextractable, stays 7/8. Honest residuals: AFRM (image-only letter), CCI (no Q4-2024 earnings 8-K filed at all), SHOP (10-Q unreachable), SKYD (pre-merger quarters). Server was restarted at batch start (was down); routes verified via the backfill's own fetches + existing live checks.

**Follow-ups (not this batch):** HAL business-vs-financial highlights priority; SHOP 6-K discovery (foreign filers); GEV footnote-definition headline wart ("1 Defined as ..." picked as headline); STZ metric-table-as-highlights wart; pending-filing cohort at 17 (batch-95 verified).

---

**What:** `DetailContext` gains `pending_filing_note` (wired from `Company.pending_filing_note` in `get_detail`), and `partials/detail_data.html` renders the same amber honesty note as the overview, below the period label and above the hero KPI cards — for tickers whose latest 10-Q/10-K is filed but EDGAR's companyfacts feed hasn't ingested its figures yet.
**Why:** Batch 53 put the note on the Overview page, but the Detail/Time Slicer page is where the user stares at the quarters and the YoY selectors — a stale latest quarter there had the same unexplained-silence defect. The partial is server-rendered on the initial page load too, so one block covers both the full detail page and every HTMX `/detail/data` swap; no route changes were needed.
**Alternatives considered:** Passing the note as a separate template variable instead of a context field (rejected — the partial's contract is `ctx`, and the overview already carries it on its context, so parity keeps both templates reading `*.pending_filing_note`); gating the note on the selected period being the latest (rejected — the note describes the app's latest-data state, which is true regardless of which period the slicer shows, and the overview behaves the same way); extending to compare/tearsheet in the same batch (deferred — the batch-54 follow-up named the detail page specifically; one batch, one item).
**Blast radius:** `financials.py` (one dataclass field + one constructor kwarg), `partials/detail_data.html` (one conditional block). No extraction, valuation, briefing, peers, calendar, or query-path changes. 6 new tests (2 get_detail plumbing incl. None-by-default, 2 partial render/omit, 2 route-level render/omit). Suite at 554 green (548 + 6). `git diff --check` clean.
**Live:** Server restarted via the launcher script (kill by explicit PID — the standing lesson). 7/7 routes 200 (V/CB/AAPL detail, V detail/data, CB overview, /calendar, /api/search?q=visa). Styled screenshots via `scripts/screenshot.py` (local Tailwind build; plotly CDN blank in the sandbox is the known artifact): V shows "Q3 FY2026 results (10-Q filed Jul 29, 2026) aren't in EDGAR's data feed yet — showing Q2 FY2026…", CB shows its Q2 FY2026 variant, AAPL (no-note control) unchanged with no amber block. Screenshot gate passed.
**Follow-ups (not this batch):** DBA/nickname alias map for descriptions (CART->Instacart, SHOO->Steve Madden); pending-filing note on the compare and tearsheet pages.

## 2026-10-11 — Batch 54: Wikipedia corporate-suffix fallback search (1 defect class)

**What:** `_best_title` now retries with the corporate suffix stripped from the query when the full-legal-name search yields nothing relevant; the fallback accepts only an article *named* the stripped name (order-insensitive word-set equality, suffix-stripped both sides, never-relevant exclusions kept). New `_strip_corp_suffix` (trailing /MA/ state tags + one suffix token), `_word_set` (keeps short words like "3M"/"D. R."), `_never_relevant` (exclusions extracted from `_title_relevant`, shared).
**Why:** `_search_titles` queries "{legal name} company", and Wikipedia's ranking degrades on suffixed names — "Atlassian Corp company" returned '8x8' and '2026 Formula One World Championship' while "Atlassian company" hits the article — leaving 10 of 132 companies description-less. The strict acceptance rule exists because the naive fallback misattributes: the stripped "Applied Digital" search surfaces "Applied Digital Data Systems", a 1969 terminal maker, which word-set equality declines (batch-47 IBM/Commodore class). CART ("Maplebear Inc." -> article "Instacart") and SHOO ("STEVEN MADDEN" -> "Steve Madden") are deliberately left unmatched — DBA/nickname aliasing needs a curated map, not fuzzy matching.
**Alternatives considered:** Merging primary+fallback candidates into one pool and re-running the batch-47 selection (rejected — more candidates raise misattribution risk; the strict rule on a separate fallback path is safer); accepting name-contained fallback titles (rejected — "Applied Digital Data Systems" *is* name-contained and wrong); also retrying with the bare ticker as query (rejected — adds nothing under the strict equality rule and risks word-tickers matching unrelated articles).
**Blast radius:** `data/wikipedia.py` only (new helpers + ~10-line fallback in `_best_title`; `_title_relevant` behavior unchanged — exclusions extracted verbatim). Fallback fires only when the primary returns nothing relevant, so the 122 described companies are untouched by construction. 8 new tests. Suite at 548 green. Live: 5 descriptions backfilled (TEAM, AMT, DHI, MMM, WFC), verified correct; server restarted.

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

---

## 2026-10-10 — Batch 47: fresh-ticker hunt round 11 + Wikipedia description rescue (2 defect classes)

**What:** (1) Seeded AVGO, MA, QCOM, INTU, ISRG, AMAT live from SEC (round 11): 8 quarters each, A=L+E on all 48 quarters, FY labels sequence-consistent including off-cycle fiscal years (AVGO FY2024Q4→FY2026Q3, QCOM FY2024Q4→FY2026Q3, INTU FY2025Q1→FY2026Q4, AMAT FY2024Q4→FY2026Q3). Two anomalies verified against raw companyfacts as genuine filed data, not extraction defects (batch-45 audit lesson applied: check the tag family the chain actually uses): AVGO FY2026Q3 $29.59B revenue / $13.09B NI are framed-quarter facts from the 2026-09-10 10-Q (the unframed $71.09B/$29.75B are 9M YTD — correctly not selected), and QCOM's FY2025Q4 -$3.12B NI is the correct FY−9M derivation ($5.541B FY − $8.658B 9M) with FY2026Q2 +$7.37B confirmed as a framed quarter fact. Valuation-copy honesty (batches 40/45: cap/rate disclosures present on AVGO/AMAT) and briefing registers (batches 41/42/46) hold on all six — no fabrication patterns. (2) **fix** Wikipedia description rescue in `data/wikipedia.py`: the 50-word `_MIN_WORDS` floor was silently discarding real company summaries — Broadcom's live summary measured 48 words via httpx (63 via curl; egress-cache variance), Visa 32, GE 20 — leaving 59 of 108 companies description-less. New design: floor 15 as a stub-rejector (not a quality bar); disambiguation pages rejected by API `type` (not length); `_search_title` generalized to `_search_titles(limit=5)`; `_best_title` selection = Wikipedia rank first, with exact-name match (squashed alphanumeric comparison, stop words retained so "Domino's Pizza Group plc" ≠ "DOMINOS PIZZA INC"), predecessor override (strictly higher overlap + name-contained + no-longer: "Lockheed Martin" over "Lockheed Corporation"), and name-contained lower-hit fallback; `_title_relevant` rewritten with ticker-acronym rule, hyphen/apostrophe normalization, first-word agreement, lead-word fallback, and never-relevant exclusions for lawsuit articles (" v. "), "List of " articles, and parenthetical pages except "(company)". `enrich_company` now passes the ticker into `get_description`. Backfill: 50 companies rescued; 5 wrong descriptions repaired — LMT's predecessor-company page → Lockheed Martin, IBM's "Commodore International" → IBM, LOPE's university page → Grand Canyon Education, SKYD's stale pre-merger text, PG's person page → P&G. The 8 remaining Nones are honest rejections (WFC/AMT/APLD/AGNC/DHI wrong search hits; CART/SHOO/MPLX need alias/fuzzy knowledge the conservative check deliberately lacks). (3) **fix** `services/peers.py`: ISRG (SIC 3842) rendered no Sector Peers section — added curated medtech map (MDT/SYK/BSX/EW/ZBH, all verified against live SEC company_tickers.json per batch-28 precedent) and a "384" SIC-prefix fallback.

**Why:** The loop's alternation calls for a fresh-ticker hunt; the round-11 seeds exposed the description gap (all six seeded with NULL descriptions, and the DB-wide count showed 59/108). A missing description is a content hole on every overview page; a wrong one (IBM-as-Commodore, LMT-as-predecessor) is worse than none — the selection rules were hardened until a full 108-company dry-run showed zero regressions vs stored descriptions.

**Alternatives considered:** Simply lowering the floor to 15 without the selection hardening was rejected after the dry run caught it admitting PG's person page and promoting subsidiaries/cases/museums above company pages. Pure max-overlap selection was rejected for the same reason (DPZ's UK franchisee, MSFT's antitrust case, WFC's museum). Trusting Wikipedia rank alone was rejected by the LMT predecessor case. Expanding the relevance check to fuzzy matching (SHOO "Steven" vs "Steve", CART's Maplebear→Instacart alias) was rejected — wrong descriptions are worse than missing ones, and those 8 stay honestly empty.

**Blast radius:** `wikipedia.py` rewritten (127-line diff); `financials.py` one-line ticker threading; `peers.py` two map additions. Descriptions are page-view-refreshed with overwrite-None semantics (pre-existing design); the dry run confirmed no stored good description flips to a worse page under the new selection. 23 new tests (21 wikipedia, 2 peers). Suite at 484 green (461 + 23). `git diff --check` clean.

**Live:** Restarted :8123 for the new code (note: `pkill -f serve_tickerlens.py` matched the invoking shell again — batch-46's warning stands; kill by PID). `/company/{ISRG,AVGO,LMT,IBM,PG}` 200 with correct descriptions and ISRG's new peer chips (MDT/SYK/BSX/EW/ZBH); all six round-11 overviews + AVGO detail/compare/vs 200. Post-view DB check: all repaired descriptions intact (no transient-search wipes). No template change (backend-only), so no screenshot per the gate rules.

**Follow-ups (not this batch):** PEG-path sector calibration + live-10Y-yield wiring still await the user's word. SEC-gapped quarters (V/KO/NEE/PYPL/F/DUK Q2-2026 + SKYD Q3-2025) remain on the 6h retry loop. 8 description-less companies (WFC, AMT, CART, SHOO, APLD, AGNC, MPLX, DHI) stay None by design.

---

## 2026-10-10 — Batch 48: freshness-retry futility audit (1 defect class)

**What:** DB-wide audit of the batch-37/44 freshness machinery (108 tickers, cached submissions). Batch-37's 6 stale tickers (V, KO, NEE, PYPL, F, DUK) all reached 8 quarters — the 6h retry loop worked as designed. XOM verified as genuine SEC-side thinness: SEC's company_tickers.json re-mapped XOM to new CIK 0002115436 ("ExxonMobil Holdings Corp", a holding-company reorganization); its companyfacts holds only 2 framed revenue quarters (2025-06-30, 2026-06-30), correctly selected over unframed 6M-YTD duplicates — 2 stored quarters is correct, not a defect. Two tickers tripped the batch-44 middle-gap check: SKYD and APLD. **fix** the middle-gap retry could not distinguish "SEC hasn't ingested the filing's facts yet" (retry-worthy) from "facts ingested but the quarter is structurally unextractable" (futile). SKYD's merger-era Q3'25 10-Q (filed 2025-11-10) facts WERE ingested — as a 53-day stub period (2025-08-08→2025-09-30) that the 70–100-day comparability window deliberately rejects — and its Q4'25 can never derive as FY−9M through the merger (no clean 240–290d 9M fact exists; the merger split it into stubs). The check therefore refired a full `fetch_and_persist` every 6h forever, never resolving. New: after any refire, `_acknowledge_unextractable_quarters` scans still-missing in-window reportDates against the fresh companyfacts and persists acknowledged ones in the new nullable `Company.xbrl_skipped_quarters` (JSON array; added via the `ensure_schema()` startup migration, with a migration test). `_missing_in_window_quarters` (extracted from `_has_unprocessed_quarter_in_window`, same semantics + skip list) backs both the check and the acknowledgment scan.

**Why:** A never-resolving 6h busy-loop burns 2 live EDGAR pulls + a full XBRL re-extraction + upserts per trigger, forever, for a quarter that can never appear. Acknowledgment is the only convergent behavior; the alternative (leaving the loop) also masked the real product question, which is whether the gap is a data hole (fixable) or a structural stub (correct to omit).

**Alternatives considered:** The first implementation acknowledged on *any* duration fact at the reportDate — live testing caught it wrongly acknowledging APLD's FY2026 10-K gap (153 non-revenue duration facts ingested, annual revenue fact still missing: genuine partial-ingestion lag, verified against live companyfacts). The predicate was rescoped to the revenue chain (`_revenue_duration_facts`, using `CONCEPTS[Metric.REVENUE].tags`) with structural shapes only: 10-Q stub (sub-70d revenue fact, no 70–100d fact) and 10-K-with-stubbed-9M (340–380d annual fact + only sub-240d revenue facts in the prior quarter's window, located via `_prior_quarter_report_date`). APLD's gap (no revenue facts at 2026-05-31) keeps retrying; a 10-K whose annual is ingested but 9M merely lags also keeps retrying (safe default). A finance-SIC filer with a stub quarter keeps retrying too — the predicate covers only the generic revenue chain; extending to bank/mREIT/BDC composites was deferred as unobserved.

**Blast radius:** `services/financials.py` only (helpers + one model column + two call sites in `refresh_financials_if_stale`); `models/company.py` one nullable column. No extraction, valuation, briefing, or template changes. 14 new tests: `_missing_in_window_quarters` (gap listing, amendment dedupe, skip honoring), `_read_skipped_quarters` tolerance, revenue-chain scoping, `_is_structural_gap` (stub / annual+stub-9M / revenue-missing / proper-9M), `_prior_quarter_report_date`, end-to-end ack-then-quiet, retry-preserved for un-ingested AND partially-ingested shapes, `ensure_schema` column migration. Suite at 498 green (484 + 14). `git diff --check` clean.

**Live:** Restarted :8123 for the new code. `/company/SKYD` refired once, persisted `["2025-09-30", "2025-12-31"]`, and the middle-gap check now returns False for SKYD (second hit 0.3s vs 12.7s refire). `/company/APLD` still trips the check and its skip column stays NULL after the refined predicate (an earlier coarse version had wrongly acknowledged it; cleared manually). 8/8 routes 200 (`/`, SKYD, APLD, AAPL, AAPL/detail, XOM, /calendar, /api/search). No template change (backend-only), so no screenshot per the gate rules. Ops note: `ps aux | grep … | xargs kill` SIGTERMed the invoking shell this run (same class of self-kill as the `pkill -f` pattern — kill by explicit PID, or start fresh when the server is already down).

**Follow-ups (not this batch):** PEG-path sector calibration + live-10Y-yield wiring still await the user's word. APLD's FY2026 10-K annual revenue fact still not ingested by SEC — the retry loop will pick it up automatically. 8 description-less companies (WFC, AMT, CART, SHOO, APLD, AGNC, MPLX, DHI) stay None by design.

## 2026-10-11 — Batch 49: fresh-ticker hunt round 12 (no defects)

**What:** Seeded AXP, BLK, MCD, SBUX, MDT, GILD live from SEC (round 12): 8 quarters each, FY labels sequence-consistent including off-cycle fiscal years (SBUX Sep-FY Sunday period-ends FY2024Q4→FY2026Q3; MDT Apr-FY Friday period-ends FY2025Q2→FY2027Q1 — the FY2027Q1 label renders correctly in AI briefings). Deep audit per the hunt pattern: (1) **BLK balance-sheet identity gap** — A=L+E fails by $5.4–6.7B (3.2–3.8%) on the 4 newest quarters. Verified against the live Q2 2026 10-Q (filed 2026-08-06): the balance sheet carries a "Temporary equity" section between liabilities and equity — Redeemable NCI in consolidated sponsored investment products ($3.872B) + Redeemable NCI in BlackRock Saturn Subco ($2.828B) = $6.700B, bridging the 2026-06-30 gap exactly. Searched us-gaap, dei, and extension taxonomies in companyfacts: no XBRL tag exists for these lines, so the gap is structurally uncloseable from facts. The stored total_equity ($57.840B) IS the filer's own "Total equity" line — the app is faithful to the filing. Verdict: genuine filed-data structure, no code fix (batch-45 precedent); folding untagged mezzanine into equity would deviate from the filer's presented lines. Same class confirmed for APLD's 18.7% gap (Series E redeemable preferred + TopCo third-party interests in Temporary equity, verified in its 2026-08-31 10-Q). DB-wide identity scan: 9 tickers with >1% gaps (APLD, BLK, CART, DLR, O, PLUG, UBER, UNH, ZTS), all plausibly mezzanine filers; none are extraction defects. (2) **GILD Q2 FY2026 -$10.496B NI / -$8.45 EPS** — the framed quarter fact (2026-04-01→2026-06-30) from the 2026-08-06 10-Q; the unframed -$8.475B is 6M YTD and was correctly not selected. Genuine filed loss, no fix. (3) **AXP bank-composite revenue $19.637B** — verified against the live 10-Q as "Total revenues net of interest expense" exactly (NoninterestIncome $14.988B + Net interest income $4.649B); the "finance revenue preference unavailable → generic chain" log line seen during seeding belonged to BLK's chain selection, not AXP's. (4) **BLK generic-chain revenue $7.084B** — verified as the 10-Q's "Total revenue" line exactly. (5) Valuation-copy honesty (batches 40/45) holds on all six: AXP Buy +25.7% (High; 1.5×15.7%=23.5× fair P/E vs 18.7× current, honest), BLK Strong Sell −69.1% (Medium; 1.0% growth → 8× floor disclosed), MCD Strong Sell −56.9% (High; 8.2× vs 19.1×, FCF cross-check tempers), SBUX Strong Sell −84.7% (Medium; −25.1% TTM decline → 8× floor disclosed, FCF supports), MDT Sell −16.3% (High; 18.2× vs 21.7×), GILD Watch/Low with no fabricated target on negative TTM earnings ("a target price would be a guess, not a model"). (6) Briefing registers (batches 41/42/46) hold: AXP/BLK render the batch-46 financial margin register ("spread discipline and fee-income efficiency"); SBUX renders the flat-revenue honesty line (−1.4%); GILD discloses the loss-making quarter ("EPS declined 641.7% YoY ... loss-making on a per-share basis"); Strong Sell-vs-Watch divergence notes fire on BLK/MCD/SBUX; MDT's Sell-vs-Watch correctly stays silent (the batch-42 rule fires on Strong Sell only — verified in code). (7) Descriptions: the six seeded description-less because ad-hoc `fetch_and_persist` bypasses the route's first-visit `enrich_company` path (not a defect — enrich only runs on the auto-seed path); a manual `enrich_company` run resolved all six via the batch-47 fetcher with zero misattributions, verified rendering in overview HTML.

**Why:** The loop's alternation calls for a fresh-ticker hunt; rounds 9–11 each surfaced real defect classes, and round 12's financial/off-cycle mix (bank composite, asset-manager revenue, Apr/Sep fiscal years) was chosen to stress exactly the chains that needed verification. The BLK mezzanine finding extends the batch-13 NEE identity precedent into a DB-wide structural pattern: temporary equity is a third balance-sheet section that XBRL companyfacts doesn't tag, so A=L+E is uncloseable for these filers and the app's faithful-line rendering is the correct behavior.

**Alternatives considered:** Deriving total_equity as `LiabilitiesAndStockholdersEquity − Liabilities` (the filer's own check total minus liabilities) would close the identity but misattributes redeemable NCI — which sits outside permanent equity by the filer's own presentation — to "Total Equity", deviating from the filing's lines. Rejected: faithfulness to filed lines beats a cosmetically closed identity the XBRL facts can't support. Adding redeemable-NCI tags to the equity chain was rejected — the tags don't exist in companyfacts (verified across all taxonomies).

**Blast radius:** Zero code changes. DB gained 48 quarter-rows + 6 descriptions (6 tickers × 8, local-only, untracked). 0 new tests; suite 498 green. `git diff --check` clean (docs only).

**Live:** 11/11 on :8123 — `/company/{AXP,BLK,MCD,SBUX,MDT,GILD}` 200, GILD/MDT/SBUX detail/compare 200, `/api/search?q=medtronic` 200, `/calendar` 200; AXP/MDT descriptions confirmed in overview HTML. No template change (backend-only), so no screenshot per the gate rules.

**Follow-ups (not this batch):** PEG-path sector calibration + live-10Y-yield wiring still await the user's word. APLD's FY2026 10-K annual revenue fact still not ingested by SEC — the retry loop keeps it armed. The 9 mezzanine-gap tickers (APLD/BLK/CART/DLR/O/PLUG/UBER/UNH/ZTS) are documented as structural, not defects — no retry or extraction work applies.

---

## 2026-10-11 — Batch 50: disclosure-pipeline audit on rounds 11–12 (4 defect classes fixed)

**What:** Integration audit of the 8-K disclosure pipeline (press-release highlights / management guidance / transcript excerpts — Gemini's headline feature from 2026-10-05, last audited in batch 18) against the 12 newest-seed tickers (rounds 11–12: AVGO, MA, QCOM, INTU, ISRG, AMAT, AXP, BLK, MCD, SBUX, MDT, GILD). Four defect classes found, all fixed, all verified against the live SEC filings:

(1) **fix** `services/ir_download.py::_pick_release_doc` — four exhibit-naming conventions the picker rejected, leaving MA, SBUX, AMD, and AMGN with zero disclosures on their stored quarters. Mastercard's `ma06302026-exx991xearnings.htm` (doubled-x "exx99" separator): tier-0 regex `ex(hibit)?[^a-z0-9]?99` requires a non-alphanumeric (or nothing) between "ex" and "99", so the alphanumeric "x" broke it → now `ex(?:hibit)?x?[^a-z0-9]?99`. Starbucks' `sbux-06282026xearningsrele.htm` and Amgen's `amgn-20260630earningsrelea.htm` (truncated "release"): tier-1 `(press|earnings)[-_]?release` → `(press|earnings)[-_ ]?rele[a-z]*\b`. AMD's `q22026991.htm` (quarter + bare "99.1" suffix, no "ex"): new tier-0 alternative `991$` on the stem. Verified the picker now matches the right exhibit for all four tickers (and still prefers the narrative release over AMD's `amdq22026earningsslidesf.htm` earnings-deck).

(2) **fix** `data/filings.py::_GUIDANCE_HEADING_RE` — the guidance extractor missed real guidance sections. AVGO's "Fourth Quarter Fiscal Year 2026 Business Outlook" (real outlook: ~$34.8B Q4 revenue guidance) — the quarter-prefixed branch allowed only one middle word and no "business" tail. INTU's "Full Year Fiscal 2027 Guidance" / "First Quarter Fiscal 2027 Guidance" / "Forward-Looking Guidance" — "full" wasn't a prefix word, "Year Fiscal 2027" middles weren't allowed, and there was no "forward-looking" prefix alternative. New: prefix list gains `full`; up to five intervening words (`quarter|fiscal|year|\d{4}`); optional `business` tail; new `forward[- ]looking` prefix branch. Verified extraction against the live AVGO/INTU exhibits (1754 / 2006 chars of real guidance).

(3) **fix** `services/financials.py::get_detail` backfill trigger — `if any(r.press_release_highlights is None ...)` meant rows with highlights filled but guidance NULL (AVGO, INTU) never re-ran the backfill, so the fixed extractor could never reach them. Trigger now covers all three disclosure fields, matching `_enrich_press_release_highlights`' own `missing` semantics. Found because AVGO's detail visit in this batch's backfill sweep left guidance NULL despite the batch-18 lazy-backfill design.

(4) **fix** `data/filings.py::extract_press_release_highlights` — JNJ's ex-99 (`a2026q2exhibit991.htm`) puts media/investor contact blocks *before* the headline and has no "Highlights" section: the old code picked "Media contact:" as the headline and let "Investor contact:" terminate the lede fallback, yielding None for the whole release. Deere's ex-99 (`de-20260820xex99d1.htm`) added two more variants of the same class: zero-width-space (`\u200b`) padding lines that filled the 6-line lede cap with invisible text, and a "(Furnished herewith)" SEC parenthetical that became the headline. New `_CONTACT_LINE_RE` skips contact lines (media/press/investor contact *or inquiries* labels + email addresses) in both the headline scan and the lede fallback; `_ADMIN_LINE_RE` gains the `(furnished herewith)` parenthetical; `_html_to_text` strips `\u200b`/`\ufeff` at the source so invisible junk never counts as content lines. Verified against the live JNJ Q2 (now 1787 chars, correct headline) and DE Q3 (now extracts with the correct "Deere Reports Third Quarter Net Income of $1.379 Billion" headline) exhibits.

(5) **guidance-heading variant, same class as (2)** — JNJ's "Full-year 2026 guidance:" (hyphenated "Full-year") needed `[\s\-]+` separators in the quarter-prefixed branch; verified live (721 chars of real guidance extracted). Deere's outlook sections ("Company Outlook & Summary", "Industry Outlook for Fiscal 2026", "Deere Segment Outlook for Fiscal 2026") use company-specific titles the generalized regex deliberately does not chase — the key number ("Net income guidance improved to $4.75B to $5.00B") is already captured in the highlights bullets, so DE's guidance=None stays an honest extraction, not a defect.

Verified correct-Nones (no defect): AXP/BLK guidance (banks publish no guidance sections — batch-18 precedent; AXP's headline "raises FY 2026 revenue growth guidance to 10%" is a headline statement, not a section), MA guidance (Mastercard's release has no guidance/outlook content at all — checked the live exhibit), AXP/BLK transcripts (releases contain no executive quotes — only boilerplate/table quote fragments; the attribution probe found zero said/commented/noted/stated/added lines), MCD guidance (McDonald's gives no forward guidance — correct None).

**Why:** The loop's alternation called for an integration audit; the disclosure pipeline is the highest-traffic never-fully-audited surface (it renders on every detail page), and rounds 11–12's diverse filers (bank, asset manager, card network, coffee, medtech, chip) stress exactly the naming/format variants batch-18's five-ticker audit didn't cover. Each defect was verified against the live filing before fixing (batch-45 lesson: check the real document, not the assumption).

**Alternatives considered:** For (1), adding literal "exx99"/"earningsrele" substrings was rejected in favor of the generalized patterns — other filers will have their own truncations, and the generalized tiers still rank below exact ex99 matches. For (3), persisting a "guidance genuinely absent" marker to stop re-attempts was rejected — the pre-existing design already re-attempts missing highlights on every visit (SEC responses are disk-cached), so widening the trigger keeps the semantics consistent rather than inventing a new state. For (4), extending `_BOILERPLATE_RE` was rejected — boilerplate is an end-of-release terminator; contact lines need skipping, not breaking, and only in the highlights path.

**Blast radius:** `filings.py` (guidance regex, contact regex + two skip sites, `\u200b`/`\ufeff` stripping, one admin-line pattern), `ir_download.py` (picker tiers 0/1 + docstring), `financials.py` (one trigger condition). No valuation, briefing, peers, calendar, or template changes. 8 new tests (4 picker conventions; 1 parametric guidance-headings test over the 5 wild headings; 1 backfill-trigger regression; 2 highlights tests for contact-block and zwsp/furnished variants). The backfill-trigger and contact-block tests were each verified to FAIL against the pre-fix code (temporary revert) before the fix was restored. Suite at 506 green (498 + 8). `git diff --check` clean.

**Live:** Server restarted three times for the new code (kill-by-PID per the standing lesson — the `pkill -f`/`xargs kill` self-kill class is now documented in AGENTS.md). Backfill sweep 1: 89/89 gap-ticker detail pages 200, 0 failures (latest-quarter gaps 89 → 80 of 114). Backfill sweep 2 (remaining 80, post-trigger/contact fixes): 80/80, 0 failures. Targeted re-visits for the later fixes: JNJ 0/0/1 → 1/1/1, DE 0/0/1 → 1/0/1, AMD 0/0/0 → 1/0/1, AMGN → 1/1/1. Spot-verified content: SBUX highlights ("Starbucks Reports Q3 Fiscal Year 2026 Results"), MA 1/0/1 (guidance correctly absent — verified against the live release), DE highlights ("Deere Reports Third Quarter Net Income of $1.379 Billion"). Final: 77 of 114 tickers still show some latest-quarter gap — the residue is dominated by banks/insurers with genuinely no guidance sections and releases with no executive quotes (verified classes), plus COIN (release embedded in the primary 8-K document, which the pipeline documents as unhandled). No template change (backend-only), so no screenshot per the gate rules.

**Follow-ups (not this batch):** PEG-path sector calibration + live-10Y-yield wiring still await the user's word. APLD's FY2026 10-K annual revenue fact still not ingested by SEC — the retry loop keeps it armed. The 9 mezzanine-gap tickers (batch 49) remain documented as structural, not defects.

---

## 2026-10-11 — Batch 51: fresh-ticker hunt round 13 + stock-split rescale defects (3 defect classes)

**What:** Seeded TXN, HON, UPS, PLD, BKNG, ACN live from SEC (round 13): 8 quarters each, A=L+E on all 48 quarters, FY labels sequence-consistent (ACN Aug-FY FY2024Q4→FY2026Q3). Deep audit per the hunt pattern surfaced a stock-split defect cluster:

(1) **fix** `xbrl._SPLIT_RATIOS` gains 8 and 25. BKNG's 25-for-1 split (effective 2026-04) went undetected — 25 wasn't a listed ratio — so the framed-fact preference picked restated post-split values for FY2025Q1/Q2 (0.40/1.10, the only quarters with ingested restated frame facts) while FY2024Q3/Q4 and FY2025Q3/Q4 kept pre-split values (74.34/31.96/84.41/44.22): a mixed-basis stored series. Verified as a genuine corporate action via `WeightedAverageNumberOfDilutedSharesOutstanding` (33.09M → 827.0M, exactly 25x). GE's 1-for-8 reverse split (2021-07-30) was the second missing ratio — multi-corroborated in live companyfacts (GE's stored window is all post-2021, unaffected, but the ratio belongs in the list). DB-wide scan of all cached companyfacts for divergent per-share facts at non-listed ratios: BKNG (25x, 6 groups) + GE (8x, 16 groups) the only multi-group hits; PFE/WFC single-group 1.5x divergences stay correctly skipped by the corroboration guard (not added — 1.5x is a routine correction magnitude).

(2) **fix** duration-aware split references in `_split_adjust_facts`. HON's 1-for-2 reverse split (2026-07, verified: shares 646.3M → 323.2M exactly halved) WAS detected, but the `certain` post-split reference map collapsed by end date: the 2026-07-23 10-Q filed both a quarterly (4.90) and a 6M YTD (9.34) fact for end 2025-06-30, the YTD value won the latest-filed tie, and the neighbor check compared quarterly facts against a YTD reference — silently skipping genuinely pre-split quarters (FY2025Q1 stayed 2.22, FY2024Q3/Q4 unscaled). `certain` is now keyed by (start, end) and the basis check only compares like duration classes (quarterly ≤120d vs YTD).

(3) **fix** `_is_pre_split_basis` replaces the absolute-distance neighbor check with log-ratio distance. Two remaining HON quarters defeated the old check: FY2025Q4's loss quarter (−0.18 — the interpolated +11.42 neighborhood had the opposite sign, so rescaling always moved it "farther away") and FY2026Q1 (1.29 — the neighborhood was interpolated across the 17.83 gain-inflated quarter). Ratio-distance compares magnitudes: the rescaled value must land clearly nearer (log(1.2) margin) to some same-class post-split reference than the original. Verified against every existing split test (NFLX 10:1 rescale/skip cases, lone-ratio guard, ordinary-restatement guard, Q4-derivation sanity, two-filing merge) — all still pass unchanged.

Re-seeded BKNG + HON: BKNG EPS now (2.98, 1.28, 0.40, 1.10, 3.39, 1.77, 1.36, 2.53), HON (4.32, 3.92, 4.44, 4.90, 5.72, −0.36, 2.58, 17.83) — implied share counts flat at ~820M / ~320M respectively, fully coherent post-split series. TXN/UPS/ACN clean (all metrics present, identity holds; the seed log's "split detected" lines beside TXN were HON's — stderr/stdout interleave, confirmed TXN has no 2026 divergences). PLD's Q2-2026 10-Q (filed 2026-07-29) has zero ingested facts in companyfacts — SEC-side lag, same class as APLD's FY2026 10-K; the batch-48 6h retry loop stays armed, no extraction defect. Descriptions enriched for all six via `enrich_company` (batch-49 ad-hoc-seed gap; zero misattributions). Valuation-copy honesty (batches 40/45) holds on the fixed data: BKNG Strong Buy $335 discloses the 40% growth / 40× P/E / 37× rate caps at Medium confidence; HON Strong Buy $954 target is arithmetically honest but driven by the gain-inflated TTM quarter — a valuation-*model* limitation (no one-time-item normalization), not a data defect.

**Why:** The loop's alternation called for a fresh-ticker hunt; the split detector (built for the NFLX 10:1 case) had never been exercised against forward splits above 20x, reverse splits at 8x, or a restating filing carrying same-end quarterly+YTD facts — round 13's filer mix hit all three. A mixed-basis EPS series corrupts every downstream consumer (YoY/QoQ trends, TTM sums, PEG targets, AI briefings), so basis consistency is a correctness invariant, not polish.

**Alternatives considered:** Adding only 25 (not 8) was rejected — GE's 1:8 reverse split is real, multi-corroborated, and the same defect class; one token, same guardrails. Fixing the neighbor check by tie-breaking `latest_by_end` toward quarterly durations was rejected — it would leave YTD facts compared against quarterly references (the mirror-image confusion). An implied-share-count disambiguation (NI/EPS per quarter) was considered for the loss-quarter case but rejected as over-engineering: magnitude-ratio distance resolves it with the data already in hand. Normalizing TTM for one-time gains (HON's $954 target) was deferred — model-scope work, needs the user's word alongside the pending PEG calibration.

**Blast radius:** `xbrl.py` only (`_SPLIT_RATIOS`, `_split_adjust_facts` certain-keying, `_neighbor_value` → `_is_pre_split_basis`, `import math`). No extraction, valuation, briefing, peers, calendar, or template changes. 4 new tests (25:1 forward, 8:1 reverse, YTD/quarterly same-end confusion, loss-quarter + outlier-neighborhood). Suite at 510 green (506 + 4). `git diff --check` clean.

**Live:** Server was down at batch start — started fresh via the launcher script (no self-kill incidents). Restarted once more after the fix landed so :8123 serves the new split code (kill by explicit PID per the standing lesson). 11/11 routes 200: 6 overviews, BKNG/HON detail + compare, BKNG-vs-HON. BKNG overview renders TTM EPS $9.05 with cap disclosures intact. No template change (backend-only), so no screenshot per the gate rules.

**Follow-ups (not this batch):** PEG-path sector calibration + live-10Y-yield wiring still await the user's word. PLD's Q2-2026 10-Q facts not yet ingested by SEC — the 6h retry loop keeps it armed (same for APLD's FY2026 10-K). Valuation-model one-time-gain normalization (HON's $954 target on a gain-inflated TTM; PLD-style REIT P/E distortion) is model-scope future work. The 9 mezzanine-gap tickers (batch 49) remain structural, not defects.

---

## 2026-10-11 — Batch 52: fresh-ticker hunt round 14 + sequence-break FY-label repair (1 defect class)

**What:** Seeded CRWD, MMM, C, SO, ABNB, BMY live from SEC (round 14): 8 quarters each, A=L+E on all 48 quarters, descriptions enriched for all six via `enrich_company` (batch-49 ad-hoc-seed gap; zero misattributions). Deep audit per the hunt pattern surfaced one defect class plus one verified correct-None:

(1) **fix** `data/xbrl.py::_repair_sequence_breaks` (new pass wired after `_dedupe_period_labels` in the extraction assembly). CrowdStrike's FY2025 10-K and Q1-FY2026 10-Q tag their periods by the calendar year the fiscal year *began* — the 2025-04-30 quarterly revenue fact in CRWD's own 2025-06-04 10-Q carries fy=2025 (verified in live companyfacts; the filer's earnings releases call it Q1 FY2026) — while later filings' comparative columns use the standard ending-year convention (fy=2026/2027). The 2025-01-31 Q4 row inherited fy=2024 from the annual fact via `_derive_q4_income`. No labels collided, so the batch-45 collision-only arbitration never fired, and the stored series read FY2025Q3 → FY2024Q4 → FY2025Q1 → FY2026Q2: `fy` decreasing across consecutive quarters, impossible for a fiscal calendar. This is the non-colliding twin of the ORCL/Salesforce mislabeled-fy class. Repair: the longest run of rows whose labels are mutual successors is the backbone (ties broken toward the run holding the latest row, whose filing carries the filer's most current convention). Only when the backbone is a strict majority of rows and at least 3 long, every other row's expected label is walked from the nearest backbone row by *calendar* quarter-steps (`round(days/91.3125)`, so a genuine gap resolves to the row's own claim) and the row is relabeled only on a pure year shift — walked fp must match claimed fp, and the target label must be unheld. A missing quarter changes fp, so it can never be "repaired" into a wrong label; a missing year walks back to the claim; near-duplicate ends that would collide keep the first via the unheld-target guard. CRWD re-extracted end-to-end: DB now reads FY2025Q3 → FY2025Q4 → FY2026Q1 → … → FY2027Q2, and the overview renders "Q2 FY2027" with the briefing's +114.3% YoY EPS thesis on the corrected label.

(2) ABNB eps=None on all 8 quarters — verified correct None, no code change. Airbnb's Q2 2026 10-Q (filed 2026-08-06, accession 0001559720-26-000027) prints "Net income per share attributable to Class A and Class B common stockholders: Basic $1.04 …" in the HTML but tags none of the values with any XBRL concept — zero `EarningsPerShare*` facts in us-gaap, dei, ecd, or any extension namespace (ABNB files no extension taxonomy at all). Structurally unextractable, same class as BLK's mezzanine equity (batch 49): the app's None is faithful to the filing. The valuation card degrades honestly via the batch-26 sales path ("No per-share earnings to anchor a P/E multiple — valuing on sales instead (less reliable)"; 20.4% TTM margin × 20.5× fair P/E → 4.2× fair P/S vs 7.5× current, Strong Sell −44.6%); the AI briefing emits no EPS line (unknown, not flat — batch-42 principle) and the Strong Sell-vs-Watch divergence note fires.

**Why:** The loop's alternation called for a fresh-ticker hunt; round 14's Jan-FY filer (CRWD) exercised the fy-labeling path in a shape the batch-45 collision arbitration didn't cover — the first non-colliding mislabeled-fy case in 126 tickers. A wrong FY label corrupts every downstream consumer that keys on it (YoY selectors, TTM windows, briefing prose), so sequence integrity is a correctness invariant.

**Alternatives considered:** Deriving labels from nominal `fiscalYearEnd` was rejected — the codebase deliberately distrusts it (JNJ reports "0103" while its filings label the Dec-ended year FY2025), and CRWD's own filings are internally inconsistent, so no single external source is authoritative; the rows' mutual sequence is the only closed-system signal. Preferring the *latest* filing's convention outright was rejected — the ORCL/Salesforce precedent shows the newest filing can itself be the mislabeled one; majority + latest-tiebreak is the conservative middle. Repairing without the strict-majority/≥3 guards was rejected — the 4-vs-4 test proves the walk alone would "repair" a genuine missing year into a wrong label.

**Blast radius:** `xbrl.py` only (new `_predecessor_label`, `_walk_label`, `_quarter_steps`, `_repair_sequence_breaks`; one wiring line in the assembly). No extraction, valuation, briefing, peers, calendar, or template changes. 8 new tests (CRWD shape, clean sequence untouched, 4-vs-4 no-majority untouched, short-backbone untouched, missing-quarter walks to own claim, fp-mismatch guard, held-target guard, newest-row blip). Suite at 518 green (510 + 8). `git diff --check` clean.

**Live:** Server restarted for the new code (kill by explicit PID per the standing lesson). 11/11 routes 200: 6 overviews, CRWD detail + compare, `/calendar`, `/api/search?q=crowdstrike`. Valuation-copy honesty (batches 40/45) holds on all six: CRWD Strong Sell −97.1% (Medium; 124.0% TTM EPS growth named as above the 40% maximum, 60× PEG-implied → 40× cap → 37× rate cap, all disclosed; FCF-yield 0.6% cross-check supports); MMM Strong Sell −71.9% and SO Strong Sell −63.7% on the disclosed 8× declining-earnings floor; C Buy +42.6% (clean PEG: 26.5× fair vs 18.5× current); BMY Strong Buy +184.5% (83.5% growth → 40% cap + 37× rate cap disclosed). Briefing registers (batches 41/42/46) hold on all six. No template change (backend-only), so no screenshot per the gate rules.

**Follow-ups (not this batch):** PEG-path sector calibration + live-10Y-yield wiring still await the user's word. APLD's FY2026 10-K annual revenue fact still not ingested by SEC — the retry loop keeps it armed (its sequence "break" is that genuine gap). PLD's Q2-2026 10-Q facts likewise still un-ingested. SKYD's 2024-quarter fy labels (Q3/Q4 FY2025 on 2024-09-30/2024-12-31, from post-merger filings' comparative columns) were investigated and deliberately left: no backbone reaches 3 rows through the merger, so the repair's guards correctly decline, and choosing the merged entity's FY convention through the merger is a judgment call, not a safe automated repair. The 9 mezzanine-gap tickers (batch 49) remain structural, not defects.

---

## 2026-10-11 — Pending-filing honesty note (batch 53)

**What:** `refresh_financials_if_stale` now computes a plain-language `Company.pending_filing_note` whenever a 10-Q/10-K is filed but EDGAR's companyfacts feed hasn't ingested its figures (the batch-37 ingestion lag); the overview page renders it as an amber note under Latest Quarter and it clears automatically once the quarter lands.
**Why:** 12 tickers showed stale quarters for ~3 months with no explanation while their 10-Qs sat filed — the retry loop was correctly armed, so the defect was user-facing silence, not pipeline failure. The note distinguishes three states precisely: ingestion lag (note), facts-ingested-but-unextracted (no note — a defect-hunt question, never mislabeled as lag), and structural stubs (no note — batch-48 acknowledgment owns those).
**Alternatives considered:** A backoff on the futile 6h re-pulls (rejected — the lag resolves unpredictably and the retry is what picks it up; the note makes the waiting legible instead); computing the note live in the route on every view (rejected — the check is TTL-gated, so persisting on the company row keeps the note valid between checks with zero extra EDGAR traffic beyond the existing companyfacts read, which reuses the already-fetched submissions feed).

---

## 2026-10-12 — Pending-filing note on compare + tearsheet (batch 56)

**What:** The batch-53 EDGAR-ingestion-lag honesty note now renders on the compare page (both quarterly and yearly modes) and the printable institutional tearsheet, completing the rollout across overview (batch 53), detail (batch 55), compare, and tearsheet. `CompareContext.pending_filing_note` is wired through `get_compare`'s shared `common` dict; the compare template reuses the exact amber classes from overview/detail; the tearsheet gets a print-proof "LATEST QUARTER DATA" block (`page-break-inside-avoid`, matching the batch-30 valuation×fundamentals callout) so a printed PDF can't be read as current when it isn't.

**Why:** A stale latest quarter is most dangerous where comparison and print amplify it: the compare page compares two stale-labeled periods without the overview's caveat, and a printed tearsheet outlives the page — the note self-clears once EDGAR ingests, so the print carries the freshness date it deserves. Wiring through the shared `common` dict rather than both `CompareContext(...)` constructions keeps the field impossible to forget in one mode.

**Alternatives considered:** Reusing the overview's `max-w-4xl mb-3` classes verbatim on the tearsheet (rejected — the tearsheet is a full-bleed light document where the bordered amber-50 callout matches the existing institutional tone, and `mb-3` inside the `space-y-8` container would collapse inconsistently); placing the note after the valuation bar instead of the header banner (rejected — freshness is a precondition for interpreting everything below it, so it belongs first).

**Blast radius:** `CompareContext` + `get_compare` wiring only; no extraction, valuation, briefing, or calendar changes. Templates: two additive conditional blocks, no redesign. 6 new tests. Suite 560 green, `git diff --check` clean. Screenshot gate passed (V note shown on both pages, AAPL control unchanged).

**Follow-ups (not this batch):** the same note on the vs page (the only remaining company data page without it); DBA/nickname alias map for descriptions (CART→Instacart, SHOO→Steve Madden, carried since batch 54).

---

## 2026-10-12 — Pending-filing note on the vs page (batch 57)

**What:** The batch-53 EDGAR-ingestion-lag honesty note now renders on the vs page, completing the rollout across overview (53), detail (55), compare (56), tearsheet (56), and vs. `VsCompany.pending_filing_note` is wired from `DetailContext.pending_filing_note` in `_vs_company` (which already carried it from batch 55 — no new service plumbing beyond the one-line pass-through); the vs template renders one amber note per affected side, prefixed with the ticker (`V: …`) since two sides make an unprefixed note ambiguous. Same amber classes as overview/detail/compare.

**Why:** The vs page was the only company data page left without the note, and it's the most dangerous surface for it: V's column reads "Q2 FY2026" while AAPL's reads "Q3 FY2026" with no explanation — exactly the silent asymmetry the note was built to call out.

**Alternatives considered:** A single shared note block for both sides (rejected — each side can have a different lagged quarter; per-side notes with ticker prefixes stay precise); putting the note inside each side's column header (rejected — the block belongs above the comparison, like the compare page's placement, where freshness reads as a precondition).

**Blast radius:** `VsCompany` model + one `_vs_company` pass-through line; one additive template block, no redesign. 7 new tests (2 service plumbing, 3 template render, 2 route-level). Suite 567 green, `git diff --check` clean. Screenshot gate passed (styled shots: V/vs/AAPL shows the V-labeled amber note, AAPL/vs/MSFT control unchanged).

**Follow-ups (not this batch):** DBA/nickname alias map for descriptions (CART→Instacart, SHOO→Steve Madden, carried since batch 54).

---

## 2026-10-12 — DBA/nickname alias map for Wikipedia descriptions (batch 58)

**What:** A curated `_DBA_ALIASES` map (ticker → exact Wikipedia article title) and a last-resort alias retry at the end of `_best_title`: when the legal-name search and the batch-54 suffix-stripped fallback both yield nothing, the alias is searched and only the article whose squashed full title exactly equals the squashed alias is accepted. Entries: CART "Maplebear Inc." → "Instacart"; SHOO "STEVEN MADDEN, LTD." → "Steve Madden, Ltd.". AGNC/APLD/MPLX deliberately excluded — no articles exist for them (both "AGNC Investment" and "Applied Digital" 404 on the summary API; MPLX searches surface only Marathon Petroleum/lists), and an alias can't fix a missing article. Live backfill: CART→Instacart ("Maplebear Inc., doing business as Instacart..."), SHOO→Steve Madden, Ltd. ("...publicly traded company that designs and markets shoes..."), both verified correct.

**Why:** This closes the last carried follow-up (batch 54→57). The two cases needed different treatments: CART's legal-name search already surfaced the right article as the top hit but word-agreement against "Maplebear" rejected it (DBA case); SHOO's "steve" vs "steven" defeated every agreement path including the suffix-stripped fallback (spelling-drift case).

**Alternatives considered:** A fuzzy relevance path for the alias retry (rejected — the founder's "Steve Madden" page would win on first-word agreement against an alias of "Steve Madden"; exactness is what makes the ", Ltd." load-bearing and keeps the batch-47 IBM/Commodore class closed); firing the alias before the suffix-stripped fallback (rejected — last-resort ordering guarantees the 130 already-described companies are provably untouched, covered by the not-consulted test); pointing AGNC at "American Capital" or MPLX at "Marathon Petroleum" (rejected — consolation attributions are misattributions).

**Blast radius:** One map + one retry block in `src/tickerlens/data/wikipedia.py`; 6 new tests. Suite 573 green, `git diff --check` clean. No template change, so no screenshot gate. Live on :8123: /company/{CART,SHOO,AGNC} all 200 with correct descriptions rendering.

**Follow-ups (not this batch):** none — the description alias map closes the last open follow-up from the batch-54 series.

---

## 2026-10-12 — Redeemable-NCI mezzanine extraction (batch 59)

**What:** New `Metric.REDEEMABLE_NCI` (`us-gaap:RedeemableNoncontrollingInterestEquityCarryingAmount` — the tag every live filer checked uses; the bare tag has no facts on any of them, so the chain is one tag), extracted per quarter as an instant balance-sheet metric, persisted in a new nullable `quarterly_financials.redeemable_nci` column (auto-migrated by `ensure_schema()`, backfilled DB-wide from cached companyfacts: 20 companies, 130 quarter-rows), and rendered as a conditional "Redeemable NCI (mezzanine)" row between liabilities and equity on the detail balance-sheet table, the tearsheet trends matrix, the compare table, the per-period CSV export, and the range table (row hidden when every quarter is None). `_derive_missing_balance_sheet` now subtracts the known mezzanine instant when deriving a missing leg (A = L + mezz + E); unknown mezzanine keeps the old two-leg formula.

**Why:** Round-16 hunt (CI, CCI, SNPS, OTIS, SPGI, ICE) found A ≠ L + E on four of six seeds — SPGI's balance sheet showed a $4.92B gap, OTIS $106M, ICE $32M, SNPS $30M (one quarter) — each exactly equal to the filer's redeemable noncontrolling interest, which sits in mezzanine equity (between liabilities and equity, part of neither). A scan of all 138 DB companies found 20 carriers (SPGI $4.92B, UNH $4.57B, APLD $2.01B, T $2.00B, ET $1.80B among them). `total_equity` is deliberately NOT inflated with the mezzanine amount — the filing's permanent-equity value stays filing-faithful (batch-49 BlackRock precedent: mezzanine gaps are in the filing itself, not extraction bugs); the fix makes the app *display* the third leg instead of hiding the imbalance.

**Alternatives considered:** Folding redeemable NCI into `total_equity` so A=L+E closes with two legs (rejected — misstates the filing's total equity; S&P's 10-Q reports total equity $31.288B, not $36.2B); leaving the gap unexplained with a footnote (rejected — a $4.9B unexplained gap reads as a data bug to the exact user who audits these pages); deriving the mezzanine instant via the identity (rejected — mezzanine is only ever filed explicitly; deriving it would fabricate it).

**Blast radius:** `data/xbrl.py` (metric + concept + wiring + derivation), `models/quarterly_financial.py` (one column), `services/financials.py` (upsert, BalanceSheet/Change/CompareDeltas models, CSV, range table), three templates (one conditional row each — additive, no redesign). 13 new tests. Suite 586 green, `git diff --check` clean. Screenshot gate passed (styled before/after): SPGI detail strictly better (identity closes: $24.59B + $4.92B + $31.29B = $60.79B), AAPL detail pixel-identical. Live on :8123 (restarted, kill-by-PID): 12/12 routes 200.

**Follow-ups (not this batch):** none — round 16 leaves no open items. SPGI's missing Q2 2026 quarter was investigated and is EDGAR ingestion lag (10-Q filed 2026-07-28, zero facts in companyfacts); the batch-53 pending-filing note already covers it and fires correctly.

---

## 2026-10-12 — Balance-sheet identity integrity: mixed-filing basis reconciliation + mezzanine third-leg gate (batch 60)

**What:** Two fixes under one theme — every rendered balance sheet must satisfy the accounting identity. (1) New `_reconcile_balance_sheet_identity` in `src/tickerlens/data/xbrl.py`, run inside `extract_recent_quarterly_financials` after per-metric extraction and before `_derive_missing_balance_sheet`: for each period end where Assets, Liabilities and Equity are all present, it checks `|A − L − mezz − E|` against `identity_tolerance`; on violation with legs drawn from ≥2 filings (provenance via the new `XbrlFact.accn` field), it replaces the quarter's legs with the earliest-filed single filing whose own facts for that end close the identity. `balance_sheet_metric` keeps its `dict[end, float]` contract via the new `_balance_sheet_facts` provenance-preserving core. (2) New `mezzanine_is_third_leg` predicate in `src/tickerlens/models/quarterly_financial.py` (+ model property): the "Redeemable NCI (mezzanine)" row renders only when a material identity gap exists in the same direction as the mezzanine value without overshoot. Wired through `_to_bs` (detail/compare/CSV), the range-table row filter in `_build_range_table`, and the tearsheet template's show-flag + per-quarter cells. The tolerance (`max($2M, 0.1% of assets)`) is defined once in models and shared by both.

**Why:** Round-17 hunt (BA, VZ, DRI, AZO, PNC, TRV) found Darden's FY2025Q2 rendering A=$12.94B against L+E=$12.52B — a $421M phantom gap. Root cause, verified against the filing: Darden's Q2 FY2026 10-Q tags its segment-note "Consolidated" total-assets column (Nov 23, 2025: $12,940.2M, context c-14) with a stale 2024-11-24 context (f-787), so per-metric latest-filed-wins picked Assets from the FY2026-Q2 filing while Liabilities/Equity came from the original FY2025-Q2 filing. Tesla's Q3-2024 quarter had the same defect class via a different mechanism (Q3-2025 10-Q comparative restated equity +$425M without restating A/L). The DB-wide identity audit then found the batch-59 follow-up: T, TMO, ACN, WMT, ET file redeemable-NCI tags while their extracted total equity already includes the amount (A−L−E closes to the dollar) — the unconditional mezzanine row double-counted (T showed L+$2.0B+E > A). A single filing's books always balance (double-entry), so the identity is a sound arbiter for both.

**Alternatives considered:** Preferring the native (earliest) filing's legs for every balance-sheet end, dropping latest-wins entirely (rejected — legitimate full restatements, e.g. 10-K comparative columns that re-report all three legs consistently, must keep flowing through; the guard only fires on violated identities, so consistent restatements are untouched); fixing DRI by excluding note-disclosure facts (rejected — companyfacts doesn't say which statement a fact came from, and note facts are sometimes the only source); deleting the mezzanine row for the five filers at extraction (rejected — the filed tag value is real data; the row is a presentation question, and the value stays in the DB/CSV); showing the mezzanine row whenever `|A−L−E|` is merely nonzero (rejected — rounding noise would flap the row; the tolerance floor covers worst-case million-rounding).

**Blast radius:** `data/xbrl.py` (XbrlFact.accn, `_balance_sheet_facts`, `_reconcile_balance_sheet_identity`, shared tolerance import; extraction only — income/cash-flow paths untouched), `models/quarterly_financial.py` (predicate + property, no schema change), `services/financials.py` (`_to_bs` gating, range-table filter), one tearsheet template conditional (no redesign). DB healed by re-extraction: TSLA Q3-2024, DRI FY2025Q2, ZTS Q1-2025 gaps → zero; SPG/CART/BLK/DLR single-filing gaps left filing-faithful. 14 new tests (6 reconciliation incl. DRI-shaped end-to-end, 8 predicate/gating). Suite 600 green, `git diff --check` clean. Screenshot gate passed (styled full-page tearsheets: T strictly better, SPGI unchanged). Live on :8123 (restarted): 10/10 routes 200.

**Follow-ups (not this batch):** SPGI's sector-peer chips render a 'vs XYZ' placeholder — possible peer-label bug, candidate for a future audit; BLK/DLR/SPG/CART single-filing gaps remain as filed (batch-49 precedent) — if a second mezzanine tag variant is ever identified, the backfill can extend.

## Batch 61 (2026-10-13) — 16-week quarterly facts are quarters

**Decision:** widen the standalone quarterly-fact duration window from 70–100 to 70–115 days (`_QUARTERLY_FACT_WINDOW`), covering 16-week (112-day) quarters filed by 52/53-week 4-4-5 retailers.

**Why:** Kroger's Q1 is 16 weeks (111–112 days). The 100-day ceiling silently discarded its Q1 revenue, net income, EPS, and operating-cash-flow facts every year — 3 of 8 stored quarters missing, with no error or warning. The missing Q1s then broke `_dedupe_period_labels`: the 2025-02-01 quarter's FY2025Q4 claim (from Kroger's own 10-K, end-year convention) collided with the 2026-01-31 10-Q's FY2025Q4 claim (begin-year convention), and the walk-back landed on a baseless "FY2023Q4" label after FY2024Q4 proved held. No other stored company was affected (DB-wide scan: KR was the only 8-quarter company missing Q1).

**Blast radius:** `data/xbrl.py` only — the window constant feeds `_income_series_for_tag`, the cash-flow q1s window (75–105 → 75–115), and all quarterly `staleness_window` usages (generic chain, finance/BDC/bank/mREIT revenue paths, NI facts for the EPS derivation). 115 stays below the 120-day split-basis class boundary, so 6M (~182d) facts still cannot enter as quarters; the Q4-derivation path (annual − 9M) is untouched. 4 new regression tests; suite 604 green. DB healed by re-seed + deletion of the two stale pre-fix out-of-window rows (no FK references; routes already `.limit(8)`).

**Alternatives considered:** a filer-specific carve-out for 4-4-5 retailers keyed off `fiscalYearEnd` (rejected — adds a new heuristic and a second notion of "quarterly"; the 100–115d band contains no standard non-quarter period, so the global widening is safe and simpler); converging Kroger's labels to the 10-K's end-year convention via `_repair_sequence_breaks` (rejected — the repair's strict-majority guard correctly declined, and the resulting begin-year series is monotonic, unique, and matches the filer's own 10-Q labels, which is the pipeline's standing convention per `_choose_fact_for_end`).

**Follow-ups (not this batch):** none — round 18 leaves no open items.

## Batch 62 (2026-10-13) — valuation design-envelope guards (REITs + hyper-growth)

**Decision:** two new Watch/unavailable guards in `compute_valuation`, placed after the batch-36 margin guard and before the PEG path (so they also block the sales fallback): (1) `is_reit` (SIC 6798 via `_is_mreit_sic`, threaded from `get_valuation`) — REITs are valued on funds from operations, not GAAP net income, so no P/E or margin-anchored P/S multiple applies; (2) EPS growth above the 40% model maximum (`_MAX_GROWTH_PCT`) — beyond it the PEG curve is clamped fiction and the TTM base is usually a one-off snapback, so the card declines instead of printing a clamped Strong Buy.

**Why:** the round-19 fresh-ticker hunt (ALL, HUM, ITW, TFC, WELL, MAR — all 8 quarters, clean sequences, identities within tolerance) exposed fabricated valuation signals. WELL rendered Strong Sell −79% (P/E 114× on depreciation-depressed GAAP EPS); ALL rendered Strong Buy +697% (37× capped P/E on a 135% investment-gain-driven EPS jump). A DB-wide scan showed the epidemic: 8 of 10 SIC-6798 REITs carried bogus PEG signals (AMT Strong Buy +48%, SPG Strong Buy +163%, PLD Strong Sell −75%, EQIX Strong Sell −44%; NLY/AGNC already Watch via the margin guard), and 36 non-REIT companies had EPS growth above the 40% model max with clamped triple-digit signals (MU +167% on 877% trough-snapback growth, COF +210%, T +397%, HON +359%, TRV +272%, BMY +184%, GS +168%). The model's own documentation calls 40% the maximum — inputs beyond it, and a sector the P/E framework cannot price, now get honest Watch copy instead of confident fabrications. Same doctrine as batch 36.

**Blast radius:** `services/valuation.py` (new `is_reit` kwarg, two guards) + `services/financials.py` (`get_valuation` threads the flag). 44 DB companies flip to Watch (8 REITs + 36 hyper-growth); all other signals verified unchanged (AAPL still Hold −5.4%). 5 new regression tests; 6 existing tests updated (3 encoded the old clamp-and-proceed behavior, 3 rate-guardrail tests retargeted from 100% to 30% growth to keep exercising the rate cap within the envelope). Suite 609 green. Live on :8123: WELL/ALL/SPG/MU cards render Watch with the new rationale copy; AAPL unchanged. No template change (backend-only).

**Alternatives considered:** capping the upside or the signal at Buy instead of Watch for hyper-growth (rejected — a capped +697% is still a fabrication; the input is outside the model's valid range, so declining is the honest output); routing REITs to the sales fallback (rejected — GAAP net margin is depressed by the same depreciation, so fair P/S = P/E × margin fabricates just as badly; verified WELL would still print a deep Sell); sector-relative multiples for banks (TFC Strong Buy +159% on a 27.7× fair P/E — real concern, but no clean detection and a bigger model redesign; logged as follow-up).

**Follow-ups (not this batch):** bank/insurer PEG multiples (sector-relative fair multiples); FFO extraction for REIT valuation (would restore real signals for the 10 Watch REITs); WELL's 10-K-only redeemable-NCI fact leaves a ~0.5% quarterly identity gap (within the 1% tolerance — observed, not invented); HUM/WELL Q2-2026 10-Qs filed 2026-07-29 not yet ingested by EDGAR (pending-filing note appears on page view via the freshness path, by design).

## Batch 63 (2026-10-13) — strict TTM windows: a gappy metric is None, never a silent partial sum

**Decision:** add `_compute_ttm_strict` in `services/financials.py` and use it for both TTM windows in `get_valuation`. In a full 4-quarter window, each metric's TTM is the sum only when *every* quarter carries that metric; otherwise the metric is None. Windows shorter than 4 rows keep the legacy skip-None convention (already flagged partial via `ttm_quarters < 4`, confidence capped at Medium).

**Why:** the round-20 hunt (HCA, EBAY, WM, NTRS, SYK, ELV — 8 quarters each, clean sequences) exposed a valuation fabrication. Northern Trust's Q2-2026 10-Q filed net income ($792.2M, correctly chosen over the $1.3178B YTD double-tagged fact) but zero XBRL EPS facts — verified directly against EDGAR companyfacts. `_sum_nullable` skipped the None, so TTM diluted EPS was a 3-quarter sum ($7.43 vs the true ~$9.56), understating earnings ~25%; the PEG path then rendered Strong Sell −64.5% on the understated base and compared it against a *complete* prior-4-quarter TTM for growth (−12.6%), an apples-to-oranges comparison. Halliburton carried the same class: its 2025 10-K tags no FY2025 Q4 EPS facts (verified zero), so HAL rendered Strong Sell −70.3% on 3-quarter EPS. The skip-None convention is correct for display aggregation (range tables, yearly views) but wrong as a valuation input: the EPS-dependent paths must be skipped and the model must fall back to the batch-33 sales path ("No per-share earnings to anchor a P/E multiple"), which already exists precisely for EPS-absent filers like ET.

**Blast radius:** `services/financials.py` only (new helper + two call sites in `get_valuation`); `compute_valuation` untouched; display aggregations (`get_overview`, range KPIs, yearly views) keep the legacy convention. DB-wide before/after dump over all 162 companies: exactly 2 signals change — NTRS Strong Sell −64.5% (peg) → Strong Buy +65.6% (sales, honest copy), HAL Strong Sell −70.3% (peg) → Strong Sell −52.9% (sales). The other 160 are byte-identical. 5 new tests (3 strict-unit, 2 `get_valuation` integration); suite 614 green.

**Alternatives considered:** sliding the window to the 4 most recent quarters *with* the metric (rejected — restores a PEG signal but mixes periods silently and needs a matching sliding prior window; more machinery, more subtle-failure surface, for a case the honest sales fallback already handles); deriving missing Q4 EPS as FY−9M (rejected for this batch — real candidate as follow-up, but carries restatement-mismatch risk and deserves its own batch); making `_compute_ttm` itself strict (rejected — would change display aggregations and the overview TTM KPIs, a UI-visible change outside this batch's scope).

**Follow-ups (not this batch):** Q4-EPS derivation (FY−9M) for 10-Ks that don't tag quarterly EPS (HAL class); bank/insurer PEG multiples (carried from batch 62); FFO extraction for REIT valuation (carried from batch 62).

## Batch 64 (2026-10-13) — ORLY description alias + seed-time enrichment; HAL-class Q4-EPS derivation closed as not tractable

**Decision 1:** curate `"ORLY": "O'Reilly Auto Parts"` in `_DBA_ALIASES` (`data/wikipedia.py`), extending the batch-58 alias map with a third entry and a second regression test for the exact-match guard.

**Why:** the round-21 hunt (CDNS, ORLY, ROST, CTAS, WST, PAYX — 8 quarters each, clean sequences, DB at 168) showed ORLY undescribed. Diagnosis: Wikipedia's primary search for "O REILLY AUTOMOTIVE INC" returns the correct article ("O'Reilly Auto Parts") as its TOP hit, but the apostrophe-join ("o"+"reilly" normalizing to "oreilly", not the company's "o"+"reilly" word pair) zeroes the word-overlap relevance score, so every relevance path in `_best_title` rejects the right answer. This is the DBA/nickname class the alias map exists for (batch-58 CART/SHOO), not a relevance-tuning bug — retuning overlap to accept it would weaken the batch-47 misattribution guards. The alias is human-verified (SEC 10-K cover page: "O'Reilly Automotive, Inc." doing business as O'Reilly Auto Parts) and exact-match guarded (the squashed-alias requirement keeps the NASCAR O'Reilly Auto Parts Series page out — covered by a new test).

**Decision 2:** `fetch_and_persist` now runs `_seed_time_enrichment` (`services/financials.py`) by default: backfill the company description and price/market-cap at seed time, blank-only, never-raising, with an `enrich=False` escape hatch for hermetic tests.

**Why:** the same audit found 21 seeded companies undescribed (15 from rounds 16–19 that never got a page view, plus the 6 round-21 tickers) and the 6 new ones priceless — because seeding never ran enrichment; it only happened inside `enrich_company` on page views. The route self-heal exists, but a 168-company DB whose coverage is a product promise shouldn't depend on someone visiting every page. Blank-only (never overwrites) differs deliberately from `enrich_company`'s clear-on-None policy: a re-seed must not wipe a good description on a transient Wikipedia failure. Never-raising follows the pipeline's standing convention (batch-16 warmers, batch-63 fallbacks). Backfilled 18/18 descriptions + 6/6 quotes live.

**Decision 3:** the batch-63 follow-up "derive missing Q4 EPS as FY−9M (HAL class)" is closed as deliberately not fixed.

**Why:** verified directly against live EDGAR companyfacts that HAL's 2024 and 2025 10-Ks carry ZERO `EarningsPerShare*` facts of any duration — the follow-up's premise (an FY anchor exists to subtract 9M from) is false. The class is 6 of 168 companies (ABNB, BRK.B, ET, HAL, MPLX, V: Q4 NI present, EPS absent). The only derivable path would be Q4 NI / implied Q4 WASO — but V has no annual WASO facts (partial coverage), and it would stack a second derivation on top of an already-derived Q4 NI, compounding error exactly the way batch 63's strict TTM windows were built to prevent. The batch-33 sales fallback with honest "no per-share earnings" copy is the correct terminal state for these filers, not a placeholder. This closes the last batch-63 follow-up; bank/insurer multiples and REIT FFO extraction remain carried.

**Blast radius:** `data/wikipedia.py` (1 map entry + comment); `services/financials.py` (new `_seed_time_enrichment` helper + 3-line call site in `fetch_and_persist` + docstring); tests (`test_wikipedia.py` +2, `test_financials.py` +3 incl. updating the existing `fetch_and_persist` test to patch the network). 18 descriptions + 6 quotes backfilled in `tickerlens.db`. Suite 619 green; `git diff --check` clean. Live on :8123 (restarted, kill-by-PID): /company/{ORLY,CDNS,ROST} 200 with descriptions rendering. No template change; screenshot gate N/A.

**Infra lesson (re-confirmed):** the stale dev server wiped ORLY's freshly backfilled description on the first page-view curl — `enrich_company` ran the OLD `wikipedia.py` (no alias) and its clear-on-None policy deleted the good value. Restart the server BEFORE any page-view verification whenever service code changed since the server started (batch-61 lesson, bitten again). The backfill script re-ran post-restart.

**Alternatives considered:** retuning `_normalize_words` to split apostrophes ("oreilly" → "o"+"reilly") instead of an alias (rejected — global tokenizer change with blast radius across all 147 described companies, for one ticker; the alias map is the curated escape hatch); making `enrich_company` blank-only too (rejected — its clear-on-None policy is deliberate per its docstring: "a fresh search that finds nothing is preferable to keeping stale/wrong text"; the seed path is the only one that needed blank-only semantics); full `enrich_company` in seed scripts instead of the targeted helper (rejected — risk factors and press highlights are expensive per the code comments; description+quote is the cheap presentable-minimum).

**Follow-ups (not this batch):** bank/insurer PEG multiples (carried from batch 62); FFO extraction for REIT valuation (carried from batch 62); risk-factor backfill for 65 companies (self-heals on page views via `enrich_company`); HAL class stays on the sales path by design (this batch's decision, terminal).

---

## Batch 65 (2026-10-13) — Q4 EPS from the continuing-operations annual tag (HAL class)

**Decision:** when a filer's 10-K tags no annual EPS under the generic tag,
derive Q4 EPS from the continuing-operations per-share tag's annual fact
(`IncomeLossFromContinuingOperationsPerDilutedShare` /
`...PerBasicShare`), gated by an implied-shares coherence check. Same
derivation machinery as before (Q4 NI over implied Q4 shares); the
fallback annual is annual-only, primary-tag annuals always win, and the
derived row carries the fallback tag as its source.

**Why:** Halliburton's 10-Ks tag no annual EPS under
`EarningsPerShareDiluted` (verified: last annual fact FY2019), while its
10-Qs tag quarters + 9M under the generic tag — so Q4 EPS was
underivable and HAL stored two EPS-less Q4 rows (FY2024, FY2025), forcing
the valuation onto the sales path. Its 10-Ks DO tag the annual under the
continuing-operations tag (FY2025 $1.50, FY2024 $2.83 via the corrected
comparative twin). This corrects batch 64's close of the same follow-up:
batch 64 verified "zero annual EPS facts" against the generic tag only,
so it missed the anchor that exists under the continuing-ops tag. With
the fallback, HAL's derived Q4s are $0.70 (FY2024) and $0.69 (FY2025),
and its valuation runs on the real PEG path (growth −11.1% YoY, P/E
17.2× on complete TTM EPS $1.90, fair value $15.22 vs $32.79 → Strong
Sell −53.6%) instead of the sales fallback (−52.9%).

**Guards (fail closed):** (1) the fallback requires the NI pair and
passes a 5% implied-shares coherence check (FY shares from NI/EPS vs 9M
shares) — a filer with material discontinued operations
(continuing-ops EPS != total EPS) is rejected rather than fabricated;
(2) the primary path gains the same check at a loose 75% as a tripwire
against scale-corrupted inputs (HAL's 2022–2024 10-Qs tagged net-income
dollar amounts, in thousands, under the EPS tag — a 1e6× mis-scale that
would otherwise print a Q4 EPS wrong by ~4×); 75% sits above the worst
legitimate divergence observed DB-wide (Capital One FY2025, 56%, from
the Discover merger + acquisition accounting) with margin — the first
cut at 10% regressed COF and SOFI to EPS-less Q4s, caught by the DB-wide
before/after diff, and the tolerance was raised with a COF-shaped
regression test locking the old subtraction value ($3.80); (3) if the
share-implied derivation returns None on the fallback path, the row is
skipped (no plain subtraction, which would mix continuing-ops annual
with total 9M). Loss years abstain from the check and keep existing
behavior.

**Blast radius:** `data/xbrl.py` only (new fallback fetch in the EPS
branch of `quarterly_income_metric`, threaded winner-only through
`_income_series_for_tag` into `_derive_q4_income`, plus the
`_shares_coherent` helper). DB-wide before/after extraction over all 168
companies (git-stash A/B on identical 6h-cached companyfacts): exactly
ONE ticker changes — HAL gains the two Q4 EPS rows; the other 167 are
byte-identical. 5 new tests (HAL-shaped derivation incl. source-tag,
discontinued-ops rejection, scale-garbage tripwire, no-NI rejection,
COF merger-divergence tolerance). Suite 624 green, `git diff --check`
clean. Live on :8123 (started fresh): 7/7 routes 200; HAL detail renders
0.6999/0.6922; HAL valuation card shows Methodology: PEG. No template
change (backend-only); screenshot gate N/A. HAL re-seeded via
`fetch_and_persist`.

**Alternatives considered:** deriving Q4 EPS as FY−9M by plain
subtraction on the fallback annual (rejected — mixes continuing-ops
annual with total 9M and reintroduces the DUOL inversion class);
adding the continuing-ops tag to the CONCEPTS chain for gap-fill
(rejected — the annual and 9M live in different tag series, so per-tag
derivation would never combine them, and standalone quarters could
silently become continuing-ops EPS); deriving from NI ÷ weighted-shares
tags (rejected — HAL tags no usable weighted-shares concept in
companyfacts); dropping the primary-path guard entirely after the
COF/SOFI false positives (rejected — the 75% tripwire keeps the
1e6×-scale protection at zero observed cost; the false positives came
from the tolerance, not the guard).

**Follow-ups (not this batch):** V/ABNB/BRK.B have no plain EPS in
companyfacts at all (multi-class dimensional EPS, excluded from
companyfacts) — needs dimensional-fact support, its own investigation;
NTRS's Q2-2026 10-Q still tags NI but zero EPS facts (10-Q gap, not a
10-K annual gap — a quarterly NI÷shares derivation is the candidate
fix); XOM stores only 2 quarters (seed-history quirk, unrelated to EPS);
bank/insurer PEG multiples (carried from batch 62); FFO extraction for
REIT valuation (carried from batch 62); risk-factor backfill for 65
companies (self-heals on page views via `enrich_company`).

## Batch 66 (2026-10-13): EPS Undistributed fallback — NTRS Q2-2026 EPS recovered

**Finding:** Northern Trust's Q2-2026 10-Q tags net income ($792.2M) but
zero plain EPS facts, so the quarter stored EPS-less and TTM diluted EPS
was a 3-quarter sum (~25% low), which the PEG path turned into a
fabricated Strong Sell (−64.5%). Batch 65's candidate fix was a
quarterly NI÷shares derivation — but live companyfacts showed a better
anchor: the 10-Q tags the face-of-statement EPS under the two-class
`...Undistributed` tags (Basic $4.25 / Diluted $4.23), verified against
the 10-Q itself: the income statement prints "PER COMMON SHARE Net
Income — Basic $4.25 — Diluted 4.23", and the two-class reconciliation
(NI applicable to common $787.5M − participating allocation $5.3M =
$782.2M over 183,993,670 shares = $4.25) proves the Undistributed value
IS the reported EPS, not a component of it.

**Fix:** `EarningsPerShareBasicUndistributed` /
`EarningsPerShareDilutedUndistributed` appended to the EPS CONCEPTS
chains in `data/xbrl.py`, so they gap-fill quarters the generic tag
lacks. The plain tag still wins every end it covers (merge order), and
the fallback is a filed value, not a derivation.

**Guards (fail closed):** the Undistributed tag is dropped from the
chain when the filer also tags a `...Distributed` fact for that metric
(`_has_distributed_eps_facts` in the EPS branch of
`quarterly_income_metric`). A filer splitting two-class EPS into
distributed + undistributed components would otherwise get the
undistributed piece stored as total EPS — understated — so the quarter
stays honestly blank instead. A DB-wide audit of the 41
EPS-null-with-NI quarters confirmed NTRS is the only Undistributed
case in the DB: ABNB/BRK.B/ET/MPLX/V carry no usable EPS tags at all
(dimensional multi-class / MLP per-unit facts, excluded from
companyfacts).

**Blast radius:** `data/xbrl.py` only (chain extension + guard +
tag maps). DB-wide before/after extraction over all 168 companies
(same 6h-cached companyfacts): exactly ONE ticker changes — NTRS gains
Q2-2026 EPS (basic 4.25, diluted 4.23); the other 167 are
byte-identical. 3 new tests (NTRS-shaped gap-fill incl. plain-wins +
source-tag, Distributed-guard honest blank, end-to-end extraction).
Suite 627 green, `git diff --check` clean. Live on :8123 (restarted):
11/11 routes 200; NTRS detail renders Q2 EPS $4.23; NTRS valuation now
runs on complete TTM diluted EPS $11.66 → Strong Buy +157.9% (PEG,
37.0× capped fair P/E, Medium confidence), replacing the fabricated
Strong Sell. No template change (backend-only); screenshot gate N/A.
NTRS re-seeded via `fetch_and_persist`.

**Alternatives considered:** quarterly NI÷shares derivation (batch 65's
candidate — rejected: the filed Undistributed EPS is authoritative and
already reflects the participating-securities allocation; NI÷shares
gives $4.31, 1.3% high, and needs a diluted-shares tag not every filer
carries); adding Undistributed without the Distributed guard (rejected —
component-split filers would get understated EPS); promoting
Undistributed to first-class chain equality (rejected — plain must win
on overlap; the existing merge order already guarantees that).

**Follow-ups (not this batch):** dimensional EPS for V/ABNB/BRK.B +
MLP per-unit EPS for ET/MPLX — needs dimensional-fact support, its own
investigation; bank/insurer PEG multiples (carried from batch 62); FFO
extraction for REIT valuation (carried from batch 62); risk-factor
backfill (self-heals on page views via `enrich_company`).

## Batch 67 (2026-10-14): fresh-ticker hunt round 22 — FICO/WDAY/RMD/GWW/CEG/CPRT seeded; GWW initials-name relevance defect fixed

**Seeds:** 6 new tickers live from SEC, 8 quarters each, clean FY sequences
(FICO Sep FY; WDAY Jan FY; RMD Jun FY; CPRT Jul FY; GWW Dec; CEG Dec),
balance-sheet identities hold (CPRT carries a 0.2% gap — no redeemable-NCI
or other extractable facts in companyfacts; filing-real/rounding, not
fixable), seed-time enrichment committed descriptions + prices for all 6.
DB at 174.

**Deep audit — three candidate defects, all verified clean:**
- FICO FY2026Q2 rev +35% QoQ ($512M → $691.7M): the 10-Q tags TWO
  revenue facts for 2026-03-31 — $1,203.6M (start 2025-10-01, fiscal H1)
  and $691.7M (start 2026-01-01, the quarter). The pipeline correctly
  keeps the quarterly one (verified: 691.7 + 511.96 = 1,203.6 = the H1
  fact). Genuine strong quarter, not an extraction defect.
- WDAY FY2027Q2 NI $632M (~3x prior quarters): companyfacts shows
  IncomeTaxExpenseBenefit of −$172M/−$305M for the quarter — a one-time
  tax benefit, filing-real (DLR batch-40 precedent).
- CEG FY2026Q1 rev $11.1B (+83% QoQ): the Calpine acquisition closed in
  the quarter; the filed numbers are what they are.

**One real defect found and fixed.** GWW was the only seeded company
left descriptionless: "W.W. GRAINGER, INC." could never resolve — the
initials mismatch (SEC normalizes "w.w" as one token; Wikipedia's
"W. W." splits into two single-letter tokens that `_normalize_words`
drops) defeats first-word agreement and the lead-word fallback, so every
relevance path rejects the correct top hit. **Fix** (`data/wikipedia.py`):
curated `"GWW": "W.W. Grainger"` in `_DBA_ALIASES` (same escape hatch as
ORLY batch 64); the alias retry accepts only the article whose squashed
title equals "wwgrainger", so "Grainger plc" (a different UK company)
can't misattribute. DB-wide check: GWW is the only company with the
initials pattern. Description backfilled and rendering.

**Valuation sanity on the 6 new cards:** FICO Strong Buy +77.3% (Medium,
PEG on filed TTM EPS $34.62, 35.4% growth — below the 40% Watch guard);
WDAY Watch (Low — +130% TTM EPS growth trips the batch-62 hyper-growth
guard, by design); RMD/CEG/CPRT/GWW Strong Sells are model-honest on
filed data (CEG's lumpy utility EPS hits the P/E floor; GWW's TTM EPS is
depressed by its real Q3-2025 charge — filed data, disclosed).

**Tests:** 2 new (alias rescues initials name; alias rejects the wrong
"Grainger plc"). Suite 629 green.

**Follow-ups (not this batch):** dimensional EPS for V/ABNB/BRK.B + MLP
per-unit EPS for ET/MPLX (carried from batch 66); bank/insurer PEG
multiples (carried from batch 62); FFO extraction for REIT valuation
(carried from batch 62); risk-factor backfill (self-heals on page views
via `enrich_company`).

## Batch 68 (2026-10-14): dimensional/multi-class EPS investigation — ABNB + ET/MPLX recovered, V/BRK.B terminal

**Investigation.** Closed the batch-65/66 follow-up "dimensional EPS for
V/ABNB/BRK.B + MLP per-unit EPS for ET/MPLX" with live EDGAR evidence.
Key structural finding: the SEC companyfacts API **strips all
dimensional facts** — 0 of 23,227 of Visa's 10-Q/10-K facts carry dims,
and Visa's `EarningsPerShareBasic` facts (verified present in the 10-Q
instance XML, context `StatementClassOfStockAxis=CommonClassAMember`,
Q3 FY2026 $2.97) are absent from the API entirely. Dimensional EPS is
therefore unrecoverable from the pipeline's data source, full stop.

**Recoverable (shipped).** Three of the five carry *dimensionless* EPS
under non-generic tags, verified against the filed 10-Qs:
- ABNB tags quarterly EPS only under
  `IncomeLossFromContinuingOperationsPerBasicShare/DilutedShare`
  (Q2 2026: $1.38/$1.37 — matches the 10-Q face). It has zero
  discontinued-operations facts, so continuing == total.
- ET/MPLX tag `NetIncomeLossPerOutstandingLimitedPartnershipUnitBasicNetOfTax`
  / `NetIncomeLossNetOfTaxPerOutstandingLimitedPartnershipUnitDiluted`
  (total-income per-unit tags; ET Q2 2026: $0.59/$0.59, MPLX: $1.06/$1.06).

**Fix** (`data/xbrl.py`): the four tags join the EPS CONCEPTS chains as
tail fallbacks (generic still wins every end it covers; inert for
corporate filers). The continuing-ops tag is gated by a new
`_has_discontinued_ops_facts` presence check — a filer with any
income-statement discontinued-ops facts gets the tag dropped, so a
continuing-ops number is never stored as total EPS (fail-closed; ET's
discontinued-ops history is why the gate is presence-based, and ET
doesn't need the tag anyway). The Q4 derivation composes: with the
continuing-ops tag as winner, annual/9M facts come from the same tag
and the NI-implied derivation runs on the primary path (ABNB Q4 2025
derived $0.5631/$0.5534 — matches the filed ~$0.55-0.56).

**Terminal (documented, not fixable from companyfacts).**
- V: EPS is per-class dimensional (stripped by the API); no
  dimensionless `WeightedAverageNumberOfSharesOutstanding` either, so
  NI÷shares derivation is impossible.
- BRK.B: `EarningsPerShareBasic` ends FY2013; modern EPS is
  dimensional per-class; WASO facts are stale (end 2015).
Both keep the batch-33 sales-path fallback with honest copy. A
NI÷shares derivation was considered and rejected: for multi-class
filers the two-class allocation makes it inexact, and V lacks even the
share counts.

**Blast radius:** DB-wide before/after extraction over all 174
companies (git-stash A/B, warm companyfacts cache): exactly ABNB, ET,
MPLX change — each gains 8 quarters of EPS; the other 171 are
byte-identical. All three re-seeded via `fetch_and_persist`.
Valuations now run on the real PEG path: ABNB TTM diluted EPS $4.39
(+6.5% YoY) → Strong Sell −74.1% (model-honest: 37.7× P/E vs 9.8× fair
on 6.5% growth; AI briefing reconciles with its fundamentals Watch);
ET Strong Buy on TTM $1.47 (+14.0%); MPLX on TTM $4.65 (+10.5%).

**Tests:** 4 new (ABNB-shaped cont-ops fill incl. exact Q4 derivation
$1.00, discontinued-ops guard honest blank, MLP per-unit fill with
source tags, plain-tag precedence). Suite 633 green.

**Follow-ups (not this batch):** bank/insurer PEG multiples (carried
from batch 62); REIT FFO extraction (carried from batch 62);
risk-factor backfill (self-heals on page views via `enrich_company`).

## Batch 69 (2026-10-14): fresh-ticker hunt round 23 — SHW/ADP/TTWO/SLB/EOG/PGR seeded; acronym "(company)" description defect fixed

**Seeds:** 6 new tickers live from SEC, 8 quarters each, clean FY sequences
(SHW Dec; ADP Jun; TTWO Mar — FY2027Q1 is the June-2026 quarter, filed
August 2026; SLB/EOG/PGR Dec), balance-sheet identity 0.000% on all 48
quarters, EPS complete on every row, descriptions present for 5 of 6
(ADP was the miss — see below). DB at 180.

**Deep audit — the TTWO FY2025Q4 loss quarter, verified genuine.** The
row shows NI −$3.726B / EPS −$21.12 against otherwise −$0.1B quarters —
the shape of an extraction bug, so it was checked against raw
companyfacts (CIK 0000946581): the filed 10-K annual NI is −$4.4789B and
the filed 9M YTD NI is −$752.7M, so Q4 = annual − 9M = −$3,726.2M
exactly; Q1–Q3 (−262M, −365.5M, −125.2M) + Q4 sums to the annual to the
dollar (a real goodwill-impairment quarter, Zynga-related). The EPS is
the batch-65 NI-implied derivation: implied FY shares 175.10M from
annual NI/EPS (−$4,478.9M / −$25.58), implied 9M shares 174.62M, Q4
share-month residual (12·FY − 9·9M)/3 = 176.53M, Q4 EPS −3,726.2/176.53
= −21.1171 — self-consistent with the filed inputs (the −0.15 vs naive
annual−9M subtraction is the different-share-count effect the
derivation exists to handle). Not a defect. The valuation layer treats
it honestly: TTM EPS growth +92.8% trips the batch-62 hyper-growth
guard → Watch, method unavailable, Low confidence — no fabricated
signal.

**One real defect found and fixed.** ADP was description-less. Root
cause (`data/wikipedia.py`): the batch-47 acronym rule matched only
titles literally equal to the ticker ("AMD", "BNY"). Wikipedia's search
for "AUTOMATIC DATA PROCESSING INC" returns "ADP (company)" at rank #1 —
the real article, disambiguated because the bare phrase is taken — but
the rule judged it irrelevant ("adp (company)" != "adp"), so the "top
hit irrelevant" branch picked the highest-overlap name-contained lower
hit: "Automatic data processing", which is a *disambiguation* page. Its
extract is correctly rejected by type, leaving ADP with no description
— the one case where the right article sat at rank #1 and the pipeline
still missed it. **Fix:** both the acronym rule in `_title_relevant` and
`_relevance_overlap` now compare the parenthetical-stripped bare title
to the ticker, so "ADP (company)" is relevant with overlap 100 — the
same standing as "AMD"/"BNY" — and the predecessor-override can no
longer displace it with a concept/disambiguation page. Safety: the
extension only fires for a "(company)"-disambiguated acronym article in
Wikipedia's own top-5 for the legal-name query — the same accepted risk
class as the existing bare-ticker rule (non-"(company)" parentheticals
still never relevant). Blast radius (DB-wide stash A/B, warm
companyfacts cache, 180 companies): exactly ADP changes
("Automatic data processing" → "ADP (company)"), 179 byte-identical.
ADP description backfilled (28-word extract, verified the ADP payroll
article) and rendering.

**Valuation sanity on the 6 new cards:** PGR Strong Buy (PEG, TTM
$19.94 +12.3%, insurer — batch-46 financial margin register holds:
"spread discipline and fee-income efficiency"); EOG Strong Buy (PEG,
TTM $12.85 +24.7%); ADP/SHW Strong Sell (PEG on filed data, ADP's
industrial margin register correct for a business-services filer); SLB
Strong Sell with the floor-guardrail honesty note (growth −29% → 8× P/E
floor, confidence capped Medium); TTWO Watch via the hyper-growth
guard. All model-honest, no fabrication patterns.

**Tests:** 2 new (acronym "(company)" relevance incl. mismatched-ticker
and non-company-parenthetical negatives + overlap-100; `_best_title`
picks "ADP (company)" over the disambiguation page on the live result
order, mocked). Suite 635 green.

**Follow-ups (not this batch):** bank/insurer PEG multiples (carried
from batch 62); REIT FFO extraction (carried from batch 62);
risk-factor backfill (self-heals on page views via `enrich_company`).

## Batch 70 (2026-10-14): bank/insurer design-envelope guard — PEG multiples can't price lenders

**Decision:** add a third design-envelope guard in `compute_valuation` (`services/valuation.py`): `is_bank_insurer` (SIC 6000–6199 banks/lenders/finance-cos, 6300–6499 insurers, via new `_is_bank_insurer_sic` in `data/xbrl.py`, threaded from `get_valuation` in `services/financials.py`) returns Watch/unavailable with honest copy before both the PEG path and the sales fallback. Placed after the batch-36 margin guard and before the batch-62 hyper-growth guard, so a bank's cyclical EPS spike gets the sector copy (the more fundamental reason the model declines).

**Why:** closes the "bank/insurer PEG multiples" follow-up carried since batch 62. A DB-wide valuation audit of all 180 companies showed the PEG curve fabricating across the whole financial sector: BAC Strong Buy +195.9% at a 37.0x "fair" P/E, CI +216.2% at 37.0x, CB +203.2% at 37.0x, PNC +199.1% at 36.4x, TFC +159% at 27.7x, NTRS +157.9% at 37.0x, BNY +122.9% at 37.0x, WFC +119.5%, JPM +108.1% — banks rarely sustain even 15x through a cycle. Loan-loss provisions, reserve releases, and rate cycles make bank/insurer EPS growth cyclical rather than compoundable, so a growth-implied multiple is the wrong framework, exactly the batch-62 doctrine (REITs) and batch-36 doctrine (margin absurdity). The sell side fabricated too: HUM −82.7%, SOFI −74.3%, UNH −67.1% at the generic 8x distressed-earnings floor, and BRK.B Strong Sell −38.4% on the sales path (fair P/S = P/E x net margin inherits the same broken multiple; the market values Berkshire on book value).

**Detection boundary:** SIC 6000–6199 + 6300–6499. Deliberately excluded: 6200–6299 (brokers/dealers, exchanges, advisors — GS, MS, SCHW, BLK, ICE are fee businesses where the P/E framework still applies; GS/MS/SCHW already Watch via the hyper-growth guard) and 6700–6799 (holding companies; REITs already guarded). COIN (6199, crypto exchange) lands inside the boundary but was already Watch/unavailable, so no signal change — noted, not special-cased.

**Blast radius:** DB-wide before/after dump over all 180 companies: exactly the 23 SIC-classified banks/insurers change — 20 flip to Watch/unavailable (incl. BRK.B off the sales path), TRV/ALL/COF keep Watch with the sector copy replacing the hyper-growth copy; the other 157 are byte-identical (AAPL still Hold). 6 new tests (5 guard unit tests incl. margin-guard precedence, hyper-growth-guard precedence, sales-path block, non-bank unaffected; 1 SIC boundary test). 2 batch-63 fixture tests retargeted: their `_valuation_company` used SIC 6021 (arbitrarily chosen as "not a REIT" in batch 63) — now a guarded SIC, so the fixture moved to neutral 3571. Suite 641 green.

**Alternatives considered:** sector-relative fair multiples (capped P/E bands for banks, e.g. 15x ceiling) — rejected per the batch-62 precedent: a capped Strong Buy is still a fabrication, the growth framework itself doesn't apply; Watch is the honest output. P/B-based valuation (book value + ROE from the stored balance sheet) would restore real signals for the 23 Watch lenders/insurers — logged as the follow-up, its own batch-sized feature. Routing banks to the sales fallback — rejected: fair P/S inherits the broken fair P/E (BRK.B proved it fabricates there too).

**Follow-ups (not this batch):** P/B-based bank/insurer valuation (restore real signals for the 23 Watch lenders/insurers); REIT FFO extraction (carried from batch 62); risk-factor backfill (self-heals on page views via `enrich_company`).

## Batch 71 (2026-10-14): P/B-based bank/insurer valuation — restoring real signals

**Decision:** replace the batch-70 bank/insurer Watch-only guard with a sector-native valuation path: price-to-book via the Gordon justified multiple, fair P/B = (ROE − g) / (CoE − g). Cost of equity = 10-year Treasury + 5pp bank equity premium, floored at 8%; g = 3% long-run nominal growth. The fair P/B is clamped to [0.5, 2.5]× (the observed through-cycle trading range for US banks/insurers), and a binding clamp names itself in the reasoning and caps confidence at Medium — the batches 40/45 honesty class for guardrail-driven targets. `get_valuation` (services/financials.py) computes `book_value_per_share` (latest total_equity ÷ shares outstanding) and `roe_pct` (TTM net income ÷ average TTM equity, strict-window NI, skip-None equity mean) from the stored quarterly rows; the FCF cross-check footnote is deliberately skipped on this path because a bank's operating cash flow mixes deposit/loan balance moves, so an FCF-yield footnote would be noise, not context.

**Why:** closes the "P/B-based bank/insurer valuation" follow-up carried since batch 62 (re-logged in batch 70). Batch 70's Watch was the honest answer to fabricated PEG signals, but 22 of the 23 lenders/insurers had complete book-equity data in the stored balance sheets — a balance-sheet business priced on book value gets a real, auditable signal instead of a permanent shrug. The Gordon formula is the textbook justified-P/B identity for a bank, and every number on the card (ROE, CoE decomposition, current vs fair P/B) is auditable from the reasoning bullets. The honesty wins are visible: BRK.B goes from a fabricated Strong Sell −38.4% (sales path) to Hold −8.5% on book value; money-center banks land on Hold (JPM −4.1%, BAC −0.8%, WFC +4.5%, PNC −0.6%) — roughly fairly priced, which matches the market; genuinely rich-on-book names (AXP 6.07× book, PGR 3.61×, UNH 3.40×) get Strong Sells the framework can defend.

**Detection boundary / honesty boundaries:** ROE ≤ 0 or missing/non-positive book equity → the same Watch/unavailable copy as batch 70 ("Book-value inputs are incomplete, so no price-to-book target can be computed"). The Gordon model gives a zero/negative justified P/B for a loss-making bank — that is nonsense, not a target — so the decline mirrors the batch-26 non-positive-margin guard on the sales path. COIN (negative ROE) is the live example: stays Watch. The method string "book" renders as METHODOLOGY: BOOK via the existing `upper()` filter — no template change, screenshot gate N/A.

**Blast radius:** DB-wide before/after dump over all 180 companies (git-stash A/B): exactly the 22 banks/insurers with positive ROE change Watch/unavailable → book path; COIN stays Watch; the other 158 are byte-identical. 8 new tests (basic JPM-shaped path, cap bind incl. naming, floor bind incl. naming, negative-ROE Watch, missing-input Watch, zero-book Watch, rate sensitivity via ten_year_yield_pct, non-bank ignores book inputs). Suite 649 green.

**Alternatives considered:** restoring a capped P/E band for banks (e.g. 15x ceiling) — rejected in batch 70 already and stays rejected: the growth framework doesn't apply to cyclical book earnings; the sector-native multiple is the honest one. GAAP book vs tangible book: the pipeline doesn't extract intangibles/goodwill, so GAAP book is the input; insurers with heavy goodwill (HUM, UNH) may read rich — accepted as a documented v1 limitation, not a reason to decline a signal (the same class as batch 70's margin-anchored caveats).

**Follow-ups (not this batch):** REIT FFO extraction (carried from batch 62); risk-factor backfill (self-heals on page views via `enrich_company`).

## Batch 72 (2026-10-15): P/FFO-based REIT valuation — closing the FFO follow-up carried since batch 62

**Decision:** value equity REITs on price-to-FFO via the Gordon justified multiple, fair P/FFO = (1 + g) / (CoE − g), with FFO extracted from XBRL at extraction time. FFO = net income + depreciation/amortization − gains on property dispositions + real-estate impairments (the NAREIT definition, computed from filed XBRL rather than the earnings-release reconciliation), stored per quarter in a new nullable `ffo` column on `quarterly_financials` (auto-migrated by `ensure_schema()`; threaded through `_compute_ttm`/`_compute_ttm_strict` and `KPISnapshot`). New `FFO_DEPRECIATION` / `FFO_DISPOSITION_GAINS` / `FFO_IMPAIRMENT` concept chains reuse the quarterly income machinery (standalone-quarter facts, Q4-from-annual derivation, freshness rules), so the composite inherits every prior defect fix. Depreciation chain: `DepreciationDepletionAndAmortization` → `DepreciationAndAmortization` → `DepreciationAmortizationAndAccretionNet` (tower REITs AMT/CCI tag the line under the accretion-net variant — live-data defect found on the backfill, 2 of 10 REITs had no FFO without it). Gains chain is property-specific tags first (`GainLossOnSaleOfProperties` …) then generic; impairment is real-estate-only (goodwill impairments stay in FFO — CCI's −$4.6B 2024Q4 fiber goodwill impairment correctly depresses its TTM FFO). Gains/impairments are episodic: a quarter with no filed fact counts as zero, and the card copy names the assumption. Cost of equity = 10-year Treasury + 4.5pp REIT equity premium, floored at 8% (bond-like cash flows earn a smaller premium than levered banks).

**Why:** closes the "REIT FFO extraction" follow-up carried since batch 62 (re-logged in batches 70/71). Batch 62's REIT guard returned Watch/unavailable for all 10 REITs — honest, but GAAP EPS structurally understates a REIT's cash earning power (WELL rendered Strong Sell −79% at 114× P/E; SPG Strong Buy +163%; PLD Strong Sell −75%), and the industry prices REITs on FFO. The Gordon justified P/FFO is the sector-native multiple, and every number on the card (TTM FFO/share, CoE decomposition, current vs fair P/FFO) is auditable from the reasoning bullets. Live signals: AMT Buy +10.6%, O Strong Buy +34.4% (fair 17.2× vs 12.7× current — O trades below its through-cycle multiple), CCI Strong Sell −25.2% (23.0× current on impairment-depressed TTM FFO), DLR −40.7% and EQIX −38.0% (data-center REITs at ~26–28× current vs 17.2× fair), PLD Strong Sell −31.9%, WELL Strong Sell −62.5% (45× current P/FFO — the model-honest read on an extreme multiple). AGNC/NLY (mortgage REITs, no property depreciation) keep the Watch copy via the batch-36 margin guard, which sits before the REIT branch by design.

**Detection boundary / honesty boundaries:** (1) FFO None (no depreciation series) or non-positive TTM FFO or missing shares → the Watch/unavailable copy ("FFO could not be computed…"). (2) The perpetual g is capped at the 3% long-run rate — recalibrated on live data after the first backfill showed the raw design fabricating: O's 7.5% TTM print implied a 71.7× justified P/FFO (Strong Buy +119% on the 28× cap), and DLR/EQIX/SPG/WELL at 11.8–80.9% hit the Gordon singularity and declined entirely. A TTM print is cyclical, not perpetual; observed declines ARE kept (a shrinking FFO stream really is worth less). The cap is named in the reasoning whenever it binds. (3) Dominant-quarter guard: a TTM window where one quarter exceeds 2.5× the median quarter is a one-off, not a run-rate — SPG's 2025Q4 ran $3.47B vs ~$0.95B typical (its $2.9B Taubman acquisition remeasurement gain is filed dimensionally, invisible to the SEC companyfacts API per the batch-68 structural finding, so the composite can't strip it; SPG's own reported Real Estate FFO confirms: $1.33B vs our $3.47B). The branch declines to Watch with the quarter named rather than printing a target on the polluted base or inventing a "normalized" number; the signal self-heals when the quarter rolls off. Threshold 2.5× clears all other REITs (WELL 1.7×, CCI 1.7× pass). (4) The 8×/28× clamp is a defensive guardrail for rate extremes, not the valuation engine (unreachable while g ≤ 3% < 8% CoE floor). The method string "ffo" renders as METHODOLOGY: FFO via the existing `upper()` filter — no template change, screenshot gate N/A.

**Blast radius:** DB-wide before/after dump over all 180 companies (git-stash A/B, after the 10-REIT backfill): exactly the 8 equity REITs change Watch/unavailable → P/FFO path (SPG Watch → Watch with the dominant-quarter copy); AGNC/NLY byte-identical (margin guard); the other 172 byte-identical. Backfill: all 10 SIC-6798 REITs re-extracted live from SEC; 8/8 equity REITs carry 8 quarters of FFO. 23 new tests (FFO composite incl. gain/impairment legs, missing-leg Nones, all three depreciation tags incl. the accretion-net tail, gain tag fallbacks, P/FFO basic/rate-sensitivity/floor-bind, growth cap naming, dominant-quarter Watch + pass-through + short-window, non-REIT ignores FFO inputs). Suite 672 green, `git diff --check` clean.

**Alternatives considered:** keeping observed TTM growth as the perpetual g (the interrupted draft's design) — rejected on live data: it printed a 71.7× justified multiple for O and declined 4 of 8 equity REITs at the singularity. Normalizing SPG's TTM by dropping 2025Q4 — rejected: inventing a "clean" number is fabrication; declining with the quarter named is the doctrine-consistent call. Extending the gain chain with the Taubman remeasurement tag — impossible: the fact is dimensional and absent from companyfacts entirely (verified by tag scan).

**Follow-ups (not this batch):** risk-factor backfill (self-heals on page views via `enrich_company`); SPG's signal self-heals when 2025Q4 rolls off the TTM (Q4-2026 filing); the dominant-quarter guard is REIT-only — the same one-off-quarter pollution class exists on the PEG path (left alone: the batch-62 hyper-growth guard already owns the extreme end there).

## Batch 73 (2026-10-15): split-capex composite for airlines + balance-sheet-total backfills missing Assets

**Decision:** (1) airline filers that split capex into flight-equipment and other-productive-asset payments get a tag-detected composite: `_flight_equipment_capex` sums `PaymentsForFlightEquipment` + `PaymentsToAcquireOtherProductiveAssets` per YTD period (re-filed periods deduped, latest filing wins), then un-cumulates with the same machinery as a single tag. The composite fires only when the flight-equipment tag's newest end is newer than the generic CAPEX chain winner's — a filer whose total tag stays current keeps the authoritative total, so a filer reporting both is never double-counted. Only 10-Q/10-K facts feed it. (2) `LiabilitiesAndStockholdersEquity` joins the TOTAL_ASSETS CONCEPTS chain as a tail fallback: a 10-Q can carry the balance-sheet total without the standalone Assets tag (Lennar's Q3 2026 10-Q files no Assets/Liabilities facts at all), and the total is definitionally Assets — gap-fills only ends the primary tag lacks, never overriding a filed Assets value; the derivation then recovers Liabilities = Assets − Equity.

**Why:** two real data defects on fresh tickers. (1) Delta's 2026 10-Qs kept filing the two capex components while the total tag stopped at Q1 2026 — the winner-take-all chain would have blanked capex and FCF for every recent quarter. The naive alternative (appending the flight tag to the chain) was rejected on measured evidence: DAL Q3 2026 flight-only $1.20B vs true $1.41B understates capex ~15% and overstates FCF by 70%+. (2) Lennar's newest 10-Q left the latest quarter's balance sheet showing "—" on total assets and liabilities — the exact fields the bank/insurer P/B path needs. Both fixes inherit every prior freshness/never-raise rule because they reuse the existing quarterly machinery.

**Detection boundary / honesty boundaries:** the composite is invisible to filers without flight-equipment facts (returns [], generic chain runs) and to filers whose total tag stays current (dispatch guard). An 8-K-tagged flight payment cannot leak into capex. The Assets fallback cannot override a filed Assets value, and it adds a tag that is true by accounting identity — no judgment call, so no new honesty class. Blast radius by construction: exactly filers carrying the newer flight tag (DAL verified live; UAL/AAL/LUV checked live — no flight-tag facts, generic chain authoritative, byte-identical behavior); exactly quarters where the standalone Assets tag is absent (LEN Q3 2026 — identity A=L+E holds to the dollar).

**Alternatives considered:** tag-appending instead of summing (rejected — the 15% capex understatement is measured, not theoretical); treating the split as a new chain candidate (rejected — winner-take-all would pick flight-only for new quarters and repeat the understatement). For Assets: deriving Assets = Liabilities + Equity (rejected — Lennar's filing lacks Liabilities too, so the direction that has a filed total is the only viable one).

**Follow-ups (not this batch):** risk-factor backfill (self-heals on page views via `enrich_company`); SPG dominant-quarter self-heal (Q4-2026 filing).

## Batch 74 (2026-10-15): hyper-growth reroute to the sales fallback — restoring real signals

**Decision:** the batch-62 hyper-growth guard (TTM EPS growth above the 40% model maximum → Watch/unavailable) no longer returns Watch. `compute_valuation` now sets a `hyper_growth` flag; the PEG path is skipped for these names (`and not hyper_growth` on the PEG condition) and they fall through to the margin-anchored sales fallback, which prices *revenue* growth through the same fair-P/S machinery (fair P/S = fair P/E × TTM net margin, growth clamped at 40%, P/S capped at 10×, batch-12 rate guardrail). The fallback's opening bullet is hyper-growth-specific — "TTM EPS growth of X% is outside the PEG model's 40% design range — a growth multiple on that base would be clamped fiction, so valuing on sales instead (less reliable)" — because the batch-33 "no per-share earnings" line would be false (EPS exists; only the growth input is unreliable). The `growth_pct` shown is revenue growth, the input actually used. Names the fallback cannot price keep their honest Watch copies: negative-margin hyper-growth via the margin guard (INTC, TEAM, TTWO, PLUG), missing revenue inputs via the nothing-usable Watch.

**Why:** the DB-wide audit showed 38 of the 51 Watch companies were the hyper-growth cohort — including NVDA, GOOGL, AMZN, AVGO, LLY, AMD, PLTR, DUOL, MU — the user's most-watched names, all showing no signal. Batches 70–72 established the pattern: guard first, then restore real signals for the cohort (banks/insurers → P/B, REITs → P/FFO). Hyper-growth's sector-native alternative is the sales fallback: revenue growth is the more durable input (BMY's 83.5% EPS growth on 3.1% revenue growth is a snapback; GEV's 741.7% EPS growth on 13% revenue growth likewise), and every binding guardrail on that path already names itself with Medium confidence (batches 40/45).

**Detection boundary / honesty boundaries:** the reroute only fires when `eps_growth_pct > 40` (strictly — 40.0 keeps the PEG path); REITs and banks/insurers keep their sector branches (placed before); the margin guard keeps margin-absurdity cases (AGNC/NLY) and negative-margin hyper-growth on Watch. Blast radius by git-stash A/B over all 186 companies: exactly the 33 hyper-growth names with usable sales inputs change (51→18 Watch); the other 153 are byte-identical. The two most extreme new signals are the margin anchor working as designed, not fabrication: CRWD Strong Sell −99.2% (52.2× current P/S on 1.1% TTM net margin) and PLTR Strong Sell −86.8% (75.8× sales) — both name the margin×P/E identity and carry Medium confidence. MU Buy +19.0% replaces the batch-62 +167% fabrication exhibit with both guardrails (40% growth clamp, 10× P/S cap) named. During the audit a suspected MU data defect ($54.2B quarterly revenue) was verified real against Micron's 2026-09-30 press release and raw SEC companyfacts — Micron files proper quarterly-duration facts; no pipeline change needed.

**Alternatives considered:** keeping Watch for hyper-growth (rejected — 38 marquee names with no signal is the largest remaining honesty gap, and the sales machinery already handles every guardrail honestly); a two-stage growth-fade model (rejected — judgment-laden, more fabrication surface than the existing clamped machinery); dropping the 10× P/S cap for the reroute (rejected — the cap is the model's documented conservatism and names itself; NVDA Strong Sell −47.6% is cap-driven but disclosed, Medium confidence).

**Follow-ups (not this batch):** risk-factor backfill (self-heals on page views via `enrich_company`); SPG dominant-quarter self-heal (Q4-2026 filing).

## Batch 75 (2026-10-15): risk-factor backfill + Item 1A extractor defects — closing the follow-up carried since batch 62

**Decision:** fix the extractor instead of just backfilling around it, then backfill. Three defect classes found by probing all 83 companies missing risk_factors: (1) `_html_to_text` replaced every tag with a space, so words split across inline `<span>`s ("RIS</span><span>K FACTORS" in DFIN 10-Ks) linearized to "RIS K FACTORS" and the start regex missed the real heading — only the TOC stub matched → None. Inline formatting tags are now stripped with no inserted space (browser-faithful; block-level separation unchanged). (2) The heading separator class lacked the em dash — Dell's "ITEM 1A — RISK FACTORS" never matched. (3) No fallback for filers that head the section with a bare "RISK FACTORS" line and no "Item 1A" prefix (McDonald's, Citi) — added, guarded two ways: exactly one standalone all-caps line (Honeywell's running page headers would misfire otherwise) and no primary candidate reaching 50 chars (so BNY/WFC's incorporation-by-reference stubs are never second-guessed — a matched real heading with a short section is an honest None). New `scripts/backfill_risk_factors.py` (never-wipe, never-raise, polite pacing) rescued 74/83; DB at 177/186 with Item 1A risk factors, which also upgrades AI-analysis risk bullets from generic sector fallbacks to company-specific prose.

**Why:** the carried follow-up claimed this "self-heals on page views via enrich_company" — verified false (enrich_company runs only on first fetch), so the gap sat at 83 companies for 13 batches. The span-split defect alone blocked MSFT, BRK.B and most DFIN-prepared large filers — the highest-value single fix available. The 9 remaining Nones are all honest: BNY/WFC incorporate Item 1A by reference (prose not in the 10-K), GE/HAL/HON/ICE/INTC/MS use heading formats no confident matcher covers, XOM's holding-company registrant (CIK 0002115436 — verified correct, not a data defect) hasn't filed a 10-K yet.

**Detection boundary / honesty boundaries:** the 500-char floor and longest-section-wins logic are untouched; the fallback only fires under the two guards above. SCHW's 711-char extraction was audited (suspected truncation) — genuine: Schwab's Item 1A ends mid-sentence with "see Item 1C. Cybersecurity", which the end marker correctly bounds.

**Alternatives considered:** a TOC page-number-anchored extraction for heading-less sections (rejected — filer page-footer formats vary too much, high garbage risk); rescuing GE/HAL/HON/ICE/INTC/MS individually (rejected for this batch — 6 heterogeneous heading formats, each a forensics project; honest Nones degrade gracefully via the None-safe disclosure macro and sector-generic AI risks).

**Follow-ups (not this batch):** GE/HAL/HON/ICE/INTC/MS heading forensics; XOM self-heal on first 10-K; SPG dominant-quarter self-heal (Q4-2026 filing); serve-stale-on-error for company_tickers.json after this batch's incident (server 500'd/stalled ~10 min when the disk cache expired and the live re-fetch timed out through the proxy — the never-raise pattern doesn't cover cik_for_ticker's live fetch; recovered on cache re-warm, no data impact).

## Batch 76 (2026-10-16): serve-stale-on-error for the EDGAR disk cache — closing the batch-75 incident follow-up

**Decision:** `EdgarClient.fetch_json` / `fetch_text` now serve the stale on-disk snapshot when the live fetch fails (timeout, connection error, non-2xx) instead of raising, plus a 5-minute per-URL failure cooldown (`FAILURE_COOLDOWN_SECONDS`) that skips re-attempting a just-failed live fetch and serves stale immediately. The incident that motivated it: when `.edgar_cache`'s company_tickers.json expired its 6h TTL, every request blocked on a 30s proxy timeout in series (~10 min stall) and then 500'd — search, `cik_for_ticker` (every company route), and peers all depend on that file. A hours-old ticker→CIK map resolves CIKs fine; a stale filing doc is identical content (filing URLs are immutable), so staleness here is safe. With no cache on disk at all (cold first boot), the exception still propagates — honest failure, no silent empty data.

**Why:** this was the last structural gap in the app's never-raise pattern — the one the batch-75 incident exposed. The two-layer design separates the concerns: the except-branch converts a hard failure into a graceful stale serve (kills the 500s), and the cooldown converts the recovery path from "30s timeout per request until SEC is reachable again" to "one failed attempt, then instant stale serves for 5 minutes" (kills the stall). Success clears the failure record, so the live fetch is retried as soon as the cooldown lapses — no manual re-warm needed.

**Detection boundary / honesty boundaries:** `fresh=True` freshness-trigger calls (`submissions`/`companyfacts` with `max_age_seconds=0`) also go through this path: on failure they now return the existing snapshot instead of raising, so the caller concludes "no new filings" — the safe, honest answer under a connectivity outage, consistent with the never-raise posture. Cooldown state is per-process memory; multi-worker deploys would each keep their own, which only affects how quickly each retries live.

**Alternatives considered:** extending company_tickers.json's TTL (rejected — the failure mode is "SEC unreachable", not "TTL too short"; any TTL eventually expires); a global circuit-breaker (rejected — per-URL failure records are more precise and self-clear; a global breaker would stall all endpoints for one URL's outage).

**Follow-ups (not this batch):** GE/HAL/HON/ICE/INTC/MS heading forensics; XOM self-heal on first 10-K; SPG dominant-quarter self-heal (Q4-2026 filing).

## Batch 77 (2026-10-16): Item 1A heading forensics — rescuing GE/HAL/HON/ICE/INTC/MS

**Decision:** close the last carried batch-75 follow-up by teaching `extract_risk_factors` the four heading shapes the six deferred tickers actually use, each verified against the real 10-K HTML. (1) Legacy parenthesized numbering — Halliburton's `Item 1(a). Risk Factors.` and ICE's `ITEM 1(A). RISK FACTORS` — as a full-line-anchored primary alternative with horizontal-whitespace-only between tokens, plus a `1(b)` end-marker alternative (ICE writes `ITEM 1 (B).` with a space). (2) Bare title-case `Risk Factors` fallback candidates (Intel, Morgan Stanley) with a prose-follow viability check: a standalone heading line only counts when its next non-blank line is ≥ 20 chars, which excludes TOC entries and running page headers (followed by page numbers / item labels). (3) Run-in `RISK FACTORS.` headings carrying prose on the same line (GE Aerospace). (4) Longest-section-wins across all viable fallback candidates instead of the old exactly-one-caps-line rule — Honeywell's 10 running `RISK FACTORS` page headers yield shorter sections than the real (earliest) heading, so the real one wins.

**Why:** batch 75 deferred these as "6 heterogeneous heading formats, each a forensics project" — the forensics showed they collapse to 4 shapes, all matchable without weakening the honesty guards. The full-line anchoring for the legacy alternative is load-bearing, not cosmetic: Halliburton's doc contains a TOC split (`Item 1(a).` / `Risk Factors` on separate lines) and a mid-sentence cross-reference (`see Part I, Item\n1(a). Risk Factors`) that an unanchored pattern would match, and longest-section-wins would then prefer the wrong (longer, earlier) candidate. The prose-follow check is the same idea for the title-case fallback: without it, Intel/Morgan Stanley's TOC `Risk Factors` + page-number entries would produce whole-document sections and win longest.

**Detection boundary / honesty boundaries:** the 500-char floor, the longest-section-wins primary logic, and the incorporation-by-reference guard (primary candidate ≥ 50 chars blocks the fallback — BNY/WFC still honestly None) are untouched. A real heading followed by a < 20-char intro line would be missed (safe direction: honest None, graceful degradation). XOM still has no 10-K (holding-company registrant) — None until its first filing, then it self-heals via the normal path.

**Alternatives considered:** per-ticker special-casing (rejected — the four shapes are general filer conventions, not ticker quirks; the regexes will serve future seeds); excluding running headers by page-footer patterns (rejected — footer formats are filer-specific, e.g. `30 Honeywell International Inc.` vs `HAL 2025 FORM 10-K | 20`, while longest-section-wins is structural); a TOC page-number-anchored extraction (rejected back in batch 75, still rejected — high garbage risk).

**Follow-ups (not this batch):** XOM self-heal on first 10-K; SPG dominant-quarter self-heal (Q4-2026 filing).

## Batch 78 (2026-10-16): NI/shares EPS derivation for annual-only EPS filers (GD)

**Decision:** add `_eps_from_income_shares` as a final gap-fill in `quarterly_income_metric` for EPS_BASIC/EPS_DILUTED: when a filer tags no quarterly EPS facts, derive quarterly EPS = quarterly net income / quarterly weighted-average shares for the same period end; Q4 (whose quarterly share count the 10-K doesn't tag) uses the share-month residual (12·FY_avg − 9·9M_avg)/3. Filed EPS facts always win via skip_ends; the derivation is skipped for two-class filers (reuses the batch-66 `_has_distributed_eps_facts` guard); it yields nothing when no share facts exist.

**Why:** the round-22 hunt found General Dynamics with all 8 quarters EPS-less — its 10-Qs haven't tagged quarterly EPS since 2019, only the 10-K annual fact. NI/shares is definitionally total EPS for the period (unlike the batch-65 Q4 path, which must infer shares from NI/EPS pairs), so no coherence check is needed; the two-class guard is the one case where the identity breaks (participating-securities allocation). V (no EPS concept in companyfacts — extension taxonomy) and BRK.B (nothing tagged since 2013) stay honestly blank, which the tests pin. The derivation also future-proofs the chain: any filer with the GD shape now seeds with complete EPS.

**Detection boundary / honesty boundaries:** derivation only fills ends the chain lacks; source_tag is `Derived:<shares tag>/NetIncomeLoss` so derived values are traceable in the DB; the Q4 residual requires positive implied shares and start-matched annual/9M share facts, else the quarter stays blank (fail closed). Loss quarters are fine (negative NI over the filed share count). Per-share facts need no split adjustment here — numerator and denominator are period-consistent, so the ratio is basis-correct under restatement.

**Alternatives considered:** storing the annual EPS fact on the Q4 row (rejected — would misread as quarterly EPS); extending the continuing-ops fallback (rejected — GD's 10-Qs tag no per-share facts at all, nothing to extend); leaving the quarters blank (rejected — the exact inputs sit in the same filings, and blank EPS degrades the valuation card to unavailable).

**Follow-ups (not this batch):** XOM self-heal on first 10-K; SPG dominant-quarter self-heal (Q4-2026 filing); V/BRK.B EPS unfixable from companyfacts (extension taxonomy / abandoned tagging — recheck only if their tagging resumes).

**Follow-ups (not this batch):** XOM self-heal on first 10-K; SPG dominant-quarter self-heal (Q4-2026 filing).

## Batch 79 (2026-10-16): fresh-ticker hunt round 25 — GIS/MKC/SJM/CLX/CPB/TSN seeded, clean audit

**Seeds:** 6 new tickers live from SEC, 8 quarters each, clean FY sequences (GIS May FY; MKC Nov FY; SJM Apr FY; CLX Jun FY; CPB Jul FY; TSN Sep FY). Balance-sheet identities hold on all 48 quarters. Descriptions present for all 6, no pending-filing notes, EPS complete on every row. DB at 197.

**Decision:** no code change — the round found nothing to fix. This is a deliberate outcome, not a gap: the three suspicious quarters were each verified against raw companyfacts and proved genuine, which is exactly what the audit is for (batch-45/69 precedent). Recording the forensics keeps the pattern reusable.

**Why the audit went deep on these three:**
- MKC FY2026Q1 EPS $3.77 against otherwise ~$0.4–0.8 quarters: the filed 10-Q fact for end 2026-02-28 is 3.77, and NI $1,016.2M / 269.4M diluted shares = 3.77 — coherent, a real one-off gain quarter.
- GIS FY2026Q4 EPS −$3.74: the 10-K tags TWO EPS facts for end 2026-05-31 — −$0.16 with frame=CY2025 (the FY2026 annual fact) and −$3.74 with frame=CY2026Q2 (the Q4 quarter fact). Frame-aware selection chose the quarterly fact; the four FY2026 quarters sum to the filed annual NI −$87.6M to the dollar. The dual-frame shape is the pipeline's home turf (batch-51/61) and it held.
- SJM FY2026Q3 EPS −$6.79: two NI facts for end 2026-01-31 — −$526.8M with start 2025-05-01 (9M YTD) and −$724.2M with start 2025-11-01 (the 3-month quarter). The quarter-length fact was chosen; stored Q1+Q2+Q3 NI sums to the filed 9M −$526.8M exactly. The −$6.79 quarter is a genuine impairment quarter (same shape as SJM's FY2025Q3/Q4 −$6.22/−$6.84 rows).

**Benign warnings, pinned for the record:** TSN's seed log said "No XBRL facts for total_liabilities" and "No XBRL facts for eps_basic". Neither is a defect. Tyson tags no plain `Liabilities` concept at all (only granular ones); the composite chain (Current + Noncurrent) derives liabilities at a 0.000% identity gap — the warning is `_safe` noise before the composite fill. eps_basic is filled from diluted EPS by the designed `_fill_missing_eps_basic` path (documented whole-chain selection), not fabricated. No action.

**Detection boundary / honesty boundaries:** unchanged. Valuation outputs on the new seeds were spot-checked rather than assumed: CPB's Strong Sell is genuine (TTM diluted EPS $1.36, −32.3% YoY → 8× floor, rationale discloses the guardrail hit and caps confidence at Medium); GIS's Watch/UNAVAILABLE is the batch-62 design-envelope guard behaving as designed.

**Alternatives considered:** inventing a code task to fill the batch (rejected — the loop's rule: if a batch finds nothing to improve, say so); re-running the dual-frame forensics as a unit test (rejected — the shapes are already covered by the batch-51/61/78 frame-selection tests; these are data confirmations, not code paths).

**Follow-ups (not this batch):** XOM self-heal on first 10-K; SPG dominant-quarter self-heal (Q4-2026 filing); V/BRK.B EPS unfixable from companyfacts (extension taxonomy / abandoned tagging — recheck only if tagging resumes).

## Batch 80 (2026-10-17): fresh-ticker hunt round 26 — EL/CL/KVUE/ECL/DD/APD; split-basis defect + Wikipedia diacritic defect + dotted Item 1A defect

**Seeds:** 6 new tickers live from SEC, 8 rows each, clean FY sequences (EL Jun-FY 2025Q1–2026Q4; APD Sep-FY 2024Q4–2026Q3; rest Dec-FY 2024Q3–2026Q2). Balance-sheet identities hold on all 48 quarters; no suspicious quarters, no blank EPS/revenue, descriptions present on 5/6 (EL rescued — see below). DB at 203.

**Defect 1 — DD mixed-basis EPS series (the find):** DuPont did a 1-for-3 reverse split effective ~Jul 2026 (diluted shares 419.7M → 139.9M; the 2026-08-04 10-Q restated comparatives ×3.0). The batch-51 `_is_pre_split_basis` EPS-neighborhood heuristic cannot classify a pre-split fact whose value overlaps the post-split range — 2026Q1's 0.39 sits nearer post-split 0.42 than rescaled 1.17 sits to 1.05 — so it left 6 of 8 quarters on the old basis (stored: 1.08, −0.28, −1.4, 0.42, −0.29, −0.3, 0.39, 1.05), the exact mixed-basis corruption batch 51 declared a correctness invariant. Verified against raw companyfacts per the batch-45 lesson: the 3.0x restatement is genuine (share counts prove the split); the stored 0.39/−0.3/−1.4 are old-basis.

**Fix 1:** filing-level share-basis classification in `data/xbrl.py`. New `_split_share_restatements` (share-count restatements at the inverse ratio give old/new levels per restating filing), `_filing_share_basis` (a pre-restating filing whose latest-period share count sits near the new level is post-split, near the old level pre-split; ±25% tolerance — splits move counts ≥2x, buyback drift stays far below), `_split_basis_share_facts` (best-effort share-fact fetch). `_is_pre_split_basis` takes a known filing basis as decisive and keeps the neighborhood heuristic only for unknown filings (no share facts — all hermetic NFLX-shape tests preserved). The share restatement need not ride in the same filing as the EPS restatement (NOW's 5-for-1: EPS restated in the 2026-01-29 10-K, shares in the 2026-07-23 10-Q), so the match is by inverse-ratio scale within 400 days, closest date winning. DD re-seeded: 3.24, −0.84, −4.20, 0.42, −0.87, −0.90, 1.17, 1.05 — NI/shares coherent (2026Q1 $0.16B/137.6M ≈ $1.16 ✓).

**Defect 2 — false-positive split event on the continuing-ops annual-fallback list (latent):** DD's 2026 10-K halved continuing-ops EPS when Qnity moved to discontinued operations; the fallback list's independent event detection read that 0.50x/0.49x reclassification as a 2:1 split (2 corroborating groups). It didn't corrupt DD's stored data (the fallback only fires when the primary tag lacks annual facts, and DD's primary has them), but for a Halliburton-shaped filer with a coincidental reclassification ratio it would rescale annual facts wrongly. **Fix:** split events are detected once on the primary (total-EPS) chain and shared with the fallback list (`_split_adjust_facts(..., events=..., share_facts=...)`); the fallback never detects independently. A real split always restates the primary tag's comparatives, so sharing loses no detection.

**DB-wide split sweep:** re-extracted the EPS series with the fixed pipeline for all 11 tickers with recent (≥2023) split events and diffed against stored: 10 identical; **NOW differed** — ServiceNow's real 5-for-1 split (shares 209M → 1,047M) left 2024Q3/2025Q3 on the old basis (2.09/2.07, 2.42/2.40) while the rest were new-basis. NOW re-seeded: 0.419, 0.365, 0.44, 0.37, 0.485, 0.387, 0.45, 0.29, fully consistent.

**Defect 3 — Wikipedia diacritic blind spot (EL description-less):** "ESTEE LAUDER COMPANIES INC" reached the right article ("Estée Lauder Companies", top hit) but every relevance path rejected it on the é — first-word agreement, lead-word fallback, and the suffix-stripped fallback's word-set equality. **Fix** `data/wikipedia.py`: new `_fold()` (NFKD + combining-mark strip) applied in `_normalize_words`, `_word_set`, `_squashed`. Cannot misattribute: it only makes already-identical words compare equal; all agreement/equality structure unchanged. EL backfilled via the seed-time enrichment path; only AGNC/APLD/MPLX remain description-less (honest blanks — no articles exist, batch-58).

**Defect 4 — dotted "ITEM 1.A." heading (CLX risk factors):** Clorox's 10-K heads Item 1A as "ITEM 1.A. RISK FACTORS" (standalone line), a shape the batch-75/77 forensics didn't cover — extractor returned None. **Fix** `data/filings.py`: dotted alternative added to `_RISK_START_RE` as a full-line-anchored variant (same cross-reference-stealing rationale as the legacy parenthesized form), plus dotted 1.B/1.C/2 end markers. CLX rescued (7,998 chars). BNY stays honestly None — its 10-K incorporates Item 1A by reference (WFC class, batch-75). Risk-factor backfill for rounds 22/25/26: 16 rescued, 4 honest Nones (BNY/WFC/XOM + CLX now filled).

**Tests:** 4 new wikipedia tests (diacritic relevance/strict/primitives/best-title); 4 new xbrl tests (DD-shaped share-basis rescale, post-split-filing positive ID, fallback event sharing, NOW-shaped later-filing share restatement); 2 new filings tests (dotted 1.A heading + cross-reference trap, TOC split-lines trap). Suite 712 green, `git diff --check` clean. Live on :8123 (server restarted for the new code): 13/13 routes 200 (6 new overviews + DD/NOW/CLX detail + DD vs APD + calendar + home); EL description and CLX risk factors render; DD/NOW valuation cards honest on the repaired series (DD Strong Sell via the disclosed sales fallback).

**Blast radius:** `data/xbrl.py` (split helpers + one call site), `data/wikipedia.py` (fold in 3 primitives), `data/filings.py` (2 regexes), tests. No valuation, briefing, peers, calendar, or template changes.

**Alternatives considered:** fixing DD by hand-editing stored rows (rejected — the heuristic defect would recur on the next split filer; the sweep proved it already had with NOW); a DBA alias for EL (rejected — the legal name reaches the right article, the checker just couldn't see through the accent; the general fix covers all accented filers); leaving the fallback's independent detection (rejected — the 0.5x fabrication is a real false-positive class).

**Follow-ups (not this batch):** XOM self-heal on first 10-K; SPG dominant-quarter self-heal (Q4-2026 filing); V/BRK.B EPS unfixable from companyfacts (extension taxonomy / abandoned tagging — recheck only if tagging resumes).

## Batch 81 (2026-10-17) — round-27 clean audit; no code change

**Seeds:** CSCO, CMCSA, CVS, AEP, AON, CCL — all 8 quarters, clean. DB at 209 companies.

**Finding:** Deep audit surfaced zero defect classes. Every suspicious value verified against raw companyfacts (CIK-level) as the filer's own number: CMCSA's $11.123B Q2-2025 NI, CVS's −$3.975B Q3-2025 NI, CSCO's NI/shares-derived Q4-FY2026 EPS 0.9703 (batch-78 path working correctly on a new annual-only filer), AON's 7.83 quarter correctly taking the finance P/B composite (not the EPS-growth guard path).

**Decision:** No code change this batch (per the standing rule: never invent work when the audit is clean). The batch-55 amber pending-filing note is doing its job for AEP (Q2 FY2026 filed Jul 30, 2026, still not in companyfacts) and the 12-ticker cohort behind it.

**Carried follow-ups rechecked:** XOM self-heal (blocked on FY2026 10-K, ~Feb 2027 — companyfacts NI frames still end CY2026Q1); V/BRK.B quarterly EPS tagging still not resumed; SPG dominant-quarter self-heal waits on the Q4-2026 filing.

**Tests:** none added; suite 712 green. **Blast radius:** none (docs + validation log only). No template change.

## Batch 82 (2026-10-17) — round-28 seeds; seed-time pending-filing note fix

**Seeds:** ABT, AFL, ANET, COR, HLT, MPC — all 8 quarters, clean. DB at 215 companies.

**Finding:** Deep audit surfaced zero XBRL data defects but one real pipeline gap. Every suspicious value verified against raw companyfacts (CIK-level) as the filer's own number: MPC Q2-2026 EPS 17.73 (own 10-Q fact, one-time gain); COR Q2-FY2026 EPS 8.40 (own 10-Q fact; Cencora's lumpy GAAP quarters are filer-real); COR's absent `Liabilities` tag is correctly covered by `_derive_missing_balance_sheet` (stored A = L + E exactly); ANET's Dec-2024 4:1 split rescaled exactly once (2.33 → 0.58 restated), confirming the batch-80 share-basis classification on a new real filer.

**Defect — seed-time pending-filing note missing:** ABT's Q2-FY2026 10-Q was filed 2026-07-28 but companyfacts has no Q2 facts yet (EDGAR ingestion lag, ~2.5 months by design), so the quarter is legitimately absent — yet `fetch_and_persist` never called `_update_pending_filing_note`, leaving the freshly seeded company with no amber honesty note until a page view ran the freshness check. The batch-53 refresh path had the note; the seed path didn't.

**Fix:** `fetch_and_persist` now calls `self._update_pending_filing_note(ticker, cik, submissions)` after the seed commit — mirrors the refresh path, never raises, reuses the just-warmed companyfacts cache. ABT re-seeded live: note renders on the overview page ("Q2 FY2026 results (10-Q filed Jul 28, 2026) aren't in EDGAR's data feed yet — showing Q1 FY2026…").

**Tests:** 2 new hermetic tests in `tests/services/test_pending_filing_note.py` (ABT-shaped seed sets the note; current seed leaves it clear); new test verified to fail pre-fix. `test_fetch_and_persist_pull_uses_live_edgar` updated to `assert_any_call(fresh=True)` — the seed-time note re-reads the warmed TTL cache after the deliberate fresh pull; the "deliberate pull bypasses cache" intent is unchanged. Suite 714 green, `git diff --check` clean. Live on :8123 (no restart needed — backend-only, no template change): 8/8 routes 200.

**Blast radius:** `src/tickerlens/services/financials.py` (one call in `fetch_and_persist`), tests. No valuation, briefing, peers, calendar, or template changes.

**Carried follow-ups rechecked:** XOM self-heal still pending (companyfacts NI frames end CY2026Q1; heals on FY2026 10-K, Feb 2027); V/BRK.B quarterly EPS tagging not resumed (still unfixable from the feed); SPG dominant-quarter self-heal waits on Q4-2026 filing; pending-filing cohort at 14 (prior 13 + ABT now honestly noted).

## Batch 83 (2026-10-17) — round-29 seeds; parent-temporary-equity mezzanine extraction

**Seeds:** CTVA, DG, KDP, PCAR, RSG, TDG — all 8 quarters, clean. DB at 221 companies.

**Finding:** Deep audit surfaced one real defect class. KDP's Q1/Q2 FY2026 balance sheets had an identity gap of exactly **$4.418B** both quarters (5–6%). Forensics against raw companyfacts (CIK-verified): `us-gaap:TemporaryEquityCarryingAmountAttributableToParent` = $4.418B — convertible preferred stock KDP issued in Q1 FY2026 to finance the JDE Peet's acquisition ($4.5B liquidation preference). Mezzanine equity (between liabilities and permanent equity, part of neither), and the batch-59 mezzanine pipeline never extracted this tag family — it only knew `RedeemableNoncontrollingInterestEquityCarryingAmount`. Every suspicious EPS on the other five tickers verified as filer-real (CTVA seasonal H2 losses; TDG quarter-length facts).

**Fix:** new `Metric.TEMPORARY_EQUITY` extracted per quarter as an instant balance-sheet metric → new nullable `quarterly_financials.temporary_equity` column (auto-migrated by `ensure_schema()`; backfilled DB-wide from cached companyfacts: 7 companies, 39 rows — KDP's 2 quarters; MPLX's $203M temp equity on FY2024Q3/Q4, which the gate correctly shows as a third leg on those two historical quarters only). `_reconcile_balance_sheet_identity` and `_derive_missing_balance_sheet` now sum both mezzanine legs; a conditional "Temporary equity (mezzanine)" row renders on the detail balance-sheet table, range table, compare, tearsheet trends matrix, and CSV exports — under the same third-leg gate as redeemable NCI, so filers whose equity already includes the line (the batch-60 double-count shape) stay hidden. KDP's sheet now closes to the dollar and the row renders at $4.42B.

**Tests:** 13 new (8 hermetic extraction/derivation incl. a both-legs-sum case, 4 third-leg gate incl. both-legs coexistence, 1 schema-migration). `test_compare_yearly_passes_mode_and_years` mock updated for the new `deltas.temporary_equity` field. Suite 727 green, `git diff --check` clean. Styled screenshot verified before commit (screenshot gate): the new row matches the existing table styling exactly — strictly-better data fix, no redesign.

**Blast radius:** `data/xbrl.py` (new metric + two-leg identity math), `models/quarterly_financial.py` (column + `temporary_equity_is_third_leg` property), `services/financials.py` (BalanceSheet/BalanceSheetChange/CompareDeltas fields, gated row in 5 surfaces, persistence upsert), 3 templates (one conditional row each). No valuation, briefing, peers, calendar, or styling changes.

**Carried follow-ups rechecked:** XOM self-heal still pending (FY2026 10-K, ~Feb 2027); SPG dominant-quarter self-heal waits on the Q4-2026 filing; V/BRK.B quarterly EPS tagging not resumed (still unfixable); pending-filing cohort at 14 (EDGAR ~2.5-month companyfacts lag, by design — ABT's seed-time note from batch 82 renders correctly).

## Batch 84 (2026-10-17) — round-30 seeds; forward-split share-restatement fix; spaced state-tag description fix

**Seeds:** LRCX, KLAC, ADI, REGN, VRTX, BSX — all 8 quarters, clean. DB at 227 companies.

**Finding:** Deep audit surfaced two real defect classes. (1) KLAC's FY2026Q4 diluted EPS showed $1.0312 (post-split basis, from the 2026-08-06 10-K) while FY2026Q1–Q3 showed $8.47/$8.68/$9.12 (pre-split 10-Q facts) — a mixed-basis series 10x off. Forensics against raw companyfacts (CIK-verified): KLAC's 10-K restated FY2024/FY2025 annual EPS and share comparatives at 0.1001x / 10x (genuine 10:1 split, Aug 2026); the 10-K tags no quarterly EPS or share comparatives in XBRL. The batch-80 filing share-basis machinery was defeated two ways: `_split_share_restatements` only accepted the reverse-split direction (share ratio 1/r), so the 133.75M → 1,337.5M forward restatement was never found and the filing-basis map stayed empty; and the neighborhood heuristic had no quarterly post-split reference to judge by, so it conservatively left the quarters alone. The 9M YTD fact did rescale (annual references existed), which is how Q4 derived correctly at 1.03 while Q1–Q3 stayed wrong. (2) VRTX had no Wikipedia description: EDGAR's name form "VERTEX PHARMACEUTICALS INC / MA" (space after the slash) defeated `_strip_corp_suffix`'s state-tag regex, so the suffix-stripped fallback query never fired and the poisoned primary search returned junk.

**Fix:** `data/xbrl.py` — `_split_share_restatements` now accepts both ratio directions (r for forward splits, 1/r for reverse); the per-share event match (inverse scale within tolerance, 400-day window, independently corroborated event) still guards against false positives, so a lone share-count jump can never fabricate a split. `data/wikipedia.py` — `_strip_corp_suffix` regex now allows whitespace between the slash and state code (`\s*/\s*[A-Z]{2}/?\s*$`). KLAC re-seeded live: all 8 quarters on the post-split basis; DD re-seeded as a regression check (byte-identical series); VRTX description backfilled live.

**Tests:** 2 new in `tests/data/test_xbrl.py` (KLAC-shaped forward share restatement detected at 10x; end-to-end KLAC mirror — quarterly pre-split facts with no quarterly post-split XBRL reference rescale via the share basis, verified to fail pre-fix), 1 new assert in `tests/data/test_wikipedia.py` (spaced state tag). Suite 729 green, `git diff --check` clean. Live on :8123 (restarted): 6/6 routes 200; KLAC detail HTML carries the repaired series, VRTX overview the description. No template change — screenshot gate N/A.

**Blast radius:** `data/xbrl.py` (one ratio condition + docstring), `data/wikipedia.py` (one regex + docstring), tests. No valuation, briefing, peers, calendar, template, or schema changes.

**Carried follow-ups rechecked:** XOM self-heal still pending (FY2026 10-K, ~Feb 2027); SPG dominant-quarter self-heal waits on the Q4-2026 filing; V/BRK.B quarterly EPS tagging not resumed (still unfixable); pending-filing cohort at 14 (EDGAR ~2.5-month companyfacts lag, by design).

## 2026-10-17 — Batch 85: discontinued-ops basis-break guard for Q4 derivation + ticker-titled Wikipedia articles

**What:** (1) New `_discontinued_basis_break_starts(companyfacts)` in `data/xbrl.py`: returns FY start dates where the 10-K reclassified a component to discontinued ops after the last 10-Q — detected when a 10-Q tags the 9M `IncomeLossFromDiscontinuedOperationsNetOfTax` (or sibling tags) as 0 but the 10-K tags the FY nonzero. `_derive_q4_income`, `_cash_flow_series_for_tag`, and the four finance revenue composites (`_finance_total_revenue`, `_bdc_quarterly_revenue`, `_bank_quarterly_revenue`, `_mreit_quarterly_revenue`) skip Q4 derivation for those FYs. (2) `_best_title`'s suffix-stripped fallback now also accepts the article titled exactly the ticker (e.g. "TJX" for TJX Companies, Inc.), guarded by relevance rule 1 (acronym pages) with disambiguation rejected at extract time.
**Why:** Batch-85 seed forensics found OXY FY2025Q4 revenue at $1.75B vs ~$5.4B real (Zacks: Q4 $5.42B, FY $22.08B): the Q3-2025 10-Q's 9M Revenues ($19.84B) still included OxyChem while the 2025 10-K's FY Revenues ($21.59B) excludes it (10-K: OxyChem "reported separately as discontinued operations ... for all periods presented"; 9M discontinued tagged 0 in the 10-Q, $262M in the 10-K), so FY − 9M mixed two bases. A missing Q4 is honest; a mixed-basis Q4 is a fabrication — and the strict-TTM machinery already renders the gap as Watch/Low-confidence with no target instead of a silently wrong sum. TJX had no description because Wikipedia titles its article "TJX" and the strict name match could never accept it.
**Alternatives considered:** A materiality floor on the discontinued amount (rejected for now — the corruption equals the discontinued component's 9M amount, which companyfacts cannot supply, so any proven break abstains; the D FY2025 edge case — a -$14M Q4 true-up tripping the detector — is documented but harmless in practice since D's 10-K filed a quarterly Q4 stub and derivation never fired); deriving the correct continuing Q4 from restated comparatives (rejected — the continuing 9M is not in companyfacts; the 2026 10-Qs' restated 2025 comparatives exist but relying on future filings is fragile); a run-rate sanity band on derived Q4s (rejected — legitimate seasonality/divestitures would false-positive; the tag-pattern proof is exact).
**Blast radius:** `data/xbrl.py` (one new helper + param threading through 7 call sites; no valuation, briefing, peers, calendar, template, or schema changes), `data/wikipedia.py` (fallback acceptance rule + docstring). 6 new tests (4 xbrl: detector unit, ongoing-discontinued-ops negative, end-to-end income skip + control, cash-flow skip; 2 wikipedia: ticker-title acceptance + near-match rejection). Suite at 735 green (729 + 6). `git diff --check` clean. DB-wide scan: 233 companies, 19 with historical breaks — all pre-2024 except OXY FY2025 (fixed live: Q4 income fields NULLed, balance sheet kept) and D FY2025 (10-K filed a Q4 stub, derivation never fired, no action).
**Live:** Server restarted via the launcher script (kill by explicit PID). 6/6 routes 200; OXY detail no longer shows the bogus $1.75B (Q4 FY2025 income cells blank, balance sheet intact); OXY overview valuation falls back honestly (Watch, Low confidence, no target); TJX overview renders the backfilled description. No template change (backend-only); screenshot gate N/A.
**Follow-ups (not this batch):** D-style immaterial Q4 true-ups tripping the detector (only matters if a future filer has no Q4 stub — monitor); XOM self-heal on first 10-K (Feb 2027); SPG dominant-quarter self-heal (Q4-2026 filing); V/BRK.B EPS unfixable from companyfacts; pending-filing cohort at 14.

## Batch 86 (2026-10-17) — earnings-calendar integration audit; no code change

**Scope:** Gemini's PRD §4.5 earnings calendar (`data/calendar.py` + `FinancialsService.get_upcoming_earnings`/`get_cached_upcoming_earnings` + `templates/calendar.html` + the home-page strip) audited against real Yahoo data for all 233 DB companies.

**Method:** Warmed the calendar cache (bounded, concurrent prefetch) for every tracked ticker, rebuilt the full event list through the production builder, and checked: event count vs DB count, duplicate tickers, date-format/consistency (`days_until` == `earnings_date − today`), sort order vs `_earnings_sort_key`, ticker display form, cohort distribution, raw Yahoo payload shapes on 8 tickers (single date, list, dividend dates, estimate types), and one external spot-check of a shown date/estimate against the company's own announcement.

**Finding:** Zero defect classes. 233/233 events, no dups, dates consistent, sort correct, canonical tickers (BRK.B). Cohort: 41 ≤7d, 130 ≤30d, 29 ≤60d, 18 ≤92d, 15 reported ≤9d ago (correct newest-first "Reported" labeling), 0 TBD/empty. Raw shapes are exactly what `_safe_date_str` handles (Earnings Date = single-element `[date]` list — the multi-element range-window case never occurs in the sampled payloads, so the first-element logic is safe). AGNC spot-check: 2026-10-19 "in 2d", EPS consensus $0.3726 — matches the confirmed Oct-19-after-close release and the $0.37–0.38 analyst range; revenue est $447.1M inside the published estimate band. The home strip shows the 4 soonest upcoming; `/calendar` renders all 233 rows with honest "Reported" pills.

**Decision:** No code change (standing rule: never invent work when the audit is clean). The never-raise, TTL-cache, prefetch/warm design is holding: cold `/calendar` is bounded by the 10s fetch timeout × concurrency, warm renders are sub-second.

**Carried follow-ups rechecked:** XOM self-heal still pending (FY2026 10-K, ~Feb 2027); SPG dominant-quarter self-heal waits on the Q4-2026 filing; V/BRK.B quarterly EPS tagging not resumed (still unfixable); pending-filing cohort at 14 (EDGAR ~2.5-month companyfacts lag, by design).

**Tests:** none added; suite 735 green, `git diff --check` clean. **Blast radius:** none (docs only). No template change; screenshot gate N/A.

## Batch 87 (2026-10-18) — round-32 seeds; derived-EPS basic/diluted ranking guard

**Seeds:** BBY, DLTR, EIX, STZ, VMC, EXPE — all 8 quarters, clean. DB at 239 companies.

**Finding:** Deep audit surfaced one real defect class. BBY's FY2026Q4 shows diluted EPS $2.5798 above basic $2.5584 — arithmetically impossible (anti-dilutive securities are excluded from the diluted count, never added). Forensics against raw companyfacts (CIK-verified): the inputs are honest — FY2026 NI $1,069M / EPS $5.06/$5.04 and 9M NI $528M / EPS $2.50/$2.48 (the "two facts, same end" pair is the normal YTD-vs-quarterly split: start=2025-02-02 vs start=2025-08-03, not a restatement). The corruption is in the batch-12 share-implied derivation itself: basic and diluted are derived independently, and the 2-decimal 9M EPS gets 3x leverage through the (12·FY_avg − 9·9M_avg)/3 share-month residual, so filing-rounded inputs invert the ranking (implied Q4 diluted shares 209.7M came out below basic 211.4M). A DB-wide scan found 49 inverted pairs across 44 tickers — all derivation artifacts, including the batch-78 NI/shares path (DD FY2025Q1 −4.23/−4.20) and loss quarters where diluted must equal basic (COIN FY2025Q4 −2.49/−2.31, the largest flip at 0.18). Every other suspicious value verified as filer-real: DLTR's FY2024Q4 −$3.70B NI is the filer's own 10-K Q4 stub (start=2024-11-03, fp="FY" mislabel — the batch-13 relabel machinery handled it; 9M + Q4 = FY to the dollar); VMC's Q3→Q4 FY2024 balance-sheet jump (+$2.7B assets, +$1.6B LT debt) is a real debt-financed acquisition, identical in the 10-K and every later comparative. STZ files no EPS tags at all (dimensional per-class EPS, like V) — data-source limit, documented.

**Fix:** new `_reconcile_eps_basic_diluted(basic, diluted)` in `data/xbrl.py`, called in `extract_recent_quarterly_financials` after `_fill_missing_eps_basic`. Any diluted > basic pair is corrupt by definition, so the diluted leg is clamped to basic (the legs differ by fractions of a percent — nothing is lost; logs a warning per correction). Series-level placement catches flips from every derivation path, and subsumes the batch-12 "residual sub-cent flips" limitation (DLTR FY2025Q4 2.5434/2.548 now 2.5434/2.5434).

**Alternatives considered:** recomputing the diluted leg via precision-rounded subtraction at reconcile time (rejected — the annual/9M facts aren't in scope at the series level, and the clamp is the invariant-preserving minimum); fixing only inside `_derive_q4_income` (rejected — it sees one metric at a time, and the batch-78 path would still flip); raising basic to diluted (rejected — basic is the binding constraint; the error is always diluted overshooting).

**Tests:** 5 new in `tests/data/test_xbrl.py` (reconciler unit: BBY-shaped flip clamped, healthy pair untouched, loss-quarter equalized, unpaired diluted ignored; end-to-end BBY-shaped fixture asserting the stored row has diluted ≤ basic — verified to fail pre-fix). Suite 740 green (735 + 5), `git diff --check` clean.

**Blast radius:** `data/xbrl.py` (one new function + one call site), tests. No valuation, briefing, peers, calendar, template, or schema changes. Backfill: 49 diluted values corrected DB-wide from cached companyfacts (44 tickers), 0 basic changed, 0 errors; 0 flipped pairs remain.

**Live:** Server restarted via the launcher script (kill by explicit PID). 6/6 routes 200 (BBY overview needed one retry — transient quote-refresh stall); BBY detail HTML no longer carries 2.5798. No template change (backend-only); screenshot gate N/A.

**Carried follow-ups rechecked:** XOM self-heal still pending (FY2026 10-K, ~Feb 2027); SPG dominant-quarter self-heal waits on the Q4-2026 filing; V/BRK.B/STZ quarterly EPS tagging not resumed (still unfixable from the feed); pending-filing cohort at 16 (14 carried + EIX/VMC seed-time notes; EDGAR ~2.5-month companyfacts lag, by design).

**Tests:** 5 new; suite 740 green, `git diff --check` clean. **Blast radius:** `data/xbrl.py` + tests. No template change; screenshot gate N/A.

## Batch 88 (2026-10-18) — AI briefing integration audit: REIT register, unknown-sector register, SIC 6400-6499 gap

**Audit:** Network-free sweep of `generate_ai_analysis` over all 239 DB companies (stored overviews + stored risk factors/guidance + stored valuations). Zero contradiction flags: the Strong-Sell reconciliation thesis renders on all 122 Watch-vs-Strong-Sell pairs and the `theses[:6]` cap never truncates it; no Strong-Buy/Avoid pairs exist.

**Finding 1 — REITs in industrial register:** all 10 SIC-6798 REITs narrated "healthy demand across commercial segments" (NLY +78.7% — an mREIT's revenue is net interest spread) and "operational leverage and pricing discipline" next to 186.4%/231.7% GAAP net margins (distorted by depreciation and unrealized gains). The batch-41/46 sector tails covered bank/securit/insurance/financ but forgot REITs.

**Fix:** `_revenue_thesis_tail`, `_revenue_decline_tail`, `_margin_thesis_tail` in `services/ai_analysis.py` take `is_reit` (default False). REIT copy: "reflecting portfolio income and balance-sheet dynamics" / "a softer quarter for portfolio income and balance-sheet dynamics" / "with REIT profitability better read through funds from operations than GAAP net margin" (FFO copy matches the valuation model's REIT path, batches 70/72). `generate_ai_analysis` gains an optional `sic` param reusing `_is_mreit_sic` from `data/xbrl.py` (with the "Real Estate" sector label as fallback for callers without the Company row); `get_ai_analysis` wires it through a local, never-raising Company lookup.

**Finding 2 — unknown sector in industrial register:** ARCC's `Company.sic` is NULL — verified honest (SEC's own submissions file for CIK 0001287750 reports no SIC), so the briefing's industrial closers were ungrounded claims. Sector-None now renders neutral register ("the quarter's operating performance" / "reflecting the quarter's profitability") instead of fabricating a register.

**Finding 3 — SIC 6400-6499 unmapped:** AON (sic 6411) got sector None while the valuation model already priced it on the insurer path (`_BANK_INSURER_SIC_RANGES` covers 6300-6499, batch 70). Added `(6400, 6499, "Insurance")` to `data/sic.py` (SIC 64xx = Insurance Agents, Brokers, and Service). Genuine side effect: AON's solvency now scores on the financial ladder (A/L 1.223x: 65 → 85; composite 55 → 59, signal still Watch) — the batch-46 principle (thin balance sheets are the business model for financials) applied consistently.

**Alternatives considered:** keying REIT copy on the "Real Estate" sector string alone (rejected — imprecise for future non-REIT real-estate filers; SIC is the source of truth and was already in the DB); backfilling ARCC's SIC (rejected — the SEC source itself is blank, so the fix must be code-level); rewriting the tails to drop closers for REITs (rejected — the REIT copy is informative and matches valuation's FFO framing).

**Tests:** 8 new — 6 in `tests/services/test_ai_analysis.py` (REIT revenue growth/decline/margin tails via sic=6798, REIT detection from the sector label alone, unknown-sector neutral register, non-REIT sic keeps industrial register — REIT tests verified to catch the old copy) and 2 in `tests/data/test_sic.py` (new file; 6400-6499 → Insurance plus boundary regression). Suite 748 green, `git diff --check` clean.

**Blast radius:** DB-wide stash A/B over 239 briefings: exactly 12 tickers change (10 REITs + ARCC + AON), 227 byte-identical, 0 signal flips, 1 composite delta (AON 55→59, justified above). No valuation, peers, calendar, tearsheet, template, or schema changes.

**Live:** service-level briefings for NLY/ARCC/AON verified with the new copy. HTTP overview pages hang on first view behind the lazy SEC disclosure backfill (pre-existing — NLY exceeded a 240s curl; the backfill short-circuits on repeat views). No template change (backend-only); screenshot gate N/A.

**Carried follow-ups rechecked:** XOM self-heal still pending (FY2026 10-K, ~Feb 2027); SPG dominant-quarter self-heal waits on the Q4-2026 filing; V/BRK.B/STZ quarterly EPS tagging not resumed (still unfixable from the feed); pending-filing cohort at 16 (EDGAR ~2.5-month companyfacts lag, by design). New: overview first-view SEC-backfill latency (NLY >240s) — candidate for backgrounding the backfill off the render path.
## Batch 89 (2026-10-18) — first-view disclosure-backfill time budget; round-33 seeds; stale-fy label repair

**Fix 1 — disclosure backfill time budget (the batch-88 follow-up):** first-view overview renders hung >240s (NLY) behind the lazy SEC disclosure backfill. Profiling a fresh ticker (HSY): `fetch_and_persist` 8.8s, quote 0.2s, description 2.7s, risk-factors 10-K 2.2s — but the 8-quarter ex-99 exhibit crawl 26s: up to 9 large sequential SEC HTML downloads, unbounded, blocking a page that doesn't even render the disclosures. New `DISCLOSURE_BACKFILL_BUDGET_SECONDS = 30.0` in `services/financials.py`; `_enrich_press_release_highlights` takes an absolute-monotonic `deadline`, processes quarters **latest-first** (latest quarter = AI-briefing context + detail default view), and stops at expiry — unfilled rows keep NULLs and self-heal on later visits through the existing any-None lazy triggers (detail backfill, enrich, refresh). Wired at all three call sites: `enrich_company` (new optional `disclosure_budget_seconds`, None = unbounded), the `refresh_financials_if_stale` refire, and the `get_detail` lazy backfill.

**Fix 2 — stale fiscal-year focus on 10-Qs (MTD, WDAY):** round-33 forensics found MTD's Q1/Q2-2025 10-Qs tagging 2025-03-31/2025-06-30 as fy=2024 and WDAY's three 2025 10-Qs tagging fy=2025 (verified against raw SEC JSON; their 10-Ks and Q3 10-Qs use the correct ending-year convention). `_dedupe_period_labels` only arbitrates collisions and `_repair_sequence_breaks` needs a 3-long backbone, so these consistent-but-wrong runs slipped through. New `_repair_stale_fy_wraps` in `data/xbrl.py`: the invariant is local and convention-independent — labels advance one quarter-step per period, so a row claiming exactly one year behind the successor expectation (same fp) is mislabeled. Walk ends ascending and relabel, guarded by an unheld-target check so genuinely shifted conventions (SKYD's FY2025Q4→FY2025Q1 wrap, whose "fixed" targets are held by later rows) are left alone instead of collided. Cascading follows from repaired labels; genuine coverage gaps change fp and can never match the signature.

**Hunt:** seeded SYY, CHD, KHC, DGX, MTD, GPC (8 quarters each, strictly descending ends, descriptions 6/6, no pending-filing notes, no identity gaps >2%, no diluted>basic inversions). Forensics confirmed suspicious values as filer-real: KHC FY2026Q2 EPS −4.60 (goodwill impairment in the 10-Q). CHD 0/8 highlights is an extractor gap, not a fetch failure — guidance extracts 8/8; CHD's pre-headline `Contact:` block trips the lede boilerplate break (deferred: only 4/246 companies affected — CHD/HUM/ORCL/SPG). GPC 1/8 disclosures is by design (only its FY2025Q4 8-K carries an ex-99; it embeds releases in the primary doc, the known data-source limit).

**Alternatives considered:** background thread for the backfill (rejected — no threading pattern in the codebase; SQLite cross-thread session risk; the time budget composes with the existing self-healing triggers with zero concurrency risk); HTMX-lazy disclosure endpoint (rejected — disclosures render on detail, which already has the lazy backfill; the defect was the unbounded inline crawl, now bounded at all three call sites); fixing the stale-fy rows by trusting SEC `fiscalYearEnd` (rejected — the codebase deliberately distrusts it per the JNJ precedent in `_choose_fact_for_end`; the sequence invariant needs no external authority); repairing SKYD's shifted series too (rejected — the unheld-target guard correctly leaves it alone; "fixing" it would manufacture collisions).

**Tests:** 8 new — 3 budget (`expired-deadline fills nothing` incl. zero exhibit fetches; `controlled-clock latest-first` proving both the budget and the ordering; `enrich_company` deadline plumbing ≈ now+30s) and 5 stale-fy (MTD shape, WDAY 3-row cascade, SKYD held-target guard, clean sequence untouched, gap safety). Suite 756 green (748 + 8), `git diff --check` clean.

**Blast radius:** budget — render paths only; extraction values unchanged, only fill timing. Stale-fy — DB-wide in-memory A/B over 246 companies: exactly 5 rows change (MTD 2, WDAY 3), SKYD untouched by the guard, 241 byte-identical. MTD/WDAY re-seeded; MTD detail HTML renders the repaired Q1/Q2 FY2025 labels.

**Live:** server restarted for the new code (kill by explicit PID). 10/10 routes 200 (home, 6 new overviews, MTD/CHD detail, /calendar). 6 round-33 seeds enrich in 12–36s each (bounded; previously unbounded). No template change (backend-only); screenshot gate N/A. DB at 245 companies.

**Carried follow-ups rechecked:** XOM self-heal still pending (FY2026 10-K, ~Feb 2027); SPG dominant-quarter self-heal waits on the Q4-2026 filing; V/BRK.B/STZ quarterly EPS tagging not resumed (still unfixable from the feed); pending-filing cohort at 16. New: highlights-extractor pre-headline `Contact:` block coverage (CHD/HUM/ORCL/SPG).

**Batch 90 — press-release highlights `Contact:`-block coverage (CHD-style pre-headline contact blocks):**

**Context:** CHD showed 0/8 press-release highlights while guidance extracted 8/8. Forensics on the live Q2-2026 ex-99 showed the release opens with a company masthead (`Church & Dwight Co., Inc.`), a bare `Contact:` header, and name/title/phone detail lines before the real headline. The old headline pass picked the masthead (first non-admin/non-contact line), and the bare `Contact:` matched the boilerplate regex's `contacts?(\s|:)` *terminator* in the lede fallback — designed for trailing contacts sections — so the lede broke before any content and the whole extraction returned None. Same format family as Oracle's exhibits (CHD/HUM/ORCL/SPG were the deferred cohort).

**Alternatives considered:** extending `_CONTACT_LINE_RE` with the bare form (rejected — that regex's matches are *skipped line-by-line*, which would leave the name/title/phone detail lines in the lede; the block must be skipped as a unit); treating the bare header as boilerplate-terminator but in the headline pass only (rejected — the header precedes the headline, so terminating there still yields no content); inferring the headline as the first all-caps line (rejected — too format-specific; JNJ-style title-case headlines are the common case).

**Tests:** 3 new — CHD-style fixture (masthead + bare `Contact:` + name/title/phone + all-caps headline; asserts the real headline is picked, masthead is not, contact details absent), Oracle-style fixture (title-case headline + trailing `Contacts:` section; asserts trailing block skipped and `About` terminates), and a `_skip_contact_block` bound test (a misfired header can never skip more than 8 detail lines).

**Blast radius:** extractor-only, backend. All 38 pre-existing filings tests green unchanged (JNJ media/investor-contact and Deere formats verified unaffected). Live backfill for CHD: 8/8 quarters filled; the detail page's any-None lazy trigger will self-heal HUM/ORCL/SPG on their next detail visit without a re-seed.

**Live:** dev server restarted for the new code (kill by explicit PID). `/company/CHD` 200, `/company/CHD/detail/data` 200 rendering the true headline with 70 words Available. No template change; screenshot gate N/A. DB at 245 companies.

**Carried follow-ups rechecked:** XOM self-heal still pending (FY2026 10-K, ~Feb 2027); SPG dominant-quarter self-heal waits on the Q4-2026 filing — and SPG's exhibit is a combined release+supplement packet with a TOC, a different defect class than the Contact block (its masthead is now skipped but the narrative-start-past-TOC fix is separate); V/BRK.B/STZ quarterly EPS tagging still unfixable from the feed; pending-filing cohort at 16.

## Batch 91 (2026-10-18) — TOC skip for combined release+supplement packets; wrapped-headline join

**Context:** batch 90 deferred SPG's combined release+supplement packet as a separate defect class: its ex-99 opens with a table of contents (cover block, section-title/page-number pairs, footnote, mini-TOC, then a `Contacts:` block) before the real narrative. The old headline pass picked `TABLE OF CONTENTS` as the headline and filled the lede with TOC entries, so extraction returned None for all 8 SPG quarters — verified against the live Q2-2026 exhibit (3.2MB, 6103 text lines; narrative starts ~60 lines in).

**Fix 1 — `_skip_toc()` (`data/filings.py`):** consumes `(title*, page-number)+` runs after a `TABLE OF CONTENTS` heading. The page number (`12`, `2–11`, `30–38`) is the discriminator — TOC titles and release headlines look alike, so title shape alone can't decide. Stops at the first narrative marker (`Contacts:` header, contact line, `For Immediate Release` banner) or a line that is neither title-shaped (≤140 chars) nor a page number. A trailing mini-TOC (`TABLE OF CONTENTS` / `EARNINGS RELEASE` / `Contacts:`) is skipped only when a narrative marker appears within the next 4 lines, so a real headline directly after a TOC is never swallowed. Requires ≥2 page-number lines: a stray "table of contents" mention in a normal release returns the index unchanged (old behavior preserved).

**Fix 2 — `_join_wrapped_headline()` (`data/filings.py`):** SPG wraps its headline mid-phrase (`...Results and` / `Increases Guidance ...`). When the picked headline ends on a conjunction/preposition and the next line is short (≤100), fragment-shaped (no terminal `.`/`!`/`?`/`:`), and marker-free (not admin/boilerplate/contact, not bullet/dateline-led), the two lines are joined. The guards keep a genuine short headline from swallowing the lede — verified against AT&T's stored headline, which ends in "and" but is followed by a `•` bullet and stays unjoined.

**Alternatives considered:** skipping TOC entries by title shape alone (rejected — title-case narrative headlines like "Simon Reports Second Quarter 2026 Results" are title-shaped and would be swallowed); terminating the skip at the first long-prose line (rejected — SPG's footnote "Includes reconciliation of consolidated net income to FFO and Real Estate FFO." is prose-shaped but part of the TOC); joining wrapped headlines on any short next line (rejected — would merge sub-headlines and lede fragments; the conjunction-break + no-terminal-punctuation guard is the conservative rule); fixing O's blank highlights in the same batch (rejected — O is a discovery gap, `_pick_release_doc` tier-0 pattern, a separate defect class; forensics recorded as a follow-up).

**Tests:** 6 new — SPG-style fixture (cover + TOC pairs + footnote + mini-TOC + `Contacts:` block + wrapped headline; asserts joined headline, narrative lede, zero TOC/contact residue), `_skip_toc` bails without page numbers, `_skip_toc` stops at the release banner, join fires on conjunction break, join ignores sentence-terminated lede, join ignores complete headlines. All 41 pre-existing filings tests green. Suite 765 green (759 + 6), `git diff --check` clean.

**Blast radius:** extractor-only, backend. The TOC path only fires on documents with a `TABLE OF CONTENTS` heading + ≥2 page numbers (previously all extracted as None or TOC junk). The headline join only fires on headlines ending in a wrap word: DB scan over 1516 filled quarters found 17 candidates (most are 120-char truncation artifacts; the bullet/dateline guards exclude real ledes). No valuation, peers, calendar, tearsheet, template, or schema changes.

**Live:** dev server restarted for the new code (kill by explicit PID). `_enrich_press_release_highlights` re-run for SPG: 8/8 quarters backfilled from live SEC exhibits with real headlines + narrative ledes. 4/4 routes 200 (home, `/company/SPG`, `/company/SPG/detail`, `/calendar`); the detail page renders the true Q2-2026 headline with no TOC or contact residue. No template change; screenshot gate N/A. DB at 245 companies.

**Carried follow-ups rechecked:** XOM self-heal still pending (FY2026 10-K, ~Feb 2027); SPG dominant-quarter self-heal waits on the Q4-2026 filing; V/BRK.B/STZ quarterly EPS tagging still unfixable from the feed; pending-filing cohort at 16; HUM/ORCL self-heal on next detail visit via the any-None lazy trigger. New: O (Realty Income) 0/8 highlights is a discovery gap — its 8-K exhibits use the `o-991q22026.htm` convention (991 as infix before the quarter marker), which `_pick_release_doc`'s tier-0 `991$`-suffix pattern never matches; and mid-phrase headline wraps (SPG Q3-2024 `...2024` / `Guidance and`) leave the continuation as the first body line by design.

## Batch 92 (2026-10-18) — 991-infix exhibit discovery convention (O / Realty Income)

**Context:** batch 91 left O's 0/8 press-release highlights as a deferred *discovery* gap (not extraction): `_pick_release_doc` tier-0 only matched the `991$` suffix convention, but O names its 99.1 exhibits `o-991q22026.htm` (991 infix before the quarter marker). Verified live against O's Q2-2026 8-K filing index (`0000726728-26-000044`): `o-991q22026.htm` is the earnings-release exhibit; the supplement `realtyincomeq22026supple.htm` coexists and must lose.

**Fix (`services/ir_download.py`):** tier-0's bare-991 branch became `991(?=q\d|[-_]|$)`. The lookahead is the conservative choice: it accepts 991 before a quarter marker (`o-991q22026`), before a separator (`o-991-q22026`), and at end-of-stem (`q22026991`, AMD's existing case), but `991` embedded in a longer digit run (`doc9912final.htm`) can never match — an exhibit-name convention without a quarter boundary or separator is not evidence of 99.1.

**Alternatives considered:** a broader `991` substring match (rejected — would false-positive on doc ids like `doc9912final`); a named O-specific pattern (rejected — the infix convention is a class, not a filer quirk; the generic form covers separators too).

**Tests:** 3 new — O's real filing-index filenames (asserts the release wins over the supplement and R1.htm), separator variant, longer-digit-run negative. All 21 pre-existing `ir_download` tests green unchanged.

**Blast radius:** discovery-only, backend. Tier-0 only ever fires on `ex99`-style names or the 991 patterns; prior matches are byte-identical under the new pattern (the old `991$` is subsumed by the lookahead's `$` alternative).

**Live:** dev server restarted for the new code (kill by explicit PID). `_enrich_press_release_highlights` re-run for O: 8/8 quarters backfilled from live SEC exhibits with real headlines + narrative ledes (Q2-2026 renders AFFO +3.8%, $2.6B invested, CEO Sumit Roy quote). 4/4 routes 200 (home, `/company/O`, `/company/O/detail`, `/calendar`). No template change; screenshot gate N/A. DB at 245 companies; the zero-highlight cohort drops to 29.

**Carried follow-ups rechecked:** XOM self-heal still pending (FY2026 10-K, ~Feb 2027); SPG dominant-quarter self-heal waits on the Q4-2026 filing; V/BRK.B/STZ quarterly EPS tagging still unfixable from the feed; pending-filing cohort at 16; HUM/ORCL self-heal on next detail visit via the any-None lazy trigger. New: 29 companies (LUV, WST, PNC, PAYX, CCL, EOG, PHM, EIX, REGN, SNPS, CB, DKS, NOC, NEM, EXPE, DUK, WDAY, ORCL, NOW, VMC, ULTA, LOPE, ACN, UBER, DUOL, SNOW, COIN, CTVA, AFRM) still show 0/8 highlights — each is likely another undiscovered `_pick_release_doc` convention, a GPC-style embedded release, or genuinely missing exhibits; audit deferred to a future batch.

## Batch 93 (2026-10-19) — zero-highlight cohort forensic sweep: 11 discovery conventions + extraction gaps (masthead blocks, prefixed contact headers)

**Context:** batch 92 deferred the audit of the remaining zero-highlight companies ("each likely another undiscovered `_pick_release_doc` convention, a GPC-style embedded release, or genuinely missing exhibits"). This batch forensically swept all 36 zero-highlight companies: fetched each one's latest Item-2.02 8-K filing indexes from EDGAR and ran `_pick_release_doc` against the real exhibit filenames.

**Finding 1 — discovery gaps (15 companies):** `_pick_release_doc` returned None for ACN (`q4fy26earnings8-kexhibit.htm`), AFRM (`affirmfq426shareholderle.htm`), CCL (`a20263qearningsrelease8-k.htm`), COIN (`q425shareholderletter.htm`), CTVA (`a2q_2026xearningsxnewsxr.htm`), DUOL (`q2fy26duolingo6-30x26share.htm`), EOG (`exh99-1080426.htm`), LLY (`q226lillysalesandearningsp.htm`), LUV (`er-6302026xerdoc.htm`), MKC (`mkcreportssolidthirdquar.htm`), NEM (`newmontq42025earningsand20.htm`), NOW (`erq2fy26.htm`), PNC (`q32026financialhighlightsa.htm`), SNOW (`fy2027q2earnings.htm`), TRV (`a991pressrelease93026.htm`).

**Fix (`services/ir_download.py::_rank`):** tier-0 `ex(?:hibit)?` became `ex(?:hibit|h)?` (EOG's `exh99-1`); tier-1 gained: `(press|earnings)[-_ ]?8[-_ ]?k` (explicit "earnings 8-K exhibit"), `earnings[-_x]?news` (Corteva's "earnings news release"), bounded `shareholder(?:le(?:t(?:ter)?)?)?(?=$|[-_.])` plus `share$`-with-quarter-marker (Affirm/Coinbase/Duolingo shareholder letters — the bound keeps `shareholdermeeting.htm` unmatched), `sales[-_ ]?and[-_ ]?earnings` (Lilly), `financial[-_ ]?highlights` (PNC, beats the `financialsupplement` tables), `reports`+quarter-word (McCormick headline-style names), `(^|[-_x.])erdoc(ument)?($|[-_.])` (Southwest — anchored so `superdocuments` can't match), `(^|[-_])erq[1-4]` (ServiceNow); tier-2 gained quarter-adjacent `earnings` (Snowflake/Newmont). The old tier-1 `(press|earnings)[-_ ]?rele[a-z]*\b` boundary became `(?=$|[-_.\d])` — the `\b` failed when "release" was followed by a digit (Carnival's `earningsrelease8-k`, Travelers' `pressrelease93026`); the lookahead is strictly more conservative for letter-followed cases.

**Finding 2 — extraction gaps (5 companies whose discovery already worked):** CB, HUM, LOPE, SNPS fetched fine but `extract_press_release_highlights` returned None. Root causes, all headline/lede pollution: (a) company-name masthead followed by a head-office address block — Chubb's street line "Bärengasse 32" became the headline and the 6-line lede budget filled with address residue (190 chars < 200 minimum); (b) role-prefixed contact-block headers ("FOR MORE INFORMATION CONTACT:", "Investor Relations Contact:", "INVESTOR CONTACT:") matched the single-line contact skip before the block-header branch, so detail lines ("Tushar Jain", "Lisa Stoner") became headlines; (c) Humana's spaced-letter "n e w s r e l e a s e" kicker wasn't an admin line.

**Fix (`data/filings.py`):** `_CONTACT_HEADER_RE` now accepts role prefixes (`for more information|investor(\s+relations)?|media|press|editorial`); the header check runs *before* the single-line contact skip in both the headline and lede loops; new `_skip_masthead_block` (bounded at 6 lines) skips address-block residue after a company-name masthead line — residue is a URL/handle, a single word (country), or a short digit-bearing line (street/postal); `_ADMIN_LINE_RE` accepts spaced-letter kickers; `_CONTACT_LINE_RE` covers `www.` URLs and `@handles`.

**Alternatives considered:** a generic "skip short lines after company name" rule (rejected — could swallow a short digit-bearing headline; the residue-shape test is narrower); teaching the extractor shareholder-letter table structure for DUOL (deferred — different document class, see follow-ups).

**Tests:** 21 new — 17 discovery (each new convention against the real observed filenames, plus `shareholdermeeting`/`superdocuments`/`doc9912final` negatives) and 4 extraction (CB masthead, SNPS prefixed headers, HUM spaced kicker + address block, LOPE header-ordering). All pre-existing tests green unchanged.

**New script:** `scripts/backfill_disclosures.py` — backfills every zero-highlight company via `_enrich_press_release_highlights` (unbounded, fill-only, per-ticker never-raise, 0.5s SEC politeness), following the `backfill_risk_factors.py` pattern.

**Blast radius:** discovery changes only add matches for previously-None names (verified: all 24 pre-existing discovery tests green); extraction changes only affect documents with company-name mastheads / prefixed contact headers / spaced kickers — full suite 789 green.

**Live:** dev server restarted for the new code. Backfill rescued 35 of 36 (ACN +7, DUK +7, then 29 more incl. CB/HUM/LOPE/SNPS after the extraction fix); zero-highlight cohort 36 → 1 (DUOL only). 8/8 routes 200 (home, `/company/{CB,ACN,DUK}`, `/company/{CB,HUM,SNPS}/detail`, `/calendar`); CB detail renders the true Q2 headline. No template change (backend-only); screenshot gate N/A. DB at 246 companies.

**Follow-ups (not this batch):** DUOL's shareholder-letter "Q2 Highlights" is a metric table (`"58.7M".isupper()` terminates section collection; mission-statement head) — needs a shareholder-letter extraction mode; REGN/EOG/WDAY quarters whose 2.02 8-Ks carry no exhibit (embedded releases, by design unhandled); the 71 partial-highlight companies self-heal via the lazy page-view trigger.

## Batch 94 (2026-10-19) — shareholder-letter metric-table extraction mode (DUOL)

**Context:** batch 93's forensic sweep rescued 35 of 36 zero-highlight companies and deferred exactly one: DUOL, whose "Q2 Highlights" is a metric table (`"58.7M".isupper()` terminates section collection; mission-statement head). This batch closed it.

**Forensics (verified against live SEC exhibits):** Duolingo's ex-99.2 shareholder letters flatten the "Q# Highlights" metric table into label/value/change line triples. The standard `_extract_highlights_section` collects "User Metrics Q2 2025 Q2 2026" and "Daily Active Users 47.7M", then breaks at "58.7M" (all-caps) — under the 150-char minimum → None; the lede fallback then starves on the mission-statement cover ("our mission is / to develop the / ...") and the "EX-99.2" junk headline → None for every quarter. Affirm's letter exhibit is image-only (46 text chars — honestly unextractable, out of scope); Coinbase's is narrative prose ("Fellow Shareholders," — no metric table).

**Fix (`data/filings.py`):** a gated shareholder-letter mode. `_is_shareholder_letter` requires the cover-title shape ("shareholder" line + "letter" line, or one "shareholder letter" line) within the first 30 lines — "dear shareholders" prose mid-document never triggers. `_shareholder_letter_headline` synthesizes "Shareholder Letter Q2 2026" from the cover quarter (proximity-windowed ±lines around the title; supports Duolingo's "Q4 / FY 2025" slash form; skips running headers — the naive first-match scan wrongly produced "Shareholder Letter Q4 2024" from the table's prior-year column). `_parse_metric_highlights` parses group headers with 2+ quarter columns, including headers wrapped across two lines ("Financial Metrics Q4 2025" / "FY 2025"), and renders bullets column-aware: same-quarter YoY pairs read "47.7M → 58.7M (23% YoY)" (margin pairs "35.9% margin → 29.6% margin"); cross-period columns (Q4 vs FY) join with "; " so no false same-period comparison is implied. Footnote lines ("(1) ...") and running headers terminate the table. Falls back to the standard path when no metric table parses (Coinbase keeps its narrative extraction). Requires ≥2 metric entries, else None.

**Discovery fix (`services/ir_download.py`):** the quarter-guarded "share" truncation branch became `share?$` — Duolingo's Q4/FY letter is truncated one step further (`q4fy25duolingo12-31x25shar.htm`), and the 8-K's EX-99.1 `...x25pres.htm` is a stub pointing at the IR website, so the letter must win. The quarter/fy guard keeps "sharkweek"/bare-"shar" from matching.

**Alternatives considered:** synthesizing the company name into the headline from running headers (rejected — cover text is unreliable; "Shareholder Letter Q2 2026" is document-derived and honest); pairing each change line with its column label in cross-period groups (rejected — the positional inference adds assumptions; "; " preserves order without implying mapping); extending the mode to image-only letters via OCR (rejected — out of scope, no text to extract).

**Tests:** 6 new — Q2 metric table (exact bullets incl. YoY, margin-pair, "at period end" annotation; the "58.7M" isupper signature now content; no mission/running-header/letter-body residue), Q4/FY mixed columns (slash-quarter headline, wrapped group header, "; " cross-period rendering, footnote termination), title-shape detection negative (CEO-quote "Dear shareholders" keeps narrative path), thin-table fallback (no fabricated bullets), "shar" discovery beats "pres", "shar" negatives. All pre-existing tests green.

**Blast radius:** extractor-only, and only for documents passing `_is_shareholder_letter` (previously all returned None — the mode can only add content, never alter press-release output); the `share?$` change only adds matches for stems ending in "shar"/"share" with a quarter/fy marker (previously None or lower-tier). Full suite 795 green (789 + 6), `git diff --check` clean.

**Live:** dev server restarted for the new code (kill by explicit PID). DUOL backfill: 8/8 quarters filled (was 0/8), all values spot-checked against real reported figures (Q3-2024 37.2M DAU +54%, Q4-2024 $748M FY revenue, Q2-2026 58.7M DAU +23%). 4/4 routes 200 (home, `/company/DUOL`, `/company/DUOL/detail`, `/calendar`); the detail page renders "Shareholder Letter Q2 2026" with real metric bullets. No template change (backend-only); screenshot gate N/A. DB at 246 companies. **Zero-highlight cohort: 0 companies.**

**Carried follow-ups rechecked:** REGN/EOG/WDAY embedded-release quarters remain by-design unhandled; 71 partial-highlight companies self-heal via the lazy page-view trigger; XOM self-heal still pending (FY2026 10-K, ~Feb 2027); SPG dominant-quarter self-heal waits on the Q4-2026 filing; V/BRK.B/STZ quarterly EPS tagging still unfixable from the feed; pending-filing cohort at 16; HUM/ORCL self-heal on next detail visit via the any-None lazy trigger.

## Batch 95 (2026-10-19) — pending-filing cohort forced recheck (verification, no code change)

**Context:** 17 companies carried amber "filed but EDGAR hasn't ingested" notes (batch 53 mechanism): V, PYPL, DUK, CB, PLD, C, SPGI, HUM, WELL, HCA, CDNS, GD, CLX, AEP, ABT, EIX, VMC — 10-Qs filed Jul 28–Aug 6 2026 (C also a May 7 Q1 10-Q), still absent from companyfacts ~2.5–5.5 months later. This batch forced the full refresh path with fresh (TTL-bypassed) submissions + companyfacts for each, to test whether the lag had cleared or the notes/extraction were hiding a defect.

**Method:** per ticker — fresh `submissions(cik, fresh=True)` + `companyfacts(cik, fresh=True)`, then `refresh_financials_if_stale` (fresh process → 6h check TTL empty → real check), then `_pending_filing_note` recompute plus an extraction-gap probe (pending candidates whose revenue-duration facts ARE now ingested would mean the note is masking an extractor defect, not lag).

**Findings (all verified against live EDGAR):**
1. **All 17 still genuinely lagged.** Every note persisted word-for-word; `ingested_but_missing` probe empty for all 17 — no pending candidate has revenue facts in companyfacts. The lag is real, not a stale-note or extraction bug.
2. **The retry loop is armed correctly.** All 17 refires returned True (latest quarterly filing postdates the `xbrl_filings_processed` marker), re-ran `extract_recent_quarterly_financials` against fresh companyfacts, stored zero new quarters, and — critically — markers did NOT advance (V still 2026-04-29, C still 2026-02-20, etc.): `_processed_filing_marker` tracks the latest *incorporated* filing, not merely seen, so the 6h retry keeps firing until the facts actually land. Quarter counts unchanged (8 each), newest labels unchanged.
3. **Lag severity is filer-uniform, not company-specific.** Revenue-fact tails confirm: C stops at 2025-12-31 (two quarters missing — Q1 filed May 7 + Q2 filed Aug 6), PYPL at 2026-03-31, V at 2026-03-31 (Sep-FY: Q2 FY2026). This is EDGAR companyfacts feed behavior, not per-filer XBRL problems.
4. **Incidental:** each refire also ran the batch-89 time-budgeted disclosure backfill; highlights coverage across the cohort is healthy (most 7/8; AEP 4/8, C 2/8 — pre-existing states).

**Blast radius:** none — read-mostly audit; the forced refires wrote nothing new (no quarter changes, no marker moves, notes byte-identical). No code change; full suite 795 green unchanged (docs-only batch).

**Live:** dev server up (200 on `/`) after a cold start at batch start. No routes affected; no template change; screenshot gate N/A. DB at 246 companies. Pending-filing cohort remains at 17 — all notes accurate, self-clearing when EDGAR ingests.

**Alternatives considered:** forcing quarter extraction from the 10-Q HTML via the IR downloader for the lagged quarters (rejected — the whole point of the batch-53 note is honesty about the feed lag; synthesizing quarters from non-companyfacts sources would break the single-source-of-truth extraction contract and the batch-48 futility accounting).

**Carried follow-ups rechecked:** REGN/EOG/WDAY embedded-release quarters remain by-design unhandled; 71 partial-highlight companies self-heal via the lazy page-view trigger; XOM self-heal still pending (FY2026 10-K, ~Feb 2027); SPG dominant-quarter self-heal waits on the Q4-2026 filing; V/BRK.B/STZ quarterly EPS tagging still unfixable from the feed; HUM/ORCL self-heal on next detail visit via the any-None lazy trigger.

## Batch 96 (2026-10-19) — round-34 seeds (clean audit); `--cohort partial` backfill mode; partial-cohort sweep

**Round-34 hunt:** seeded AXON, KMX, FAST, MSCI, LDOS, TT (8 quarters each, strictly descending ends, descriptions 6/6, highlights 8/8 at seed, no pending-filing notes, no balance-sheet identity gaps >2%, no diluted>basic inversions). Forensics confirmed suspicious values as filer-real or derived-honest: KMX FY2026Q4 eps_d=−0.8618 derives from the 10-K annual diluted EPS 1.68 minus Q1–Q3 (CarMax's Q4 FY2026, ended 2026-02-28, was a real ~$120M net-loss quarter — FY NetIncomeLoss $247.29M vs Q1 alone $210.38M, filed 2026-04-15); AXON FY2025Q3 −0.03 is a loss quarter with diluted=basic (normal, not an inversion — my 1.001-ratio checker flags it, the real clamp does not). LDOS's seed printed two ancient split rescale detections (2013-12-10 ×4.0, 2014-03-27 ×4.0195) — pre-window facts only, no current impact.

**ASML rejected at the door (by design):** `fetch_and_persist` raised `UnsupportedFilerError` — ASML reports in EUR and files 20-F instead of 10-Q/10-K. The route renders the plain-language 404 ("This company reports in EUR; files 20-F, 20-F/A instead of 10-Q/10-K — Tickerlens covers US-GAAP filers reporting in USD with quarterly 10-Q/10-K filings.") — verified live on :8123. No code change needed; the guard works as specified. TSM would fail the same way (not seeded).

**Fix (`scripts/backfill_disclosures.py`):** new `--cohort partial` mode with `_partial_highlight_tickers` (some-but-not-all quarters carrying highlights; `"[]"` counts as empty, matching `_filled_count`). This closes the long-carried "partial-highlight companies self-heal via the lazy page-view trigger" follow-up *actively* instead of passively — the trigger does work (the cohort drifted 71→70 between batches via page views), but the sweep finishes the job.

**Sweep (background run, 71 partial companies, unbounded, per-ticker never-raise):** 11 rescued to 8/8 (TGT +7, HON +6, SHW +6, ROST +5, FDX +4, EL +3, BKNG +3, AWK +2, COF +1, DE +1, LUV +1); 60 unchanged (no exhibit discovered/extracted). Partial cohort 71 → 60; 192 companies now at 8/8 highlights; zero-highlight cohort stays at 0. DB at 252 companies.

**Alternatives considered:** running the sweep inline in the foreground (rejected — 11 minutes, and the batch had other work); extending the zero selector's `"[]"` semantics to match (rejected — pre-existing behavior, changing it would alter which companies the default cohort picks; documented in the new test instead); seeding TSM as the ASML replacement (rejected — same 20-F filer class).

**Tests:** 3 new — partial selector includes only 1–7-filled companies (zero/full/"[]"-only/rowless excluded), zero selector still excludes partials (with the "[]" semantics note), CLI flag choices. Full suite 798 green (795 + 3), `git diff --check` clean.

**Blast radius:** script-only change plus seed data; default cohort behavior byte-identical (verified: zero-selector green unchanged, and the `--cohort partial --limit 2` dry run hit the same ABT/ACN it targeted). No valuation, route, template, or schema changes.

**Live:** dev server restarted at batch start (was down). 14/14 routes 200 (6 new overviews + 6 new details + /calendar + ASML 404). TGT/HON detail pages render the rescued highlights. Valuations render for all 6 seeds (peg: AXON Strong Sell −95.0%, KMX Strong Sell −68.4%, FAST Strong Sell −42.3%, MSCI Hold +2.0%, LDOS Strong Sell −32.0%, TT Strong Sell −77.3%) — clamp-bound where applicable per the batch-40/45 honesty class. No template change (backend-only); screenshot gate N/A.

**Carried follow-ups rechecked:** 60 partial-highlight residuals (likely embedded-release quarters like REGN/EOG/WDAY, EDGAR-lagged quarters, or undiscovered exhibit conventions — next batch's forensic target); XOM self-heal still pending (FY2026 10-K, ~Feb 2027); SPG dominant-quarter self-heal waits on the Q4-2026 filing; V/BRK.B/STZ quarterly EPS tagging still unfixable from the feed; pending-filing cohort at 17 (batch-95 verified); HUM/ORCL self-heal on next detail visit via the any-None lazy trigger.

## 2026-10-19 — batch 97: earnings 8-K matching is a three-guard problem

Matching a 10-Q/10-K to its earnings-release 8-K cannot be done on date proximity alone. Four real counterexamples forced a three-guard rule:
- **PNC** filed a 2.02 investor-conference 8-K (11-07) *after* its 10-Q (11-03), nearer the filing date than the earnings 8-K (10-15) → guard: candidates must be filed ≤ the 10-Q/10-K filing date.
- **Tesla** furnishes production/deliveries under 2.02 two days after quarter end, three weeks before the earnings 8-K → guard: candidates must be filed ≥7 days after period end (books can't be closed sooner).
- **OXY** filed a "pre-earnings" 2.02 8-K (10-09) before the real earnings 8-K (11-12) → "earliest" alone picks the pre-release; nearest-to-filing (with the two guards) picks correctly.
- **FDX** filed a recast-supplement 2.02 8-K after the earnings 8-K → the ≤ filing-date guard excludes it.

Final rule: candidates are 2.02 8-Ks filed 7–60 days after period end and not after the formal filing; nearest to the filing date wins. The audit (252 companies) confirmed only PNC and FDX had wrong content stored; both were cleared and re-filled.

Related: EDGAR submissions bucket pagination is required for both 10-Q/10-K discovery (high-volume filers' "recent" bucket holds < n_quarters) and 8-K coverage (an 8-K can sit in an older bucket than its 10-Q); and discovery must extend to the oldest *stored* period, not just the latest N filings, because the stored window lags submissions when companyfacts is behind.

## 2026-10-19 — batch 98: CIK successions need a curated map, and fact-merge dedupe must key on (start, end, accession)

SEC moved XOM's ticker to a new CIK (0002115436, "ExxonMobil Holdings Corp") — the ticker map resolves there, and the new CIK's companyfacts starts at the succession. Proven the same economic entity (not a batch-47-class misattribution) by two independent facts: the Q2-2026 10-Q accession 0000034088-26-000093 is attributed to *both* CIKs in their submissions feeds, and the new CIK's Q2-2026 revenue ($116.0B) continues the old CIK's consolidated run rate. So the fix is a curated `_CIK_SUCCESSIONS` map (human-verified entries only, like the batch-58 DBA alias map), not auto-detection from accession prefixes — prefixes also differ for filing agents (Donnelley's 0001193125), so a generic detector would merge wrong entities.

Two implementation lessons:
- **Dedupe key needs the start leg.** One 10-Q files both the standalone-quarter fact and the YTD fact for the same period end (Q2 = 6M − Q1 derivation needs both). An (end, accession) key silently dropped the YTD leg and killed every Q2/Q3 derivation — the merged extraction returned Q1/Q4-only quarters. Caught by the live re-seed probe before commit; (start, end, accession) fixed it.
- **Keep the merge a module-level function, not a client method.** The service tests stub the EDGAR client with a bare MagicMock configuring only `companyfacts`; a new client method auto-mocks to an empty payload and broke 14 tests. `companyfacts_with_predecessors(client, cik)` takes any client-like object and the mocks keep working unchanged.

Related: the disclosure pipeline's `discover_earnings_filings` still reads only the current CIK's submissions — XOM's pre-Q2-2026 earnings 8-Ks live under the old CIK, so its older quarters' press-release highlights need a predecessor-submissions merge (carried follow-up, not this batch).

## 2026-10-20 — batch 99: disclosure discovery merges predecessor-CIK submissions, and every filing carries its source CIK

**What:** `discover_earnings_filings` now fetches the predecessor-CIK submissions feeds (from the batch-98 `_CIK_SUCCESSIONS` map) alongside the current CIK's; each extracted filing/8-K carries `src_cik`, accession collisions across feeds dedupe to the current CIK's copy, and `EarningsPeriod` carries `sec_cik`/`er_cik` so `_find_ex99_doc`, `sec_doc_url`, and `er_doc_url` build archives URLs under the filing's own source CIK.

**Why:** The batch-98 companyfacts merge fixed XOM's quarterly figures (2 → 8 rows), but its pre-Q2-2026 earnings 8-Ks — and therefore 7 of 8 quarters' press-release highlights — live only under the predecessor CIK's submissions feed, invisible to discovery. The archives path is per-CIK (`/Archives/edgar/data/34088/...`); building it with the current CIK 404s, so the source CIK must travel with each filing.

**Alternatives considered:** Deriving the CIK from the accession prefix (e.g. `0000034088-26-000101` → 34088) — rejected: accession prefixes also differ for filing agents (Donnelley's 0001193125), so a generic derivation would misroute agent-filed exhibits; the explicit `src_cik` tag is always the feed the filing was actually listed in. Within-source dedupe — rejected: a CIK's buckets are disjoint from its recent block, so the first dedupe form (which also deduped within a source) broke the batch-97 pagination test on fixture accession reuse; dedupe applies across sources only.

**Related:** predecessor fetches are best-effort (log + skip) so a dead old feed never breaks the current CIK; each source pages its own bucket list independently.

## 2026-10-20 — batch 100: cover-page title blocks need a skip, and headline joins need a section-heading stop

**What:** Goldman Sachs' ex-99.1 opens with a cover page (period title + "Earnings Results" + inline contacts + masthead + repeated banner) before the real headline. The fix (`_cover_block_headline` in `data/filings.py`) triggers only on the full cover shape — period title, kind line, a Media/Investor-Relations contact line carrying a phone number, and a banner repeating the period words, all within 12 lines — then skips past the banner and joins the real (often mid-phrase-wrapped) headline with a section-heading stop.

**Why this shape:** the trigger's narrowness is the safety. A period title alone ("Second Quarter 2026") also appears as a legit headline in other filers' docs; requiring the contact-with-phone + banner repeat keeps the fire rate at exactly the cover layout. Four title wraps observed across GS's Workiva/Donnelley vintages are all handled ("Second Quarter 2026"; "Full Year and"/"Fourth Quarter 2025"; "Full Year"/"and"/"Fourth Quarter 2024"; "Third Quarter"/"2024").

**Two extraction principles:**
- A headline continuation candidate that is itself a table fragment ("Financial Summary") is the metric-table heading, not headline — but $-/%-bearing fragments never stop the join, because real headline continuations carry figures ("Share of $20.98 ..."). This is deliberately narrower than the batch-91 wrap-tail rule and lives only in the cover path; `_join_wrapped_headline` is untouched.
- A short table heading ("Book Value Per Share") directly above 2+ fragment rows is table residue: `_drop_table_fragment_runs` now folds it into the run so a heading + its last row drops as one 3-line run instead of leaking into the lede. 1–2 fragment runs with no heading are still kept (batch-97 behavior).

**Alternatives considered:** extending `_join_wrapped_headline` to join mid-phrase wraps globally — rejected: the batch-91 design deliberately limits it to conjunction/preposition breaks so a genuine short headline never swallows the lede; the cover path is the only place we *know* the next lines are headline. Deriving the real headline from the banner text — rejected: the banner ("SECOND QUARTER 2026 EARNINGS RESULTS") is not the headline.

**Related:** closes the batch-97 "GS cover-page extraction" follow-up; GS backfilled 6/8 → 8/8 (the 2 previously-None quarters rescued by current discovery). Still open: HAL business-vs-financial highlights priority; SHOP 6-K discovery (foreign filers).

## Batch 102 — financial-density ranking of highlights candidates
- The leading bullet block and every "Highlights" section compete on financial density rather than position: score (1, count) when ≥2 figure lines and ≥40% of lines carry financial markers (`_FINANCIAL_LINE_RE`: $/% amounts or revenue/EPS/margin/cash-flow/dividend/repurchase keywords), else (0,0); earliest candidate wins ties. Preserves the old first-match behavior exactly when nothing is financial.
- A wrapped bullet continuation is part of the item unless it closes with terminal punctuation and the next line isn't a bullet — that shape is the dateline paragraph. This is deliberately narrow: it only affects the leading-bullet block, not the lede fallback.

**Alternatives considered:** preferring the *headed* "Financial Highlights" section by name match over the leading block — rejected: Halliburton never heads its financial bullets; position + density generalizes to any filer that front-loads figures. Penalizing guidance-forward lines ("expect", "outlook") — deferred: no live case needs it yet.

**Related:** closes the carried "HAL business-vs-financial highlights priority" follow-up; HAL backfilled 8/8 financial-led.

## 2026-10-20 — Batch 103: 6-K earnings-release discovery for foreign filers

**What:** `discover_earnings_filings` now anchors quarters on earnings-release 6-Ks when no 10-Q/10-K covers the report date, and the non-2.02 fallback considers 6-K filings as release candidates — with the 6-K's primary doc (the cover form) excluded from the exhibit pick, the period reference checked against the primary-doc name as well as the exhibit name, and equidistant ties broken toward the most release-named primary doc.
**Why:** SHOP's Q3-2024 quarter was unreachable: its quarterly filing sits beyond the submissions feed's recent window (no paginated buckets), while its earnings release sits in the feed as a 6-K. Foreign filers furnish earnings on 6-K with an empty `items` field, so the entire 8-K-keyed pipeline was blind to them — and a naive pick would have taken the press-release-named 6-K cover form (or the results-tables 6-K's financial-statements 99.1) instead of the real release (`a3pr.htm`).
**Alternatives considered:** synthesizing periods from 6-K reportDates without a formal anchor — rejected: the anchor integrates with the existing period_end matching, FY labeling, and source-string machinery. Treating the 6-K primary doc as the release — rejected: it is the cover form; the release is always the EX-99.1 exhibit. Requiring only a quarter token in the primary-doc name (no month-end guard) — rejected: event-dated 6-Ks (dividend declarations) can carry quarter tokens; the month-end requirement keeps them out.

**Related:** closes the carried "SHOP 6-K discovery (foreign filers)" follow-up; SHOP backfilled 7/8 → 8/8. Still open: GEV footnote-definition headline wart; STZ table-row wart; pending-filing cohort at 17; partial residuals at 4 (AFRM, LIN image-only; CCI no Q4-2024 8-K; SKYD pre-merger).

## 2026-10-20 — Batch 104: footnote-definition legend lines are never headline material

**What:** new `_FOOTNOTE_DEF_RE` in `data/filings.py`, skipped in the headline pass and the lede pass of `extract_press_release_highlights`; `_ADMIN_LINE_RE` extended with bare `^page\s+\d+$` and lone `^news$`.

**Why:** GEV's Workiva ex-99 opens with a footnote legend block (`1 Defined as remaining performance obligation (RPO)` / `*Non-GAAP Financial Measure` / `Page 1`) before the real headline, and the numeric definition line was being stored as the headline — a visible defect on the detail page. `_LEDE_FOOTNOTE_RE` only matches parenthesized markers (`(a)`, `(1)`), so bare-key definitions were invisible to every skip rule.

**Two implementation lessons:**
- **A fix's blast radius must be scanned against the DB before commit.** The scan found SO's Q2-2024 exhibit carrying the same Workiva header shape: skipping bare "Page 1" alone would have promoted the lone "News" kicker to headline (strictly worse than "Page 1"). The `^news$` admin addition was a discovered requirement, not a design choice — and it rescued SO's real headline ("Southern Company reports second-quarter 2024 earnings"), which no previous pass had ever reached. The scan pattern: match the new skip regexes against stored headlines (1 hit: the GEV wart) and first-lines (2 hits: GEV, SO) before writing the repair.
- **The definition verb is the guard, not the number.** `^\d{1,3}\s+` alone would swallow numeric-opening headlines; requiring `(defined as|represents|includes|excludes|reflects)` keeps "2025 outlook raised", "1Q26 record quarter", and "1 billion in buybacks" safe. Same principle as the batch-100 cover-block narrowness: the trigger's narrowness is the safety.

**Related:** closes the carried "GEV footnote-definition headline wart"; live repair cleared and re-filled GEV Q2 FY2025 + SO Q2 FY2024. Still open: STZ table-row wart (metric-table-as-highlights — deliberately deferred: real headline + real figures, a separate quality class); pending-filing cohort at 17; partial residuals at 4 (AFRM, LIN image-only; CCI no Q4-2024 8-K; SKYD pre-merger).

## 2026-10-21 — Batch 105: contact-block residue headlines
**Decision:** Treat contact-block residue as a headline-quality defect class, not just a skip-logic gap. A DB-wide scan (not just the seed tickers) found 248 affected quarters, proving the extractor's contact handling had systematic blind spots across ~48 tickers.
**Rationale:** The batch-104 lesson (blast-radius scan before repair) applied again — the seed tickers (PGR/NKE) were symptoms, not the disease. Fixing the code without the DB scan would have left ~200 stale rows.
**Consequence:** Live repair is now a standard batch tool for extractor fixes. The repair script only overwrites when the new headline differs (None never overwrites, except for deliberate unparseable-page-line clears), making it safe to re-run.

## 2026-10-21 — Batch 106: headline-fragment defect classes from round-35 seeds

**What:** Four new headline-quality defect classes fixed in `data/filings.py`, surfaced by seeding MRK/EMR/FCX/DOW/URI/CNC: (1) verb-fragment headlines (`_HEADLINE_VERB_TAIL_RE` — a headline ending with a headline verb is a company+verb fragment; join the continuation); (2) dash-wrapped page numbers (`- 1 -`, `-`, `1 -`, `- 1`) as admin lines; (3) suite-address masthead residue (`_SUITE_ADDRESS_RE`); (4) split-kicker residue (`Release`/`Press` alone, lone comma). Plus: `_join_wrapped_headline` iterates (max 3) for multi-line headlines; comma-wrap signal; `&`/`–`/`—` match without `\b` in the wrap-tail (the `\b` never fires between space and `&`); 140-char continuation cap (was 100); trailing-comma strip on picked headlines.

**Why:** 58 quarters had verb-fragment headlines (`Freeport Reports` ×8, `Walmart Reports` ×7, `GRAND CANYON EDUCATION, INC. REPORTS` ×8, etc.), 6 had suite-address headlines, 3 had page-number headlines — all visible on company pages. The batch-91 wrap-tail design (conjunction/preposition breaks only) couldn't handle company+verb fragments, which are the most common wrap shape in the wild.

**Two implementation lessons:**
- **A fix's blast radius must be scanned before AND after repair.** The first repair pass wrote 3 bad values (`1 -` → `1 -` still junk; `WM Announces Fourth Quarter and` truncated; `Merck &` fragment) because the fixes were incomplete. Each bad value forced a code refinement (page-fragment patterns, join iteration, `&` without `\b`). The repair script's "overwrite only when different" is not enough — a second pass must verify the NEW values aren't also junk.
- **The `\b` word boundary doesn't work for symbols.** `\b&\s*$` never matches `Merck &` because there's no word boundary between space and `&`. Symbols (`&`, `–`, `—`) must match without `\b`; words keep `\b` on both sides so `Anderson` doesn't match `and`.

**Related:** Closes the batch-105 `WMT fragment wraps` follow-up (7/7 WMT quarters fixed). Still open: STZ table-row wart; UAL/INTC company-name headlines; PLUG/CB fragments; pending-filing cohort at 20 (verified systematic EDGAR lag, not our bug); partial residuals at 4.

## 2026-10-21 — Batch 107: APH/EFX extraction defects from round-36 seeds

**Decision:** Four extraction fixes in `data/filings.py`, all surfaced by seeding COP/APH/CARR/EFX/BKR/ED: (1) bullet-led lines are prose, not table rows — `_looks_like_financial_table` no longer counts •/●/- lines toward the data_rows >= 4 threshold (Amphenol's narrative bullets each carry $ and %); (2) `_skip_bare_masthead_name` — a ≤3-word non-headline-shaped candidate is a masthead when a headline-shaped line follows within 6 lines past admin/residue/labels with ≥1 residue line seen; verb-tail/wrap-tail candidates are excluded (they belong to `_join_wrapped_headline`); (3) `_join_wrapped_headline` also joins when the next line opens with and/or/but (mid-phrase wrap, mirror of the wrap tail); (4) full street addresses (house number + ZIP) are `_ADMIN_LINE_RE` — Equifax's 50-char address cleared the 48-char masthead-residue bound.

**Rationale:** The batch-97 financial-table guard was built for Lilly/WM tables (no bullets); Amphenol's bullets are the first narrative section dense enough with $+% to trip it. The 48-char residue bound is load-bearing for short headlines, so long addresses needed their own precise pattern rather than a bound relaxation.

**Blast-radius method (batch-106 lesson applied):** old-vs-new extraction compared on AAPL/JPM/LLY/WM/MRK samples — all 5 identical. The 924-test suite (including batch 97–106 headline regression tests) is green. The DB-wide scan's 149 flagged headlines are pre-existing classes ('EARNINGS RELEASE', 'EXHIBIT-99.1', 'INVESTOR RELATIONS:'), not regressions — recorded as carried follow-ups.

**Pending-filing recheck lesson:** a naive "any fact with end=2026-06-30" check false-positived on 424B2 fee facts, DEF 14A proxy tables, and S-4 registration fees. The revenue-duration-facts check in `_pending_filing_note` is the correct ground truth — a recheck must use it, not raw fact existence.

**Related:** APH 2/8 → 8/8 highlights, EFX 8/8 headlines fixed. Still open: STZ table-row wart; UAL/INTC company-name headlines (no clear headline in doc); PLUG/CB fragments; pending-filing cohort at 22; partial residuals at 4; Wikipedia 403s; 149 pre-existing junk-headline shapes.

## 2026-10-21 — Batch 108: ordinal-tail headline fragments from round-37 seeds

**What:** Three headline-fragment fixes in `data/filings.py`, surfaced by seeding XEL/PCG/SRE/PPL/PEG/ETR and hunting the carried PLUG/CB fragment follow-up: (1) `_HEADLINE_ORDINAL_TAIL_RE` — a headline ending on First/Second/Third/Fourth/Full is a wrapped fragment (never a complete headline); the continuation joins under the standard guards. (2) Quarter-tail + bare-year — "{ordinal} Quarter"/"Full Year" followed by a bare `20\d{2}` year joins, bypassing the digit-lead guard for this exact shape only (the year is never a lede start). (3) The 1-word fragment join and company-name+verb-lead join now feed their joined fragment through `_join_wrapped_headline` instead of breaking immediately — previously "Kroger"/"Reports Third Quarter 2025 Results and" stored a dangling "and". Plus: `_skip_bare_masthead_name` returns None on ordinal-tail candidates (batch-107 misfire: "Plug Power Third" read as masthead, "Quarter 2025 Highlights" as residue, "$177M..." picked as headline).

**Why:** 12 quarters had ordinal-tail fragments (PLUG 1, ICE 8, KR 3) and 4 had dangling wrap tails from the fragment joins — all visible on company pages. The batch-105 1-word join and batch-107 masthead skip were each built for a narrower shape; the ordinal tail sits exactly at their intersection (a ≤3-word fragment that is neither masthead nor complete headline).

**Blast-radius method (batch-106 lesson applied):** old-vs-new extraction compared on 16 good exhibits (AAPL/JPM/LLY/WM/MRK/MSFT/NVDA/XOM, 2 quarters each) — 0 diffs. The 933-test suite (including batch 91–107 headline regression tests) is green. The repair's "overwrite only when different" plus a second repair pass verified no new junk values (the first pass wrote 4 dangling-"and" values, which the continuation fix then corrected — the batch-106 "verify new values" lesson in action).

**Two more fixes in batch 108:** (4) Xcel address-block masthead — the residue-skip now fires on date lines (and no longer consumes date lines as residue), date+city+ZIP is `_ADMIN_LINE_RE`, and an all-caps ≤3-word line before an all-caps headline is a masthead skip. The numeric-date variant ("10/31/2024 Minneapolis, MN 55401") was caught by re-running the repair and finding 2 quarters still bad — the batch-106 "verify new values" lesson again. (5) Xcel XBRL revenue tag — `RegulatedAndUnregulatedOperatingRevenue` added to the revenue chain; Xcel's `Revenues` went stale in 2019 and the fallback-to-first-non-empty-tag rule had seeded 2017-2019 quarters. XEL deleted and re-seeded to 2024-2026.

**Related:** Closes the batch-105/106/107 `PLUG/CB fragment wraps` follow-up (PLUG 2026Q1 stale "Power Reports..." → "Plug Power Reports..."; CB 2024Q3 stale "Reports Third..." → "Chubb Reports Third..."). Still open: STZ table-row wart; UAL/INTC company-name headlines; CB "Core" 5-line wraps (digit-led continuations, needs a bigger design); pending-filing cohort at 22; partial backfill gaps (PEG 6/8); Wikipedia 403s; 149 pre-existing junk-headline shapes.

## 2026-10-21 — Batch 109: stale company-name headlines repaired; 4 extractor fixes

**What:** A DB-wide scan for company-name-as-headline (46 quarters, 7 tickers) found the stored values were stale extractions — the current extractor recovers the real headline from the same exhibits. Repaired 42 quarters (CPRT 8, UAL 8, PCAR 7, CAT 6, INTC 6, RSG 2, C 5), each new headline verified against its exhibit before writing (batch-106 lesson). Four fixes in `data/filings.py`: (1) department lines ("Public Affairs Department") are masthead residue — end-anchored, ≤4 words, masthead-context only; (2) `_skip_masthead_block` stops at contact headers so the contact-header branch handles the block; (3) trailing ";" is a wrap-tail signal (RSG); (4) `_COMPANY_NAME_LINE_RE` accepts an optional "(NYSE: C)" ticker parenthetical (Citi).

**Why:** "United Airlines" / "Intel Corporation" / "PACCAR Inc" as headlines hid the real release headlines ("United Posts Q2 Results Above Wall Street Expectations...", "PACCAR Increases Quarterly Revenues and Profits", "FIRST QUARTER 2024 RESULTS AND KEY METRICS"). The batch-108 carried note said UAL/INTC had "no clear headline in doc" — live exhibit inspection proved that wrong; only BRK.B genuinely has no headline.

**Deliberately excluded:** BRK.B (8 quarters) — its release has no headline; the current code picks the dateline "Omaha, NE (BRK.A; BRK.B) –", which is not better than the stored company name. Suppressing dateline-as-headline is a design decision (it affects the no-headline fallback path), not a quick fix. PCAR 2026-03-31 has no ex-99 exhibit; old value kept.

**Blast-radius method:** old-vs-new extraction on cached exhibits via git stash — only the two intended changes (PCAR, Citi). 941-test suite (5 new) green. 7 company pages + 2 detail pages HTTP 200; repaired headlines render.

**Related:** Closes the batch-105/106/107/108 `UAL/INTC company-name-as-headline` follow-up (plus PCAR/CPRT/CAT/RSG/C variants). Still open: BRK.B no-headline design; STZ table-row wart; CB "Core" 5-line wraps; SRE tail fragments; 149 junk-headline shapes.

## 2026-10-21 — Batch 110: document-label headlines repaired; 7 extractor fixes

**What:** A DB-wide scan of the 149 pre-existing junk-headline shapes surfaced the document-label family — 91 quarters across 13 tickers whose stored headline was an exhibit/document label (AMGN/BNY/DIS/KMB/NOC 'EARNINGS RELEASE', MA 'Earnings Release', ELV spaced-letter label, BAC 'THE PRESS RELEASE', APD/C 'EXHIBIT-99.1' + Citi 'ECHIBIT' typo, TMUS 'TMUS EXHIBIT 99.1', CVX 'FOR RELEASE AT … EXHIBIT 99.1', TJX '<name> FOR IMMEDIATE RELEASE', DIS date-lines). Seven fixes in `data/filings.py`: spaced-letter earnings label, ticker/date-prefixed label, generalized "Earnings Release" branch (unconditional skip — the batch-105 headline-shaped-next-line guard left Amgen/Northrop broken), exhibit-marker dash/ticker-prefix/typo variants, name-prefixed FOR IMMEDIATE RELEASE, pre-headline address-block shapes (city/ST ZIP, telephone, street), and `_MAX_HEADLINE_CHARS` 220→300 (TJX's genuine 243-char headline was unpickable). Repaired 82 quarters (all new headlines verified pre-write; second pass clean) and cleared BAC ×8 to None (slide decks — the batch-105 page-lines steady state).

**Why:** These labels hid real headlines on major-company pages ("Mastercard Incorporated Reports Third Quarter 2024 Financial Results", "AMGEN REPORTS…", "T-Mobile Delivers…"). The label family shares one shape — exhibit metadata before the release headline — so one batch fixes the whole class.

**Blast-radius method (batch-106/108 lesson applied):** old-vs-new extraction on 16 good exhibits via git stash — only the 2 intended ELV changes. Two regressions caught by the suite mid-batch: the `\s*` spaced pattern also matched unspaced "Earnings Release" (a `_skip_toc` entry title) — narrowed to `\s+`; the new address patterns reclassified Amphenol's residue lines as admin, defeating `_skip_bare_masthead_name`'s `saw_residue` guard — the residue check now runs before the admin check there. The 951-test suite (10 new) is green. A second repair pass confirmed the writes (84/84 idempotent skips on re-run).

**Related:** Closes the batch-109 `C 'EXHIBIT-99.1'/'ECHIBIT 99.1'` follow-up and most of the 'EARNINGS RELEASE'/'Earnings Release' classes. Still open: BRK.B no-headline design; STZ table-row wart; CB "Core" 5-line wraps; SRE "2025 Results" head-fragments; contact/address/tagline junk-headline classes (~180 quarters); pending-filing cohort at 22; partial residuals; Wikipedia 403s.

## 2026-10-22 — Batch 111: contact-class junk headlines repaired; 2 extractor fixes

**What:** A DB-wide re-scan (82 → 40 suspicious) surfaced the contact-header/contact-name family: 43 quarters across QCOM, BLK, HCA, HLT, DUK, RMD whose stored headlines were contact-block residue. Live-exhibit probes showed HCA/HLT/DUK/RMD were stale extractions (current code already fixed them); QCOM 'Qualcomm Contact:' and BLK 'INVESTOR RELATIONS:' were still broken. Two fixes in `_CONTACT_HEADER_RE` (`data/filings.py`): (1) company-name-prefixed header without the word "Company" (`|^[\w&.,'\-\s]{1,80}\s+contacts?:\s*$` — the batch-105 branch required "... Company Contact:"); (2) bare role labels allow a trailing colon (`^(investor relations|corporate communications|media relations):?$`).

**Why:** These residue headlines sat on major-company pages (every BlackRock and Qualcomm quarter). Both branches are full-line anchored — a real headline never ends with "Contact(s):" and never IS "Investor Relations:" — so the fire rate stays narrow. HCA's back-to-back 'INVESTOR CONTACT:'/'MEDIA CONTACT:' block needed no new code: `_skip_contact_block`'s batch-105 email/phone lookahead already consumes it (verified on the live exhibit before deciding not to add a special case).

**Blast-radius method:** old-vs-new extraction on 18 good exhibits via git stash — 0 diffs across 36 quarters. The one regex sanity "mismatch" during development (Hilton's 'Investor Contact 7930 Jones Branch Drive') turned out to be expected pre-existing behavior (an existing test requires that shape to be skipped) — checked before dismissing.

**Related:** Closes the batch-110 `contact/address-block junk-headline classes` follow-up's contact family. Still open: STZ table-row wart; BRK.B no-headline design; CB "Core" 5-line wraps; SRE "2025 Results" fragments; 40 residual junk-headline shapes (ROST rules, TFC backtick, VZ image names, XYZ period labels, taglines); pending-filing cohort at 22; partial residuals; Wikipedia 403s.

## 2026-10-22 — Batch 112: no-headline design decision (dateline is never a headline)

**What:** Resolved the batch-109 carried design question: when an earnings release has no headline (Berkshire Hathaway's releases: company name + "NEWS RELEASE" + date + dateline, then the lede), the stored headline is **None** — not the company name (old code) and not the dateline (pre-fix code). The extractor now recognizes a dateline (`_DATELINE_RE`: city + state/country with optional date/parenthetical tickers, trailing dash) and stops the headline scan there with headline=None; the lede starts after the dateline. Also generalized the batch-110 "Earnings Release" document-label branch to quarter-prefixed variants ("FIRST QUARTER 2026 EARNINGS RELEASE"), which had become the headline on BRK.B's Q1 2026 quarter.

**Why:** A dateline is release metadata, like the date line already excluded — storing it as the headline was the same class of junk as the contact-block and document-label families. Berkshire's Q2 2025 detail page showed "Omaha, NE (BRK.A; BRK.B) –" as the headline; now it shows the lede ("Berkshire's operating results…") with no headline line, which the disclosure template renders fine (no template change needed — the macro prints body text verbatim).

**Blast-radius method:** old-vs-new extraction on 18 good exhibits via git stash — 0 diffs across 36 quarters for both fixes. The dateline branch only fires when no headline was found first (headline always precedes the dateline in real releases), and the label regex requires a quarter-word + year prefix, so genuine headlines ("X Schedules First Quarter Earnings Release") can't match.

**Related:** Closes the batch-109/110/111 `BRK.B no-headline design` follow-up; extends the batch-110 document-label family. New follow-ups: same-day multi-8-K matching defect (seed picked the succession 8-K over the earnings 8-K for BRK.B 2025-03-31); discover_earnings_filings item-2.02 filter misses some earnings 8-Ks (4 BRK.B quarters had live exhibits the discovery didn't find). Still open: STZ table-row wart; CB "Core" 5-line wraps; SRE "2025 Results" fragments; 40 residual junk-headline shapes; pending-filing cohort at 22; partial residuals; Wikipedia 403s.

## 2026-10-22 — Batch 113: earnings-8-K matching admits post-filing releases; 75-day annual window

**What:** Two fixes in `services/ir_download.py` for earnings-release 8-K discovery, resolving the batch-112 forensic follow-up. The four "missed" BRK.B quarters' 8-Ks all carry Item 2.02 — they were dropped by the batch-97 guards, not the item filter: (1) Berkshire files the 10-Q/10-K a day or two *before* furnishing the earnings-release 8-K, violating the "earnings must predate the formal filing" guard; (2) its FY-2025 release came 61 days after year-end, outside the 60-day quarterly window. New shared `_er_8k_candidate_pools` helper (used by both `_match_8k` and the batch-101 non-2.02 fallback): a post-filing grace pool (1–3 days after the formal filing, only when no pre-filing candidate exists) plus a 75-day period-end window for annual (10-K) periods.

**Why:** The batch-97 guards were built around the PNC/Tesla shapes (a later 2.02 conference 8-K; a 2-day post-period deliveries 8-K) — both still hold: the grace pool is capped at 3 days and only fires with no primary candidate, so PNC's 4-day-post-filing conference 8-K still loses, and the 7-day floor still excludes Tesla's deliveries 8-K. Filers that furnish the real earnings release after the 10-Q (Berkshire's pattern) are rare but real — a flagship ticker silently lost 4 of 8 quarters' release discovery. All 8 BRK.B quarters now discover the exact accessions the batch-112 manual forensic had to locate by hand.

**Blast-radius method (batch-106/108 lesson applied):** old-vs-new `discover_earnings_filings` via git stash on 8 tickers (AAPL/MSFT/JPM/XOM/BRK.B/C/TSLA/PNC) × 8 quarters — the ONLY diffs are the 4 BRK.B quarters going from unmatched to correctly matched. 962-test suite (5 new) green; `git diff --check` clean.

**Related:** Closes the batch-112 `discover_earnings_filings item filter misses some earnings 8-Ks` follow-up (framing corrected: the item filter was fine; the guards were wrong) and the `same-day multi-8-K matching` follow-up — verified as a seed-script artifact, not a production defect: the succession 8-K carries 5.02,9.01 (no 2.02) and can never enter the discovery candidate pool. Still open: STZ table-row wart; CB "Core" 5-line wraps; SRE "2025 Results" fragments; 40 residual junk-headline shapes; pending-filing cohort at 22; partial residuals incl. PEG 6/8; Wikipedia 403s.

## 2026-10-22 — Batch 114: hyper-growth reroute line must not claim EPS growth for no-EPS filers

**What:** In `services/valuation.py`'s sales-fallback, the batch-74 hyper-growth opening line ("TTM EPS growth of X% is outside the PEG model's 40% design range — ... valuing on sales instead") now only fires when `ttm_eps_diluted is not None`. Filers with no usable XBRL EPS facts (KKR, STZ) get the batch-33 honest line ("No per-share earnings to anchor a P/E multiple — valuing on sales instead (less reliable).").

**Why:** The batch-74 comment asserted "per-share earnings exist here" — false when the growth input is the net-income fallback. For KKR the card claimed "TTM EPS growth of 53.7%" with zero EPS facts in the company's filings (53.7% was TTM net-income growth), and implied the PEG path was skipped due to the design range when it was never reachable (it requires per-share EPS to anchor). Same shape on STZ (57.4%). This is the fabricated-signal honesty class from batches 26/36/62 — the model must not invent an EPS growth story, even in a footnote. The valuation numbers themselves are untouched: the margin-anchored sales fallback on real revenue/margin/net-income with Medium confidence is the designed behavior (KKR keeps Strong Buy +35.8%).

**How the no-EPS cohort was verified:** DB-wide scan for companies with no EPS facts in recent quarters: KKR/STZ rendered the false line (fixed); BKR/HSY/V/LEN already rendered the honest line (net-income growth ≤40%, so the hyper-growth branch never fired); OXY is Watch/unavailable; BRK.B is on the book path. ON keeps the batch-74 line — verified genuinely correct (8/8 quarters carry EPS facts; TTM EPS growth 41.3% > 40% is real EPS growth, so the reroute story holds). Companion forensics: HSY's EPS tags stop in 2010, BKR tags EPS annually only, V/STZ/KKR have no standard EPS tags at all — all genuine filer behavior, no extraction defect; the extractor's honest Nones are correct.

**Blast-radius method:** service-level check of all 8 no-EPS-recent companies' valuations — only KKR/STZ changed lines; existing batch-74 tests (which all pass ttm_eps_diluted non-None) unaffected. 1 new regression test; 963-test suite green; `git diff --check` clean; /company/{KKR,STZ,ON} 200 with corrected copy (dev server restarted — the running process had the pre-fix module loaded).

**Related:** Closes the batch-114 seeding-round finding. Still open: STZ table-row wart; CB "Core" 5-line wraps; SRE "2025 Results" fragments; 40 residual junk-headline shapes; pending-filing cohort at 22; partial residuals incl. PEG 6/8; Wikipedia 403s.

## 2026-10-22 — Batch 115: never-headline line guard; contact block must not eat wrapped-headline fragments

**What:** (1) New `_NEVER_HEADLINE_RE` in `data/filings.py`, checked in the headline-pick loop before the masthead-name skip: lines with no alphanumeric characters (Truist's `` ` ``, Welltower's `'`, Ross's underscore rule, Chevron's `\`), single alphanumeric tokens with a digit at 5+ chars (Verizon's `VZQTR20FIN` image filename), page-number + junk-token artifacts (Airbnb's `1 §:)airbnb`), exchange:ticker masthead lines (`NYSE: TRV`), and 1–4-word section labels ending in a colon (`Summary Points:`) are never headlines. (2) `_skip_contact_block` now stops at a wrapped-headline fragment: a line ending on a headline wrap/verb/ordinal tail whose next line is a plausible continuation (Sempra's `Sempra Reports Third-Quarter` / `2025 Results`). (3) `_HEADLINE_ORDINAL_TAIL_RE` / `_HEADLINE_QUARTER_TAIL_RE` cover the hyphenated ordinal-quarter form and `_HEADLINE_YEAR_LEAD_RE` covers year-led continuations. (4) Bullet markers are stripped from picked headlines. (5) `_looks_like_masthead_residue` recognizes exchange:ticker lines.

**Why:** Monkeypatched branch tracing on the live exhibits showed the true failure paths, all different from the stored values' appearance: the punctuation lines were misread as *bare masthead names*, jumping the pick onto contact-detail lines (so the stored `_`/`'`/`` ` `` understated the live damage — the current code produced *new* junk like `Executive Vice President, Senior Vice President, Investor Relations` and `Tim McHugh (419) 247-2800`); Sempra's 3-word headline fragment was eaten as contact detail because it fell below the 4-word/40-char content test. Each pattern is narrowness-guarded (short tickers like `3M`, `2026 Outlook`-shaped lines, real headlines never match).

**Blast-radius method:** old-vs-new extraction via `git stash` on 16 diverse tickers × 120 quarters (AAPL/MSFT/JPM/XOM/BRK.B/TSLA/PNC/C/DUOL/GS/F/AMPH/WMT/KR/RSG/SPG) — **0 diffs**; only the targeted junk shapes change. 10 new regression tests; 973-test suite green; `git diff --check` clean; 8 company pages + 3 detail/data routes 200 with repaired headlines rendering.

**Related:** Closes the carried "40 residual junk-headline shapes" follow-up (plus 7 extra TRV address-line headlines and 3 PLTR bullet headlines the scan missed — 58 rows repaired, 1 cleared). PCAR 2026-03-31's stale `PACCAR Inc` was cleared, not kept: the accession genuinely has no ex-99 exhibit (verified batch 109), so "Not available" is the honest UI state. Still open: STZ table-row wart; CB "Core" 5-line wraps; ABNB heading-less metric table (shareholder-letter metric parse needs a highlights heading); pending-filing cohort at 22; partial residuals incl. PEG 6/8; Wikipedia 403s.

## 2026-10-23 — Batch 116: lone country-name masthead lines are never headlines

**What:** `_NEVER_HEADLINE_RE` in `data/filings.py` gained a full-line-anchored country-name branch (USA/U.S./U.S.A., United States, UK/U.K./United Kingdom, Canada, Mexico, Germany, France, Japan, Ireland, Netherlands, Switzerland, Australia, Singapore, India, Brazil). Also fixed the pick-and-verify discipline note from batch 116 seeding: CHD and WM were already in the DB, so the seed script's OK lines meant idempotent re-persistence, not new coverage — the round-39 report names the 4 genuinely new tickers (FIS, ROK, TROW, WRB).

**Why:** Rockwell's exhibits head the release with a Donnelley masthead — street address, "Milwaukee, WI 53204", then a lone "USA" line — before the "News Release" kicker and contact block. The address lines match admin/contact patterns, but "USA" cleared every guard and became the headline for all 8 ROK quarters. A DB-wide ≤2-word-headline scan (2222 rows) confirmed ROK was the only ticker with this shape; the batch-115 scan missed it because it looked for classified junk shapes, not short ones.

**Blast-radius method:** old-vs-new `extract_press_release_highlights` via `git stash` on 10 diverse tickers × 81 quarters (AAPL/MSFT/JPM/XOM/BRK.B/TSLA/PNC/C/DUOL/GS) — **0 diffs**; the branch only fires on a lone country-name line before the headline pick. Narrowness regression-tested against "U.S. revenue grew 44% year-over-year.", "USA Today Launches Fund", "Canada's Finest Reports Results", "3M", "2026 Outlook".

**Related:** Extends the batch-115 never-headline family (punctuation, filename tokens, page headers, exchange:ticker, section labels). The live repair (8 ROK rows) keeps the family-wide practice: overwrite only on a different non-None headline. Still open: STZ table-row wart; CB "Core" 5-line wraps; ABNB heading-less metric table; pending-filing cohort at 22; partial residuals incl. PEG 6/8; Wikipedia 403s.

## 2026-10-24 — Batch 117: pending-filing note must walk backward for middle-gap filings

**What:** `_quarter_label_for_report_date` in `services/financials.py` now signs the quarter-step count at the call site: forward via `_quarter_steps(newest_end, report_date)` when the filing is newer, backward via `-_quarter_steps(report_date, newest_end)` when it predates the newest stored row, and the newest label itself when the dates are equal. The shared `_quarter_steps` helper in `data/xbrl.py` is unchanged.

**Why:** `_quarter_steps` is forward-only by construction (`max(1, round(days/91.3125))`) — the xbrl sequence repair always passes earlier < later and negates explicitly for the backward case. The note-label call site passed `(newest_end, report_date)` unconditionally, which was safe while notes only ever labeled filings newer than the newest stored row (the classic ingestion-lag shape). Once DOW and URI landed Q3 FY2026 with Q2 still missing, the first middle-gap note computed a −92-day distance, floored it to +1, and walked Q3 forward to "Q4 FY2026" — telling users a Q4 filing existed when the Jul 24 filing was the Q2 10-Q. `_walk_label` already implemented predecessor steps; the call site just never produced a negative count.

**How the cohort was verified:** all 26 stored-note companies were rechecked against live EDGAR companyfacts via the app's EdgarClient — every Q2 FY2026 revenue fact still absent, older quarters present, so no note was stale and none cleared. DOW/URI Q3 filings (Oct 21/23) are ingested and now stored; their notes recomputed to the correct Q2 label on the next page view after a server restart. The deeper data observation (Q3 facts flowing while Q2 facts stay absent) is left as an open question — a YTD-difference derivation could backfill Q2, but that is a new extraction behavior, not a label fix, and was not built here.

**Blast-radius method:** the forward path is byte-identical (same helper call as before); the backward branch is newly exercised by 4 regression tests (backward walk, year-boundary backward walk, same-end label, middle-gap note end-to-end). 978-test suite green; `git diff --check` clean; /company/{DOW,URI} 200 with corrected notes.

**Related:** Closes the batch-117 pending-cohort recheck finding. Still open: STZ table-row wart; CB "Core" 5-line wraps; ABNB heading-less metric table; pending-filing cohort at 26; partial residuals incl. PEG 6/8; Wikipedia 403s; Q2 backfill via YTD-difference derivation (open question).

## 2026-10-24 — Batch 118: verb-tail headlines may join a year-led "Results" fragment; a dateline sentence does not break the leading bullet block

**What:** (1) `_join_wrapped_headline` in `data/filings.py` bypasses the digit-led bad-start guard for the exact shape verb-tail headline + `^20\d{2}\s+Results\b` ("Prudential Financial, Inc. Announces" / "2024 Results"). (2) `_leading_bullet_block` skips a leading dateline-sentence line (`_DATELINE_LEAD_RE`: all-caps location + dash, e.g. "NEWARK, N.J. – ...") before any bullet is collected, so bullets after a dateline sentence still count as the leading block.

**Why:** Seeding Prudential surfaced a two-defect chain. For 4Q24, the refused join left "2024 Results" as the first body line, which killed the leading-bullet detection; the "Financial Highlights" table header then became the whole body, under 200 chars, so extraction returned None and the quarter stored no highlights. For the other quarters, the dateline sentence between headline and bullets had the same bullet-block-killing effect: 2025 Q4 and 2026 Q2 stored the "(in millions, unaudited)" table header as their highlights, 2026 Q1 stored the dateline paragraph. Both guards stay narrow: the year-Results bypass requires a verb tail *and* the word "Results" after the year (a bare year after a verb tail still does not join — the batch-108 negative holds), and the dateline skip fires only before any bullet is collected (a dateline line is never bullet material; mid-block lines keep the existing continuation behavior).

**Blast-radius method:** full-text old-vs-new `extract_press_release_highlights` via `git stash` on 16 tickers × 130 quarters — exactly 4 diffs, all PRU, all improvements (2024 Q4 None → headline + bullets; 2025 Q4 / 2026 Q2 table header → bullets; 2026 Q1 dateline prose → bullets); the other 126 quarters byte-identical. 7 new regression tests; 985-test suite green; `git diff --check` clean; 14 live checks (6 new tickers × overview + detail, PRU detail re-check, MRSH overview re-check).

**Related:** Closes the PRU 7/8 seeding-round finding. Still open: STZ table-row wart; CB "Core" 5-line wraps (other digit-led shapes); ABNB heading-less metric table; pending-filing cohort at 26; partial residuals incl. PEG 6/8; Wikipedia 403s; MMC → MRSH ticker alias (no redirect yet); table-header sections winning when a release has no bullets at all.

## 2026-10-24 — Batch 119: renamed symbols redirect to their current ticker

**What:** `TICKER_RENAMES` (`{"MMC": "MRSH"}`) and `resolve_renamed_ticker()` in `routes/company.py`, plus a `renamed_ticker_redirect` HTTP middleware in `main.py` that 301-redirects GET/HEAD requests for `/company/<old>…` to `/company/<new>…`, preserving the full subpath and query string. POST requests are excluded.

**Why:** A renamed symbol disappears from SEC company_tickers.json, so no fetch path can ever resolve it — /company/MMC 404'd despite Marsh's full history sitting in the DB under MRSH. The 404 page's close-match suggestions are a fallback, not a fix: a user following an old link, bookmark, or search result wants the company, not a "did you mean" page. A 301 (not 302) because a ticker rename is permanent — browsers and search engines should update the URL. Middleware rather than per-route edits because the rename must hold on every company surface (overview, detail, compare, vs, tearsheet, news, downloads) and a single path-parsing site guarantees that; a future rename is one map entry, not N route edits. POST is excluded on purpose: redirecting a watch/unwatch POST would either drop the action or silently act on a different company — both worse than the current 404.

**Blast-radius method:** the middleware's condition is `method in (GET, HEAD)` and `parts[1] in TICKER_RENAMES` — with a one-entry map, exactly one ticker's GETs change behavior; all other requests take the identical `call_next` path. Verified by the unchanged 54-test route file plus 9 new tests (map, 301 + Location for overview/lowercase/subpath+query/vs, non-renamed 404, POST untouched). 994-test suite green; `git diff --check` clean; live 301s verified against the restarted dev server.

**Related:** Closes the batch-118 ticker-alias follow-up (MMC → MRSH). Still open: STZ table-row wart; CB "Core" 5-line wraps; ABNB heading-less metric table; pending-filing cohort at 26; partial residuals incl. PEG 6/8; Wikipedia 403s; table-header sections winning when a release has no bullets at all.

## 2026-10-24 — Batch 120: a discontinued-ops basis break needs restatement proof, not just the 9M-zero → FY-nonzero shape; exhibit "991" also precedes a digit-quarter token

**What:** (1) `_discontinued_basis_break_starts` in `data/xbrl.py` now requires two proofs for a basis break: the 9M 10-Q discontinued-ops zero followed by a nonzero FY 10-K fact (batch 85, unchanged) AND a restatement by the fiscal year's own 10-K of a prior-year annual fact under a primary income-statement tag (new `_tenk_restates_prior_year`, over the discontinued tags plus Revenues, the contract-revenue tag, SalesRevenueNet/GoodsNet, NetIncomeLoss, both EPS tags, and OpCF). The year's own 10-K is identified as the earliest 10-K to file an annual fact for that start — later 10-Ks file the same period only as comparatives. (2) `_release_name_rank` in `services/ir_download.py` accepts `991` before a digit-quarter token (`[1-4]q\d`), covering Cincinnati Financial's `exhibit9911q25.htm` shape.

**Why:** (1) Verisk proved the batch-85 trigger over-fires. Its FY2024 shows the exact OXY shape — 9M discontinued-ops $0 in the 10-Q, FY $6.8M in the 10-K — but the $6.8M is a residual gain on the Energy business discontinued in 2022 and presented as discontinued "for all periods presented" ever since, so the 2024 10-Q and 10-K continuing revenues sit on the same basis; the Q4 2024 earnings release reports $736M, exactly FY − 9M. The batch-85 trigger alone cannot distinguish a reclassification (OxyChem, newly discontinued in the 2025 10-K) from a residual gain on an already-discontinued business. The restatement proof can: a 10-K that re-presents history restates prior-year annual facts — OXY's 2025 10-K restated FY2024 Revenues $26,725M → $22,019M — while a 10-K with no re-presentation leaves comparatives untouched — VRSK's FY2023 revenues, NI, EPS, and OpCF are byte-identical across the 2023/2024/2025 10-Ks. The own-10-K dating matters independently: the old latest-wins pairing let the 2025 10-K's $1,364M FY2023 comparative masquerade as OXY's FY2023 fact, manufacturing a FY2023 "break" from 2023 10-Q zeros even though the 2023 10-K itself tagged $0 and restated nothing. Deliberately no materiality floor (the batch-85 reasoning stands — an income-based floor cannot bound a revenue error, since a low-margin component's 9M revenues can dwarf its income). (2) CINF's 99.1 exhibits concatenate the quarter digit directly after 991 for Q1–Q3 (`9911q25`, `9912q25`, `9913q25`) while Q4 uses the plain quarter marker (`991q424`); the old lookahead covered `q\d`, separators, and letters but not a digit-quarter token, so discovery matched the 8-K but found no exhibit for six quarters. The 99.2 mirrors (`9921q25`) still never match — they carry 992, not 991 — and the `doc9912final.htm` negative still holds (`2final` is not a quarter token).

**Blast-radius method:** basis-break sets compared pre/post across 23 tickers (VRSK, OXY, the standard 16, all 6 new seeds) — only VRSK FY2024 (intended: derives $735.6M) and OXY FY2023 (correct: out-of-window, and the old value was a latest-wins artifact) changed; C's 2018/2019/2023 and HAL's 2017 breaks unchanged. OXY FY2025 still breaks (Q4 FY2025 revenue honestly None on the live detail page). Exhibit-rank change verified by the CINF discovery probe (all 8 quarters resolve to their 99.1 exhibits) plus the full ir_download suites. 3 new regression tests; 997-test suite green; `git diff --check` clean; live pages verified (VRSK Q4 FY2024 $735.6M in detail chart data, CINF 8/8 highlights, MMC 301).

**Related:** Still open: STZ table-row wart; CB "Core" 5-line wraps; ABNB heading-less metric table; CINF subsidiary-list prefix + trailing quote fragment in highlights (cosmetic); MTB address-line prefix in highlights; OXY Q4 FY2024 stored revenue $2.054B is a mixed-basis derivation (2025 10-K restated FY2024 Revenues while 9M 2024 stayed $19,965M — needs a derivation-vintage rule with a DB-wide derived-Q4 blast-radius pass); pending-filing cohort at 26 + VRSK Q2 2026; partial residuals incl. PEG 6/8; Wikipedia 403s; table-header sections winning when a release has no bullets at all.

## 2026-10-24 — Batch 121: Q4 derivation must pair facts by vintage — a restated annual pairs with an unrestated 9M only

**What:** `_derive_q4_income` (and the cash-flow un-cumulation in `_cash_flow_series_for_tag`) now derive Q4 from the contemporaneous pair when the year's annual fact was restated by a later filing but the 9M fact was not: the FY leg is replaced by the year's own-10-K value (earliest-filed 10-K annual fact for that start, `_own_tenk_annual_value`) while the 9M leg stays. When the 9M was itself restated (earliest-filed 9M value for that end, `_own_ytd_value`, differs from the latest-wins value), no substitution happens — the latest legs already pair consistently. The NI annual in the EPS share-implied path gets the same per-pair treatment. `_values_differ` fences split-rounding noise by comparing at the coarser filing precision.

**Why:** Latest-wins dedup pairs a restated FY with an unrestated 9M whenever a later 10-K restates a prior-year annual — and prior-year restatements turn out to be common, not exceptional. OXY is the demonstrated case (FY2024 Revenues $26,725M → $22,019M ex-OxyChem; 9M $19,965M untouched; old derivation $2,054M vs as-reported $6,760M), and the DB-wide pass found 757 such value diffs across 220 of 292 companies, including AAPL Q4 FY2008 (old NI $2,421M vs as-reported $1,136M; old diluted EPS $2.68 vs as-reported $1.26). The first, unrefined version of the rule substituted unconditionally — and the AAPL trace caught it over-firing: FY2013's annual AND 9M were both restated onto the post-split basis, so substituting the own-10-K annual mixed bases the other way and failed the coherence check, deleting a good derived row. The refined gate (annual-restated AND 9M-not-restated) is the correct pairing rule: it asks whether each leg is on the old or the new basis and only repairs the mixed pairs. Split-rounding tolerance is needed because the split rescale leaves the own-10-K value a rounding step from the filed latest value (NFLX 7.19/10 = 0.719 vs filed 0.72); the blind spot is bounded at half the coarser precision unit (≤5¢ for EPS, $0 for integer dollars) and the latest value is the corrected one inside it. The break years are untouched by design: the batch-85/120 guard runs first and abstains there, because the break year's own 10-K is already on the new basis, so no contemporaneous pair exists.

**Blast-radius method:** full DB-wide old-vs-new comparison (new rule vs `_own_tenk_annual_value` patched to None) over all 292 companies × 5 metrics, with fp-label changes separated from value changes (a derived-row gain/loss relabels a filed Q4 stub FY↔Q4 at an identical value — 25 such labels, not value changes). 757 value diffs, 10 added/removed derived rows, 0 fetch errors. Repair scope decided by joining diff ends against stored rows: only 8 tickers had in-window diffs (AEP, AJG, BAC, COIN, CRWD, LLY, NOW, OXY), all re-seeded through the production path; the other 749 diffs sit outside stored windows and self-correct on each ticker's next seed. 8 new regression tests (OXY pair, cash-flow pair, both-restated keeps-latest ×2, annual-restated-only EPS, split-rounding ×2, no-own-10-K unchanged); 1005-test suite green; `git diff --check` clean; live routes green with OXY detail rendering 6760000000.0 and no 2054 remnant.

**Related:** Closes the batch-120 OXY mixed-basis follow-up. Still open: STZ table-row wart; CB "Core" 5-line wraps; ABNB heading-less metric table; CINF subsidiary-list prefix + trailing quote fragment in highlights (cosmetic); MTB address-line prefix in highlights; pending-filing cohort at 26 + VRSK Q2 2026; partial residuals incl. PEG 6/8; Wikipedia 403s; table-header sections winning when a release has no bullets at all. New: the live pipeline applies only the 2020 4:1 split rescale to AAPL's pre-2014 per-share facts (single detected event; pre-2014 quarters sit 7× above the current basis) — a multi-split detection batch is open, and batch 121 deliberately keeps each series internally consistent on the split machinery's basis rather than fixing that here. Accepted limitation: a 9M restated in a later 10-Q during the window before the next 10-K restates the annual leaves a temporarily mixed pair (no substitution when the FY is unrestated); it self-heals on the next re-seed. Accepted residual risk of the refined guard: a component acquired and discontinued within a single fiscal year leaves no prior-year comparative to restate, so the restatement proof cannot catch it — that shape requires a same-year acquire-and-dispose, and every demonstrated reclassification does restate comparatives.

## 2026-10-24 — Batch 122: the 7-for-1 split ratio joins the detector; split corroboration must agree on one ratio

**What:** (1) `_SPLIT_RATIOS` in `data/xbrl.py` gains 7 (AAPL's 7-for-1 split, 2014-06-09). (2) `_detect_split_events` now filters corroborating votes to those within `_SPLIT_RATIO_TOLERANCE` of the median scale and requires at least `_SPLIT_MIN_CORROBORATING_GROUPS` agreeing votes; the event's scale is the median of the agreeing cluster and its `period_ends` cover only agreeing periods.

**Why:** (1) The batch-121 multi-split note was exactly this gap: AAPL's diluted-EPS facts carry 10 restatement pairs at 1/7 (0.1427–0.1432, filed 2014-07-23 through 2015-04-28) that the detector could never see, so pre-2014 facts rescaled by the 2020 4:1 event alone — 4x instead of 28x. NFLX's July-2015 7:1 split was invisible for the same reason. (2) The naive fix alone shipped a false positive: CRM's Aug-2018 10-Q restated Q2 quarterly basic EPS 0.02 → 0.06 (3x) and 6M basic EPS 0.01 → 0.07 (7x) — tiny rounded values, no split — and the old median-of-all-votes rule fired a 7.0 event on those two disagreeing votes, which would have inflated CRM's 2008–2011 basic EPS 7x. A real split restates every comparative at one ratio, so disagreement is disproof, not corroboration. The median-cluster form (rather than all-votes-must-agree) keeps genuine events robust to one stray rounding vote: a stray ratio outside tolerance cannot kill a 5-vote cluster, and cannot join it either.

**Blast-radius method:** DB-wide old-vs-new EPS basic/diluted series over all 292 companies (same script shape as batch 121): with both fixes, 82 value diffs — AAPL 36 (all pre-2014 ends, now ÷28, e.g. Q3 FY2008 basic 1.21 → 0.043) and NFLX 46 (2015 7:1 at 0.1449 + 2025 10:1 at 0.1001, both verified as clean single-ratio clusters) — CRM clean, no other ticker changed. The pre-fix blast (ratio only) showed the CRM damage explicitly (15 diffs, all ×7 upward) and is what forced the second fix. All 82 diffs sit outside stored 8-quarter windows, so no re-seed was needed. 3 new regression tests (AAPL 7:1 end-to-end, CRM mixed-ratio rejection, agreeing-cluster-with-stray control); 1008-test suite green; `git diff --check` clean; live routes green.

**Related:** Closes the batch-121 multi-split open item. Still open: STZ table-row wart; CB "Core" 5-line wraps; ABNB heading-less metric table; CINF/MTB cosmetic prefixes; pending-filing cohort at 26 + VRSK Q2 2026; partial residuals incl. PEG 6/8; Wikipedia 403s; table-header sections winning when a release has no bullets at all; the batch-121 transient-window limitation.

## 2026-10-25 — Batch 123: a flattened two-column contact table is not a headline — skip it by its role-label row

**What:** New `_skip_contact_table` in `data/filings.py`, called from the headline pass just before the final pick, plus a doubled-role-label alternative in `_CONTACT_HEADER_RE`. The skip fires when: the next line is a role-label row (one or more of investor/media/corporate-communications/press/public relations, optional colon); the candidate line is short (≤6 words), has no terminal punctuation, and contains no headline word (reports/announces/results/quarter/fiscal/earnings/revenue); and a headline-shaped line appears within 8 lines past table-continuation rows (repeated phrase via new `_is_repeated_phrase`, company-name line, admin/contact line, or short label line). Otherwise it returns None and the original behavior holds exactly.

**Why:** Akamai's Q4 releases are the demonstrated case: the full-year release puts a two-column contact table before the title (names row / roles row / company row / wrapped title), while Q1–Q3 put the title first — so only the two Q4 quarters broke, both storing contact names as headlines. Every existing guard misses the names row for a different reason: it is 4 words and headline-shaped (so the bare-masthead skip's ≤3-word, non-headline-shaped requirements fail), and there is no header line for the contact-header branch (the roles row is "Media Relations Investor Relations", a doubled label the old header regex could not match). The three guards are each load-bearing: the role-row lookahead is the table's signature (a real headline is never followed by a role-label row); the no-headline-word rule keeps a genuine verbless headline safe even if a role line somehow follows it; and the must-find-a-headline-ahead rule means a table whose headline never arrives swallows nothing. The doubled-label header alternative is added to `_CONTACT_HEADER_RE` itself (not just the new skip) so the lede fallback and every other header-branch caller also read the shape as a contact header.

**Blast-radius method:** DB-wide scan for the defect shape (stored highlights body opening with a role-label row) over all 2370 quarters with highlights: exactly 2 rows, both AKAM Q4 — the defect is fully contained, no silent cohort. Direct re-extraction from exhibit HTML (the backfill path skips filled rows, so it cannot measure an extractor change) over AKAM + AAPL/ROK/MTB/WDC/FSLR: exactly 2 attributable diffs, both AKAM Q4 improvements; ROK/MTB/WDC/FSLR byte-identical; AAPL's 8 diffs are pre-existing 1-char whitespace drift (stored len 1396 vs both pre- and post-123 extractor len 1395, proven via a stashed pre-123 extraction — the stored rows predate current `_html_to_text` spacing), deliberately left untouched rather than churning stored rows for invisible whitespace. Live repair overwrote only the 2 AKAM rows (new differs and non-None guard, batch-118 pattern); the other 6 AKAM quarters re-extracted identical. 7 new regression tests (AKAM Q4 end-to-end, doubled-role header, repeated-phrase unit, skip index, and three negatives: verb headline, no headline ahead, no role row); 1015-test suite green; `git diff --check` clean; live quarter-specific detail/data renders show both repaired headlines with bullet blocks and zero contact-name remnants.

**Related:** Closes the AKAM contact-name headline defect found by seed round 42 (LULU, WDC, FSLR, ENPH, TTD, AKAM — DB at 298). Still open: STZ table-row wart; CB "Core" 5-line wraps; ABNB heading-less metric table; CINF/MTB cosmetic prefixes; LULU Q3 FY2024/FY2025 section-header headline ("EARNINGS RELEASE & STOCK REPURCHASE PROGRAM" — needs raw-document investigation); pending-filing cohort at 26 + VRSK Q2 2026; partial residuals incl. PEG 6/8; Wikipedia 403s; table-header sections winning when a release has no bullets at all; the batch-121 transient-window limitation.

## 2026-10-25 — Batch 124: a compound earnings-release document title is not the headline — skip it by its exhibit marker

**What:** New `_is_compound_earnings_title` in `data/filings.py`, called from the headline pass just before the bare-label branch, plus a dedicated `_EXHIBIT_MARKER_RE`. The skip fires when: the line carries "earnings release" followed by "&" or "and"; an exhibit-marker line ("Exhibit 99.1" / "EXHIBIT 99.1" / "EX-99.1") appears within the next 2 lines; and the line immediately after that marker is headline-shaped and carries a headline verb (announces/reports).

**Why:** lululemon's Q3 releases are the demonstrated case: the combined earnings-release + buyback 8-K titles its exhibit "EARNINGS RELEASE & STOCK REPURCHASE PROGRAM", and that title sits before "Exhibit 99.1" while the real headline ("LULULEMON ATHLETICA INC. ANNOUNCES THIRD QUARTER FISCAL 2024/2025 RESULTS") follows it — so both Q3 quarters stored the document title. Q4 was immune because its title is the bare "EARNINGS RELEASE", which the label branch already skips. The three guards are each load-bearing: the "&"/"and" requirement separates compound titles from bare labels and results headlines; the marker lookahead means a compound title with no marker after it keeps old behavior; and the verb-headline requirement is what protects JPMorgan — its "EARNINGS RELEASE - THIRD QUARTER 2025 RESULTS" title is also followed by an exhibit marker, but the line after the marker is the company name/address block, not a verb headline, so JPM's 8 stored headlines are untouched (proven by re-extraction: JPM headlines identical pre/post-124, and its body drift is pre-existing, proven via a stashed pre-124 extraction). A regex bug in the first version (`\b` after `&`, which can never match since "&" followed by a space has no word boundary) was caught by the new tests and fixed to `(&|and\b)`.

**Blast-radius method:** DB-wide scan for the defect shape (stored headline containing "earnings release" with "&"/"and") over all 2370 quarters with highlights: exactly 2 rows, both LULU Q3 — fully contained, no silent cohort. Direct re-extraction from exhibit HTML over LULU + JPM/XOM/AKAM/AAPL/ROK/MTB/WDC/FSLR: exactly 2 attributable diffs, both LULU Q3 headline improvements (bodies otherwise identical); XOM/AKAM/ROK/MTB/WDC/FSLR byte-identical; JPM body diffs and AAPL 1–2-char diffs proven pre-existing (stash comparison for JPM, batch-123 proof for AAPL) and deliberately left untouched. Live repair overwrote only the 2 LULU rows (new differs and non-None guard, batch-118 pattern); the other 6 LULU quarters re-extracted identical. 4 new regression tests (LULU Q3 end-to-end, "&"/"and" forms, helper guard negatives, JPM-shape preservation); 1019-test suite green; `git diff --check` clean; live quarter-specific detail/data renders show both repaired headlines with zero doc-title remnants.

**Related:** Closes the LULU Q3 headline defect carried from seed round 42 (batch 123). Still open: STZ table-row wart; CB "Core" 5-line wraps; ABNB heading-less metric table; CINF/MTB cosmetic prefixes; XOM doc-title headlines ("3Q 2025 Earnings Release" with the real "ExxonMobil Announces..." headline unpicked — title-after-marker shape, needs its own rule); pending-filing cohort at 26 + VRSK Q2 2026; partial residuals incl. PEG 6/8; Wikipedia 403s; table-header sections winning when a release has no bullets at all; the batch-121 transient-window limitation.

## 2026-10-25 — Batch 125: slide-deck bullet-run mega-lines split into pseudo-lines; deck titles are never headlines

**What:** New `_split_bullet_runs` in `data/filings.py`, applied at the top of `extract_press_release_highlights` before any headline/section/lede logic, plus a slide-deck-title branch on `_NEVER_HEADLINE_RE`. A line longer than the 300-char headline cap with at least two " • " separators splits into one pseudo-line per bullet; continuation pieces keep a "• " prefix so downstream bullet logic treats them as bullets. The never-headline branch matches a line starting with a page number + quarter token + "Financial Highlights".

**Why:** Bank of America's releases are slide decks: `_html_to_text` flattens a whole highlights slide into one ~7,000-char line with bullets joined by " • ". The headline loop saw a single over-cap line, picked no headline, and the batch-105 page-line guard discarded the release — BAC was blank on all 8 quarters, the only whole-company blank left. Splitting restores the bullets the rest of the pipeline already knows how to handle. The deck-title branch is load-bearing: without it the split's first piece ("1 2Q26 Financial Highlights… Business Segment Highlights… Consumer Banking") became the headline. The "• " prefix on continuations is load-bearing in the other direction: the batch-115 bullet-headline strip is what turns the lead bullet into a clean headline, and the lede's bullet handling is what keeps the body as bullets rather than table fragments.

**Deliberately not done:** exact recovery of BAC's true "Bank of America Reports…" headline. It is glued to sub-heads and endnotes inside the final bullet piece with no sentence boundary ("…Up 34% YoY 2Q26 Revenue Up 15% YoY…"), so extracting it exactly would need BAC-specific surgery; the lead-bullet headline (Palantir precedent) plus genuine segment bullets is honest and informative. Also not added: a bullet skip in the headline loop — bullet-as-headline is tested Palantir/Skydance behavior, and skipping bullets would regress those cases. EOG's 7 blank quarters were investigated in the same audit and are a different defect class (combined release + supplement packet whose TOC entries escape the SPG TOC rule, landing extraction on footnote fragments) — left for its own batch rather than stretched into this one.

**Blast-radius method:** the split only fires on >300-char lines with ≥2 " • " separators, so prose releases are byte-identical by construction; the never-headline branch only matches page-number + token + "Financial Highlights" lines. 3 new regression tests (split unit behavior, BAC-shaped end-to-end extraction, deck-title narrowness); 1021-test suite green; `git diff --check` clean. Live repair backfilled all 8 BAC quarters (blank cohort 25 → 17); /company/BAC overview and detail/data both 200 with the backfilled highlights rendering.

**Related:** Closes the BAC whole-company blank found by the batch-125 blank-highlights audit. Still open: EOG 7/8 blank (TOC + supplement packet); SKYD 4 blank (structurally unextractable per batch 48); PEG 2 + AFRM/CCI/LIN/PCAR 1 blank each; STZ table-row wart; CB "Core" 5-line wraps; ABNB heading-less metric table; CINF/MTB cosmetic prefixes; XOM doc-title headlines (title-after-marker shape); pending-filing cohort at 28; Wikipedia 403s; table-header sections winning when a release has no bullets at all; the batch-121 transient-window limitation.

## 2026-10-25 — Batch 126: a footnote definition or a table of contents is never press-release highlights — result-level guards, not headline-loop skips

**What:** Two result-level guards in `extract_press_release_highlights` (after headline cleanup, before truncation): (1) a headline matching `_FOOTNOTE_HEADLINE_RE` (`^\([A-Za-z0-9]\)` — a single letter/digit in parentheses) returns None; (2) a headline whose body consists entirely (≥2 lines) of title + trailing page-number lines (`_TOC_ENTRY_RE`, `^.+ \d{1,3}$`) returns None.

**Why:** EOG Resources' exhibits are combined release + supplement packets whose narrative text lives in full-page images; the text layer is only the supplement TOC and tables. Six exhibits land on a footnote definition as the headline (the SPG TOC rule over-consumes tables and stops at the first >140-char line, a footnote legend); Q3 FY2024 lands on the TOC subtitle with TOC entries as the body (only one standalone page line, so the TOC rule never fires). The guards are result-level deliberately: skipping footnote lines inside the headline loop would not fix anything — a 700-line table document always yields some pick (a table heading, a units line, a financial row), so the loop would just move the garbage. Only a document-level "this result is not highlights" decision yields the honest blank. The single-character footnote bound is load-bearing: "(NYSE: ACME)" and "(2026)" parentheticals are not footnote markers (the character after the first is not ")"), so exchange- and year-prefixed headlines are untouched; the all-lines TOC bound is load-bearing in the other direction, since a real lede never consists entirely of title + page-number lines.

**Blast-radius method:** DB-wide scans over all 2378 stored highlight rows for both guard shapes: exactly 1 footnote-headline row (EOG Q1 FY2026 — cleared to NULL in the live repair) and 0 TOC-entry bodies, so no other stored row changes. Post-fix live re-extraction over all 8 EOG exhibits returns None on every quarter. 5 new regression tests (both EOG shapes end-to-end; NYSE- and year-prefixed headline preservation; normal release with numbered lede lines preserved); 1026-test suite green; `git diff --check` clean; /company/EOG overview + detail 200 with the Q1 FY2026 garbage gone.

**Related:** Closes the EOG follow-up carried from batch 125 (with a corrected mechanism: TOC over-consumption + under-firing, not simply "not skipped"). EOG is now honestly 8/8 blank — its image-page narrative is structurally unextractable short of OCR, same class as SKYD per batch 48. Still open: STZ table-row wart; CB "Core" 5-line wraps; ABNB heading-less metric table; CINF/MTB cosmetic prefixes; XOM doc-title headlines (title-after-marker shape); SKYD 4 + PEG 2 + AFRM/CCI/LIN/PCAR 1 blank each; pending-filing cohort at 28 + VRSK Q2 2026; Wikipedia 403s; table-header sections winning when a release has no bullets at all; the batch-121 transient-window limitation; a bounded `_skip_toc` fix (its over-consumption is now harmless given these guards, so it stays open rather than risking SPG).

## 2026-10-25 — Batch 127: an abbreviated quarter earnings-release title after the exhibit marker is never the headline

**What:** New `_is_quarter_earnings_title` in `data/filings.py`, called from the headline pass just after the batch-124 compound-title branch, plus a dedicated `_QUARTER_ABBR_EARNINGS_TITLE_RE`. The skip fires when: the line is exactly "<digit>Q <year> Earnings Release" (full-line anchored); an exhibit-marker line ("Exhibit 99.1" / "EX-99.1", via the existing `_EXHIBIT_MARKER_RE`) appears within the previous 3 lines; and the next non-admin line after the title (admin lines like "FOR IMMEDIATE RELEASE <date>" skipped via `_ADMIN_LINE_RE`) is headline-shaped and carries a headline verb (announces/reports).

**Why:** ExxonMobil's exhibits put the document title after the exhibit marker — "EXHIBIT 99.1" / "3Q 2024 Earnings Release" / "FOR IMMEDIATE RELEASE November 1, 2024" / "ExxonMobil Announces Third-Quarter 2024 Results" — so all 8 XOM quarters stored the document title. The spelled-out quarter label ("FIRST QUARTER 2026 EARNINGS RELEASE", batches 105/110/112) was already skipped, but the abbreviated form matched no existing rule, and batch 124's compound-title rule requires the marker to follow the title, which is the reverse of this shape. The three guards are each load-bearing: the full-line anchor is what keeps JPMorgan's genuine headlines safe ("JPMORGAN CHASE & CO. EARNINGS RELEASE - THIRD QUARTER 2024 RESULTS" is a results headline, not a bare quarter title); the marker lookbehind separates a real exhibit document title from a coincidental quarter-label line; and the verb guard is what keeps a release whose only title is the quarter label on old behavior rather than skipping into bullets or a table row.

**Blast-radius method:** DB-wide scan for the defect shape (`^[1234]Q YYYY Earnings Release$`) over all 2384 stored highlight rows: exactly 8 rows, all XOM — fully contained, no silent cohort. Direct re-extraction from exhibit HTML over XOM + JPM/AKAM controls: exactly 8 attributable diffs, all XOM headline improvements with bodies byte-identical apart from the headline (proven by headline-swap equality, not assumed); JPM/AKAM 8/8 identical. 3 new regression tests (XOM Q3 end-to-end, helper guard negatives, JPM-shape preservation); 1029-test suite green; `git diff --check` clean; live repair overwrote only the 8 XOM rows (DB is git-ignored, so the repair lives in the local DB and re-seeds reproduce it via the fixed extractor); /company/XOM overview + detail + detail/data all 200 with the repaired headline and zero doc-title remnants.

**Related:** Closes the XOM doc-title follow-up carried from batches 123–126. Still open: STZ table-row wart; CB "Core" 5-line wraps; ABNB heading-less metric table; CINF/MTB cosmetic prefixes; EOG honestly 8/8 blank (image-page narrative, structurally unextractable short of OCR); SKYD 4 + PEG 2 + AFRM/CCI/LIN/PCAR 1 blank each; pending-filing cohort at 28 + VRSK Q2 2026; partial residuals incl. PEG 6/8; Wikipedia 403s; table-header sections winning when a release has no bullets at all; the batch-121 transient-window limitation; a bounded `_skip_toc` fix (its over-consumption is now harmless given the batch-126 guards, so it stays open rather than risking SPG).

## 2026-10-25 — Batch 128: a 99.1 exhibit marker followed directly by a quarter-end date run is the release

**What:** `_release_name_rank`'s "991" infix lookahead gains a date-run alternative (`\d{6,8}` followed by end-of-stem or a separator) in `services/ir_download.py`.

**Why:** Cognizant furnishes its earnings release as `exhibit9916302026.htm` — 99.1 plus the quarter-end date with no separator — and no existing rule matched it: the tier-0 ex99 regex's digit guard exists to keep 99.2+ supplements out, and it rejects any 99.1 marker whose "1" is followed by a digit, which is exactly what a date run does. All 8 CTSH quarters therefore discovered their 2.02 8-Ks but found no exhibit, landing 0/8 despite clean, extractable releases. The date-run bound is what keeps the rule honest: a 6–8-digit run is a date (MDDYYYY/MMDDYYYY), while the `doc9912final` shape (1 digit) and 5-digit runs stay unmatched, and 992/993 supplements never contain 991 at all.

**Blast-radius method:** All 84 ir_download tests green (every prior exhibit convention unchanged); the new alternative fires only on "991" + 6–8-digit-date stems. Live repair backfilled CTSH 8/8 with real headlines; the detail/data route renders the repaired highlights.

**Related:** Closes the CTSH blank cohort found by seed round 43 (DB at 303). Still open: MO doc-label headline prefix; USB deck-section titles as headlines; STZ table-row wart; CB "Core" wraps; ABNB heading-less metric table; CINF/MTB cosmetic prefixes; EOG/SKYD honest blanks; PEG/AFRM/CCI/LIN/PCAR blanks; pending-filing cohort; Wikipedia 403s; table-header sections winning on bullet-less releases; the batch-121 transient-window limitation; a bounded `_skip_toc` fix.

## 2026-10-26 — Batch 129: a dated press-release document label is never the headline

**What:** New `_is_dated_press_release_label` in `data/filings.py`, called from the headline pass just after the batch-127 quarter-title branch, plus `_DATED_PRESS_RELEASE_LABEL_RE`. The skip fires when the line matches "<prefix> (EARNINGS) PRESS RELEASE,? DATED <full month date>" at end of line and stays within 140 chars.

**Why:** Altria's exhibits put a document label between the exhibit header and the "Exhibit 99.1" marker — "ALTRIA GROUP, INC. EARNINGS PRESS RELEASE, DATED OCTOBER 31, 2024" — so all 8 MO quarters stored the label instead of the real headline. No earlier rule caught it: the masthead branch requires a corporate-suffix ending (Inc./Corp./Co.), and the label ends with a date; the batch-124 compound-title rule needs an "&/and" continuation, and batch 127's quarter-title rule needs an exact "<digit>Q <year>" shape. The date anchor is the whole discriminator and needs no marker lookbehind/lookahead, unlike 124/127: a genuine headline never ends with "DATED <full date>", and the label precedes its marker in both MO variants (with and without "EARNINGS"/comma), so a marker condition would only narrow the rule against its own evidence. The 140-char bound is load-bearing in the other direction: a prose sentence that happens to end "... press release, dated <date>" is not swallowed.

**Blast-radius method:** DB-wide scan for a dated-label first paragraph over all 2424 stored highlight rows: exactly the 8 MO rows — fully contained, no silent cohort. Direct re-extraction over all 8 MO exhibits: exactly 8 attributable diffs, all headline repairs with the label gone. 3 new regression tests (MO Q3 end-to-end, Q4 variant, helper guard negatives); 1035-test suite green; `git diff --check` clean; live repair overwrote only the 8 MO rows (DB is git-ignored, so the repair lives in the local DB and re-seeds reproduce it via the fixed extractor); /company/MO overview + detail + detail/data all 200 with zero doc-label remnants.

**Related:** Closes the MO doc-label follow-up carried from batch 128. Still open: USB deck-section titles as headlines; STZ table-row wart; CB "Core" wraps; ABNB heading-less metric table; CINF/MTB cosmetic prefixes; EOG/SKYD honest blanks; PEG/AFRM/CCI/LIN/PCAR blanks; pending-filing cohort; Wikipedia 403s; table-header sections winning on bullet-less releases; the batch-121 transient-window limitation; a bounded `_skip_toc` fix.
