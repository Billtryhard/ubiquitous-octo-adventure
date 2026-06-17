"""Per-position valuation: marks, P&L, DTE, greeks, and progress metrics."""

from __future__ import annotations

from datetime import date
from typing import Optional

from . import blackscholes as bs
from .models import Greeks, OptionQuote, Position, PositionValuation, SHARES_PER_CONTRACT


def progress_pct(entry: float, current: float, level: Optional[float]) -> Optional[float]:
    """Progress from entry toward a target/stop level, as a percentage.

    ``0%`` means the mark is still at entry; ``100%`` means it has reached the
    level. Works in either direction (target above or stop below entry) and
    can read negative (moved the wrong way) or above 100 (overshot). Returns
    ``None`` when the level is unset or coincides with entry.
    """
    if level is None or entry is None or current is None:
        return None
    denom = level - entry
    if denom == 0:
        return None
    return (current - entry) / denom * 100.0


def value_share_position(
    position: Position, spot: Optional[float], asof: date
) -> PositionValuation:
    mark = spot
    cost_basis = position.entry_price * position.contracts
    current_value = mark * position.contracts if mark is not None else None
    pl = (current_value - cost_basis) if current_value is not None else None
    pl_pct = (pl / cost_basis * 100.0) if (pl is not None and cost_basis) else None
    return PositionValuation(
        position_id=position.id,
        asof=asof,
        asset_type=position.asset_type,
        ticker=position.ticker,
        mark=mark,
        current_value=current_value,
        cost_basis=cost_basis,
        unrealized_pl=pl,
        unrealized_pl_pct=pl_pct,
        progress_to_target=progress_pct(position.entry_price, mark, position.target_price),
        progress_to_stop=progress_pct(position.entry_price, mark, position.stop_price),
    )


def value_option_position(
    position: Position,
    quote: Optional[OptionQuote],
    spot: float,
    asof: date,
    rate: float = 0.045,
) -> PositionValuation:
    mult = SHARES_PER_CONTRACT
    mark = quote.mark if quote is not None else None
    iv = quote.iv if quote is not None else None

    cost_basis = position.entry_price * mult * position.contracts
    current_value = mark * mult * position.contracts if mark is not None else None
    pl = (current_value - cost_basis) if current_value is not None else None
    pl_pct = (pl / cost_basis * 100.0) if (pl is not None and cost_basis) else None

    dte = position.days_to_expiry(asof)

    greeks = None
    if iv is not None and dte is not None:
        t = max(dte, 0) / 365.0
        delta, gamma, theta, vega = bs.greeks(
            position.option_type, spot, position.strike, max(t, 1e-9), rate, iv
        )
        greeks = Greeks(delta=delta, gamma=gamma, theta=theta, vega=vega)

    return PositionValuation(
        position_id=position.id,
        asof=asof,
        asset_type=position.asset_type,
        ticker=position.ticker,
        mark=mark,
        current_value=current_value,
        cost_basis=cost_basis,
        unrealized_pl=pl,
        unrealized_pl_pct=pl_pct,
        dte=dte,
        greeks=greeks,
        iv=iv,
        progress_to_target=progress_pct(position.entry_price, mark, position.target_price),
        progress_to_stop=progress_pct(position.entry_price, mark, position.stop_price),
    )
