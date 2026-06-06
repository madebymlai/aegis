import numpy as np
import pandas as pd
import pytest

from research.aegis_research.portfolio_policy import (
    apply_executable_mask_and_terminal_liquidation,
    validate_signed_target_weights,
)


def _close_columns() -> pd.Index:
    return pd.Index(["A", "B", "C"], name="symbol")


def _index(periods: int = 4) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=periods)


def test_package_exports_only_two_public_symbols() -> None:
    import research.aegis_research.portfolio_policy as package

    assert set(package.__all__) == {
        "apply_executable_mask_and_terminal_liquidation",
        "validate_signed_target_weights",
    }


def test_convert_to_allocations_is_deleted() -> None:
    import research.aegis_research.portfolio_policy as package

    assert not hasattr(package, "convert_to_allocations")


def test_signed_weights_passthrough_returns_identical_frame_after_reindex() -> None:
    columns = _close_columns()
    index = _index()
    frame = pd.DataFrame(
        {
            "A": [0.5, np.nan, 0.0, 0.4],
            "B": [-0.5, np.nan, 0.0, -0.4],
            "C": [np.nan, np.nan, 0.0, np.nan],
        },
        index=index,
    )
    frame.columns = columns

    out = validate_signed_target_weights(
        frame,
        close_columns=columns,
        gross_cap=1.0,
    )

    assert out.columns.equals(columns)
    assert out.index.equals(index)
    pd.testing.assert_frame_equal(out, frame.astype(float))


def test_negative_weights_are_accepted() -> None:
    columns = _close_columns()
    index = _index(1)
    frame = pd.DataFrame({"A": [-0.5], "B": [0.5], "C": [0.0]}, index=index)
    frame.columns = columns

    out = validate_signed_target_weights(frame, close_columns=columns, gross_cap=1.0)

    assert out.iloc[0].to_dict() == {"A": -0.5, "B": 0.5, "C": 0.0}


def test_gross_exposure_uses_absolute_sum_under_cap() -> None:
    columns = _close_columns()
    index = _index(1)
    # Σ|wᵢ| = 1.0 ≤ gross_cap, even though the signed sum (net) is 0.
    frame = pd.DataFrame({"A": [-0.5], "B": [0.5], "C": [0.0]}, index=index)
    frame.columns = columns

    out = validate_signed_target_weights(frame, close_columns=columns, gross_cap=1.0)

    assert out.iloc[0].to_dict() == {"A": -0.5, "B": 0.5, "C": 0.0}


def test_gross_exposure_above_cap_is_rejected_fail_closed() -> None:
    columns = _close_columns()
    index = _index(1)
    # Σ|wᵢ| = 1.5 > gross_cap 1.0
    frame = pd.DataFrame({"A": [-0.5], "B": [0.5], "C": [0.5]}, index=index)
    frame.columns = columns

    with pytest.raises(ValueError, match="gross_cap"):
        validate_signed_target_weights(frame, close_columns=columns, gross_cap=1.0)


def test_net_exposure_above_net_cap_is_rejected_fail_closed() -> None:
    columns = _close_columns()
    index = _index(1)
    # Σ|wᵢ| = 1.0 ≤ gross_cap, but net Σwᵢ = 1.0 > net_cap 0.2 (drifts net-long).
    frame = pd.DataFrame({"A": [0.5], "B": [0.5], "C": [0.0]}, index=index)
    frame.columns = columns

    with pytest.raises(ValueError, match="net_cap"):
        validate_signed_target_weights(
            frame, close_columns=columns, gross_cap=1.0, net_cap=0.2
        )


def test_market_neutral_book_within_net_cap_passes() -> None:
    columns = _close_columns()
    index = _index(1)
    # Σ|wᵢ| = 2.0 ≤ gross_cap 2.0, net Σwᵢ = 0.0 ≤ net_cap (market-neutral).
    frame = pd.DataFrame({"A": [1.0], "B": [-1.0], "C": [0.0]}, index=index)
    frame.columns = columns

    out = validate_signed_target_weights(
        frame, close_columns=columns, gross_cap=2.0, net_cap=0.0
    )

    assert out.iloc[0].to_dict() == pytest.approx({"A": 1.0, "B": -1.0, "C": 0.0})


def test_negative_net_exposure_below_negative_net_cap_is_rejected() -> None:
    columns = _close_columns()
    index = _index(1)
    # net Σwᵢ = -1.0; |net| = 1.0 > net_cap 0.2 (drifts net-short).
    frame = pd.DataFrame({"A": [-0.5], "B": [-0.5], "C": [0.0]}, index=index)
    frame.columns = columns

    with pytest.raises(ValueError, match="net_cap"):
        validate_signed_target_weights(
            frame, close_columns=columns, gross_cap=1.0, net_cap=0.2
        )


def test_net_cap_defaults_to_gross_cap_when_omitted() -> None:
    columns = _close_columns()
    index = _index(1)
    # net Σwᵢ = 1.0 = gross_cap; with no net_cap it defaults to gross and passes.
    frame = pd.DataFrame({"A": [0.5], "B": [0.5], "C": [0.0]}, index=index)
    frame.columns = columns

    out = validate_signed_target_weights(frame, close_columns=columns, gross_cap=1.0)

    assert out.iloc[0].to_dict() == pytest.approx({"A": 0.5, "B": 0.5, "C": 0.0})


def test_leveraged_gross_cap_above_one_is_allowed() -> None:
    columns = _close_columns()
    index = _index(1)
    # Σ|wᵢ| = 1.6 ≤ gross_cap 2.0 (a leveraged book)
    frame = pd.DataFrame({"A": [-1.0], "B": [0.6], "C": [0.0]}, index=index)
    frame.columns = columns

    out = validate_signed_target_weights(frame, close_columns=columns, gross_cap=2.0)

    assert out.iloc[0].to_dict() == pytest.approx({"A": -1.0, "B": 0.6, "C": 0.0})


def test_all_nan_row_passes_through_as_no_rebalance() -> None:
    columns = _close_columns()
    index = _index(2)
    frame = pd.DataFrame(
        {"A": [np.nan, 0.6], "B": [np.nan, -0.4], "C": [np.nan, 0.0]},
        index=index,
    )
    frame.columns = columns

    out = validate_signed_target_weights(frame, close_columns=columns, gross_cap=1.0)

    assert out.iloc[0].isna().all()
    assert out.iloc[1].to_dict() == pytest.approx({"A": 0.6, "B": -0.4, "C": 0.0})


def test_reordered_columns_are_realigned_to_close_columns() -> None:
    columns = _close_columns()
    index = _index(1)
    frame = pd.DataFrame({"C": [0.0], "A": [0.5], "B": [-0.5]}, index=index)

    out = validate_signed_target_weights(frame, close_columns=columns, gross_cap=1.0)

    assert list(out.columns) == ["A", "B", "C"]
    assert out.iloc[0].to_dict() == pytest.approx({"A": 0.5, "B": -0.5, "C": 0.0})


def test_symbol_mismatch_raises_with_named_symbol() -> None:
    columns = _close_columns()
    index = _index(1)
    frame = pd.DataFrame({"A": [0.5], "B": [0.5], "Z": [0.0]}, index=index)

    with pytest.raises(ValueError, match="missing|not present"):
        validate_signed_target_weights(frame, close_columns=columns, gross_cap=1.0)


def test_empty_frame_passes_through() -> None:
    columns = pd.Index([], name="symbol")
    frame = pd.DataFrame(index=_index(0), columns=columns)

    out = validate_signed_target_weights(frame, close_columns=columns, gross_cap=1.0)

    assert out.empty


def test_terminal_row_is_force_liquidated_to_zero_for_every_symbol() -> None:
    columns = _close_columns()
    index = _index(4)
    allocations = pd.DataFrame(
        {
            "A": [0.5, np.nan, 0.3, 0.7],
            "B": [-0.5, np.nan, -0.4, -0.2],
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
