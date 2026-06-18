"""Command-line entry point for the data, valuation & analytics layers."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from .analytics import AnalyticsConfig, compute_analytics, store_analytics
from .macro import MacroWeights, SyntheticMacroProvider, compute_macro_score, store_macro
from .news import YFinanceHeadlineProvider, compute_news
from .positions import load_positions
from .providers import SyntheticProvider
from .report import render, render_analytics, render_market_context
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

    # Market data feed
    p.add_argument("--feed", choices=["synthetic", "webull"], default="synthetic",
                   help="market data feed for quotes & option chains (default synthetic)")
    p.add_argument("--webull-max-expiries", type=int, default=None,
                   help="cap expirations pulled per underlying from Webull (default: all)")
    p.add_argument("--feed-fallback", action="store_true",
                   help="fall back to the synthetic feed if the live feed can't connect")
    p.add_argument("--import-positions", nargs="?", const="positions.json", default=None,
                   metavar="PATH",
                   help="import live holdings from Webull into PATH (default positions.json) "
                        "and exit; does not run the monitor")

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

    # Market context (Layer 3)
    p.add_argument("--no-macro", action="store_true", help="skip the deterministic macro gate")
    p.add_argument("--no-news", action="store_true", help="skip the Claude news analysis")
    p.add_argument("--news-window", type=int, default=3, help="headline lookback in days (default 3)")
    p.add_argument("--live-news", action="store_true",
                   help="pull live headlines via yfinance instead of the synthetic provider")
    p.add_argument("--no-news-cache", action="store_true",
                   help="ignore the per-day news cache (will re-bill the API)")
    p.add_argument("--macro-weights", default=None,
                   help="comma-separated weights vix_level,vix_percentile,term_structure,"
                        "breadth,credit (must sum to 1.0)")
    return p


def _parse_macro_weights(spec):
    if not spec:
        return MacroWeights()
    parts = [float(x) for x in spec.split(",")]
    if len(parts) != 5:
        raise argparse.ArgumentTypeError(
            "--macro-weights needs 5 comma-separated values: "
            "vix_level,vix_percentile,term_structure,breadth,credit"
        )
    w = MacroWeights(*parts)
    w.validate()
    return w


def _build_feed(args):
    """Select the market data feed, with optional synthetic fallback."""
    if args.feed == "synthetic":
        return SyntheticProvider(rate=args.rate)

    if args.feed == "webull":
        from .webull_feed import WebullProvider
        try:
            return WebullProvider.from_env(max_expiries=args.webull_max_expiries)
        except Exception as exc:
            msg = f"webull feed unavailable: {exc}"
            if args.feed_fallback:
                print(f"{msg} — falling back to synthetic feed", file=sys.stderr)
                return SyntheticProvider(rate=args.rate)
            raise SystemExit(
                f"{msg}\nSet WEBULL_EMAIL / WEBULL_PASSWORD (and WEBULL_MFA / "
                f"WEBULL_TRADE_PIN if required), or pass --feed-fallback."
            )
    raise SystemExit(f"unknown feed {args.feed!r}")


def _import_positions(args) -> int:
    """Pull live holdings from Webull, write the positions file, and exit."""
    from .webull_feed import WebullProvider, write_positions_file
    try:
        provider = WebullProvider.from_env(max_expiries=args.webull_max_expiries)
    except Exception as exc:
        raise SystemExit(
            f"position import needs the Webull feed: {exc}\n"
            f"Set WEBULL_EMAIL / WEBULL_PASSWORD (and WEBULL_MFA / WEBULL_TRADE_PIN if required)."
        )
    positions = provider.fetch_positions()
    if not positions:
        print("No open positions returned by Webull — nothing written.", file=sys.stderr)
        return 1
    write_positions_file(positions, args.import_positions)
    print(f"Imported {len(positions)} position(s) from Webull -> {args.import_positions}")
    for p in positions:
        print(f"  {p.id}  x{p.contracts:g} @ {p.entry_price:g}")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.import_positions is not None:
        return _import_positions(args)
    provider = _build_feed(args)
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

        # Market context (Layer 3): macro gate + Claude news analysis
        macro_result = None
        if not args.no_macro:
            weights = _parse_macro_weights(args.macro_weights)
            inputs = SyntheticMacroProvider().get_macro_inputs(args.asof)
            macro_result = compute_macro_score(inputs, weights)
            store_macro(storage, macro_result)

        news_results = []
        if not args.no_news:
            headline_provider = YFinanceHeadlineProvider() if args.live_news else None
            news_results = compute_news(
                positions, args.asof, storage,
                headline_provider=headline_provider,
                window_days=args.news_window,
                use_cache=not args.no_news_cache,
            )

        if macro_result is not None or news_results:
            print(render_market_context(macro_result, news_results))
    finally:
        storage.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
