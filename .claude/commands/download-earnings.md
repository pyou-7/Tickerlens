# download-earnings — Earnings PDF Download Skill

Downloads quarterly earnings materials for any US public company and organizes them into a structured folder.

## How to Run

```bash
.venv/bin/python scripts/download_earnings.py TICKER [--periods 4] [--out output]
```

**Examples:**
```bash
.venv/bin/python scripts/download_earnings.py AVGO
.venv/bin/python scripts/download_earnings.py CRWD --periods 4
.venv/bin/python scripts/download_earnings.py AAPL --periods 8
```

## Output Structure

All companies land under `output/` (gitignored). If a company folder already exists,
only new files/folders are added — existing PDFs are never overwritten.

```
output/                          ← gitignored
├── AVGO/
│   ├── FY2025/
│   │   ├── Earnings_Releases/   AVGO_Q2_FY2025_Earnings_Release.pdf
│   │   └── SEC_Filings/         AVGO_Q2_FY2025_10-Q.pdf
│   └── FY2026/
│       └── ...
├── CRWD/
│   └── ...
└── CIEN/
    └── ...
```

Q4 of a fiscal year is always the 10-K (annual report) and is stored in SEC_Filings/.

## What It Downloads

| Document | Source | How |
|----------|--------|-----|
| Earnings Release | SEC EDGAR 8-K exhibit 99 | Download HTML → Chrome headless PDF |
| 10-Q | SEC EDGAR main filing | Download HTML → Chrome headless PDF |
| 10-K | SEC EDGAR main filing | Download HTML → Chrome headless PDF |

**Not downloaded:** Investor presentations (Broadcom and most semis don't publish slide decks), earnings call transcripts (get from Seeking Alpha or IR webcasts).

## Key Implementation Details

### Earnings Release Detection
- Signal: `form="8-K"` with `items` containing `"2.02"` (SEC standard = "Results of Operations")
- Universal across all US public companies — no company-specific logic needed
- 8-K is matched to its quarter by filing date proximity: 0–21 days before the 10-Q/10-K

### Fiscal Year Labeling Algorithm
1. Each 10-K anchors a FY: `fy = report_date.year` (works for all US FY conventions)
2. Each 10-Q is assigned to the nearest following 10-K's FY
3. If no 10-K follows (most-recent open quarters), `fy = prior_10k_fy + 1`
4. Quarter number = ordinal position of 10-Qs within the same FY group

This handles January FY ends (CRWD FY2026 = Jan 2026), October FY ends (AVGO FY2025 = Nov 2025), and standard December ends correctly.

### Why Chrome Headless (Not WeasyPrint)
EDGAR filings are complex HTML with inline XBRL. Chrome produces faithful, well-formatted PDFs (85–153 pages for 10-Q/10-K). WeasyPrint is not installed and would require significant dependency setup on macOS.

### SEC Rate Limiting
- EDGAR `data.sec.gov` endpoints: handled by `EdgarClient` throttler (≤10/sec)
- `archive.sec.gov` (HTML downloads): raw httpx with 150ms spacing between requests
- If you see "Undeclared Automated Tool" errors, wait ~60 seconds and retry

### Caching
- EDGAR JSON responses cached in `.edgar_cache/` (by URL hash)
- Filing index HTML pages cached with `.html` extension in `.edgar_cache/`
- Re-running is safe — existing PDFs are skipped automatically

## Key Files

| File | Purpose |
|------|---------|
| `src/tickerlens/services/ir_download.py` | Core service: filing discovery, FY labeling, 8-K matching |
| `src/tickerlens/data/edgar.py` | EDGAR client: fetch_json, fetch_text, submissions, company_tickers |
| `scripts/download_earnings.py` | CLI: orchestrates download + Chrome PDF conversion |

## Known Limitations

- Chrome must be installed at `/Applications/Google Chrome.app/` (macOS only as-is)
- IR presentations (slide decks): not available on SEC EDGAR; IR sites block automation
- Transcripts: not automated; use Seeking Alpha (`seekingalpha.com/symbol/TICKER/earnings/transcripts`)
- Companies that amend 10-Qs (10-Q/A) may pull the wrong document — check if `primaryDocument` looks right
