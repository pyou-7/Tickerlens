# Live Validation — 2026-09-28, batch 3

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here. (Pushes in
> this batch failed on GitHub auth — commits are local; validation below
> covers the shipped code as it runs.)

## Scope

- **Commits:** `8b5ce62` (watchlist), `adc2cee` (XOM label fix), `d6d46fd` (Cmd+K)
- **Validated at:** 2026-09-28 ~23:30 CDT, server `uvicorn tickerlens.main:app :8123` restarted fresh from `main`
- **Method:** HTTP requests + HTML content assertions against the live server. Test suite: **125 passed**.

## Results

| # | Check | Result |
|---|---|---|
| 1 | `POST /company/AAPL/watch` (HX-Request) → 200, returns "★ Watching" button posting to `/watch/remove` | ✅ |
| 2 | `GET /` shows Watchlist section with AAPL pinned | ✅ |
| 3 | `POST /company/AAPL/watch/remove` (HX-Request) → 200, returns "☆ Watch" button | ✅ |
| 4 | `GET /` no longer shows Watchlist section after unwatch | ✅ |
| 5 | Non-JS `POST /company/MSFT/watch` → 303 → company page; MSFT pinned on home | ✅ |
| 6 | Home pin row shows ticker, name, last price, valuation-signal badge with color | ✅ |
| 7 | XOM detail selector: `['Q2 FY2026', 'Q2 FY2025']` — unique after re-seed (was duplicated) | ✅ |
| 8 | XOM DB rows: `Q2 FY2025 2025-06-30`, `Q2 FY2026 2026-06-30` — labels corrected in place via upsert | ✅ |
| 9 | MSFT detail: 8 unique quarters (`Q1 FY2025`…`Q4 FY2026`), overview 200 | ✅ |
| 10 | RDDT (recent IPO) detail: 8 unique quarters (`Q3 FY2024`…`Q2 FY2026`), overview 200 | ✅ |
| 11 | RDDT valuation card: Buy, Medium, price $143.08 → model target | ✅ |
| 12 | RDDT CSV download `?granularity=quarterly&quarter=Q2%20FY2026` → 200 | ✅ |
| 13 | `/api/search?q=redd` → 200, RDDT in results | ✅ |
| 14 | `GET /` header renders `⌘K` hint badge | ✅ |
| 15 | `/static/js/search.js` served contains the Cmd+K keydown listener; `node --check` clean | ✅ |
| 16 | Full test suite | ✅ 125 passed |

**16/16 live checks passed.** No new defects found on MSFT or RDDT.

## Defect found and fixed (round 4)

- **XOM comparative-label collision:** XOM's SEC CIK (`0002115436`) holds only one filing, so the 2025-06-30 comparative column inherited `fy=2026` and duplicated the "Q2 FY2026" selector option. Fixed in `xbrl._dedupe_period_labels` (unique (fy, fp) enforced at extraction; latest end keeps its label). Verified live after re-seed.

## Environment notes

- Pushes fail: no GitHub credentials on this machine (`could not read Username for 'https://github.com'`). 4 commits now queued locally (`4fc7a9d`, `8b5ce62`, `adc2cee`, `d6d46fd`).
- `curl` against localhost needs `--noproxy '*'` here; Python `urllib` is unaffected.
