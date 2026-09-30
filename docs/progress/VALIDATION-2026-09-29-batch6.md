# Live Validation — 2026-09-29 (batch 6)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here. This batch's
> push failed (no GitHub auth in this environment — commits queue locally),
> so this validates the committed changes against the running app.

## Scope

- **Commit range:** `63aa334..923f4fa` (3 commits: defect-hunt round 11 fixes, single-year ZIP feat, docs)
- **Validated at:** 2026-09-29 ~23:30 CDT, server `uvicorn tickerlens.main:app :8123` restarted fresh from `main`
- **Method:** HTTP requests against the live server + HTML/ZIP content assertions + DB spot checks. Test suite: **210 passed** (201 prior + 9 new). `git diff --check` clean.

## Results

| # | Check | Result |
|---|---|---|
| 1 | `GET /` → 200 | ✅ |
| 2 | LLY re-seed: FCF now non-null for all 8 quarters in DB ($0.16B–$7.76B, was 0/8) | ✅ |
| 3 | `GET /company/LLY` → 200; Overview FCF card renders **$7.76B** (+458.1% YoY) — was "—" | ✅ |
| 4 | COST re-seed: Q3 FY2026 FCF **$2.04B** in DB, 8/8 quarters non-null (251-day 9M fact now uncumulated) | ✅ |
| 5 | V re-seed: Total Equity **$35.66B** (= 95.05 − 59.39) — was "—" | ✅ |
| 6 | AMD/WMT/AMZN re-seed: liabilities now derived — $17.24B / $195.68B / $544.07B (were "—") | ✅ |
| 7 | Fresh tickers AMZN + CAT seeded clean; AMZN overview 200, revenue $200.6B, EPS $5.82/$5.75 | ✅ |
| 8 | `GET /company/COST/download/year.zip?year=2026` → 200, `application/zip` | ✅ |
| 9 | Archive contains `COST/COST_Q1-FY2026.csv`, `COST_Q2-FY2026.csv`, `COST_Q3-FY2026.csv`, `COST/COST_year_summary.csv` | ✅ |
| 10 | `year_summary.csv` header `# Periods,Q1 FY2026 → Q2 FY2026 → Q3 FY2026`, `metric,Q1 FY2026,Q2 FY2026,Q3 FY2026` | ✅ |
| 11 | `GET /company/COST/download/year.zip` (no year) → `COST_year_FY2026.zip` (latest-year fallback) | ✅ |
| 12 | `GET /company/COST/download/year.zip?year=1999` → 200 (unknown-year fallback, not 422) | ✅ |
| 13 | `GET /company/ZZZZ/download/year.zip` → 404 | ✅ |
| 14 | `GET /company/COST/detail?granularity=yearly` → 200; "⇓ Year (ZIP)" button present, Alpine `:href` bound to live year select | ✅ |
| 15 | Known by-design Nones unchanged: V EPS (dimensional facts excluded), bank/insurer/REIT FCF | ✅ |

## Notes

- Push to `origin/main` failed: `fatal: could not read Username for 'https://github.com'` (no persistent auth in this environment). 10 commits now queued locally (7 from batch 5 + 3 from this batch) awaiting the user's next PAT.
- SEC Archives document downloads still 403 ("Undeclared Automated Tool"); index/JSON API unaffected — press-release backfill remains best-effort and self-heals on future refreshes.
