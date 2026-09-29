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

---

# Live Validation — 2026-09-29 batch 4 (afternoon)

> Standing workflow: validate shipped changes live against the running
> application after every batch, and record the results here.

## Scope

- **Commit range:** `422c394..01a3af2` (5 commits: O net-income fix, 5y compare preset, compare ZIP, LLY liabilities fix, docs)
- **Validated at:** 2026-09-29 ~15:20 CDT, server `uvicorn tickerlens.main:app :8123` restarted fresh from `main` (post-batch-4 code)
- **Method:** HTTP requests against the live server + HTML/ZIP content assertions (17 checks). Test suite: **188 passed**.
- **Push:** `git push origin main` failed — no GitHub auth in this environment (`could not read Username for 'https://github.com'`). The 5 commits are queued locally, as in prior batches.

## Results

| # | Check | Result |
|---|---|---|
| 1 | `GET /` → 200 | ✅ |
| 2 | `GET /company/O` → 200; valuation card intact (Hold, Medium) | ✅ |
| 3 | O net-income fix: `/company/O/detail/data` shows Net Income **$343.95M** (+74.7% YoY) for Q2 FY2026 — previously "—" | ✅ |
| 4 | O compare: Net Income row A=$343.95M, B=$196.92M, Δ=+$147.04M, +74.7% | ✅ |
| 5 | `GET /company/O/compare` → 200 | ✅ |
| 6 | `GET /company/O/download/history.zip` → 200 | ✅ |
| 7 | `GET /company/AAPL/compare?preset=5y` → 200; 5Y button highlighted; B=Q4 FY2024 (oldest available) | ✅ |
| 8 | `GET /company/AAPL/compare?preset=qoq` → 200 (existing preset unaffected) | ✅ |
| 9 | `GET /company/AAPL/compare?mode=yearly` → 200 | ✅ |
| 10 | `GET /company/XOM/compare` → 200 (2-quarter history edge) | ✅ |
| 11 | `GET /company/AAPL/compare/download?preset=5y` → 200, `AAPL_compare.zip`: `AAPL/AAPL_Q3-FY2026.csv`, `AAPL/AAPL_Q4-FY2024.csv`, `AAPL/AAPL_compare_summary.csv`; summary revenue row `109417000000.0,94930000000.0,14487000000.0,15.26` | ✅ |
| 12 | `GET /company/AAPL/compare/download?mode=yearly` → 200: `AAPL/AAPL_FY2026.csv`, `AAPL/AAPL_FY2025.csv`, `AAPL/AAPL_compare_summary.csv` | ✅ |
| 13 | `GET /company/MSFT/compare/download?period_a=Q4%20FY2026&period_b=Q4%20FY2025` → 200; summary NI row `35766000000.0,27233000000.0,8533000000.0,31.33` | ✅ |
| 14 | "⇓ Compare (ZIP)" button present on the compare page | ✅ |
| 15 | `GET /company/ZZZQINVALID/compare/download` → 404 (not 500) | ✅ |
| 16 | `GET /company/AAPL/compare/download?preset=decade` → 422 (Literal validation) | ✅ |
| 17 | Full test suite | ✅ 188 passed |

**17/17 live checks passed.**

## Defect-hunt notes (batch 4)

- **O (Realty Income):** `NetIncomeLoss` quarterly facts stop at 2025-09-30 (273-day lag); fix verified — net income restored for 2026 Q1 ($311.8M) and Q2 ($344.0M), matching the filer's `NetIncomeLossAvailableToCommonStockholdersBasic` facts.
- **LLY (Eli Lilly):** no `Liabilities` tag in companyfacts; total liabilities derived via Assets − Equity — verified live (Q2 FY2026: 108.4B = 142.3 − 33.9).
- **XOM Q2 2026 revenue $116.0B:** verified against the actual 10-Q (filed 2026-08-03) — the filer's real number, not a defect.
- **V (Visa):** EPS tags absent from companyfacts entirely (per-share-class EPS uses dimensional facts, which companyfacts excludes) — data-source limit, not a code defect; EPS shows "—" by design.
- Finance threshold change (400→180d) regression-checked: MET still prefers quarterly `Revenues` (19.2B), JPM/WFC still use the bank composite — all current through 2026-06-30.
- UNH, HD, LLY, MA extraction-only sweeps: all 8 quarters, sensible values, no new defects.

## Environment notes

- Live-browser visual check remains blocked (browser VM cannot reach this machine's localhost; outbound tunneling blocked by the network proxy). HTTP render + content assertions stand in.
- `curl` against localhost needs `--noproxy '*'` (proxy env vars interfere); Python `urllib` is unaffected.
- SEC Archives document fetches still 403 ("Undeclared Automated Tool"); index listings + companyfacts JSON API work.
