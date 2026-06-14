"""Benchmark-capture ranking Metrics — the crash-gain objectives.

From the measuring-crisis-alpha research: drawdown-aware objectives (UPI,
CDaR) reward smoothness and trade away crash-time gain; the allocator's true
objective is a sleeve that *gains* when the benchmark falls. Down-capture
(Morningstar form) measures exactly that — compounded sleeve return over
benchmark-down days divided by the compounded benchmark return over the same
days; below zero means the sleeve gained while the benchmark fell. It is
minimised, so the registered Metric is its negation (the ranking loop sorts
descending). The capture spread (up-capture minus down-capture) is the
less-degenerate variant: it additionally rewards keeping upside, penalising
the "smooth and dead" book that pure down-capture would accept.

Both read the portfolio value once and take the benchmark from the batch's
own close panel (the benchmark column per group), excluding near-zero
benchmark days (|b| < eps) where the ratio is unstable. The benchmark symbol
is a **parameter** (SPY is our universe's macro factor, not a constant): a
factory closes it over and records it in metadata, so the same capture Metric
works against any benchmark present in the run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from research.aegis_research.configuration import ReportConfig
from research.aegis_research.metrics.contracts import (
    SOURCE_TYPE_CUSTOM,
    ExtractorSpec,
    MetricDefinition,
)
from research.aegis_research.metrics.custom.support import EquityCurve

NEG_DOWN_CAPTURE_ID = "neg_down_capture"
CAPTURE_SPREAD_ID = "capture_spread"

DEFAULT_BENCHMARK = "SPY"
_EPSILON = 0.0005


def _captures(pf: Any, benchmark: str) -> tuple[pd.Series, pd.Series]:
    """Per-group (down_capture, up_capture) from one value read.

    The benchmark is the batch's own benchmark close per group (identical
    content across groups, aligned to the value frame's group columns), so the
    metric needs no data beyond what the portfolio already carries. A split with
    an empty up/down day set, or a near-zero compounded benchmark move, yields
    NaN — not rankable, same signal as an all-cash Sharpe.
    """
    curve = EquityCurve.from_portfolio(pf)
    benchmark_returns = curve.benchmark_returns(benchmark)
    returns = curve.returns()

    def _compounded(mask: pd.DataFrame, frame: pd.DataFrame) -> pd.Series:
        return (1.0 + frame.where(mask, 0.0)).prod() - 1.0

    down = benchmark_returns < -_EPSILON
    up = benchmark_returns > _EPSILON
    down_bench = _compounded(down, benchmark_returns).where(down.any())
    up_bench = _compounded(up, benchmark_returns).where(up.any())

    down_capture = _compounded(down, returns) / down_bench.where(down_bench.abs() > _EPSILON)
    up_capture = _compounded(up, returns) / up_bench.where(up_bench.abs() > _EPSILON)
    return down_capture, up_capture


def _make_neg_down_capture_read(benchmark: str) -> Callable[[Any, ReportConfig], pd.Series]:
    def _read(pf: Any, config: ReportConfig) -> pd.Series:
        """Negated down-capture: positive when the sleeve gains as the benchmark falls."""
        down_capture, _ = _captures(pf, benchmark)
        return -down_capture

    return _read


def _make_capture_spread_read(benchmark: str) -> Callable[[Any, ReportConfig], pd.Series]:
    def _read(pf: Any, config: ReportConfig) -> pd.Series:
        """Up-capture minus down-capture: rewards upside kept plus downside escaped."""
        down_capture, up_capture = _captures(pf, benchmark)
        return up_capture - down_capture

    return _read


def _definition(metric_id: str, title: str, benchmark: str) -> MetricDefinition:
    return MetricDefinition(
        id=metric_id,
        title=title,
        source_type=SOURCE_TYPE_CUSTOM,
        unit="ratio",
        value_semantics="benchmark_capture_ratio",
        provider="aegis",
        target="portfolio",
        source_method="get_value",
        required_report_output=False,
        required_gate_input=False,
        metadata={"benchmark": benchmark},
    )


def capture_metrics(
    benchmark: str = DEFAULT_BENCHMARK,
) -> list[tuple[MetricDefinition, ExtractorSpec]]:
    """The benchmark-capture Metrics as (definition, extractor) pairs for one benchmark."""
    return [
        (
            _definition(NEG_DOWN_CAPTURE_ID, f"Negated {benchmark} Down-Capture", benchmark),
            ExtractorSpec(_make_neg_down_capture_read(benchmark)),
        ),
        (
            _definition(CAPTURE_SPREAD_ID, f"{benchmark} Capture Spread (up minus down)", benchmark),
            ExtractorSpec(_make_capture_spread_read(benchmark)),
        ),
    ]


__all__ = [
    "CAPTURE_SPREAD_ID",
    "DEFAULT_BENCHMARK",
    "NEG_DOWN_CAPTURE_ID",
    "capture_metrics",
]
