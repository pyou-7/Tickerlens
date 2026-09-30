# Live Validation — 2026-09-30 post-push (commits 4048a15..af154d8)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here.

## Scope

- **Commit range pushed:** `4048a15..af154d8` (27 commits: batches 5–10 —
  range ZIP, watchlist notes/tags, single-year ZIP, sibling-ticker links,
  404 did-you-mean, range tables + hero KPI cards, cross-company compare,
  defect-hunt rounds 11–14)
- **Validated at:** 2026-09-30 ~15:55 CDT, server restarted fresh from `main` on :8123
- **Method:** HTTP requests + content assertions. Test suite: **250 passed**.

## Results

| # | Check | Result |
|---|---|---|
| 1 | `GET /` → 200 | ✅ |
| 2 | `GET /api/search?q=msf` → MSFT ranked | ✅ |
| 3 | `GET /company/AAPL` → 200, valuation card renders | ✅ |
| 4 | `GET /company/GOOGL` → "Also trades as GOOG" (batch 7) | ✅ |
| 5 | `GET /company/DUOL` → 200 (batch 8 Q4 EPS fix) | ✅ |
| 6 | `GET /company/SOFI` → 200 (batch 8 FCF suppression) | ✅ |
| 7 | `GET /company/AAPL/compare` → 200 | ✅ |
| 8 | `GET /company/AAPL/vs/MSFT` → 200, cross-company compare (batch 10) | ✅ |
| 9 | Per-period CSV download → 200 | ✅ |
| 10 | `GET /company/AAPL/download/year.zip?year=2025` → 200, 5-file zip (batch 6) | ✅ |
| 11 | `GET /company/APPL` → 404 with "Did you mean" (batch 8) | ✅ |
| 12 | `GET /company/ZZZQINVALID` → friendly 404 | ✅ |

**12/12 passed.** (Initial check used a guessed `/compare-cross` URL and 404'd;
the real route `/company/{ticker}/vs/{other}` verified 200 — a check-script
error, not an app defect.)

## Environment notes

- Push done via one-time user-supplied PAT (used once, never stored).
- Live-browser visual check still blocked (browser VM can't reach localhost; tunneling blocked by proxy).
- `curl` needs `--noproxy '*'` here; Python `urllib` unaffected.
