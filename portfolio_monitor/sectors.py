"""Ticker -> sector resolution.

Resolution order:
1. an explicit config mapping (``sectors.json`` or a dict passed in), then
2. an optional yfinance fallback (``Ticker(...).info['sector']``), then
3. ``"Unknown"``.

The yfinance fallback is best-effort and wrapped in a try/except so the
analytics layer runs fully offline (the default synthetic feed never reaches
it); resolved values are cached so a given ticker is looked up at most once.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Optional

UNKNOWN = "Unknown"

# Sensible built-in defaults so common tickers resolve without any config.
DEFAULT_SECTORS: Dict[str, str] = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Technology",
    "AMD": "Technology",
    "GOOGL": "Communication Services",
    "META": "Communication Services",
    "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
    "SPY": "Index/ETF",
    "QQQ": "Index/ETF",
    "JPM": "Financials",
    "XOM": "Energy",
}


class SectorLookup:
    def __init__(
        self,
        config_path: Optional[str] = "sectors.json",
        mapping: Optional[Dict[str, str]] = None,
        use_yfinance_fallback: bool = True,
    ):
        self._map: Dict[str, str] = dict(DEFAULT_SECTORS)
        if config_path and os.path.exists(config_path):
            with open(config_path) as fh:
                self._map.update({k.upper(): v for k, v in json.load(fh).items()})
        if mapping:
            self._map.update({k.upper(): v for k, v in mapping.items()})
        self.use_yfinance_fallback = use_yfinance_fallback
        self._cache: Dict[str, str] = {}

    def sector(self, ticker: str) -> str:
        ticker = ticker.upper()
        if ticker in self._map:
            return self._map[ticker]
        if ticker in self._cache:
            return self._cache[ticker]
        resolved = self._yfinance_sector(ticker) if self.use_yfinance_fallback else None
        resolved = resolved or UNKNOWN
        self._cache[ticker] = resolved
        return resolved

    @staticmethod
    def _yfinance_sector(ticker: str) -> Optional[str]:
        try:  # pragma: no cover - network/optional dependency
            import yfinance  # type: ignore

            info = yfinance.Ticker(ticker).info or {}
            sector = info.get("sector")
            return sector or None
        except Exception:
            return None
