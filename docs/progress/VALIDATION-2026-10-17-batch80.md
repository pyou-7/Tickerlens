# Validation — batch 80 (2026-10-17): fresh-ticker hunt round 26 + 3 defect fixes

## Pre-touch suite
- `git fetch origin`: no new origin commits (local main 71 ahead → now 75 ahead of origin/main).
- Full suite BEFORE any code: **702 passed** in 32.72s (only pre-existing SQLAlchemy `utcnow` DeprecationWarnings).
- Dev server on :8123 was down — restarted via `hidden_files/serve_tickerlens.py` (repo .venv python, cwd=repo root); restarted again after the code changes to pick them up.

## Seeds
- `hidden_files/batch80_seed.py`: EL, CL, KVUE, ECL, DD, APD — **all OK, 8 quarters each**.
- Audit `hidden_files/batch80_audit.py`: clean FY sequences (EL Jun-FY, APD Sep-FY); no balance-sheet identity gaps >1%; no suspicious EPS; EPS/revenue complete; descriptions present on 5/6 (EL rescued — see fixes); no pending-filing notes.

## Defect forensics (raw companyfacts, CIK-verified)
- **DD mixed-basis EPS:** 1-for-3 reverse split ~Jul 2026 proven by share counts (419.7M → 139.9M for 2025Q2); 2026-08-04 10-Q restated comparatives ×3.0. Stored series had 6/8 quarters on old basis (0.39/−0.3/−1.4 unscaled) — the batch-51 neighborhood heuristic failed on value overlap. Fixed via share-basis filing classification; DD re-seeded to 3.24/−0.84/−4.20/0.42/−0.87/−0.90/1.17/1.05, NI/shares coherent.
- **NOW (sweep find):** real 5-for-1 split (shares 209M → 1,047M); 2024Q3/2025Q3 stored old-basis (2.09/2.07, 2.42/2.40). Re-seeded to 0.419/0.365/0.44/0.37/0.485/0.387/0.45/0.29.
- **False-positive 0.5x split event:** DD's 2026 10-K halved continuing-ops EPS (Qnity → discontinued ops); the fallback list's independent detection read it as a 2:1 split. Fixed by sharing primary-chain events (latent — never corrupted stored data).
- **EL description:** top Wikipedia hit was correct; the é defeated all relevance paths. Fixed via NFKD fold; backfilled and rendering.
- **CLX risk factors:** "ITEM 1.A. RISK FACTORS" dotted heading unhandled. Fixed; rescued (7,998 chars). BNY stays honestly None (incorporates Item 1A by reference, WFC class).
- DB-wide split sweep: all 11 recent-split tickers re-extracted and diffed vs stored — 10 identical, NOW fixed as above.

## Live routes (:8123, server restarted for new code)
| Route | Status | Note |
|---|---|---|
| / | 200 (0.25s) | fast |
| /company/DD | 200 (30.5s) | cold enrichment; valuation Strong Sell via disclosed sales fallback (TTM EPS growth 132.6% > 40% design max; confidence Medium) |
| /company/DD/detail | 200 (1.0s) | |
| /company/EL | 200 (20.5s) | cold enrichment; Estée Lauder description renders |
| /company/CL | 200 (14.7s) | cold enrichment |
| /company/KVUE | 200 (22.0s) | cold enrichment |
| /company/ECL | 200 (17.2s) | cold enrichment |
| /company/APD | 200 (17.2s) | cold enrichment |
| /company/DD/vs/APD | 200 (2.2s) | |
| /calendar | 200 (0.38s) | 197/197 companies dated |
| /company/CLX/detail | 200 (27.6s) | cold enrichment; rescued risk factors render |
| /company/NOW | 200 (8.1s) | repaired series |
| /company/DD/detail | 200 (1.0s) | re-check after restart |

**13/13 green.** No template change (backend-only, screenshot gate N/A).

## Code/tests
- `src/tickerlens/data/xbrl.py`: share-basis split classification (`_split_share_restatements`, `_filing_share_basis`, `_split_basis_share_facts`); `_is_pre_split_basis` takes known filing basis as decisive; split events detected once on primary chain, shared with fallback.
- `src/tickerlens/data/wikipedia.py`: NFKD diacritic fold in `_normalize_words`/`_word_set`/`_squashed`.
- `src/tickerlens/data/filings.py`: full-line-anchored dotted "ITEM 1.A." start alternative + dotted 1.B/1.C/2 end markers.
- 10 new tests (4 wikipedia, 4 xbrl, 2 filings). Full suite: **712 passed**. `git diff --check` clean.

## Commits
- `8e48e96` fix: share-basis split classification + shared primary-chain split events (batch 80)
- `eed037a` fix: diacritic folding in Wikipedia title comparison (batch 80)
- `10e6393` fix: dotted 'ITEM 1.A.' risk-factor heading (batch 80)
- `7320130` docs: batch 80 - round-26 seeds EL/CL/KVUE/ECL/DD/APD + split-basis/diacritic/dotted-1A fixes
- (pending) docs: batch 80 validation log (queued, no push)
- Queue now 75 commits ahead of origin/main, 0 pushed (no token pasted this session).
