from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.metrics import make_metric_registry_for
from research.aegis_research.optimization.candidate_paths import (
    CandidatePathError,
    build_development_paths,
    materialize_candidates,
)
from research.aegis_research.optimization.observation_blocks import (
    ObservationBlocks,
    analyze_development_paths,
)
from research.aegis_research.optimization.precompute import (
    IndicatorPrecompute,
    build_candidate_index,
    candidate_keys,
)
from research.aegis_research.optimization.source import OptimizationSource
from research.aegis_research.optimization.window_evaluation import ResolvedBook
from tests.support.research.aegis_research.factories import (
    make_optimization_config,
    make_portfolio_config,
    make_report_config,
    make_run_arrays,
)


def _source(
    lookbacks: Any,
    *,
    params: Mapping[str, vbt.Param] | None = None,
) -> OptimizationSource:
    candidate_params = dict(
        params
        or {
            "indicator.window": vbt.Param([1, 3]),
            "strategy.threshold": vbt.Param([0.25, 0.75]),
        }
    )

    def precompute(
        close: pd.DataFrame, n_candidates: int, **param_lists: Any
    ) -> IndicatorPrecompute:
        return IndicatorPrecompute(
            outputs={"indicator": np.ones((len(close.index), n_candidates))},
            candidate_index=build_candidate_index(param_lists),
            n_symbols=len(close.columns),
        )

    def simulate(
        close: pd.DataFrame,
        indicator_values: Mapping[str, np.ndarray],
        n_candidates: int,
        **param_lists: Any,
    ) -> pd.DataFrame:
        assert indicator_values["indicator"].shape == (len(close.index), n_candidates)
        keys = candidate_keys(param_lists)
        columns = pd.MultiIndex.from_tuples(
            [(key, symbol) for key in keys for symbol in close.columns],
            names=["candidate_id", "symbol"],
        )
        allocations = pd.DataFrame(np.nan, index=close.index, columns=columns)
        allocations.iloc[:-1, :] = 1.0
        return allocations

    return OptimizationSource(
        precompute=precompute,
        simulate=simulate,
        resolve_lookbacks=lookbacks,
        params=candidate_params,
        output_name="allocation",
        evidence={},
        diagnostics={},
        metadata={},
    )


def test_development_paths_resolve_one_common_start_from_the_sampled_grid() -> None:
    index = pd.date_range("2024-01-01", periods=8)
    close = pd.DataFrame({"A": np.arange(10.0, 18.0)}, index=index)
    seen: list[dict[str, Any]] = []

    def lookbacks(params: Mapping[str, Any]) -> Mapping[str, int]:
        seen.append(dict(params))
        return {
            "indicators/demo": params["indicator.window"],
            "strategies/demo": 2,
        }

    paths = build_development_paths(
        arrays=make_run_arrays(close=close, open_=close),
        source=_source(lookbacks),
        optimization=make_optimization_config(),
        book=ResolvedBook(
            make_portfolio_config(
                direction="longonly", fees=0.0, slippage=0.0, fill_timing="next_close"
            )
        ),
        report=make_report_config(),
        metric_registry=make_metric_registry_for(()),
        min_trades=2,
        ranking_metric="total_return",
    )

    assert paths.candidates.count == 4
    assert seen == [
        {"indicator.window": 1, "strategy.threshold": 0.25},
        {"indicator.window": 1, "strategy.threshold": 0.75},
        {"indicator.window": 3, "strategy.threshold": 0.25},
        {"indicator.window": 3, "strategy.threshold": 0.75},
    ]
    assert paths.lookbacks.candidate_warmup_bars == (2, 2, 3, 3)
    assert paths.lookbacks.resolved_warmup_bars == 3
    assert paths.lookbacks.scored_start == 3
    assert paths.replay.scored_start == 3
    assert paths.allocations.index.equals(index)
    assert paths.replay.values.index.equals(index)
    assert list(paths.full_period_metrics.index) == list(paths.candidates.keys)
    assert paths.verdicts.under_traded == set(paths.candidates.keys)


@pytest.mark.parametrize(
    ("resolved", "message"),
    [({}, "at least one Component"), ({"indicators/demo": -1}, "non-negative integer")],
)
def test_invalid_lookback_contract_fails_before_replay(
    monkeypatch: pytest.MonkeyPatch,
    resolved: Mapping[str, int],
    message: str,
) -> None:
    close = pd.DataFrame({"A": np.arange(10.0, 18.0)})
    replayed = False

    def replay_spy(*args: Any, **kwargs: Any) -> Any:
        nonlocal replayed
        replayed = True
        raise AssertionError("replay must not run")

    monkeypatch.setattr(
        "research.aegis_research.optimization.candidate_paths.replay_candidates",
        replay_spy,
    )

    with pytest.raises(CandidatePathError, match=message):
        build_development_paths(
            arrays=make_run_arrays(close=close, open_=close),
            source=_source(lambda params: resolved),
            optimization=make_optimization_config(),
            book=ResolvedBook(make_portfolio_config(fill_timing="next_close")),
            report=make_report_config(),
            metric_registry=make_metric_registry_for(()),
            min_trades=0,
            ranking_metric="total_return",
        )

    assert replayed is False


def test_fixed_seed_materializes_the_same_random_candidate_sample() -> None:
    params = {
        "indicator.window": vbt.Param([1, 2, 3, 4]),
        "strategy.threshold": vbt.Param([0.25, 0.5, 0.75]),
    }
    optimization = make_optimization_config(search="random", random_subset=5, seed=17)

    first = materialize_candidates(params, optimization)
    second = materialize_candidates(params, optimization)

    assert first == second
    assert first.count == 5
    assert len(set(first.keys)) == 5


def test_random_sample_changes_common_start_only_through_sampled_candidates() -> None:
    close = pd.DataFrame({"A": np.arange(10.0, 18.0)})
    params = {"indicator.window": vbt.Param([1, 2, 3, 4])}

    def build(seed: int):
        return build_development_paths(
            arrays=make_run_arrays(close=close, open_=close),
            source=_source(
                lambda candidate: {"indicators/demo": candidate["indicator.window"]},
                params=params,
            ),
            optimization=make_optimization_config(
                search="random", random_subset=1, seed=seed
            ),
            book=ResolvedBook(make_portfolio_config(fill_timing="next_close")),
            report=make_report_config(),
            metric_registry=make_metric_registry_for(()),
            min_trades=0,
            ranking_metric="total_return",
        )

    seed_zero = build(0)
    seed_one = build(1)

    assert seed_zero.candidates.keys == ((4,),)
    assert seed_zero.lookbacks.scored_start == 4
    assert seed_one.candidates.keys == ((2,),)
    assert seed_one.lookbacks.scored_start == 2
    assert build(0).lookbacks == seed_zero.lookbacks


def test_batched_full_period_metrics_match_sequential_candidate_replays() -> None:
    close = pd.DataFrame({"A": np.arange(10.0, 18.0)})
    book = ResolvedBook(
        make_portfolio_config(
            direction="longonly", fees=0.001, slippage=0.0, fill_timing="next_close"
        )
    )
    report = make_report_config()
    registry = make_metric_registry_for(())
    source = _source(lambda params: {"source": 1})
    batch = build_development_paths(
        arrays=make_run_arrays(close=close, open_=close),
        source=source,
        optimization=make_optimization_config(),
        book=book,
        report=report,
        metric_registry=registry,
        min_trades=0,
        ranking_metric="total_return",
    )

    for position, key in enumerate(batch.candidates.keys):
        scalar_params = {
            name: vbt.Param([key[level]])
            for level, name in enumerate(batch.candidates.param_names)
        }
        sequential = build_development_paths(
            arrays=make_run_arrays(close=close, open_=close),
            source=_source(lambda params: {"source": 1}, params=scalar_params),
            optimization=make_optimization_config(),
            book=book,
            report=report,
            metric_registry=registry,
            min_trades=0,
            ranking_metric="total_return",
        )
        pd.testing.assert_series_equal(
            batch.full_period_metrics.iloc[position],
            sequential.full_period_metrics.iloc[0],
            check_names=False,
        )


def test_development_paths_flow_unchanged_into_observation_analysis() -> None:
    index = pd.date_range("2024-01-01", periods=8)
    close = pd.DataFrame({"A": np.arange(10.0, 18.0)}, index=index)
    report = make_report_config()
    registry = make_metric_registry_for(())
    paths = build_development_paths(
        arrays=make_run_arrays(close=close, open_=close),
        source=_source(lambda params: {"source": 2}),
        optimization=make_optimization_config(),
        book=ResolvedBook(
            make_portfolio_config(
                direction="longonly", fees=0.0, slippage=0.0, fill_timing="next_close"
            )
        ),
        report=report,
        metric_registry=registry,
        min_trades=0,
        ranking_metric="total_return",
    )
    portfolio = paths.replay.portfolio

    analysis = analyze_development_paths(
        paths,
        ObservationBlocks.from_bounds(index, [(2, 5), (5, 8)]),
        report=report,
        metric_registry=registry,
        ranking_metric="total_return",
    )

    assert set(analysis.metric_matrices) == set(registry.ids())
    assert analysis.ranking_ranks.shape == (paths.candidates.count, 2)
    assert analysis.result.best.params == {
        "indicator.window": 1,
        "strategy.threshold": 0.25,
    }
    assert paths.replay.portfolio is portfolio
