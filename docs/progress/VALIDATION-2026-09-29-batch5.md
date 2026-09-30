# Batch 5 live validation — 2026-09-29 (~19:10 CDT)

Push did NOT go through (no GitHub auth in this environment — `fatal: could
not read Username`); 5 commits queued locally on main. Everything below was
validated live against `uvicorn tickerlens.main:app :8123` with the batch's
code running.

## Test suite

- `.venv/bin/python -m pytest tests/ -q` → **201 passed** (188 baseline + 13 new)
- `git diff --check` → clean

## Defect-hunt evidence (fresh tickers UNH, HD, GS, PG, DIS — all seeded live)

| Check | Result |
|---|---|
| UNH Total Equity, all 8 quarters | populated (was "—" ×8); renders `$104.51B` on detail tab |
| PG Cash & Equivalents, all 8 quarters | populated (was "—" ×8); renders `$9.94B`; identity exact: 72.21+54.31=126.52=assets |
| GS Q2 2026 EPS Basic | `$20.98` (filled from diluted); other quarters keep own basic values |
| Overview / detail / compare pages × 5 tickers | all HTTP 200, no 500s |
| Valuation cards | render (GS Strong Buy, UNH/HD/PG/DIS Sell-side signals — data-driven, not asserted) |

## Range-view ZIP (`GET /company/{ticker}/download/range.zip`)

| Check | Result |
|---|---|
| `?chart_from=Q3 FY2025&chart_to=Q4 FY2026` (MSFT) | 200; 6 per-quarter CSVs + `MSFT_range_summary.csv` (metric × quarters) |
| Summary content | `# Periods,Q3 FY2025 → … → Q4 FY2026`; `Revenue,70066000000.0,…,90007000000.0` |
| Unknown ticker | 404 |
| Detail page | "⇓ Range (ZIP)" button present, carries current window params |

## Watchlist notes (`POST /company/{ticker}/watch/note`)

| Check | Result |
|---|---|
| Save note (plain POST) | 303; note renders on Overview page and home-page pins |
| HTMX (`HX-Request`) | returns `watch_note.html` partial with saved note |
| Unwatched ticker | 404 |
| Cleanup | test watch entry removed; watchlist empty again |

## Commits (local, queued for push)

- `4c67edc` fix: instant-fact staleness blind spot
- `f5db400` fix: per-quarter diluted→basic EPS fallback
- `b5afe1d` feat: range-view ZIP download (PRD §4.8 slice 3)
- `0db0c2b` feat: watchlist notes (PRD §4.6 slice 4)
- `4b99a36` docs: status, decisions, PRD, handoff for batch 5

**One thing needing the user:** `git push origin main` needs their fresh fine-grained PAT (paste in chat, used once via env var, never stored).
