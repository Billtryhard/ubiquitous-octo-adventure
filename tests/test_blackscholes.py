import math

from portfolio_monitor import blackscholes as bs


def test_norm_cdf_known_values():
    assert math.isclose(bs.norm_cdf(0.0), 0.5, abs_tol=1e-9)
    assert math.isclose(bs.norm_cdf(1.96), 0.975, abs_tol=1e-3)
    assert math.isclose(bs.norm_cdf(-1.96), 0.025, abs_tol=1e-3)


def test_call_put_parity():
    # C - P = S - K*e^{-rT}
    S, K, T, r, sig = 100.0, 95.0, 0.5, 0.045, 0.25
    c = bs.price("call", S, K, T, r, sig)
    p = bs.price("put", S, K, T, r, sig)
    assert math.isclose(c - p, S - K * math.exp(-r * T), abs_tol=1e-9)


def test_atm_call_delta_near_half():
    delta, gamma, theta, vega = bs.greeks("call", 100, 100, 1.0, 0.0, 0.2)
    assert 0.5 < delta < 0.62  # slight positive drift from d1
    assert gamma > 0
    assert vega > 0
    assert theta < 0  # long option bleeds time value


def test_put_delta_negative():
    delta, *_ = bs.greeks("put", 100, 100, 1.0, 0.045, 0.2)
    assert -1.0 < delta < 0.0


def test_expired_returns_intrinsic_and_zero_greeks():
    assert bs.price("call", 110, 100, 0.0, 0.045, 0.2) == 10.0
    assert bs.price("put", 90, 100, 0.0, 0.045, 0.2) == 10.0
    delta, gamma, theta, vega = bs.greeks("call", 110, 100, 0.0, 0.045, 0.2)
    assert (delta, gamma, theta, vega) == (1.0, 0.0, 0.0, 0.0)


def test_implied_vol_roundtrip():
    S, K, T, r, sig = 100.0, 105.0, 0.4, 0.045, 0.33
    px = bs.price("call", S, K, T, r, sig)
    iv = bs.implied_vol("call", px, S, K, T, r)
    assert iv is not None
    assert math.isclose(iv, sig, abs_tol=1e-3)
