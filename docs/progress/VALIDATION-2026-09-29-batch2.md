# Live Validation — 2026-09-29 (batch 2)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here. This batch's
> push failed (no GitHub auth in this environment — commits queue locally),
> so this validates the committed changes against the running app.

## Scope

- **Commit range:** `2db06bb..eb5febb` (3 commits: ex-99 exhibit discovery fix, compare mode slice 1, docs)
- **Validated at:** 2026-09-29 ~07:30 CDT, server `uvicorn tickerlens.main:app :8123` restarted fresh from `main`
- **Method:** HTTP requests against the live server + HTML content assertions (16 checks). Test suite: **157 passed**.

## Results

| # | Check | Result |
|---|---|---|
| 1 | `GET /` → 200 | ✅ |
| 2 | Test suite: 157 passed (8 new ir_download + 9 new compare), `git diff --check` clean | ✅ |
| 3 | Fresh-ticker defect hunt: META / GOOGL / TSLA / AMD seeded via `/company/{ticker}` → all 200, 8 unique quarter options each, no duplicates | ✅ |
| 4 | GOOGL Q2 FY2026 FCF −$5.86B verified against raw XBRL facts (OpCF YTD $84.86B − Q1 $45.79B = $39.07B; CapEx YTD $80.60B − Q1 $35.67B = $44.93B; FCF = −$5.86B) — genuine AI-capex quarter, NOT a bug | ✅ |
| 5 | Press-release highlights gap found: 7/11 seeded tickers had 0/8 periods with highlights (NVDA, META, GOOGL, TSLA, AMD, JNJ, RDDT) vs 8/8 for AAPL/MSFT/PLUG | ✅ |
| 6 | Root cause confirmed: NVDA's 8-K index lists `q2fy27pr.htm` (no "ex99" anywhere) — old matcher returned None | ✅ |
| 7 | Fixed matcher discovers all 8 NVDA `q*Nfy*pr.htm` exhibits via `discover_earnings_filings` | ✅ |
| 8 | Backfill blocked by environment: SEC Archives doc fetches → 403 "Undeclared Automated Tool" (index listings + JSON API unaffected); enrichment self-heals on future refreshes | ✅ (documented) |
| 9 | `GET /company/AAPL/compare` → 200; default Q3 FY2026 vs Q3 FY2025; Revenue $109.42B vs $94.04B, Δ +$15.38B / +16.4% ▲ | ✅ |
| 10 | `?preset=qoq` → Q3 FY2026 vs Q2 FY2026; EPS diluted $2.02 vs $2.01, Δ +$0.01 / +0.5% | ✅ |
| 11 | Free-form `?period_a=Q1 FY2026&period_b=bogus` → falls back to YoY-ago Q1 FY2025, 200 | ✅ |
| 12 | `GET /company/GOOGL/compare?period_a=Q2 FY2026&period_b=Q1 FY2026` → 200; Revenue $119.80B vs $109.90B, Δ +$9.90B / +9.0% ▲ | ✅ |
| 13 | `GET /company/ZZZZ/compare` → 404 (friendly, not 500) | ✅ |
| 14 | "⇄ Compare periods" link present in detail-page breadcrumb | ✅ |
| 15 | Detail page + per-period CSV download + history ZIP still 200 after changes (no regressions) | ✅ |
| 16 | `git push origin main` → failed (`could not read Username` — no GitHub credentials in this environment); 3 commits queued locally | ✅ (expected) |

## Notes

- The SEC 403 on Archives document fetches is new environmental behavior observed this batch (index/JSON API fine). It blocks press-release backfills for all tickers right now, not just the newly-fixed ones. Worth retrying in a later batch; a proper declared `EDGAR_USER_AGENT` with contact info may help, but inventing contact details is not appropriate — flag to the user if it persists.
- Compare mode is quarterly-only (slice 1). Yearly compare, range-mode tables, and the 5-year-ago preset stay future.
