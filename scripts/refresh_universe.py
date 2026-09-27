#!/usr/bin/env python3
"""Tickerlens Universe & Watchlist Batch Ingestion CLI Tool.

Enables batch refreshing and ingestion across watchlist items, the local database,
or top universe tickers with rate limiting, optional disclosure extraction,
and comprehensive summary reporting.

Usage examples:
    # Refresh all pinned watchlist companies
    .venv/bin/python scripts/refresh_universe.py --watchlist

    # Refresh all companies currently in the database with 8-K disclosures
    .venv/bin/python scripts/refresh_universe.py --all-db --include-disclosures

    # Ingest or update specific tickers and pin them
    .venv/bin/python scripts/refresh_universe.py --tickers AMD,AVGO,QCOM --pin

    # Ingest top 10 market leaders (dry run preview)
    .venv/bin/python scripts/refresh_universe.py --top 10 --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from sqlalchemy import select

from tickerlens.models.company import Company
from tickerlens.models.database import get_session
from tickerlens.models.quarterly_financial import QuarterlyFinancial
from tickerlens.models.watchlist import WatchlistItem
from tickerlens.services.ingestion import IngestionService, RefreshResult


def _fmt_money(val: float | None) -> str:
    if val is None:
        return "—"
    abs_v = abs(val)
    sign = "-" if val < 0 else ""
    if abs_v >= 1e9:
        return f"{sign}${abs_v / 1e9:.1f}B"
    if abs_v >= 1e6:
        return f"{sign}${abs_v / 1e6:.1f}M"
    return f"{sign}${abs_v:,.0f}"


def print_progress(idx: int, total: int, res: RefreshResult) -> None:
    counter = f"[{idx}/{total}]"
    if res.success:
        pin_badge = " [📌 Pinned]" if res.is_pinned else ""
        rev_str = f"Rev: {_fmt_money(res.latest_revenue)}"
        ni_str = f"NI: {_fmt_money(res.latest_net_income)}"
        disc_str = f", {res.disclosures_count} docs" if res.disclosures_count else ""
        print(
            f"  {counter} \033[1;32m✓\033[0m \033[1m{res.ticker:<5}\033[0m "
            f"({res.name[:25]:<25}) → {res.latest_period:<10} | "
            f"{rev_str:<12} | {ni_str:<12} | {res.quarters_count} Qs{disc_str}{pin_badge} "
            f"(\033[90m{res.duration_seconds}s\033[0m)"
        )
    else:
        err_msg = (res.error or "Unknown error")[:50]
        print(
            f"  {counter} \033[1;31m✗\033[0m \033[1m{res.ticker:<5}\033[0m "
            f"→ FAILED: {err_msg} (\033[90m{res.duration_seconds}s\033[0m)"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tickerlens Universe & Watchlist Batch Ingestion Tool"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--watchlist",
        "-w",
        action="store_true",
        help="Refresh all pinned companies in the watchlist (default)",
    )
    group.add_argument(
        "--all-db",
        "-a",
        action="store_true",
        help="Refresh all companies currently stored in the database",
    )
    group.add_argument(
        "--top",
        type=int,
        metavar="N",
        help="Ingest/refresh top N tech universe leaders (e.g. --top 10)",
    )
    parser.add_argument(
        "--tickers",
        "-t",
        type=str,
        help="Comma-separated list of tickers (e.g. AAPL,MSFT,NVDA)",
    )
    parser.add_argument(
        "positional_tickers",
        nargs="*",
        metavar="TICKER",
        help="Optional space-separated ticker symbols",
    )
    parser.add_argument(
        "--periods",
        "-p",
        type=int,
        default=12,
        help="Number of historical quarters to fetch and normalize (default: 12)",
    )
    parser.add_argument(
        "--include-disclosures",
        "-d",
        action="store_true",
        help="Extract 8-K press release highlights, guidance, and executive commentary",
    )
    parser.add_argument(
        "--pin",
        action="store_true",
        help="Pin ingested companies to the watchlist dashboard",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Throttling delay in seconds between tickers (default: 0.2s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect target tickers and DB status without executing network fetches or writes",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output final summary results as JSON",
    )

    args = parser.parse_args()

    svc = IngestionService()
    db = get_session()

    try:
        # Determine targets
        target_tickers: list[str] = []

        if args.tickers:
            target_tickers.extend(t.strip().upper() for t in args.tickers.split(",") if t.strip())

        if args.positional_tickers:
            target_tickers.extend(t.strip().upper() for t in args.positional_tickers if t.strip())

        if args.top:
            target_tickers.extend(svc.get_top_universe_tickers(limit=args.top))
        elif args.all_db:
            companies = db.execute(select(Company).order_by(Company.ticker.asc())).scalars().all()
            target_tickers.extend(c.ticker for c in companies if c.ticker)
        elif not target_tickers or args.watchlist:
            # Default to watchlist
            items = db.execute(select(WatchlistItem).where(WatchlistItem.is_pinned.is_(True))).scalars().all()
            for it in items:
                comp = db.get(Company, it.cik)
                if comp and comp.ticker:
                    target_tickers.append(comp.ticker)

        # Deduplicate while preserving order
        target_tickers = list(dict.fromkeys(target_tickers))

        if not target_tickers:
            print("\033[1;33mWarning:\033[0m No target tickers found to refresh.")
            return 0

        # Mode banner
        if not args.json:
            print("=" * 76)
            print("\033[1;36m  TICKERLENS UNIVERSE & WATCHLIST BATCH INGESTION TOOL\033[0m")
            print("=" * 76)
            print(f"  Target Count:        {len(target_tickers)} companies")
            print(f"  Target Tickers:      {', '.join(target_tickers)}")
            print(f"  Quarters Depth:      {args.periods} periods")
            print(f"  Include Disclosures: {'Yes (8-K PR, Guidance, Exec Remarks)' if args.include_disclosures else 'No (XBRL core fundamentals)'}")
            print(f"  Auto-Pin:            {'Yes' if args.pin else 'No'}")
            print(f"  Rate Limit Delay:    {args.delay}s")
            print(f"  Execution Mode:      {'\033[1;33mDRY RUN (Preview only)\033[0m' if args.dry_run else '\033[1;32mEXECUTE\033[0m'}")
            print("-" * 76)

        if args.dry_run:
            if not args.json:
                print("  Current Database Status for Target Companies:\n")
                for idx, t in enumerate(target_tickers, 1):
                    comp = db.execute(select(Company).where(Company.ticker == t)).scalar_one_or_none()
                    if comp:
                        q_count = db.execute(
                            select(QuarterlyFinancial).where(QuarterlyFinancial.cik == comp.cik)
                        ).scalars().all()
                        w_item = db.execute(select(WatchlistItem).where(WatchlistItem.cik == comp.cik)).scalar_one_or_none()
                        pinned = " [📌 Pinned]" if w_item and w_item.is_pinned else ""
                        print(f"  [{idx}/{len(target_tickers)}] {t:<5} | CIK {comp.cik} | {len(q_count)} quarters in DB | {comp.name}{pinned}")
                    else:
                        print(f"  [{idx}/{len(target_tickers)}] {t:<5} | \033[33mNot yet ingested\033[0m (will be fetched from SEC EDGAR)")
                print("\n" + "=" * 76)
                print("  DRY RUN COMPLETE — 0 changes applied.")
                print("=" * 76)
            else:
                print(json.dumps({"dry_run": True, "target_tickers": target_tickers}, indent=2))
            return 0

        # Execute Batch
        summary = svc.refresh_tickers(
            tickers=target_tickers,
            periods=args.periods,
            include_disclosures=args.include_disclosures,
            pin=args.pin,
            delay=args.delay,
            session=db,
            progress_callback=None if args.json else print_progress,
        )

        if args.json:
            print(summary.model_dump_json(indent=2))
        else:
            print("-" * 76)
            print("\033[1;32m  BATCH REFRESH SUMMARY\033[0m")
            print(f"  • Total Processed:    {summary.total_requested}")
            print(f"  • Succeeded:          \033[1;32m{summary.succeeded}\033[0m")
            print(f"  • Failed:             {summary.failed}")
            print(f"  • Total Quarters DB:  {summary.total_quarters}")
            if args.include_disclosures:
                print(f"  • Disclosures Added:  {summary.total_disclosures}")
            print(f"  • Total Duration:     {summary.elapsed_seconds}s")
            print("=" * 76)

        return 0 if summary.failed == 0 else 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
