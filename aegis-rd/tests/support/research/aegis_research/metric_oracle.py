"""Report-grade metric oracle for parity testing.

An independent reference implementation of the six central portfolio metrics,
computed through VectorBT PRO's canonical ``pf.stats()`` table rather than the
hand-assembled accessor path used in production
(``metrics.accessors.central_metrics_from_*``).

Its sole purpose is to be a *different* implementation that the production path
can be pinned against: ``pf.stats()`` exercises VBT's blessed metric assembly,
while production calls individual accessors with manual unit conversions. Parity
between the two guards against unit/sign drift (percent scaling, drawdown
magnitude) and positional-index mistakes in the grouped sweep path.

This is test support, not a production surface — it deliberately drops the
availability/diagnostics scaffolding and returns only the value keys.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import pandas as pd

from research.aegis_research.configuration import ReportConfig
from research.aegis_research.metrics.stats import (
    PORTFOLIO_METRIC_CATALOG,
    PORTFOLIO_STATS_METRICS,
)

SYMBOL_LEVEL = "symbol"


def report_grade_metrics(pf: Any, config: ReportConfig) -> dict[str, float | None]:
    """Headline (single shared-cash group) metric values via ``pf.stats()``."""
    stats, sharpe = _raw_sources(pf, config)
    return {
        name: _select_headline(metric, _title(pf, metric), stats, sharpe)
        for name, metric in PORTFOLIO_METRIC_CATALOG.items()
    }


def report_grade_metrics_by_candidate(
    pf: Any,
    config: ReportConfig,
    candidate_ids: Iterable[Any],
) -> dict[Any, dict[str, float | None]]:
    """Per-candidate metric values via ``pf.stats()`` for a batched portfolio."""
    stats, sharpe = _raw_sources(pf, config)
    titles = {name: _title(pf, metric) for name, metric in PORTFOLIO_METRIC_CATALOG.items()}
    return {
        candidate_id: {
            name: _select_candidate(metric, titles[name], stats, sharpe, candidate_id)
            for name, metric in PORTFOLIO_METRIC_CATALOG.items()
        }
        for candidate_id in candidate_ids
    }


def _raw_sources(pf: Any, config: ReportConfig) -> tuple[Any, Any]:
    stats = pf.stats(metrics=list(PORTFOLIO_STATS_METRICS), agg_func=None)
    sharpe = pf.get_sharpe_ratio(
        freq=pd.Timedelta(config.freq),
        year_freq=pd.Timedelta(config.year_freq),
    )
    return stats, sharpe


def _select_headline(metric: dict[str, Any], title: str, stats: Any, sharpe: Any) -> float | None:
    if metric["source_method"] == "stats":
        raw = _headline_from_values(_stat_value_map(stats, title))
    else:
        raw = _headline_from_values(_value_map(sharpe))
    return _normalize(metric, raw)


def _select_candidate(
    metric: dict[str, Any], title: str, stats: Any, sharpe: Any, candidate_id: Any
) -> float | None:
    if metric["source_method"] == "stats":
        raw = _candidate_stat_value(stats, title, candidate_id)
    else:
        raw = _candidate_value(sharpe, candidate_id)
    return _normalize(metric, raw)


def _title(pf: Any, metric: dict[str, Any]) -> str:
    identity = metric["vbt_metric"]
    try:
        title = pf.metrics[identity].get("title")
    except KeyError as error:
        raise ValueError(f"VectorBT metric identity {identity!r} is not registered") from error
    if not title:
        raise ValueError(f"VectorBT metric identity {identity!r} has no title")
    return str(title)


def _stat_value_map(stats: Any, name: str) -> dict[str, Any]:
    if isinstance(stats, pd.DataFrame):
        if name in stats.index:
            return _value_map(stats.loc[name])
        if name in stats.columns:
            return _value_map(stats[name])
        return {}
    return {"portfolio": stats.get(name)}


def _value_map(value: Any) -> dict[str, Any]:
    if isinstance(value, pd.DataFrame):
        return {str(key): item for key, item in value.stack().items()}
    if isinstance(value, pd.Series):
        return {str(key): item for key, item in value.items()}
    return {"portfolio": value}


def _headline_from_values(values: dict[str, Any]) -> Any:
    if len(values) != 1:
        raise ValueError("shared-cash headline metrics must resolve to exactly one group")
    return next(iter(values.values()))


def _candidate_stat_value(stats: Any, name: str, candidate_id: Any) -> Any:
    if isinstance(stats, pd.DataFrame):
        if candidate_id in stats.index and name in stats.columns:
            return stats.loc[candidate_id, name]
        if name in stats.index and candidate_id in stats.columns:
            return stats.loc[name, candidate_id]
    if isinstance(stats, pd.Series):
        return stats.get(name) if name in stats.index else stats.get(candidate_id)
    return None


def _candidate_value(value: Any, candidate_id: Any) -> Any:
    if isinstance(value, pd.Series):
        return value.get(candidate_id)
    return value


def _normalize(metric: dict[str, Any], raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        numeric = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    if metric["vbt_metric"] == "max_dd":
        return abs(numeric)
    return numeric
