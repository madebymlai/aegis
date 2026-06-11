"""Conditional Drawdown at Risk ratio — the UPI robustness cross-check.

CDaR at level alpha is the mean of the worst (1 - alpha) fraction of drawdown
observations (Chekhlov, Uryasev & Zabarankin 2005): alpha near 0 gives average
drawdown, alpha near 1 collapses onto the single-path maximum drawdown. The
measuring-crisis-alpha research places the robust ranking middle at moderate
alpha, so this Metric fixes alpha at 0.2 and ranks on annualized return over
CDaR. Higher is better, matching the ranking loop's descending sort.
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

CDAR_RATIO_ID = "cdar_ratio"

_CDAR_ALPHA = 0.2

CDAR_RATIO_DEFINITION = MetricDefinition(
    id=CDAR_RATIO_ID,
    title="CDaR Ratio (alpha 0.2)",
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


def _read_cdar_ratio(pf: Any, config: ReportConfig) -> pd.Series:
    """Annualized return over CDaR(0.2), per group, from one value read.

    Everything derives from the single ``get_value`` accessor call so the
    extractor honours the one-read-per-batch contract. A flat equity curve
    (zero CDaR) yields NaN, the same not-rankable signal as an all-cash
    Sharpe.
    """
    value = pf.get_value()
    if isinstance(value, pd.Series):
        value = value.to_frame()

    losses = 1.0 - value / value.cummax()
    tail_threshold = losses.quantile(_CDAR_ALPHA)
    cdar = losses.where(losses.ge(tail_threshold, axis=1)).mean()

    growth = value.iloc[-1] / value.iloc[0]
    annualized = growth ** (config.periods_per_year / len(value)) - 1.0

    return annualized / cdar.replace(0.0, np.nan)


CDAR_RATIO_EXTRACTOR = ExtractorSpec(_read_cdar_ratio)

__all__ = [
    "CDAR_RATIO_DEFINITION",
    "CDAR_RATIO_EXTRACTOR",
    "CDAR_RATIO_ID",
]
