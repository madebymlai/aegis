from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pandas as pd
import pytest

from research.aegis_research.metrics import MetricRegistry
from research.aegis_research.metrics.contracts import ExtractorSpec, MetricDefinition
from research.aegis_research.optimization.candidate_evidence import (
    candidate_rows_from_result,
)
from research.aegis_research.optimization.candidate_paths import (
    CandidateLookbacks,
    DevelopmentPlan,
    MaterializedCandidates,
)
from research.aegis_research.optimization.candidate_store import (
    CandidateStore,
    CandidateStoreError,
)
from research.aegis_research.optimization.candidate_validity import Verdicts
from research.aegis_research.optimization.continuous_evidence import (
    CONTINUOUS_SELECTION_EVIDENCE_SCHEMA_VERSION,
    build_continuous_evidence,
    matrix_from_evidence,
    matrix_to_evidence,
    observation_blocks_from_evidence,
)
from research.aegis_research.optimization.observation_blocks import (
    ObservationBlockAnalysis,
    ObservationBlocks,
)
from research.aegis_research.optimization.preflight import OptimizationPreflight
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)
from tests.support.research.aegis_research.factories import (
    make_optimization_config,
    make_ranking_config,
    make_report_config,
)


def _registry():
    registry = MetricRegistry()
    registry.register(
        MetricDefinition(
            id="total_return",
            title="Total Return",
            source_type="vbt_stats",
            unit="percent",
            value_semantics="complete-period return",
            boundary_semantics="native_continuous",
        ),
        ExtractorSpec(
            read=lambda portfolio, report: None,
            scale="percent",
            range_factory=lambda report: lambda portfolio, **bounds: None,
            range_kind="native_full_path_returns",
        ),
    )
    return registry.freeze()


def _case(candidate_count: int = 2, *, resolved_warmup_bars: int | None = None):
    index = pd.date_range("2024-01-01", periods=10)
    keys = tuple((position + 1,) for position in range(candidate_count))
    candidates = MaterializedCandidates(
        param_names=("window",),
        param_lists={"window": tuple(key[0] for key in keys)},
        keys=keys,
    )
    resolved_warmup = resolved_warmup_bars or candidate_count
    candidate_warmups = list(range(1, candidate_count + 1))
    candidate_warmups[-1] = resolved_warmup
    lookbacks = CandidateLookbacks(
        by_candidate=tuple(
            {
                "indicators/demo@demo": candidate_warmups[position],
                "strategies/demo@strategy": 0,
            }
            for position in range(candidate_count)
        ),
        candidate_warmup_bars=tuple(candidate_warmups),
        resolved_warmup_bars=resolved_warmup,
        scored_start=resolved_warmup,
    )
    blocks = ObservationBlocks.from_bounds(
        index,
        [(resolved_warmup, 6), (6, 10)],
        labels=["block-000", "block-001"],
    )
    candidate_index = pd.MultiIndex.from_tuples(keys, names=["window"])
    raw = pd.DataFrame(
        [[10.0 - position, 5.0 + position] for position in range(candidate_count)],
        index=candidate_index,
        columns=pd.MultiIndex.from_tuples(
            [("block-000", resolved_warmup, 6), ("block-001", 6, 10)],
            names=["observation_block", "start", "end"],
        ),
    )
    ranks = raw.rank(axis="index", ascending=False)
    evaluated = [
        EvaluatedCandidate(
            params={"window": key[0]},
            score=float(ranks.iloc[position].mean()),
            observation_block_metrics={
                "block-000": {"total_return": float(raw.iloc[position, 0])},
                "block-001": {"total_return": float(raw.iloc[position, 1])},
            },
            metrics={"total_return": float(raw.iloc[position].mean())},
        )
        for position, key in enumerate(keys)
    ]
    result = OptimizationResult(
        best=evaluated[0],
        median=evaluated[(candidate_count - 1) // 2],
        worst=evaluated[-1],
        total_candidates=candidate_count,
    )
    preflight = OptimizationPreflight(
        diagnostics={"schema_version": "optimization_preflight.v2"},
        plan=DevelopmentPlan(candidates=candidates, lookbacks=lookbacks),
        blocks=blocks,
    )
    analysis = ObservationBlockAnalysis(
        blocks=blocks,
        metric_matrices={"total_return": raw},
        ranking_ranks=ranks,
        full_period_metrics=pd.DataFrame(
            {"total_return": raw.mean(axis="columns")}, index=candidate_index
        ),
        verdicts=Verdicts(valid=set(keys)),
        result=result,
    )
    return index, preflight, analysis


@pytest.mark.parametrize("candidate_count", [1, 2])
def test_continuous_evidence_round_trips_protocol_and_matrix(candidate_count: int) -> None:
    index, preflight, analysis = _case(candidate_count)
    published = build_continuous_evidence(
        analysis=analysis,
        preflight=preflight,
        optimization=make_optimization_config(observation_block_bars=4),
        metric_registry=_registry(),
        ranking=make_ranking_config(metric="total_return"),
        report=make_report_config(),
        direction="longonly",
        fill_timing="next_close",
        data_start="2024-01-01",
    )

    evidence = published.execution
    assert evidence["schema_version"] == CONTINUOUS_SELECTION_EVIDENCE_SCHEMA_VERSION
    assert evidence["history_role"] == "development_selection"
    assert "held_out" not in repr(evidence).lower()
    assert "friedman" not in repr(evidence).lower()
    protocol = evidence["selection_identity"]["observation_block_protocol"]
    assert protocol["constructor"] == "Splitter.from_splits"
    assert protocol["application"] == {
        "attach_bounds": True,
        "iteration": "split_wise",
        "merge_func": "column_stack",
        "right_inclusive": False,
        "wrap_results": True,
    }
    assert protocol["native_rec_sim_range"] is False
    replay = evidence["selection_identity"]["replay_protocol"]
    assert replay["portfolio_optimizer"] == {
        "nonzero_only": False,
        "unique_only": False,
        "valid_only": True,
    }
    assert replay["portfolio"]["pf_method"] == "from_signals"
    assert replay["fill_timing"]["vbt_effective_delay_bars"] == 1
    assert evidence["warmup"]["resolved_warmup_bars"] == candidate_count
    assert evidence["warmup"]["maximum_drivers"][0]["candidate_position"] == candidate_count - 1
    assert evidence["selection_identity"]["metric_protocol"]["extractors"][
        "total_return"
    ]["kind"] == "native_full_path_returns"

    restored_blocks = observation_blocks_from_evidence(index, evidence)
    restored_matrix = matrix_from_evidence(
        evidence["raw_metric_matrices"]["total_return"]
    )
    assert restored_blocks.index.equals(analysis.blocks.index)
    assert restored_blocks.bounds == analysis.blocks.bounds
    assert restored_blocks.labels == analysis.blocks.labels
    pd.testing.assert_frame_equal(restored_matrix, analysis.metric_matrices["total_return"])
    assert restored_matrix.shape == (candidate_count, 2)


def test_candidate_identity_and_key_change_with_selection_protocol() -> None:
    _, preflight, analysis = _case()
    published = build_continuous_evidence(
        analysis=analysis,
        preflight=preflight,
        optimization=make_optimization_config(observation_block_bars=4),
        metric_registry=_registry(),
        ranking=make_ranking_config(metric="total_return"),
        report=make_report_config(),
        direction="longonly",
        fill_timing="next_close",
        data_start="2024-01-01",
    )
    changed_identity = deepcopy(published.selection_identity)
    changed_identity["observation_block_protocol"]["application"]["right_inclusive"] = True

    rows = candidate_rows_from_result(
        analysis.result,
        source_identity={"strategy": {"id": "demo"}},
        data_identity={"instruments": ["SYN.XNAS"]},
        book_settings={"direction": "longonly"},
        selection_identity=published.selection_identity,
    )
    changed_rows = candidate_rows_from_result(
        analysis.result,
        source_identity={"strategy": {"id": "demo"}},
        data_identity={"instruments": ["SYN.XNAS"]},
        book_settings={"direction": "longonly"},
        selection_identity=changed_identity,
    )

    assert rows[0]["candidate_key"] != changed_rows[0]["candidate_key"]
    assert "selection_metrics" not in rows[0]
    assert "held_out_metrics" not in rows[0]
    assert rows[0]["observation_block_metrics"]["block-000"]["total_return"] == 10.0


def test_selection_identity_changes_with_admissibility_and_metric_calendar() -> None:
    _, preflight, analysis = _case()
    common = {
        "analysis": analysis,
        "preflight": preflight,
        "optimization": make_optimization_config(observation_block_bars=4),
        "metric_registry": _registry(),
        "direction": "longonly",
        "fill_timing": "next_close",
        "data_start": "2024-01-01",
    }

    original = build_continuous_evidence(
        ranking=make_ranking_config(min_trades=0),
        report=make_report_config(freq="1D", year_freq="252D"),
        **common,
    )
    changed_admissibility = build_continuous_evidence(
        ranking=make_ranking_config(min_trades=5),
        report=make_report_config(freq="1D", year_freq="252D"),
        **common,
    )
    changed_calendar = build_continuous_evidence(
        ranking=make_ranking_config(min_trades=0),
        report=make_report_config(freq="2D", year_freq="252D"),
        **common,
    )

    assert original.selection_identity != changed_admissibility.selection_identity
    assert original.selection_identity != changed_calendar.selection_identity
    assert original.selection_identity["ranking"]["min_trades"] == 0
    assert original.selection_identity["metric_inputs"] == {
        "freq": "1D",
        "periods_per_year": 252,
        "year_freq": "252D",
    }


def test_evidence_publishes_only_authoritative_admissible_ranks() -> None:
    _, preflight, analysis = _case(3)
    admissible_ranks = pd.DataFrame(
        [[1.0, 1.0], [2.0, 2.0]],
        index=analysis.ranking_ranks.index[1:],
        columns=analysis.ranking_ranks.columns,
    )
    analysis = replace(
        analysis,
        ranking_ranks=admissible_ranks,
        verdicts=Verdicts(invalid={(1,)}, valid={(2,), (3,)}),
        result=replace(
            analysis.result,
            excluded_invalid=1,
            excluded_degenerate=1,
            total_candidates=3,
        ),
    )

    evidence = build_continuous_evidence(
        analysis=analysis,
        preflight=preflight,
        optimization=make_optimization_config(observation_block_bars=4),
        metric_registry=_registry(),
        ranking=make_ranking_config(metric="total_return"),
        report=make_report_config(),
        direction="longonly",
        fill_timing="next_close",
        data_start="2024-01-01",
    ).execution

    assert evidence["mean_ranks"] == [
        {"candidate_position": 1, "params": {"window": 2}, "value": 1.0},
        {"candidate_position": 2, "params": {"window": 3}, "value": 2.0},
    ]
    assert evidence["candidate_accounting"]["verdicts"] == [
        {"candidate_position": 0, "params": {"window": 1}, "verdict": "invalid"},
        {"candidate_position": 1, "params": {"window": 2}, "verdict": "valid"},
        {"candidate_position": 2, "params": {"window": 3}, "verdict": "valid"},
    ]


@pytest.mark.parametrize(
    ("path", "changed_value"),
    [
        (("replay_protocol", "fill_timing", "vbt_effective_delay_bars"), 2),
        (("metric_protocol", "extractors", "total_return", "kind"), "other"),
        (
            ("metric_protocol", "extractors", "total_return", "boundary_semantics"),
            "other",
        ),
        (("warmup", "candidates", 0, "component_lookbacks", "indicators/demo@demo"), 9),
        (("observation_block_protocol", "bounds", 0, "end"), 5),
    ],
)
def test_candidate_key_changes_for_each_pinned_execution_contract(
    path: tuple[str | int, ...], changed_value: object
) -> None:
    _, preflight, analysis = _case()
    published = build_continuous_evidence(
        analysis=analysis,
        preflight=preflight,
        optimization=make_optimization_config(observation_block_bars=4),
        metric_registry=_registry(),
        ranking=make_ranking_config(metric="total_return"),
        report=make_report_config(),
        direction="longonly",
        fill_timing="next_close",
        data_start="2024-01-01",
    )
    changed_identity = deepcopy(published.selection_identity)
    cursor = changed_identity
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = changed_value

    common = {
        "source_identity": {"strategy": {"id": "demo"}},
        "data_identity": {"instruments": ["SYN.XNAS"]},
        "book_settings": {"direction": "longonly"},
    }
    original = candidate_rows_from_result(
        analysis.result,
        selection_identity=published.selection_identity,
        **common,
    )
    changed = candidate_rows_from_result(
        analysis.result,
        selection_identity=changed_identity,
        **common,
    )

    assert original[0]["candidate_key"] != changed[0]["candidate_key"]


def test_matrix_round_trip_restores_timestamp_and_tuple_candidate_params() -> None:
    index = pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2024-01-01T12:30:00Z"), ("fast", 5))],
        names=["at", "settings"],
    )
    columns = pd.MultiIndex.from_tuples(
        [("block-000", 0, 2), ("block-001", 2, 4)],
        names=["observation_block", "start", "end"],
    )
    matrix = pd.DataFrame([[1.0, 2.0]], index=index, columns=columns)

    restored = matrix_from_evidence(matrix_to_evidence(matrix))

    pd.testing.assert_frame_equal(restored, matrix)


def test_maximum_lookback_change_moves_scored_interval_and_replay_identity() -> None:
    _, original_preflight, original_analysis = _case(resolved_warmup_bars=2)
    _, changed_preflight, changed_analysis = _case(resolved_warmup_bars=3)
    common = {
        "optimization": make_optimization_config(observation_block_bars=4),
        "metric_registry": _registry(),
        "ranking": make_ranking_config(metric="total_return"),
        "report": make_report_config(),
        "direction": "longonly",
        "fill_timing": "next_close",
        "data_start": "2024-01-01",
    }
    original = build_continuous_evidence(
        analysis=original_analysis,
        preflight=original_preflight,
        **common,
    )
    changed = build_continuous_evidence(
        analysis=changed_analysis,
        preflight=changed_preflight,
        **common,
    )

    assert original.selection_identity["scored_interval"]["start"] == 2
    assert changed.selection_identity["scored_interval"]["start"] == 3
    assert original.selection_identity["replay_protocol"]["portfolio"]["sim_start"] == 2
    assert changed.selection_identity["replay_protocol"]["portfolio"]["sim_start"] == 3
    assert original.selection_identity != changed.selection_identity


def test_candidate_store_rejects_stale_and_mismatched_selection_evidence(tmp_path) -> None:
    _, preflight, analysis = _case()
    published = build_continuous_evidence(
        analysis=analysis,
        preflight=preflight,
        optimization=make_optimization_config(observation_block_bars=4),
        metric_registry=_registry(),
        ranking=make_ranking_config(metric="total_return"),
        report=make_report_config(),
        direction="longonly",
        fill_timing="next_close",
        data_start="2024-01-01",
    )
    rows = candidate_rows_from_result(
        analysis.result,
        source_identity={"strategy": {"id": "demo"}},
        data_identity={"instruments": ["SYN.XNAS"]},
        book_settings={"direction": "longonly"},
        selection_identity=published.selection_identity,
    )
    provenance = {
        "schema_version": "candidate_store_provenance.v2",
        "source": {"strategy": {"id": "demo"}},
        "selection_identity": published.selection_identity,
    }

    stale = deepcopy(rows)
    stale[0]["schema_version"] = "candidate_eval_row.v2"
    with (
        CandidateStore(tmp_path / "stale" / "candidates.sqlite3") as store,
        pytest.raises(CandidateStoreError, match="schema_version"),
    ):
        store.insert_completed_run(
            run_id="run-stale", candidate_rows=stale, provenance=provenance
        )

    mismatched = deepcopy(provenance)
    mismatched["selection_identity"]["ranking"]["metric"] = "sharpe_ratio"
    with (
        CandidateStore(tmp_path / "mismatch" / "candidates.sqlite3") as store,
        pytest.raises(CandidateStoreError, match="selection identity"),
    ):
        store.insert_completed_run(
            run_id="run-mismatch", candidate_rows=rows, provenance=mismatched
        )


@pytest.mark.parametrize(
    ("path", "changed_value"),
    [
        (("replay_protocol", "implementation_fingerprint"), "altered"),
        (("replay_protocol", "portfolio", "pf_method"), "from_orders"),
        (
            (
                "observation_block_protocol",
                "application",
                "right_inclusive",
            ),
            True,
        ),
        (
            ("metric_protocol", "candidate_vector_contract"),
            "scalar_candidate.v1",
        ),
        (("metric_protocol", "extractors", "total_return", "kind"), "other"),
        (("ranking", "score"), "raw_metric"),
        (("trial_lineage", "search"), "other"),
    ],
)
def test_candidate_store_rejects_altered_selection_semantics(
    tmp_path, path: tuple[str, ...], changed_value: object
) -> None:
    _, preflight, analysis = _case()
    published = build_continuous_evidence(
        analysis=analysis,
        preflight=preflight,
        optimization=make_optimization_config(observation_block_bars=4),
        metric_registry=_registry(),
        ranking=make_ranking_config(metric="total_return"),
        report=make_report_config(),
        direction="longonly",
        fill_timing="next_close",
        data_start="2024-01-01",
    )
    altered_identity = deepcopy(published.selection_identity)
    cursor = altered_identity
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = changed_value
    rows = candidate_rows_from_result(
        analysis.result,
        source_identity={"strategy": {"id": "demo"}},
        data_identity={"instruments": ["SYN.XNAS"]},
        selection_identity=altered_identity,
    )
    provenance = {
        "schema_version": "candidate_store_provenance.v2",
        "selection_identity": altered_identity,
    }

    with (
        CandidateStore(tmp_path / "altered" / "candidates.sqlite3") as store,
        pytest.raises(CandidateStoreError, match="invalid"),
    ):
        store.insert_completed_run(
            run_id="run-altered", candidate_rows=rows, provenance=provenance
        )


def test_candidate_store_rejects_row_params_that_disagree_with_identity(tmp_path) -> None:
    _, preflight, analysis = _case()
    published = build_continuous_evidence(
        analysis=analysis,
        preflight=preflight,
        optimization=make_optimization_config(observation_block_bars=4),
        metric_registry=_registry(),
        ranking=make_ranking_config(metric="total_return"),
        report=make_report_config(),
        direction="longonly",
        fill_timing="next_close",
        data_start="2024-01-01",
    )
    rows = candidate_rows_from_result(
        analysis.result,
        source_identity={"strategy": {"id": "demo"}},
        data_identity={"instruments": ["SYN.XNAS"]},
        selection_identity=published.selection_identity,
    )
    rows[0]["params"] = {"window": 999}
    provenance = {
        "schema_version": "candidate_store_provenance.v2",
        "selection_identity": published.selection_identity,
    }

    with (
        CandidateStore(tmp_path / "params" / "candidates.sqlite3") as store,
        pytest.raises(CandidateStoreError, match=r"params.*identity"),
    ):
        store.insert_completed_run(
            run_id="run-params", candidate_rows=rows, provenance=provenance
        )
