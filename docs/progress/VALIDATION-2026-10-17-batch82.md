# Validation — batch 82 (2026-10-17): fresh-ticker hunt round 28 + seed-time pending-filing note fix

## Pre-touch suite
- `git fetch origin`: no new origin commits (local main 77 ahead of origin/main, unchanged this batch).
- Full suite BEFORE any code: **712 passed** in ~26s (only pre-existing SQLAlchemy `utcnow` DeprecationWarnings).
- Dev server on :8123 was down — restarted via `hidden_files/serve_tickerlens.py` (repo .venv python, cwd=repo root); backend-only change, so no restart needed afterward.

## Seeds
- `hidden_files/batch82_seed.py`: ABT, AFL, ANET, COR, HLT, MPC — **all OK, 8 quarters each**. DB now 215 companies.
- Audit `hidden_files/batch82_audit.py`: clean FY sequences (COR Sep-FY Q3 labeled correctly), period ends strictly descending, no identity gaps >2%, descriptions present on all 6, no amber notes carried.
- ANET split-log lines: 4:1 split (Dec 2024) restatements detected and merged (ratio ~0.25); pre-split quarters rescaled once — verified below.

## Defect forensics (raw companyfacts, CIK-verified)
- **MPC FY2026Q2 EPS 17.73 (NI $5.138B):** filer-real — the 2026-08-04 10-Q files USD/shares 17.73 for 2026-04-01..2026-06-30. One-time gain quarter; not a basis-mixing bug.
- **COR FY2026Q2 EPS 8.40 (NI $1.641B):** filer-real — the 2026-05-06 10-Q files 8.40 for 2026-01-01..2026-03-31. Cencora's lumpy GAAP quarters (Q4 FY2024 EPS 0.017 on a $3.4M NI quarter) are the filer's own numbers.
- **COR missing `total_liabilities` facts:** not a gap — direct `Liabilities` tag is absent (COR files LiabilitiesCurrent + LiabilitiesAndStockholdersEquity), but `_derive_missing_balance_sheet` fills it from Assets − Equity − mezzanine; stored rows have A = L + E exactly (e.g. 2026-06-30: 80.566B + 3.239B = 83.806B). No defect.
- **ANET post-split EPS basis:** the Dec-2024 4:1 split is correctly rescaled — 2024-11-08 10-Q fact 2.33 (pre-split) vs 2025-11-05 10-K restated fact 0.58; stored 0.58. No double-rescale. Batch-80 share-basis classification working on a new real filer.
- **ABT missing Q2-2026 quarter:** **real gap found** — Q2 FY2026 10-Q filed 2026-07-28 sits in submissions; companyfacts has no Q2 revenue facts (EDGAR ingestion lag), so the quarter is legitimately absent — but the batch-55 amber honesty note was NOT set: `fetch_and_persist` never called `_update_pending_filing_note`. Newly seeded companies stayed note-less until a page-view-triggered freshness check ran.

## Fix (backend-only, no template change)
- `src/tickerlens/services/financials.py` (`fetch_and_persist`): call `self._update_pending_filing_note(ticker, cik, submissions)` after the seed commit — mirrors the refresh path (batch 53); never-raising; reuses the just-warmed companyfacts cache.
- Verified live: re-seeded ABT with the new code → note set: "Q2 FY2026 results (10-Q filed Jul 28, 2026) aren't in EDGAR's data feed yet — showing Q1 FY2026. This page updates automatically once EDGAR publishes the figures."
- **Tests:** 2 new hermetic tests in `tests/services/test_pending_filing_note.py` (ABT-shaped seed sets the note; current seed leaves it clear). New test verified to fail pre-fix. Updated `test_fetch_and_persist_pull_uses_live_edgar` to `assert_any_call(fresh=True)` — the seed-time note re-reads the warmed cache after the deliberate fresh pull; intent (deliberate pull bypasses cache) unchanged.
- Full suite: **714 passed** (712 + 2 new). `git diff --check` clean.

## Live routes (:8123)
| Route | Status | Note |
|---|---|---|
| / | 200 | |
| /company/ABT | 200 | amber note renders: "Q2 FY2026 results (10-Q filed Jul 28, 2026) aren't in EDGAR's data feed yet — showing Q1 FY2026…" |
| /company/ANET | 200 | Strong Buy, Medium |
| /company/MPC | 200 | |
| /company/COR | 200 | |
| /company/HLT | 200 | |
| /company/AFL | 200 | |
| /calendar | 200 | |

**8/8 green.** No template change (backend-only, screenshot gate N/A).

## Carried follow-ups rechecked (no action)
- **XOM self-heal:** not yet — companyfacts NetIncomeLoss frames still end at CY2026Q1; first healing 10-K (FY2026) files Feb 2027.
- **V / BRK.B EPS tagging:** not resumed — still unfixable from the feed.
- **SPG dominant-quarter self-heal:** waits on the Q4-2026 filing.
- **Pending-filing cohort:** 14 tickers (prior 13 + ABT now honestly noted). EDGAR companyfacts lag ~2.5 months by design; notes render and self-clear.

## Commits
- 2 commits this batch: `fix:` seed-time pending-filing note + `docs:` batch 82 row/entry/validation log.
- Queue: 79 commits ahead of origin/main, 0 pushed (no token pasted this session).
