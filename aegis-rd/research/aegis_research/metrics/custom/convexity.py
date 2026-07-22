"""Convexity-axis verification metrics (verifying-strategy-family-membership).

Five benchmark-relative metrics place a candidate's frozen return stream on
the convexity axis, so a sleeve earns its label from realized behaviour
rather than its mechanism declaration:

1. **Quarterly own-return skew** — convex sleeves are right-skewed; trend's
   long-gamma payoff accumulates over a move and only emerges at quarterly
   horizon, so skew is measured on quarterly-compounded returns.
2. **Treynor-Mazuy quadratic convexity** — regress the stream on the
   standardized benchmark and its square; the squared coefficient ``beta_2`` is
   convexity (a positive "smile"), the linear coefficient ``beta_1`` the
   directional beta. Standardizing the benchmark by its own vol makes ``beta_2``
   scale-invariant.
3. **Crisis-conditional return** — mean stream return on the benchmark's
   worst-decile days; isolates tail behaviour from the calm-dominated average.
4. **Bear-regime beta** — local benchmark beta when the benchmark is below its
   16th percentile; a defensive sleeve translates benchmark losses into gains.
5. **Crisis-conditional return** — the same crisis-conditional idea measured at the
   multi-month *horizon* the trend payoff develops over (Fung-Hsieh 2001), not the
   day: a genuinely convex slow-crisis sleeve co-crashes on the benchmark's worst
   *days* (metric 3 reads negative: trend lags a fast shock) yet pays over the worst
   *quarters* (this reads positive: 2022-style grinds). To be a number worth trusting
   it is *stabilized*: the downside conditioning is smooth (weight by the benchmark
   window's shortfall below its mean - no worst-quantile cutoff to choose) and the
   payoff is averaged over a band of multi-month horizons (no single-window choice),
   each annualized to a common scale. Smoothing removes the threshold knob and the
   band-average removes the horizon knob; together they cut the design-choice spread
   several-fold. The residual magnitude uncertainty (a typical sample holds only a
   couple of crises) is irreducible and is reported post-hoc as a block-bootstrap CI
   (``crisis_payoff_bootstrap_ci_from_curve``); so the engine ranks on this point
   estimate (a low-variance conditional mean, far more split-stable than a
   third-moment skew) and the interval is the trust check.

The benchmark is a **parameter**, not a constant: SPY is the dominant macro
factor in our ten-ETF universe, but the conditional signatures move with the
choice (swap SPY for a 60/40 proxy and crisis-conditional + regime-beta change),
so the benchmark symbol is closed over by a factory and recorded in metadata.

Convexity is benchmark-relative *by definition* (the Treynor-Mazuy beta_2 is the
loading on the benchmark's square; there is no benchmark-free convexity - the
intrinsic axis is skew, metric 1). So the benchmark need not be a *traded* symbol:
if it is in the batch's close panel it is read from there, otherwise it is pulled
lazily over the portfolio's own date span and aligned (cached per span). That keeps
the equity reference without forcing SPY into every strategy's universe - none of the
non-equity sleeves hold it - and degrades to NaN (not an error) if it cannot be
sourced. The intrinsic skew metric needs no benchmark at all.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from research.aegis_research.configuration import ReportConfig
from research.aegis_research.metrics.contracts import (
    SOURCE_TYPE_CUSTOM,
    ExtractorSpec,
    MetricDefinition,
)
from research.aegis_research.metrics.custom.support import EquityCurve

DEFAULT_BENCHMARK = "SPY"

# Tail/regime partition points (verifying-strategy-family-membership).
_WORST_DECILE = 0.10
_BEAR_PCTILE = 0.16
_QUARTER = "QE"
# Crisis-conditional payoff design ("how to stabilize it"). The payoff is averaged over a band of
# multi-month horizons (trading days): averaging removes the single-horizon knob, and every horizon is
# kept short enough to survive a one-year split (max < 252). The annualization base puts the
# differently-sized horizons on one per-year scale before they are averaged.
_HORIZON_BAND = (42, 63, 84, 126)
_ANNUALIZATION_DAYS = 252.0
# Benchmark-free convexity payoff: the net decile tail of overlapping multi-month own-returns — the
# right tail the sleeve is hired to grow vs the left tail it must keep shallow. A window floor keeps the
# decile means stable on a finite Development path.
_TAIL_QUANTILE = 0.10
_MIN_TAIL_WINDOWS = 30

# Metric ids name the behaviour each measures, not the estimator that computes it
# (a Treynor-Mazuy regression yields market_convexity + market_beta; the regression
# is an implementation detail, not the name).
QUARTERLY_RETURN_SKEW_ID = "quarterly_return_skew"
MARKET_CONVEXITY_ID = "market_convexity"
MARKET_BETA_ID = "market_beta"
CRASH_DAY_RETURN_ID = "crash_day_return"
CRISIS_QUARTER_RETURN_ID = "crisis_quarter_return"
BEAR_MARKET_BETA_ID = "bear_market_beta"
TREND_CONVEXITY_PAYOFF_ID = "trend_convexity_payoff"


# ── Shared read of (stream returns, benchmark returns) per group ──────────────

# Benchmark close cached per (symbol, span) so the three benchmark-relative metrics share
# one lazy pull per batch rather than re-fetching.
_BENCHMARK_CACHE: dict[tuple[str, str, str], pd.Series] = {}


def _lazy_benchmark_close(symbol: str, index: pd.DatetimeIndex) -> pd.Series:
    """Pull the benchmark close over the portfolio's own span, tz-conformed to the target index.

    Only used when the benchmark is not a traded column: convexity is benchmark-relative by
    definition, so the reference is sourced on demand rather than required in the universe.

    The pulled close is normalized to calendar dates and then conformed to ``index``'s tz, which
    is the portfolio value index it will be reindexed onto downstream
    (``EquityCurve.aligned_benchmark_returns``). yf-sourced panels carry a tz-aware (UTC) index, so
    a tz-naive benchmark would reindex to all-NaN — silently NaN-ing every benchmark-relative
    metric. Matching the tz keeps the alignment real.
    """
    key = (symbol, str(index.min()), str(index.max()))
    if key not in _BENCHMARK_CACHE:
        from vectorbtpro import vbt

        close = vbt.YFData.pull(
            symbol, start=index.min(), end=index.max() + pd.Timedelta(days=1)
        ).get("Close")
        if isinstance(close.index, pd.DatetimeIndex) and close.index.tz is not None:
            close.index = close.index.tz_localize(None)
        close.index = close.index.normalize()
        if index.tz is not None:
            close.index = close.index.tz_localize(index.tz)
        _BENCHMARK_CACHE[key] = close
    return _BENCHMARK_CACHE[key]


def _stream_and_benchmark(pf: Any, benchmark: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-group daily returns of the stream and of the benchmark, from one read."""
    return _stream_and_benchmark_from_curve(EquityCurve.from_portfolio(pf), benchmark)


def _stream_and_benchmark_from_curve(
    curve: EquityCurve, benchmark: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stream and benchmark daily returns from an already-read curve (the shared-read path).

    The benchmark is read from the traded close panel when present, else pulled lazily and aligned; an
    unavailable benchmark yields NaN returns so the benchmark-relative reducers degrade to NaN rather
    than failing the run. Taking the curve (instead of the portfolio) lets a composite Metric share one
    ``get_value`` read across several benchmark-relative statistics.
    """
    if curve.has_symbol(benchmark):
        return curve.returns(), curve.benchmark_returns(benchmark)
    try:
        close = _lazy_benchmark_close(benchmark, curve.value.index)
    except Exception:
        close = pd.Series(np.nan, index=curve.value.index)
    return curve.returns(), curve.aligned_benchmark_returns(close)


_BOOTSTRAP_SEED = 0
_BOOTSTRAP_DRAWS = 500


def _crisis_payoff_bootstrap_ci(
    stream: np.ndarray, bench: np.ndarray, *, lower: float, upper: float
) -> tuple[float, float]:
    """Stationary block-bootstrap CI for the band-averaged crisis-conditional payoff.

    Overlapping multi-month windows are heavily autocorrelated, so a naive standard error understates
    the uncertainty; resampling contiguous blocks (length = the longest horizon) preserves that
    dependence. With only a couple of crises in a typical sample the interval is honestly wide, and that
    width is the irreducible uncertainty the point estimate hides. Seeded, so the bound is deterministic.
    """
    n = stream.size
    block = max(_HORIZON_BAND)
    if n < block:
        return np.nan, np.nan
    rng = np.random.default_rng(_BOOTSTRAP_SEED)
    n_blocks = int(np.ceil(n / block))
    draws = np.empty(_BOOTSTRAP_DRAWS)
    for d in range(_BOOTSTRAP_DRAWS):
        starts = rng.integers(0, n - block + 1, n_blocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        draws[d] = _crisis_quarter_return(stream[idx], bench[idx])
    return float(np.nanpercentile(draws, lower * 100.0)), float(
        np.nanpercentile(draws, upper * 100.0)
    )


def crisis_payoff_bootstrap_ci_from_curve(
    curve: EquityCurve, benchmark: str, *, lower: float = 0.05, upper: float = 0.95
) -> pd.DataFrame:
    """Per-group (lower, upper) block-bootstrap CI of the crisis-conditional payoff, from one read.

    Post-hoc trust / shortlist-ranking aid (the "rank on a lower confidence bound" option from
    [[measuring-crisis-alpha]]): too heavy to compute per Candidate per Observation Block, but the right way to
    rank a final shortlist of locked candidates - a positive payoff resting on one lucky crisis is
    shrunk toward its (wide) lower bound. Returns a frame indexed by group with ``lower``/``upper`` columns.
    """
    returns, bench = _stream_and_benchmark_from_curve(curve, benchmark)
    rows: dict[Any, tuple[float, float]] = {}
    for col in returns.columns:
        pair = pd.concat([returns[col], bench[col]], axis=1).dropna()
        if len(pair) < max(_HORIZON_BAND):
            rows[col] = (np.nan, np.nan)
            continue
        rows[col] = _crisis_payoff_bootstrap_ci(
            pair.iloc[:, 0].to_numpy(), pair.iloc[:, 1].to_numpy(), lower=lower, upper=upper
        )
    return pd.DataFrame.from_dict(rows, orient="index", columns=["lower", "upper"])


def _per_column(
    returns: pd.DataFrame,
    benchmark: pd.DataFrame,
    fn: Callable[[np.ndarray, np.ndarray], float],
) -> pd.Series:
    """Apply a (stream, benchmark) -> float reducer to each group, NaN-dropping pairwise."""
    out: dict[Any, float] = {}
    for col in returns.columns:
        pair = pd.concat([returns[col], benchmark[col]], axis=1).dropna()
        if len(pair) < 3:
            out[col] = np.nan
            continue
        out[col] = fn(pair.iloc[:, 0].to_numpy(), pair.iloc[:, 1].to_numpy())
    return pd.Series(out)


# ── Signature reducers ────────────────────────────────────────────────────────


def _tm_betas(stream: np.ndarray, bench: np.ndarray) -> tuple[float, float]:
    """Treynor-Mazuy (raw market beta_1, scale-invariant convexity beta_2).

    Regress R = a + c1*x + c2*x^2 on the standardized benchmark x = bench/std(bench).
    ``beta_2 = c2`` is the convexity coefficient, kept on the standardized scale so it
    is comparable across assets and frequencies (the vault's requirement). The linear
    term is returned as the *raw* market beta ``beta_1 = c1/std(bench)`` so it matches
    the per-family thresholds, which are dimensionless market betas (trend low ~[-0.1,
    0.1]; carry moderate-positive >= 0.20), not return-per-standard-deviation slopes.
    """
    sd = bench.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return np.nan, np.nan
    x = bench / sd
    design = np.column_stack([np.ones_like(x), x, x * x])
    coef, *_ = np.linalg.lstsq(design, stream, rcond=None)
    return float(coef[1] / sd), float(coef[2])


def _bear_beta(stream: np.ndarray, bench: np.ndarray) -> float:
    """Local benchmark beta on bear days (benchmark below its 16th percentile)."""
    threshold = np.quantile(bench, _BEAR_PCTILE)
    mask = bench <= threshold
    if mask.sum() < 2:
        return np.nan
    cov = np.cov(stream[mask], bench[mask], ddof=1)
    var = cov[1, 1]
    return float(cov[0, 1] / var) if var > 0 else np.nan


def _crisis_conditional(stream: np.ndarray, bench: np.ndarray) -> float:
    """Mean stream return on the benchmark's worst-decile days."""
    threshold = np.quantile(bench, _WORST_DECILE)
    mask = bench <= threshold
    return float(stream[mask].mean()) if mask.any() else np.nan


def _rolling_compound(daily: np.ndarray, horizon: int) -> np.ndarray:
    """Overlapping ``horizon``-day compounded simple returns from a daily array.

    Window ending at ``t`` compounds days ``t-horizon+1 .. t``; computed as differences of
    cumulative log-growth so the whole overlapping series is one vectorised pass. Returns an
    empty array when there are fewer than ``horizon`` days (the caller degrades to NaN).
    """
    if daily.size < horizon:
        return np.empty(0)
    log_growth = np.cumsum(np.log1p(daily))
    windowed = log_growth[horizon - 1 :] - np.concatenate(([0.0], log_growth[:-horizon]))
    return np.expm1(windowed)


def _crisis_conditional_payoff(stream: np.ndarray, bench: np.ndarray, horizon: int) -> float:
    """Annualized downside-weighted mean stream return at one horizon (no hard threshold).

    Both series are compounded into overlapping ``horizon``-day windows; each window is weighted by the
    benchmark window's shortfall below its *mean* (``max(mean - b, 0)``), so the weight grows smoothly
    as the benchmark does worse and there is no quantile cutoff to choose (removing the threshold knob
    that made a single worst-quantile mean swing several-fold). The weighted-mean stream return is then
    annualized so horizons of different lengths share one scale before they are averaged.
    """
    stream_h = _rolling_compound(stream, horizon)
    bench_h = _rolling_compound(bench, horizon)
    if stream_h.size == 0 or bench_h.size == 0:
        return np.nan
    weight = np.maximum(bench_h.mean() - bench_h, 0.0)
    total = weight.sum()
    if total <= 0.0:
        return np.nan
    payoff = float((weight * stream_h).sum() / total)
    return (1.0 + payoff) ** (_ANNUALIZATION_DAYS / horizon) - 1.0


def _crisis_quarter_return(stream: np.ndarray, bench: np.ndarray) -> float:
    """Smooth, horizon-band-averaged annualized return when the benchmark does badly.

    The stabilized convexity signature: the downside conditioning is *smooth* (a mean-shortfall weight,
    not a worst-quantile cutoff) and the payoff is *averaged over a band of multi-month horizons*, each
    annualized to a common scale. Smoothing removes the threshold knob and the band-average removes the
    single-window knob; together they were validated to cut the design-choice spread several-fold versus
    a single-horizon worst-quintile mean. The residual magnitude uncertainty (a typical sample holds
    only a couple of crises) is irreducible and is reported, post-hoc, by
    ``crisis_payoff_bootstrap_ci_from_curve`` - so the engine ranks on this low-variance point estimate
    and the bootstrap interval is the trust check.
    """
    payoffs = [_crisis_conditional_payoff(stream, bench, h) for h in _HORIZON_BAND]
    finite = [p for p in payoffs if np.isfinite(p)]
    return float(np.mean(finite)) if finite else np.nan


# ── Benchmark-free convexity payoff (the trend-sleeve ranker) ─────────────────


def _net_tail_payoff(stream: np.ndarray, horizon: int) -> float:
    """Annualized (right-decile mean + left-decile mean) of overlapping ``horizon``-day own returns.

    The realized convex signature without a benchmark: a trend sleeve is hired to grow the right tail
    (dislocation gains) while keeping the left tail shallow (calm bleed), so the sum of the two decile
    means is positive exactly when "infrequent large gains compensate frequent small losses" (Sepp 2018;
    [[what-makes-a-trend-sleeve-convex]]). Magnitude-aware (unlike a normalized skew coefficient), so it
    cannot prefer a sharply-skewed but barely-trading book - the failure mode the roster note flags when
    a pole is ranked on skew without crisis capture. Annualized so the horizon band shares one scale.
    """
    windows = _rolling_compound(stream, horizon)
    if windows.size < _MIN_TAIL_WINDOWS:
        return np.nan
    lo, hi = np.quantile(windows, [_TAIL_QUANTILE, 1.0 - _TAIL_QUANTILE])
    right, left = windows[windows >= hi], windows[windows <= lo]
    if right.size == 0 or left.size == 0:
        return np.nan
    payoff = float(right.mean() + left.mean())
    return (1.0 + payoff) ** (_ANNUALIZATION_DAYS / horizon) - 1.0


def _trend_convexity_payoff(stream: np.ndarray) -> float:
    """Horizon-band-averaged net tail payoff — the benchmark-free convexity ranker.

    Mirrors ``crisis_quarter_return``'s two stabilizers (overlapping daily windows for a dense return
    distribution; a band-average over ~2-6 months to drop the single-horizon knob) but on the *intrinsic*
    skew axis, which needs no benchmark - so it ranks the convex shape on a catalog-only book where SPY
    cannot be sourced. Measured at the multi-month horizon the trend payoff develops over, never daily
    (the convexity is invisible below the trend half-life - Sepp 2018).
    """
    vals = [_net_tail_payoff(stream, h) for h in _HORIZON_BAND]
    finite = [v for v in vals if np.isfinite(v)]
    return float(np.mean(finite)) if finite else np.nan


def _make_trend_convexity_payoff_read() -> Callable[[Any, ReportConfig], pd.Series]:
    def _read(pf: Any, config: ReportConfig) -> pd.Series:
        returns = EquityCurve.from_portfolio(pf).returns()
        return pd.Series(
            {
                col: _trend_convexity_payoff(returns[col].dropna().to_numpy())
                for col in returns.columns
            }
        )

    return _read


TREND_CONVEXITY_PAYOFF_DEFINITION = MetricDefinition(
    id=TREND_CONVEXITY_PAYOFF_ID,
    title="Trend Convexity Payoff (net multi-month tail return, 2-6mo band)",
    source_type=SOURCE_TYPE_CUSTOM,
    unit="return",
    value_semantics=(
        "right-tail gain net of left-tail loss over overlapping 2-6 month windows; "
        "benchmark-free convexity (higher = lose-small / pay-big)"
    ),
    boundary_semantics="block_local",
    provider="aegis",
    target="portfolio",
    source_method="get_value",
    required_report_output=False,
    required_gate_input=False,
    metadata={"horizon_band_days": list(_HORIZON_BAND), "tail_quantile": _TAIL_QUANTILE},
)
TREND_CONVEXITY_PAYOFF_EXTRACTOR = ExtractorSpec(
    _make_trend_convexity_payoff_read(), contract_version=1
)


# ── Per-benchmark read factories ──────────────────────────────────────────────


def _make_quarterly_skew_read(benchmark: str) -> Callable[[Any, ReportConfig], pd.Series]:
    def _read(pf: Any, config: ReportConfig) -> pd.Series:
        returns, _ = _stream_and_benchmark(pf, benchmark)
        quarterly = (1.0 + returns).resample(_QUARTER).prod() - 1.0
        return quarterly.skew(axis=0)

    return _read


def _make_tm_read(benchmark: str, *, which: int) -> Callable[[Any, ReportConfig], pd.Series]:
    def _read(pf: Any, config: ReportConfig) -> pd.Series:
        returns, bench = _stream_and_benchmark(pf, benchmark)
        return _per_column(returns, bench, lambda s, b: _tm_betas(s, b)[which])

    return _read


def _make_crisis_conditional_read(benchmark: str) -> Callable[[Any, ReportConfig], pd.Series]:
    def _read(pf: Any, config: ReportConfig) -> pd.Series:
        returns, bench = _stream_and_benchmark(pf, benchmark)
        return _per_column(returns, bench, _crisis_conditional)

    return _read


def _make_crisis_quarter_read(benchmark: str) -> Callable[[Any, ReportConfig], pd.Series]:
    def _read(pf: Any, config: ReportConfig) -> pd.Series:
        returns, bench = _stream_and_benchmark(pf, benchmark)
        return _per_column(returns, bench, _crisis_quarter_return)

    return _read


def _make_bear_regime_beta_read(benchmark: str) -> Callable[[Any, ReportConfig], pd.Series]:
    def _read(pf: Any, config: ReportConfig) -> pd.Series:
        returns, bench = _stream_and_benchmark(pf, benchmark)
        return _per_column(returns, bench, _bear_beta)

    return _read


# ── Registry records, parameterised by benchmark ──────────────────────────────


def _definition(
    metric_id: str, title: str, unit: str, semantics: str, benchmark: str
) -> MetricDefinition:
    return MetricDefinition(
        id=metric_id,
        title=title,
        source_type=SOURCE_TYPE_CUSTOM,
        unit=unit,
        value_semantics=semantics,
        boundary_semantics="block_local",
        provider="aegis",
        target="portfolio",
        source_method="get_value",
        required_report_output=False,
        required_gate_input=False,
        metadata={"benchmark": benchmark},
    )


def convexity_metrics(
    benchmark: str = DEFAULT_BENCHMARK,
) -> list[tuple[MetricDefinition, ExtractorSpec]]:
    """The convexity-axis verification metrics as (definition, extractor) pairs for one benchmark."""
    return [
        (
            _definition(
                QUARTERLY_RETURN_SKEW_ID,
                "Quarterly Return Skew",
                "skew",
                "are the big quarters gains (right tail) or losses (left)?",
                benchmark,
            ),
            ExtractorSpec(_make_quarterly_skew_read(benchmark), contract_version=1),
        ),
        (
            _definition(
                MARKET_CONVEXITY_ID,
                f"Market Convexity vs {benchmark}",
                "coefficient",
                "does it gain more on big moves either way? (Treynor-Mazuy beta_2)",
                benchmark,
            ),
            ExtractorSpec(_make_tm_read(benchmark, which=1), contract_version=1),
        ),
        (
            _definition(
                MARKET_BETA_ID,
                f"Market Beta vs {benchmark}",
                "coefficient",
                "net directional exposure to the market (Treynor-Mazuy beta_1)",
                benchmark,
            ),
            ExtractorSpec(_make_tm_read(benchmark, which=0), contract_version=1),
        ),
        (
            _definition(
                CRASH_DAY_RETURN_ID,
                f"Crash-Day Return ({benchmark} worst decile)",
                "return",
                "average return on the market's worst days",
                benchmark,
            ),
            ExtractorSpec(_make_crisis_conditional_read(benchmark), contract_version=1),
        ),
        (
            _definition(
                CRISIS_QUARTER_RETURN_ID,
                f"Crisis-Conditional Return ({benchmark}, smooth downside, 2-6mo band)",
                "return",
                "annualized return when the benchmark does badly (smooth downside weight, horizon-band-averaged)",
                benchmark,
            ),
            ExtractorSpec(_make_crisis_quarter_read(benchmark), contract_version=1),
        ),
        (
            _definition(
                BEAR_MARKET_BETA_ID,
                f"Bear-Market Beta vs {benchmark}",
                "beta",
                "exposure specifically in down regimes",
                benchmark,
            ),
            ExtractorSpec(_make_bear_regime_beta_read(benchmark), contract_version=1),
        ),
    ]


__all__ = [
    "BEAR_MARKET_BETA_ID",
    "CRASH_DAY_RETURN_ID",
    "CRISIS_QUARTER_RETURN_ID",
    "DEFAULT_BENCHMARK",
    "MARKET_BETA_ID",
    "MARKET_CONVEXITY_ID",
    "QUARTERLY_RETURN_SKEW_ID",
    "TREND_CONVEXITY_PAYOFF_DEFINITION",
    "TREND_CONVEXITY_PAYOFF_EXTRACTOR",
    "TREND_CONVEXITY_PAYOFF_ID",
    "convexity_metrics",
    "crisis_payoff_bootstrap_ci_from_curve",
]
