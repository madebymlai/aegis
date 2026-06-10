import numpy as np
import pandas as pd
import pytest

from research.aegis_research.portfolio_policy import (
    apply_executable_mask_and_terminal_liquidation,
    assert_signed_allocations_within_caps,
)


def _symbol_columns() -> pd.Index:
    return pd.Index(["A", "B", "C"], name="symbol")


def _index(periods: int = 4) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=periods)


def _book(weights: dict[str, list[float]], periods: int = 1) -> pd.DataFrame:
    frame = pd.DataFrame(weights, index=_index(periods))
    frame.columns = _symbol_columns()
    return frame


def test_package_exports_expected_public_symbols() -> None:
    import research.aegis_research.portfolio_policy as package

    assert set(package.__all__) == {
        "apply_executable_mask_and_terminal_liquidation",
        "assert_signed_allocations_within_caps",
    }


def test_convert_to_allocations_is_deleted() -> None:
    import research.aegis_research.portfolio_policy as package

    assert not hasattr(package, "convert_to_allocations")


def test_validate_signed_target_weights_is_deleted() -> None:
    # The aligning validator had zero production callers; the simulation path is
    # gated by assert_signed_allocations_within_caps alone.
    import research.aegis_research.portfolio_policy as package

    assert not hasattr(package, "validate_signed_target_weights")


def test_signed_book_within_gross_cap_passes() -> None:
    # Σ|wᵢ| = 1.0 ≤ gross_cap, even though the signed sum (net) is 0.
    allocations = _book({"A": [-0.5], "B": [0.5], "C": [0.0]})

    assert_signed_allocations_within_caps(allocations, gross_cap=1.0)


def test_gross_exposure_above_cap_is_rejected_fail_closed() -> None:
    # Σ|wᵢ| = 1.5 > gross_cap 1.0
    allocations = _book({"A": [-0.5], "B": [0.5], "C": [0.5]})

    with pytest.raises(ValueError, match="gross_cap"):
        assert_signed_allocations_within_caps(allocations, gross_cap=1.0)


def test_net_exposure_above_net_cap_is_rejected_fail_closed() -> None:
    # Σ|wᵢ| = 1.0 ≤ gross_cap, but net Σwᵢ = 1.0 > net_cap 0.2 (drifts net-long).
    allocations = _book({"A": [0.5], "B": [0.5], "C": [0.0]})

    with pytest.raises(ValueError, match="net_cap"):
        assert_signed_allocations_within_caps(allocations, gross_cap=1.0, net_cap=0.2)


def test_market_neutral_book_within_net_cap_passes() -> None:
    # Σ|wᵢ| = 2.0 ≤ gross_cap 2.0, net Σwᵢ = 0.0 ≤ net_cap (market-neutral).
    allocations = _book({"A": [1.0], "B": [-1.0], "C": [0.0]})

    assert_signed_allocations_within_caps(allocations, gross_cap=2.0, net_cap=0.0)


def test_negative_net_exposure_below_negative_net_cap_is_rejected() -> None:
    # net Σwᵢ = -1.0; |net| = 1.0 > net_cap 0.2 (drifts net-short).
    allocations = _book({"A": [-0.5], "B": [-0.5], "C": [0.0]})

    with pytest.raises(ValueError, match="net_cap"):
        assert_signed_allocations_within_caps(allocations, gross_cap=1.0, net_cap=0.2)


def test_net_cap_defaults_to_gross_cap_when_omitted() -> None:
    # net Σwᵢ = 1.0 = gross_cap; with no net_cap it defaults to gross and passes.
    allocations = _book({"A": [0.5], "B": [0.5], "C": [0.0]})

    assert_signed_allocations_within_caps(allocations, gross_cap=1.0)


def test_leveraged_gross_cap_above_one_is_allowed() -> None:
    # Σ|wᵢ| = 1.6 ≤ gross_cap 2.0 (a leveraged book)
    allocations = _book({"A": [-1.0], "B": [0.6], "C": [0.0]})

    assert_signed_allocations_within_caps(allocations, gross_cap=2.0)


def test_nonpositive_gross_cap_is_rejected_fail_closed() -> None:
    allocations = _book({"A": [0.0], "B": [0.0], "C": [0.0]})

    with pytest.raises(ValueError, match="gross_cap"):
        assert_signed_allocations_within_caps(allocations, gross_cap=0.0)


def test_longonly_direction_rejects_negative_weight_fail_closed() -> None:
    # A long-only Run must not emit a short leg.
    allocations = _book({"A": [0.5], "B": [-0.5], "C": [0.0]})

    with pytest.raises(ValueError, match="longonly"):
        assert_signed_allocations_within_caps(
            allocations, gross_cap=1.0, direction="longonly"
        )


def test_shortonly_direction_rejects_positive_weight_fail_closed() -> None:
    # A short-only Run must not emit a long leg.
    allocations = _book({"A": [-0.5], "B": [0.5], "C": [0.0]})

    with pytest.raises(ValueError, match="shortonly"):
        assert_signed_allocations_within_caps(
            allocations, gross_cap=1.0, direction="shortonly"
        )


def test_shortonly_direction_admits_all_negative_book() -> None:
    # An all-negative book is a valid short-only Run (zeros are allowed).
    allocations = _book({"A": [-0.5], "B": [-0.5], "C": [0.0]})

    assert_signed_allocations_within_caps(
        allocations, gross_cap=1.0, direction="shortonly"
    )


def test_both_direction_admits_either_sign() -> None:
    allocations = _book({"A": [0.5], "B": [-0.5], "C": [0.0]})

    assert_signed_allocations_within_caps(allocations, gross_cap=1.0, direction="both")


def test_longonly_sign_flip_caught_despite_passing_gross_and_net_caps() -> None:
    # A sign-flip in a long-only-intended Run: [+.5, +.5] -> [-.5, +.5].
    # Σ|wᵢ| = 1.0 (passes gross_cap) and Σwᵢ = 0.0 (passes net_cap), yet the short
    # leg slips past both caps — only the sign guard catches it.
    allocations = _book({"A": [-0.5], "B": [0.5], "C": [0.0]})

    with pytest.raises(ValueError, match="longonly"):
        assert_signed_allocations_within_caps(
            allocations, gross_cap=1.0, net_cap=1.0, direction="longonly"
        )


def test_unknown_direction_is_rejected_fail_closed() -> None:
    allocations = _book({"A": [0.5], "B": [0.5], "C": [0.0]})

    with pytest.raises(ValueError, match="direction"):
        assert_signed_allocations_within_caps(
            allocations, gross_cap=1.0, direction="sideways"
        )


def test_default_direction_admits_signed_book() -> None:
    # No direction argument: default admits either sign (long-only callers stay green).
    allocations = _book({"A": [0.5], "B": [-0.5], "C": [0.0]})

    assert_signed_allocations_within_caps(allocations, gross_cap=1.0)


def test_all_nan_row_passes_as_no_rebalance() -> None:
    allocations = _book(
        {"A": [np.nan, 0.6], "B": [np.nan, -0.4], "C": [np.nan, 0.0]}, periods=2
    )

    assert_signed_allocations_within_caps(allocations, gross_cap=1.0)


def test_empty_frame_passes() -> None:
    allocations = pd.DataFrame(index=_index(0), columns=pd.Index([], name="symbol"))

    assert_signed_allocations_within_caps(allocations, gross_cap=1.0)


def _candidate_wide_frame(weights_by_candidate: dict[str, list[float]]) -> pd.DataFrame:
    columns = pd.MultiIndex.from_tuples(
        [
            (candidate, symbol)
            for candidate, weights in weights_by_candidate.items()
            for symbol in ("A", "B")[: len(weights)]
        ],
        names=["candidate_id", "symbol"],
    )
    values = [weight for weights in weights_by_candidate.values() for weight in weights]
    return pd.DataFrame([values], index=_index(1), columns=columns)


def test_candidate_wide_frame_gates_each_candidate_independently() -> None:
    # candidate-a is fully invested both legs (gross 1.0); candidate-b idles.
    allocations = _candidate_wide_frame(
        {"candidate-a": [0.5, -0.5], "candidate-b": [0.0, 0.0]}
    )

    assert_signed_allocations_within_caps(allocations, gross_cap=1.0, net_cap=0.0)


def test_candidate_wide_frame_names_the_breaching_candidate() -> None:
    # candidate-b breaches gross (Σ|wᵢ| = 1.5) while candidate-a stays within cap;
    # the error must name the offender, not just report a breach.
    allocations = _candidate_wide_frame(
        {"candidate-a": [0.5, 0.5], "candidate-b": [1.0, 0.5]}
    )

    with pytest.raises(ValueError, match="candidate-b"):
        assert_signed_allocations_within_caps(allocations, gross_cap=1.0)


def test_terminal_row_is_force_liquidated_to_zero_for_every_symbol() -> None:
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
