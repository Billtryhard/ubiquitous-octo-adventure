"""Command-line entry point for the data & valuation layer."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from .providers import SyntheticProvider
from .report import render
from .runner import run_from_file


def parse_asof(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"--asof must be YYYY-MM-DD, got {value!r}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="portfolio_monitor",
        description="Pull marks, snapshot chains, and value an options + equity book.",
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
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    provider = SyntheticProvider(rate=args.rate)
    result = run_from_file(
        args.positions,
        asof=args.asof,
        provider=provider,
        db_path=args.db,
        snapshots_dir=args.snapshots_dir,
        rate=args.rate,
        write_snapshots=not args.no_snapshots,
    )
    print(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
