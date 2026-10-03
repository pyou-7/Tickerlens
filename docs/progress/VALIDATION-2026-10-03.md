# Validation log — 2026-10-03 (overnight session, batches 12–13 prep)

## Integration: Gemini UI work merged
- `origin/main` had moved 4 commits ahead (Gemini's UI overhaul: theme engine,
  microinteractions, home redesign, popular bar). Local batch-11 commits rebased
  on top cleanly after resolving 3 conflicts:
  - `detail.html`: mobile bottom-sheet behavior merged with Gemini's new
    light/dark card styling (behavior added, visuals untouched).
  - `docs/DECISIONS.md`, `docs/PROJECT_STATUS.md`: kept both sides' entries.
- Result: `main` = 2917cf2 + 6 replayed commits, tree clean, `git diff --check` clean.

## UI verification (styled screenshots, local Tailwind build)
- `scripts/screenshot.py` added (persistent, self-healing: installs Chrome,
  rebuilds CSS, starts server). Fixed a build bug where unquoted `**` glob
  dropped all `md:` variants from the CSS.
- Screenshots: home, AAPL overview/detail/compare/vs — all render correctly
  in the new light/dark theme. No regressions from the rebase.
- **Found and fixed**: floating "Print PDF / History ZIP" pill overlapped the
  sticky per-period download bar at the bottom of the detail page. Merged into
  a single action bar (Full history ZIP + per-period CSV + Print PDF).
  Commit `b1074f4`. Screenshot-verified after fix.

## Batch 12: rate-aware valuation guardrail
- `compute_valuation(ten_year_yield_pct=None)` → default 4.5% benchmark.
- Fair P/E capped at `100 / (yield × 0.6)`; binding adds a reasoning note and
  caps confidence at Medium. Dormant below ~2.7% yields.
- Live check: 32% grower at 5.3% yield → 31.4x cap, note present, Medium.
- Tests: 270 passing (5 new + 2 snapshot expectations updated).

## Test summary
- `pytest tests/ -q`: **270 passed**, 20 warnings (pre-existing SQLAlchemy
  deprecation).
- Live HTTP: `/company/AAPL` 200, `/api/search?q=aapl` 200.
- Screenshots: 6 styled renders reviewed, no visual regressions.

## Push state
- 8 commits queued locally (6 batch-11 + pill fix + batch 12). Push still
  blocked on auth (SSH key / token from user). Not nagged.
