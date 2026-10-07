# Post-push validation — 2026-10-07 09:35 CDT

Push: `b9e03d7..c81db0e` (11 commits, batches 17–25) to `origin/main` via
user-supplied transient PAT (one-time use, never stored). Local and remote
in sync after push.

## What went up
- 1428b8d (17): quote-refresh audit — normalized cache keys, refresh fast path
- e2d32be (18): 8-K disclosure integration audit
- 5e51a42 (19): AI-briefing Unknown-tier copy fix
- d8130c0 (20): peer-coverage gaps — Sector Peers row for 12+ companies
- 9a0a4af (21): FY-label collision arbitration + unsupported-filer message
- 7ae287f (22): tearsheet audit, no defects (docs only)
- 9d53920 (23): calendar BRK.B display, cache-key normalization, parallel prefetch
- a1c881a (24): news relevance for ambiguous tickers + artifact filter
- c7e3d6a (25): AI analysis sector-aware solvency + Strong Sell divergence note
- plus batch validation-log docs commits

## Live checks (running server, post-push code)
| Route | Status | Time |
|---|---|---|
| `/` | 200 | 0.48s |
| `/company/AAPL` | 200 | 15.2s (cold Yahoo quote timeout, graceful) |
| `/company/AAPL/news` | 200 | 10.1s (cold news fetch) |
| `/company/BRK.B` | 200 | 15.2s (cold Yahoo quote timeout, graceful) |
| `/company/JPM` | 200 | 15.5s (cold Yahoo quote timeout, graceful) |
| `/company/AAPL/detail` | 200 | 0.14s |
| `/company/AAPL/tearsheet` | 200 | 0.14s |
| `/calendar` | 200 | 0.02s |
| `/company/ORCL` | 200 | 6.7s (first-visit fetch) |
| `/api/search?q=msft` | 200 | 0.01s |
| `/company/ASML` | 404 (friendly unsupported-filer) | 0.10s |
| `/company/ZZZZ` | 404 (friendly) | 0.05s |

12/12 checks passed. Slow first-hits are Yahoo cold-fetch timeouts from this
VM (15s cap, never-raise) — pages render correctly regardless.

## Tests
`pytest tests/ -q`: 373 passed.

## Result
**12/12 live checks passed. Push verified.**
