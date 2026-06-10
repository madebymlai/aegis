from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import pandas as pd

from research.aegis_research.configuration import ReportConfig
from research.aegis_research.metrics.contracts import ExtractorSpec


def central_metrics_from_grouped_accessors(
    pf: Any,
    config: ReportConfig,
    candidate_keys: list[tuple],
    param_names: list[str],
    extractors: Mapping[str, ExtractorSpec],
) -> pd.DataFrame:
    """Grouped metric extraction via a registry-driven loop.

    One VBT accessor call per metric over the whole batched portfolio,
    independent of candidate count. Transforms (scale, abs) are applied
    per-candidate via the declarative flags on each ``ExtractorSpec``.

    ``extractors`` is the registry's extractor mapping in registration order
    (catalog metrics, then any custom ones); that order is the output column
    order. The loop owns no knowledge of which metrics exist — it computes
    exactly the records it is handed.
    """
    metric_ids = list(extractors)

    # --- one read per metric, over the whole batch ---
    raw: dict[str, Any] = {
        metric_id: extractors[metric_id].read(pf, config) for metric_id in metric_ids
    }

    # --- per-candidate slice + transforms ---
    rows: list[dict[str, Any]] = []
    for i in range(len(candidate_keys)):
        row: dict[str, Any] = {}
        for metric_id in metric_ids:
            spec = extractors[metric_id]
            val = _ith(raw[metric_id], i)
            if spec.abs_:
                val = abs(val)
            if spec.scale == "percent":
                val = _pct(val)
            row[metric_id] = _finalize(val)
        rows.append(row)

    index = pd.MultiIndex.from_tuples(candidate_keys, names=param_names)
    # The metric grid is uniformly float64 (None -> NaN). Without the explicit
    # dtype, a column whose every candidate finalizes to None (e.g. sharpe in a
    # no-trade window) lands as an all-NA object column, and pandas' deprecated
    # all-NA dtype reconciliation fires (FutureWarning) when vbt row-stacks it
    # with the float64 frames from other windows (incl. the runner's all-invalid
    # NaN frame). Downstream consumers read values through optional_float, so
    # NaN-vs-None inside the grid is invisible to ranking and Evidence.
    return pd.DataFrame(rows, index=index, dtype="float64")


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
