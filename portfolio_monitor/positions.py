"""Loading and validating the positions book from JSON."""

from __future__ import annotations

import json
from typing import List

from .models import OPTION, SHARES, Position

_REQUIRED_COMMON = ("asset_type", "ticker", "entry_price", "contracts")


def load_positions(path: str) -> List[Position]:
    """Load ``positions.json`` into a list of :class:`Position`.

    The file may be either a bare JSON array of rows or an object with a
    ``"positions"`` key. ids are auto-generated for option rows that omit them.
    """
    with open(path) as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        rows = data.get("positions", [])
    else:
        rows = data
    return [parse_position(row) for row in rows]


def parse_position(row: dict) -> Position:
    asset_type = str(row.get("asset_type", "")).lower().strip()
    if asset_type not in (OPTION, SHARES):
        raise ValueError(f"unknown asset_type {row.get('asset_type')!r} (expected 'option' or 'shares')")
    for key in _REQUIRED_COMMON:
        if row.get(key) in (None, ""):
            raise ValueError(f"position {row.get('ticker', '?')}: missing required field {key!r}")

    return Position(
        asset_type=asset_type,
        ticker=row["ticker"],
        entry_price=float(row["entry_price"]),
        contracts=float(row["contracts"]),
        id=row.get("id"),
        entry_date=row.get("entry_date"),
        target_price=_opt_float(row.get("target_price")),
        stop_price=_opt_float(row.get("stop_price")),
        option_type=row.get("option_type"),
        strike=_opt_float(row.get("strike")),
        expiry=row.get("expiry"),
    )


def _opt_float(value):
    if value in (None, ""):
        return None
    return float(value)
