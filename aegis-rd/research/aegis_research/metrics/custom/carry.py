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

3. **Carry downside L-skew** — the *family-membership* gate, robust edition. The
   concave pole must carry materially negative skew or it is not short-gamma at
   all; but the third-moment (Pearson) skew we used before is the worst possible
   estimator of that, because it is an average of *cubed* deviations and a single
   crash quarter dominates it (Kim-White: conventional skew is "extremely
   sensitive to single outliers"). This replaces it with the **L-moment skewness**
   (tau_3 = l3 / l2), a linear function of order statistics that is bounded in
   (-1, 1), exists whenever the mean does, and has far lower bias and sampling
   variance than the moment skew (Hosking; Bastianin finds L/TL-moments give the
   lowest RMSE on financial series). Measured on the same overlapping multi-month
   compounded windows as the tail budget (the concave signature lives at the
   multi-month horizon, not the day), band-averaged. Two-sided by intent: a pole
   must be deep enough to be genuinely short-gamma (tau_3 clearly < 0) *and*
   survivable (the tail budget floor) — skew is a mandate the pole must hold, not
   an objective to maximize (maximizing depth buys uncompensated crash).

None of the three sees the pole's *portfolio* job. That is a relational property
- income in calm, and a budgeted loss placed where the trend pole is *up* - which
no function of the carry stream alone can price (a stream can look ideal standalone
and still co-crash with trend). The **allocator** helpers below close that gap:
they score a carry candidate by its manipulation-proof contribution to the blended
*book*, and by its downside correlation to the trend pole. See
"The metric to rank on" in [[what-makes-a-carry-sleeve-an-income-engine]].
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

# Allocator defaults: the floor's fixed carry weight in vol-normalized risk space
# (runs/floor/2026-06-14 addendum) and the book's mandate volatility. Both poles are
# rescaled to this same book vol before the MPPM, so the certainty-equivalent delta
# ranks payoff *shape and placement*, never scale (the ranker A/B lesson: MPPM on a
# free scale axis ranks mu-noise; pinning the book vol removes that axis by construction).
DEFAULT_BLEND_WEIGHT = 0.40
DEFAULT_BOOK_VOL = 0.10
_DOWNSIDE_QUANTILE = 0.10

CARRY_INCOME_UTILITY_ID = "carry_income_utility"
CARRY_TAIL_BUDGET_ID = "carry_tail_budget"
CARRY_DOWNSIDE_LSKEW_ID = "carry_downside_lskew"


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


def _l_skewness(values: np.ndarray) -> float:
    """Sample L-skewness (tau_3 = l3 / l2) via probability-weighted moments.

    L-moments are linear combinations of order statistics, so - unlike the
    third-moment skew's cubed deviations - a single outlier moves this only
    linearly (Hosking 1990; Kim-White 2004). Bounded in (-1, 1), it exists for
    any stream with a finite mean. Non-positive L-scale (a degenerate, ~constant
    window set) returns NaN rather than dividing by ~0.
    """
    ordered = np.sort(values)
    n = ordered.size
    if n < 4:
        return np.nan
    i = np.arange(1, n + 1)
    b0 = float(ordered.mean())
    b1 = float(np.sum((i - 1) / (n - 1) * ordered) / n)
    b2 = float(np.sum((i - 1) * (i - 2) / ((n - 1) * (n - 2)) * ordered) / n)
    l2 = 2.0 * b1 - b0
    l3 = 6.0 * b2 - 6.0 * b1 + b0
    if l2 <= 0.0:
        return np.nan
    return l3 / l2


def _carry_downside_lskew(stream: np.ndarray) -> float:
    """Horizon-band-averaged robust (L-moment) skew of overlapping multi-month returns.

    The family-membership number: a concave income pole must read clearly negative
    (short-gamma), measured where the concave signature lives - the multi-month
    horizon - with an estimator a lone crash cannot dominate.
    """
    vals = []
    for horizon in _HORIZON_BAND:
        windows = _rolling_compound(stream, horizon)
        if windows.size >= _MIN_TAIL_WINDOWS:
            skew = _l_skewness(windows)
            if np.isfinite(skew):
                vals.append(skew)
    return float(np.mean(vals)) if vals else np.nan


# ── Allocator: the pole's portfolio contribution (needs the trend stream) ──────
#
# These price the relational job no single-book metric can see. They take the carry
# candidate's daily returns AND the trend pole's daily returns, already aligned to a
# common calendar by the caller (the floor harness). They are not registered as
# sweep-time metrics: a per-candidate custom metric only sees its own book, so wiring
# the allocator utility *into* a sweep needs the trend pole's returns as a stored
# fixture (a follow-up). Until then the two-stage design holds: the sweep ranks on the
# single-book gates above, and these rank the shortlist in the composite.

def _to_unit_vol(daily: np.ndarray) -> np.ndarray | None:
    sd = float(np.std(daily))
    if not np.isfinite(sd) or sd <= 0.0:
        return None
    return daily / sd


def _blended_book(
    carry_daily: np.ndarray,
    trend_daily: np.ndarray,
    *,
    carry_weight: float,
    book_vol_annual: float,
) -> np.ndarray | None:
    """The two-pole book: put each LEG at the book vol, blend (1-w)/w, keep the blend as is.

    Each leg is unit-vol-normalized then scaled to ``book_vol_annual`` - this pins the
    scale axis at the *leg* level (the carry pole's own volatility is a mandate, not a
    free knob, so it must not be a way to score higher). The blend's volatility then
    *floats* with the correlation structure: a pole that diversifies trend lowers book
    vol and shallows the joint tail (higher MPPM); one that co-crashes raises both
    (lower MPPM). The blend is a real return stream (1+r stays positive at ~10% vol), so
    the MPPM is well defined. Crucially the blend is NOT re-normalized to a fixed vol -
    doing so would divide out exactly the concentrated joint-crash risk we mean to price,
    perversely rewarding a co-crashing pole for raising raw book vol.
    """
    if carry_daily.size != trend_daily.size or carry_daily.size < _MIN_OBSERVATIONS:
        return None
    z_carry = _to_unit_vol(carry_daily)
    z_trend = _to_unit_vol(trend_daily)
    if z_carry is None or z_trend is None:
        return None
    leg_vol = book_vol_annual / np.sqrt(_ANNUALIZATION_DAYS)
    carry_leg = z_carry * leg_vol
    trend_leg = z_trend * leg_vol
    return (1.0 - carry_weight) * trend_leg + carry_weight * carry_leg


def composite_book_utility(
    carry_daily: np.ndarray,
    trend_daily: np.ndarray,
    *,
    carry_weight: float = DEFAULT_BLEND_WEIGHT,
    rho: float = DEFAULT_RISK_AVERSION,
    book_vol_annual: float = DEFAULT_BOOK_VOL,
) -> float:
    """MPPM certainty-equivalent growth of the blended two-pole book (the ranker level)."""
    book = _blended_book(
        carry_daily, trend_daily, carry_weight=carry_weight, book_vol_annual=book_vol_annual
    )
    if book is None:
        return np.nan
    return _carry_income_utility(book, rho)


def composite_allocator_utility(
    carry_daily: np.ndarray,
    trend_daily: np.ndarray,
    *,
    carry_weight: float = DEFAULT_BLEND_WEIGHT,
    rho: float = DEFAULT_RISK_AVERSION,
    book_vol_annual: float = DEFAULT_BOOK_VOL,
) -> float:
    """The allocator metric: the carry pole's manipulation-proof contribution to the book.

    ``delta_theta = Theta(book with this carry pole) - Theta(trend pole alone)``, both
    at the same book vol. Positive = the pole earns its place. Because the MPPM's power
    utility weights the book's joint-loss states, delta_theta prices, in one number,
    income (raises the calm book), the tail (only insofar as it deepens the *book's*
    tail), and crisis-conditional placement (a pole whose losses land in trend's *gains*
    never deepens the book's tail and scores high; one that co-crashes with trend scores
    low). It is the Tasche marginal-contribution rho(X) - rho(X - X_i) with rho the
    negative MPPM, and it is manipulation-proof at the book level (Goetzmann et al.).
    """
    theta_book = composite_book_utility(
        carry_daily, trend_daily, carry_weight=carry_weight, rho=rho, book_vol_annual=book_vol_annual
    )
    trend_ref = _blended_book(
        trend_daily, trend_daily, carry_weight=0.0, book_vol_annual=book_vol_annual
    )
    if not np.isfinite(theta_book) or trend_ref is None:
        return np.nan
    theta_trend = _carry_income_utility(trend_ref, rho)
    if not np.isfinite(theta_trend):
        return np.nan
    return theta_book - theta_trend


def downside_correlation(
    carry_daily: np.ndarray,
    trend_daily: np.ndarray,
    *,
    quantile: float = _DOWNSIDE_QUANTILE,
) -> float:
    """Correlation of carry to trend on trend's worst-``quantile`` days (Ang-Chen-Xing).

    The relational guard the composite utility's ranking rests on: a full-sample
    correlation hides crisis co-movement (Page-Panariello), so the pole is gated on its
    correlation *in the states the diversification is bought* - it must not co-crash with
    the convex pole. NaN when the conditioning set is too thin to correlate.
    """
    if carry_daily.size != trend_daily.size or carry_daily.size < _MIN_TAIL_WINDOWS:
        return np.nan
    threshold = np.quantile(trend_daily, quantile)
    mask = trend_daily <= threshold
    if mask.sum() < _MIN_OBSERVATIONS or np.std(carry_daily[mask]) <= 0.0:
        return np.nan
    return float(np.corrcoef(carry_daily[mask], trend_daily[mask])[0, 1])


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

CARRY_DOWNSIDE_LSKEW_DEFINITION = MetricDefinition(
    id=CARRY_DOWNSIDE_LSKEW_ID,
    title="Carry Downside L-Skew (robust L-moment skew, 2-6mo band)",
    source_type=SOURCE_TYPE_CUSTOM,
    unit="ratio",
    value_semantics=(
        "robust L-moment skewness (tau_3) of overlapping 2-6 month own returns; "
        "the concave family-membership gate (clearly negative = short-gamma)"
    ),
    provider="aegis",
    target="portfolio",
    source_method="get_value",
    required_report_output=False,
    required_gate_input=False,
    metadata={"horizon_band_days": list(_HORIZON_BAND), "estimator": "l_moment_tau3"},
)
CARRY_DOWNSIDE_LSKEW_EXTRACTOR = ExtractorSpec(_make_stream_read(_carry_downside_lskew))


__all__ = [
    "CARRY_DOWNSIDE_LSKEW_DEFINITION",
    "CARRY_DOWNSIDE_LSKEW_EXTRACTOR",
    "CARRY_DOWNSIDE_LSKEW_ID",
    "CARRY_INCOME_UTILITY_DEFINITION",
    "CARRY_INCOME_UTILITY_EXTRACTOR",
    "CARRY_INCOME_UTILITY_ID",
    "CARRY_TAIL_BUDGET_DEFINITION",
    "CARRY_TAIL_BUDGET_EXTRACTOR",
    "CARRY_TAIL_BUDGET_ID",
    "DEFAULT_BLEND_WEIGHT",
    "DEFAULT_BOOK_VOL",
    "DEFAULT_RISK_AVERSION",
    "composite_allocator_utility",
    "composite_book_utility",
    "carry_utility_rho_sensitivity_from_curve",
    "downside_correlation",
]
