"""WebullProvider tests against a fake client (the real package/network is
never required). Verifies the response mapping into Chain/OptionQuote, the
mark logic, and end-to-end valuation through run_monitor."""

from datetime import date

from portfolio_monitor.models import OPTION, SHARES, Position
from portfolio_monitor.positions import load_positions
from portfolio_monitor.runner import run_monitor
from portfolio_monitor.webull_feed import (
    WebullProvider,
    parse_occ_symbol,
    position_from_webull,
    positions_to_json,
)


class FakeWebull:
    """Mimics the unofficial ``webull`` package surface we use."""

    def get_quote(self, stock=None, tId=None):
        return {"close": "191.25", "bid": "191.10", "ask": "191.40"}

    def get_options_expiration_dates(self, stock=None, count=-1):
        return [{"date": "2026-09-18", "days": 93}, {"date": "2026-12-18", "days": 184}]

    def get_positions(self):
        return [
            # stock lot
            {
                "ticker": {"symbol": "AAPL", "type": 2},
                "position": "200",
                "costPrice": "175.40",
            },
            # option lot with explicit fields
            {
                "assetType": "option",
                "ticker": {"symbol": "AAPL  260918C00190000", "unSymbol": "AAPL"},
                "optionType": "call",
                "strikePrice": "190",
                "optionExpireDate": "2026-09-18",
                "position": "5",
                "costPrice": "8.50",
            },
            # option lot relying on OCC-symbol parsing + total cost
            {
                "ticker": {"symbol": "TSLA  261218P00250000"},
                "position": "2",
                "cost": "1700",   # total dollars -> 1700 / (2 * 100) = 8.50/share
            },
            # closed line -> skipped
            {"ticker": {"symbol": "NVDA"}, "position": "0", "costPrice": "100"},
        ]

    def get_options(self, stock=None, expireDate=None, **kwargs):
        # Two strikes per expiry, each with call+put legs.
        return [
            {
                "strikePrice": "190",
                "call": {
                    "bid": "10.00", "ask": "11.00", "close": "10.40",
                    "impVol": "0.31", "volume": "1200", "openInterest": "5400",
                },
                "put": {
                    "bidList": [{"price": "8.20"}], "askList": [{"price": "8.80"}],
                    "close": "8.50", "impVol": "0.34", "volume": "900", "openInterest": "4100",
                },
            },
            {
                "strikePrice": "200",
                "call": {
                    # no bid/ask -> mark falls back to last (close)
                    "close": "5.10", "impVol": "0.29", "volume": "300", "openInterest": "2200",
                },
                "put": {
                    "bid": "15.00", "ask": "16.00", "close": "15.40",
                    "impVol": "0.36", "volume": "150", "openInterest": "1800",
                },
            },
        ]


def test_get_spot_prefers_last_trade():
    prov = WebullProvider(FakeWebull())
    assert prov.get_spot("AAPL", date(2026, 6, 17)) == 191.25


def test_chain_mapping_and_mark_logic():
    prov = WebullProvider(FakeWebull())
    chain = prov.get_chain("AAPL", date(2026, 6, 17))
    assert chain.ticker == "AAPL"
    assert chain.spot == 191.25
    # 2 expiries x 2 strikes x 2 directions = 8 quotes
    assert len(chain.quotes) == 8

    call190 = chain.find("call", 190.0, date(2026, 9, 18))
    assert call190 is not None
    assert call190.mark == 10.5          # mid of 10.00/11.00
    assert call190.iv == 0.31
    assert call190.volume == 1200
    assert call190.open_interest == 5400

    # bidList/askList form is parsed too
    put190 = chain.find("put", 190.0, date(2026, 9, 18))
    assert put190.mark == 8.5            # mid of 8.20/8.80

    # missing both bid and ask -> mark falls back to last
    call200 = chain.find("call", 200.0, date(2026, 9, 18))
    assert call200.bid is None and call200.ask is None
    assert call200.mark == 5.10


def test_max_expiries_caps_calls():
    prov = WebullProvider(FakeWebull(), max_expiries=1)
    chain = prov.get_chain("AAPL", date(2026, 6, 17))
    assert {q.expiry for q in chain.quotes} == {date(2026, 9, 18)}


def test_parse_occ_symbol():
    assert parse_occ_symbol("AAPL  260918C00190000") == ("AAPL", "call", 190.0, date(2026, 9, 18))
    assert parse_occ_symbol("TSLA261218P00250000") == ("TSLA", "put", 250.0, date(2026, 12, 18))
    assert parse_occ_symbol("AAPL") is None      # plain equity
    assert parse_occ_symbol("") is None


def test_position_from_webull_variants():
    # stock
    stock = position_from_webull({"ticker": {"symbol": "AAPL"}, "position": "200", "costPrice": "175.40"})
    assert stock.asset_type == SHARES and stock.ticker == "AAPL"
    assert stock.contracts == 200 and stock.entry_price == 175.40

    # option via OCC symbol + total cost (no explicit fields)
    opt = position_from_webull({"ticker": {"symbol": "TSLA  261218P00250000"}, "position": "2", "cost": "1700"})
    assert opt.asset_type == OPTION and opt.ticker == "TSLA"
    assert opt.option_type == "put" and opt.strike == 250.0
    assert opt.expiry == date(2026, 12, 18)
    assert opt.entry_price == 8.50           # 1700 / (2 * 100)
    assert opt.id == "TSLA_2026-12-18_250P"

    # zero-quantity line is dropped
    assert position_from_webull({"ticker": {"symbol": "NVDA"}, "position": "0"}) is None


def test_fetch_positions_and_roundtrip(tmp_path):
    prov = WebullProvider(FakeWebull())
    positions = prov.fetch_positions()
    ids = {p.id for p in positions}
    assert ids == {"AAPL_shares", "AAPL_2026-09-18_190C", "TSLA_2026-12-18_250P"}

    # The serialized file reloads through the normal loader unchanged.
    path = tmp_path / "positions.json"
    path.write_text(positions_to_json(positions))
    reloaded = load_positions(str(path))
    assert {p.id for p in reloaded} == ids
    aapl_opt = next(p for p in reloaded if p.id == "AAPL_2026-09-18_190C")
    assert aapl_opt.option_type == "call" and aapl_opt.strike == 190.0
    assert aapl_opt.contracts == 5 and aapl_opt.entry_price == 8.50


def test_end_to_end_valuation_through_webull(tmp_path):
    positions = [
        Position(asset_type="option", ticker="AAPL", option_type="call", strike=190,
                 expiry=date(2026, 9, 18), entry_price=8.50, contracts=5),
        Position(asset_type="shares", ticker="AAPL", entry_price=175.40, contracts=200),
    ]
    result = run_monitor(
        positions, asof=date(2026, 6, 17),
        provider=WebullProvider(FakeWebull()),
        db_path=str(tmp_path / "p.db"), snapshots_dir=str(tmp_path / "s"),
    )
    by_id = {v.position_id: v for v in result.valuations}
    opt = by_id["AAPL_2026-09-18_190C"]
    assert opt.mark == 10.5
    assert opt.current_value == 10.5 * 100 * 5
    assert opt.greeks is not None          # computed from the live IV (0.31)
    assert by_id["AAPL_shares"].mark == 191.25
