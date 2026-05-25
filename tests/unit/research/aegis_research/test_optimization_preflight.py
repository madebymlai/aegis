from __future__ import annotations

import pandas as pd
import pytest
from vectorbtpro import vbt

from research.aegis_research.config import (
    OptimizationConfig,
    OptimizationEvidenceConfig,
    RunSplitConfig,
)
from research.aegis_research.optimization.preflight import (
    PreflightError,
    build_preflight,
)
from research.aegis_research.run_splits import RunSplit, RunSplitsResult


def test_preflight_reports_grid_shape_and_execution_policy() -> None:
    diagnostics = build_preflight(
        params={
            "fast_window": vbt.Param([5, 10]),
            "entry_threshold": vbt.Param([0.4, 0.45], level=1),
            "exit_threshold": vbt.Param([0.6, 0.55], level=1),
        },
        optimization=_optimization(execute={"chunk_len": "auto", "mono_chunk_len": 50}),
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
    assert diagnostics["estimated_result_cells"] == 96
    assert diagnostics["estimated_portfolio_broadcast_cells"] == 400
    assert diagnostics["retained_selection_grid_rows"] == 48
    assert diagnostics["selection_result_rows"] == 24
    assert diagnostics["candidate_row_count"] == 4
    assert diagnostics["leaderboard_row_count"] == 4
    assert diagnostics["promotion_row_count"] == 1
    assert diagnostics["execute"] == {"chunk_len": "auto", "mono_chunk_len": 50}


def test_preflight_allows_random_subset_when_sampled_shape_fits() -> None:
    diagnostics = build_preflight(
        params={
            "fast_window": vbt.Param(range(1_000)),
            "slow_window": vbt.Param(range(1_000)),
        },
        optimization=_optimization(search="random", random_subset=10),
        split_result=_split_result(split_count=1, selection_rows=5, held_out_rows=5),
        symbol_count=1,
        has_open_prices=False,
    )

    assert diagnostics["theoretical_combinations"] == 1_000_000
    assert diagnostics["sampled_combinations"] == 10
    assert diagnostics["estimated_portfolio_broadcast_cells"] == 400


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
                max_public_artifact_bytes=10_000,
            ),
            split_result=_split_result(split_count=2, selection_rows=5, held_out_rows=5),
            symbol_count=1,
            has_open_prices=False,
        )

    assert "max_public_artifact_bytes" in str(error.value)
    assert error.value.diagnostics["theoretical_combinations"] == 1_000_000
    assert error.value.diagnostics["sampled_combinations"] == 100
    assert error.value.diagnostics["estimated_public_rows"] == 1525


def test_preflight_return_grid_all_retains_all_set_grid_rows() -> None:
    diagnostics = build_preflight(
        params={"window": vbt.Param([5, 10, 20])},
        optimization=_optimization(return_grid="all"),
        split_result=_split_result(split_count=2, selection_rows=3, held_out_rows=2),
        symbol_count=1,
        has_open_prices=False,
    )

    assert diagnostics["retained_selection_grid_rows"] == 36
    assert diagnostics["retained_grid_rows"] == 72
    assert diagnostics["estimated_public_rows"] == 106


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


def test_preflight_computes_batch_budget_and_mono_chunk_len() -> None:
    diagnostics = build_preflight(
        params={"fast_window": vbt.Param([5, 10])},
        optimization=_optimization(),
        split_result=_split_result(split_count=1, selection_rows=100, held_out_rows=50),
        symbol_count=2,
        has_open_prices=True,
    )
    # materialized_frame_count = 4 + 1(open) = 5
    # max_set_rows = max(100, 50) = 100
    # bytes_per_candidate = 2 symbols × 100 bars × 8 dtype × 5 frames = 8000
    assert diagnostics["max_set_rows"] == 100
    assert diagnostics["batch_bytes_per_candidate"] == 8000
    # default ceiling 2GB → floor(2_000_000_000 / 8000) = 250_000, capped to 2 candidates
    assert diagnostics["computed_mono_chunk_len"] == 2
    assert diagnostics["limits"]["max_batch_expansion_bytes"] == 2_000_000_000


def test_preflight_fails_closed_when_single_candidate_exceeds_batch_budget() -> None:
    # 2 symbols × 500 bars × 8 dtype × 5 frames = 40_000 bytes per candidate
    # ceiling 30_000 → even mono_chunk_len=1 doesn't fit → fail closed
    with pytest.raises(PreflightError, match="max_batch_expansion_bytes") as error:
        build_preflight(
            params={"window": vbt.Param([5, 10, 20])},
            optimization=_optimization(max_batch_expansion_bytes=30_000),
            split_result=_split_result(split_count=1, selection_rows=500, held_out_rows=200),
            symbol_count=2,
            has_open_prices=True,
        )
    diag = error.value.diagnostics
    assert diag["computed_mono_chunk_len"] == 0
    assert diag["batch_bytes_per_candidate"] == 40_000
    assert diag["max_set_rows"] == 500
    assert diag["symbol_count"] == 2
    assert diag["materialized_frame_count"] == 5


def test_preflight_proceeds_at_mono_chunk_len_one_boundary() -> None:
    # 2 symbols × 500 bars × 8 dtype × 5 frames = 40_000 bytes per candidate
    # ceiling exactly 40_000 → mono_chunk_len=1 fits → proceed
    diagnostics = build_preflight(
        params={"window": vbt.Param([5, 10, 20])},
        optimization=_optimization(max_batch_expansion_bytes=40_000),
        split_result=_split_result(split_count=1, selection_rows=500, held_out_rows=200),
        symbol_count=2,
        has_open_prices=True,
    )
    assert diagnostics["computed_mono_chunk_len"] == 1
    assert diagnostics["batch_bytes_per_candidate"] == 40_000


def test_preflight_return_grid_off_excludes_grid_rows_but_counts_public_payloads() -> None:
    diagnostics = build_preflight(
        params={"window": vbt.Param([5, 10, 20])},
        optimization=_optimization(return_grid="off"),
        split_result=_split_result(split_count=2, selection_rows=3, held_out_rows=2),
        symbol_count=1,
        has_open_prices=False,
    )

    assert diagnostics["retained_selection_grid_rows"] == 0
    assert diagnostics["retained_grid_rows"] == 0
    assert diagnostics["sampled_row_count"] == 3
    assert diagnostics["candidate_row_count"] == 3
    assert diagnostics["leaderboard_row_count"] == 3
    assert diagnostics["estimated_public_rows"] == 34


def _optimization(
    *,
    search: str = "grid",
    random_subset: int | None = None,
    seed: int | None = None,
    return_grid: str = "first",
    max_estimated_output_cells: int = 1_000_000,
    max_public_artifact_bytes: int = 1_000_000,
    max_batch_expansion_bytes: int = 2_000_000_000,
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
            max_batch_expansion_bytes=max_batch_expansion_bytes,
        ),
        random_subset=random_subset,
        seed=seed,
        execute=execute or {},
        evidence=OptimizationEvidenceConfig(return_grid=return_grid),
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
