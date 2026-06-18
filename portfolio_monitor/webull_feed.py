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

import json
import os
import re
from datetime import date, datetime
from typing import List, Optional, Sequence, Tuple

from .models import OPTION, SHARES, Chain, OptionQuote, Position
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


# OCC option symbol, e.g. "AAPL  260918C00190000":
#   <root><YYMMDD><C|P><strike * 1000, zero-padded to 8>
_OCC_RE = re.compile(r"^\s*(?P<root>[A-Za-z.\-]+)\s*(?P<ymd>\d{6})(?P<cp>[CP])(?P<strike>\d{8})\s*$")


def parse_occ_symbol(symbol: str):
    """Parse an OCC option symbol into (underlying, option_type, strike, expiry).

    Returns ``None`` if the string is not an OCC option symbol (e.g. plain
    equity tickers like ``"AAPL"``).
    """
    if not symbol:
        return None
    m = _OCC_RE.match(symbol)
    if not m:
        return None
    ymd = m.group("ymd")
    expiry = date(2000 + int(ymd[0:2]), int(ymd[2:4]), int(ymd[4:6]))
    option_type = "call" if m.group("cp") == "C" else "put"
    strike = int(m.group("strike")) / 1000.0
    return m.group("root").upper(), option_type, strike, expiry


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

    # -- live positions -----------------------------------------------------

    def fetch_positions(self) -> List[Position]:
        """Import the account's current holdings as :class:`Position` rows.

        Read-only: this reads positions, it does not place or modify orders.
        Cost basis maps to ``entry_price`` (per-share premium for options, per
        share for stock) so unrealized P/L lines up with how you entered.
        """
        raw = _account_positions(self.client)
        out: List[Position] = []
        for item in raw:
            pos = position_from_webull(item)
            if pos is not None:
                out.append(pos)
        return out


def _account_positions(client) -> List[dict]:
    """Pull the raw position rows from whichever client method exists.

    The unofficial package has shifted between ``get_positions()`` and
    ``get_account()['positions']`` across versions, so try both.
    """
    if hasattr(client, "get_positions"):
        rows = client.get_positions()
        if rows:
            return list(rows)
    if hasattr(client, "get_account"):
        acct = client.get_account() or {}
        return list(acct.get("positions", []))
    return []


def position_from_webull(raw: dict) -> Optional[Position]:
    """Map one raw Webull position dict into a :class:`Position`.

    Tolerant of the unofficial response shape: option terms come from explicit
    fields when present, otherwise from parsing the OCC symbol.
    """
    ticker_info = raw.get("ticker") or {}
    symbol = (
        ticker_info.get("symbol")
        or ticker_info.get("disSymbol")
        or raw.get("symbol")
        or ""
    )

    qty = _f(raw.get("position")) or _f(raw.get("quantity"))
    if not qty:
        return None  # closed / zero-quantity line

    # Decide option vs. stock. Prefer explicit signals, fall back to OCC parse.
    asset_type = str(raw.get("assetType") or ticker_info.get("type") or "").lower()
    explicit_opt = any(
        raw.get(k) is not None or ticker_info.get(k) is not None
        for k in ("optionType", "strikePrice", "optionExpireDate", "expireDate", "direction")
    )
    occ = parse_occ_symbol(symbol)
    is_option = (asset_type == "option") or explicit_opt or occ is not None

    if is_option:
        option_type = (
            raw.get("optionType")
            or ticker_info.get("optionType")
            or raw.get("direction")
            or ticker_info.get("direction")
        )
        strike = _f(raw.get("strikePrice") or ticker_info.get("strikePrice"))
        expiry_str = (
            raw.get("optionExpireDate")
            or raw.get("expireDate")
            or ticker_info.get("expireDate")
        )
        underlying = (
            raw.get("unSymbol") or ticker_info.get("unSymbol")
        )
        expiry = None
        if expiry_str:
            try:
                expiry = date.fromisoformat(str(expiry_str)[:10])
            except ValueError:
                expiry = None
        # Fill any gaps from the OCC symbol.
        if occ is not None:
            occ_root, occ_type, occ_strike, occ_expiry = occ
            underlying = underlying or occ_root
            option_type = option_type or occ_type
            strike = strike if strike is not None else occ_strike
            expiry = expiry or occ_expiry
        if option_type:
            option_type = str(option_type).lower()
            if option_type in ("c", "long", "buy"):
                option_type = "call"
            elif option_type in ("p", "short", "sell"):
                option_type = "put"
        if not (underlying and option_type and strike is not None and expiry):
            return None  # not enough to value it — skip rather than guess

        cost_price = _option_cost_per_share(raw, qty)
        return Position(
            asset_type=OPTION,
            ticker=underlying,
            option_type=option_type,
            strike=strike,
            expiry=expiry,
            entry_price=cost_price if cost_price is not None else 0.0,
            contracts=qty,
        )

    # Stock / ETF lot.
    if not symbol:
        return None
    cost_price = _f(raw.get("costPrice"))
    if cost_price is None:
        total = _f(raw.get("cost"))
        if total is not None and qty:
            cost_price = total / qty
    return Position(
        asset_type=SHARES,
        ticker=symbol,
        entry_price=cost_price if cost_price is not None else 0.0,
        contracts=qty,
    )


def _option_cost_per_share(raw: dict, qty: float) -> Optional[float]:
    """Per-share premium for an option lot (our entry_price convention)."""
    cost_price = _f(raw.get("costPrice"))
    if cost_price is not None:
        return cost_price
    total = _f(raw.get("cost"))
    if total is not None and qty:
        # Webull totals are dollars; each contract is 100 shares.
        return total / (qty * 100.0)
    return None


def positions_to_json(positions: Sequence[Position]) -> str:
    """Serialize positions into the ``{"positions": [...]}`` file format that
    :func:`portfolio_monitor.positions.load_positions` reads back."""
    rows = [p.to_record() for p in positions]
    return json.dumps({"positions": rows}, indent=2)


def write_positions_file(positions: Sequence[Position], path: str) -> None:
    with open(path, "w") as fh:
        fh.write(positions_to_json(positions))
        fh.write("\n")
