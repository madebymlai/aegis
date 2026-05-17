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


def portfolio_metrics(pf: Any, config: ReportConfig) -> dict[str, Any]:
    stats = pf.stats(
        metrics=["total_return", "max_dd", "total_trades", "win_rate", "total_fees_paid"],
        agg_func=None,
    )
    per_symbol = {
        "total_return_pct": _metric_map(stats, "Total Return [%]"),
        "max_drawdown_pct": _metric_map(stats, "Max Drawdown [%]"),
        "total_trades": _metric_map(stats, "Total Trades"),
        "win_rate_pct": _metric_map(stats, "Win Rate [%]"),
        "total_fees_paid": _metric_map(stats, "Total Fees Paid"),
        "sharpe_ratio": _value_map(
            pf.get_sharpe_ratio(
                freq=pd.Timedelta(config.freq),
                year_freq=pd.Timedelta(config.year_freq),
            )
        ),
    }
    return {
        "total_return_pct": _mean_metric(per_symbol["total_return_pct"]),
        "sharpe_ratio": _mean_metric(per_symbol["sharpe_ratio"]),
        "max_drawdown_pct": _max_metric(per_symbol["max_drawdown_pct"]),
        "total_trades": _sum_metric(per_symbol["total_trades"]),
        "win_rate_pct": _mean_metric(per_symbol["win_rate_pct"]),
        "total_fees_paid": _sum_metric(per_symbol["total_fees_paid"]),
        "per_symbol": per_symbol,
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

    decision_grade = validation_metadata.get("decision_grade", True)
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


def _value_map(value: Any) -> dict[str, Any]:
    if isinstance(value, pd.DataFrame):
        return {
            "__".join(map(str, key)) if isinstance(key, tuple) else str(key): _scalar_metric(item)
            for key, item in value.stack().items()
        }
    if isinstance(value, pd.Series):
        return {str(key): _scalar_metric(item) for key, item in value.items()}
    return {"portfolio": _scalar_metric(value)}


def _mean_metric(values: dict[str, Any]) -> Any:
    numbers = _numeric_values(values)
    return sum(numbers) / len(numbers) if numbers else None


def _sum_metric(values: dict[str, Any]) -> Any:
    numbers = _numeric_values(values)
    return sum(numbers) if numbers else None


def _max_metric(values: dict[str, Any]) -> Any:
    numbers = _numeric_values(values)
    return max(numbers) if numbers else None


def _numeric_values(values: dict[str, Any]) -> list[float]:
    return [float(value) for value in values.values() if value is not None]


def _scalar_metric(value: Any) -> Any:
    if isinstance(value, (pd.Series, pd.DataFrame)):
        raise TypeError("metric value must be scalar")
    if pd.isna(value):
        return None
    return to_builtin(value)
