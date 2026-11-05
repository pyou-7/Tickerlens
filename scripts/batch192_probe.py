"""Batch 192 probe: inspect the three carried-forward candidates.

  1. BBY 2026-01-31: stored row carries a "Revenue ($ in millions)" line.
  2. APD 2026-03-31: asterisk-note line in the section path.
  3. CSX: dateline ".1" glue.
Prints stored rows and live extraction side by side.
"""
import sqlite3
import sys

sys.path.insert(0, "src")
from tickerlens.data.filings import extract_press_release_highlights

DB = "tickerlens.db"


def stored(ticker, pe):
    c = sqlite3.connect(DB)
    row = c.execute(
        "SELECT press_release_highlights, press_release_source FROM quarterly_financials "
        "WHERE cik IN (SELECT cik FROM companies WHERE ticker=?) AND period_end=?",
        (ticker, pe),
    ).fetchone()
    c.close()
    return row


def show(ticker, pe):
    row = stored(ticker, pe)
    print(f"===== {ticker} {pe} =====")
    if not row:
        print("  NO STORED ROW")
        return
    text, src = row
    print(f"  source={src} stored_len={len(text or '')}")
    for i, line in enumerate((text or "").splitlines()):
        print(f"  S{i:02d}: {line!r}")
    try:
        live, live_src = extract_press_release_highlights(ticker, pe)
    except Exception as e:  # noqa: BLE001
        print(f"  LIVE ERROR: {e!r}")
        return
    print(f"  live source={live_src} live_len={len(live or '')}")
    for i, line in enumerate((live or "").splitlines()):
        print(f"  L{i:02d}: {line!r}")


show("BBY", "2026-01-31")
show("APD", "2026-03-31")
