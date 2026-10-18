# Validation — batch 81 (2026-10-17): fresh-ticker hunt round 27 — clean audit, no defects

## Pre-touch suite
- `git fetch origin`: no new origin commits (local main 76 ahead of origin/main, unchanged this batch).
- Full suite BEFORE any code: **712 passed** in 23.34s (only pre-existing SQLAlchemy `utcnow` DeprecationWarnings).
- Dev server on :8123 was down — restarted via `hidden_files/serve_tickerlens.py` (repo .venv python, cwd=repo root); no code changes this batch, so no restart needed afterward.

## Seeds
- `hidden_files/batch81_seed.py`: CSCO, CMCSA, CVS, AEP, AON, CCL — **all OK, 8 quarters each**. DB now 209 companies.
- Audit `hidden_files/batch80_audit.py CSCO CMCSA CVS AEP AON CCL`: clean FY sequences (CSCO Jul-FY, CCL Nov-FY — both correct), no balance-sheet identity gaps >1%, no suspicious EPS (4×-median), zero blank EPS/revenue quarters, descriptions present on all 6.

## Defect forensics (raw companyfacts, CIK-verified) — all suspicious values confirmed filer-real
- **CMCSA Q2-2025 NI $11.123B / EPS 2.98:** confirmed as the filer's own 10-Q fact (CY2025Q2, filed 2026-07-23 — an amended filing; value matches stored 11123M). One-time gain; TTM growth −49.1% handled by the declining-earnings 8× floor.
- **CVS Q3-2025 NI −$3.975B / EPS −3.13:** confirmed as the filer's own 10-Q fact (filed 2025-10-29). One-time premium-deficiency charge; valuation tempers via 10% FCF yield.
- **CSCO Q4-FY2026 EPS 0.9703:** no quarterly EPS frame in companyfacts (annual-only EPS filer) — derived via the batch-78 NI/shares path: Q4 NI $3.859B = annual $13.267B − Q1–Q3 $9.408B; 3.859/3.977 ≈ 0.9703; quarterly EPS sums to 3.34 ≈ annual 3.33. Coherent.
- **AON Q4-2025 EPS 7.83:** filer-real gain quarter; routes through the finance P/B composite (SIC 6411), not the EPS-growth guard path — Strong Sell on capped 2.5× P/B vs 6.4× current is by design.

## Live routes (:8123)
| Route | Status | Note |
|---|---|---|
| /company/CSCO | 200 (17.6s) | cold enrichment; Buy, Medium |
| /company/CMCSA | 200 (16.3s) | cold enrichment; Buy, Medium — honest declining-earnings copy |
| /company/CVS | 200 (15.6s) | cold enrichment; Strong Sell, Medium — honest floor copy, FCF tempered |
| /company/AEP | 200 (0.7s) | Strong Buy, Medium; amber note renders: "Q2 FY2026 results (10-Q filed Jul 30, 2026) aren't in EDGAR's data feed yet — showing Q1 FY2026. This page updates automatically." |
| /company/AON | 200 (17.6s) | cold enrichment; Strong Sell, Medium — finance P/B path, capped-2.5× copy |
| /company/CCL | 200 (8.0s) | cold enrichment; Strong Buy, High |
| /company/CCL/detail | 200 | |
| /company/CVS/detail | 200 | |
| /company/CSCO/vs/CMCSA | 200 | |
| /calendar | 200 | |

**10/10 green.** No template change (backend-only, screenshot gate N/A). Valuation cards on all six are guardrailed with honest copy (CMCSA declining-floor, AON P/B-cap, CVS floor+FCF-temper).

## Carried follow-ups rechecked (no action)
- **XOM self-heal:** not yet — companyfacts NetIncomeLoss frames still end at CY2026Q1; first healing 10-K (FY2026) files Feb 2027. Stored stub (2 quarters) unchanged.
- **V / BRK.B EPS tagging:** not resumed — still no quarterly EarningsPerShareDiluted frames in companyfacts. Remains unfixable from the feed.
- **Pending-filing cohort:** 13 tickers (V, PYPL, CB, PLD, C, SPGI, HUM, WELL, HCA, CDNS, GD, CLX + new AEP) — EDGAR companyfacts lag ~2.5 months behind submissions; notes rendering and self-clearing by design.

## Code/tests
- No code changes — audit found no defect class. `git diff --check` clean (no diff).
- 0 new tests (nothing to regress); suite stays 712 green.

## Commits
- No commits this batch (docs-only batch; seed data lives in the untracked local DB).
- Queue unchanged: 76 commits ahead of origin/main, 0 pushed (no token pasted this session).
