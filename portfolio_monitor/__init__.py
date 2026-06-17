"""Options + equity portfolio monitor — Layer 1: data & valuation.

Public surface that later layers import:

    from portfolio_monitor import run_monitor, load_positions, Storage
    from portfolio_monitor.models import Position, Chain, PositionValuation

The default feed is a deterministic synthetic provider so the monitor runs
fully offline; swap in a real :class:`FinanceProvider` for live data.
"""

from .models import (
    Chain,
    Greeks,
    OptionQuote,
    Position,
    PositionValuation,
    SHARES_PER_CONTRACT,
)
from .positions import load_positions, parse_position
from .providers import FinanceProvider, SyntheticProvider
from .runner import RunResult, run_from_file, run_monitor
from .snapshots import write_chain_snapshot, load_chain_snapshot
from .storage import Storage
from .valuation import value_option_position, value_share_position
from . import blackscholes

__all__ = [
    "Chain",
    "Greeks",
    "OptionQuote",
    "Position",
    "PositionValuation",
    "SHARES_PER_CONTRACT",
    "load_positions",
    "parse_position",
    "FinanceProvider",
    "SyntheticProvider",
    "RunResult",
    "run_monitor",
    "run_from_file",
    "write_chain_snapshot",
    "load_chain_snapshot",
    "Storage",
    "value_option_position",
    "value_share_position",
    "blackscholes",
]
