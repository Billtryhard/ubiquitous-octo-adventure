"""Layer 2 — portfolio analytics built on top of Layer 1 valuations.

Computes, for a single run:

* **Allocation** — % of total value by ticker and by sector, with
  informational concentration flags (ticker cap, sector cap).
* **Aggregate greeks** — net delta in share-equivalent terms, total daily
  theta in dollars (what the book loses per day if nothing moves), and net
  vega in dollars per 1 IV point.
* **IV environment** (per option) — current IV plus IV rank / percentile from
  stored daily snapshots over a lookback, a "building history" label until
  enough history exists, rich / cheap flags, and a near-expiry flag.

Everything is informational — the layer surfaces facts, it does not advise.
Results are persisted to the same SQLite database under ``analytics_*`` tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from .models import Position, PositionValuation, SHARES_PER_CONTRACT
from .sectors import SectorLookup
from .storage import Storage


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class AnalyticsConfig:
    ticker_cap_pct: float = 40.0       # warn if a ticker exceeds this % of value
    sector_cap_pct: float = 60.0       # warn if a sector exceeds this % of value
    iv_lookback_days: int = 252        # IV rank/percentile window
    iv_min_history_days: int = 20      # below this -> "building history"
    iv_rich_threshold: float = 78.0    # IV rank above -> rich
    iv_cheap_threshold: float = 38.0   # IV rank below -> cheap
    dte_warn_threshold: int = 45       # DTE at/under -> surface time-decay/roll


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AllocationItem:
    key: str
    value: float
    pct: float
    flagged: bool = False


@dataclass
class Allocation:
    total_value: float
    by_ticker: List[AllocationItem] = field(default_factory=list)
    by_sector: List[AllocationItem] = field(default_factory=list)


@dataclass
class AggregateGreeks:
    net_delta_shares: float        # share-equivalent delta across the book
    net_gamma_shares: float        # share-equivalent gamma (per 1.00 move)
    total_theta_dollars: float     # $/day if nothing moves (long options < 0)
    net_vega_dollars: float        # $ per 1 IV point (1.00 vol-point)


@dataclass
class IVEnvironment:
    position_id: str
    ticker: str
    current_iv: Optional[float]
    iv_rank: Optional[float]
    iv_percentile: Optional[float]
    history_days: int
    status: str                    # "building history" | "ok"
    valuation: str                 # "rich" | "cheap" | "normal" | "n/a"
    dte: Optional[int]
    near_expiry: bool


@dataclass
class AnalyticsResult:
    asof: date
    config: AnalyticsConfig
    allocation: Allocation
    greeks: AggregateGreeks
    iv_environment: List[IVEnvironment] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------


def _allocation(
    valuations: List[PositionValuation],
    sectors: SectorLookup,
    config: AnalyticsConfig,
) -> Allocation:
    by_ticker: Dict[str, float] = {}
    by_sector: Dict[str, float] = {}
    for v in valuations:
        if v.current_value is None:
            continue
        by_ticker[v.ticker] = by_ticker.get(v.ticker, 0.0) + v.current_value
        sec = sectors.sector(v.ticker)
        by_sector[sec] = by_sector.get(sec, 0.0) + v.current_value

    total = sum(by_ticker.values())

    def items(d: Dict[str, float], cap: float) -> List[AllocationItem]:
        out = []
        for key, val in sorted(d.items(), key=lambda kv: kv[1], reverse=True):
            pct = (val / total * 100.0) if total else 0.0
            out.append(AllocationItem(key=key, value=val, pct=pct, flagged=pct > cap))
        return out

    return Allocation(
        total_value=total,
        by_ticker=items(by_ticker, config.ticker_cap_pct),
        by_sector=items(by_sector, config.sector_cap_pct),
    )


def _aggregate_greeks(
    positions_by_id: Dict[str, Position],
    valuations: List[PositionValuation],
) -> AggregateGreeks:
    net_delta = 0.0
    net_gamma = 0.0
    total_theta = 0.0
    net_vega = 0.0
    for v in valuations:
        pos = positions_by_id.get(v.position_id)
        if pos is None:
            continue
        if pos.is_shares:
            # Each share has delta 1, no gamma/theta/vega.
            net_delta += pos.contracts
            continue
        if v.greeks is None:
            continue
        scale = SHARES_PER_CONTRACT * pos.contracts
        net_delta += v.greeks.delta * scale
        net_gamma += v.greeks.gamma * scale
        total_theta += v.greeks.theta * scale   # theta already per-share per-day
        net_vega += v.greeks.vega * scale        # vega per 1 IV point per share
    return AggregateGreeks(
        net_delta_shares=net_delta,
        net_gamma_shares=net_gamma,
        total_theta_dollars=total_theta,
        net_vega_dollars=net_vega,
    )


def _iv_rank_percentile(history_ivs: List[float], current: float):
    """Return ``(iv_rank, iv_percentile)`` over the historical IV series.

    * IV rank      = (current - min) / (max - min) * 100
    * IV percentile= share of historical observations below the current IV
    """
    lo = min(history_ivs)
    hi = max(history_ivs)
    if hi > lo:
        iv_rank = (current - lo) / (hi - lo) * 100.0
    else:
        iv_rank = 0.0
    below = sum(1 for x in history_ivs if x < current)
    iv_percentile = below / len(history_ivs) * 100.0
    return iv_rank, iv_percentile


def _iv_environment(
    positions_by_id: Dict[str, Position],
    valuations: List[PositionValuation],
    storage: Storage,
    asof: date,
    config: AnalyticsConfig,
) -> List[IVEnvironment]:
    cutoff = asof - timedelta(days=config.iv_lookback_days)
    out: List[IVEnvironment] = []
    for v in valuations:
        pos = positions_by_id.get(v.position_id)
        if pos is None or not pos.is_option:
            continue

        rows = storage.iv_history(
            pos.ticker, pos.option_type, float(pos.strike), pos.expiry.isoformat()
        )
        ivs: List[float] = []
        for asof_date, iv, _mark in rows:
            if iv is None:
                continue
            d = datetime.strptime(asof_date, "%Y-%m-%d").date()
            if cutoff <= d <= asof:
                ivs.append(iv)

        history_days = len(ivs)
        current = v.iv
        dte = v.dte
        near_expiry = dte is not None and dte <= config.dte_warn_threshold

        if history_days < config.iv_min_history_days or current is None:
            out.append(
                IVEnvironment(
                    position_id=v.position_id,
                    ticker=pos.ticker,
                    current_iv=current,
                    iv_rank=None,
                    iv_percentile=None,
                    history_days=history_days,
                    status="building history",
                    valuation="n/a",
                    dte=dte,
                    near_expiry=near_expiry,
                )
            )
            continue

        iv_rank, iv_pctile = _iv_rank_percentile(ivs, current)
        if iv_rank > config.iv_rich_threshold:
            valuation = "rich"
        elif iv_rank < config.iv_cheap_threshold:
            valuation = "cheap"
        else:
            valuation = "normal"

        out.append(
            IVEnvironment(
                position_id=v.position_id,
                ticker=pos.ticker,
                current_iv=current,
                iv_rank=iv_rank,
                iv_percentile=iv_pctile,
                history_days=history_days,
                status="ok",
                valuation=valuation,
                dte=dte,
                near_expiry=near_expiry,
            )
        )
    return out


def compute_analytics(
    positions: List[Position],
    valuations: List[PositionValuation],
    storage: Storage,
    asof: date,
    config: Optional[AnalyticsConfig] = None,
    sectors: Optional[SectorLookup] = None,
) -> AnalyticsResult:
    config = config or AnalyticsConfig()
    sectors = sectors or SectorLookup()
    positions_by_id = {p.id: p for p in positions}

    return AnalyticsResult(
        asof=asof,
        config=config,
        allocation=_allocation(valuations, sectors, config),
        greeks=_aggregate_greeks(positions_by_id, valuations),
        iv_environment=_iv_environment(positions_by_id, valuations, storage, asof, config),
    )


# ---------------------------------------------------------------------------
# Persistence (Layer 2 owns its own tables on the shared connection)
# ---------------------------------------------------------------------------

ANALYTICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS analytics_allocation (
    asof_date  TEXT NOT NULL,
    dimension  TEXT NOT NULL,         -- 'ticker' | 'sector'
    key        TEXT NOT NULL,
    value      REAL NOT NULL,
    pct        REAL NOT NULL,
    flagged    INTEGER NOT NULL,
    PRIMARY KEY (asof_date, dimension, key)
);

CREATE TABLE IF NOT EXISTS analytics_greeks (
    asof_date           TEXT PRIMARY KEY,
    net_delta_shares    REAL NOT NULL,
    net_gamma_shares    REAL NOT NULL,
    total_theta_dollars REAL NOT NULL,
    net_vega_dollars    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics_iv (
    asof_date     TEXT NOT NULL,
    position_id   TEXT NOT NULL,
    ticker        TEXT NOT NULL,
    current_iv    REAL,
    iv_rank       REAL,
    iv_percentile REAL,
    history_days  INTEGER NOT NULL,
    status        TEXT NOT NULL,
    valuation     TEXT NOT NULL,
    dte           INTEGER,
    near_expiry   INTEGER NOT NULL,
    PRIMARY KEY (asof_date, position_id)
);
"""


def ensure_analytics_schema(storage: Storage) -> None:
    storage.conn.executescript(ANALYTICS_SCHEMA)
    storage.conn.commit()


def store_analytics(storage: Storage, result: AnalyticsResult) -> None:
    ensure_analytics_schema(storage)
    asof = result.asof.isoformat()
    conn = storage.conn
    with storage._tx():
        for dim, items in (("ticker", result.allocation.by_ticker),
                           ("sector", result.allocation.by_sector)):
            for it in items:
                conn.execute(
                    """INSERT OR REPLACE INTO analytics_allocation
                       (asof_date, dimension, key, value, pct, flagged)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (asof, dim, it.key, it.value, it.pct, int(it.flagged)),
                )
        g = result.greeks
        conn.execute(
            """INSERT OR REPLACE INTO analytics_greeks
               (asof_date, net_delta_shares, net_gamma_shares,
                total_theta_dollars, net_vega_dollars)
               VALUES (?, ?, ?, ?, ?)""",
            (asof, g.net_delta_shares, g.net_gamma_shares,
             g.total_theta_dollars, g.net_vega_dollars),
        )
        for iv in result.iv_environment:
            conn.execute(
                """INSERT OR REPLACE INTO analytics_iv
                   (asof_date, position_id, ticker, current_iv, iv_rank,
                    iv_percentile, history_days, status, valuation, dte, near_expiry)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (asof, iv.position_id, iv.ticker, iv.current_iv, iv.iv_rank,
                 iv.iv_percentile, iv.history_days, iv.status, iv.valuation,
                 iv.dte, int(iv.near_expiry)),
            )
