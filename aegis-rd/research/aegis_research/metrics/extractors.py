"""Built-in vectorised metric extractors.

Each extractor is a pure ``read(pf, config) -> Series`` making exactly one VBT
accessor call over the whole grouped batch. Transforms (scale, abs) are declared
as flags on the :class:`ExtractorSpec` and applied by the extraction loop in
``central_metrics_from_grouped_accessors`` — they are NOT baked into the reads.

``BUILTIN_EXTRACTORS`` pairs each built-in metric id with its spec; the pair is
registered into the :class:`MetricRegistry` alongside the metric's definition
(``stats.register_vbt_stats_metrics``), so the registry record is the single
home for both *what a Metric is* and *how it is read*. There is no process-global
extractor state — a Metric's extractor lives and dies with its registry.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from research.aegis_research.configuration import ReportConfig
from research.aegis_research.metrics.contracts import ExtractorSpec


def _to_series(value: Any) -> pd.Series:
    """Normalise a VBT MaybeSeries return to a plain Series."""
    if isinstance(value, pd.Series):
        return value
    return pd.Series([value])


def _read_total_return(pf: Any, config: ReportConfig) -> pd.Series:
    return _to_series(pf.get_total_return())


def _read_max_dd(pf: Any, config: ReportConfig) -> pd.Series:
    return _to_series(pf.get_max_drawdown())


def _read_total_trades(pf: Any, config: ReportConfig) -> pd.Series:
    return _to_series(pf.exit_trades.count())


def _read_win_rate(pf: Any, config: ReportConfig) -> pd.Series:
    return _to_series(pf.exit_trades.status_closed.get_win_rate())


def _read_total_fees_paid(pf: Any, config: ReportConfig) -> pd.Series:
    return _to_series(pf.orders.fees.sum())


def _read_sharpe_ratio(pf: Any, config: ReportConfig) -> pd.Series:
    return _to_series(
        pf.get_sharpe_ratio(
            freq=pd.Timedelta(config.freq),
            year_freq=pd.Timedelta(config.year_freq),
        )
    )


def _native_range_factory(metric_id: str):
    def factory(config: ReportConfig):
        def extractor(pf: Any, *, sim_start: int, sim_end: int) -> pd.Series:
            kwargs = {
                "sim_start": sim_start,
                "sim_end": sim_end,
                "rec_sim_range": False,
            }
            if metric_id == "total_return":
                returns = pf.get_returns(rec_sim_range=False)
                if isinstance(returns, pd.Series):
                    returns = returns.to_frame()
                return (1.0 + returns.iloc[sim_start:sim_end].fillna(0.0)).prod() - 1.0
            if metric_id == "max_dd":
                drawdown = pf.get_drawdown(rec_sim_range=False)
                if isinstance(drawdown, pd.Series):
                    drawdown = drawdown.to_frame()
                return drawdown.iloc[sim_start:sim_end].min()
            if metric_id == "sharpe_ratio":
                return _to_series(
                    pf.get_sharpe_ratio(
                        **kwargs,
                        freq=pd.Timedelta(config.freq),
                        year_freq=pd.Timedelta(config.year_freq),
                    )
                )
            if metric_id == "total_trades":
                return _to_series(pf.get_exit_trades(**kwargs).count())
            if metric_id == "win_rate":
                return _to_series(
                    pf.get_exit_trades(**kwargs).status_closed.get_win_rate()
                )
            if metric_id == "total_fees_paid":
                return _to_series(pf.get_orders(**kwargs).fees.sum())
            raise KeyError(metric_id)

        return extractor

    return factory


BUILTIN_EXTRACTORS: dict[str, ExtractorSpec] = {
    "total_return": ExtractorSpec(
        _read_total_return, scale="percent", range_factory=_native_range_factory("total_return")
    ),
    "max_dd": ExtractorSpec(
        _read_max_dd, scale="percent", abs_=True, range_factory=_native_range_factory("max_dd")
    ),
    "total_trades": ExtractorSpec(
        _read_total_trades, range_factory=_native_range_factory("total_trades")
    ),
    "win_rate": ExtractorSpec(
        _read_win_rate, scale="percent", range_factory=_native_range_factory("win_rate")
    ),
    "total_fees_paid": ExtractorSpec(
        _read_total_fees_paid, range_factory=_native_range_factory("total_fees_paid")
    ),
    "sharpe_ratio": ExtractorSpec(
        _read_sharpe_ratio, range_factory=_native_range_factory("sharpe_ratio")
    ),
}
