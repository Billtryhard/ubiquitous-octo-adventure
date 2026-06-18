"""Options + equity portfolio monitor — Layer 1: data & valuation.

Public surface that later layers import:

    from portfolio_monitor import run_monitor, load_positions, Storage
    from portfolio_monitor.models import Position, Chain, PositionValuation

The default feed is a deterministic synthetic provider so the monitor runs
fully offline; swap in a real :class:`FinanceProvider` for live data.
"""

from .analytics import (
    AggregateGreeks,
    Allocation,
    AnalyticsConfig,
    AnalyticsResult,
    IVEnvironment,
    compute_analytics,
    store_analytics,
)
from .models import (
    Chain,
    Greeks,
    OptionQuote,
    Position,
    PositionValuation,
    SHARES_PER_CONTRACT,
)
from .macro import (
    MacroInputs,
    MacroProvider,
    MacroResult,
    MacroWeights,
    SyntheticMacroProvider,
    compute_macro_score,
    store_macro,
)
from .news import (
    ClaudeNewsAnalyzer,
    Headline,
    HeadlineProvider,
    NewsAnalysis,
    SyntheticHeadlineProvider,
    YFinanceHeadlineProvider,
    compute_news,
)
from .positions import load_positions, parse_position
from .sectors import SectorLookup
from .webull_feed import (
    WebullProvider,
    parse_occ_symbol,
    position_from_webull,
    webull_available,
)
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
    "AggregateGreeks",
    "Allocation",
    "AnalyticsConfig",
    "AnalyticsResult",
    "IVEnvironment",
    "compute_analytics",
    "store_analytics",
    "SectorLookup",
    "MacroInputs",
    "MacroProvider",
    "MacroResult",
    "MacroWeights",
    "SyntheticMacroProvider",
    "compute_macro_score",
    "store_macro",
    "ClaudeNewsAnalyzer",
    "Headline",
    "HeadlineProvider",
    "NewsAnalysis",
    "SyntheticHeadlineProvider",
    "YFinanceHeadlineProvider",
    "compute_news",
    "WebullProvider",
    "webull_available",
    "parse_occ_symbol",
    "position_from_webull",
]
