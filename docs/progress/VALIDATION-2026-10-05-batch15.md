# Post-push validation — 2026-10-05 16:05 CDT

Push: `6c3d64c..608737f` (2 commits) to `origin/main` via user-supplied
transient PAT (session reuse per user's "keep using this token" — one-time
use, never stored). Local and remote in sync after push.

## What went up
- `ed6cbd5` docs: post-push validation log for the news-feature push.
- `608737f` fix (batch 15): Yahoo symbol normalization (`BRK.B`→`BRK-B`
  for quotes + earnings calendar), honest "Unknown" cap tier instead of
  default Mid-Cap, BRK.B $1.08T market-cap backfill. 3 new regression tests.

## Live checks (running server, post-push code)
| Route | Status | Time |
|---|---|---|
| `/` | 200 | 0.08s |
| `/company/AAPL` | 200 | 0.19s |
| `/company/AAPL/news` | 200 | 1.29s (cold fetch) |
| `/company/BRK.B` | 200 | 0.18s |
| `/company/AAPL/detail` | 200 | 0.17s |
| `/company/AAPL/tearsheet` | 200 | 0.13s |
| `/calendar` | 200 | 0.01s |
| `/company/AAPL/vs/MSFT` | 200 | 0.12s |
| `/api/search?q=brk.b` | 200 | 0.007s |
| `/company/ZZZZ` | 404 (friendly) | 0.03s |

10/10 checks passed. BRK.B overview verified via styled screenshot:
$504.26, Market Cap $1.08T, AI briefing tier Mega-Cap.

## Tests
`pytest tests/ -q`: 311 passed.

## Result
**10/10 live checks passed. Push verified.**
