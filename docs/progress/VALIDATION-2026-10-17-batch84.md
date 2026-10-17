# Validation — batch 84 (2026-10-17): round-30 seeds + forward-split share-restatement fix + spaced state-tag description fix

## Pre-touch suite
- `git fetch origin`: no new origin commits (local main 81 ahead of origin/main, unchanged this batch).
- Full suite BEFORE any code: **727 passed** in ~26s (only pre-existing SQLAlchemy `utcnow` DeprecationWarnings).
- Dev server on :8123 was down — restarted via `hidden_files/serve_tickerlens.py` (cwd=repo root) before seeding.

## Seeds
- `hidden_files/batch84_seed.py`: LRCX, KLAC, ADI, REGN, VRTX, BSX — **all OK, 8 quarters each**. DB now 227 companies.
- Audit `hidden_files/batch84_audit.py`: clean FY sequences (LRCX Jun-FY, ADI Nov-FY), period ends strictly descending, identities hold, no amber notes.
- ADI/BSX "No XBRL facts for total_liabilities" seed warnings are benign: `_derive_missing_balance_sheet` closes A = L + E to the dollar (verified per quarter).

## Defect forensics (raw companyfacts, CIK-verified)
- **KLAC mixed-basis EPS (real defect):** FY2026Q4 $1.0312 (post-split, from the 2026-08-06 10-K) vs FY2026Q1–Q3 $8.47/$8.68/$9.12 (pre-split 10-Q facts). The 10-K restated FY2024/FY2025 annual EPS at 0.1001x and diluted shares 133.75M → 1,337.5M (genuine 10:1 split) but tags no quarterly comparatives. `_split_share_restatements` only accepted the reverse-split direction (share ratio 1/r), so the forward restatement was never found → `_filing_share_basis` empty → neighborhood heuristic had no quarterly post-split reference → conservative no-op. The 9M YTD fact did rescale (annual references existed), which is why Q4 derived correctly while Q1–Q3 stayed 10x off.
- **LRCX triple split-vote dates (not a defect):** 2025-01-31/04-25/08-11 log lines are per-vote-date warnings fired before `_merge_duplicate_events` collapses them — one merged event per metric, no double rescale; series verified consistent.
- **VRTX undescribed (real defect):** EDGAR name "VERTEX PHARMACEUTICALS INC / MA" (space after slash) defeated the state-tag regex, so the suffix-stripped Wikipedia fallback never fired.

## Fixes (backend-only, no template change)
- `data/xbrl.py`: `_split_share_restatements` accepts both ratio directions (r and 1/r); per-share event match (inverse scale, 400-day window, corroborated event) still guards false positives. Docstring corrected (shares scale WITH the split ratio).
- `data/wikipedia.py`: `_strip_corp_suffix` regex → `\s*/\s*[A-Z]{2}/?\s*$`.
- **Re-seeds:** KLAC — all 8 quarters now post-split basis (Q1–Q3 0.848/0.869/0.913, consistent with Q4 1.0312; FY2025Q1–Q3 0.702/0.617/0.817). DD (regression check) — series byte-identical. VRTX description backfilled live.
- **DB-wide residual scan:** same-sign adjacent-quarter EPS ratio within 3% of a split ratio → 36 hits, all earnings-volatility doubles on small denominators (0.45→0.90 shapes); no other split victim.
- **Tests:** 2 new xbrl (forward share-restatement detection; KLAC-shaped end-to-end rescale, fails pre-fix), 1 new wikipedia assert. Full suite: **729 passed**. `git diff --check` clean.

## Live routes (:8123, restarted for the new code)
| Route | Status | Note |
|---|---|---|
| / | 200 | |
| /company/KLAC | 200 | |
| /company/KLAC/detail | 200 | repaired series renders: 0.848/0.869/0.913/1.0312 |
| /company/VRTX | 200 | description renders |
| /company/LRCX/detail | 200 | split-adjusted series consistent |
| /calendar | 200 | |

**6/6 green.** No template change — screenshot gate N/A.

## Carried follow-ups rechecked (no action)
- **XOM self-heal:** not yet — companyfacts NetIncomeLoss frames still end at CY2026Q1; first healing 10-K (FY2026) files Feb 2027.
- **V / BRK.B EPS tagging:** not resumed — still unfixable from the feed.
- **SPG dominant-quarter self-heal:** waits on the Q4-2026 filing.
- **Pending-filing cohort:** 14 tickers (unchanged; EDGAR companyfacts lag ~2.5 months by design; notes render and self-clear).

## Commits
- 2 commits this batch: `fix:` forward-split share-restatement detection + spaced state-tag strip (with tests) + `docs:` batch 84 row/entry/validation log.
- Queue: 83 commits ahead of origin/main, 0 pushed (no token pasted this session).
