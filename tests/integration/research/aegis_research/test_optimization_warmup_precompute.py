"""Warmup-preserving optimization (aegis-rd-94v.1/.2 precomputed-store reuse).

Encodes the cw2 bug at the precompute/simulate seam: an indicator whose lookback
window meets-or-exceeds the per-split selection slice is all-NaN when computed on
the bare slice (no prior history), so the strategy holds cash every bar and the
candidate takes zero trades. The fix computes indicators once over the full series
and slices those warmup-complete outputs per selection and held-out window, so the
candidate trades on every split for which the full series supplies >= lookback history.

In-tree synthetic fixtures only (no live data, no network).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration import OptimizationConfig
from research.aegis_research.metrics import make_default_metric_registry
from research.aegis_research.optimization.precompute import (
    IndicatorPrecompute,
    build_candidate_index,
)
from research.aegis_research.optimization.ranking import OptimizationResult
from research.aegis_research.optimization.runner import execute_optimization
from research.aegis_research.optimization.source import OptimizationSource
from research.aegis_research.run_splits import build_run_splits_result
from tests.support.research.aegis_research.factories import (
    make_optimization_config,
    make_portfolio_config,
    make_ranking_config,
    make_report_config,
    make_run_split_config,
)

N_ROWS = 32
SLICE_LEN = 4  # length=8, split=0.5 -> 4-bar selection slice per split
WARMUP_WINDOW = 4  # lookback == slice length -> bare-slice is all-NaN (the bug)


def _uptrend_close() -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=N_ROWS, freq="D")
    levels = 100.0 * (1.01 ** np.arange(N_ROWS))
    return pd.DataFrame({"SYN": levels}, index=index)


def _downtrend_close() -> pd.DataFrame:
    """Close that falls ~0.99^x each day so a buy-and-hold valid candidate loses money."""
    index = pd.date_range("2024-01-01", periods=N_ROWS, freq="D")
    levels = 100.0 * (0.99 ** np.arange(N_ROWS))
    return pd.DataFrame({"SYN": levels}, index=index)


def _warmup_precompute(
    close: pd.DataFrame, n_candidates: int, **param_lists
) -> IndicatorPrecompute:
    """Causal momentum (close[t]/close[t-window]-1); first ``window`` rows are NaN."""
    windows = param_lists["window"]
    prices = close.to_numpy()
    n_rows, n_symbols = prices.shape
    outputs = np.full((n_rows, n_candidates * n_symbols), np.nan)
    for candidate, window in enumerate(windows):
        block = np.full((n_rows, n_symbols), np.nan)
        if window < n_rows:
            block[window:] = prices[window:] / prices[:-window] - 1.0
        outputs[:, candidate * n_symbols : (candidate + 1) * n_symbols] = block
    return IndicatorPrecompute(
        outputs={"mom": outputs},
        candidate_index=build_candidate_index(param_lists),
        n_symbols=n_symbols,
    )


def _gated_simulate(
    close_window: pd.DataFrame, indicator_window, n_candidates: int, **param_lists
) -> pd.DataFrame:
    """Buy equal-weight on the first warmup-complete bar; else hold cash (no trade)."""
    momentum = indicator_window["mom"]
    n_symbols = len(close_window.columns)
    windows = param_lists["window"]
    allocations = np.full((len(close_window), n_candidates * n_symbols), np.nan)
    for candidate in range(n_candidates):
        block = momentum[:, candidate * n_symbols : (candidate + 1) * n_symbols]
        warmup_complete = ~np.isnan(block).any(axis=1)
        if warmup_complete.any():
            first = int(np.argmax(warmup_complete))
            allocations[first, candidate * n_symbols : (candidate + 1) * n_symbols] = (
                1.0 / n_symbols
            )
    symbols = list(close_window.columns)
    columns = pd.MultiIndex.from_tuples(
        [(windows[c], sym) for c in range(n_candidates) for sym in symbols],
        names=["window", "symbol"],
    )
    return pd.DataFrame(allocations, index=close_window.index, columns=columns)


def _source(windows: list[int]) -> OptimizationSource:
    return OptimizationSource(
        precompute=_warmup_precompute,
        simulate=_gated_simulate,
        params={"window": vbt.Param(windows)},
        output_name="target_weights",
        evidence={"source": "synthetic_warmup"},
        diagnostics={},
        metadata={},
    )


def _optimization(
    *, search: str = "grid", random_subset: int | None = None, seed: int | None = None
) -> OptimizationConfig:
    return make_optimization_config(
        search=search,
        random_subset=random_subset,
        seed=seed,
        split=make_run_split_config(method="from_rolling", params={"length": 8, "split": 0.5}),
    )


def _run(windows: list[int], *, optimization: OptimizationConfig | None = None) -> OptimizationResult:
    optimization = optimization or _optimization()
    return execute_optimization(
        close=_uptrend_close(),
        open_=_uptrend_close(),
        source=_source(windows),
        optimization=optimization,
        portfolio=make_portfolio_config(fees=0.0, slippage=0.0, direction="longonly"),
        report=make_report_config(),
        ranking=make_ranking_config(metric="total_return", min_weight=0.3),
        metric_registry=make_default_metric_registry(),
        split_result=build_run_splits_result(_uptrend_close().index, optimization.split),
    )


def _representative(result, params: dict):
    for candidate in (result.best, result.median, result.worst):
        if candidate.params == params:
            return candidate
    raise AssertionError(f"no representative with params {params}")


def _window_starts(set_: str) -> dict[int, int]:
    splitter = vbt.Splitter.from_rolling(
        _uptrend_close().index, length=8, split=0.5, set_labels=["selection", "held_out"]
    )
    starts = splitter.apply(lambda range_: range_.start, vbt.Rep("range_"), set_=set_)
    return {label: int(start) for label, start in starts.items()}


def _selection_starts() -> dict[int, int]:
    return _window_starts("selection")


def _held_out_starts() -> dict[int, int]:
    return _window_starts("held_out")


def test_bare_slice_indicator_is_all_nan_when_lookback_meets_slice_length() -> None:
    """The bug: computing the indicator on the bare slice loses all warmup."""
    close = _uptrend_close()
    selection_slice = close.iloc[SLICE_LEN : 2 * SLICE_LEN]  # one 4-bar selection window

    bare = _warmup_precompute(selection_slice, 1, window=[WARMUP_WINDOW])
    bare_window = bare.window(slice(None), [(WARMUP_WINDOW,)])
    assert np.isnan(bare_window["mom"]).all()

    # Full-series precompute then slice the SAME window: warmup-complete, non-NaN.
    full = _warmup_precompute(close, 1, window=[WARMUP_WINDOW])
    full_window = full.window(slice(SLICE_LEN, 2 * SLICE_LEN), [(WARMUP_WINDOW,)])
    assert not np.isnan(full_window["mom"]).any()


def test_runner_full_series_precompute_lets_warmup_candidate_trade() -> None:
    """The fix: the warmup-sensitive candidate trades on every warmup-complete split."""
    result = _run([WARMUP_WINDOW])
    candidate = result.best  # single candidate fills all three slots
    assert candidate.params == {"window": WARMUP_WINDOW}

    starts = _selection_starts()
    warmup_complete = {s for s, start in starts.items() if start >= WARMUP_WINDOW}
    assert warmup_complete, "fixture should produce at least one warmup-complete split"

    for split_label, start in starts.items():
        total_return = candidate.selection_metrics[split_label]["total_return"]
        if start >= WARMUP_WINDOW:
            # Full-series warmup -> indicator non-NaN -> equal-weight buy in uptrend.
            assert total_return is not None and total_return > 0.0, (
                f"split {split_label} (start {start}) should trade after warmup fix"
            )
        else:
            # Window sits inside the series-initial warmup: correctly holds cash.
            assert total_return == 0.0 or total_return is None


def test_runner_excludes_candidate_whose_lookback_exceeds_full_history() -> None:
    """A candidate with no finite full-series indicator values is invalid, not worst."""
    result = _run([2, N_ROWS + 1])

    assert result.excluded_degenerate == 1
    # Distinguishability (story 7): the dropped candidate is reported as *invalid*
    # (lookback > full history), a subset of the generic degenerate count.
    assert result.excluded_invalid == 1
    assert result.excluded_invalid <= result.excluded_degenerate
    for candidate in (result.best, result.median, result.worst):
        assert candidate.params == {"window": 2}
        assert candidate.score > 0.0


def test_runner_reports_zero_excluded_invalid_when_all_candidates_are_valid() -> None:
    """No lookback>history candidate -> excluded_invalid is 0 (distinct from degenerate)."""
    result = _run([2, 3])

    assert result.excluded_invalid == 0


def test_runner_reuses_full_series_precompute_for_held_out_warmup() -> None:
    """Held-out uses the same store instead of recomputing indicators on bare slices."""
    result = _run([WARMUP_WINDOW])
    candidate = result.best

    starts = _held_out_starts()
    assert starts and min(starts.values()) >= WARMUP_WINDOW

    for split_label, start in starts.items():
        total_return = candidate.held_out_metrics[split_label]["total_return"]
        assert total_return is not None and total_return > 0.0, (
            f"held-out split {split_label} (start {start}) should use precomputed warmup"
        )


def test_seeded_up_front_sampling_is_deterministic() -> None:
    """One materialised candidate set, seeded -> identical grid for a fixed seed."""
    windows = [2, 3, 4, 5, 6, 7, 8]
    optimization = _optimization(search="random", random_subset=4, seed=11)

    first = _run(windows, optimization=optimization)
    second = _run(windows, optimization=optimization)

    for slot in ("best", "median", "worst"):
        a = getattr(first, slot)
        b = getattr(second, slot)
        assert a.params == b.params
        assert a.selection_metrics == b.selection_metrics


def test_candidate_metrics_are_isolated_from_the_chunk_they_share() -> None:
    """Store column-gathering parity: a candidate's metrics don't depend on which
    other candidates it is batched with (single-pass reference == grouped sweep)."""
    target = {"window": 2}
    alone = _run([2])
    grouped = _run([2, 4, 6])

    alone_metrics = _representative(alone, target).selection_metrics
    grouped_metrics = _representative(grouped, target).selection_metrics
    assert alone_metrics == grouped_metrics


def test_parallel_and_sequential_selection_grids_are_byte_identical(monkeypatch) -> None:
    """Phase 1 keeps mono-chunk/pathos parallelism; forcing a single sequential
    mono-chunk yields the same selection metrics (no fan-out/ordering bug)."""
    from research.aegis_research.optimization import runner

    real_parameterized = runner.vbt.parameterized

    def sequential(func, **kwargs):
        # Collapse to one in-process mono-chunk (drop the pathos engine).
        forced = {k: v for k, v in kwargs.items() if k != "execute_kwargs"}
        forced["mono_n_chunks"] = 1
        return real_parameterized(func, **forced)

    windows = [2, 3, 4, 5, 6]
    parallel = _run(windows)

    monkeypatch.setattr(runner.vbt, "parameterized", sequential)
    sequential_result = _run(windows)

    for slot in ("best", "median", "worst"):
        assert getattr(parallel, slot).params == getattr(sequential_result, slot).params
        assert (
            getattr(parallel, slot).selection_metrics
            == getattr(sequential_result, slot).selection_metrics
        )


def test_invalid_cash_holder_never_outranks_money_losing_valid_candidate() -> None:
    """Regression: invalid cash-holder must not outrank a money-losing valid candidate.

    An Invalid Candidate (lookback > full history → all-NaN indicator → strategy
    holds cash → total_return == 0.0, finite) must never be selected as a
    representative, even when every valid candidate loses money (total_return < 0).

    Without masking the Invalid cash-holder scores a real 0.0 in the grid, which
    beats a money-losing valid candidate at, e.g., -0.86 if ranked by total_return.
    The verdict excludes the Invalid by key, so the cash-holder never reaches the
    three representative slots.

    Ranking metric MUST be total_return (finite-for-cash). Under Sharpe the
    cash-holder scores NaN and is excluded as non-trading regardless, so the
    regression would pass vacuously.
    """
    close = _downtrend_close()
    # window=2 is warmup-complete (buys equal-weight in a downtrend → loses money).
    # window=N_ROWS+1 is invalid (lookback > full history → all-NaN → cash hold).
    invalid_window = N_ROWS + 1
    windows = [2, invalid_window]

    optimization = _optimization()
    result = execute_optimization(
        close=close,
        open_=close,
        source=_source(windows),
        optimization=optimization,
        portfolio=make_portfolio_config(fees=0.0, slippage=0.0, direction="longonly"),
        report=make_report_config(),
        ranking=make_ranking_config(metric="total_return", min_weight=0.3),
        metric_registry=make_default_metric_registry(),
        split_result=build_run_splits_result(close.index, optimization.split),
    )

    invalid_params: dict = {"window": invalid_window}
    for candidate in (result.best, result.median, result.worst):
        assert candidate.params != invalid_params, (
            f"Invalid cash-holder {invalid_params!r} must not appear among "
            f"representatives; got score={candidate.score}, params={candidate.params}"
        )
        assert candidate.score < 0.0, (
            f"valid candidate {candidate.params} should lose money in a downtrend; "
            f"got score={candidate.score}"
        )

    # The Invalid Candidate is counted in the result.
    assert result.excluded_invalid == 1
    assert result.excluded_degenerate >= 1
    assert result.total_candidates == 2
