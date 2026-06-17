"""Plain-text rendering of a run's valuations for the terminal."""

from __future__ import annotations

from typing import List

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
