# Validation — batch 79 (2026-10-16): fresh-ticker hunt round 25

## Pre-touch suite
- `git fetch origin`: no new origin commits (local main 69 ahead → now 70 ahead of origin/main).
- Full suite BEFORE any code: **702 passed** in 36.55s (only pre-existing SQLAlchemy `utcnow` DeprecationWarnings).
- Dev server on :8123 was down — restarted via `hidden_files/serve_tickerlens.py` (repo .venv python, cwd=repo root).

## Seeds
- `hidden_files/batch79_seed.py`: GIS, MKC, SJM, CLX, CPB, TSN — **all OK, 8 quarters each**.
- Audit `hidden_files/batch79_audit.py`: period ends strictly descending for all 6; no balance-sheet identity gaps >2%; EPS complete on all rows; descriptions present; no pending-filing notes.

## Deep-audit forensics (raw companyfacts, CIK-verified)
- MKC FY2026Q1 EPS 3.77: filed 10-Q fact; NI 1016.2M / 269.4M shares = 3.77 coherent → genuine.
- GIS FY2026Q4 EPS −3.74: dual EPS facts (annual −0.16 frame=CY2025 vs quarterly −3.74 frame=CY2026Q2); frame-aware selection correct; FY2026 quarters sum to filed annual NI −87.6M exactly → genuine.
- SJM FY2026Q3 EPS −6.79: dual NI facts (9M YTD −526.8M vs 3-month −724.2M); quarter-length fact chosen; Q1+Q2+Q3 sums to filed 9M −526.8M exactly → genuine.
- TSN "no Liabilities/eps_basic facts" warnings: benign (composite liabilities 0.000% gap; eps_basic filled from diluted by design).

## Live routes (:8123)
| Route | Status | Note |
|---|---|---|
| /company/GIS | 200 (18.7s) | cold enrichment; valuation Watch/UNAVAILABLE = batch-62 guard, as designed |
| /company/SJM | 200 (30.9s) | cold enrichment |
| /company/TSN | 200 (28.8s) | cold enrichment |
| /company/CPB | 200 (25.8s) | cold enrichment; Strong Sell genuine (TTM EPS $1.36, −32.3% YoY → 8× floor; rationale notes guardrail, confidence Medium) |
| / | 200 (0.8s) | fast |

**5/5 green.** No template change (backend-only, screenshot gate N/A).

## Code/tests
- No defects found → no code change, no new tests. `git diff --check` clean.
- Suite state: 702 green (pre-touch; nothing touched since).

## Commits
- (pending) docs: batch 79 - round-25 seeds GIS/MKC/SJM/CLX/CPB/TSN (PROJECT_STATUS row + DECISIONS entry)
- (pending) docs: batch 79 validation log (queued, no push)
- Queue now 71 commits ahead of origin/main, 0 pushed.
