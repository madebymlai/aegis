from __future__ import annotations

import math
from typing import Any

import pandas as pd

from research.aegis_research.configuration.schema import ReportConfig
from research.aegis_research.metrics.extractors import (
    get_custom_extractor_keys,
    get_extractors,
)
from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS

METRIC_INDEX_NAME = "metric_name"


def central_metrics_from_grouped_accessors(
    pf: Any,
    config: ReportConfig,
    candidate_keys: list[tuple],
    param_names: list[str],
) -> pd.DataFrame:
    """Grouped metric extraction via registry-driven loop.

    One VBT accessor call per metric over the whole batched portfolio,
    independent of candidate count.  Transforms (scale, abs) are applied
    per-candidate via declarative flags from the ``EXTRACTORS`` map.
    """
    extractors = get_extractors()
    all_metric_keys = list(PORTFOLIO_METRIC_VALUE_KEYS) + list(get_custom_extractor_keys())

    # --- one read per metric ---
    raw_series: dict[str, pd.Series] = {}
    for metric_id in all_metric_keys:
        spec = extractors[metric_id]
        raw_series[metric_id] = spec.read(pf, config)

    # --- per-candidate slice + transforms ---
    n = len(candidate_keys)
    rows: list[dict[str, Any]] = []
    for i in range(n):
        row: dict[str, Any] = {}
        for metric_id in all_metric_keys:
            spec = extractors[metric_id]
            val = _ith(raw_series[metric_id], i)
            if spec.abs_:
                val = abs(val)
            if spec.scale == "percent":
                val = _pct(val)
            row[metric_id] = _finalize(val)
        rows.append(row)

    index = pd.MultiIndex.from_tuples(candidate_keys, names=param_names)
    return pd.DataFrame(rows, index=index)


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


def _ith(series: Any, idx: int) -> Any:
    if isinstance(series, (pd.Series, pd.DataFrame)):
        return series.iloc[idx]
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
