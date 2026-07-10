"""Per-window evaluation contract: the WindowEvaluator seam.

WindowEvaluator owns the per-(split, set) coordination the optimization sweep
performs for one window and one chunk of Candidates: slice the price and
precomputed-indicator windows by the splitter's ``range_``, short-circuit a
chunk whose every Candidate is Invalid, run the strategy ``simulate``, and turn
the allocations into a Candidate-by-Metric frame. These were trapped inside a
closure fed to ``vbt.parameterized``; here the same coordination is driven
directly through ``evaluate`` without standing up the splitter machinery.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.metrics import make_default_metric_registry
from research.aegis_research.optimization.precompute import empty_precompute
from research.aegis_research.optimization.source import OptimizationSource
from research.aegis_research.optimization.window_evaluator import WindowEvaluator
from tests.support.research.aegis_research.factories import (
    make_portfolio_config,
    make_report_config,
    make_run_arrays,
)


def _uptrend_close(n: int = 12) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=n, freq="D")
    levels = 100.0 * (1.01 ** np.arange(n))
    return pd.DataFrame({"SYN": levels}, index=index)


def _exposure_simulate(
    close_window: pd.DataFrame, indicator_window: Any, n_combos: int, **param_lists: Any
) -> pd.DataFrame:
    """Each Candidate buys ``alpha`` exposure on the first bar and holds (uptrend ⇒ return ∝ alpha)."""
    alphas = param_lists["alpha"]
    symbols = list(close_window.columns)
    columns = pd.MultiIndex.from_tuples(
        [(alpha, symbol) for alpha in alphas for symbol in symbols],
        names=["alpha", "symbol"],
    )
    data = np.full((len(close_window), len(columns)), np.nan)
    for candidate_idx, alpha in enumerate(alphas):
        for symbol_idx in range(len(symbols)):
            data[0, candidate_idx * len(symbols) + symbol_idx] = alpha / len(symbols)
    return pd.DataFrame(data, index=close_window.index, columns=columns)


def _source(simulate: Any) -> OptimizationSource:
    return OptimizationSource(
        precompute=empty_precompute,
        simulate=simulate,
        params={"alpha": vbt.Param([0.5, 1.0])},
        output_name="target_weights",
        evidence={},
        diagnostics={},
        metadata={},
    )


def _evaluator(
    close: pd.DataFrame,
    simulate: Any,
    *,
    store: Any = None,
) -> WindowEvaluator:
    return WindowEvaluator(
        source=_source(simulate),
        portfolio=make_portfolio_config(fees=0.0, slippage=0.0, direction="longonly"),
        report=make_report_config(),
        arrays=make_run_arrays(close=close, open_=close),
        store=store if store is not None else empty_precompute(close, 2, alpha=[0.5, 1.0]),
        extractors=dict(make_default_metric_registry().extractors),
    )


class _RaisingStore:
    """A store whose window slice must never be reached (proves the short-circuit).

    Carries its own ``invalid_keys`` — the evaluator reads the Invalid set from the
    store, not from a separate field, so the fake supplies both behaviours.
    """

    def __init__(self, invalid_keys: set) -> None:
        self.invalid_keys = invalid_keys

    def window(self, range_: slice, keys: Any) -> dict:
        raise AssertionError("store.window must not be sliced for an all-Invalid chunk")


def _boom_simulate(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("simulate must not run for an all-Invalid chunk")


class _RecordingStore:
    """Records each window slice and returns no indicator outputs."""

    def __init__(self, invalid_keys: set | None = None) -> None:
        self.calls: list[tuple[slice, list]] = []
        self.invalid_keys = invalid_keys or set()

    def window(self, range_: slice, keys: Any) -> dict:
        self.calls.append((range_, list(keys)))
        return {}


def test_evaluate_produces_one_metric_row_per_candidate() -> None:
    close = _uptrend_close()
    evaluator = _evaluator(close, _exposure_simulate)

    frame = evaluator.evaluate(slice(0, len(close)), alpha=[0.5, 1.0])

    assert list(frame.index.names) == ["alpha"]
    assert list(frame.index) == [(0.5,), (1.0,)]
    assert "total_return" in frame.columns
    # Uptrend, zero costs: total_return is monotonic in alpha exposure.
    assert frame.loc[(1.0,), "total_return"] > frame.loc[(0.5,), "total_return"] > 0.0


def test_evaluate_short_circuits_an_all_invalid_chunk_to_a_nan_frame() -> None:
    close = _uptrend_close()
    # Candidate keys are built in sorted-param-name order: alpha ⇒ (0.5,), (1.0,).
    evaluator = _evaluator(
        close,
        _boom_simulate,
        store=_RaisingStore(invalid_keys={(0.5,), (1.0,)}),
    )

    frame = evaluator.evaluate(slice(0, len(close)), alpha=[0.5, 1.0])

    # Same shape as a real metric frame — one row per Candidate, every registry
    # column present — but entirely NaN, and reached without simulating.
    assert list(frame.index) == [(0.5,), (1.0,)]
    assert list(frame.columns) == list(make_default_metric_registry().extractors)
    assert frame.isna().to_numpy().all()


def test_evaluate_slices_windows_and_delegates_for_a_partly_invalid_chunk() -> None:
    close = _uptrend_close()
    store = _RecordingStore(invalid_keys={(0.5,)})
    recorded: dict[str, Any] = {}

    def _recording_simulate(
        close_window: pd.DataFrame, indicator_window: Any, n_combos: int, **param_lists: Any
    ) -> Any:
        recorded["close_window"] = close_window
        recorded["n_combos"] = n_combos
        recorded["param_lists"] = param_lists
        return vbt.NoResult

    # Only one of two Candidates is Invalid ⇒ the chunk is NOT short-circuited.
    evaluator = _evaluator(close, _recording_simulate, store=store)
    range_ = slice(2, 8)

    result = evaluator.evaluate(range_, alpha=[0.5, 1.0])

    # Simulate ran over the sliced price window for the full chunk (all-or-nothing).
    assert recorded["n_combos"] == 2
    assert recorded["param_lists"] == {"alpha": [0.5, 1.0]}
    pd.testing.assert_frame_equal(recorded["close_window"], close.iloc[range_])
    # The store was sliced by the same range and Candidate keys.
    assert store.calls == [(range_, [(0.5,), (1.0,)])]
    # A NoResult from simulate propagates out unchanged.
    assert result is vbt.NoResult


def test_dual_series_signal_drives_simulate_and_pnl_prices_the_portfolio() -> None:
    """The regression net for the mixed-view bug (aegis-rd-cyms.3).

    On a dual-series Run the strategy's ``simulate`` must receive the SIGNAL
    view (the frames its indicators were precomputed on), while the portfolio
    prices P&L exclusively from the P&L view. Before the fix the P&L-adjusted
    Close leaked into ``simulate`` alongside signal-precomputed indicators.
    """
    n = 12
    signal_close = _uptrend_close(n)  # 1% drift
    index = signal_close.index
    # Distinguishable P&L view: steeper drift, so pricing on the wrong view
    # shows up in total_return, not just in frame identity.
    pnl_levels = 50.0 * (1.03 ** np.arange(n))
    pnl_close = pd.DataFrame({"SYN": pnl_levels}, index=index)
    captured: dict[str, pd.DataFrame] = {}

    def _capturing_simulate(
        close_window: pd.DataFrame, indicator_window: Any, n_combos: int, **param_lists: Any
    ) -> pd.DataFrame:
        captured["close_window"] = close_window
        return _exposure_simulate(close_window, indicator_window, n_combos, **param_lists)

    evaluator = WindowEvaluator(
        source=_source(_capturing_simulate),
        portfolio=make_portfolio_config(fees=0.0, slippage=0.0, direction="longonly"),
        report=make_report_config(),
        arrays=make_run_arrays(
            close=signal_close,
            open_=signal_close,
            pnl_close=pnl_close,
            pnl_open=pnl_close,
        ),
        store=empty_precompute(signal_close, 2, alpha=[0.5, 1.0]),
        extractors=dict(make_default_metric_registry().extractors),
    )

    frame = evaluator.evaluate(slice(0, n), alpha=[0.5, 1.0])

    # The strategy allocated from the signal view — the same frames its
    # indicators were precomputed on — not the P&L view.
    pd.testing.assert_frame_equal(captured["close_window"], signal_close)
    # The portfolio priced P&L from the P&L view: full exposure earns the P&L
    # series' return, not the signal series'. total_return is in percent.
    pnl_return_pct = (pnl_levels[-1] / pnl_levels[0] - 1.0) * 100.0
    signal_return_pct = (
        signal_close.iloc[-1, 0] / signal_close.iloc[0, 0] - 1.0
    ) * 100.0
    total_return = frame.loc[(1.0,), "total_return"]
    assert total_return == pytest.approx(pnl_return_pct, rel=1e-9)
    assert total_return != pytest.approx(signal_return_pct, rel=1e-3)


def test_evaluate_returns_no_result_for_empty_allocations() -> None:
    close = _uptrend_close()

    def _empty_simulate(
        close_window: pd.DataFrame, indicator_window: Any, n_combos: int, **param_lists: Any
    ) -> pd.DataFrame:
        return pd.DataFrame(index=close_window.index)  # no candidate columns

    evaluator = _evaluator(close, _empty_simulate)

    result = evaluator.evaluate(slice(0, len(close)), alpha=[0.5, 1.0])

    # Degenerate allocations never reach the portfolio simulator.
    assert result is vbt.NoResult
