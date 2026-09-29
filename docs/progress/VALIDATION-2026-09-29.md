# Live Validation — 2026-09-29 (batch 5)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here. This batch's
> push failed (no GitHub auth in this environment — commits queue locally),
> so this validates the committed changes against the running app.

## Scope

- **Commit range:** `36d1d2c..263d47f` (4 commits: NVDA CapEx fix, history ZIP, watchlist refresh-all, chart range window)
- **Validated at:** 2026-09-29 ~03:10 CDT, server `uvicorn tickerlens.main:app :8123` restarted fresh from `main`
- **Method:** HTTP requests against the live server + HTML content assertions (21 checks). Test suite: **140 passed**.

## Results

| # | Check | Result |
|---|---|---|
| 1 | `GET /` → 200 | ✅ |
| 2 | Watchlist pins + "⟳ Refresh quotes" button on home | ✅ |
| 3 | NVDA FCF restored: 8/8 quarters non-null in DB (was 0/8) | ✅ |
| 4 | `GET /company/NVDA` → 200 | ✅ |
| 5 | Valuation card: "Cross-check: FCF yield 2.3% (below the 4% hurdle)" — no longer "unavailable" | ✅ |
| 6 | `GET /company/AAPL/download/history.zip` → 200 | ✅ |
| 7 | `Content-Disposition: attachment; filename="AAPL_history.zip"`, `application/zip` | ✅ |
| 8 | 8 files, all `AAPL/AAPL_*.csv` namespaced under `AAPL/` | ✅ |
| 9 | ZIP CSV matches per-period format (`# Company,…` header, `metric,value,yoy_pct,qoq_pct`) | ✅ |
| 10 | `GET /company/ZZZZ/download/history.zip` → 404 (friendly, not 500) | ✅ |
| 11 | `GET /company/AAPL/detail` → 200 | ✅ |
| 12 | "Full history (ZIP)" button present in detail view | ✅ |
| 13 | `chart_from` / `chart_to` selects present in slicer | ✅ |
| 14 | `GET /detail/data?chart_from=Q1 FY2025&chart_to=Q2 FY2025` → 200 | ✅ |
| 15 | Chart JSON windowed to exactly `["Q1 FY2025", "Q2 FY2025"]` | ✅ |
| 16 | `POST /watchlist/refresh` (plain) → 303 redirect to `/` | ✅ |
| 17 | `POST /watchlist/refresh` (HTMX) → 200, returns `#watchlist-section` partial | ✅ |
| 18 | Per-period CSV download still → 200 (regression) | ✅ |
| 19 | `GET /api/search?q=aapl` → 200, AAPL in results (regression — decorator was clobbered mid-batch, re-added) | ✅ |
| 20 | Unknown ticker overview still → friendly 404 (regression) | ✅ |
| 21 | Full test suite | ✅ 140 passed |

**21/21 live checks passed.**

## Defect-hunt notes (batch 5)

- Seeded **NVDA** (Jan FYE — calendar diversity vs AAPL Sep / MSFT Jun / JNJ Dec): found the CapEx tag abandonment (`PaymentsToAcquirePropertyPlantAndEquipment` ends 2020; CapEx now filed as `PaymentsToAcquireProductiveAssets`). Fixed via fallback chain + staleness rule; re-seeded 8/8 quarters with FCF.
- **XOM** (2 quarters, single-filing CIK): FCF stays `None` by design — its only 10-Q reports cash flow as H1-YTD, so no standalone quarter can be un-cumulated. Stored revenue values verified as true 90-day quarterly facts (`Revenues` tag files both durations). Honest "—" is correct.
- **MSFT** (Jun FYE): 8 clean quarters, unique selector labels, valuation card renders with guardrail honesty ("fair P/E hit the 40× cap").

## Environment notes

- Live-browser visual check remains blocked: the browser VM cannot reach this machine's localhost, and outbound tunneling is blocked by the network proxy (verified 2026-09-28). HTTP render + content assertions are the visual validation until that is unblocked.
- `curl` against localhost needs `--noproxy '*'` in this environment (proxy env vars interfere).
- Push failed: `fatal: could not read Username for 'https://github.com'` — no GitHub auth in this environment. 4 commits queue locally (`30a9431`, `f349198`, `c90bf6e`, `263d47f`).
- Process hygiene: `pgrep -f 'uvicorn tickerlens'` inside an exec shell matches the shell's own command line — the shell gets SIGTERM'd. Use the bracket form `pgrep -f '[u]vicorn tickerlens'` instead.
