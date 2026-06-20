"""End-to-end: a dual-series run simulates P&L on the ``pnl_adjustment`` series.

A futures store symbol may declare two continuous series — ``adjustment`` (the signal
series the indicators run on) and ``pnl_adjustment`` (the series the portfolio simulates
P&L against), named for NautilusTrader's backward modes. This drives the WHOLE pipeline
(``run_strategy_sweep``) twice with identical signals and asserts the portfolio P&L is
computed on the P&L series in the dual run and on the signal series in the single run —
i.e. the second series actually reaches the portfolio simulation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from aegis_data.store import write_native_bars

from research.aegis_research.run_pipeline import run_strategy_sweep
from tests.support.research.aegis_research.run_config_fixtures import build_resolved_run_config

# Disjoint price levels per adjustment so the captured portfolio close pins the series.
_RATIO_BASE = 100.0
_SPREAD_BASE = 1000.0
_BUSINESS_DAYS = pd.bdate_range("2022-01-03", "2022-09-30")


def _ohlcv(base: float) -> pd.DataFrame:
    # Strictly increasing close so the demo strategy (long on up-days) trades every bar.
    close = [base + i * 0.1 for i in range(len(_BUSINESS_DAYS))]
    return pd.DataFrame(
        {
            "Open": close,
            "High": [c + 0.5 for c in close],
            "Low": [c - 0.5 for c in close],
            "Close": close,
            "Volume": [1_000.0] * len(close),
        },
        index=_BUSINESS_DAYS,
    )


def _write_by_adjustment(request: Any, *, store_dir: Any) -> object:
    """Fake the Databento futures pull: each adjustment gets a disjoint price level."""
    for ref in request.refs:
        base = _RATIO_BASE if ref.adjustment == "backward_ratio" else _SPREAD_BASE
        write_native_bars(
            ref,
            "1D",
            _ohlcv(base),
            required_arrays=("Open", "High", "Low", "Close", "Volume"),
            store_dir=store_dir,
        )
    return object()


def _store_future(*, pnl_adjustment: str | None) -> dict[str, Any]:
    symbol: dict[str, Any] = {"root": "ES", "ccy": "EUR", "adjustment": "backward_ratio"}
    if pnl_adjustment is not None:
        symbol["pnl_adjustment"] = pnl_adjustment
    return symbol


def _portfolio_close_levels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_id: str,
    pnl_adjustment: str | None,
) -> list[float]:
    """Run the full pipeline once and return every close value the portfolio simulated on."""
    captured: list[pd.DataFrame] = []
    from research.aegis_research.optimization import window_evaluator

    real = window_evaluator.simulate_portfolio_batch

    def spy(close: pd.DataFrame, *args: Any, **kwargs: Any) -> Any:
        captured.append(close)
        return real(close, *args, **kwargs)

    monkeypatch.setattr(window_evaluator, "simulate_portfolio_batch", spy)
    monkeypatch.setattr("aegis_data.coverage.pull_databento_futures_bars", _write_by_adjustment)

    resolved = build_resolved_run_config(
        tmp_path,
        data={
            "source": "store",
            "provider": "databento",
            "dataset": "GLBX.MDP3",
            "symbols": [_store_future(pnl_adjustment=pnl_adjustment)],
            "arrays": ["OHLCV"],
            "start": "2022-01-03",
            "end": "2022-09-30",
            "timeframe": "1D",
            "missing_index": "drop",
        },
        optimization={"split": {"max_splits": 10}},
    )
    run_strategy_sweep(resolved, component_registry=resolved.component_registry, run_id=run_id)

    return [float(value) for frame in captured for value in frame.to_numpy().ravel()]


def test_dual_series_simulates_pnl_on_the_pnl_adjustment_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path / "store"))
    monkeypatch.chdir(tmp_path)

    single = _portfolio_close_levels(tmp_path, monkeypatch, run_id="single", pnl_adjustment=None)
    dual = _portfolio_close_levels(
        tmp_path, monkeypatch, run_id="dual", pnl_adjustment="backward_spread"
    )

    assert single and dual  # both runs actually simulated a portfolio
    # Identical signals (both signal on backward_ratio), but the portfolio P&L is computed on
    # the signal series for the single run and on the backward_spread series for the dual run.
    assert max(single) < 500.0  # single run simulated on the ratio series (~100)
    assert min(dual) > 500.0  # dual run simulated on the spread series (~1000)
