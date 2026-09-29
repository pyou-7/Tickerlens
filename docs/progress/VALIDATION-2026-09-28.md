# Live Validation — 2026-09-28 (post-push)

> Standing workflow: after every push, validate the shipped changes live
> against the running application and record the results here.

## Scope

- **Commit range:** `2053656..862560d` (16 commits: valuation signal, defect fixes, CSV download, valuation history, FCF cross-check, search combobox)
- **Validated at:** 2026-09-28 ~22:55 CDT, server `uvicorn tickerlens.main:app :8123` restarted fresh from `main`
- **Method:** HTTP requests against the live server + HTML content assertions (17 checks). Test suite: **120 passed**.

## Results

| # | Check | Result |
|---|---|---|
| 1 | `GET /` → 200, search combobox present | ✅ |
| 2 | `GET /api/search?q=app` → 200, ranked JSON | ✅ |
| 3 | Search ranking: `q=tsl` → TSLA first; `q=johnson` → JCI, JNJ | ✅ |
| 4 | `GET /company/AAPL` → 200 | ✅ |
| 5 | Valuation card renders: Hold, Medium, $342.58 → $348.40 target (+1.7%), PEG reasoning | ✅ |
| 6 | Guardrail honesty live: "fair P/E hit the 40× cap … confidence capped at Medium" | ✅ |
| 7 | FCF cross-check footnote live: "FCF yield 2.7% (below the 4% hurdle)" | ✅ |
| 8 | `GET /company/ZZZQINVALID` → friendly 404, not 500 | ✅ |
| 9 | `GET /company/AAPL/detail` → 200 | ✅ |
| 10 | Press-release highlights show real earnings-release text | ✅ |
| 11 | Sticky download button present in detail view | ✅ |
| 12 | `GET /detail/data` HTMX partial → 200 | ✅ |
| 13 | `GET /detail/download?granularity=yearly&year=2025` → 200, `text/csv`, `attachment; filename="AAPL_FY2025.csv"`, metadata header + data rows | ✅ |
| 14 | `POST /company/AAPL/refresh` → 200 (no 500 on Wikipedia/quote failures) | ✅ |
| 15 | `GET /company/JNJ` → 200, valuation card: Strong Sell, Medium (clamp-bound honesty) | ✅ |
| 16 | `GET /company/PLUG` → 200, valuation card: Strong Buy via sales fallback | ✅ |
| 17 | Full test suite | ✅ 120 passed |

**17/17 live checks passed** (two initial script artifacts — truncated HTML segment and header-case lookup — re-verified manually as passes).

## Environment notes

- Live-browser visual check remains blocked: the browser VM cannot reach this machine's localhost, and outbound tunneling is blocked by the network proxy (verified 2026-09-28). HTTP render + content assertions are the visual validation until that is unblocked.
- `curl` against localhost needs `--noproxy '*'` in this environment (proxy env vars interfere); Python `urllib` is unaffected.
- Pushes require GitHub auth, which is not persistent here: 2026-09-28 push done via one-time user-supplied PAT (used once, never stored).
