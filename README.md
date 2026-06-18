# Portfolio Monitor

An options + equity portfolio monitor.

* **Layer 1 — Data & Valuation**: loads a mixed book of option and share
  positions, pulls marks, computes Black-Scholes greeks locally, snapshots the
  full option chain per underlying (JSON + SQLite) for later diffing, and
  reports per-position valuation.
* **Layer 2 — Analytics**: allocation & concentration, aggregate
  portfolio-level greeks, and per-option IV environment (IV rank/percentile,
  rich/cheap, near-expiry) built on the stored snapshots.
* **Layer 3 — Market context**: a deterministic 0-100 macro gate and a daily
  Claude news analysis per held name (summary, sentiment, drivers, position
  flags — informational, never a trade signal).

Pure Python standard library — **no third-party runtime dependencies**
(`pytest` is used only for tests).

## Quick start

```bash
# Value the example book as of a given date
python3 -m portfolio_monitor --asof 2026-06-17

# Custom book / database / snapshot dir / risk-free rate
python3 -m portfolio_monitor \
    --positions positions.json \
    --db portfolio.db \
    --snapshots-dir snapshots \
    --asof 2026-06-17 \
    --rate 0.045
```

`--asof YYYY-MM-DD` stamps the run date used for **storage and diffing**.
Marks always come from the current feed — there is no historical chain
reconstruction. Re-running the same `--asof` is idempotent (INSERT OR REPLACE).

## Positions input (`positions.json`)

One book holds two row types. The file may be a bare JSON array or an object
with a `"positions"` key.

### Option rows
| field | notes |
|-------|-------|
| `id` | optional — auto-generated as `TICKER_YYYY-MM-DD_<strike><C\|P>` |
| `asset_type` | `"option"` |
| `ticker` | underlying symbol |
| `option_type` | `"call"` or `"put"` |
| `strike` | strike price |
| `expiry` | `YYYY-MM-DD` |
| `entry_price` | **per-share** premium |
| `contracts` | number of contracts |
| `entry_date` | `YYYY-MM-DD` |
| `target_price` | optional, **per share** |
| `stop_price` | optional, **per share** |

### Share rows
| field | notes |
|-------|-------|
| `id` | e.g. `AAPL_shares` (auto-generated if omitted) |
| `asset_type` | `"shares"` |
| `ticker` | symbol |
| `entry_price` | per share |
| `contracts` | number of **shares** |
| `entry_date`, `target_price`, `stop_price` | as above |

> **Important:** for options, `entry_price` / `target_price` / `stop_price` are
> **per share**. Each contract controls 100 shares, so the per-contract dollar
> value is `price × 100`. The valuation layer applies that 100× multiplier.

## What a run produces

**Market data pull** (per option contract): `bid`, `ask`, `last`, `iv`,
`volume`, `open_interest`. `mark = (bid + ask) / 2` when both exist, else
`last`. For shares, `mark` = current spot.

**Greeks** — Black-Scholes computed locally (`math.erf`, no external lib) from
each contract's IV, a configurable annual risk-free rate (default `0.045`), and
actual days to expiry. Conventions: `delta`/`gamma` per 1.00 underlying move,
`theta` per calendar day, `vega` per 1 percentage-point of IV (all per share).

**Snapshots** — every run writes the **full pulled chain** per underlying to
`snapshots/TICKER_YYYY-MM-DD.json` and mirrors it into SQLite
(`chain_snapshots`). This is what later layers diff for new-strike /
new-expiry detection and to build IV history.

**Valuation** — per position: `mark`, current value, unrealized P&L (`$` and
`%`), DTE (options), and progress to target / progress to stop as percentages
(`0%` = at entry, `100%` = level reached; reads negative if it moved the wrong
way, can exceed 100% on overshoot).

Everything is stored in a single SQLite database: `positions`,
`underlying_snapshots`, `chain_snapshots`, `valuations`.

## Layer 2 — Analytics

Runs automatically after valuation (disable with `--no-analytics`) and is
persisted to the same SQLite database (`analytics_allocation`,
`analytics_greeks`, `analytics_iv`). Everything is **informational** — it
surfaces facts, it does not advise.

**Allocation & concentration** — percent of total value by ticker and by
sector. Sectors resolve via `sectors.json` (config), then an optional yfinance
fallback, then `Unknown`. Flags any ticker over `--ticker-cap` (default 40%) or
sector over `--sector-cap` (default 60%).

**Aggregate greeks** (portfolio-level exposures):
* **Net delta** in share-equivalent terms (options: `delta × 100 × contracts`;
  shares contribute 1 each).
* **Total daily theta** in dollars — what the book loses per day if nothing
  moves.
* **Net vega** in dollars per 1 IV point.

**IV environment** (per option) — current IV plus an **IV rank** and **IV
percentile** computed from stored daily snapshots over `--iv-lookback` (default
252 days). Until `--iv-min-history` days exist (default 20) it shows
*building history*. Flags **rich** (IV rank > `--iv-rich`, default 78) or
**cheap** (< `--iv-cheap`, default 38), and marks contracts within
`--dte-warn` days of expiry (default 45) so upcoming time-decay / roll
decisions are visible.

```bash
python3 -m portfolio_monitor --asof 2026-06-17 \
    --sectors sectors.json --ticker-cap 40 --sector-cap 60 \
    --iv-lookback 252 --iv-min-history 20 --iv-rich 78 --iv-cheap 38 --dte-warn 45
```

```python
from portfolio_monitor import compute_analytics, store_analytics, Storage, SectorLookup, run_monitor

with Storage("portfolio.db") as st:
    result = run_monitor(positions, asof, storage=st)
    analytics = compute_analytics(positions, result.valuations, st, asof, sectors=SectorLookup())
    store_analytics(st, analytics)
```

> IV rank needs history. Run the monitor once per trading day (advancing
> `--asof`) to accumulate the snapshots that IV rank/percentile are computed
> from.

## Layer 3 — Market context

Runs after analytics. Two independent parts; both persist to the same SQLite
database (`macro_score`, `news_analysis`). Everything is **context, not a
trade signal**.

### Macro gate (deterministic, 0-100)

A pure, reproducible read on the environment the book sits in — same inputs in,
same score out. Higher = calmer / more risk-supportive. Five sub-scores
(each 0-100) blended with configurable weights that must sum to 1.0:

| Sub-score | Driver | Higher score when… |
|-----------|--------|--------------------|
| `vix_level` | VIX | VIX is low |
| `vix_percentile` | VIX vs its trailing 1-year range | VIX is low in its own range |
| `term_structure` | VIX vs VIX3M | contango (VIX3M > VIX) |
| `breadth` | % of SPY constituents above their 200-day MA (proxy) | breadth healthy |
| `credit` | HYG vs TLT (1-year percentile) | credit risk-on / spreads tight |

Inputs come from a `MacroProvider`; the default `SyntheticMacroProvider`
derives a full 1-year history deterministically from the run date (so the
percentile sub-scores are meaningful and the gate is reproducible offline). A
live provider would pull `^VIX` / `^VIX3M` / `HYG` / `TLT` and a breadth series.

```bash
python3 -m portfolio_monitor --asof 2026-06-17 \
    --macro-weights 0.25,0.25,0.2,0.15,0.15   # vix_level,vix_percentile,term_structure,breadth,credit
```

### News analysis (Claude via API, per held name)

For each underlying, recent headlines (default 3-day window) are sent to Claude
(`claude-opus-4-8`, via the official `anthropic` SDK, structured output). Per
name it returns: a short factual **summary** of what happened, a **sentiment**
read (positive / neutral / negative), the **key drivers**, and a **position
flag** for anything that specifically affects a held position (e.g. earnings
dated before an option's expiry). **Claude summarizes and flags — it does not
say buy, sell, hold, or roll.**

* **Caching** — each name's analysis is cached per day (`news_analysis` table),
  so re-running a day never re-bills the API. This is the only paid part of the
  system; per-call cost is small and surfaced as an estimate.
* **Graceful degradation** — if the `anthropic` SDK isn't installed or
  `ANTHROPIC_API_KEY` is unset, names are returned with status `skipped` (with a
  reason) instead of crashing, so the rest of the monitor still runs offline.
  Skips are never cached, so a later run with a key fills them in.
* **Headlines** — default `SyntheticHeadlineProvider` (deterministic, offline);
  pass `--live-news` to pull live headlines via yfinance.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m portfolio_monitor --asof 2026-06-17 --live-news --news-window 3
# offline / no key: news is skipped with a clear note; macro gate still runs
python3 -m portfolio_monitor --asof 2026-06-17 --no-news
```

Optional Layer 3 dependencies: `pip install anthropic yfinance`.

## Data feed

The data layer talks to the feed through the `FinanceProvider` interface
(`portfolio_monitor/providers.py`). The default `SyntheticProvider` generates a
deterministic, self-consistent chain from a Black-Scholes surface so the whole
monitor runs offline and reproducibly:

* re-running the same `asof` reproduces identical numbers;
* advancing `asof` shifts spot and IV slightly, giving later layers real
  day-over-day movement to diff and to build IV history from.

To use a live feed (yfinance, a broker API, or the bundled finance MCP server),
implement `get_spot` and `get_chain` on a `FinanceProvider` subclass and pass
the instance to `run_monitor(...)`.

### Webull (live quotes & option chains)

A `WebullProvider` is included that pulls live spot prices and full option
chains (bid/ask/last/IV/volume/OI) via the **unofficial** `webull` PyPI
package:

```bash
pip install webull
export WEBULL_EMAIL=you@example.com WEBULL_PASSWORD=...   # + WEBULL_MFA / WEBULL_TRADE_PIN if required
python3 -m portfolio_monitor --asof 2026-06-17 --feed webull
python3 -m portfolio_monitor --asof 2026-06-17 --feed webull --feed-fallback   # synthetic if login fails
python3 -m portfolio_monitor --asof 2026-06-17 --feed webull --webull-max-expiries 6
```

> ⚠️ The `webull` package is **unofficial / reverse-engineered**: it logs in
> with your email + password (plus MFA / trade PIN), can break without notice,
> and using it may conflict with Webull's Terms of Service. `WebullProvider` is
> **read-only** — it pulls marks and chains, it never places orders. Login can
> be interactive (MFA); for unattended runs, authenticate once and pass the
> client into `WebullProvider(client)` directly. Option IV comes from Webull's
> feed; if a field is missing, greeks fall back to the local Black-Scholes
> solver. Keep `--feed synthetic` (the default) for fully offline runs.

## Importable API (for later layers)

```python
from datetime import date
from portfolio_monitor import run_monitor, load_positions, Storage

positions = load_positions("positions.json")
result = run_monitor(positions, asof=date(2026, 6, 17), db_path="portfolio.db")

print(result.total_value, result.total_pl)
for v in result.valuations:
    print(v.position_id, v.mark, v.unrealized_pl, v.dte, v.greeks)

# Read back snapshots / IV history for diffing
with Storage("portfolio.db") as st:
    st.list_snapshot_dates("AAPL")
    st.iv_history("AAPL", "call", 190.0, "2026-09-18")
```

### Module map
| module | responsibility |
|--------|----------------|
| `models.py` | dataclasses: `Position`, `OptionQuote`, `Chain`, `Greeks`, `PositionValuation` |
| `positions.py` | load / validate `positions.json` |
| `blackscholes.py` | pricing, greeks, implied-vol solver (stdlib only) |
| `providers.py` | `FinanceProvider` interface + `SyntheticProvider` |
| `valuation.py` | per-position mark / P&L / DTE / greeks / progress |
| `snapshots.py` | dated JSON chain files |
| `storage.py` | single-file SQLite schema + read helpers |
| `runner.py` | `run_monitor` orchestration, `RunResult` |
| `sectors.py` | ticker→sector lookup (config + yfinance fallback) |
| `analytics.py` | allocation, aggregate greeks, IV environment + persistence |
| `webull_feed.py` | live quotes & option chains via the unofficial `webull` package |
| `macro.py` | deterministic macro gate (providers, scoring, persistence) |
| `news.py` | Claude news analysis (headlines, analyzer, caching, persistence) |
| `report.py` | terminal rendering (valuation + analytics + market context) |
| `cli.py` | argument parsing / entry point |

## Tests

```bash
python3 -m pytest -q
```
