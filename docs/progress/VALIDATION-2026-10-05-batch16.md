# Post-push validation — 2026-10-05 19:35 CDT

Push: `608737f..7c58b2c` (2 commits) to `origin/main` via user-supplied
transient PAT (session reuse per user's "keep using this token" — one-time
use, never stored). Local and remote in sync after push.

## What went up
- `558f84c` docs: post-push validation log for batch 15.
- `7c58b2c` fix(perf) batch 16: home page no longer blocks on cold
  earnings-calendar cache. `get_upcoming_earnings()` had fetched all 52
  tracked tickers' Yahoo calendars sequentially (10s timeout each, worst
  case ~9 min) on the `/` render path — the landing page hung >2 min on a
  cold cache (confirmed in server logs: dozens of sequential calendar
  timeouts). New `get_cached_upcoming_earnings()`: peek-only calendar reads
  + background warmer, mirroring the batch-13 quote-cache pattern.

## Live checks (running server, post-push code)
| Route | Status | Time |
|---|---|---|
| `/` | 200 | 0.23s (was >2 min cold) |
| `/calendar` | 200 | 0.01s |
| `/company/AAPL` | 200 | 0.18s |
| `/company/BRK.B` | 200 | 0.16s |
| `/api/search?q=nvda` | 200 | 0.01s |

5/5 checks passed.

## Tests
`pytest tests/ -q`: 319 passed (8 new in batch 16).

## Result
**5/5 live checks passed. Push verified.**
