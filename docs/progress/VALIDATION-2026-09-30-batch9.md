# Live Validation — 2026-09-30 (batch 9)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here. This batch's
> push failed (no GitHub auth in this environment — commits queue locally),
> so this validates the committed changes against the running app.

## Scope

- **Commit range:** `f1581c3..3110fa4` (3 commits: defect-hunt round 13 fixes; range-mode tables; docs)
- **Validated at:** 2026-09-30 ~11:30–12:30 CDT, server `uvicorn tickerlens.main:app :8123` (restarted fresh mid-batch so the running code includes the new commits)
- **Method:** HTTP requests against the live server + HTML/CSV/ZIP content assertions; DB assertions on re-seeded tickers; full pytest suite (16 checks). Test suite: **226 passed** (220 prior + 6 new).

## Results

| # | Check | Result |
|---|---|---|
| 1 | Fresh seed KO → 200, 8 quarters, all metrics present, Assets = Liabilities + Equity holds (104.2 = 70.6 + 33.6) | ✅ |
| 2 | Fresh seed ABBV → 200; **defect found**: only 7 quarters (phantom FY row stole a slot — 10-K tags its 91-day Q4 `Revenues` stub fp="FY", verified vs raw SEC JSON) | ✅ found |
| 3 | Fix verified: ABBV re-seeded → **8 quarters**, Q3 FY2024 restored, Q4 FY2025 = filer's own 1.02/1.02 EPS (pre-fix seed's −0.0124/−0.0122 loss-quarter basic/diluted inversion also gone) | ✅ |
| 4 | Fresh seed MS → 200, 8 quarters, FCF correctly suppressed (finance SIC), identity holds | ✅ |
| 5 | Fresh seed NEE → 200; **defect found**: $10.3B Assets = Liabilities + Equity gap (154.79 + 55.22 ≠ 221.42 — parent-only equity tag vs total assets/liabilities) | ✅ found |
| 6 | Fix verified: NEE re-seeded → identity holds every quarter (154.79 + 66.63 = 221.42 exactly on Q1 FY2026; worst residual 401M = cross-tag filing rounding) | ✅ |
| 7 | Fresh seed AMT (REIT, finance-SIC revenue path) → 200; **defect found**: 7 quarters (same phantom-FY pattern via `_finance_total_revenue`) | ✅ found |
| 8 | Fix verified: AMT re-seeded → **8 quarters**, Q3 FY2024 restored | ✅ |
| 9 | `GET /company/KO/detail/data?chart_from=Q4%20FY2024&chart_to=Q2%20FY2025` → 200; all 3 tabs render the metric × quarters grid (Q4 FY2024, Q1 FY2025, Q2 FY2025 headers; "Range view: …" note); Net Income cells $2.19B/$3.33B/$3.81B and Total Equity $24.86B/$26.20B/$28.59B match the DB | ✅ |
| 10 | Default `GET /company/KO/detail/data` → 200, no range grid — single-period tables with YoY/QoQ unchanged (regression) | ✅ |
| 11 | Regression: `/company/KO/compare` → 200; `/company/KO/detail?granularity=yearly` → 200; `/company/APPL` → 404 with suggestions; `/api/search?q=appl` → 200; `/` → 200 | ✅ |
| 12 | Regression: history/compare/range ZIP downloads → 200; per-period CSV → 200 with correct `# Company`/`# Period` header | ✅ |
| 13 | Full test suite `.venv/bin/python -m pytest tests/ -q` | ✅ 226 passed |
| 14 | `git diff --check` | ✅ clean |
| 15 | `git push origin main` | ❌ failed as expected — `could not read Username for 'https://github.com'` (no persistent auth); 3 commits queued locally (`0f494c1`, `c812651`, `3110fa4`) |
| 16 | No `.env` in any commit; `git status` clean after commits | ✅ |

**15/16 checks passed; the 1 failure is the expected push-auth failure, not a code issue.**

## Defect-hunt notes (round 13)

- Five fresh tickers exercised (KO, ABBV, MS, NEE, AMT — beverage, pharma, bank, utility, REIT). Two real defects found and fixed; KO/MS seeded clean with no issues.
- The mislabeled-stub fix was verified to also repair the bank-composite double-count hazard (same-end stub + derived Q4 would have been summed) — MS's components didn't exhibit the mislabeling, but the code path is now guarded.
- Residual filing-rounding gaps in NEE's identity (≤401M on ~$190B) are cross-tag rounding, not a defect — left as-is.

## Suggested focus for next batch

- **Watchlist §4.6 remaining polish**: pin ordering / manual sort, or a "last refreshed" timestamp on home pins (the refresh-all slice exists but pins don't show quote age — stale prices are silent).
- **Range mode**: yearly-mode range tables (fiscal-year columns) would complete §4.2's range story; the current slice is quarterly-only.
- **Defect hunt round 14**: utilities/REITs with heavy NCI (e.g. DUK, AMT already done) and 52/53-week filers beyond COST to stress the window floors.
