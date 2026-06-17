"""Layer 3a — deterministic macro gate (0-100).

A pure, reproducible score for the general market environment the book sits
in. Same inputs in → same score out. Higher = calmer / more risk-supportive;
lower = more stressed / defensive. It is **context, not a signal** — it
describes the weather, it does not tell you to trade.

Five sub-scores (each 0-100, higher = calmer), blended with configurable
weights that must sum to 1.0:

* ``vix_level``      — outright VIX (low VIX → high score).
* ``vix_percentile`` — where today's VIX sits in its trailing 1-year range
  (low percentile → high score).
* ``term_structure`` — VIX vs VIX3M. Contango (VIX3M > VIX) is the calm,
  normal state → high score; backwardation (VIX > VIX3M) → low score.
* ``breadth``        — percent of SPY constituents above their 200-day MA
  (a breadth proxy). Healthier breadth → high score.
* ``credit``         — HYG vs TLT. Credit risk-on (HYG strong relative to TLT,
  high in its own 1-year range → spreads tightening) → high score.

Inputs arrive through a :class:`MacroProvider`; the default
:class:`SyntheticMacroProvider` derives everything deterministically from the
run date so the gate is fully reproducible offline. A live provider would pull
^VIX / ^VIX3M / HYG / TLT and a breadth series instead.
"""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List

from .storage import Storage


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class MacroWeights:
    """Blend weights for the five sub-scores. Must sum to 1.0."""

    vix_level: float = 0.20
    vix_percentile: float = 0.20
    term_structure: float = 0.20
    breadth: float = 0.20
    credit: float = 0.20

    def as_dict(self) -> Dict[str, float]:
        return {
            "vix_level": self.vix_level,
            "vix_percentile": self.vix_percentile,
            "term_structure": self.term_structure,
            "breadth": self.breadth,
            "credit": self.credit,
        }

    def validate(self) -> None:
        total = sum(self.as_dict().values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"macro weights must sum to 1.0, got {total:.6f}")


# Score-mapping bounds (fixed so the mapping is deterministic; documented).
VIX_CALM = 12.0    # at/below -> 100
VIX_PANIC = 40.0   # at/above -> 0
TS_CONTANGO = 0.85   # VIX/VIX3M ratio at/below -> 100 (steep contango)
TS_BACKWARD = 1.10   # VIX/VIX3M ratio at/above -> 0 (backwardation)


# ---------------------------------------------------------------------------
# Inputs and result
# ---------------------------------------------------------------------------


@dataclass
class MacroInputs:
    asof: date
    vix: float
    vix3m: float
    vix_history_1y: List[float]
    breadth_pct: float            # 0-100, percent of constituents > 200d MA
    hyg_tlt_ratio: float
    hyg_tlt_ratio_history_1y: List[float]


@dataclass
class MacroResult:
    asof: date
    score: float                  # 0-100 blended
    label: str
    components: Dict[str, float]  # sub-score name -> 0-100
    weights: Dict[str, float]
    inputs: Dict[str, float]      # snapshot of the raw drivers


class MacroProvider(ABC):
    @abstractmethod
    def get_macro_inputs(self, asof: date) -> MacroInputs:
        ...


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def percentile_of(value: float, history: List[float]) -> float:
    """Percent of historical observations strictly below ``value`` (0-100)."""
    if not history:
        return 50.0
    below = sum(1 for x in history if x < value)
    return below / len(history) * 100.0


def score_vix_level(vix: float) -> float:
    return _clamp(100.0 * (VIX_PANIC - vix) / (VIX_PANIC - VIX_CALM))


def score_vix_percentile(vix: float, history: List[float]) -> float:
    # Low VIX percentile (calm relative to its own year) -> high score.
    return _clamp(100.0 - percentile_of(vix, history))


def score_term_structure(vix: float, vix3m: float) -> float:
    if vix3m <= 0:
        return 50.0
    ratio = vix / vix3m
    return _clamp(100.0 * (TS_BACKWARD - ratio) / (TS_BACKWARD - TS_CONTANGO))


def score_breadth(breadth_pct: float) -> float:
    return _clamp(breadth_pct)


def score_credit(ratio: float, history: List[float]) -> float:
    # HYG strong relative to TLT (high in its own range) = risk-on = high score.
    return _clamp(percentile_of(ratio, history))


def _label(score: float) -> str:
    if score >= 67:
        return "supportive / calm"
    if score >= 33:
        return "neutral / mixed"
    return "stressed / defensive"


def compute_macro_score(inputs: MacroInputs, weights: MacroWeights | None = None) -> MacroResult:
    weights = weights or MacroWeights()
    weights.validate()

    components = {
        "vix_level": score_vix_level(inputs.vix),
        "vix_percentile": score_vix_percentile(inputs.vix, inputs.vix_history_1y),
        "term_structure": score_term_structure(inputs.vix, inputs.vix3m),
        "breadth": score_breadth(inputs.breadth_pct),
        "credit": score_credit(inputs.hyg_tlt_ratio, inputs.hyg_tlt_ratio_history_1y),
    }
    w = weights.as_dict()
    score = sum(components[k] * w[k] for k in components)

    return MacroResult(
        asof=inputs.asof,
        score=score,
        label=_label(score),
        components=components,
        weights=w,
        inputs={
            "vix": inputs.vix,
            "vix3m": inputs.vix3m,
            "vix_1y_percentile": percentile_of(inputs.vix, inputs.vix_history_1y),
            "breadth_pct": inputs.breadth_pct,
            "hyg_tlt_ratio": inputs.hyg_tlt_ratio,
        },
    )


# ---------------------------------------------------------------------------
# Synthetic (deterministic) provider
# ---------------------------------------------------------------------------


def _unit(*parts) -> float:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


class SyntheticMacroProvider(MacroProvider):
    """Deterministic macro inputs derived purely from the run date.

    Produces a 1-year daily VIX history and HYG/TLT-ratio history so that the
    percentile sub-scores are meaningful, and is stable for any given ``asof``
    (re-running reproduces identical inputs → identical score).
    """

    def _vix_on(self, d: date) -> float:
        o = d.toordinal()
        base = 17.0
        slow = 6.0 * math.sin(o / 47.0)          # multi-week regime swings
        fast = 2.5 * math.sin(o / 6.0 + 1.3)     # short-term chop
        jitter = (_unit("vix", d.isoformat()) - 0.5) * 1.5
        return max(9.0, base + slow + fast + jitter)

    def _hyg_tlt_on(self, d: date) -> float:
        o = d.toordinal()
        base = 1.20
        swing = 0.08 * math.sin(o / 53.0 + 0.7)
        jitter = (_unit("credit", d.isoformat()) - 0.5) * 0.01
        return base + swing + jitter

    def get_macro_inputs(self, asof: date) -> MacroInputs:
        hist_days = [asof - timedelta(days=i) for i in range(252, 0, -1)]
        vix_hist = [self._vix_on(d) for d in hist_days]
        ratio_hist = [self._hyg_tlt_on(d) for d in hist_days]

        vix = self._vix_on(asof)
        # VIX3M sits above VIX in calm regimes (contango), below in stress.
        contango = 1.06 + 0.04 * math.sin(asof.toordinal() / 31.0)
        # In high-VIX regimes, compress/invert the term structure.
        stress = max(0.0, (vix - 22.0) / 18.0)
        vix3m = vix * (contango - 0.18 * stress)

        breadth = 55.0 + 25.0 * math.sin(asof.toordinal() / 41.0 + 2.0)
        breadth = _clamp(breadth + (_unit("breadth", asof.isoformat()) - 0.5) * 6.0)

        return MacroInputs(
            asof=asof,
            vix=round(vix, 2),
            vix3m=round(vix3m, 2),
            vix_history_1y=vix_hist,
            breadth_pct=round(breadth, 1),
            hyg_tlt_ratio=round(self._hyg_tlt_on(asof), 4),
            hyg_tlt_ratio_history_1y=ratio_hist,
        )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

MACRO_SCHEMA = """
CREATE TABLE IF NOT EXISTS macro_score (
    asof_date       TEXT PRIMARY KEY,
    score           REAL NOT NULL,
    label           TEXT NOT NULL,
    vix_level       REAL NOT NULL,
    vix_percentile  REAL NOT NULL,
    term_structure  REAL NOT NULL,
    breadth         REAL NOT NULL,
    credit          REAL NOT NULL,
    vix             REAL,
    vix3m           REAL,
    breadth_pct     REAL,
    hyg_tlt_ratio   REAL,
    pulled_at       TEXT NOT NULL
);
"""


def ensure_macro_schema(storage: Storage) -> None:
    storage.conn.executescript(MACRO_SCHEMA)
    storage.conn.commit()


def store_macro(storage: Storage, result: MacroResult) -> None:
    from datetime import datetime

    ensure_macro_schema(storage)
    c = result.components
    with storage._tx() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO macro_score
               (asof_date, score, label, vix_level, vix_percentile, term_structure,
                breadth, credit, vix, vix3m, breadth_pct, hyg_tlt_ratio, pulled_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.asof.isoformat(), result.score, result.label,
                c["vix_level"], c["vix_percentile"], c["term_structure"],
                c["breadth"], c["credit"],
                result.inputs.get("vix"), result.inputs.get("vix3m"),
                result.inputs.get("breadth_pct"), result.inputs.get("hyg_tlt_ratio"),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
