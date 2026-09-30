# Live Validation — 2026-09-30 (batch 7)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here. This batch's
> push failed (no GitHub auth in this environment — commits queue locally),
> so this validates the committed changes against the running app.

## Scope

- **Commit range:** `e486283..9f82bb5` (2 commits: "Also trades as" sibling-ticker link; sqlite journal/wal/shm gitignore)
- **Validated at:** 2026-09-30 ~03:20 CDT, server `uvicorn tickerlens.main:app :8123` started fresh from `main` after the code commit
- **Method:** HTTP requests against the live server + HTML content assertions (10 checks). Test suite: **214 passed** (210 prior + 4 new sibling-ticker tests).

## Results

| # | Check | Result |
|---|---|---|
| 1 | `GET /company/GOOGL` → 200, header shows `Also trades as <a href="/company/GOOG">GOOG</a>` | ✅ |
| 2 | `GET /company/AAPL` → 200, no "Also trades as" hint (single-class filer) | ✅ |
| 3 | `GET /company/GOOGL/detail` → 200, sibling hint present | ✅ |
| 4 | `GET /company/GOOGL/compare` → 200, sibling hint present | ✅ |
| 5 | `GET /company/GOOG` (not previously seeded) → 200 via auto-seed path, header shows `Also trades as <a href="/company/GOOGL">GOOGL</a>` — reverse link verified | ✅ |
| 6 | `sibling_tickers` unit tests: same-CIK match, self excluded, sorted, case-insensitive exclude, empty for single-class/unknown CIK | ✅ 4/4 |
| 7 | `get_sibling_tickers` unknown ticker → `[]` (never raises; hint hides) — verified via service call on a bogus ticker | ✅ |
| 8 | `GET /` (home, watchlist pins) → 200 (regression) | ✅ |
| 9 | Per-period CSV download `GET /company/GOOGL/detail/download` → 200 (regression) | ✅ |
| 10 | Full test suite | ✅ 214 passed |

**10/10 live checks passed.**

## Commit-hygiene note

- Mid-batch: `git add -A` swept up a transient `tickerlens.db-journal` (SQLite journal from the running server). Caught before finalizing — removed via `git rm --cached` + amend, and added `tickerlens.db-journal/-wal/-shm` to `.gitignore` (commit `9f82bb5`). Lesson for future agents: never `git add -A` in this repo while the dev server is running; the DB journals are ephemeral.

## Defect-hunt notes (round 12, in progress at write time)

- A defect-hunting subagent is exercising fresh tickers (CRM, SNOW, NET, SHOP foreign-filer, DPZ/HON/RTX/ABBV/MRK/NFLX/COIN/PLTR/UBER/MSFT candidates) against the live app to find real data defects before this batch's next work items. Findings will land in the batch report and/or a follow-up validation log.

## Environment notes

- Live-browser visual check remains blocked: the browser VM cannot reach this machine's localhost, and outbound tunneling is blocked by the network proxy (verified 2026-09-28). HTTP render + content assertions are the visual validation until that is unblocked.

---

# Live Validation — 2026-09-30 (batch 8)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here. This batch's
> push failed (no GitHub auth in this environment — commits queue locally),
> so this validates the committed changes against the running app.

## Scope

- **Commit range:** `1fb8ced..67bdf13` (3 commits: share-implied Q4 EPS + finance-SIC FCF suppression; 404 "Did you mean" suggestions; docs)
- **Validated at:** 2026-09-30 ~07:30 CDT, server `uvicorn tickerlens.main:app :8123` restarted fresh from `main` after the code commits
- **Method:** HTTP requests against the live server + HTML content assertions and DB spot-checks (12 checks). Test suite: **220 passed** (214 prior + 4 XBRL + 2 route tests). `git diff --check` clean.

## Defect hunt (round 12)

Fresh tickers seeded beyond the usuals: **SOFI** (fintech lender, SIC 6199), **DUOL** (SaaS, SIC 7372), **UBER** (marketplace, SIC 7389), **RBLX** (gaming, SIC 7372). Two real defects found:

1. **Q4 EPS derived by subtracting per-share values** — `FY_EPS − 9M_EPS` divides by different share counts, so DUOL's FY2025 Q4 rendered diluted **$0.94 above basic $0.88** (arithmetically impossible; a huge Q3 tax benefit moved the denominators). Also left float noise (`0.8800000000000008`) in CSV exports.
2. **SoFi rendered −$3.99B FCF** — honest OpCF − CapEx arithmetic, but a meaningless metric for a lender (OpCF dominated by loan-book flows); every bank/insurer/REIT peer shows "—".

Not defects: DUOL Q3 FY2025 net income $292M / EPS $6.36 (one-time tax benefit, real filing data); UBER Q3 FY2025 $6.6B net income (investment gains, real).

## Results

| # | Check | Result |
|---|---|---|
| 1 | `POST /company/DUOL/refresh` → 200; DB: FY2025 Q4 `eps_basic=0.9047 > eps_diluted=0.8935` (was 0.8800000000000008 / 0.9400000000000004 inverted) | ✅ |
| 2 | `GET /company/DUOL/compare?period_a=Q4 FY2025&period_b=Q3 FY2025` → 200, shows `EPS (Basic) $0.90`, `EPS (Diluted) $0.89` — ranking correct, no float noise | ✅ |
| 3 | `POST /company/SOFI/refresh` → 200; DB: all 8 quarters `free_cash_flow IS NULL` (was −$3.99B) | ✅ |
| 4 | `GET /company/SOFI` → 200, Free Cash Flow KPI card renders "—" | ✅ |
| 5 | `GET /company/APPL` (unknown ticker) → 404 with "Did you mean" + `<a href="/company/AAPL">` suggestion links | ✅ |
| 6 | `GET /company/ZZZZ` with suggestion lookup forced to fail → 404, plain page, no "Did you mean" (best-effort fallback) | ✅ via unit test |
| 7 | `GET /company/DUOL`, `/company/SOFI`, `/company/DUOL/detail`, `/company/DUOL/compare` → 200 (regression; valuation card exercises the changed TTM EPS) | ✅ |
| 8 | `GET /api/search?q=appl` → 200 (regression; ranker shared with 404 suggestions) | ✅ |
| 9 | UBER/RBLX re-seeded: Q4 EPS basic ≥ diluted on all derived quarters (RBLX identical at −$0.45; UBER FY2024 Q4 $3.2944 vs $3.2972 — sub-cent flip from the filing's own cent-rounding, documented as a limitation) | ✅ |
| 10 | New XBRL tests: DUOL regression, NI-missing fallback (0.88 exact, no float noise), zero-EPS fallback, finance-SIC FCF suppression + non-finance unaffected | ✅ 4/4 |
| 11 | New route tests: 404 suggestions render; lookup failure still renders plain 404 | ✅ 2/2 |
| 12 | Full test suite | ✅ 220 passed |

**12/12 live checks passed.**

## Push status

- `git push origin main` failed: `could not read Username for 'https://github.com'` — no persistent GitHub auth in this environment (expected per standing workflow).
- **17 commits now queued locally** (`origin/main..HEAD`): batches 6, 7, and 8 (code + docs + validation logs). Next push session with a fresh PAT will clear the queue.

## Environment notes

- Live-browser visual check remains blocked: the browser VM cannot reach this machine's localhost, and outbound tunneling is blocked by the network proxy (verified 2026-09-28). HTTP render + content assertions are the visual validation until that is unblocked.
- SEC Archives document fetches still 403 ("Undeclared Automated Tool"); index/JSON API unaffected. Press-release highlight backfill remains self-healing on future refreshes.
