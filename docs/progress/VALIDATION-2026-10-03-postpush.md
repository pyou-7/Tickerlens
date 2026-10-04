# Post-push validation — 2026-10-03 22:15 CDT

Push: `2917cf2..e7153cc` (13 commits) to `origin/main` via user-supplied
transient PAT (one-time use, never stored). Local and remote in sync after
push (`main...origin/main`, no ahead/behind).

## What went up
- Batch 11 (6): Netflix split-EPS rescale, BRK.B ticker normalization,
  IFRS-filer clean error, mobile bottom-sheet period selector, docs.
- UI fix: floating action pill merged into sticky download bar (no overlap).
- Batch 12: rate-aware valuation guardrail (`ten_year_yield_pct`).
- Batch 13: defect-hunt round 16 + popular-bar live day-change % via TTL cache.
- Batch 14: Yahoo quote cache + 15s timeout hardening.
- Validation logs + persistent screenshot script.

## Live checks (fresh uvicorn, post-push code)
| Route | Status | Time |
|---|---|---|
| `/` | 200 | 0.07s |
| `/company/AAPL` | 200 | 0.26s |
| `/company/AAPL/detail` | 200 | 0.10s |
| `/company/AAPL/compare` | 200 | 0.06s |
| `/company/AAPL/vs/MSFT` | 200 | 0.10s |
| `/api/search?q=msft` | 200 | 0.006s |
| `/company/ZZZZ` | 404 (friendly) | 0.03s |

7/7 checks passed.

## Screenshots
Styled renders (local Tailwind build) of home and AAPL overview reviewed —
new light/dark theme intact, KPI cards, valuation section all correct.
No visual regressions.

## Tests
`pytest tests/ -q`: 284 passed (last full run pre-push; no code changed
since except this log).

## Result
**7/7 live checks passed. Push verified.**
