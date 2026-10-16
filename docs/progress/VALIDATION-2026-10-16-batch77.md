# VALIDATION — batch 77 (2026-10-16) — Item 1A heading forensics (GE/HAL/HON/ICE/INTC/MS)

**QUEUED (no push this run — no token pasted in session).**

## What changed
- `src/tickerlens/data/filings.py`:
  - `_RISK_START_RE`: new full-line-anchored alternative for legacy parenthesized numbering (`Item 1(a). Risk Factors.` / `ITEM 1(A). RISK FACTORS`), horizontal-whitespace-only so TOC split-lines and mid-sentence cross-references can't match.
  - `_RISK_END_RE`: new `1(b)` alternative (covers ICE's spaced `ITEM 1 (B). UNRESOLVED STAFF COMMENTS`).
  - New `_RISK_TITLE_LINE_RE` (bare title-case `Risk Factors`) and `_RISK_RUNIN_RE` (`RISK FACTORS.` + prose on the same line), plus `_followed_by_prose` viability check (≥ 20 chars).
  - Fallback rewritten: all viable standalone/run-in candidates, longest-section-wins (replaces exactly-one-caps-line rule). Incorporation-by-reference guard untouched.
- `tests/data/test_filings.py`: 6 new tests (legacy 1(a) incl. TOC-split + cross-ref traps, spaced-paren 1(B), run-in heading, title-case fallback with TOC/running-header exclusion, longest-caps-wins over Honeywell-style running headers, title-case TOC-only → None).
- `docs/PROJECT_STATUS.md`: batch-77 row. `docs/DECISIONS.md`: batch-77 entry.
- DB: `scripts/backfill_risk_factors.py` rescued GE, HAL, HON, ICE, INTC, MS (all ~8k chars, real Item 1A prose verified) → 183/186 companies with risk factors. BNY/WFC (incorporate by reference) and XOM (no 10-K yet) remain honest Nones.

## Test results
- `tests/data/test_filings.py`: 36/36 pass (6 new).
- Full suite: **698 passed**, 0 failed (baseline 692 + 6 new).
- `git diff --check`: clean.

## Live validation (:8123, server restarted to pick up the filings.py change)
| Route | Status |
|---|---|
| `/company/HAL/detail` | 200, rescued Halliburton risk text renders (`When considering an investment in Halliburton…`) |
| `/company/GE` | 200 |
| `/company/MSFT` | 200 |
| `/calendar` | 200 |
| `/` | 200 |

Real-data extraction verified pre-backfill against the cached 10-K HTMLs: GE/HAL/HON/ICE/INTC/MS all extract genuine Item 1A opening prose (no TOC stubs, no cross-ref winners, no next-section bleed within the 8k truncation).

## Template/UI
No template change (backend-only) — screenshot gate N/A.

## Commits
- `8850a0b` fix: Item 1A heading forensics — legacy 1(a), title-case fallback, run-in headings (batch 77)
- `b62bbcc` docs: batch 77 (PROJECT_STATUS row + DECISIONS entry)
- Queue now 66 commits ahead of origin/main, 0 pushed.
