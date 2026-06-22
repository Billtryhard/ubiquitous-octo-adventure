"""Black-Scholes pricing and greeks, computed locally with the stdlib only.

No numpy / scipy: the standard normal CDF is built from ``math.erf``.

Conventions returned by :func:`greeks`:

* ``delta`` - per 1.00 move in the underlying (raw, per share).
* ``gamma`` - per 1.00 move in the underlying (raw, per share).
* ``theta`` - **per calendar day** (annual theta / 365).
* ``vega``  - per **1 percentage-point** (0.01) change in implied vol.

All greeks are per-share. Multiply by 100 (shares/contract) and by the number
of contracts to get position-level greeks.
"""

from __future__ import annotations

import math
from typing import Tuple

SQRT_2PI = math.sqrt(2.0 * math.pi)
DAYS_PER_YEAR = 365.0


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / SQRT_2PI


def _d1_d2(spot, strike, t, rate, sigma) -> Tuple[float, float]:
    vol_sqrt_t = sigma * math.sqrt(t)
    d1 = (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * t) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return d1, d2


def price(option_type: str, spot, strike, t, rate, sigma) -> float:
    """Black-Scholes theoretical option price (per share)."""
    option_type = option_type.lower()
    if t <= 0 or sigma <= 0 or spot <= 0:
        # Expired / degenerate: fall back to intrinsic value.
        if option_type == "call":
            return max(spot - strike, 0.0)
        return max(strike - spot, 0.0)
    d1, d2 = _d1_d2(spot, strike, t, rate, sigma)
    disc = math.exp(-rate * t)
    if option_type == "call":
        return spot * norm_cdf(d1) - strike * disc * norm_cdf(d2)
    return strike * disc * norm_cdf(-d2) - spot * norm_cdf(-d1)


def greeks(option_type: str, spot, strike, t, rate, sigma):
    """Return ``(delta, gamma, theta_per_day, vega_per_1pct)``.

    ``t`` is time to expiry in years. Degenerate inputs (expired, zero vol)
    return zeroed greeks with a step-function delta, which keeps callers from
    having to special-case expiry.
    """
    option_type = option_type.lower()
    if t <= 0 or sigma <= 0 or spot <= 0:
        if option_type == "call":
            delta = 1.0 if spot > strike else 0.0
        else:
            delta = -1.0 if spot < strike else 0.0
        return delta, 0.0, 0.0, 0.0

    d1, d2 = _d1_d2(spot, strike, t, rate, sigma)
    disc = math.exp(-rate * t)
    pdf_d1 = norm_pdf(d1)
    sqrt_t = math.sqrt(t)

    gamma = pdf_d1 / (spot * sigma * sqrt_t)
    vega_annual = spot * pdf_d1 * sqrt_t  # per 1.00 vol

    if option_type == "call":
        delta = norm_cdf(d1)
        theta_annual = (
            -(spot * pdf_d1 * sigma) / (2.0 * sqrt_t)
            - rate * strike * disc * norm_cdf(d2)
        )
    else:
        delta = norm_cdf(d1) - 1.0
        theta_annual = (
            -(spot * pdf_d1 * sigma) / (2.0 * sqrt_t)
            + rate * strike * disc * norm_cdf(-d2)
        )

    theta_per_day = theta_annual / DAYS_PER_YEAR
    vega_per_1pct = vega_annual / 100.0
    return delta, gamma, theta_per_day, vega_per_1pct


def implied_vol(
    option_type: str,
    market_price: float,
    spot,
    strike,
    t,
    rate,
    lo: float = 1e-4,
    hi: float = 5.0,
    tol: float = 1e-6,
    max_iter: int = 100,
):
    """Invert Black-Scholes for implied vol via bisection.

    Returns ``None`` when the price is outside the no-arbitrage band so an
    implied vol does not exist. Useful for later layers that want to back out
    IV from a marked price rather than trust a feed's IV field.
    """
    if t <= 0 or market_price <= 0:
        return None
    if price(option_type, spot, strike, t, rate, hi) < market_price:
        return None  # price too high even at the vol ceiling
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        diff = price(option_type, spot, strike, t, rate, mid) - market_price
        if abs(diff) < tol:
            return mid
        if diff > 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)
