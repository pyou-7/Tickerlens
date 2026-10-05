# Post-push validation — 2026-10-05 10:58 CDT

Push: `7c3f4eb..6c3d64c` (2 commits) to `origin/main` via user-supplied
transient PAT (one-time use, never stored). Local and remote in sync after
push (`main...origin/main`, no ahead/behind).

## What went up
- `cafc3ae` docs: post-push validation log for the 2026-10-03 push.
- `6c3d64c` feat: Latest News section on company overview (Google News RSS,
  30-min TTL cache, HTMX lazy-load, never-raises) + startup schema migration
  `ensure_schema()` fixing the 500s on all company pages caused by Gemini's
  disclosure columns shipping without a migration.

## Live checks (running server, post-push code)
| Route | Status | Time |
|---|---|---|
| `/` | 200 | 0.24s |
| `/company/AAPL` | 200 | 0.18s |
| `/company/AAPL/news` | 200 | 0.002s (cached) |
| `/company/AAPL/detail` | 200 | 0.04s |
| `/company/AAPL/tearsheet` | 200 | 0.11s |
| `/calendar` | 200 | 0.007s |
| `/company/AAPL/vs/MSFT` | 200 | 0.07s |
| `/api/search?q=msft` | 200 | 0.02s |
| `/company/ZZZZ` | 404 (friendly) | 0.03s |

9/9 checks passed. The `/company/AAPL/news` partial returns 6 real headlines
with source badges and age labels; the migration was verified live (company
pages returned 500 before the restart, 200 after).

## Screenshots
Styled renders (local Tailwind build) reviewed: overview page in Gemini's new
design intact (sector peers, CIK badge, KPI cards, AI briefing); news section
renders in the same card language with 6 headlines, sources, and ages.

## Tests
`pytest tests/ -q`: 308 passed (11 new: news parsing/cache/route, migration).

## Result
**9/9 live checks passed. Push verified.**
