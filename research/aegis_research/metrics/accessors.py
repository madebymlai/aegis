from __future__ import annotations

import math
from typing import Any

import pandas as pd

from research.aegis_research.configuration.schema import ReportConfig
from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS

METRIC_INDEX_NAME = "metric_name"


def central_metrics_from_accessors(pf: Any, config: ReportConfig) -> pd.Series:
    raw = {
        "total_return": _pct(_scalar(pf.get_total_return())),
        "max_dd": _pct(abs(_scalar(pf.get_max_drawdown()))),
        "total_trades": _scalar(pf.exit_trades.count()),
        "win_rate": _pct(_scalar(pf.exit_trades.get_win_rate())),
        "total_fees_paid": _scalar(pf.orders.fees.sum()),
        "sharpe_ratio": _scalar(
            pf.get_sharpe_ratio(
                freq=pd.Timedelta(config.freq),
                year_freq=pd.Timedelta(config.year_freq),
            )
        ),
    }
    values = {name: _finalize(raw[name]) for name in PORTFOLIO_METRIC_VALUE_KEYS}
    series = pd.Series(values, name="value")
    series.index.name = METRIC_INDEX_NAME
    return series


def _scalar(value: Any) -> float:
    if isinstance(value, (pd.Series, pd.DataFrame)):
        return value.iloc[0]
    if hasattr(value, "item"):
        return value.item()
    return value


def _pct(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) * 100.0
    except (TypeError, ValueError):
        return value


def _finalize(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return value
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric
