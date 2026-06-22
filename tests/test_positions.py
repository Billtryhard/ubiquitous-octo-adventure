from datetime import date

import pytest

from portfolio_monitor import load_positions, parse_position
from portfolio_monitor.models import Position


def test_auto_id_for_option():
    p = parse_position(
        {
            "asset_type": "option",
            "ticker": "aapl",
            "option_type": "call",
            "strike": 190,
            "expiry": "2026-09-18",
            "entry_price": 8.5,
            "contracts": 5,
        }
    )
    assert p.id == "AAPL_2026-09-18_190C"
    assert p.ticker == "AAPL"
    assert p.is_option


def test_auto_id_for_shares():
    p = parse_position(
        {"asset_type": "shares", "ticker": "AAPL", "entry_price": 100, "contracts": 50}
    )
    assert p.id == "AAPL_shares"
    assert p.is_shares
    assert p.multiplier == 1


def test_option_multiplier_is_100():
    p = parse_position(
        {
            "asset_type": "option",
            "ticker": "X",
            "option_type": "put",
            "strike": 10,
            "expiry": "2026-09-18",
            "entry_price": 1.0,
            "contracts": 1,
        }
    )
    assert p.multiplier == 100


def test_bad_option_type_rejected():
    with pytest.raises(ValueError):
        parse_position(
            {
                "asset_type": "option",
                "ticker": "X",
                "option_type": "straddle",
                "strike": 10,
                "expiry": "2026-09-18",
                "entry_price": 1.0,
                "contracts": 1,
            }
        )


def test_missing_required_field_rejected():
    with pytest.raises(ValueError):
        parse_position({"asset_type": "shares", "ticker": "X", "contracts": 10})


def test_days_to_expiry():
    p = parse_position(
        {
            "asset_type": "option",
            "ticker": "X",
            "option_type": "call",
            "strike": 10,
            "expiry": "2026-06-27",
            "entry_price": 1.0,
            "contracts": 1,
        }
    )
    assert p.days_to_expiry(date(2026, 6, 17)) == 10


def test_load_example_positions():
    positions = load_positions("positions.json")
    assert len(positions) == 3
    assert {p.asset_type for p in positions} == {"option", "shares"}
