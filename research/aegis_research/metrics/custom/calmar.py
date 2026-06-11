"""Calmar ratio — the pre-registered fragile negative control.

Annualized return over the absolute maximum drawdown. The measuring-crisis-alpha
research predicts this metric selects visibly more overfit candidates than the
robust drawdown-aware objectives (UPI, CDaR): its denominator is a single-path
order statistic whose sampling dispersion scales with track length, so one
episode dominates the ranking. Registered to *confirm* that failure mode on our
data, not to use.
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

CALMAR_RATIO_ID = "calmar_ratio"

CALMAR_RATIO_DEFINITION = MetricDefinition(
    id=CALMAR_RATIO_ID,
    title="Calmar Ratio",
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


def _read_calmar_ratio(pf: Any, config: ReportConfig) -> pd.Series:
    """Annualized return over |max drawdown|, per group, from one value read.

    A flat curve (zero drawdown) yields NaN — not rankable, the same signal
    as an all-cash Sharpe.
    """
    value = pf.get_value()
    if isinstance(value, pd.Series):
        value = value.to_frame()

    drawdown = value / value.cummax() - 1.0
    max_drawdown = drawdown.min().abs()

    growth = value.iloc[-1] / value.iloc[0]
    annualized = growth ** (config.periods_per_year / len(value)) - 1.0

    return annualized / max_drawdown.replace(0.0, np.nan)


CALMAR_RATIO_EXTRACTOR = ExtractorSpec(_read_calmar_ratio)

__all__ = [
    "CALMAR_RATIO_DEFINITION",
    "CALMAR_RATIO_EXTRACTOR",
    "CALMAR_RATIO_ID",
]
