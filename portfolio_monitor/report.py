"""Plain-text rendering of a run's valuations for the terminal."""

from __future__ import annotations

from typing import List

from .analytics import AnalyticsResult
from .models import PositionValuation
from .runner import RunResult


def _fmt(value, spec="{:.2f}", dash="-"):
    return spec.format(value) if value is not None else dash


def _pct(value):
    return f"{value:+.1f}%" if value is not None else "-"


def render(result: RunResult) -> str:
    lines: List[str] = []
    lines.append(f"Portfolio monitor — as-of {result.asof.isoformat()} "
                 f"(risk-free rate {result.rate:.3%})")
    lines.append("=" * 110)

    header = (
        f"{'POSITION':<24}{'TYPE':<7}{'MARK':>9}{'VALUE':>12}"
        f"{'P&L $':>12}{'P&L %':>9}{'DTE':>5}{'→TGT':>8}{'→STOP':>8}"
    )
    lines.append(header)
    lines.append("-" * 110)

    for v in result.valuations:
        lines.append(
            f"{v.position_id:<24}{v.asset_type:<7}"
            f"{_fmt(v.mark):>9}{_fmt(v.current_value, '{:,.0f}'):>12}"
            f"{_fmt(v.unrealized_pl, '{:+,.0f}'):>12}{_pct(v.unrealized_pl_pct):>9}"
            f"{(str(v.dte) if v.dte is not None else '-'):>5}"
            f"{_pct(v.progress_to_target):>8}{_pct(v.progress_to_stop):>8}"
        )

    lines.append("-" * 110)
    lines.append(
        f"{'TOTAL':<24}{'':<7}{'':>9}"
        f"{result.total_value:>12,.0f}{result.total_pl:>+12,.0f}"
        f"{(result.total_pl / result.total_cost_basis * 100 if result.total_cost_basis else 0):>+8.1f}%"
    )

    # Greeks block for options (per-position, scaled to the held size).
    option_vals = [v for v in result.valuations if v.greeks is not None]
    if option_vals:
        lines.append("")
        lines.append("Option greeks (per share, IV from feed):")
        lines.append(
            f"{'POSITION':<24}{'IV':>8}{'DELTA':>9}{'GAMMA':>9}{'THETA/d':>10}{'VEGA/1%':>10}"
        )
        lines.append("-" * 70)
        for v in option_vals:
            g = v.greeks
            lines.append(
                f"{v.position_id:<24}{_fmt(v.iv, '{:.1%}'):>8}"
                f"{_fmt(g.delta, '{:+.3f}'):>9}{_fmt(g.gamma, '{:.4f}'):>9}"
                f"{_fmt(g.theta, '{:+.3f}'):>10}{_fmt(g.vega, '{:+.3f}'):>10}"
            )

    if result.snapshot_files:
        lines.append("")
        lines.append("Snapshots written:")
        for path in result.snapshot_files:
            lines.append(f"  {path}")
    return "\n".join(lines)


def render_analytics(a: AnalyticsResult) -> str:
    cfg = a.config
    lines: List[str] = []
    lines.append("")
    lines.append(f"Portfolio analytics — as-of {a.asof.isoformat()}")
    lines.append("=" * 70)

    # -- Allocation ---------------------------------------------------------
    lines.append(f"Allocation by ticker (total value {a.allocation.total_value:,.0f}):")
    for it in a.allocation.by_ticker:
        flag = f"  ⚠ > {cfg.ticker_cap_pct:.0f}% cap" if it.flagged else ""
        lines.append(f"  {it.key:<10}{it.value:>14,.0f}{it.pct:>8.1f}%{flag}")
    lines.append("Allocation by sector:")
    for it in a.allocation.by_sector:
        flag = f"  ⚠ > {cfg.sector_cap_pct:.0f}% cap" if it.flagged else ""
        lines.append(f"  {it.key:<22}{it.value:>14,.0f}{it.pct:>8.1f}%{flag}")

    flagged = [i.key for i in a.allocation.by_ticker if i.flagged] + \
              [i.key for i in a.allocation.by_sector if i.flagged]
    if flagged:
        lines.append(f"  Concentration flags (informational): {', '.join(flagged)}")
    else:
        lines.append("  Concentration: no caps exceeded.")

    # -- Aggregate greeks ---------------------------------------------------
    g = a.greeks
    lines.append("")
    lines.append("Aggregate greeks (portfolio-level exposures):")
    lines.append(f"  Net delta        {g.net_delta_shares:>14,.1f} share-equivalents")
    lines.append(f"  Net gamma        {g.net_gamma_shares:>14,.2f} per 1.00 move")
    lines.append(f"  Daily theta      {g.total_theta_dollars:>14,.0f} $/day "
                 f"({'loses' if g.total_theta_dollars < 0 else 'gains'} if nothing moves)")
    lines.append(f"  Net vega         {g.net_vega_dollars:>14,.0f} $ per 1 IV point")

    # -- IV environment -----------------------------------------------------
    if a.iv_environment:
        lines.append("")
        lines.append("IV environment (per option):")
        lines.append(
            f"  {'POSITION':<24}{'IV':>7}{'RANK':>7}{'PCTILE':>8}{'STATUS':>11}"
            f"{'FLAG':>8}{'DTE':>5}"
        )
        lines.append("  " + "-" * 70)
        for iv in a.iv_environment:
            rank = f"{iv.iv_rank:.0f}" if iv.iv_rank is not None else "-"
            pct = f"{iv.iv_percentile:.0f}" if iv.iv_percentile is not None else "-"
            cur = f"{iv.current_iv:.1%}" if iv.current_iv is not None else "-"
            flag = iv.valuation if iv.valuation in ("rich", "cheap") else ""
            dte_txt = str(iv.dte) if iv.dte is not None else "-"
            if iv.near_expiry:
                dte_txt += "!"
            status = "building" if iv.status == "building history" else "ok"
            lines.append(
                f"  {iv.position_id:<24}{cur:>7}{rank:>7}{pct:>8}{status:>11}"
                f"{flag:>8}{dte_txt:>5}"
            )
        near = [iv.position_id for iv in a.iv_environment if iv.near_expiry]
        if near:
            lines.append(
                f"  Near expiry (≤ {cfg.dte_warn_threshold}d), time decay accelerating: "
                f"{', '.join(near)}"
            )
        building = [iv.position_id for iv in a.iv_environment if iv.status == "building history"]
        if building:
            lines.append(
                f"  IV rank 'building history' (< {cfg.iv_min_history_days} days stored): "
                f"{', '.join(building)}"
            )
    return "\n".join(lines)
