# Live Validation — 2026-09-30 (batch 7)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here. This batch's
> push failed (no GitHub auth in this environment — commits queue locally),
> so this validates the committed changes against the running app.

## Scope

- **Commit range:** `e486283..9f82bb5` (2 commits: "Also trades as" sibling-ticker link; sqlite journal/wal/shm gitignore)
- **Validated at:** 2026-09-30 ~03:20 CDT, server `uvicorn tickerlens.main:app :8123` started fresh from `main` after the code commit
- **Method:** HTTP requests against the live server + HTML content assertions (10 checks). Test suite: **214 passed** (210 prior + 4 new sibling-ticker tests).

## Results

| # | Check | Result |
|---|---|---|
| 1 | `GET /company/GOOGL` → 200, header shows `Also trades as <a href="/company/GOOG">GOOG</a>` | ✅ |
| 2 | `GET /company/AAPL` → 200, no "Also trades as" hint (single-class filer) | ✅ |
| 3 | `GET /company/GOOGL/detail` → 200, sibling hint present | ✅ |
| 4 | `GET /company/GOOGL/compare` → 200, sibling hint present | ✅ |
| 5 | `GET /company/GOOG` (not previously seeded) → 200 via auto-seed path, header shows `Also trades as <a href="/company/GOOGL">GOOGL</a>` — reverse link verified | ✅ |
| 6 | `sibling_tickers` unit tests: same-CIK match, self excluded, sorted, case-insensitive exclude, empty for single-class/unknown CIK | ✅ 4/4 |
| 7 | `get_sibling_tickers` unknown ticker → `[]` (never raises; hint hides) — verified via service call on a bogus ticker | ✅ |
| 8 | `GET /` (home, watchlist pins) → 200 (regression) | ✅ |
| 9 | Per-period CSV download `GET /company/GOOGL/detail/download` → 200 (regression) | ✅ |
| 10 | Full test suite | ✅ 214 passed |

**10/10 live checks passed.**

## Commit-hygiene note

- Mid-batch: `git add -A` swept up a transient `tickerlens.db-journal` (SQLite journal from the running server). Caught before finalizing — removed via `git rm --cached` + amend, and added `tickerlens.db-journal/-wal/-shm` to `.gitignore` (commit `9f82bb5`). Lesson for future agents: never `git add -A` in this repo while the dev server is running; the DB journals are ephemeral.

## Defect-hunt notes (round 12, in progress at write time)

- A defect-hunting subagent is exercising fresh tickers (CRM, SNOW, NET, SHOP foreign-filer, DPZ/HON/RTX/ABBV/MRK/NFLX/COIN/PLTR/UBER/MSFT candidates) against the live app to find real data defects before this batch's next work items. Findings will land in the batch report and/or a follow-up validation log.

## Environment notes

- Live-browser visual check remains blocked: the browser VM cannot reach this machine's localhost, and outbound tunneling is blocked by the network proxy (verified 2026-09-28). HTTP render + content assertions are the visual validation until that is unblocked.
