---
name: skill-earnings-download
description: How to download, organize, and PDF-convert quarterly earnings materials for any US public company using the generalized ir_download service
metadata:
  type: project
---

# Earnings Download Skill

## Run command

```bash
.venv/bin/python scripts/download_earnings.py TICKER [--periods 4]
```

Examples: `AVGO`, `CRWD`, `AAPL`. Output always lands in `output/{TICKER}/FY{year}/...`.

## What gets downloaded

- **Earnings Releases**: SEC 8-K exhibit 99 (press release) → PDF
- **SEC Filings**: 10-Q (quarterly) or 10-K (annual) → PDF
- NOT automated: investor presentations (IR sites block bots), transcripts

## Key files

- `src/tickerlens/services/ir_download.py` — filing discovery service
- `scripts/download_earnings.py` — CLI orchestrator
- `.claude/commands/download-earnings.md` — full skill reference with edge cases

## How 8-K earnings releases are detected

Universal SEC signal: `form="8-K"` with `items` containing `"2.02"` (Item 2.02 = Results of Operations). No company-specific logic needed.

## How FY/quarter labels are assigned

Algorithm anchors on 10-K report year, assigns 10-Qs to the FY of the next following 10-K. Handles Jan FY ends (CRWD) and Oct/Nov FY ends (AVGO) correctly without relying on the unreliable `fiscalYearEnd` EDGAR field.

## PDF conversion

Downloads EDGAR HTML locally (authenticated User-Agent required), then renders with Chrome headless (`/Applications/Google Chrome.app`). Produces 85–153 page PDFs for 10-Q/K, 13–14 pages for earnings releases.

**Why:** EDGAR HTML requires full browser rendering. Chrome headless is the most reliable option on macOS without extra dependencies.

## Folder structure produced

```
output/                    ← gitignored root
└── {TICKER}/              ← created on first run, added-to on subsequent runs
    └── {FY}/
        ├── Earnings_Releases/  {TICKER}_{Q}_{FY}_Earnings_Release.pdf
        └── SEC_Filings/        {TICKER}_{Q}_{FY}_10-Q.pdf  (or 10-K)
```

**Why:** No README.md or DOCUMENT_INVENTORY.md — user prefers clean folders.
`output/` is gitignored so PDFs never get committed.
Existing PDFs are always skipped (add-only, never overwrites).

## Tested with

- AVGO (Broadcom) — FY ends November, 4 quarters ✓
- CRWD (CrowdStrike) — FY ends January ✓
- CIEN (Ciena) — FY ends October ✓
