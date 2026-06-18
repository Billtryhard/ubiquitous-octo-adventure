"""Core dataclasses shared across the data & valuation layer.

These types are intentionally lightweight and free of any I/O so that later
layers (alerting, reporting, backtesting, ...) can import and reuse them
without pulling in the data-feed or storage machinery.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

# Number of underlying shares represented by a single option contract.
SHARES_PER_CONTRACT = 100

OPTION = "option"
SHARES = "shares"


def _parse_date(value) -> Optional[date]:
    """Parse a YYYY-MM-DD string (or pass through a date) into a date."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(str(value), "%Y-%m-%d").date()


@dataclass
class Position:
    """A single line in the book — either an option or a share lot.

    For options, ``entry_price``/``target_price``/``stop_price`` are quoted
    **per share** (i.e. per-share premium). Each contract controls
    ``SHARES_PER_CONTRACT`` (100) shares, so the per-contract dollar value is
    ``price * 100``. ``contracts`` is the number of contracts for options and
    the number of shares for a share lot.
    """

    asset_type: str
    ticker: str
    entry_price: float
    contracts: float
    id: Optional[str] = None
    entry_date: Optional[date] = None
    target_price: Optional[float] = None
    stop_price: Optional[float] = None

    # Option-only fields
    option_type: Optional[str] = None  # "call" | "put"
    strike: Optional[float] = None
    expiry: Optional[date] = None

    def __post_init__(self):
        self.asset_type = self.asset_type.lower().strip()
        self.ticker = self.ticker.upper().strip()
        self.entry_date = _parse_date(self.entry_date)
        if self.is_option:
            self.option_type = (self.option_type or "").lower().strip()
            self.expiry = _parse_date(self.expiry)
            if self.option_type not in ("call", "put"):
                raise ValueError(
                    f"option {self.ticker}: option_type must be 'call' or 'put', "
                    f"got {self.option_type!r}"
                )
            if self.strike is None:
                raise ValueError(f"option {self.ticker}: strike is required")
            if self.expiry is None:
                raise ValueError(f"option {self.ticker}: expiry is required")
        if not self.id:
            self.id = self.auto_id()

    @property
    def is_option(self) -> bool:
        return self.asset_type == OPTION

    @property
    def is_shares(self) -> bool:
        return self.asset_type == SHARES

    @property
    def multiplier(self) -> int:
        """Dollar multiplier applied to a per-share price for this position."""
        return SHARES_PER_CONTRACT if self.is_option else 1

    def auto_id(self) -> str:
        """Stable id auto-generated from the contract terms.

        Options -> ``TICKER_YYYY-MM-DD_<STRIKE><C|P>`` (e.g. AAPL_2026-01-16_190C).
        Shares  -> ``TICKER_shares``.
        """
        if self.is_option:
            strike_txt = (
                f"{self.strike:g}" if self.strike is not None else "?"
            )
            cp = "C" if self.option_type == "call" else "P"
            exp = self.expiry.isoformat() if self.expiry else "?"
            return f"{self.ticker}_{exp}_{strike_txt}{cp}"
        return f"{self.ticker}_shares"

    def days_to_expiry(self, as_of: date) -> Optional[int]:
        if not self.is_option or self.expiry is None:
            return None
        return (self.expiry - as_of).days

    def to_record(self) -> dict:
        """Flat dict suitable for JSON / SQLite storage."""
        return {
            "id": self.id,
            "asset_type": self.asset_type,
            "ticker": self.ticker,
            "option_type": self.option_type,
            "strike": self.strike,
            "expiry": self.expiry.isoformat() if self.expiry else None,
            "entry_price": self.entry_price,
            "contracts": self.contracts,
            "entry_date": self.entry_date.isoformat() if self.entry_date else None,
            "target_price": self.target_price,
            "stop_price": self.stop_price,
        }


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------


@dataclass
class OptionQuote:
    """A single option contract quote pulled from the feed."""

    ticker: str
    option_type: str
    strike: float
    expiry: date
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    iv: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None

    @property
    def mark(self) -> Optional[float]:
        """Mid = (bid + ask) / 2 when both exist, else last."""
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2.0
        return self.last

    def contract_key(self) -> str:
        cp = "C" if self.option_type == "call" else "P"
        return f"{self.option_type}:{self.strike:g}:{self.expiry.isoformat()}"

    def to_record(self) -> dict:
        return {
            "ticker": self.ticker,
            "option_type": self.option_type,
            "strike": self.strike,
            "expiry": self.expiry.isoformat(),
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "mark": self.mark,
            "iv": self.iv,
            "volume": self.volume,
            "open_interest": self.open_interest,
        }


@dataclass
class Chain:
    """The full pulled option chain for a single underlying on a given date."""

    ticker: str
    spot: float
    asof: date
    pulled_at: datetime
    quotes: list = field(default_factory=list)  # list[OptionQuote]

    def find(self, option_type: str, strike: float, expiry: date) -> Optional[OptionQuote]:
        for q in self.quotes:
            if (
                q.option_type == option_type
                and math.isclose(q.strike, strike)
                and q.expiry == expiry
            ):
                return q
        return None

    def to_record(self) -> dict:
        return {
            "ticker": self.ticker,
            "spot": self.spot,
            "asof": self.asof.isoformat(),
            "pulled_at": self.pulled_at.isoformat(timespec="seconds"),
            "quotes": [q.to_record() for q in self.quotes],
        }


@dataclass
class Greeks:
    """Black-Scholes greeks, in trader conventions (see blackscholes.py)."""

    delta: float
    gamma: float
    theta: float  # per calendar day
    vega: float   # per 1 percentage-point change in IV

    def to_record(self) -> dict:
        return asdict(self)


@dataclass
class PositionValuation:
    """Computed valuation for one position on a given run date."""

    position_id: str
    asof: date
    asset_type: str
    ticker: str
    mark: Optional[float]
    current_value: Optional[float]
    cost_basis: float
    unrealized_pl: Optional[float]
    unrealized_pl_pct: Optional[float]
    dte: Optional[int] = None
    greeks: Optional[Greeks] = None
    iv: Optional[float] = None
    progress_to_target: Optional[float] = None
    progress_to_stop: Optional[float] = None

    def to_record(self) -> dict:
        rec = {
            "position_id": self.position_id,
            "asof": self.asof.isoformat(),
            "asset_type": self.asset_type,
            "ticker": self.ticker,
            "mark": self.mark,
            "current_value": self.current_value,
            "cost_basis": self.cost_basis,
            "unrealized_pl": self.unrealized_pl,
            "unrealized_pl_pct": self.unrealized_pl_pct,
            "dte": self.dte,
            "iv": self.iv,
            "progress_to_target": self.progress_to_target,
            "progress_to_stop": self.progress_to_stop,
        }
        if self.greeks is not None:
            rec.update(
                {
                    "delta": self.greeks.delta,
                    "gamma": self.greeks.gamma,
                    "theta": self.greeks.theta,
                    "vega": self.greeks.vega,
                }
            )
        else:
            rec.update({"delta": None, "gamma": None, "theta": None, "vega": None})
        return rec
