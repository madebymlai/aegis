"""Convergent-engine ranking and shape metrics.

The convergent engine is hired to compound a compensated premium in ordinary
markets while accepting an understood convergence-break state. That job does
not require negative skew. Some implementations are concave and short-gamma;
others may be symmetric or positively skewed. Three metrics split evaluation
accordingly: rank on a smooth low-variance utility estimate, then report tail
severity and realized shape without turning either report into a membership gate.

Sharpe remains especially dangerous for a concave implementation: its maximizing
payoff is "regular modest profits punctuated by occasional crashes"
(Goetzmann-Ingersoll-Spiegel-Welch), so a Sharpe-ranked short-gamma sweep selects
the candidate that best hides its tail.

1. **Convergent income utility** — the manipulation-proof performance measure (MPPM):
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
   ``convergent_utility_rho_sensitivity_from_curve`` reports it post hoc.

2. **Convergent tail budget** — the budgeted-bleed report: the actual left-decile
   mean of overlapping multi-month compounded own returns, band-averaged over
   the same 2-6 month horizons as the convexity metrics (a short-gamma blowup
   plays out over weeks, and a daily tail badly understates it; ranking directly
   on tail quantiles is estimator-unstable on short samples, per
   Varga-Haszonits-Kondor, which is why this is reported, not used as the
   ranker). A candidate claiming concavity should show the loss state it is paid
   to accept, and the reported magnitude must remain survivable for the book. For
   other convergent mechanisms this remains a tail-severity description.

3. **Convergent downside L-skew** — the realized-sample shape report, robust edition. A
   candidate intended to fill the concave pole must exhibit materially negative skew
   or it is not short-gamma at all; but the third-moment (Pearson) skew we used before is
   the worst possible
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
   survivable (the tail budget floor). This sign expectation is conditional on a
   short-gamma mechanism; it is not a requirement of the convergent role itself.
   Even there, skew is a report rather than an objective to maximize, because
   maximizing depth buys uncompensated crash risk.

None of the three sees the pole's *portfolio* job. That is a relational property
- income in calm, and a budgeted loss placed where the trend pole is *up* - which
no function of the convergent stream alone can price (a stream can look ideal standalone
and still co-crash with trend). The **allocator** helpers below close that gap:
they score a convergent candidate by its manipulation-proof contribution to the blended
*book*, and by its downside correlation to the trend pole. See
"The metric to rank on" in [[what-makes-a-convergent-sleeve-an-income-engine]].
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
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

# Allocator defaults: the floor's fixed convergent weight in vol-normalized risk space
# (runs/floor/2026-06-14 addendum) and the book's mandate volatility. Each LEG is pinned to
# this volatility; the blended book's own volatility then floats with the leg correlation, so
# delta_theta is NOT a matched-risk comparison. That float is what makes the co-crash penalty
# work and what makes the sign scale-dependent - one mechanism, both effects, measured and
# documented in _blended_book and tracked in aegis-rd-600y.
DEFAULT_CONVERGENT_WEIGHT = 0.40
# Matches aegis-trader's book.toml book_vol_target. It is a default, not a constant of
# nature: a caller evaluating a book run at another volatility should pass that instead,
# because the comparison happens at whatever level this sets.
DEFAULT_BOOK_VOL = 0.09
_DOWNSIDE_QUANTILE = 0.10

# Paired-resample inference defaults. One sample of delta_theta is a point estimate on
# dependent, autocorrelated streams; the article's ranking rule asks for superiority
# inferred from paired resampling, not from a single number. Block lengths span the
# horizon band so a reader can see whether the verdict survives longer dependence.
# Retained only as the documented fallback for callers that pass block lengths
# explicitly; the default path now derives the band from the data (block_length_band).
DEFAULT_BLOCK_LENGTHS = (21, 63, 126)
DEFAULT_BOOTSTRAP_SAMPLES = 2_000
DEFAULT_BOOTSTRAP_SEED = 42
_INTERVAL_QUANTILES = (0.025, 0.975)

CONVERGENT_INCOME_UTILITY_ID = "convergent_income_utility"
CONVERGENT_TAIL_BUDGET_ID = "convergent_tail_budget"
CONVERGENT_DOWNSIDE_LSKEW_ID = "convergent_downside_lskew"


# ── Reducers ──────────────────────────────────────────────────────────────────


def _convergent_income_utility(daily: np.ndarray, rho: float = DEFAULT_RISK_AVERSION) -> float:
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
    """Actual left-decile mean of overlapping ``horizon``-day own returns.

    The loss side of convexity's net tail payoff, alone: how much the sleeve
    gives back when its multi-month windows go badly, on the horizon a
    short-gamma unwind actually develops over. A window floor keeps the decile
    mean stable on a finite Development path. The result stays in capital-budget units:
    -0.08 means an 8% loss over the stated horizon, not an annualized projection.
    """
    windows = _rolling_compound(stream, horizon)
    if windows.size < _MIN_TAIL_WINDOWS:
        return np.nan
    lo = np.quantile(windows, _TAIL_QUANTILE)
    left = windows[windows <= lo]
    if left.size == 0:
        return np.nan
    payoff = float(left.mean())
    return max(payoff, -1.0)


def _convergent_tail_budget(stream: np.ndarray) -> float:
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


def _convergent_downside_lskew(stream: np.ndarray) -> float:
    """Horizon-band-averaged robust (L-moment) skew of overlapping multi-month returns.

    A realized-shape description measured at the multi-month horizon, with an
    estimator a lone bad print cannot dominate. Contractual payoff identity and
    realized sample shape remain separate claims.
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
# These price the relational job no single-book metric can see. They take the convergent
# candidate's daily returns AND the trend pole's daily returns, already aligned to a
# common calendar by the caller (the floor harness). They are not registered as
# sweep-time metrics: a per-candidate custom metric only sees its own book, so wiring
# the allocator utility *into* a sweep needs the trend pole's returns as a stored
# fixture (a follow-up). Until then the two-stage design holds: the sweep ranks on the
# single-book measure above, reports tail and shape, and these helpers evaluate the
# shortlist in the paired book.


def _to_unit_vol(daily: np.ndarray) -> np.ndarray | None:
    sd = float(np.std(daily))
    if not np.isfinite(sd) or sd <= 0.0:
        return None
    return daily / sd


def _blended_book(
    convergent_daily: np.ndarray,
    trend_daily: np.ndarray,
    *,
    convergent_weight: float,
    book_vol_annual: float,
) -> np.ndarray | None:
    """The two-pole book: put each LEG at the book vol, blend (1-w)/w, let the blend float.

    Each leg is unit-vol-normalized then scaled to ``book_vol_annual`` - this pins the
    scale axis at the *leg* level (the convergent pole's own volatility is a mandate, not a
    free knob, so it must not be a way to score higher). The blend's volatility then
    *floats* with the correlation structure: a pole that diversifies trend lowers book vol,
    one that co-crashes raises it.

    That float is deliberate and it is also this metric's central confound. Both readings
    were measured on 2026-07-25 and both are true:

    - It is **why the co-crash penalty works.** Co-movement raises the blend's volatility,
      which the MPPM prices directly. Levering the blend back to a common volatility instead
      *inverts* the ranking: on the matched-marginal fixture in the tests, the decoupled pole
      wins 8/8 under this convention and 0/8 at matched volatility when the pole's drift is
      low, because the diversifying blend needs more leverage to reach the target and that
      amplifies its tail faster than its shape advantage repays. The inversion clears only
      once the pole earns roughly 25%/yr; the live convergent sleeve earns 4.2%.
    - It **confounds the sign with scale.** The MPPM is a certainty-equivalent growth *rate*,
      not a scale-invariant score - ``Theta(lambda r)`` is approximately
      ``lambda mu - (rho/2) lambda^2 sigma^2`` - so the blend at ~7.7% volatility is compared
      against a reference at 10% and is charged for the de-risking it supplied. On the live
      pair that alone moves the answer from -0.014 to +0.008. Standard practice for comparing
      portfolios of unequal risk is to match volatility first (Graham-Harvey's GH2), and the
      live allocator does exactly that when it scales sleeves to ``book_vol_target``.

    So ``delta_theta`` from this construction is **not** a matched-risk comparison and its sign
    should not be read as one. Fixing that without losing the co-crash penalty needs the
    placement question moved to the ``downside_correlation`` guard, which is scale-free and
    separates the same fixture cleanly (+0.93 against -0.07) - a design change tracked
    separately, not a convention swap.
    """
    if convergent_daily.size != trend_daily.size or convergent_daily.size < _MIN_OBSERVATIONS:
        return None
    z_convergent = _to_unit_vol(convergent_daily)
    z_trend = _to_unit_vol(trend_daily)
    if z_convergent is None or z_trend is None:
        return None
    leg_vol = book_vol_annual / np.sqrt(_ANNUALIZATION_DAYS)
    convergent_leg = z_convergent * leg_vol
    trend_leg = z_trend * leg_vol
    return (1.0 - convergent_weight) * trend_leg + convergent_weight * convergent_leg


def composite_book_utility(
    convergent_daily: np.ndarray,
    trend_daily: np.ndarray,
    *,
    convergent_weight: float = DEFAULT_CONVERGENT_WEIGHT,
    rho: float = DEFAULT_RISK_AVERSION,
    book_vol_annual: float = DEFAULT_BOOK_VOL,
) -> float:
    """MPPM certainty-equivalent growth of the blended two-pole book (the ranker level)."""
    book = _blended_book(
        convergent_daily,
        trend_daily,
        convergent_weight=convergent_weight,
        book_vol_annual=book_vol_annual,
    )
    if book is None:
        return np.nan
    return _convergent_income_utility(book, rho)


def composite_allocator_utility(
    convergent_daily: np.ndarray,
    trend_daily: np.ndarray,
    *,
    convergent_weight: float = DEFAULT_CONVERGENT_WEIGHT,
    rho: float = DEFAULT_RISK_AVERSION,
    book_vol_annual: float = DEFAULT_BOOK_VOL,
) -> float:
    """The allocator metric: the convergent pole's manipulation-proof contribution to the book.

    ``delta_theta = Theta(book with this convergent pole) - Theta(trend pole alone)``, with
    each *leg* pinned to ``book_vol_annual``. Positive = the pole earns its place. Because
    the MPPM's power utility weights the book's joint-loss states, delta_theta prices, in one
    number, income (raises the calm book), the tail (only insofar as it deepens the *book's*
    tail), and crisis-conditional placement (a pole whose losses land in trend's *gains*
    never deepens the book's tail and scores high; one that co-crashes with trend scores
    low). It is manipulation-proof at the book level (Goetzmann-Ingersoll-Spiegel-Welch).

    Two corrections to what this docstring used to claim, both established 2026-07-25.

    **It is not a matched-volatility comparison.** The legs are pinned; the two *books* are
    not. The blend floats to roughly 7.7% against a 10% reference, and since the MPPM is a
    growth *rate* rather than a scale-invariant score, some of ``delta_theta`` is that scale
    gap rather than the pole's quality - enough to carry the sign on the live pair. See
    :func:`_blended_book` for why the float is nonetheless kept: it is the channel through
    which the co-crash penalty operates, and matching volatility inverts that penalty at
    realistic drift. Read the sign as convention-dependent, and read the accompanying
    ``downside_correlation`` alongside it, not after it.

    **It is not a Tasche marginal risk contribution**, though this docstring said so. Tasche's
    ``rho(X) - rho(X - X_i)`` carries its meaning - the Euler and RORAC allocation results -
    only for a risk measure homogeneous of degree 1, and a CRRA certainty-equivalent growth
    rate is not: ``Theta(lambda r)`` is approximately ``lambda mu - (rho/2) lambda^2 sigma^2``.
    The arithmetic shape is shared; none of the guarantees are. The reference here is also the
    trend leg at full weight rather than Tasche's ``(1-w)`` remainder, a second departure.

    ``book_vol_annual`` is not cosmetic: it sets the risk level the comparison happens at, and
    callers should pass the volatility their book actually runs at.
    """
    theta_book = composite_book_utility(
        convergent_daily,
        trend_daily,
        convergent_weight=convergent_weight,
        rho=rho,
        book_vol_annual=book_vol_annual,
    )
    trend_ref = _blended_book(
        trend_daily, trend_daily, convergent_weight=0.0, book_vol_annual=book_vol_annual
    )
    if not np.isfinite(theta_book) or trend_ref is None:
        return np.nan
    theta_trend = _convergent_income_utility(trend_ref, rho)
    if not np.isfinite(theta_trend):
        return np.nan
    return theta_book - theta_trend


def downside_correlation(
    convergent_daily: np.ndarray,
    trend_daily: np.ndarray,
    *,
    quantile: float = _DOWNSIDE_QUANTILE,
) -> float:
    """Correlation of convergent to trend on trend's worst-``quantile`` days (Ang-Chen-Xing).

    The relational guard the composite utility's ranking rests on: a full-sample
    correlation hides crisis co-movement (Page-Panariello), so the pole is gated on its
    correlation *in the states the diversification is bought* - it must not co-crash with
    the convex pole. NaN when the conditioning set is too thin to correlate.
    """
    if convergent_daily.size != trend_daily.size or convergent_daily.size < _MIN_TAIL_WINDOWS:
        return np.nan
    threshold = np.quantile(trend_daily, quantile)
    mask = trend_daily <= threshold
    if mask.sum() < _MIN_OBSERVATIONS or np.std(convergent_daily[mask]) <= 0.0:
        return np.nan
    return float(np.corrcoef(convergent_daily[mask], trend_daily[mask])[0, 1])


# ── Paired-resample inference on the allocator metric ─────────────────────────


class AllocatorEvaluationError(ValueError):
    """A paired evaluation was asked for on streams that cannot support it."""


@dataclass(frozen=True)
class DeltaThetaInterval:
    """Percentile interval of ``delta_theta`` under one circular-block resample width."""

    block_length: int
    samples: int
    lower: float
    upper: float

    @property
    def excludes_zero(self) -> bool:
        """True when the interval sits wholly on one side of zero."""
        return self.lower > 0.0 or self.upper < 0.0


@dataclass(frozen=True)
class AllocatorContribution:
    """The convergent pole's verdict in the paired book: estimate, guard, and inference."""

    delta_theta: float
    downside_correlation: float
    intervals: tuple[DeltaThetaInterval, ...]

    @property
    def earns_its_seat(self) -> bool:
        """True when the pole adds certainty equivalent at every resample width.

        A positive point estimate alone is not a verdict on dependent streams, so this
        requires every block length's interval to exclude zero from above.
        """
        return self.delta_theta > 0.0 and all(interval.lower > 0.0 for interval in self.intervals)


def _flat_top_weight(x: float) -> float:
    """Politis-Romano (1995) flat-top lag window: 1, then a linear taper, then 0."""
    magnitude = abs(x)
    if magnitude < 0.5:
        return 1.0
    if magnitude <= 1.0:
        return 2.0 * (1.0 - magnitude)
    return 0.0


def optimal_block_length(series: np.ndarray) -> int:
    """Politis-White (2004) automatic block length for the CIRCULAR block bootstrap.

    Includes the Patton-Politis-White (2009) correction. Hand-picked calendar block lengths
    (a month, a quarter, six months) have no basis in the selection literature and can be
    badly wrong: Hall-Horowitz-Jing (1995) put the optimal length for a two-sided interval at
    order ``n**(1/3)``, which is about 12 at ``n = 1889``, so a six-month block is an order of
    magnitude too long and leaves only ~15 blocks to resample. Since
    :attr:`AllocatorContribution.earns_its_seat` requires *every* block length's interval to
    clear zero, the longest and most oversmoothed one silently binds the verdict.

    ``D`` uses the ``4/3`` circular-block constant, not the stationary bootstrap's ``2``.
    """
    n = series.size
    if n < _MIN_TAIL_WINDOWS:
        return 1
    centered = series - series.mean()
    variance = float(np.dot(centered, centered) / n)
    if not np.isfinite(variance) or variance <= 0.0:
        return 1

    consecutive = max(5, int(np.sqrt(np.log10(n))))
    max_lag = min(int(np.ceil(np.sqrt(n))) + consecutive, n - 1)

    def autocovariance(lag: int) -> float:
        span = abs(lag)
        return float(np.dot(centered[: n - span], centered[span:]) / n)

    correlations = np.array([autocovariance(k) / variance for k in range(1, max_lag + 1)])
    threshold = 2.0 * np.sqrt(np.log10(n) / n)
    insignificant = np.abs(correlations) < threshold

    # Smallest lag after which `consecutive` correlations are all inside the band.
    m_hat = 0
    for start in range(len(insignificant) - consecutive + 1):
        if insignificant[start : start + consecutive].all():
            m_hat = start + 1
            break
    else:  # no such run: fall back to the last lag still outside the band
        outside = np.flatnonzero(~insignificant)
        m_hat = int(outside[-1]) + 1 if outside.size else 1

    lag_window = min(2 * m_hat, max_lag)
    lags = np.arange(-lag_window, lag_window + 1)
    weights = np.array([_flat_top_weight(k / lag_window) for k in lags])
    covariances = np.array([autocovariance(int(k)) for k in lags])

    g_hat = float(np.sum(weights * np.abs(lags) * covariances))
    long_run_variance = float(np.sum(weights * covariances))
    d_hat = (4.0 / 3.0) * long_run_variance**2
    if not np.isfinite(g_hat) or not np.isfinite(d_hat) or d_hat <= 0.0 or g_hat == 0.0:
        return 1

    block = (2.0 * g_hat**2 / d_hat) ** (1.0 / 3.0) * n ** (1.0 / 3.0)
    ceiling = int(np.ceil(min(3.0 * np.sqrt(n), n / 3.0)))
    return int(np.clip(round(block), 1, ceiling))


def block_length_band(convergent_daily: np.ndarray, trend_daily: np.ndarray) -> tuple[int, ...]:
    """A sensitivity band bracketing the automatic selection: ``(b/2, b, 2b)``.

    The selector is univariate and no Politis-White extension to a paired statistic exists in
    the literature, so the longer of the two legs' selections is taken - conservative, since a
    longer block preserves more dependence, and chosen rather than derived. Politis and White
    warn against trusting the selector blindly, so the verdict is read across a bracket rather
    than a point.
    """
    selected = max(optimal_block_length(convergent_daily), optimal_block_length(trend_daily))
    return tuple(sorted({max(1, selected // 2), selected, selected * 2}))


def _circular_block_positions(
    observations: int, block_length: int, rng: np.random.Generator
) -> np.ndarray:
    """Indices of one circular-block resample, preserving runs of length ``block_length``."""
    block_count = int(np.ceil(observations / block_length))
    starts = rng.integers(0, observations, size=block_count)
    offsets = np.arange(block_length)
    return ((starts[:, None] + offsets) % observations).ravel()[:observations]


def _delta_theta_interval(
    convergent_daily: np.ndarray,
    trend_daily: np.ndarray,
    *,
    block_length: int,
    samples: int,
    rng: np.random.Generator,
    convergent_weight: float,
    rho: float,
    book_vol_annual: float,
) -> DeltaThetaInterval:
    """Resample both legs at the same positions, rescoring ``delta_theta`` on each draw.

    Positions are shared so the pair's contemporaneous dependence - the whole object
    ``delta_theta`` prices - survives resampling. Drawing the legs independently would
    destroy exactly the co-crash structure the metric exists to penalize.
    """
    deltas = np.empty(samples)
    for draw in range(samples):
        positions = _circular_block_positions(trend_daily.size, block_length, rng)
        deltas[draw] = composite_allocator_utility(
            convergent_daily[positions],
            trend_daily[positions],
            convergent_weight=convergent_weight,
            rho=rho,
            book_vol_annual=book_vol_annual,
        )
    finite = deltas[np.isfinite(deltas)]
    if finite.size == 0:
        return DeltaThetaInterval(block_length, samples, np.nan, np.nan)
    lower, upper = np.quantile(finite, _INTERVAL_QUANTILES)
    return DeltaThetaInterval(block_length, samples, float(lower), float(upper))


def evaluate_allocator_contribution(
    convergent_daily: np.ndarray,
    trend_daily: np.ndarray,
    *,
    convergent_weight: float = DEFAULT_CONVERGENT_WEIGHT,
    rho: float = DEFAULT_RISK_AVERSION,
    book_vol_annual: float = DEFAULT_BOOK_VOL,
    block_lengths: Sequence[int] | None = None,
    samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> AllocatorContribution:
    """Score a convergent candidate in the paired book, with resample-based inference.

    Takes two already-aligned daily net return streams and returns the allocator verdict:
    the ``delta_theta`` point estimate, the downside-correlation guard, and a percentile
    interval per block length. Callers own the alignment and the config-to-returns step;
    this function owns the paired statistics and nothing else, so a run, a notebook, and a
    CLI all reach the same answer through it.

    ``block_lengths`` defaults to :func:`block_length_band`, which selects from the streams'
    own dependence (Politis-White) rather than from the calendar. Pass an explicit sequence
    only to override that.
    """
    if convergent_daily.size != trend_daily.size:
        raise AllocatorEvaluationError(
            f"streams must be aligned: {convergent_daily.size} convergent "
            f"observations against {trend_daily.size} trend observations"
        )
    if block_lengths is None:
        block_lengths = block_length_band(convergent_daily, trend_daily)
    longest_block = max(block_lengths, default=0)
    if longest_block > trend_daily.size:
        raise AllocatorEvaluationError(
            f"block length {longest_block} exceeds {trend_daily.size} common observations"
        )
    rng = np.random.default_rng(seed)
    intervals = tuple(
        _delta_theta_interval(
            convergent_daily,
            trend_daily,
            block_length=block_length,
            samples=samples,
            rng=rng,
            convergent_weight=convergent_weight,
            rho=rho,
            book_vol_annual=book_vol_annual,
        )
        for block_length in block_lengths
    )
    return AllocatorContribution(
        delta_theta=composite_allocator_utility(
            convergent_daily,
            trend_daily,
            convergent_weight=convergent_weight,
            rho=rho,
            book_vol_annual=book_vol_annual,
        ),
        downside_correlation=downside_correlation(convergent_daily, trend_daily),
        intervals=intervals,
    )


# ── Post-hoc trust check ──────────────────────────────────────────────────────


def convergent_utility_rho_sensitivity_from_curve(
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
        rows[col] = {rho: _convergent_income_utility(stream, rho) for rho in rhos}
    return pd.DataFrame.from_dict(rows, orient="index")


# ── Registry records ──────────────────────────────────────────────────────────


def _make_stream_read(
    fn: Callable[[np.ndarray], float],
) -> Callable[[Any, ReportConfig], pd.Series]:
    def _read(pf: Any, config: ReportConfig) -> pd.Series:
        returns = EquityCurve.from_portfolio(pf).returns()
        return pd.Series({col: fn(returns[col].dropna().to_numpy()) for col in returns.columns})

    return _read


CONVERGENT_INCOME_UTILITY_DEFINITION = MetricDefinition(
    id=CONVERGENT_INCOME_UTILITY_ID,
    title=f"Convergent Income Utility (MPPM rho={DEFAULT_RISK_AVERSION:g}, certainty-equivalent growth)",
    source_type=SOURCE_TYPE_CUSTOM,
    unit="return",
    value_semantics=(
        "annualized certainty-equivalent excess growth for a crash-averse (CRRA) evaluator; "
        "manipulation-proof (higher = more income net of the tail it hides)"
    ),
    boundary_semantics="block_local",
    provider="aegis",
    target="portfolio",
    source_method="get_value",
    required_report_output=False,
    required_gate_input=False,
    metadata={"risk_aversion": DEFAULT_RISK_AVERSION, "risk_free": 0.0},
)
CONVERGENT_INCOME_UTILITY_EXTRACTOR = ExtractorSpec(
    _make_stream_read(_convergent_income_utility), contract_version=1
)

CONVERGENT_TAIL_BUDGET_DEFINITION = MetricDefinition(
    id=CONVERGENT_TAIL_BUDGET_ID,
    title="Convergent Tail Budget (actual left-decile loss, 2-6mo band)",
    source_type=SOURCE_TYPE_CUSTOM,
    unit="return",
    value_semantics=(
        "actual mean loss in the worst decile of overlapping 2-6 month own returns; "
        "the sleeve's budgeted bleed (closer to zero = shallower tail)"
    ),
    boundary_semantics="block_local",
    provider="aegis",
    target="portfolio",
    source_method="get_value",
    required_report_output=False,
    required_gate_input=False,
    metadata={"horizon_band_days": list(_HORIZON_BAND), "tail_quantile": _TAIL_QUANTILE},
)
CONVERGENT_TAIL_BUDGET_EXTRACTOR = ExtractorSpec(
    _make_stream_read(_convergent_tail_budget), contract_version=1
)

CONVERGENT_DOWNSIDE_LSKEW_DEFINITION = MetricDefinition(
    id=CONVERGENT_DOWNSIDE_LSKEW_ID,
    title="Convergent Downside L-Skew (robust L-moment skew, 2-6mo band)",
    source_type=SOURCE_TYPE_CUSTOM,
    unit="ratio",
    value_semantics=(
        "robust L-moment skewness (tau_3) of overlapping 2-6 month own returns; "
        "the realized sample shape report (negative = observed left asymmetry)"
    ),
    boundary_semantics="block_local",
    provider="aegis",
    target="portfolio",
    source_method="get_value",
    required_report_output=False,
    required_gate_input=False,
    metadata={"horizon_band_days": list(_HORIZON_BAND), "estimator": "l_moment_tau3"},
)
CONVERGENT_DOWNSIDE_LSKEW_EXTRACTOR = ExtractorSpec(
    _make_stream_read(_convergent_downside_lskew), contract_version=1
)


__all__ = [
    "CONVERGENT_DOWNSIDE_LSKEW_DEFINITION",
    "CONVERGENT_DOWNSIDE_LSKEW_EXTRACTOR",
    "CONVERGENT_DOWNSIDE_LSKEW_ID",
    "CONVERGENT_INCOME_UTILITY_DEFINITION",
    "CONVERGENT_INCOME_UTILITY_EXTRACTOR",
    "CONVERGENT_INCOME_UTILITY_ID",
    "CONVERGENT_TAIL_BUDGET_DEFINITION",
    "CONVERGENT_TAIL_BUDGET_EXTRACTOR",
    "CONVERGENT_TAIL_BUDGET_ID",
    "DEFAULT_BLOCK_LENGTHS",
    "DEFAULT_BOOK_VOL",
    "DEFAULT_BOOTSTRAP_SAMPLES",
    "DEFAULT_BOOTSTRAP_SEED",
    "DEFAULT_CONVERGENT_WEIGHT",
    "DEFAULT_RISK_AVERSION",
    "AllocatorContribution",
    "AllocatorEvaluationError",
    "DeltaThetaInterval",
    "block_length_band",
    "composite_allocator_utility",
    "composite_book_utility",
    "convergent_utility_rho_sensitivity_from_curve",
    "downside_correlation",
    "evaluate_allocator_contribution",
    "optimal_block_length",
]
