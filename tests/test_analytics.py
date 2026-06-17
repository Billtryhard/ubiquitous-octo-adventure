from datetime import date, timedelta

from portfolio_monitor import Storage, load_positions, run_monitor
from portfolio_monitor.analytics import (
    AnalyticsConfig,
    compute_analytics,
    store_analytics,
)
from portfolio_monitor.models import Greeks, Position, PositionValuation
from portfolio_monitor.sectors import SectorLookup


def _share_val(pid, ticker, value, contracts):
    p = Position(asset_type="shares", ticker=ticker, entry_price=value / contracts,
                 contracts=contracts, id=pid)
    v = PositionValuation(
        position_id=pid, asof=date(2026, 6, 17), asset_type="shares", ticker=ticker,
        mark=value / contracts, current_value=value, cost_basis=value,
        unrealized_pl=0.0, unrealized_pl_pct=0.0,
    )
    return p, v


def test_sector_lookup_config_and_default():
    s = SectorLookup(config_path=None, use_yfinance_fallback=False)
    assert s.sector("AAPL") == "Technology"
    assert s.sector("ZZZZ") == "Unknown"
    s2 = SectorLookup(config_path=None, mapping={"ZZZZ": "Custom"}, use_yfinance_fallback=False)
    assert s2.sector("zzzz") == "Custom"


def test_allocation_and_concentration_flags(tmp_path):
    # AAPL 70 (Tech), MSFT 20 (Tech), XOM 10 (Energy) -> total 100
    p1, v1 = _share_val("a", "AAPL", 70.0, 70)
    p2, v2 = _share_val("b", "MSFT", 20.0, 20)
    p3, v3 = _share_val("c", "XOM", 10.0, 10)
    storage = Storage(str(tmp_path / "p.db"))
    sectors = SectorLookup(config_path=None, use_yfinance_fallback=False)
    res = compute_analytics([p1, p2, p3], [v1, v2, v3], storage, date(2026, 6, 17),
                            AnalyticsConfig(), sectors)
    storage.close()

    assert res.allocation.total_value == 100.0
    aapl = next(i for i in res.allocation.by_ticker if i.key == "AAPL")
    assert aapl.pct == 70.0
    assert aapl.flagged  # > 40% ticker cap
    tech = next(i for i in res.allocation.by_sector if i.key == "Technology")
    assert tech.pct == 90.0
    assert tech.flagged  # > 60% sector cap
    energy = next(i for i in res.allocation.by_sector if i.key == "Energy")
    assert not energy.flagged


def test_aggregate_greeks_share_equivalent():
    # Long 2 AAPL calls, delta 0.5/sh -> 0.5*100*2 = 100 share-equiv delta
    opt = Position(asset_type="option", ticker="AAPL", option_type="call", strike=190,
                   expiry=date(2026, 9, 18), entry_price=8.5, contracts=2, id="o")
    ov = PositionValuation(
        position_id="o", asof=date(2026, 6, 17), asset_type="option", ticker="AAPL",
        mark=10.0, current_value=2000.0, cost_basis=1700.0, unrealized_pl=300.0,
        unrealized_pl_pct=17.6, dte=93, iv=0.30,
        greeks=Greeks(delta=0.5, gamma=0.01, theta=-0.10, vega=0.375),
    )
    # 50 shares of AAPL contribute 50 delta
    sp = Position(asset_type="shares", ticker="AAPL", entry_price=100, contracts=50, id="s")
    sv = PositionValuation(
        position_id="s", asof=date(2026, 6, 17), asset_type="shares", ticker="AAPL",
        mark=190.0, current_value=9500.0, cost_basis=5000.0, unrealized_pl=4500.0,
        unrealized_pl_pct=90.0,
    )
    storage_stub = None
    from portfolio_monitor.analytics import _aggregate_greeks
    g = _aggregate_greeks({"o": opt, "s": sp}, [ov, sv])
    assert g.net_delta_shares == 0.5 * 100 * 2 + 50  # 150
    assert g.total_theta_dollars == -0.10 * 100 * 2  # -20 $/day
    assert g.net_vega_dollars == 0.375 * 100 * 2     # 75 $ per IV point


def test_iv_building_history_then_rank(tmp_path):
    """With one stored run -> building history; after enough runs -> ranked."""
    db = tmp_path / "p.db"
    snaps = tmp_path / "snaps"
    positions = load_positions("positions.json")
    sectors = SectorLookup(config_path=None, use_yfinance_fallback=False)
    cfg = AnalyticsConfig(iv_min_history_days=5)

    # First run: only 1 day of history
    asof0 = date(2026, 6, 1)
    storage = Storage(str(db))
    r = run_monitor(positions, asof=asof0, storage=storage, snapshots_dir=str(snaps))
    a = compute_analytics(positions, r.valuations, storage, asof0, cfg, sectors)
    opt_iv = [iv for iv in a.iv_environment]
    assert opt_iv and all(iv.status == "building history" for iv in opt_iv)
    storage.close()

    # Accumulate several more daily runs
    for i in range(1, 7):
        asof = asof0 + timedelta(days=i)
        storage = Storage(str(db))
        r = run_monitor(positions, asof=asof, storage=storage, snapshots_dir=str(snaps))
        a = compute_analytics(positions, r.valuations, storage, asof, cfg, sectors)
        storage.close()

    # Now we have 7 days >= min history 5 -> ranked
    assert a.iv_environment
    for iv in a.iv_environment:
        assert iv.status == "ok"
        assert iv.iv_rank is not None
        assert 0.0 <= iv.iv_rank <= 100.0
        assert iv.valuation in ("rich", "cheap", "normal")


def test_near_expiry_flag():
    p = Position(asset_type="option", ticker="X", option_type="call", strike=10,
                 expiry=date(2026, 6, 27), entry_price=1.0, contracts=1, id="x")
    v = PositionValuation(
        position_id="x", asof=date(2026, 6, 17), asset_type="option", ticker="X",
        mark=1.0, current_value=100.0, cost_basis=100.0, unrealized_pl=0.0,
        unrealized_pl_pct=0.0, dte=10, iv=0.4,
        greeks=Greeks(delta=0.5, gamma=0.01, theta=-0.05, vega=0.1),
    )

    class _StubStorage:
        def iv_history(self, *a):
            return []

    from portfolio_monitor.analytics import _iv_environment
    out = _iv_environment({"x": p}, [v], _StubStorage(), date(2026, 6, 17),
                          AnalyticsConfig(dte_warn_threshold=45))
    assert out[0].near_expiry is True


def test_store_analytics_persists(tmp_path):
    db = tmp_path / "p.db"
    snaps = tmp_path / "snaps"
    positions = load_positions("positions.json")
    asof = date(2026, 6, 17)
    storage = Storage(str(db))
    r = run_monitor(positions, asof=asof, storage=storage, snapshots_dir=str(snaps))
    a = compute_analytics(positions, r.valuations, storage, asof,
                          sectors=SectorLookup(config_path=None, use_yfinance_fallback=False))
    store_analytics(storage, a)

    alloc = storage.conn.execute(
        "SELECT COUNT(*) FROM analytics_allocation WHERE asof_date = ?", (asof.isoformat(),)
    ).fetchone()[0]
    assert alloc > 0
    greeks = storage.conn.execute(
        "SELECT net_delta_shares FROM analytics_greeks WHERE asof_date = ?", (asof.isoformat(),)
    ).fetchone()
    assert greeks is not None
    ivc = storage.conn.execute(
        "SELECT COUNT(*) FROM analytics_iv WHERE asof_date = ?", (asof.isoformat(),)
    ).fetchone()[0]
    assert ivc == sum(1 for p in positions if p.is_option)
    storage.close()
