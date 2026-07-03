"""Carry-pole ranking metrics (what-makes-a-carry-sleeve-an-income-engine).

The concave income pole is hired to compound a premium in calm markets while
losing a *budgeted* amount in the tail. Sharpe is the one objective that pole
can game by construction: the Sharpe-maximizing payoff is "regular modest
profits punctuated by occasional crashes" (Goetzmann-Ingersoll-Spiegel-Welch),
so a Sharpe-ranked config sweep of a short-gamma sleeve selects the candidate
that best hides its tail. Two metrics split the job the vault's way — rank on a
smooth low-variance point estimate, gate on the tail:

1. **Carry income utility** — the manipulation-proof performance measure (MPPM):
   the annualized certainty-equivalent excess growth rate a CRRA evaluator with
   relative risk aversion ``rho`` assigns to the realized stream,

       theta = 1 / ((1 - rho) * dt) * ln( mean_t (1 + r_t)^(1 - rho) )

   Payoff-shaping cannot raise it without adding genuine expected utility, so it
   prices the hidden left tail the way the sleeve's owner experiences it (a day
   approaching total loss drives it to -inf). It is the concave mirror of
   ``trend_convexity_payoff`` and obeys the same stabilizer discipline: a smooth
   utility-weighted mean, no threshold or horizon knob, one interpretable
   parameter (rho, default 3, evaluators plausibly in 2-4). The risk-free hurdle
   is taken as zero: streams are net returns, and a common cash hurdle shifts
   every candidate in a sweep identically, so it cannot reorder them.
   Rho-stability of a ranking is a trust check, not a second knob —
   ``carry_utility_rho_sensitivity_from_curve`` reports it post hoc.

2. **Carry tail budget** — the budgeted-bleed gate: the annualized left-decile
   mean of overlapping multi-month compounded own returns, band-averaged over
   the same 2-6 month horizons as the convexity metrics (a short-gamma blowup
   plays out over weeks, and a daily tail badly understates it; ranking directly
   on tail quantiles is estimator-unstable on short samples, per
   Varga-Haszonits-Kondor, which is why this is a reported gate, not the
   ranker). A concave pole must show a left tail — it is paid for one — but the
   number must clear the floor the book can survive.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pandas as pd

from research.aegis_research.configuration import ReportConfig
from research.aegis_research.metrics.contracts import (
    SOURCE_TYPE_CUSTOM,
    ExtractorSpec,
    MetricDefinition,
)
from research.aegis_research.metrics.custom.convexity import (
    _ANNUALIZATION_DAYS,
    _HORIZON_BAND,
    _MIN_TAIL_WINDOWS,
    _TAIL_QUANTILE,
    _rolling_compound,
)
from research.aegis_research.metrics.custom.support import EquityCurve

# Evaluator relative risk aversion for the MPPM: Goetzmann et al. place a
# plausible evaluator at rho ~ 2-4; 3 is the midpoint and the registered ranker.
DEFAULT_RISK_AVERSION = 3.0
_SENSITIVITY_RHOS = (2.0, 3.0, 4.0, 5.0)
_MIN_OBSERVATIONS = 3

CARRY_INCOME_UTILITY_ID = "carry_income_utility"
CARRY_TAIL_BUDGET_ID = "carry_tail_budget"


# ── Reducers ──────────────────────────────────────────────────────────────────

def _carry_income_utility(daily: np.ndarray, rho: float = DEFAULT_RISK_AVERSION) -> float:
    """Annualized MPPM certainty-equivalent excess growth of one daily stream.

    A day at or beyond total loss has -inf power utility for rho > 1, so the
    stream scores -inf rather than averaging its ruin away — the property that
    makes the measure manipulation-proof rather than merely skew-aware.
    """
    if daily.size < _MIN_OBSERVATIONS:
        return np.nan
    growth = 1.0 + daily
    if np.any(growth <= 0.0):
        return float("-inf")
    mean_utility = float(np.mean(growth ** (1.0 - rho)))
    return _ANNUALIZATION_DAYS / (1.0 - rho) * float(np.log(mean_utility))


def _left_tail_budget(stream: np.ndarray, horizon: int) -> float:
    """Annualized left-decile mean of overlapping ``horizon``-day own returns.

    The loss side of convexity's net tail payoff, alone: how much the sleeve
    gives back when its multi-month windows go badly, on the horizon a
    short-gamma unwind actually develops over. A window floor keeps the decile
    mean stable on a held-out split; a mean at or beyond -100% cannot be
    annualized and reports as -1.0 (the budget is gone).
    """
    windows = _rolling_compound(stream, horizon)
    if windows.size < _MIN_TAIL_WINDOWS:
        return np.nan
    lo = np.quantile(windows, _TAIL_QUANTILE)
    left = windows[windows <= lo]
    if left.size == 0:
        return np.nan
    payoff = float(left.mean())
    if 1.0 + payoff <= 0.0:
        return -1.0
    return (1.0 + payoff) ** (_ANNUALIZATION_DAYS / horizon) - 1.0


def _carry_tail_budget(stream: np.ndarray) -> float:
    """Horizon-band-averaged left tail — the budgeted-bleed number (<= 0 in practice)."""
    vals = [_left_tail_budget(stream, h) for h in _HORIZON_BAND]
    finite = [v for v in vals if np.isfinite(v)]
    return float(np.mean(finite)) if finite else np.nan


# ── Post-hoc trust check ──────────────────────────────────────────────────────

def carry_utility_rho_sensitivity_from_curve(
    curve: EquityCurve, *, rhos: Sequence[float] = _SENSITIVITY_RHOS
) -> pd.DataFrame:
    """Per-group MPPM across a band of evaluator risk aversions, from one read.

    The ranker pins rho; this reports whether the *ranking* was rho's doing.
    Goetzmann et al. find rankings fairly stable across rho in [2, 5] — a
    shortlist whose order flips inside that band is leaning on the knob and
    should not be promoted on this metric. Returns a frame indexed by group
    with one column per rho.
    """
    returns = curve.returns()
    rows: dict[Any, dict[float, float]] = {}
    for col in returns.columns:
        stream = returns[col].dropna().to_numpy()
        rows[col] = {rho: _carry_income_utility(stream, rho) for rho in rhos}
    return pd.DataFrame.from_dict(rows, orient="index")


# ── Registry records ──────────────────────────────────────────────────────────

def _make_stream_read(fn: Callable[[np.ndarray], float]) -> Callable[[Any, ReportConfig], pd.Series]:
    def _read(pf: Any, config: ReportConfig) -> pd.Series:
        returns = EquityCurve.from_portfolio(pf).returns()
        return pd.Series({col: fn(returns[col].dropna().to_numpy()) for col in returns.columns})

    return _read


CARRY_INCOME_UTILITY_DEFINITION = MetricDefinition(
    id=CARRY_INCOME_UTILITY_ID,
    title=f"Carry Income Utility (MPPM rho={DEFAULT_RISK_AVERSION:g}, certainty-equivalent growth)",
    source_type=SOURCE_TYPE_CUSTOM,
    unit="return",
    value_semantics=(
        "annualized certainty-equivalent excess growth for a crash-averse (CRRA) evaluator; "
        "manipulation-proof (higher = more income net of the tail it hides)"
    ),
    provider="aegis",
    target="portfolio",
    source_method="get_value",
    required_report_output=False,
    required_gate_input=False,
    metadata={"risk_aversion": DEFAULT_RISK_AVERSION, "risk_free": 0.0},
)
CARRY_INCOME_UTILITY_EXTRACTOR = ExtractorSpec(_make_stream_read(_carry_income_utility))

CARRY_TAIL_BUDGET_DEFINITION = MetricDefinition(
    id=CARRY_TAIL_BUDGET_ID,
    title="Carry Tail Budget (left-decile multi-month return, 2-6mo band)",
    source_type=SOURCE_TYPE_CUSTOM,
    unit="return",
    value_semantics=(
        "annualized mean of the worst decile of overlapping 2-6 month own returns; "
        "the sleeve's budgeted bleed (closer to zero = shallower tail)"
    ),
    provider="aegis",
    target="portfolio",
    source_method="get_value",
    required_report_output=False,
    required_gate_input=False,
    metadata={"horizon_band_days": list(_HORIZON_BAND), "tail_quantile": _TAIL_QUANTILE},
)
CARRY_TAIL_BUDGET_EXTRACTOR = ExtractorSpec(_make_stream_read(_carry_tail_budget))


__all__ = [
    "CARRY_INCOME_UTILITY_DEFINITION",
    "CARRY_INCOME_UTILITY_EXTRACTOR",
    "CARRY_INCOME_UTILITY_ID",
    "CARRY_TAIL_BUDGET_DEFINITION",
    "CARRY_TAIL_BUDGET_EXTRACTOR",
    "CARRY_TAIL_BUDGET_ID",
    "DEFAULT_RISK_AVERSION",
    "carry_utility_rho_sensitivity_from_curve",
]
