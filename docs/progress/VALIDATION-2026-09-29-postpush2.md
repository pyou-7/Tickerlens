# Live Validation — 2026-09-29 post-push (commits c6615d7..4048a15)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here.

## Scope

- **Commit range pushed:** `c6615d7..4048a15` (6 commits: compare 5Y preset, compare-view ZIP, Realty Income net-income fix, Eli Lilly liabilities derivation, docs, batch-4 validation log)
- **Validated at:** 2026-09-29 ~15:50 CDT, server restarted fresh from `main` on :8123
- **Method:** HTTP requests + content assertions. Test suite: **188 passed**.

## Results

| # | Check | Result |
|---|---|---|
| 1 | `GET /` → 200 | ✅ |
| 2 | `GET /api/search?q=msf` → MSFT ranked | ✅ |
| 3 | `GET /company/AAPL` → 200, valuation card renders | ✅ |
| 4 | `GET /company/O` (Realty Income) → 200, valuation card renders (net-income tag fix) | ✅ |
| 5 | `GET /company/LLY` (Eli Lilly) → 200 (liabilities derivation fix) | ✅ |
| 6 | `GET /company/AAPL/compare` → 200 | ✅ |
| 7 | Per-period CSV download → 200, data rows | ✅ |
| 8 | `GET /company/AAPL/download/history.zip` → 200, `application/zip`, `AAPL_history.zip`, 8 per-quarter CSVs, valid archive | ✅ |
| 9 | `GET /company/ZZZQINVALID` → friendly 404 | ✅ |

**9/9 passed.** (The ZIP check initially crashed the check script on binary
decode — re-verified as a valid zip archive, not an app defect.)

## Environment notes

- Push done via one-time user-supplied PAT (used once, never stored).
- Live-browser visual check still blocked (browser VM can't reach localhost; tunneling blocked by proxy).
- `curl` needs `--noproxy '*'` here; Python `urllib` unaffected.
