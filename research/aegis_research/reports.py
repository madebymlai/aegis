from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from research.aegis_research.config import ReportConfig, to_builtin


def portfolio_metrics(pf: Any) -> dict[str, Any]:
    stats = pf.stats(agg_func=None)
    if isinstance(stats, pd.DataFrame):
        stats = stats.iloc[0]
    return {
        "total_return_pct": _metric(stats, "Total Return [%]"),
        "sharpe_ratio": _metric(stats, "Sharpe Ratio"),
        "max_drawdown_pct": _metric(stats, "Max Drawdown [%]"),
        "total_trades": _metric(stats, "Total Trades"),
        "win_rate_pct": _metric(stats, "Win Rate [%]"),
        "total_fees_paid": _metric(stats, "Total Fees Paid"),
    }


def build_survival_report(
    experiment_name: str,
    train_metrics: dict[str, Any],
    test_metrics: dict[str, Any],
    config: ReportConfig,
    validation_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    oos_sharpe = test_metrics.get("sharpe_ratio")
    oos_drawdown = test_metrics.get("max_drawdown_pct")
    oos_trades = test_metrics.get("total_trades")

    if oos_sharpe is None or oos_sharpe < config.min_oos_sharpe:
        reasons.append(f"OOS Sharpe below threshold: {oos_sharpe} < {config.min_oos_sharpe}")
    if oos_drawdown is None or oos_drawdown / 100 > config.max_oos_drawdown:
        reasons.append(f"OOS drawdown too high: {oos_drawdown}% > {config.max_oos_drawdown:.0%}")
    if oos_trades is None or oos_trades < config.min_oos_trades:
        reasons.append(f"Too few OOS trades: {oos_trades} < {config.min_oos_trades}")

    status = "survived" if not reasons else "rejected"
    if oos_trades is not None and oos_trades < config.min_oos_trades:
        status = "needs_more_evidence"

    return {
        "experiment": experiment_name,
        "status": status,
        "validation": validation_metadata or {},
        "reasons": reasons or ["OOS metrics cleared configured survival thresholds"],
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
    }


def write_report(report: dict[str, Any], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(to_builtin(report), indent=2, sort_keys=True) + "\n")


def _metric(stats: pd.Series, name: str) -> Any:
    value = stats.get(name)
    if pd.isna(value):
        return None
    return to_builtin(value)
