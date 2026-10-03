# Validation log — 2026-10-03 (overnight session, batches 12–13 prep)

## Integration: Gemini UI work merged
- `origin/main` had moved 4 commits ahead (Gemini's UI overhaul: theme engine,
  microinteractions, home redesign, popular bar). Local batch-11 commits rebased
  on top cleanly after resolving 3 conflicts:
  - `detail.html`: mobile bottom-sheet behavior merged with Gemini's new
    light/dark card styling (behavior added, visuals untouched).
  - `docs/DECISIONS.md`, `docs/PROJECT_STATUS.md`: kept both sides' entries.
- Result: `main` = 2917cf2 + 6 replayed commits, tree clean, `git diff --check` clean.

## UI verification (styled screenshots, local Tailwind build)
- `scripts/screenshot.py` added (persistent, self-healing: installs Chrome,
  rebuilds CSS, starts server). Fixed a build bug where unquoted `**` glob
  dropped all `md:` variants from the CSS.
- Screenshots: home, AAPL overview/detail/compare/vs — all render correctly
  in the new light/dark theme. No regressions from the rebase.
- **Found and fixed**: floating "Print PDF / History ZIP" pill overlapped the
  sticky per-period download bar at the bottom of the detail page. Merged into
  a single action bar (Full history ZIP + per-period CSV + Print PDF).
  Commit `b1074f4`. Screenshot-verified after fix.

## Batch 12: rate-aware valuation guardrail
- `compute_valuation(ten_year_yield_pct=None)` → default 4.5% benchmark.
- Fair P/E capped at `100 / (yield × 0.6)`; binding adds a reasoning note and
  caps confidence at Medium. Dormant below ~2.7% yields.
- Live check: 32% grower at 5.3% yield → 31.4x cap, note present, Medium.
- Tests: 270 passing (5 new + 2 snapshot expectations updated).

## Test summary
- `pytest tests/ -q`: **270 passed**, 20 warnings (pre-existing SQLAlchemy
  deprecation).
- Live HTTP: `/company/AAPL` 200, `/api/search?q=aapl` 200.
- Screenshots: 6 styled renders reviewed, no visual regressions.

## Push state
- 8 commits queued locally (6 batch-11 + pill fix + batch 12). Push still
  blocked on auth (SSH key / token from user). Not nagged.

---

## Validation log — 2026-10-03 (overnight session, batches 13–14)

### Batch 13: defect hunt round 16 (fresh tickers)
- Hunt harness exercised the live XBRL pipeline on JPM, BAC, AMZN, TSLA, XOM,
  UNH, NEE, AMT, PFE, DIS with sanity checks (4 rows, positive revenue,
  EPS present, diluted ≤ basic, balance-sheet identity, monotonic ends,
  unique fy/fp labels).
- **No XBRL defects found.** Non-findings recorded in DECISIONS.md:
  - XOM returns 2 rows — honest: SEC companyfacts holds only the Q2-2026 10-Q
    (submissions confirm). Sparse-window QoQ gap guard already renders "—".
  - AMT Q4-2025 revenue ($2,737.5M) exactly equals Q1-2026 — verified against
    raw facts as genuine arithmetic coincidence
    (10,644.6 − 2,562.8 − 2,626.9 − 2,717.4 = 2,737.5), not a labeling bug.
  - NEE missing Q2-2026 — SEC companyfacts processing lag (10-Q filed 2026-07-24).
  - DIS FYE "1003" labels verified correct (FY2026 Q1 end 2025-12-27).
- **Found and fixed**: `get_popular_stocks()` served hardcoded 2026-09-30
  day-change percents as live data (NVDA +3.1% shown; live was +1.34%). Now
  reads Yahoo `regularMarketChangePercent` through a thread-safe 5-min TTL
  `QuoteCache`; static values demoted to fallback seed. Non-blocking render:
  peek-only cache reads + single background daemon warmer; home page never
  waits on Yahoo. Backend-only — no template changes.
  Commit `9cf197e`. 11 new tests.

### Batch 14: performance + robustness
- `refresh_watchlist_quotes()` now reads through the TTL `QuoteCache`.
- `yf.Ticker.info` had no socket timeout — new `_fetch_info()` enforces a 15s
  hard timeout via a shared 4-worker pool; executor-shutdown `RuntimeError`
  → `TimeoutError` (no teardown tracebacks); never-raise contracts kept.
  Audit: EDGAR (30s) / Wikipedia (10s) timeouts in place; SEC `fetch_json`
  never caches malformed bodies; first-visit fetch → friendly 404.
  Commit `a120196`.

### Test summary
- `pytest tests/ -q`: **284 passed** (270 baseline + 14 new), 20 warnings
  (pre-existing SQLAlchemy deprecation). `git diff --check` clean.
- Live HTTP against uvicorn on :8123 (fresh restart per batch):
  - `/` 200 — 0.26s cold-cache (seed + background warm) / 0.07s warm.
    Popular bar shows live values after warming (NVDA +1.3%, TSLA +4.7%,
    AAPL +1.0%, PLTR −0.7% — all differ from the old hardcoded seed).
  - `/api/search?q=aapl` 200 — 0.10s first / 0.006s warm.
  - `/company/AAPL` 200 — 0.12s / 0.08s (matches pre-batch baseline).
  - `/company/AAPL/detail` 200 — 0.10s / 0.03s.
  - `POST /watchlist/refresh` 303 (normal post-refresh redirect).
  - `/company/ZZZZ` 404 (friendly page, no 500).
- No template changes in either batch — screenshot gate not triggered
  (UI rule: templates touched only for visual bugs; none found).

### Push state
- **11 commits queued locally** (9 + 2 new: 9cf197e, a120196). Push still
  blocked on user auth (SSH key `pyou-7-tickerlens-push` not yet added to
  GitHub, or a transient PAT). Not attempted overnight per instructions;
  not nagged.

### Loop state
- Batches 13 and 14 complete. This was the final bounded run (batch 12 ran in
  the main session; user authorized max 3). **Cron disabled** via
  `cron.update(enabled=false)` after this run.
