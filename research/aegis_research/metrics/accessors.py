from __future__ import annotations

import math
from typing import Any

import pandas as pd

from research.aegis_research.configuration.schema import ReportConfig
from research.aegis_research.metrics.stats import PORTFOLIO_METRIC_VALUE_KEYS

METRIC_INDEX_NAME = "metric_name"


def central_metrics_from_grouped_accessors(
    pf: Any,
    config: ReportConfig,
    candidate_keys: list[tuple],
    param_names: list[str],
) -> pd.DataFrame:
    raw_total_return = _to_series(pf.get_total_return())
    raw_max_dd = _to_series(pf.get_max_drawdown()).abs()
    raw_trades = _to_series(pf.exit_trades.count())
    raw_win_rate = _to_series(pf.exit_trades.get_win_rate())
    raw_fees = _to_series(pf.orders.fees.sum())
    raw_sharpe = _to_series(pf.get_sharpe_ratio(
        freq=pd.Timedelta(config.freq),
        year_freq=pd.Timedelta(config.year_freq),
    ))
    n = len(candidate_keys)
    rows = []
    for i in range(n):
        raw = {
            "total_return": _pct(_ith(raw_total_return, i, n)),
            "max_dd": _pct(abs(_ith(raw_max_dd, i, n))),
            "total_trades": _ith(raw_trades, i, n),
            "win_rate": _pct(_ith(raw_win_rate, i, n)),
            "total_fees_paid": _ith(raw_fees, i, n),
            "sharpe_ratio": _ith(raw_sharpe, i, n),
        }
        rows.append({name: _finalize(raw[name]) for name in PORTFOLIO_METRIC_VALUE_KEYS})
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


def _to_series(value: Any) -> pd.Series:
    if isinstance(value, pd.Series):
        return value
    return pd.Series([value])


def _ith(series: Any, idx: int, total: int) -> Any:
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
