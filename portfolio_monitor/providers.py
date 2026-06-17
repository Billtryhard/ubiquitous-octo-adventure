"""Finance data feed providers.

The data layer talks to the feed through the :class:`FinanceProvider`
interface. The default :class:`SyntheticProvider` generates a deterministic,
self-consistent option chain locally so the whole monitor runs offline and
reproducibly — essential for testing the snapshot/diff and IV-history features
of later layers.

To wire in a real feed (e.g. yfinance, a broker API, or the bundled finance
MCP server), implement the same two methods and pass the instance to the
runner. Because chains are derived from a Black-Scholes surface, the synthetic
marks and the locally computed greeks stay internally consistent.
"""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional, Sequence, Tuple

from . import blackscholes as bs
from .models import Chain, OptionQuote


class FinanceProvider(ABC):
    """Abstract market-data feed."""

    @abstractmethod
    def get_spot(self, ticker: str, asof: date) -> float:
        """Current spot price for an underlying."""

    @abstractmethod
    def get_chain(
        self,
        ticker: str,
        asof: date,
        extra_contracts: Optional[Sequence[Tuple[str, float, date]]] = None,
    ) -> Chain:
        """Full option chain for an underlying.

        ``extra_contracts`` is a list of ``(option_type, strike, expiry)``
        triples that MUST appear in the returned chain even if they fall
        outside the standard grid (so every held contract is always quoted and
        snapshotted).
        """

    def quote_option(
        self, ticker: str, option_type: str, strike: float, expiry: date, asof: date
    ) -> OptionQuote:
        """Quote for a single contract. Defaults to a chain lookup."""
        chain = self.get_chain(ticker, asof, extra_contracts=[(option_type, strike, expiry)])
        q = chain.find(option_type, strike, expiry)
        if q is None:  # pragma: no cover - defensive
            raise KeyError(f"contract not found: {ticker} {option_type} {strike} {expiry}")
        return q


def _seed(*parts) -> int:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16)


def _unit(*parts) -> float:
    """Deterministic float in [0, 1) from the given parts."""
    return _seed(*parts) / 0xFFFFFFFF


class SyntheticProvider(FinanceProvider):
    """Deterministic synthetic feed driven by a Black-Scholes surface.

    Everything (spot, IV smile, prices) is a pure function of
    ``(ticker, asof)`` plus the contract terms, so:

    * re-running on the same ``asof`` reproduces identical numbers, and
    * advancing ``asof`` by a day shifts spot and IV slightly, giving later
      layers real day-over-day movement to diff and to build IV history from.
    """

    def __init__(self, rate: float = 0.045, base_prices: Optional[dict] = None):
        self.rate = rate
        # Anchor spot for a few well-known tickers; anything else is hashed.
        self.base_prices = {
            "AAPL": 190.0,
            "MSFT": 420.0,
            "SPY": 540.0,
            "NVDA": 120.0,
            "TSLA": 250.0,
            "AMD": 160.0,
        }
        if base_prices:
            self.base_prices.update(base_prices)

    # -- underlying ---------------------------------------------------------

    def _anchor_price(self, ticker: str) -> float:
        if ticker in self.base_prices:
            return self.base_prices[ticker]
        # Deterministic anchor in roughly [20, 520) for unknown tickers.
        return 20.0 + 500.0 * _unit(ticker, "anchor")

    def get_spot(self, ticker: str, asof: date) -> float:
        anchor = self._anchor_price(ticker)
        # Smooth-ish daily drift: a small deterministic wiggle around anchor.
        ordinal = asof.toordinal()
        wiggle = math.sin(ordinal / 9.0 + _unit(ticker, "phase") * 6.283)
        daily = (_unit(ticker, asof.isoformat(), "spot") - 0.5) * 0.01
        spot = anchor * (1.0 + 0.03 * wiggle + daily)
        return round(spot, 2)

    # -- volatility surface -------------------------------------------------

    def _base_iv(self, ticker: str, asof: date) -> float:
        base = 0.20 + 0.35 * _unit(ticker, "iv")  # 20%..55% baseline per name
        # Gentle term/day variation so IV history is non-trivial.
        drift = 0.04 * math.sin(asof.toordinal() / 13.0 + _unit(ticker, "ivphase") * 6.283)
        return max(0.05, base + drift)

    def _iv_for(self, ticker: str, asof: date, strike: float, expiry: date, spot: float) -> float:
        base = self._base_iv(ticker, asof)
        t = max((expiry - asof).days, 0) / 365.0
        # Volatility smile: OTM strikes carry a premium.
        moneyness = math.log(strike / spot) if spot > 0 else 0.0
        smile = 0.15 * moneyness * moneyness
        # Mild term structure: shorter dated slightly more volatile.
        term = 0.03 * math.exp(-t)
        return max(0.03, base + smile + term)

    # -- grid construction --------------------------------------------------

    def _expiries(self, asof: date) -> List[date]:
        """A handful of monthly-ish expiries after ``asof``."""
        out = []
        for weeks in (2, 6, 14, 27, 53):
            out.append(asof + timedelta(weeks=weeks))
        return out

    def _strikes(self, spot: float) -> List[float]:
        step = _strike_step(spot)
        center = round(spot / step) * step
        n = 8  # strikes on each side of the money
        return [round(center + i * step, 2) for i in range(-n, n + 1) if center + i * step > 0]

    # -- quotes -------------------------------------------------------------

    def _build_quote(
        self, ticker: str, asof: date, spot: float, option_type: str, strike: float, expiry: date
    ) -> OptionQuote:
        t = max((expiry - asof).days, 0) / 365.0
        iv = self._iv_for(ticker, asof, strike, expiry, spot)
        theo = bs.price(option_type, spot, strike, max(t, 1e-6), self.rate, iv)
        theo = max(theo, 0.01)
        # Spread widens for cheaper / less liquid contracts.
        rel_spread = 0.02 + 0.04 * _unit(ticker, strike, expiry.isoformat(), option_type, "spr")
        half = max(theo * rel_spread, 0.01)
        bid = round(max(theo - half, 0.0), 2)
        ask = round(theo + half, 2)
        last = round(theo * (1.0 + (_unit(ticker, strike, expiry.isoformat(), "last") - 0.5) * 0.01), 2)
        moneyness = abs(math.log(strike / spot)) if spot > 0 else 0.0
        liquidity = math.exp(-3.0 * moneyness)
        volume = int(2000 * liquidity * _unit(ticker, strike, expiry.isoformat(), option_type, asof.isoformat(), "vol"))
        oi = int(8000 * liquidity * _unit(ticker, strike, expiry.isoformat(), option_type, "oi"))
        return OptionQuote(
            ticker=ticker,
            option_type=option_type,
            strike=float(strike),
            expiry=expiry,
            bid=bid,
            ask=ask,
            last=last,
            iv=round(iv, 4),
            volume=volume,
            open_interest=oi,
        )

    def get_chain(
        self,
        ticker: str,
        asof: date,
        extra_contracts: Optional[Sequence[Tuple[str, float, date]]] = None,
    ) -> Chain:
        spot = self.get_spot(ticker, asof)
        expiries = self._expiries(asof)
        strikes = self._strikes(spot)

        # (option_type, strike, expiry) -> dedup set
        wanted = set()
        for exp in expiries:
            for k in strikes:
                wanted.add(("call", float(k), exp))
                wanted.add(("put", float(k), exp))
        for c in extra_contracts or []:
            otype, strike, expiry = c[0], float(c[1]), c[2]
            wanted.add((otype, strike, expiry))

        quotes = [
            self._build_quote(ticker, asof, spot, otype, strike, expiry)
            for (otype, strike, expiry) in sorted(
                wanted, key=lambda c: (c[2].isoformat(), c[0], c[1])
            )
        ]
        return Chain(
            ticker=ticker,
            spot=spot,
            asof=asof,
            pulled_at=datetime.now(),
            quotes=quotes,
        )


def _strike_step(spot: float) -> float:
    if spot < 25:
        return 1.0
    if spot < 100:
        return 2.5
    if spot < 250:
        return 5.0
    return 10.0
