# Validation — batch 83 (2026-10-17): fresh-ticker hunt round 29 + parent-temporary-equity mezzanine extraction

## Pre-touch suite
- `git fetch origin`: no new origin commits (local main 79 ahead of origin/main, unchanged this batch).
- Full suite BEFORE any code: **714 passed** in ~26s (only pre-existing SQLAlchemy `utcnow` DeprecationWarnings).
- Dev server on :8123 was down — restarted via `hidden_files/serve_tickerlens.py` (cwd=repo root) before seeding.

## Seeds
- `hidden_files/batch83_seed.py`: CTVA, DG, KDP, PCAR, RSG, TDG — **all OK, 8 quarters each**. DB now 221 companies.
- Audit `hidden_files/batch83_audit.py`: clean FY sequences (DG Jan-FY, TDG Sep-FY Saturday period ends), period ends strictly descending, descriptions present on all 6, no amber notes carried.
- One identity flag: **KDP FY2026Q1 6.04% / FY2026Q2 5.04%** — investigated below.

## Defect forensics (raw companyfacts, CIK-verified)
- **KDP gap exactly $4,418,000,000 both quarters:** `us-gaap:TemporaryEquityCarryingAmountAttributableToParent` = 4.418B at 2026-03-31 and 2026-06-30 (0 at 2025-12-31); `TemporaryEquityLiquidationPreference` = 4.5B — convertible preferred stock issued Q1 FY2026 to finance the JDE Peet's acquisition. Parent-attributable mezzanine equity; the batch-59 pipeline extracted only the redeemable-NCI tag, so the leg was dropped and the sheet showed A ≠ L + E. MinorityInterest (3.921B/4.196B) is correctly folded into stored total_equity already.
- **CTVA FY2025Q4 EPS −0.8046 / Q3 −0.47:** match the quarter-length 10-Q facts (start 2025-10-01 / 2025-07-01); seasonal crop-protection H2 losses, NI coherent. Filer-real, no defect.
- **TDG FY2026Q1 EPS 6.62 vs Q2 9.2:** match quarter-length facts (start 2025-10-01 / 2025-12-28); the 9M YTD 25.2 facts correctly skipped. Filer-real, no defect.
- **MPLX (backfill surprise):** $203M TemporaryEquityCarryingAmountAttributableToParent on FY2024Q3/Q4 only — the gate correctly shows it as a third leg on those two historical quarters (gap = 203M exactly), hidden elsewhere. Genuine historical mezzanine line.

## Fix (backend + 3 conditional template rows, no redesign)
- `data/xbrl.py`: new `Metric.TEMPORARY_EQUITY` (`TemporaryEquityCarryingAmountAttributableToParent`, instant USD); `BALANCE_SHEET_METRICS` + extraction wiring; `_reconcile_balance_sheet_identity` and `_derive_missing_balance_sheet` sum both mezzanine legs (A = L + mezz + E).
- `models/quarterly_financial.py`: new nullable `temporary_equity` column (auto-migrated by `ensure_schema()`) + `temporary_equity_is_third_leg` property (reuses the batch-60 gate).
- `services/financials.py`: BalanceSheet / BalanceSheetChange / CompareDeltas fields; gated "Temporary equity (mezzanine)" row in the detail table, range table, compare, and CSV exports; persistence upsert writes the column.
- Templates (one conditional row each, strictly-better data fix): `partials/detail_data.html`, `company/compare.html`, `company/tearsheet.html`.
- **Backfill** `hidden_files/batch83_backfill.py`: 221 companies from cached companyfacts — 7 affected, 39 rows (KDP 3, MPLX 6, RDDT/O/SOFI/NKE/COIN $0M noise rows — gate-hidden).
- **Tests:** 13 new — `tests/data/test_temporary_equity.py` (8 hermetic: extraction, equity-not-inflated, identity closes, none-when-absent, metric-by-end, derived-L subtracts temp, derived-E subtracts temp, both-legs-sum; fail pre-fix by construction), `tests/data/test_temporary_equity_third_leg.py` (4: gate keeps/shows/hides, both legs coexist), schema-migration test for the new column. `test_compare_yearly_passes_mode_and_years` mock updated for `deltas.temporary_equity` (was 500ing on the new template field — test-mock gap, not app defect).
- Full suite: **727 passed** (714 + 13 new). `git diff --check` clean.
- Screenshot gate: styled screenshot of `/company/KDP/detail` (Tailwind built locally, Chrome headless) — "Temporary equity (mezzanine) $4.42B" row renders between Total Liabilities and Total Equity, styling identical to sibling rows. `~/workspace/tickerlens-shots/batch83/kdp-detail-tempequity.png`.

## Live routes (:8123, restarted for the new column)
| Route | Status | Note |
|---|---|---|
| / | 200 | |
| /company/CTVA | 200 | |
| /company/DG | 200 | |
| /company/KDP | 200 | |
| /company/PCAR | 200 | |
| /company/RSG | 200 | |
| /company/TDG | 200 | |
| /company/KDP/detail | 200 | new row renders: "Temporary equity (mezzanine) $4.42B"; sheet closes |
| /company/KDP/compare | 200 | row renders |
| /company/KDP/vs/MPLX | 200 | |
| /company/KDP/tearsheet | 200 | row renders |
| /company/KDP/detail/download | 200 | CSV contains "Temporary equity (mezzanine),4418000000.0" |
| /company/KDP/compare/download | 200 | ZIP summary CSV contains the row |
| /calendar | 200 | |

**14/14 green.** No template redesign (data row only); screenshot gate satisfied.

## Carried follow-ups rechecked (no action)
- **XOM self-heal:** not yet — companyfacts NetIncomeLoss frames still end at CY2026Q1; first healing 10-K (FY2026) files Feb 2027.
- **V / BRK.B EPS tagging:** not resumed — still unfixable from the feed.
- **SPG dominant-quarter self-heal:** waits on the Q4-2026 filing.
- **Pending-filing cohort:** 14 tickers (unchanged; EDGAR companyfacts lag ~2.5 months by design; notes render and self-clear).

## Commits
- 2 commits this batch: `fix:` parent-temporary-equity mezzanine extraction + `docs:` batch 83 row/entry/validation log.
- Queue: 81 commits ahead of origin/main, 0 pushed (no token pasted this session).
