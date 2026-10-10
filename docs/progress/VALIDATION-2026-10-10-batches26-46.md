# Post-push validation — 2026-10-10 ~17:55 CDT

Push: `c81db0e..2ab0d84` (42 commits, batches 26–46) to `origin/main` via
user-supplied transient PAT (one-time use, never stored). Local and remote
in sync after push. Queue empty.

## What went up (batches 26–46)
- 26: margin-anchored fair P/S (killed fabricated Strong Buys on loss-makers)
- 27: 6 new tickers (COIN/RIVN/HOOD/UBER/PLTR/O) + honest declining-earnings copy
- 28: 13 dead/wrong-company peer tickers fixed
- 29: APLD revenue tag fix ($341.9M) + earnings auto-refresh on new 10-Q/10-K
- 30: tearsheet valuation-divergence callout
- 31: auto-refresh restart-resilience fix
- 32: /vs filings refresh for both tickers
- 33: ET/DUK/UNP/GE seeds + partnership-equity mapping + honest no-EPS copy
- 34: home earnings strip "Today!" pill
- 35: BNY Q4-stub doubling fix
- 36: mREIT revenue coverage + >100% net-margin guard
- 37: EDGAR cache TTL + processed-filing marker fix
- 38: BDC revenue coverage (ARCC) + 6 seeds
- 39: partial fiscal-year disclosure
- 40: PEG floor-copy honesty + 6 seeds
- 41: AI-briefing revenue flat/decline branches
- 42: AI-briefing EPS thesis
- 43: calendar audit (clean) + 6 seeds
- 44: SKYD rename + thin-ticker backfill + middle-gap refresh
- 45: 6 seeds + cap-side valuation-copy honesty
- 46: AI-briefing margin-thesis sector register

## Live checks (running server, post-push code)
| Route | Status | Time |
|---|---|---|
| `/` | 200 | 0.49s |
| `/company/AAPL` | 200 | 1.63s |
| `/company/APLD` | 200 | 18.6s (cold Yahoo quote timeout, graceful) |
| `/company/JPM` | 200 | 1.08s |
| `/company/SKYD` | 200 | 4.77s |
| `/company/AAPL/detail` | 200 | 0.16s |
| `/company/AAPL/tearsheet` | 200 | 0.15s |
| `/calendar` | 200 | 0.02s |
| `/api/search?q=msft` | 200 | 0.01s |
| `/company/DUOL` | 200 | 9.64s (filings freshness check) |
| `/company/NLY` | 200 | 2.13s |
| `/company/ARCC` | 200 | 1.73s |

12/12 checks passed. Dev server had died (VM replacement); restarted via
serve_tickerlens.py before validation.

## Tests
`pytest tests/ -q`: 461 passed.

## Result
**12/12 live checks passed. Push verified.**
