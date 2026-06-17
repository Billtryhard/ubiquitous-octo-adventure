"""Dated JSON snapshot files for pulled option chains.

Every run writes ``snapshots/TICKER_YYYY-MM-DD.json`` containing the full
pulled chain for each underlying. These files are the human-readable mirror of
the ``chain_snapshots`` SQLite table and let later layers diff today vs a prior
run for new-strike / new-expiry detection without touching the database.
"""

from __future__ import annotations

import json
import os
from datetime import date

from .models import Chain


def snapshot_path(snapshots_dir: str, ticker: str, asof: date) -> str:
    return os.path.join(snapshots_dir, f"{ticker}_{asof.isoformat()}.json")


def write_chain_snapshot(chain: Chain, snapshots_dir: str = "snapshots") -> str:
    """Write a chain to its dated JSON file and return the path."""
    os.makedirs(snapshots_dir, exist_ok=True)
    path = snapshot_path(snapshots_dir, chain.ticker, chain.asof)
    with open(path, "w") as fh:
        json.dump(chain.to_record(), fh, indent=2, sort_keys=True)
    return path


def load_chain_snapshot(path: str) -> dict:
    """Load a previously written snapshot JSON (raw dict form)."""
    with open(path) as fh:
        return json.load(fh)
