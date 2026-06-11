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
Each metric reads the benchmark from the batch's own close panel — no input
beyond what the portfolio already carries — and returns a per-group Series, the
same record shape the built-in extractors use.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from research.aegis_research.component_registry.contracts import SYMBOL_LEVEL
from research.aegis_research.configuration import ReportConfig
from research.aegis_research.metrics.contracts import (
    SOURCE_TYPE_CUSTOM,
    ExtractorSpec,
    MetricDefinition,
)

DEFAULT_BENCHMARK = "SPY"

# Tail/regime partition points (verifying-strategy-family-membership).
_WORST_DECILE = 0.10
_BEAR_PCTILE = 0.16
_QUARTER = "QE"

QUARTERLY_SKEW_ID = "quarterly_skew"
TM_CONVEXITY_ID = "tm_convexity_beta2"
TM_LINEAR_BETA_ID = "tm_linear_beta1"
CRISIS_CONDITIONAL_RETURN_ID = "crisis_conditional_return"
BEAR_REGIME_BETA_ID = "bear_regime_beta"


# ── Shared read of (stream returns, benchmark returns) per group ──────────────

def _stream_and_benchmark(pf: Any, benchmark: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-group daily returns of the stream and of the benchmark.

    Mirrors the capture metrics: the benchmark is the batch's own benchmark
    close per group (identical content across groups, aligned to the value
    frame's columns), so the read needs nothing beyond the portfolio.
    """
    value = pf.get_value()
    if isinstance(value, pd.Series):
        value = value.to_frame()
    benchmark_close = pf.close.xs(benchmark, level=SYMBOL_LEVEL, axis=1)
    benchmark_close.columns = value.columns
    return value.pct_change(), benchmark_close.pct_change()


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
            _definition(QUARTERLY_SKEW_ID, "Quarterly Own-Return Skew", "skew",
                        "quarterly_return_skewness", benchmark),
            ExtractorSpec(_make_quarterly_skew_read(benchmark)),
        ),
        (
            _definition(TM_CONVEXITY_ID, f"Treynor-Mazuy Convexity beta_2 vs {benchmark}",
                        "coefficient", "standardized_quadratic_convexity", benchmark),
            ExtractorSpec(_make_tm_read(benchmark, which=1)),
        ),
        (
            _definition(TM_LINEAR_BETA_ID, f"Treynor-Mazuy Linear beta_1 vs {benchmark}",
                        "coefficient", "standardized_linear_beta", benchmark),
            ExtractorSpec(_make_tm_read(benchmark, which=0)),
        ),
        (
            _definition(CRISIS_CONDITIONAL_RETURN_ID,
                        f"Crisis-Conditional Return ({benchmark} worst decile)",
                        "return", "crisis_conditional_mean_return", benchmark),
            ExtractorSpec(_make_crisis_conditional_read(benchmark)),
        ),
        (
            _definition(BEAR_REGIME_BETA_ID, f"Bear-Regime Beta vs {benchmark}",
                        "beta", "bear_regime_conditional_beta", benchmark),
            ExtractorSpec(_make_bear_regime_beta_read(benchmark)),
        ),
    ]


__all__ = [
    "BEAR_REGIME_BETA_ID",
    "CRISIS_CONDITIONAL_RETURN_ID",
    "DEFAULT_BENCHMARK",
    "QUARTERLY_SKEW_ID",
    "TM_CONVEXITY_ID",
    "TM_LINEAR_BETA_ID",
    "convexity_metrics",
]
