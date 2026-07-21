from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from research.aegis_research.metrics.contracts import (
    SOURCE_TYPE_VBT_STATS,
    MetricDefinition,
    MetricRegistryError,
)
from research.aegis_research.metrics.extractors import BUILTIN_EXTRACTORS
from research.aegis_research.metrics.registry import MetricRegistry

VBT_STATS_PROVIDER = "vectorbtpro"
VBT_PORTFOLIO_TARGET = "portfolio"

SUPPORTED_PORTFOLIO_STATS: dict[str, dict[str, Any]] = {
    "total_return": {
        "direction": "maximize",
        "unit": "percent",
        "value_semantics": "percentage_return",
        "source_method": "stats",
        "required_report_output": True,
        "required_gate_input": False,
    },
    "max_dd": {
        "direction": "minimize",
        "unit": "percent_loss_magnitude",
        "value_semantics": "drawdown_loss_magnitude_percent",
        "source_method": "stats",
        "required_report_output": True,
        "required_gate_input": True,
    },
    "total_trades": {
        "direction": "maximize",
        "unit": "count",
        "value_semantics": "trade_count",
        "source_method": "stats",
        "required_report_output": True,
        "required_gate_input": True,
    },
    "win_rate": {
        "direction": "maximize",
        "unit": "percent",
        "value_semantics": "winning_trade_rate_percent",
        "source_method": "stats",
        "required_report_output": True,
        "required_gate_input": False,
    },
    "total_fees_paid": {
        "direction": "minimize",
        "unit": "cash",
        "value_semantics": "fee_cost_cash",
        "source_method": "stats",
        "required_report_output": True,
        "required_gate_input": False,
    },
    "sharpe_ratio": {
        "direction": "maximize",
        "unit": "ratio",
        "value_semantics": "risk_adjusted_return_ratio",
        "source_method": "get_sharpe_ratio",
        "required_report_output": True,
        "required_gate_input": True,
        "required_inputs": ("frequency", "year_frequency"),
    },
}

PORTFOLIO_METRIC_CATALOG: dict[str, dict[str, Any]] = {
    metric_id: {
        "vbt_metric": metric_id,
        "unit": overlay["unit"],
        "source_method": overlay["source_method"],
        "required_report_output": overlay["required_report_output"],
        "required_gate_input": overlay["required_gate_input"],
    }
    for metric_id, overlay in SUPPORTED_PORTFOLIO_STATS.items()
}
PORTFOLIO_METRIC_VALUE_KEYS = tuple(PORTFOLIO_METRIC_CATALOG)
PORTFOLIO_STATS_METRICS = tuple(
    metric["vbt_metric"]
    for metric in PORTFOLIO_METRIC_CATALOG.values()
    if metric["source_method"] == "stats"
)


def register_vbt_stats_metrics(
    registry: MetricRegistry,
    *,
    portfolio_metrics: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    metrics = portfolio_metrics if portfolio_metrics is not None else _portfolio_metrics()
    for metric_id, overlay in SUPPORTED_PORTFOLIO_STATS.items():
        extractor = BUILTIN_EXTRACTORS[metric_id]
        if extractor.range_factory is None:
            raise MetricRegistryError(
                f"VectorBT Portfolio Metric {metric_id!r} has no bounds-aware extractor"
            )
        registry.register(
            _portfolio_metric_definition(metric_id, overlay, metrics),
            extractor,
        )


def _portfolio_metrics() -> Mapping[str, Mapping[str, Any]]:
    import vectorbtpro as vbt

    return vbt.Portfolio.metrics


def _portfolio_metric_definition(
    metric_id: str,
    overlay: Mapping[str, Any],
    metrics: Mapping[str, Mapping[str, Any]],
) -> MetricDefinition:
    try:
        vbt_metric = metrics[metric_id]
    except KeyError as error:
        raise MetricRegistryError(
            f"VectorBT Portfolio stats metric {metric_id!r} is not registered"
        ) from error
    title = vbt_metric.get("title")
    if not title:
        raise MetricRegistryError(f"VectorBT Portfolio stats metric {metric_id!r} has no title")
    return MetricDefinition(
        id=metric_id,
        title=str(title),
        source_type=SOURCE_TYPE_VBT_STATS,
        unit=str(overlay["unit"]),
        value_semantics=str(overlay["value_semantics"]),
        direction=overlay["direction"],
        boundary_semantics="native_continuous",
        required_inputs=tuple(overlay.get("required_inputs", ())),
        provider=VBT_STATS_PROVIDER,
        target=VBT_PORTFOLIO_TARGET,
        vbt_metric=metric_id,
        source_method=str(overlay["source_method"]),
        required_report_output=bool(overlay["required_report_output"]),
        required_gate_input=bool(overlay["required_gate_input"]),
    )
