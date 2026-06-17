"""Command-line entry point for the data, valuation & analytics layers."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from .analytics import AnalyticsConfig, compute_analytics, store_analytics
from .positions import load_positions
from .providers import SyntheticProvider
from .report import render, render_analytics
from .runner import run_monitor
from .sectors import SectorLookup
from .storage import Storage


def parse_asof(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"--asof must be YYYY-MM-DD, got {value!r}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="portfolio_monitor",
        description="Pull marks, snapshot chains, value a book, and report analytics.",
    )
    p.add_argument("--positions", default="positions.json", help="positions JSON file")
    p.add_argument("--db", default="portfolio.db", help="SQLite database path")
    p.add_argument("--snapshots-dir", default="snapshots", help="directory for dated chain JSON")
    p.add_argument(
        "--asof",
        type=parse_asof,
        default=date.today(),
        help="run date (YYYY-MM-DD) used for storage/diffing; defaults to today. "
        "Marks still come from the current feed.",
    )
    p.add_argument("--rate", type=float, default=0.045, help="annual risk-free rate (default 0.045)")
    p.add_argument("--no-snapshots", action="store_true", help="skip writing dated JSON files")

    # Analytics (Layer 2)
    p.add_argument("--no-analytics", action="store_true", help="skip the analytics summary")
    p.add_argument("--sectors", default="sectors.json", help="ticker->sector config JSON")
    p.add_argument("--ticker-cap", type=float, default=40.0, help="ticker concentration cap %% (default 40)")
    p.add_argument("--sector-cap", type=float, default=60.0, help="sector concentration cap %% (default 60)")
    p.add_argument("--iv-lookback", type=int, default=252, help="IV rank/percentile lookback in days (default 252)")
    p.add_argument("--iv-min-history", type=int, default=20, help="min stored days before IV rank (default 20)")
    p.add_argument("--iv-rich", type=float, default=78.0, help="IV rank above this is 'rich' (default 78)")
    p.add_argument("--iv-cheap", type=float, default=38.0, help="IV rank below this is 'cheap' (default 38)")
    p.add_argument("--dte-warn", type=int, default=45, help="DTE at/under this surfaces time decay (default 45)")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    provider = SyntheticProvider(rate=args.rate)
    positions = load_positions(args.positions)

    storage = Storage(args.db)
    try:
        result = run_monitor(
            positions,
            asof=args.asof,
            provider=provider,
            storage=storage,
            snapshots_dir=args.snapshots_dir,
            rate=args.rate,
            write_snapshots=not args.no_snapshots,
        )
        print(render(result))

        if not args.no_analytics:
            config = AnalyticsConfig(
                ticker_cap_pct=args.ticker_cap,
                sector_cap_pct=args.sector_cap,
                iv_lookback_days=args.iv_lookback,
                iv_min_history_days=args.iv_min_history,
                iv_rich_threshold=args.iv_rich,
                iv_cheap_threshold=args.iv_cheap,
                dte_warn_threshold=args.dte_warn,
            )
            sectors = SectorLookup(config_path=args.sectors)
            analytics = compute_analytics(
                positions, result.valuations, storage, args.asof, config, sectors
            )
            store_analytics(storage, analytics)
            print(render_analytics(analytics))
    finally:
        storage.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
