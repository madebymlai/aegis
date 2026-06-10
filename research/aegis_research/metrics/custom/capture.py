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
own close panel (the SPY column per group), excluding near-zero benchmark
days (|b| < eps) where the ratio is unstable.
"""

from __future__ import annotations

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

NEG_DOWN_CAPTURE_ID = "neg_down_capture"
CAPTURE_SPREAD_ID = "capture_spread"

_BENCHMARK_SYMBOL = "SPY"
_EPSILON = 0.0005

NEG_DOWN_CAPTURE_DEFINITION = MetricDefinition(
    id=NEG_DOWN_CAPTURE_ID,
    title="Negated SPY Down-Capture",
    source_type=SOURCE_TYPE_CUSTOM,
    unit="ratio",
    value_semantics="benchmark_capture_ratio",
    provider="aegis",
    target="portfolio",
    source_method="get_value",
    required_report_output=False,
    required_gate_input=False,
)

CAPTURE_SPREAD_DEFINITION = MetricDefinition(
    id=CAPTURE_SPREAD_ID,
    title="SPY Capture Spread (up minus down)",
    source_type=SOURCE_TYPE_CUSTOM,
    unit="ratio",
    value_semantics="benchmark_capture_ratio",
    provider="aegis",
    target="portfolio",
    source_method="get_value",
    required_report_output=False,
    required_gate_input=False,
)


def _captures(pf: Any) -> tuple[pd.Series, pd.Series]:
    """Per-group (down_capture, up_capture) from one value read.

    The benchmark is the batch's own SPY close per group (identical content
    across groups, aligned to the value frame's group columns), so the metric
    needs no data beyond what the portfolio already carries. A split with an
    empty up/down day set, or a near-zero compounded benchmark move, yields
    NaN — not rankable, same signal as an all-cash Sharpe.
    """
    value = pf.get_value()
    if isinstance(value, pd.Series):
        value = value.to_frame()

    benchmark_close = pf.close.xs(_BENCHMARK_SYMBOL, level=SYMBOL_LEVEL, axis=1)
    benchmark_close.columns = value.columns
    benchmark = benchmark_close.pct_change()
    returns = value.pct_change()

    def _compounded(mask: pd.DataFrame, frame: pd.DataFrame) -> pd.Series:
        return (1.0 + frame.where(mask, 0.0)).prod() - 1.0

    down = benchmark < -_EPSILON
    up = benchmark > _EPSILON
    down_bench = _compounded(down, benchmark).where(down.any())
    up_bench = _compounded(up, benchmark).where(up.any())

    down_capture = _compounded(down, returns) / down_bench.where(down_bench.abs() > _EPSILON)
    up_capture = _compounded(up, returns) / up_bench.where(up_bench.abs() > _EPSILON)
    return down_capture, up_capture


def _read_neg_down_capture(pf: Any, config: ReportConfig) -> pd.Series:
    """Negated down-capture: positive when the sleeve gains as SPY falls."""
    down_capture, _ = _captures(pf)
    return -down_capture


def _read_capture_spread(pf: Any, config: ReportConfig) -> pd.Series:
    """Up-capture minus down-capture: rewards upside kept plus downside escaped."""
    down_capture, up_capture = _captures(pf)
    return up_capture - down_capture


NEG_DOWN_CAPTURE_EXTRACTOR = ExtractorSpec(_read_neg_down_capture)
CAPTURE_SPREAD_EXTRACTOR = ExtractorSpec(_read_capture_spread)

__all__ = [
    "CAPTURE_SPREAD_DEFINITION",
    "CAPTURE_SPREAD_EXTRACTOR",
    "CAPTURE_SPREAD_ID",
    "NEG_DOWN_CAPTURE_DEFINITION",
    "NEG_DOWN_CAPTURE_EXTRACTOR",
    "NEG_DOWN_CAPTURE_ID",
]
