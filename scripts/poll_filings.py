#!/usr/bin/env python3
"""Tickerlens Automated SEC Filing Poller & Watcher CLI Tool.

Monitors SEC EDGAR submissions for pinned watchlist companies or specified tickers,
detects newly filed 10-Q, 10-K, or 8-K reports, and automatically triggers
comprehensive fundamental refreshes.

Usage examples:
    # Run a one-time check across pinned watchlist companies
    .venv/bin/python scripts/poll_filings.py --once

    # Run continuously as a background daemon (checking every 5 minutes)
    .venv/bin/python scripts/poll_filings.py --daemon --interval 300

    # Check specific tickers without auto-refreshing
    .venv/bin/python scripts/poll_filings.py --tickers NVDA,AAPL --no-refresh
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import signal
import sys
import time

from tickerlens.models.database import get_session
from tickerlens.services.filing_watcher import FilingWatcherService, DiscoveredFiling, WatcherCheckSummary


def print_discovered(ticker: str, discovered: list[DiscoveredFiling]) -> None:
    if not discovered:
        print(f"  • \033[1m{ticker:<5}\033[0m: No new filings (up to date)")
        return

    for d in discovered:
        status = "\033[1;32m✓ Refreshed Metrics\033[0m" if d.refreshed_metrics else "\033[33mLogged\033[0m"
        print(
            f"  🎉 \033[1;36mNEW FILING DETECTED\033[0m: \033[1m{d.ticker}\033[0m "
            f"Form \033[1m{d.form}\033[0m (Filed: {d.filing_date}, Acc: {d.accession_number[:18]}...) → {status}"
        )


def run_once(args: argparse.Namespace) -> int:
    svc = FilingWatcherService()
    db = get_session()

    try:
        now_str = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if not args.json:
            print("=" * 76)
            print("\033[1;36m  TICKERLENS AUTOMATED SEC FILING WATCHER\033[0m")
            print("=" * 76)
            print(f"  Execution Time:      {now_str}")
            print(f"  Auto-Refresh:        {'Enabled' if not args.no_refresh else 'Disabled (detect only)'}")
            print(f"  Target Scope:        {args.tickers if args.tickers else 'Pinned Watchlist Companies'}")
            print("-" * 76)

        if args.tickers:
            tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
            all_discovered: list[DiscoveredFiling] = []
            refreshed_count = 0
            for ticker in tickers:
                disc = svc.check_company_for_new_filings(
                    ticker,
                    auto_refresh=not args.no_refresh,
                    session=db,
                )
                if disc:
                    all_discovered.extend(disc)
                    if any(d.refreshed_metrics for d in disc):
                        refreshed_count += 1
                if not args.json:
                    print_discovered(ticker, disc)

            summary = WatcherCheckSummary(
                checked_count=len(tickers),
                new_filings_count=len(all_discovered),
                refreshed_companies_count=refreshed_count,
                new_filings=all_discovered,
                checked_at=now_str,
            )
        else:
            summary = svc.check_watchlist(
                pinned_only=True,
                auto_refresh=not args.no_refresh,
                session=db,
                progress_callback=None if args.json else print_discovered,
            )

        if args.json:
            print(summary.model_dump_json(indent=2))
        else:
            print("-" * 76)
            print(
                f"  Check complete: {summary.checked_count} companies scanned, "
                f"\033[1m{summary.new_filings_count}\033[0m new filings found, "
                f"\033[1m{summary.refreshed_companies_count}\033[0m companies updated."
            )
            print("=" * 76)

        return 0

    finally:
        db.close()


def run_daemon(args: argparse.Namespace) -> int:
    interval = max(30, args.interval)
    print("=" * 76)
    print("\033[1;36m  TICKERLENS SEC FILING WATCHER DAEMON STARTED\033[0m")
    print("=" * 76)
    print(f"  Polling interval:    {interval} seconds ({interval / 60:.1f} minutes)")
    print(f"  Auto-Refresh:        {'Enabled' if not args.no_refresh else 'Disabled'}")
    print("  Press Ctrl+C to terminate cleanly.")
    print("=" * 76)

    running = True

    def handle_exit(signum, frame):
        nonlocal running
        print("\n\033[1;33mShutting down filing watcher daemon...\033[0m")
        running = False

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    loop_count = 0
    while running:
        loop_count += 1
        now_str = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"\n[\033[90m{now_str}\033[0m] Cycle #{loop_count}: Checking SEC EDGAR...")
        try:
            run_once(args)
        except Exception as e:
            print(f"\033[1;31mError during polling cycle: {e}\033[0m")

        # Sleep in small increments for responsive SIGINT handling
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)

    print("Daemon stopped gracefully.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tickerlens Automated SEC Filing Poller & Watcher CLI"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously as a background polling daemon",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Polling interval in seconds for daemon mode (default: 300s / 5min)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check and exit (default)",
    )
    parser.add_argument(
        "--tickers",
        "-t",
        type=str,
        help="Comma-separated list of tickers to check instead of entire watchlist",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Record new filings without triggering automatic data refreshes",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output check summary as JSON",
    )

    args = parser.parse_args()

    if args.daemon:
        return run_daemon(args)
    return run_once(args)


if __name__ == "__main__":
    sys.exit(main())
