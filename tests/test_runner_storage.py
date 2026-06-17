import os
from datetime import date

from portfolio_monitor import Storage, load_positions, run_monitor
from portfolio_monitor.providers import SyntheticProvider
from portfolio_monitor.snapshots import load_chain_snapshot, snapshot_path


def test_synthetic_provider_deterministic():
    prov = SyntheticProvider()
    a = prov.get_chain("AAPL", date(2026, 6, 17))
    b = prov.get_chain("AAPL", date(2026, 6, 17))
    assert a.spot == b.spot
    assert [q.mark for q in a.quotes] == [q.mark for q in b.quotes]


def test_synthetic_provider_moves_day_over_day():
    prov = SyntheticProvider()
    a = prov.get_chain("AAPL", date(2026, 6, 17))
    b = prov.get_chain("AAPL", date(2026, 6, 18))
    assert a.spot != b.spot  # gives later layers something to diff


def test_held_contract_always_in_chain():
    prov = SyntheticProvider()
    # An off-grid strike that won't appear on the standard grid.
    chain = prov.get_chain(
        "AAPL", date(2026, 6, 17),
        extra_contracts=[("call", 187.5, date(2026, 9, 18))],
    )
    assert chain.find("call", 187.5, date(2026, 9, 18)) is not None


def test_full_run_persists_and_snapshots(tmp_path):
    db = tmp_path / "p.db"
    snaps = tmp_path / "snaps"
    positions = load_positions("positions.json")
    asof = date(2026, 6, 17)

    result = run_monitor(
        positions, asof=asof, db_path=str(db), snapshots_dir=str(snaps), rate=0.045,
    )

    assert len(result.valuations) == len(positions)
    # every option has greeks and DTE
    for v in result.valuations:
        if v.asset_type == "option":
            assert v.greeks is not None
            assert v.dte is not None

    # JSON snapshot exists and mirrors SQLite
    aapl_path = snapshot_path(str(snaps), "AAPL", asof)
    assert os.path.exists(aapl_path)
    snap = load_chain_snapshot(aapl_path)
    assert snap["ticker"] == "AAPL"
    assert len(snap["quotes"]) > 0

    with Storage(str(db)) as st:
        rows = st.get_chain_rows("AAPL", asof.isoformat())
        assert len(rows) == len(snap["quotes"])
        vrows = st.conn.execute("SELECT COUNT(*) FROM valuations").fetchone()[0]
        assert vrows == len(positions)


def test_rerun_same_asof_is_idempotent(tmp_path):
    db = tmp_path / "p.db"
    snaps = tmp_path / "snaps"
    positions = load_positions("positions.json")
    asof = date(2026, 6, 17)
    run_monitor(positions, asof=asof, db_path=str(db), snapshots_dir=str(snaps))
    run_monitor(positions, asof=asof, db_path=str(db), snapshots_dir=str(snaps))
    with Storage(str(db)) as st:
        vrows = st.conn.execute("SELECT COUNT(*) FROM valuations").fetchone()[0]
        assert vrows == len(positions)  # no duplicate rows


def test_asof_stamps_storage(tmp_path):
    db = tmp_path / "p.db"
    snaps = tmp_path / "snaps"
    positions = load_positions("positions.json")
    run_monitor(positions, asof=date(2026, 6, 17), db_path=str(db), snapshots_dir=str(snaps))
    run_monitor(positions, asof=date(2026, 6, 18), db_path=str(db), snapshots_dir=str(snaps))
    with Storage(str(db)) as st:
        dates = st.list_snapshot_dates("AAPL")
        assert dates == ["2026-06-17", "2026-06-18"]
        # IV history accumulates across run dates for a held contract
        hist = st.iv_history("AAPL", "call", 190.0, "2026-09-18")
        assert len(hist) == 2
