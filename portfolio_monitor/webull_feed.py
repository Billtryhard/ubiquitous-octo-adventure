"""Live quotes & option chains from Webull (unofficial ``webull`` package).

This is a drop-in :class:`FinanceProvider` — implement ``get_spot`` and
``get_chain`` and the rest of the monitor (valuation, greeks, snapshots,
analytics) is unchanged.

⚠️ The ``webull`` PyPI package is **unofficial / reverse-engineered**. It logs
in with your Webull email + password (plus MFA / trade PIN), can break without
notice, and using it may conflict with Webull's Terms of Service. This module
is **read-only** — it pulls marks and chains, it never places orders. Keep the
synthetic provider as a fallback for offline runs.

The ``webull`` import is lazy and the field parsing is deliberately tolerant
(the unofficial response shapes drift between package versions), so importing
this module never requires the package to be installed.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import List, Optional, Sequence, Tuple

from .models import Chain, OptionQuote
from .providers import FinanceProvider


def webull_available() -> tuple[bool, str]:
    """Whether the unofficial ``webull`` package can be imported."""
    try:
        import webull  # noqa: F401
    except ImportError:
        return False, "webull package not installed (pip install webull)"
    return True, ""


def _f(value) -> Optional[float]:
    """Tolerant float coercion: handles None, '', and trailing '%'."""
    if value is None or value == "":
        return None
    try:
        s = str(value).strip().rstrip("%")
        return float(s)
    except (TypeError, ValueError):
        return None


def _i(value) -> Optional[int]:
    f = _f(value)
    return int(f) if f is not None else None


def _first_price(leg: dict, key: str) -> Optional[float]:
    """Webull legs carry either a scalar (e.g. ``bid``) or a list
    (``bidList``: ``[{'price': ...}]``). Read whichever is present."""
    if key in leg:
        return _f(leg.get(key))
    lst = leg.get(f"{key}List")
    if isinstance(lst, list) and lst:
        return _f(lst[0].get("price"))
    return None


class WebullProvider(FinanceProvider):
    """Pulls spot + full option chains from Webull.

    Construct with an already-authenticated client (preferred and testable),
    or use :meth:`from_env` to log in from environment variables.

    ``max_expiries`` bounds how many expirations are pulled per underlying for
    the full-chain snapshot (``None`` = all); each expiry is one API call.
    """

    def __init__(self, client, max_expiries: Optional[int] = None):
        self.client = client
        self.max_expiries = max_expiries

    # -- construction -------------------------------------------------------

    @classmethod
    def from_env(cls, max_expiries: Optional[int] = None) -> "WebullProvider":
        """Log in using WEBULL_EMAIL / WEBULL_PASSWORD (+ optional MFA / PIN).

        Webull login frequently requires an MFA code and a trade PIN, and may
        be interactive — for unattended runs, authenticate once and pass the
        resulting client into ``WebullProvider(client)`` directly, persisting
        the session token yourself. This helper is a convenience for the
        simple case.
        """
        ok, reason = webull_available()
        if not ok:
            raise RuntimeError(reason)
        import webull  # type: ignore

        email = os.environ.get("WEBULL_EMAIL")
        password = os.environ.get("WEBULL_PASSWORD")
        if not email or not password:
            raise RuntimeError(
                "set WEBULL_EMAIL and WEBULL_PASSWORD (and WEBULL_MFA / "
                "WEBULL_TRADE_PIN if your account requires them)"
            )
        wb = webull.webull()
        mfa = os.environ.get("WEBULL_MFA")
        login_kwargs = {}
        if mfa:
            login_kwargs["mfa"] = mfa
        result = wb.login(email, password, **login_kwargs)
        if isinstance(result, dict) and result.get("accessToken") is None and not getattr(wb, "_access_token", None):
            raise RuntimeError(f"webull login failed: {result}")
        pin = os.environ.get("WEBULL_TRADE_PIN")
        if pin:
            try:
                wb.get_trade_token(pin)
            except Exception:
                pass  # only needed for trading; quotes work without it
        return cls(wb, max_expiries=max_expiries)

    # -- spot ---------------------------------------------------------------

    def get_spot(self, ticker: str, asof: date) -> float:
        quote = self.client.get_quote(stock=ticker) or {}
        # Prefer last trade; fall back to mid of bid/ask if needed.
        spot = _f(quote.get("close")) or _f(quote.get("pPrice")) or _f(quote.get("price"))
        if spot is None:
            bid = _first_price(quote, "bid")
            ask = _first_price(quote, "ask")
            if bid is not None and ask is not None:
                spot = (bid + ask) / 2.0
        if spot is None:
            raise RuntimeError(f"webull: no spot price for {ticker}: {quote!r}")
        return round(spot, 4)

    # -- chain --------------------------------------------------------------

    def _leg_to_quote(
        self, ticker: str, option_type: str, strike: float, expiry: date, leg: dict
    ) -> OptionQuote:
        return OptionQuote(
            ticker=ticker,
            option_type=option_type,
            strike=strike,
            expiry=expiry,
            bid=_first_price(leg, "bid"),
            ask=_first_price(leg, "ask"),
            last=_f(leg.get("close")) or _f(leg.get("latestPrice")),
            iv=_f(leg.get("impVol")),
            volume=_i(leg.get("volume")),
            open_interest=_i(leg.get("openInterest")),
        )

    def get_chain(
        self,
        ticker: str,
        asof: date,
        extra_contracts: Optional[Sequence[Tuple[str, float, date]]] = None,
    ) -> Chain:
        spot = self.get_spot(ticker, asof)

        # Pull the available expirations, then the chain for each.
        exp_dates = self.client.get_options_expiration_dates(stock=ticker) or []
        dates = [e.get("date") for e in exp_dates if e.get("date")]
        if self.max_expiries is not None:
            dates = dates[: self.max_expiries]

        quotes: List[OptionQuote] = []
        for exp_str in dates:
            try:
                expiry = date.fromisoformat(exp_str)
            except (TypeError, ValueError):
                continue
            rows = self.client.get_options(stock=ticker, expireDate=exp_str) or []
            for row in rows:
                strike = _f(row.get("strikePrice"))
                if strike is None:
                    continue
                for direction in ("call", "put"):
                    leg = row.get(direction)
                    if isinstance(leg, dict):
                        quotes.append(
                            self._leg_to_quote(ticker, direction, strike, expiry, leg)
                        )

        return Chain(
            ticker=ticker,
            spot=spot,
            asof=asof,           # marks come from the live feed; asof stamps the run
            pulled_at=datetime.now(),
            quotes=quotes,
        )
