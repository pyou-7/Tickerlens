# Live Validation — 2026-09-29 (batch 3)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here. This batch's
> push failed (no GitHub auth in this environment — commits queue locally),
> so this validates the committed changes against the running app.

## Scope

- **Commit range:** `34ce7ae..21d33af` (6 commits: bank revenue composite fix,
  unwatch-from-home, docs, yearly compare, finance Revenues preference, docs)
- **Validated at:** 2026-09-29 ~11:15 CDT, server `uvicorn tickerlens.main:app :8123`
  restarted fresh from `main` (multiple restarts during the batch — each code
  change was followed by a restart before live checks)
- **Method:** HTTP requests against the live server + HTML content assertions +
  raw XBRL fact cross-checks. Test suite: **176 passed**, `git diff --check` clean.

## Results

| # | Check | Result |
|---|---|---|
| 1 | Test suite: 176 passed (10 new xbrl + 5 new compare-yearly + 1 new route-yearly + 3 new unwatch), `git diff --check` clean | ✅ |
| 2 | Defect hunt: seeded COST (Aug FYE), BAC, WMT (Jan FYE), V, WFC, MET, O — all 200, 8 unique quarters each, zero duplicate (fy, fp) labels | ✅ |
| 3 | JPM defect: seeded with 2013–2014 quarters — banks file quarterly revenue as `NoninterestIncome` + `InterestIncomeExpenseNet` while the generic `Revenues` chain holds only annual facts (JPM quarterly `Revenues` stops 2014); revenue is the canonical anchor so net income/EPS were also pinned a decade stale | ✅ (found) |
| 4 | Bank pattern confirmed across JPM/BAC/WFC/C/GS/MS/USB: components fresh for all 7; composite == quarterly `Revenues` exactly on BAC 2026 Q1/Q2 (diff 0) | ✅ |
| 5 | Fix: finance SICs (6000–6299) use composite revenue series; JPM re-seeded → Q3 FY2024–Q2 FY2026, revenue $42–57B; Q2 2026 $57.35B cross-checked = $31.836B + $25.511B standalone quarterly facts (no YTD leakage) | ✅ |
| 6 | WFC re-seeded → fresh quarters (old code would have seeded 2019–2020) | ✅ |
| 7 | MET defect: seeded with $0.72B/quarter revenue — generic chain prefers `RevenueFromContractWithCustomerExcludingAssessedTax`, a fee-income sub-component for insurers, over the filer's own `Revenues` ($19.15B total) | ✅ (found) |
| 8 | Fix: finance SICs (6000–6999) prefer quarterly `Revenues` when absolutely current (≤400d from today — relative check can't work since JPM files nothing else quarterly); MET re-seeded → $19.15B Q2 2026, matches raw fact | ✅ |
| 9 | JPM regression under new ordering: re-seeded → still $57.35B composite (stale `Revenues` correctly skipped) | ✅ |
| 10 | Unwatch-from-home: `POST /company/V/watch` → pin shows `watch/remove?next=home` form; plain POST → 303 to `/`, row removed; HTMX POST → 200 with `watchlist-section` partial; Overview toggle unchanged (303 to `/company/{ticker}`, button partial for HTMX) | ✅ |
| 11 | Yearly compare: `GET /company/AAPL/compare?mode=yearly` → 200, headers FY2026 vs FY2025, correct `selected` year options, `name="year_a"` present | ✅ |
| 12 | `?mode=yearly&year_a=2025&year_b=2024` → 200; `&year_a=2099` → falls back to latest/prior; quarterly `GET /company/AAPL/compare` → 200 with YoY/QoQ presets intact (yearly hides them) | ✅ |
| 13 | `GET /company/BAC/compare?mode=yearly` → 200 (bank-seeded data renders yearly compare) | ✅ |
| 14 | Detail/overview/compare pages for JPM, WFC, COST render 200 after re-seeds (no regressions) | ✅ |
| 15 | `git push origin main` → failed (`could not read Username` — no GitHub credentials in this environment); 6 commits queued locally (20 total ahead of origin/main) | ✅ (expected) |

## Notes

- TSM (foreign 20-F filer, IFRS taxonomy) → friendly 404 page (not a 500). The company exists; the app can't parse IFRS `ifrs-full` tags yet. Recorded as a known limitation, not fixed this batch — IFRS support is a real feature, not a defect fix.
- SEC Archives 403 ("Undeclared Automated Tool") persists — press-release backfills still blocked, self-heal on future refreshes.
- Server-restart discipline mattered twice this batch: live checks ran against stale code until the server was restarted (caught by the `?next=home` param being ignored and JPM re-seeding stale quarters). Always restart `uvicorn` after code changes before HTTP verification.
- Suggested next batch focus: range-mode slice 2 (KPI cards / tables follow the From/To range, not just the chart) or the 5-year-ago compare preset once history depth grows; otherwise continue the defect hunt with energy/utilities tickers.
