# Live Validation — 2026-09-30 batch 10 (pre-push)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here. This batch's
> push failed (no GitHub auth in the session), so this validates the queued
> commits against the running app pre-push.

## Scope

- **Commit range:** `7820800..7808dba` (4 commits: XBRL gap-fill defect fix, range-mode hero KPIs, watchlist tags, cross-company compare)
- **Validated at:** 2026-09-30 ~15:30 CDT, server `uvicorn tickerlens.main:app :8123` restarted fresh from `main` (restarts at each code change; final boot after the vs-page commit)
- **Method:** HTTP requests against the live server + HTML content assertions. Test suite: **250 passed**.
- **Push status:** ❌ failed — `git push origin main` → "could not read Username" (no PAT supplied this session). 26 commits queued locally.

## Results

| # | Check | Result |
|---|---|---|
| 1 | Defect fix: T Q1/Q2 2026 FCF now $2.72B/$5.10B after refresh (was None — continuing-ops OpCF tag switch) | ✅ |
| 2 | Defect fix: INTC cash $8.79B/$8.95B for the two skipped quarters after refresh (was None — restricted-cash composite tag) | ✅ |
| 3 | Defect fix: previously stored T/INTC values byte-identical after re-seed (gap-fill never overrides winner) | ✅ |
| 4 | Range KPIs: `/company/KO/detail/data?chart_from=Q4%20FY2024&chart_to=Q2%20FY2025` → hero shows "Q4 FY2024 → Q2 FY2025 (3 quarters, summed)", $35.21B revenue, "vs prior 2Q" badges | ✅ |
| 5 | Range KPIs: full-history detail data has no "quarters, summed" (period cards unchanged) | ✅ |
| 6 | Watchlist tags: `POST /company/KO/watch` → 303 (watched) | ✅ |
| 7 | Watchlist tags: `POST /company/KO/watch/tags` (HTMX) → 200, `id="watch-tags"` partial with `dividend` + `blue-chip` chips | ✅ |
| 8 | Watchlist tags: home page pins show both tag chips | ✅ |
| 9 | Watchlist tags: Overview page renders the tag editor (`id="watch-tags"`, "Add tags…") | ✅ |
| 10 | Watchlist tags: `POST /company/KO/watch/tags` on unwatched ticker → 404 (correct guard) | ✅ |
| 11 | Watchlist tags: `POST /company/KO/watch/remove` → 303 (test watch removed; DB left as found) | ✅ |
| 12 | Alembic migration `8b2d4f6a1c93` applied to live DB (tags column present) | ✅ |
| 13 | Cross-company compare: `GET /company/KO/vs/PEP` → 200, all 8 metric rows + both signal badges | ✅ |
| 14 | Cross-company compare: real values both sides — KO $12.47B ▲+12.1% vs PEP $24.18B ▲+6.4% | ✅ |
| 15 | Cross-company compare: Overview page shows "⇄ Compare" peer-ticker form | ✅ |
| 16 | Full test suite | ✅ 250 passed |

**16/16 live checks passed.**

## Environment notes

- Live-browser visual check remains blocked (browser VM localhost ≠ app VM; no tunneling). HTTP render + content assertions are the validation.
- `curl` against localhost needs `--noproxy '*'` here.
- The dev server does not hot-reload service/route code: restarted 4× this batch (after each code change) — symptom when forgotten is the new template rendering with old service behavior.
- Push queue stands at 26 commits awaiting the next user-supplied PAT.
