# Validation — batch 85 (2026-10-17): round-31 seeds + discontinued-ops basis-break guard + ticker-title description fix

## Pre-touch suite
- `git fetch origin`: no new origin commits (local main 83 ahead of origin/main, unchanged this batch).
- Full suite BEFORE any code: **729 passed** (~28s; only pre-existing SQLAlchemy `utcnow` DeprecationWarnings).
- Dev server on :8123 was down — restarted via `hidden_files/serve_tickerlens.py` (cwd=repo root) before seeding.

## Seeds
- `hidden_files/batch85_seed.py`: TJX, ULTA, DKS, OXY, NEM, DDOG — **all OK, 8 quarters each**. DB now 233 companies.
- Audit `hidden_files/batch85_audit.py`: clean FY sequences (Jan-FY trio TJX/ULTA/DKS labeled FY2026Q2/FY2027Q2 correctly), period ends strictly descending, no balance-sheet identity gaps >2%, no pending-filing notes.
- Two audit flags investigated (see forensics): OXY FY2025Q4 revenue $1.75B (REAL DEFECT — fixed) and TJX missing description (REAL DEFECT — fixed). DKS FY2025Q4 EPS $1.4106, NEM FY2025Q4 EPS $1.1847, TJX FY2026Q4 EPS $1.5693, ULTA FY2025Q4 EPS $8.0123 all verified arithmetically honest against raw NI/share facts (DKS: FY NI $849,239K − 9M $720,902K = $128,337K Q4 NI → $1.4106 on implied ~91M shares).

## Defect forensics (raw companyfacts, CIK-verified)
- **OXY mixed-basis Q4 (real defect):** Q3-2025 10-Q tags 9M Revenues $19,841M (start 2025-01-01, incl. OxyChem) and the 2025 10-K tags FY Revenues $21,593M (continuing ops only — 10-K HTML confirms OxyChem "reported separately as discontinued operations ... for all periods presented"; 9M `IncomeLossFromDiscontinuedOperationsNetOfTax` = 0 in the 10-Q vs $262M in the 10-K). FY − 9M = $1,752M vs ~$5.4B real (Zacks: Q4 $5.42B, FY $22.08B). Ground truth cross-checked via web search (Zacks/Seeking Alpha/MarketBeat Q4-2025 reports, Feb 2026).
- **TJX undescribed (real defect):** Wikipedia's article for the company is titled "TJX" (verified via the summary API — extract opens "The TJX Companies, Inc. is an American multinational off-price department store corporation..."); the fallback's strict stripped-name match could never accept a ticker-titled article.

## Fixes (backend-only, no template change)
- `data/xbrl.py`: new `_discontinued_basis_break_starts(companyfacts)` — fires only on the filer's own proof (tagged 9M interim discontinued = 0 → tagged nonzero annual, same FY, interim filed first). `_derive_q4_income`, `_cash_flow_series_for_tag`, and the four finance revenue composites (`_finance_total_revenue`, `_bdc_quarterly_revenue`, `_bank_quarterly_revenue`, `_mreit_quarterly_revenue`) skip Q4 derivation for break FYs.
- `data/wikipedia.py`: `_best_title` fallback accepts the article titled exactly the ticker, guarded by `_title_relevant` rule 1 (acronym pages); docstring updated.
- **Re-seeds:** OXY — FY2025Q4 income fields (revenue, net_income, eps_basic, eps_diluted, free_cash_flow, ffo) NULLed, balance-sheet legs kept; TJX — description backfilled ("The TJX Companies, Inc. is an American multinational off-price department store corporation...").
- **DB-wide residual scan** (`hidden_files/batch85_blast.py`, 233 companies, 0 errors): 19 companies with historical breaks — all pre-2024 except OXY FY2025 (fixed) and D FY2025 (10-K filed a quarterly Q4 revenue stub, so derivation never fired — no action; the immaterial -$14M true-up edge case is documented in DECISIONS as a known limitation).
- **Tests:** 4 new xbrl (detector unit on OXY-shaped facts; ongoing-discontinued-ops negative — nonzero interims never trip; end-to-end income skip with no-break control deriving $1.752B; cash-flow Q4 skip), 2 new wikipedia (ticker-title acceptance; near-match "TJX Logistics" still declined). Full suite: **735 passed**. `git diff --check` clean.

## Live routes (:8123, restarted for the new code)
| Route | Status | Note |
|---|---|---|
| / | 200 | |
| /company/OXY | 200 | valuation falls back honestly: Watch, Low confidence, no model target (was feeding the bogus Q4) |
| /company/OXY/detail | 200 | bogus $1.75B gone; Q4 FY2025 income cells blank, balance sheet intact |
| /company/TJX | 200 | description renders |
| /company/DDOG/detail | 200 | |
| /calendar | 200 | |

**6/6 green.** No template change — screenshot gate N/A.

## Carried follow-ups rechecked (no action)
- **XOM self-heal:** not yet — latest quarter still FY2026Q2 (2026-06-30); first healing 10-K files Feb 2027.
- **V / BRK.B EPS tagging:** not resumed — still unfixable from the feed.
- **SPG dominant-quarter self-heal:** waits on the Q4-2026 filing.
- **Pending-filing cohort:** 14 tickers (unchanged; EDGAR companyfacts lag ~2.5 months by design; notes render and self-clear).

## Commits
- 2 commits this batch: `fix:` discontinued-ops basis-break guard + ticker-title description acceptance (with 6 tests) + `docs:` batch 85 row/entry/validation log.
- Queue: 85 commits ahead of origin/main, 0 pushed (no token pasted this session).
