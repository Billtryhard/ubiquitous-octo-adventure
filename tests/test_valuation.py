from datetime import date

from portfolio_monitor.models import OptionQuote, Position
from portfolio_monitor.valuation import (
    progress_pct,
    value_option_position,
    value_share_position,
)


def test_progress_pct_directions():
    # entry 10, target 20: at 15 we're halfway -> 50%
    assert progress_pct(10, 15, 20) == 50.0
    # entry 10, stop 5: at 7.5 we're halfway to stop -> 50%
    assert progress_pct(10, 7.5, 5) == 50.0
    # moved the wrong way reads negative
    assert progress_pct(10, 8, 20) < 0
    assert progress_pct(10, 10, None) is None


def test_share_valuation():
    p = Position(asset_type="shares", ticker="AAPL", entry_price=100.0, contracts=10,
                 target_price=120.0, stop_price=90.0)
    v = value_share_position(p, spot=110.0, asof=date(2026, 6, 17))
    assert v.cost_basis == 1000.0
    assert v.current_value == 1100.0
    assert v.unrealized_pl == 100.0
    assert v.unrealized_pl_pct == 10.0
    assert v.progress_to_target == 50.0  # halfway from 100 to 120
    assert v.dte is None


def test_option_valuation_uses_100x_multiplier():
    p = Position(
        asset_type="option", ticker="AAPL", option_type="call", strike=190,
        expiry=date(2026, 9, 18), entry_price=8.50, contracts=5,
        target_price=17.0, stop_price=4.25,
    )
    quote = OptionQuote(
        ticker="AAPL", option_type="call", strike=190, expiry=date(2026, 9, 18),
        bid=10.0, ask=11.0, last=10.4, iv=0.30, volume=100, open_interest=500,
    )
    v = value_option_position(p, quote, spot=195.0, asof=date(2026, 6, 17), rate=0.045)
    # mark = mid = 10.5; per-share
    assert v.mark == 10.5
    # cost = 8.50 * 100 * 5 = 4250 ; value = 10.5 * 100 * 5 = 5250
    assert v.cost_basis == 4250.0
    assert v.current_value == 5250.0
    assert v.unrealized_pl == 1000.0
    assert v.dte == (date(2026, 9, 18) - date(2026, 6, 17)).days
    assert v.greeks is not None
    assert 0 < v.greeks.delta < 1  # long call
    assert v.iv == 0.30


def test_mark_falls_back_to_last_without_both_quotes():
    p = Position(asset_type="option", ticker="X", option_type="put", strike=10,
                 expiry=date(2026, 9, 18), entry_price=1.0, contracts=1)
    quote = OptionQuote(ticker="X", option_type="put", strike=10,
                        expiry=date(2026, 9, 18), bid=None, ask=None, last=2.0, iv=0.5)
    v = value_option_position(p, quote, spot=9.0, asof=date(2026, 6, 17))
    assert v.mark == 2.0
