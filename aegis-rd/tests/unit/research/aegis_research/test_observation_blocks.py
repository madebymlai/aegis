from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.metrics.contracts import (
    SOURCE_TYPE_CUSTOM,
    SOURCE_TYPE_VBT_STATS,
    ExtractorSpec,
    MetricDefinition,
)
from research.aegis_research.optimization.candidate_validity import Verdicts
from research.aegis_research.optimization.observation_blocks import (
    ObservationBlocks,
    apply_metric_to_blocks,
    apply_registered_metric_to_blocks,
    rank_observation_block_candidates,
)
from tests.support.research.aegis_research.factories import make_report_config


def _candidate_index(*values: int) -> pd.MultiIndex:
    return pd.MultiIndex.from_tuples([(value,) for value in values], names=["window"])


@pytest.mark.parametrize(
    "bounds",
    [[], [(0, 0)], [(-1, 2)], [(0, 5)], [(0, 2), (3, 4)], [(0, 3), (2, 4)]],
)
def test_observation_blocks_reject_invalid_or_noncontiguous_bounds(
    bounds: list[tuple[int, int]],
) -> None:
    with pytest.raises(ValueError, match="Observation Block"):
        ObservationBlocks.from_bounds(pd.RangeIndex(4), bounds)


def test_observation_blocks_reject_mismatched_or_duplicate_labels() -> None:
    index = pd.RangeIndex(4)

    with pytest.raises(ValueError, match="labels"):
        ObservationBlocks.from_bounds(index, [(0, 2), (2, 4)], labels=["only-one"])
    with pytest.raises(ValueError, match="labels"):
        ObservationBlocks.from_bounds(index, [(0, 2), (2, 4)], labels=["same", "same"])


def test_resolve_scored_interval_covers_rows_and_merges_final_remainder() -> None:
    index = pd.RangeIndex(13)

    blocks = ObservationBlocks.resolve_scored_interval(
        index,
        scored_start=3,
        block_bars=4,
    )

    assert blocks.bounds == ((3, 7), (7, 13))
    assert blocks.labels == ("block-000", "block-001")


def test_resolve_scored_interval_keeps_exact_complete_blocks() -> None:
    blocks = ObservationBlocks.resolve_scored_interval(
        pd.RangeIndex(11),
        scored_start=3,
        block_bars=4,
    )

    assert blocks.bounds == ((3, 7), (7, 11))


@pytest.mark.parametrize(("row_count", "scored_start", "block_bars"), [(7, 0, 4), (5, 4, 1)])
def test_resolve_scored_interval_requires_two_blocks(
    row_count: int,
    scored_start: int,
    block_bars: int,
) -> None:
    with pytest.raises(ValueError, match="at least two"):
        ObservationBlocks.resolve_scored_interval(
            pd.RangeIndex(row_count),
            scored_start=scored_start,
            block_bars=block_bars,
        )


def test_vbt_constructor_and_apply_contract_are_pinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = pd.date_range("2024-01-01", periods=6)
    candidate_index = _candidate_index(1, 2)
    portfolio = object()
    calls: dict[str, Any] = {}

    class FakeSplitter:
        def apply(self, callback: Any, *args: Any, **kwargs: Any) -> pd.DataFrame:
            calls["apply_args"] = args
            calls["apply_kwargs"] = kwargs
            vectors = [callback((0, 2), portfolio), callback((2, 6), portfolio)]
            return pd.concat(vectors, axis=1, keys=[("b0", 0, 2), ("b1", 2, 6)])

    def from_splits(*args: Any, **kwargs: Any) -> FakeSplitter:
        calls["constructor_args"] = args
        calls["constructor_kwargs"] = kwargs
        return FakeSplitter()

    monkeypatch.setattr(vbt.Splitter, "from_splits", from_splits)
    blocks = ObservationBlocks.from_bounds(index, [(0, 2), (2, 6)], labels=["b0", "b1"])
    seen: list[tuple[object, int, int]] = []

    def extractor(full_portfolio: object, *, sim_start: int, sim_end: int) -> pd.Series:
        seen.append((full_portfolio, sim_start, sim_end))
        return pd.Series([sim_start, sim_end], index=candidate_index, dtype=float)

    result = apply_metric_to_blocks(blocks, portfolio, extractor, candidate_index)

    assert calls["constructor_args"] == (
        index,
        [slice(0, 2), slice(2, 6)],
    )
    assert calls["constructor_kwargs"]["squeeze"] is False
    assert calls["constructor_kwargs"]["fix_ranges"] is True
    assert calls["constructor_kwargs"]["split_labels"].equals(
        pd.Index(["b0", "b1"], name="observation_block")
    )
    assert calls["constructor_kwargs"]["set_labels"].equals(pd.Index(["observation"], name="set"))
    assert isinstance(calls["apply_args"][0], vbt.Rep)
    assert calls["apply_args"][1] is portfolio
    assert calls["apply_kwargs"] == {
        "attach_bounds": True,
        "right_inclusive": False,
        "iteration": "split_wise",
        "merge_func": "column_stack",
        "wrap_results": True,
    }
    assert seen == [(portfolio, 0, 2), (portfolio, 2, 6)]
    assert result.shape == (2, 2)
    assert result.index.equals(candidate_index)


def test_metric_callback_rejects_scalar_collapse_before_stacking() -> None:
    blocks = ObservationBlocks.from_bounds(pd.RangeIndex(4), [(0, 2), (2, 4)])

    with pytest.raises(ValueError, match="CandidateMetricVector"):
        apply_metric_to_blocks(
            blocks,
            object(),
            lambda portfolio, *, sim_start, sim_end: 1.0,
            _candidate_index(1),
        )


def test_metric_callback_rejects_noncanonical_candidate_order() -> None:
    candidate_index = _candidate_index(1, 2)
    blocks = ObservationBlocks.from_bounds(pd.RangeIndex(4), [(0, 4)])

    with pytest.raises(ValueError, match="canonical Candidate Index"):
        apply_metric_to_blocks(
            blocks,
            object(),
            lambda portfolio, *, sim_start, sim_end: pd.Series(
                [2.0, 1.0], index=candidate_index[::-1]
            ),
            candidate_index,
        )


def test_one_candidate_remains_a_vector_and_two_dimensional_matrix() -> None:
    candidate_index = _candidate_index(1)
    blocks = ObservationBlocks.from_bounds(pd.RangeIndex(4), [(0, 2), (2, 4)])

    result = apply_metric_to_blocks(
        blocks,
        object(),
        lambda portfolio, *, sim_start, sim_end: pd.Series(
            [sim_end - sim_start], index=candidate_index, dtype=float
        ),
        candidate_index,
    )

    assert result.shape == (1, 2)
    assert result.index.equals(candidate_index)
    assert result.columns.names == ["observation_block", "start", "end"]
    assert result.columns.tolist() == [("block-000", 0, 2), ("block-001", 2, 4)]

    definition = MetricDefinition(
        id="score",
        title="Score",
        source_type=SOURCE_TYPE_CUSTOM,
        unit="ratio",
        value_semantics="test score",
    )
    selected = rank_observation_block_candidates(
        result,
        param_names=("window",),
        verdicts=Verdicts(valid={(1,)}),
        full_period_metrics=pd.DataFrame({"score": [999.0]}, index=candidate_index),
        definition=definition,
    ).result

    assert selected.best == selected.median == selected.worst
    assert selected.best.score == 1.0


def test_registered_metric_aligns_authored_levels_to_canonical_candidate_identity() -> None:
    blocks = ObservationBlocks.from_bounds(pd.RangeIndex(4), [(0, 2), (2, 4)])
    candidate_index = pd.MultiIndex.from_tuples([(1, 2), (3, 4)], names=["a", "b"])
    authored_index = pd.MultiIndex.from_tuples([(2, 1), (4, 3)], names=["b", "a"])
    definition = MetricDefinition(
        id="score",
        title="Score",
        source_type=SOURCE_TYPE_VBT_STATS,
        unit="ratio",
        value_semantics="test score",
    )
    spec = ExtractorSpec(
        read=lambda portfolio, report: None,
        range_factory=lambda report: (
            lambda portfolio, *, sim_start, sim_end: pd.Series(
                [sim_start + 1.0, sim_end + 1.0], index=authored_index
            )
        ),
    )

    result = apply_registered_metric_to_blocks(
        blocks,
        object(),
        object(),
        definition,
        spec,
        make_report_config(),
        candidate_index,
    )

    assert result.index.equals(candidate_index)
    assert result.iloc[:, 0].tolist() == [1.0, 3.0]
    assert result.iloc[:, 1].tolist() == [3.0, 5.0]


def test_registered_metric_restores_single_candidate_level_name_dropped_by_vbt() -> None:
    blocks = ObservationBlocks.from_bounds(pd.RangeIndex(4), [(0, 2), (2, 4)])
    candidate_index = pd.MultiIndex.from_tuples([(0,)], names=["candidate"])
    definition = MetricDefinition(
        id="score",
        title="Score",
        source_type=SOURCE_TYPE_VBT_STATS,
        unit="ratio",
        value_semantics="test score",
    )
    spec = ExtractorSpec(
        read=lambda portfolio, report: None,
        range_factory=lambda report: (
            lambda portfolio, *, sim_start, sim_end: pd.Series(
                [sim_end - sim_start], index=pd.RangeIndex(1), dtype=float
            )
        ),
    )

    result = apply_registered_metric_to_blocks(
        blocks,
        object(),
        object(),
        definition,
        spec,
        make_report_config(),
        candidate_index,
    )

    assert result.index.equals(candidate_index)
    assert result.to_numpy().tolist() == [[2.0, 2.0]]


def test_registered_metric_expands_vbt_candidate_key_index_to_canonical_levels() -> None:
    blocks = ObservationBlocks.from_bounds(pd.RangeIndex(4), [(0, 2), (2, 4)])
    candidate_index = pd.MultiIndex.from_tuples(
        [(1, 0.25), (3, 0.75)], names=["window", "threshold"]
    )
    collapsed_index = pd.Index([(1, 0.25), (3, 0.75)], tupleize_cols=False, name="candidate_id")
    definition = MetricDefinition(
        id="score",
        title="Score",
        source_type=SOURCE_TYPE_VBT_STATS,
        unit="ratio",
        value_semantics="test score",
    )
    spec = ExtractorSpec(
        read=lambda portfolio, report: None,
        range_factory=lambda report: (
            lambda portfolio, *, sim_start, sim_end: pd.Series(
                [sim_start + 1.0, sim_end + 1.0], index=collapsed_index
            )
        ),
    )

    result = apply_registered_metric_to_blocks(
        blocks,
        object(),
        object(),
        definition,
        spec,
        make_report_config(),
        candidate_index,
    )

    assert result.index.equals(candidate_index)
    assert result.iloc[:, 0].tolist() == [1.0, 3.0]


def test_mean_rank_beats_one_arbitrarily_large_block_win_and_ignores_full_metric() -> None:
    candidate_index = _candidate_index(1, 2, 3)
    metric_matrix = pd.DataFrame(
        [[1_000_000.0, 0.0, 0.0], [1.0, 1.0, 1.0], [-1.0, -1.0, -1.0]],
        index=candidate_index,
        columns=["b0", "b1", "b2"],
    )
    full_metrics = pd.DataFrame({"score": [1_000_000.0, 3.0, -3.0]}, index=candidate_index)
    definition = MetricDefinition(
        id="score",
        title="Score",
        source_type=SOURCE_TYPE_CUSTOM,
        unit="ratio",
        value_semantics="test score",
        direction="maximize",
    )

    result = rank_observation_block_candidates(
        metric_matrix,
        param_names=("window",),
        verdicts=Verdicts(valid=set(candidate_index.tolist())),
        full_period_metrics=full_metrics,
        definition=definition,
    ).result

    assert result.best.params == {"window": 2}
    assert result.median.params == {"window": 1}
    assert result.worst.params == {"window": 3}
    assert result.best.score == pytest.approx(4 / 3)


def test_published_ranks_are_the_exact_admissible_ranks_used_for_selection() -> None:
    candidate_index = _candidate_index(1, 2, 3)
    metric_matrix = pd.DataFrame(
        [[100.0, 100.0], [10.0, 20.0], [5.0, 15.0]],
        index=candidate_index,
        columns=["b0", "b1"],
    )
    definition = MetricDefinition(
        id="score",
        title="Score",
        source_type=SOURCE_TYPE_CUSTOM,
        unit="ratio",
        value_semantics="test score",
        direction="maximize",
    )

    ranking = rank_observation_block_candidates(
        metric_matrix,
        param_names=("window",),
        verdicts=Verdicts(invalid={(1,)}, valid={(2,), (3,)}),
        full_period_metrics=pd.DataFrame({"score": [100.0, 15.0, 10.0]}, index=candidate_index),
        definition=definition,
    )

    assert ranking.ranks.index.tolist() == [(2,), (3,)]
    assert ranking.ranks.to_numpy().tolist() == [[1.0, 1.0], [2.0, 2.0]]
    assert ranking.result.best.params == {"window": 2}
    assert ranking.result.best.score == 1.0
    assert ranking.result.worst.params == {"window": 3}
    assert ranking.result.worst.score == 2.0


@pytest.mark.parametrize(
    ("direction", "values"),
    [
        ("maximize", [[1.0, 1.0], [1.0, 1.0], [0.0, 0.0], [None, None]]),
        ("minimize", [[-1.0, -1.0], [-1.0, -1.0], [0.0, 0.0], [None, None]]),
    ],
)
def test_exact_rank_ties_use_parameter_order_for_odd_even_and_missing(
    direction: str, values: list[list[float | None]]
) -> None:
    candidate_index = _candidate_index(1, 2, 3, 4)
    matrix = pd.DataFrame(
        values,
        index=candidate_index,
        columns=["b0", "b1"],
    )
    definition = MetricDefinition(
        id="score",
        title="Score",
        source_type=SOURCE_TYPE_CUSTOM,
        unit="ratio",
        value_semantics="test score",
        direction=direction,
    )

    result = rank_observation_block_candidates(
        matrix,
        param_names=("window",),
        verdicts=Verdicts(valid=set(candidate_index.tolist())),
        full_period_metrics=pd.DataFrame(
            {"score": [999.0, -999.0, 0.0, 0.0]}, index=candidate_index
        ),
        definition=definition,
    ).result

    assert result.best.params == {"window": 1}
    assert result.median.params == {"window": 2}
    assert result.worst.params == {"window": 4}
