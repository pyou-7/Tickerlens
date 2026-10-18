# VALIDATION — batch 78 (2026-10-16) — round-22 seeding + NI/shares EPS derivation (GD)

**QUEUED (no push this run — no token pasted in session).**

## What changed
- `src/tickerlens/data/xbrl.py`:
  - New `SHARES_TAG` map (basic/diluted weighted-average share counts).
  - New `_eps_from_income_shares(companyfacts, fiscal_year_end, metric, skip_ends)`: quarterly EPS = quarterly NI / quarterly weighted-average shares for ends the chain lacks; Q4 via share-month residual (12·FY_avg − 9·9M_avg)/3; skipped for two-class filers (`_has_distributed_eps_facts`); honestly blank when no share facts exist. Source tag `Derived:<shares tag>/NetIncomeLoss`.
  - `quarterly_income_metric`: final `_merge_gap_fill` of filed EPS series + derived series for EPS_BASIC/EPS_DILUTED (filed facts always win).
- `tests/data/test_xbrl.py`: `make_companyfacts` gains optional `diluted_shares_values`/`basic_shares_values`; 4 new tests (GD-shaped derivation + Q4 residual incl. annual reconciliation, filed-facts-win, two-class guard, no-shares blank).
- `docs/PROJECT_STATUS.md`: batch-78 row. `docs/DECISIONS.md`: batch-78 entry.
- DB: seeded GD, NSC, CHTR, DASH, AFRM (8 quarters each, clean); BNY refreshed (already in DB); GD re-seeded after the fix — all 8 quarters now carry EPS, FY2025 derived sum $15.45 = filed annual. DB at 191 companies.

## Test results
- `tests/data/test_xbrl.py`: 122/122 pass (4 new).
- Full suite: **702 passed**, 0 failed (baseline 698 + 4 new).
- `git diff --check`: clean.

## Live validation (:8123, server restarted to pick up the xbrl.py change)
| Route | Status |
|---|---|
| `/company/GD` | 200 — overview renders TTM diluted EPS $15.90 (+10.4% YoY); valuation card has real EPS where it previously had none |
| `/company/BNY` | 200 |
| `/company/NSC` | 200 |
| `/company/CHTR` | 200 |
| `/company/DASH` | 200 |
| `/company/AFRM` | 200 |
| `/company/GD/detail` | 200 |
| `/company/GD/compare` | 200 |
| `/company/GD/vs/NSC` | 200 |

Freshness sweep (pre-seed): the 10 pending-note 10-Qs (filed Jul/Aug 2026) still not ingested by EDGAR — verified live against PYPL companyfacts (Revenues max end 2026-03-31); amber notes stay honest. XOM still has no 10-K. AFRM FY2026Q4 EPS $4.59 verified as genuine filed data (10-K NI $1.93B / 349M shares).

## Template/UI
No template change (backend-only) — screenshot gate N/A.

## Commits
- (pending) fix: NI/shares EPS derivation for annual-only EPS filers + round-22 seeds (batch 78)
- (pending) docs: batch 78 (PROJECT_STATUS row + DECISIONS entry)
- (pending) docs: batch 78 validation log (queued, no push)
- Queue now 69 commits ahead of origin/main, 0 pushed.
