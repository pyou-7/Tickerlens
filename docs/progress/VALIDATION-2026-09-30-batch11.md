# Live Validation — 2026-09-30 batch 11 (push queued)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here. The push did
> not go through (no persistent GitHub auth in this environment — `git push`
> failed with "could not read Username"; 5 commits queued locally), so this
> validates the batch's commits against a fresh local server instead.

## Scope

- **Commits (queued locally):** `89f4baa` (split-EPS rescale fix), `75ec191`
  (mobile bottom-sheet period selector), `e16dd9f` (BRK.B normalization +
  IFRS filer error), `63f8387` (docs)
- **Validated at:** 2026-09-30 ~19:10 CDT, server restarted fresh from `main` on :8123
- **Method:** HTTP requests + content assertions. Test suite: **261 passed**.

## Results

| # | Check | Result |
|---|---|---|
| 1 | `GET /` → 200 | ✅ |
| 2 | `GET /company/NFLX` → 200 (split fix) | ✅ |
| 3 | `GET /company/NFLX/detail` → 200, `#slicer-panel` markup present, Q4 FY2024 EPS renders 0.426 (was −13.58) | ✅ |
| 4 | `GET /company/NFLX/detail/data` → 200, EPS trend `[0.539, 0.426, 0.66, 0.72, 0.586, 0.565, 1.23, 0.8]` — smooth, no −87% cliff | ✅ |
| 5 | `GET /company/BRK.B` → 200 (ticker normalization; 8 quarters seeded) | ✅ |
| 6 | `GET /api/search?q=brk.b` → `BRK-B` top result | ✅ |
| 7 | `GET /company/TSM` → 404 with clean message: "no US-GAAP facts (reports under dei, ifrs-full, srt); Tickerlens supports US-GAAP filers only" (was bare `KeyError: 'us-gaap'`) | ✅ |
| 8 | `GET /company/GOOGL` → "Also trades as" hint intact (regression) | ✅ |
| 9 | `GET /company/AAPL/compare` → 200 (regression) | ✅ |
| 10 | `GET /company/AAPL/vs/MSFT` → 200 (regression) | ✅ |
| 11 | `GET /company/AAPL/detail/download` → 200 CSV (regression) | ✅ |
| 12 | `GET /company/AAPL/download/year.zip?year=2025` → 200 (regression) | ✅ |
| 13 | `git diff --check` clean on all commits | ✅ |
| 14 | Full suite `.venv/bin/python -m pytest tests/ -q` → 261 passed | ✅ |

**14/14 passed.**

## Data notes

- Fresh tickers seeded this batch: DIS, PYPL, NFLX, LMT, ZTS, CRM, BRK.B —
  all 4–8 quarters, all metrics present, accounting identity holds (gap 0.0).
- NFLX re-seeded post-fix: EPS now `0.54/0.43/0.66/0.72/0.59/0.56/1.23/0.80`
  (basic > diluted every quarter). NVDA re-seed idempotent (split already
  handled via restated comparatives; fix changed nothing).
- TSM/ASML seed attempts correctly refused (IFRS-only filers).

## Environment notes

- Push failed as expected (no stored credentials); 5 commits queued locally
  for the next user-supplied PAT.
- Live-browser visual check still blocked (browser VM can't reach localhost;
  tunneling blocked by proxy). Bottom-sheet behavior verified via markup +
  CSS presence, not visually.
- `curl` needs `--noproxy '*'` here.
