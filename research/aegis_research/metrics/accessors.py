from __future__ import annotations

import math
from typing import Any

import pandas as pd

from research.aegis_research.configuration.schema import ReportConfig
from research.aegis_research.metrics.extractors import EXTRACTORS
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
    # --- one read per metric ---
    raw_series: dict[str, pd.Series] = {}
    for metric_id in PORTFOLIO_METRIC_VALUE_KEYS:
        spec = EXTRACTORS[metric_id]
        raw_series[metric_id] = spec.read(pf, config)

    # --- per-candidate slice + transforms ---
    n = len(candidate_keys)
    rows: list[dict[str, Any]] = []
    for i in range(n):
        row: dict[str, Any] = {}
        for metric_id in PORTFOLIO_METRIC_VALUE_KEYS:
            spec = EXTRACTORS[metric_id]
            raw = _ith(raw_series[metric_id], i)
            row[metric_id] = _apply_transforms(raw, spec)
        rows.append(row)

    index = pd.MultiIndex.from_tuples(candidate_keys, names=param_names)
    return pd.DataFrame(rows, index=index)


def central_metrics_from_accessors(pf: Any, config: ReportConfig) -> pd.Series:
    """Single-portfolio central metrics.

    Uses the same ``EXTRACTORS`` registry and transform pipeline as
    ``central_metrics_from_grouped_accessors``.
    """
    values: dict[str, Any] = {}
    for metric_id in PORTFOLIO_METRIC_VALUE_KEYS:
        spec = EXTRACTORS[metric_id]
        raw = _ith(spec.read(pf, config), 0)
        values[metric_id] = _apply_transforms(raw, spec)
    series = pd.Series(values, name="value")
    series.index.name = METRIC_INDEX_NAME
    return series


def _ith(series: Any, idx: int) -> Any:
    if isinstance(series, (pd.Series, pd.DataFrame)):
        return series.iloc[idx]
    return series


def _pct(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) * 100.0
    except (TypeError, ValueError):
        return value


def _apply_transforms(raw: Any, spec: Any) -> float | None:
    """Apply the declarative transforms declared by an ExtractorSpec."""
    val = raw
    if spec.abs_:
        val = abs(val)
    if spec.scale == "percent":
        val = _pct(val)
    return _finalize(val)


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
