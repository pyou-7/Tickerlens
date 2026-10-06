# Post-change live validation — Batch 17 (2026-10-05 ~23:05 CDT)

Batch 17: integration audit of the automatic quote-refresh commit (b9e03d7).
Changed: `src/tickerlens/data/yahoo.py` (normalized cache keys), `src/tickerlens/services/financials.py`
(refresh fast path + conditional commit), `src/tickerlens/routes/company.py` (compute-once),
5 new tests. Dev server restarted on :8123 with the new code before checking.

## Test suite
- `.venv/bin/python -m pytest tests/ -q` → **330 passed** (325 baseline + 5 new), 0 failed
- `git diff --check` → clean

## Live HTTP checks (curl --noproxy '*' → :8123)
| # | Route | Result |
|---|-------|--------|
| 1 | `/` (home, warm_tracked_quotes path) | 200, 0.08s |
| 2 | `/company/AAPL` (overview) | 200, 0.21s warm |
| 3 | `/company/AAPL/detail` | 200 |
| 4 | `/company/AAPL/tearsheet` | 200 |
| 5 | `/company/AAPL/vs/MSFT` | 200 |
| 6 | `/company/BRK.B` (dotted ticker → normalized cache key) | 200, 0.17s |
| 7 | `/company/ZZZZINVALID` | 404 (clean, no 500) |

**7/7 passed.** No template/styling changes in this batch → no screenshot gate needed.

## Notes
- Commits queued locally (no push token in this session): batch-17 work commit + this validation log.
  `git status` clean apart from the queued commits; nothing pushed.
