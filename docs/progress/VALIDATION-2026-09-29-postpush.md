# Live Validation — 2026-09-29 post-push (commits 862560d..c6615d7)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here.

## Scope

- **Commit range pushed:** `862560d..c6615d7` (21 commits: watchlist slices, compare modes, chart range window, ZIP download, bank/finance revenue fixes, press-release exhibit fix, Cmd+K, validation logs)
- **Validated at:** 2026-09-29 ~12:50 CDT, server restarted fresh from `main` on :8123
- **Method:** HTTP requests + HTML content assertions. Test suite: **176 passed**.

## Results

| # | Check | Result |
|---|---|---|
| 1 | `GET /` → 200 | ✅ |
| 2 | `GET /api/search?q=aap` → AAPL ranked | ✅ |
| 3 | `GET /company/AAPL` → 200, valuation card (Hold, Medium, reasoning) | ✅ |
| 4 | `GET /company/AAPL/detail` → 200 with press-release highlights | ✅ |
| 5 | Per-period CSV download → 200, data rows | ✅ |
| 6 | `GET /company/NVDA` → 200 (CapEx-fallback fix ticker) | ✅ |
| 7 | `GET /company/ZZZQINVALID` → friendly 404 | ✅ |
| 8 | Download endpoint without params → handled, no 500 | ✅ |
| 9 | Watchlist end-to-end: `POST /company/AAPL/watch` → home shows pin; `POST /company/AAPL/watch/remove?next=home` → pin gone | ✅ |

**9/9 passed.** (Initial script flagged #9 because the empty watchlist correctly
renders no section and "AAPL" also appears in the search placeholder —
re-verified manually as correct behavior.)

## Environment notes

- Push done via one-time user-supplied PAT (used once, never stored).
- Live-browser visual check still blocked (browser VM can't reach localhost; tunneling blocked by proxy).
- `curl` needs `--noproxy '*'` here; Python `urllib` unaffected.
