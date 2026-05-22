import numpy as np
import pandas as pd
import pytest

from research.aegis_research.portfolio_policy import (
    apply_executable_mask_and_terminal_liquidation,
    convert_to_allocations,
)
from research.aegis_research.portfolio_policy.policy import (
    STRATEGY_ALLOCATION_OUTPUTS,
)


def _close_columns() -> pd.Index:
    return pd.Index(["A", "B", "C"], name="symbol")


def _index(periods: int = 4) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=periods)


def test_package_exports_only_two_public_symbols() -> None:
    import research.aegis_research.portfolio_policy as package

    assert set(package.__all__) == {
        "apply_executable_mask_and_terminal_liquidation",
        "convert_to_allocations",
    }


def test_target_weights_passthrough_returns_identical_frame_after_reindex() -> None:
    columns = _close_columns()
    index = _index()
    frame = pd.DataFrame(
        {
            "A": [0.5, np.nan, 0.0, 0.4],
            "B": [0.5, np.nan, 0.0, 0.4],
            "C": [np.nan, np.nan, 0.0, np.nan],
        },
        index=index,
    )
    frame.columns = columns

    out = convert_to_allocations(
        frame,
        "target_weights",
        close_columns=columns,
        target_exposure_cap=1.0,
    )

    assert out.columns.equals(columns)
    assert out.index.equals(index)
    pd.testing.assert_frame_equal(out, frame.astype(float))


def test_active_shape_equal_weights_selected_symbols() -> None:
    columns = _close_columns()
    index = _index(1)
    frame = pd.DataFrame(
        {"A": [True], "B": [True], "C": [False]},
        index=index,
    )

    out = convert_to_allocations(
        frame,
        "active",
        close_columns=columns,
        target_exposure_cap=1.0,
    )

    assert out.iloc[0].to_dict() == {"A": 0.5, "B": 0.5, "C": 0.0}


def test_scores_shape_equal_weights_non_nan_cells() -> None:
    columns = _close_columns()
    index = _index(1)
    frame = pd.DataFrame(
        {"A": [1.4], "B": [0.8], "C": [np.nan]},
        index=index,
    )

    out = convert_to_allocations(
        frame,
        "scores",
        close_columns=columns,
        target_exposure_cap=1.0,
    )

    assert out.iloc[0].to_dict() == {"A": 0.5, "B": 0.5, "C": 0.0}


def test_ranks_shape_equal_weights_under_smaller_cap() -> None:
    columns = pd.Index(["A", "B", "C", "D"], name="symbol")
    index = _index(1)
    frame = pd.DataFrame(
        {"A": [1.0], "B": [2.0], "C": [np.nan], "D": [np.nan]},
        index=index,
    )

    out = convert_to_allocations(
        frame,
        "ranks",
        close_columns=columns,
        target_exposure_cap=0.8,
    )

    assert out.iloc[0].to_dict() == pytest.approx(
        {"A": 0.4, "B": 0.4, "C": 0.0, "D": 0.0}
    )


def test_all_nan_row_in_scores_passes_through_as_nan() -> None:
    columns = _close_columns()
    index = _index(2)
    frame = pd.DataFrame(
        {
            "A": [np.nan, 0.6],
            "B": [np.nan, 0.4],
            "C": [np.nan, np.nan],
        },
        index=index,
    )

    out = convert_to_allocations(
        frame,
        "scores",
        close_columns=columns,
        target_exposure_cap=1.0,
    )

    assert out.iloc[0].isna().all()
    assert out.iloc[1].to_dict() == pytest.approx({"A": 0.5, "B": 0.5, "C": 0.0})


def test_all_false_active_row_returns_all_zero_row() -> None:
    columns = _close_columns()
    index = _index(1)
    frame = pd.DataFrame(
        {"A": [False], "B": [False], "C": [False]},
        index=index,
    )

    out = convert_to_allocations(
        frame,
        "active",
        close_columns=columns,
        target_exposure_cap=1.0,
    )

    assert out.iloc[0].to_dict() == {"A": 0.0, "B": 0.0, "C": 0.0}


def test_all_nan_active_row_is_no_rebalance() -> None:
    columns = _close_columns()
    index = _index(1)
    frame = pd.DataFrame(
        {"A": [np.nan], "B": [np.nan], "C": [np.nan]},
        index=index,
        dtype=object,
    )

    out = convert_to_allocations(
        frame,
        "active",
        close_columns=columns,
        target_exposure_cap=1.0,
    )

    assert out.iloc[0].isna().all()


def test_reorderd_columns_are_realigned_to_close_columns() -> None:
    columns = _close_columns()
    index = _index(1)
    frame = pd.DataFrame(
        {"C": [True], "A": [True], "B": [True]},
        index=index,
    )

    out = convert_to_allocations(
        frame,
        "active",
        close_columns=columns,
        target_exposure_cap=1.0,
    )

    assert list(out.columns) == ["A", "B", "C"]
    assert out.iloc[0].to_dict() == pytest.approx(
        {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}
    )


def test_symbol_mismatch_raises_with_named_symbol() -> None:
    columns = _close_columns()
    index = _index(1)
    frame = pd.DataFrame(
        {"A": [True], "B": [True], "Z": [True]},
        index=index,
    )

    with pytest.raises(ValueError, match="missing|not present"):
        convert_to_allocations(
            frame,
            "active",
            close_columns=columns,
            target_exposure_cap=1.0,
        )


def test_target_weights_with_negative_value_rejected() -> None:
    columns = _close_columns()
    index = _index(1)
    frame = pd.DataFrame(
        {"A": [-0.1], "B": [0.5], "C": [0.4]},
        index=index,
    )

    with pytest.raises(ValueError, match="negative|longonly"):
        convert_to_allocations(
            frame,
            "target_weights",
            close_columns=columns,
            target_exposure_cap=1.0,
        )


def test_target_weights_with_row_sum_above_cap_rejected() -> None:
    columns = _close_columns()
    index = _index(1)
    frame = pd.DataFrame(
        {"A": [0.5], "B": [0.5], "C": [0.5]},
        index=index,
    )

    with pytest.raises(ValueError, match="exceeds target_exposure_cap"):
        convert_to_allocations(
            frame,
            "target_weights",
            close_columns=columns,
            target_exposure_cap=1.0,
        )


def test_unknown_declared_shape_rejected_naming_contract() -> None:
    columns = _close_columns()
    index = _index(1)
    frame = pd.DataFrame({"A": [1.0], "B": [1.0], "C": [1.0]}, index=index)

    with pytest.raises(ValueError, match="unsupported declared_shape"):
        convert_to_allocations(
            frame,
            "entries",
            close_columns=columns,
            target_exposure_cap=1.0,
        )

    with pytest.raises(ValueError, match="unsupported declared_shape"):
        convert_to_allocations(
            frame,
            "momentum",
            close_columns=columns,
            target_exposure_cap=1.0,
        )


def test_strategy_allocation_outputs_membership() -> None:
    assert STRATEGY_ALLOCATION_OUTPUTS == frozenset(
        {"active", "scores", "ranks", "target_weights"}
    )


def test_direction_rejected_when_not_longonly() -> None:
    columns = _close_columns()
    index = _index(1)
    frame = pd.DataFrame({"A": [True], "B": [True], "C": [True]}, index=index)

    with pytest.raises(ValueError, match="longonly"):
        convert_to_allocations(
            frame,
            "active",
            close_columns=columns,
            target_exposure_cap=1.0,
            direction="both",
        )


def test_terminal_row_is_force_liquidated_to_zero_for_every_symbol() -> None:
    columns = _close_columns()
    index = _index(4)
    allocations = pd.DataFrame(
        {
            "A": [0.5, np.nan, 0.3, 0.7],
            "B": [0.5, np.nan, 0.4, 0.2],
            "C": [np.nan, np.nan, 0.3, 0.1],
        },
        index=index,
    )

    masked, diag = apply_executable_mask_and_terminal_liquidation(
        allocations, market_index=index
    )

    assert masked.iloc[-1].to_dict() == {"A": 0.0, "B": 0.0, "C": 0.0}
    assert diag["terminal_liquidation"] is True


def test_split_gap_row_is_masked_to_nan_and_diagnostic_incremented() -> None:
    market_index = pd.date_range("2024-01-01", periods=5)
    split_index = market_index[[0, 1, 3, 4]]
    allocations = pd.DataFrame(
        {
            "A": [0.5, 0.5, 0.5, 0.5],
            "B": [0.5, 0.5, 0.5, 0.5],
        },
        index=split_index,
    )

    masked, diag = apply_executable_mask_and_terminal_liquidation(
        allocations, market_index=market_index
    )

    assert masked.iloc[2].isna().all()
    assert masked.iloc[0].to_dict() == {"A": 0.5, "B": 0.5}
    assert masked.iloc[1].to_dict() == {"A": 0.5, "B": 0.5}
    assert masked.iloc[-1].to_dict() == {"A": 0.0, "B": 0.0}
    assert diag["non_executable_rows"] == 1
    assert diag["non_executable_by_symbol"] == {"A": 1, "B": 1}


def test_zero_row_in_non_terminal_non_gap_location_passes_through() -> None:
    index = _index(3)
    allocations = pd.DataFrame(
        {"A": [0.5, 0.0, 0.5], "B": [0.5, 0.0, 0.5]},
        index=index,
    )

    masked, _ = apply_executable_mask_and_terminal_liquidation(
        allocations, market_index=index
    )

    assert masked.iloc[1].to_dict() == {"A": 0.0, "B": 0.0}


def test_nan_row_passes_through_unchanged_except_terminal() -> None:
    index = _index(3)
    allocations = pd.DataFrame(
        {"A": [0.5, np.nan, 0.5], "B": [0.5, np.nan, 0.5]},
        index=index,
    )

    masked, _ = apply_executable_mask_and_terminal_liquidation(
        allocations, market_index=index
    )

    assert masked.iloc[0].to_dict() == {"A": 0.5, "B": 0.5}
    assert masked.iloc[1].isna().all()
    assert masked.iloc[-1].to_dict() == {"A": 0.0, "B": 0.0}


def test_multi_candidate_wide_frame_is_masked_and_terminally_liquidated() -> None:
    market_index = pd.date_range("2024-01-01", periods=5)
    split_index = market_index[[0, 1, 3, 4]]
    columns = pd.MultiIndex.from_product(
        [["candidate-a", "candidate-b"], ["A", "B"]],
        names=["candidate_id", "symbol"],
    )
    allocations = pd.DataFrame(0.5, index=split_index, columns=columns)

    masked, diag = apply_executable_mask_and_terminal_liquidation(
        allocations, market_index=market_index
    )

    assert masked.iloc[2].isna().all()
    assert (masked.iloc[-1] == 0.0).all()
    assert diag["non_executable_rows"] == 1
    assert diag["non_executable_by_symbol"] == {"A": 1, "B": 1}


def test_masking_without_market_index_only_force_liquidates_terminal() -> None:
    index = _index(4)
    allocations = pd.DataFrame(
        {"A": [0.5, 0.5, 0.5, 0.5], "B": [0.5, 0.5, 0.5, 0.5]},
        index=index,
    )

    masked, diag = apply_executable_mask_and_terminal_liquidation(
        allocations, market_index=None
    )

    assert masked.iloc[:-1].equals(allocations.iloc[:-1].astype(float))
    assert masked.iloc[-1].to_dict() == {"A": 0.0, "B": 0.0}
    assert diag["non_executable_rows"] == 0


def test_market_index_missing_simulation_row_raises() -> None:
    index = _index(3)
    market_index = index[[0, 2]]
    allocations = pd.DataFrame(
        {"A": [0.5, 0.5, 0.5], "B": [0.5, 0.5, 0.5]}, index=index
    )

    with pytest.raises(ValueError, match="market_index"):
        apply_executable_mask_and_terminal_liquidation(
            allocations, market_index=market_index
        )
