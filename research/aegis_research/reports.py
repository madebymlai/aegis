from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from research.aegis_research.config import (
    REPORT_STATUS_NEEDS_MORE_EVIDENCE,
    REPORT_STATUS_REJECTED,
    REPORT_STATUS_SURVIVED,
    ReportConfig,
    to_builtin,
)
from research.aegis_research.splits import split_purging_passed

PORTFOLIO_METRIC_SCOPE = "shared_cash_group"
METRICS_SCHEMA_VERSION = "metrics.v2"
PORTFOLIO_STATS_METRICS = (
    "total_return",
    "max_dd",
    "total_trades",
    "win_rate",
    "total_fees_paid",
)


def portfolio_metrics(pf: Any, config: ReportConfig) -> dict[str, Any]:
    sharpe_kwargs = {
        "freq": pd.Timedelta(config.freq),
        "year_freq": pd.Timedelta(config.year_freq),
    }
    stats = pf.stats(metrics=list(PORTFOLIO_STATS_METRICS), agg_func=None)
    per_symbol_stats = pf.stats(
        metrics=list(PORTFOLIO_STATS_METRICS),
        agg_func=None,
        group_by=False,
    )
    sharpe_ratio = pf.get_sharpe_ratio(**sharpe_kwargs)
    per_symbol = {
        "total_return_pct": _metric_map(per_symbol_stats, "Total Return [%]"),
        "max_drawdown_pct": _metric_map(per_symbol_stats, "Max Drawdown [%]"),
        "total_trades": _metric_map(per_symbol_stats, "Total Trades"),
        "win_rate_pct": _metric_map(per_symbol_stats, "Win Rate [%]"),
        "total_fees_paid": _metric_map(per_symbol_stats, "Total Fees Paid"),
        "sharpe_ratio": _value_map(
            pf.get_sharpe_ratio(
                **sharpe_kwargs,
                group_by=False,
            )
        ),
    }
    return {
        "total_return_pct": _headline_metric(stats, "Total Return [%]"),
        "sharpe_ratio": _headline_value(sharpe_ratio),
        "max_drawdown_pct": _headline_metric(stats, "Max Drawdown [%]"),
        "total_trades": _headline_metric(stats, "Total Trades"),
        "win_rate_pct": _headline_metric(stats, "Win Rate [%]"),
        "total_fees_paid": _headline_metric(stats, "Total Fees Paid"),
        "metric_scope": PORTFOLIO_METRIC_SCOPE,
        "metric_assumptions": portfolio_metric_assumptions(config),
        "per_symbol": per_symbol,
    }


def portfolio_metric_assumptions(config: ReportConfig) -> dict[str, Any]:
    return {
        "scope": PORTFOLIO_METRIC_SCOPE,
        "scope_detail": "one shared cash group across configured symbols",
        "freq": config.freq,
        "year_freq": config.year_freq,
        "benchmark_status": "none",
        "benchmark_source": None,
    }


def build_survival_report(
    experiment_name: str,
    train_metrics: dict[str, Any],
    test_metrics: dict[str, Any],
    config: ReportConfig,
    validation_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    validation_metadata = validation_metadata or {}
    oos_sharpe = test_metrics.get("sharpe_ratio")
    oos_drawdown = test_metrics.get("max_drawdown_pct")
    oos_trades = test_metrics.get("total_trades")

    decision_grade = validation_metadata.get("decision_grade", False)
    split_safety = validation_metadata.get("target", {}).get("split_safety", {})
    if (
        decision_grade
        and split_safety.get("purging_required")
        and not split_purging_passed(validation_metadata.get("split_metadata"))
    ):
        decision_grade = False
        reasons.append("Validation is missing public split evidence for label-window purging")
    if not decision_grade:
        reasons.append("Validation is non-decision-grade until purged CV is applied")

    if oos_sharpe is None or oos_sharpe < config.min_oos_sharpe:
        reasons.append(f"OOS Sharpe below threshold: {oos_sharpe} < {config.min_oos_sharpe}")
    if oos_drawdown is None or oos_drawdown / 100 > config.max_oos_drawdown:
        reasons.append(f"OOS drawdown too high: {oos_drawdown}% > {config.max_oos_drawdown:.0%}")
    if oos_trades is None or oos_trades < config.min_oos_trades:
        reasons.append(f"Too few OOS trades: {oos_trades} < {config.min_oos_trades}")

    status = REPORT_STATUS_SURVIVED if not reasons else REPORT_STATUS_REJECTED
    if not decision_grade:
        status = REPORT_STATUS_NEEDS_MORE_EVIDENCE
    if oos_trades is not None and oos_trades < config.min_oos_trades:
        status = REPORT_STATUS_NEEDS_MORE_EVIDENCE

    return {
        "experiment": experiment_name,
        "status": status,
        "validation": validation_metadata,
        "reasons": reasons or ["OOS metrics cleared configured survival thresholds"],
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
    }


def write_report(report: dict[str, Any], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(to_builtin(report), indent=2, sort_keys=True) + "\n")


def _metric_map(stats: Any, name: str) -> dict[str, Any]:
    if isinstance(stats, pd.DataFrame):
        if name in stats.index:
            return _value_map(stats.loc[name])
        if name in stats.columns:
            return _value_map(stats[name])
        return {}
    return {"portfolio": _scalar_metric(stats.get(name))}


def _headline_metric(stats: Any, name: str) -> Any:
    return _headline_from_values(_metric_map(stats, name))


def _headline_value(value: Any) -> Any:
    return _headline_from_values(_value_map(value))


def _headline_from_values(values: dict[str, Any]) -> Any:
    if len(values) != 1:
        raise ValueError("shared-cash headline metrics must resolve to exactly one group")
    return next(iter(values.values()))


def _value_map(value: Any) -> dict[str, Any]:
    if isinstance(value, pd.DataFrame):
        return {
            "__".join(map(str, key)) if isinstance(key, tuple) else str(key): _scalar_metric(item)
            for key, item in value.stack().items()
        }
    if isinstance(value, pd.Series):
        return {str(key): _scalar_metric(item) for key, item in value.items()}
    return {"portfolio": _scalar_metric(value)}


def _scalar_metric(value: Any) -> Any:
    if isinstance(value, (pd.Series, pd.DataFrame)):
        raise TypeError("metric value must be scalar")
    if pd.isna(value):
        return None
    return to_builtin(value)
