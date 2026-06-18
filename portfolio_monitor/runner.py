"""Orchestration: pull data, snapshot, value, persist.

``run_monitor`` is the single importable entry point that later layers build
on. It is feed-agnostic (any :class:`FinanceProvider`) and storage-agnostic
(give it a path or an open :class:`Storage`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .models import Chain, Position, PositionValuation
from .positions import load_positions
from .providers import FinanceProvider, SyntheticProvider
from .snapshots import write_chain_snapshot
from .storage import Storage
from .valuation import value_option_position, value_share_position


@dataclass
class RunResult:
    asof: date
    rate: float
    chains: Dict[str, Chain]
    valuations: List[PositionValuation]
    snapshot_files: List[str] = field(default_factory=list)

    @property
    def total_cost_basis(self) -> float:
        return sum(v.cost_basis for v in self.valuations if v.cost_basis is not None)

    @property
    def total_value(self) -> float:
        return sum(v.current_value for v in self.valuations if v.current_value is not None)

    @property
    def total_pl(self) -> float:
        return sum(v.unrealized_pl for v in self.valuations if v.unrealized_pl is not None)


def run_monitor(
    positions: List[Position],
    asof: date,
    provider: Optional[FinanceProvider] = None,
    storage: Optional[Storage] = None,
    db_path: str = "portfolio.db",
    snapshots_dir: str = "snapshots",
    rate: float = 0.045,
    write_snapshots: bool = True,
) -> RunResult:
    """Pull marks for ``asof``, snapshot chains, value every position, persist.

    ``asof`` stamps the run for storage and diffing; marks always come from the
    current feed (no historical chain reconstruction).
    """
    provider = provider or SyntheticProvider(rate=rate)

    owns_storage = storage is None
    storage = storage or Storage(db_path)
    try:
        storage.save_positions(positions)

        # Collect held option contracts per underlying so the snapshot chain
        # always includes them even if they fall off the standard grid.
        underlyings = sorted({p.ticker for p in positions})
        extra: Dict[str, list] = {t: [] for t in underlyings}
        for p in positions:
            if p.is_option:
                extra[p.ticker].append((p.option_type, p.strike, p.expiry))

        chains: Dict[str, Chain] = {}
        snapshot_files: List[str] = []
        for ticker in underlyings:
            chain = provider.get_chain(ticker, asof, extra_contracts=extra[ticker])
            chains[ticker] = chain
            storage.save_chain(chain)
            if write_snapshots:
                snapshot_files.append(write_chain_snapshot(chain, snapshots_dir))

        valuations: List[PositionValuation] = []
        for p in positions:
            chain = chains[p.ticker]
            if p.is_option:
                quote = chain.find(p.option_type, p.strike, p.expiry)
                valuations.append(
                    value_option_position(p, quote, chain.spot, asof, rate=rate)
                )
            else:
                valuations.append(value_share_position(p, chain.spot, asof))

        storage.save_valuations(valuations)

        return RunResult(
            asof=asof,
            rate=rate,
            chains=chains,
            valuations=valuations,
            snapshot_files=snapshot_files,
        )
    finally:
        if owns_storage:
            storage.close()


def run_from_file(
    positions_path: str,
    asof: date,
    **kwargs,
) -> RunResult:
    """Convenience wrapper that loads positions from JSON then runs."""
    positions = load_positions(positions_path)
    return run_monitor(positions, asof, **kwargs)
