# VALIDATION — batch 76 (2026-10-16) — serve-stale-on-error + failure cooldown

**QUEUED (no push this run — no token pasted in session).**

## What changed
- `src/tickerlens/data/edgar.py`: `fetch_json`/`fetch_text` serve the stale on-disk snapshot on any live-fetch failure (timeout, connection error, non-2xx) instead of raising; new `FAILURE_COOLDOWN_SECONDS = 5 min` per-URL failure record skips re-attempting a just-failed live fetch (serves stale immediately); success clears the record; no cache on disk → exception still propagates.
- `tests/data/test_edgar.py`: 6 new tests.

## Test results
- `tests/data/test_edgar.py`: 13/13 pass (6 new).
- Full suite: **692 passed**, 0 failed (baseline 686 + 6 new).
- `git diff --check`: clean.

## Live validation (:8123, server restarted to pick up the change)
| Route | Status |
|---|---|
| `/` | 200 |
| `/api/search?q=aapl` | 200, `{"ticker":"AAPL","name":"Apple Inc.","cik":"0000320193"}` |
| `/company/AAPL` | 200 |
| `/company/AAPL/detail` | 200 |
| `/company/AAPL/vs/MSFT` | 200 |
| `/company/BRK.B` | 200 |
| `/calendar` | 200 |

(`company_tickers` resolution verified via `/api/search`; earlier `/search` 404 was a wrong path on my part — the route is `/api/search`.)

## Template/UI
No template change (backend-only) — screenshot gate N/A.

## Commits
- `f98f9a2` fix: serve-stale-on-error for EDGAR disk cache + 5-min failure cooldown (batch 76)
- `72014c3` docs: batch 76 (PROJECT_STATUS row + DECISIONS entry)
- Queue now 62 commits ahead of origin/main, 0 pushed.
