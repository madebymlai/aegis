"""Ulcer Performance Index — drawdown-aware ranking Metric.

The Ulcer Index is the root-mean-square of percentage drawdowns from the
running peak, penalising both depth and duration underwater; the Ulcer
Performance Index (Martin ratio) divides annualized return by it. It is the
robust stress-aware ranking objective from the measuring-crisis-alpha
research: it integrates the whole equity curve (many observations, no
arbitrary threshold) instead of collapsing onto the single worst episode the
way Calmar or a one-window crisis return does. Higher is better, matching the
ranking loop's descending sort.
"""

from __future__ import annotations

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

ULCER_PERFORMANCE_INDEX_ID = "ulcer_performance_index"

ULCER_PERFORMANCE_INDEX_DEFINITION = MetricDefinition(
    id=ULCER_PERFORMANCE_INDEX_ID,
    title="Ulcer Performance Index",
    source_type=SOURCE_TYPE_CUSTOM,
    unit="ratio",
    value_semantics="risk_adjusted_return_ratio",
    required_inputs=("frequency", "year_frequency"),
    provider="aegis",
    target="portfolio",
    source_method="get_value",
    required_report_output=False,
    required_gate_input=False,
)


def _read_ulcer_performance_index(pf: Any, config: ReportConfig) -> pd.Series:
    """Annualized return over the Ulcer Index, per group, from one value read.

    Everything derives from the single ``get_value`` accessor call so the
    extractor honours the one-read-per-batch contract. A flat equity curve
    (zero Ulcer Index) yields NaN, the same not-rankable signal as an
    all-cash Sharpe.
    """
    curve = EquityCurve.from_portfolio(pf)
    drawdown = curve.drawdown_curve()
    ulcer = np.sqrt((drawdown**2).mean())
    annualized = curve.annualized_return(config.periods_per_year)
    return annualized / ulcer.replace(0.0, np.nan)


ULCER_PERFORMANCE_INDEX_EXTRACTOR = ExtractorSpec(_read_ulcer_performance_index)

__all__ = [
    "ULCER_PERFORMANCE_INDEX_DEFINITION",
    "ULCER_PERFORMANCE_INDEX_EXTRACTOR",
    "ULCER_PERFORMANCE_INDEX_ID",
]
