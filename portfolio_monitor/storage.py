"""SQLite persistence for the data & valuation layer.

Everything lands in a single SQLite database (default ``portfolio.db``):

* ``positions``           - the book as loaded for a run.
* ``underlying_snapshots``- spot per underlying per run date.
* ``chain_snapshots``     - the full pulled option chain per underlying per run
                            date (mirror of the dated JSON files). This is what
                            later layers diff for new-strike / new-expiry
                            detection and to build IV history.
* ``valuations``          - per-position valuation results per run date.

All writes are keyed on ``asof_date`` and use INSERT OR REPLACE so re-running a
given ``--asof`` is idempotent.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterable, List, Optional

from .models import Chain, Position, PositionValuation

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id          TEXT PRIMARY KEY,
    asset_type  TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    option_type TEXT,
    strike      REAL,
    expiry      TEXT,
    entry_price REAL NOT NULL,
    contracts   REAL NOT NULL,
    entry_date  TEXT,
    target_price REAL,
    stop_price  REAL
);

CREATE TABLE IF NOT EXISTS underlying_snapshots (
    ticker     TEXT NOT NULL,
    asof_date  TEXT NOT NULL,
    spot       REAL NOT NULL,
    pulled_at  TEXT NOT NULL,
    PRIMARY KEY (ticker, asof_date)
);

CREATE TABLE IF NOT EXISTS chain_snapshots (
    ticker        TEXT NOT NULL,
    asof_date     TEXT NOT NULL,
    option_type   TEXT NOT NULL,
    strike        REAL NOT NULL,
    expiry        TEXT NOT NULL,
    bid           REAL,
    ask           REAL,
    last          REAL,
    mark          REAL,
    iv            REAL,
    volume        INTEGER,
    open_interest INTEGER,
    pulled_at     TEXT NOT NULL,
    PRIMARY KEY (ticker, asof_date, option_type, strike, expiry)
);

CREATE TABLE IF NOT EXISTS valuations (
    asof_date          TEXT NOT NULL,
    position_id        TEXT NOT NULL,
    asset_type         TEXT NOT NULL,
    ticker             TEXT NOT NULL,
    mark               REAL,
    current_value      REAL,
    cost_basis         REAL,
    unrealized_pl      REAL,
    unrealized_pl_pct  REAL,
    dte                INTEGER,
    iv                 REAL,
    delta              REAL,
    gamma              REAL,
    theta              REAL,
    vega               REAL,
    progress_to_target REAL,
    progress_to_stop   REAL,
    pulled_at          TEXT NOT NULL,
    PRIMARY KEY (asof_date, position_id)
);

CREATE INDEX IF NOT EXISTS idx_chain_ticker_date ON chain_snapshots (ticker, asof_date);
CREATE INDEX IF NOT EXISTS idx_chain_iv_history ON chain_snapshots (ticker, option_type, strike, expiry);
"""


class Storage:
    """Thin wrapper around a SQLite connection with the layer's schema."""

    def __init__(self, path: str = "portfolio.db"):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @contextmanager
    def _tx(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # -- positions ----------------------------------------------------------

    def save_positions(self, positions: Iterable[Position]):
        with self._tx() as c:
            for p in positions:
                r = p.to_record()
                c.execute(
                    """INSERT OR REPLACE INTO positions
                       (id, asset_type, ticker, option_type, strike, expiry,
                        entry_price, contracts, entry_date, target_price, stop_price)
                       VALUES (:id, :asset_type, :ticker, :option_type, :strike, :expiry,
                               :entry_price, :contracts, :entry_date, :target_price, :stop_price)""",
                    r,
                )

    # -- snapshots ----------------------------------------------------------

    def save_chain(self, chain: Chain):
        """Mirror a full pulled chain (+ spot) into SQLite."""
        asof = chain.asof.isoformat()
        pulled_at = chain.pulled_at.isoformat(timespec="seconds")
        with self._tx() as c:
            c.execute(
                """INSERT OR REPLACE INTO underlying_snapshots
                   (ticker, asof_date, spot, pulled_at) VALUES (?, ?, ?, ?)""",
                (chain.ticker, asof, chain.spot, pulled_at),
            )
            for q in chain.quotes:
                c.execute(
                    """INSERT OR REPLACE INTO chain_snapshots
                       (ticker, asof_date, option_type, strike, expiry,
                        bid, ask, last, mark, iv, volume, open_interest, pulled_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        q.ticker, asof, q.option_type, q.strike, q.expiry.isoformat(),
                        q.bid, q.ask, q.last, q.mark, q.iv, q.volume, q.open_interest,
                        pulled_at,
                    ),
                )

    # -- valuations ---------------------------------------------------------

    def save_valuations(self, valuations: Iterable[PositionValuation]):
        pulled_at = datetime.now().isoformat(timespec="seconds")
        with self._tx() as c:
            for v in valuations:
                r = v.to_record()
                r["pulled_at"] = pulled_at
                c.execute(
                    """INSERT OR REPLACE INTO valuations
                       (asof_date, position_id, asset_type, ticker, mark, current_value,
                        cost_basis, unrealized_pl, unrealized_pl_pct, dte, iv,
                        delta, gamma, theta, vega, progress_to_target, progress_to_stop,
                        pulled_at)
                       VALUES (:asof, :position_id, :asset_type, :ticker, :mark, :current_value,
                               :cost_basis, :unrealized_pl, :unrealized_pl_pct, :dte, :iv,
                               :delta, :gamma, :theta, :vega, :progress_to_target,
                               :progress_to_stop, :pulled_at)""",
                    r,
                )

    # -- read helpers (handy for later layers / diffing) --------------------

    def get_chain_rows(self, ticker: str, asof_date: str) -> List[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM chain_snapshots WHERE ticker = ? AND asof_date = ?"
            " ORDER BY expiry, option_type, strike",
            (ticker, asof_date),
        )
        return cur.fetchall()

    def list_snapshot_dates(self, ticker: str) -> List[str]:
        cur = self.conn.execute(
            "SELECT DISTINCT asof_date FROM chain_snapshots WHERE ticker = ? ORDER BY asof_date",
            (ticker,),
        )
        return [r[0] for r in cur.fetchall()]

    def iv_history(self, ticker: str, option_type: str, strike: float, expiry: str):
        """IV time series for one contract across all stored run dates."""
        cur = self.conn.execute(
            """SELECT asof_date, iv, mark FROM chain_snapshots
               WHERE ticker = ? AND option_type = ? AND strike = ? AND expiry = ?
               ORDER BY asof_date""",
            (ticker, option_type, strike, expiry),
        )
        return cur.fetchall()
