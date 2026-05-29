from __future__ import annotations

import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.config import (
    OptimizationConfig,
    RunSplitConfig,
)
from research.aegis_research.optimization.preflight import (
    PreflightError,
    build_preflight,
)
from research.aegis_research.run_splits import RunSplit, RunSplitsResult


def test_preflight_reports_two_phase_shape_and_execution_policy() -> None:
    diagnostics = build_preflight(
        params={
            "fast_window": vbt.Param([5, 10]),
            "entry_threshold": vbt.Param([0.4, 0.45], level=1),
            "exit_threshold": vbt.Param([0.6, 0.55], level=1),
        },
        optimization=_optimization(execute={"chunk_len": "auto"}),
        split_result=_split_result(split_count=2, selection_rows=3, held_out_rows=2),
        symbol_count=2,
        has_open_prices=True,
    )

    assert diagnostics["schema_version"] == "optimization_preflight.v1"
    assert diagnostics["theoretical_combinations"] == 4
    assert diagnostics["conditioned_combinations"] == 4
    assert diagnostics["sampled_combinations"] == 4
    assert diagnostics["split_count"] == 2
    assert diagnostics["selection_rows"] == 6
    assert diagnostics["held_out_rows"] == 4
    assert diagnostics["symbol_count"] == 2
    assert diagnostics["metric_count"] == 6
    assert diagnostics["materialized_frame_count"] == 5
    assert diagnostics["held_out_candidates"] == 3
    # Phase 1: full 4-combo grid x 2 splits x 6 metrics. Phase 3: 3 reps x 2 x 6.
    assert diagnostics["selection_result_cells"] == 48
    assert diagnostics["held_out_result_cells"] == 36
    assert diagnostics["estimated_result_cells"] == 84
    # Phase 1 broadcast: 4 combos x 6 selection rows x 2 symbols x 5 frames.
    # Phase 3 broadcast: 3 reps x 4 held-out rows x 2 symbols x 5 frames.
    assert diagnostics["selection_broadcast_cells"] == 240
    assert diagnostics["held_out_broadcast_cells"] == 120
    assert diagnostics["estimated_portfolio_broadcast_cells"] == 360
    assert diagnostics["estimated_output_cells"] == 360
    # Public artifact: 3 role rows + 3 candidates x 2 splits x 2 sets + 1 lock.
    assert diagnostics["candidate_row_count"] == 3
    assert diagnostics["lock_row_count"] == 1
    assert diagnostics["estimated_public_rows"] == 16
    assert diagnostics["execute"] == {"chunk_len": "auto"}
    assert "max_batch_expansion_bytes" not in diagnostics["limits"]


def test_preflight_public_rows_reflect_three_candidate_publish() -> None:
    # A 500-combo selection grid still publishes exactly three representative
    # candidates — the public artifact never scaled back to a per-combo leaderboard.
    diagnostics = build_preflight(
        params={"window": vbt.Param(range(500))},
        optimization=_optimization(),
        split_result=_split_result(split_count=2, selection_rows=3, held_out_rows=2),
        symbol_count=1,
        has_open_prices=False,
    )

    assert diagnostics["sampled_combinations"] == 500
    assert diagnostics["candidate_row_count"] == 3
    assert diagnostics["estimated_public_rows"] == 3 + 3 * 2 * 2 + 1


def test_preflight_held_out_phase_scales_with_three_candidates_not_the_grid() -> None:
    diagnostics = build_preflight(
        params={"window": vbt.Param([5, 10, 20, 40])},
        optimization=_optimization(),
        split_result=_split_result(split_count=2, selection_rows=10, held_out_rows=4),
        symbol_count=1,
        has_open_prices=False,
    )

    assert diagnostics["sampled_combinations"] == 4
    assert diagnostics["held_out_candidates"] == 3
    assert diagnostics["selection_result_cells"] == 4 * 2 * 6
    assert diagnostics["held_out_result_cells"] == 3 * 2 * 6
    # Selection rows total = 10 x 2 splits; held-out rows total = 4 x 2; frames = 4.
    assert diagnostics["selection_broadcast_cells"] == 4 * 20 * 1 * 4
    assert diagnostics["held_out_broadcast_cells"] == 3 * 8 * 1 * 4
    assert diagnostics["estimated_result_cells"] == 4 * 2 * 6 + 3 * 2 * 6
    assert diagnostics["estimated_portfolio_broadcast_cells"] == 4 * 20 * 1 * 4 + 3 * 8 * 1 * 4


def test_preflight_held_out_candidates_clamp_to_a_small_grid() -> None:
    diagnostics = build_preflight(
        params={"window": vbt.Param([5])},
        optimization=_optimization(),
        split_result=_split_result(split_count=1, selection_rows=4, held_out_rows=2),
        symbol_count=1,
        has_open_prices=False,
    )

    assert diagnostics["sampled_combinations"] == 1
    assert diagnostics["held_out_candidates"] == 1
    assert diagnostics["held_out_result_cells"] == 1 * 1 * 6
    # Three role rows are still published even when the grid holds one candidate.
    assert diagnostics["candidate_row_count"] == 3


def test_preflight_allows_random_subset_when_sampled_shape_fits() -> None:
    diagnostics = build_preflight(
        params={
            "fast_window": vbt.Param(range(1_000)),
            "slow_window": vbt.Param(range(1_000)),
        },
        optimization=_optimization(search="random", random_subset=10, seed=42),
        split_result=_split_result(split_count=1, selection_rows=5, held_out_rows=5),
        symbol_count=1,
        has_open_prices=False,
    )

    assert diagnostics["theoretical_combinations"] == 1_000_000
    assert diagnostics["sampled_combinations"] == 10
    # Phase 1: 10 x 5 x 1 x 4 = 200. Phase 3: 3 x 5 x 1 x 4 = 60.
    assert diagnostics["estimated_portfolio_broadcast_cells"] == 260


def test_preflight_rejects_random_subset_above_executable_combinations() -> None:
    with pytest.raises(PreflightError, match="random_subset") as error:
        build_preflight(
            params={
                "fast_window": vbt.Param([2, 5]),
                "slow_window": vbt.Param([10, 20]),
            },
            optimization=_optimization(search="random", random_subset=100, seed=42),
            split_result=_split_result(split_count=1, selection_rows=5, held_out_rows=5),
            symbol_count=1,
            has_open_prices=False,
        )

    assert error.value.diagnostics["sampled_combinations"] == 4
    assert error.value.diagnostics["sampled_count_source"] == "shape_estimate"


def test_preflight_rejects_oversized_exhaustive_grid_before_execution() -> None:
    with pytest.raises(PreflightError) as error:
        build_preflight(
            params={
                "fast_window": vbt.Param(range(1_000)),
                "slow_window": vbt.Param(range(1_000)),
            },
            optimization=_optimization(max_estimated_output_cells=100),
            split_result=_split_result(split_count=1, selection_rows=5, held_out_rows=5),
            symbol_count=1,
            has_open_prices=False,
        )

    assert "max_estimated_output_cells" in str(error.value)
    assert error.value.diagnostics["theoretical_combinations"] == 1_000_000
    assert error.value.diagnostics["sampled_combinations"] == 1_000_000


def test_preflight_rejects_random_sample_above_evidence_budget() -> None:
    with pytest.raises(PreflightError) as error:
        build_preflight(
            params={
                "fast_window": vbt.Param(range(1_000)),
                "slow_window": vbt.Param(range(1_000)),
            },
            optimization=_optimization(
                search="random",
                random_subset=100,
                seed=42,
                max_public_artifact_bytes=10_000,
            ),
            split_result=_split_result(split_count=2, selection_rows=5, held_out_rows=5),
            symbol_count=1,
            has_open_prices=False,
        )

    assert "max_public_artifact_bytes" in str(error.value)
    assert error.value.diagnostics["theoretical_combinations"] == 1_000_000
    assert error.value.diagnostics["sampled_combinations"] == 100
    assert error.value.diagnostics["estimated_public_rows"] == 16


def test_preflight_conditioned_grid_uses_vbt_executable_combinations() -> None:
    diagnostics = build_preflight(
        params={
            "fast_window": vbt.Param([2, 5, 10], condition="fast_window < slow_window"),
            "slow_window": vbt.Param([3, 8]),
        },
        optimization=_optimization(),
        split_result=_split_result(split_count=1, selection_rows=3, held_out_rows=2),
        symbol_count=1,
        has_open_prices=False,
    )

    assert diagnostics["theoretical_combinations"] == 6
    assert diagnostics["conditioned_combinations"] == 3
    assert diagnostics["sampled_combinations"] == 3
    assert diagnostics["sampled_count_source"] == "vbt.combine_params"


def test_search_mode_is_exhaustive_for_non_random_search() -> None:
    diagnostics = build_preflight(
        params={"window": vbt.Param([5, 10, 20])},
        optimization=_optimization(),
        split_result=_split_result(split_count=1, selection_rows=3, held_out_rows=2),
        symbol_count=1,
        has_open_prices=False,
    )

    assert diagnostics["search_mode"] == "exhaustive"


def test_search_mode_is_random_when_subset_reduces_the_grid() -> None:
    diagnostics = build_preflight(
        params={
            "fast_window": vbt.Param(range(1_000)),
            "slow_window": vbt.Param(range(1_000)),
        },
        optimization=_optimization(search="random", random_subset=10, seed=42),
        split_result=_split_result(split_count=1, selection_rows=5, held_out_rows=5),
        symbol_count=1,
        has_open_prices=False,
    )

    assert diagnostics["sampled_combinations"] == 10
    assert diagnostics["search_mode"] == "random"


def test_search_mode_is_exhaustive_auto_when_subset_matches_total_combos() -> None:
    diagnostics = build_preflight(
        params={"fast_window": vbt.Param([2, 5]), "slow_window": vbt.Param([10, 20])},
        optimization=_optimization(search="random", random_subset=4, seed=42),
        split_result=_split_result(split_count=1, selection_rows=5, held_out_rows=5),
        symbol_count=1,
        has_open_prices=False,
    )

    # 4 executable combos == random_subset -> the min() runs every combo.
    assert diagnostics["sampled_combinations"] == 4
    assert diagnostics["search_mode"] == "exhaustive_auto"


def test_search_mode_exhaustive_auto_surfaced_when_subset_exceeds_combos() -> None:
    # Param locking reduces the grid below random_subset; the run fails closed,
    # but the evidence still classifies it as exhaustive_auto.
    with pytest.raises(PreflightError, match="random_subset") as error:
        build_preflight(
            params={"fast_window": vbt.Param([2, 5]), "slow_window": vbt.Param([10, 20])},
            optimization=_optimization(search="random", random_subset=100, seed=42),
            split_result=_split_result(split_count=1, selection_rows=5, held_out_rows=5),
            symbol_count=1,
            has_open_prices=False,
        )

    assert error.value.diagnostics["search_mode"] == "exhaustive_auto"


def _optimization(
    *,
    search: str = "grid",
    random_subset: int | None = None,
    seed: int | None = None,
    max_estimated_output_cells: int = 1_000_000,
    max_public_artifact_bytes: int = 1_000_000,
    execute: dict[str, object] | None = None,
) -> OptimizationConfig:
    return OptimizationConfig(
        search=search,
        split=RunSplitConfig(
            method="from_rolling",
            params={"length": 10, "split": 0.5},
            max_splits=100,
            max_estimated_output_cells=max_estimated_output_cells,
            max_public_artifact_bytes=max_public_artifact_bytes,
        ),
        random_subset=random_subset,
        seed=seed,
        execute=execute or {},
    )


def _split_result(
    *,
    split_count: int,
    selection_rows: int,
    held_out_rows: int,
) -> RunSplitsResult:
    splits = []
    for split_number in range(split_count):
        offset = split_number * (selection_rows + held_out_rows)
        selection_index = pd.RangeIndex(offset, offset + selection_rows)
        held_out_index = pd.RangeIndex(
            offset + selection_rows, offset + selection_rows + held_out_rows
        )
        splits.append(
            RunSplit(
                label=f"split_{split_number}",
                set_indices={"selection": selection_index, "held_out": held_out_index},
                selection_set="selection",
                held_out_set="held_out",
            )
        )
    return RunSplitsResult(
        splits=splits,
        metadata={"schema_version": "run_splits.v1", "n_splits": split_count},
    )
