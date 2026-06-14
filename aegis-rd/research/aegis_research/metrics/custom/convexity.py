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

# Metric ids name the behaviour each measures, not the estimator that computes it
# (a Treynor-Mazuy regression yields market_convexity + market_beta; the regression
# is an implementation detail, not the name).
QUARTERLY_RETURN_SKEW_ID = "quarterly_return_skew"
MARKET_CONVEXITY_ID = "market_convexity"
MARKET_BETA_ID = "market_beta"
CRASH_DAY_RETURN_ID = "crash_day_return"
BEAR_MARKET_BETA_ID = "bear_market_beta"


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
    """Per-group daily returns of the stream and of the benchmark, from one read.

    The benchmark is read from the traded close panel when present, else pulled lazily and
    aligned; an unavailable benchmark yields NaN returns so the benchmark-relative reducers
    degrade to NaN rather than failing the run.
    """
    curve = EquityCurve.from_portfolio(pf)
    if curve.has_symbol(benchmark):
        return curve.returns(), curve.benchmark_returns(benchmark)
    try:
        close = _lazy_benchmark_close(benchmark, curve.value.index)
    except Exception:
        close = pd.Series(np.nan, index=curve.value.index)
    return curve.returns(), curve.aligned_benchmark_returns(close)


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


def _make_bear_regime_beta_read(benchmark: str) -> Callable[[Any, ReportConfig], pd.Series]:
    def _read(pf: Any, config: ReportConfig) -> pd.Series:
        returns, bench = _stream_and_benchmark(pf, benchmark)
        return _per_column(returns, bench, _bear_beta)

    return _read


# ── Registry records, parameterised by benchmark ──────────────────────────────

def _definition(metric_id: str, title: str, unit: str, semantics: str, benchmark: str) -> MetricDefinition:
    return MetricDefinition(
        id=metric_id,
        title=title,
        source_type=SOURCE_TYPE_CUSTOM,
        unit=unit,
        value_semantics=semantics,
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
            _definition(QUARTERLY_RETURN_SKEW_ID, "Quarterly Return Skew", "skew",
                        "are the big quarters gains (right tail) or losses (left)?", benchmark),
            ExtractorSpec(_make_quarterly_skew_read(benchmark)),
        ),
        (
            _definition(MARKET_CONVEXITY_ID, f"Market Convexity vs {benchmark}",
                        "coefficient", "does it gain more on big moves either way? (Treynor-Mazuy beta_2)", benchmark),
            ExtractorSpec(_make_tm_read(benchmark, which=1)),
        ),
        (
            _definition(MARKET_BETA_ID, f"Market Beta vs {benchmark}",
                        "coefficient", "net directional exposure to the market (Treynor-Mazuy beta_1)", benchmark),
            ExtractorSpec(_make_tm_read(benchmark, which=0)),
        ),
        (
            _definition(CRASH_DAY_RETURN_ID,
                        f"Crash-Day Return ({benchmark} worst decile)",
                        "return", "average return on the market's worst days", benchmark),
            ExtractorSpec(_make_crisis_conditional_read(benchmark)),
        ),
        (
            _definition(BEAR_MARKET_BETA_ID, f"Bear-Market Beta vs {benchmark}",
                        "beta", "exposure specifically in down regimes", benchmark),
            ExtractorSpec(_make_bear_regime_beta_read(benchmark)),
        ),
    ]


__all__ = [
    "BEAR_MARKET_BETA_ID",
    "CRASH_DAY_RETURN_ID",
    "DEFAULT_BENCHMARK",
    "MARKET_BETA_ID",
    "MARKET_CONVEXITY_ID",
    "QUARTERLY_RETURN_SKEW_ID",
    "convexity_metrics",
]
