import numpy as np
import pandas as pd
import pytest

from aegis_runtime.exposure_validation import ExposureLimits, validate_exposure


def _index(periods: int = 1) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=periods)


def _book(weights: dict[str, list[float]], periods: int = 1) -> pd.DataFrame:
    return pd.DataFrame(weights, index=_index(periods))


def _candidate_frame(weights_by_candidate: dict[str, list[float]]) -> pd.DataFrame:
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


# --- ExposureLimits ------------------------------------------------------------

def test_limits_reject_nonpositive_gross_cap_fail_closed() -> None:
    with pytest.raises(ValueError, match="gross_cap must be > 0"):
        ExposureLimits(gross_cap=0.0)


def test_limits_reject_unknown_direction_fail_closed() -> None:
    with pytest.raises(ValueError, match="direction"):
        ExposureLimits(gross_cap=1.0, direction="sideways")


def test_limits_net_cap_defaults_to_gross_cap() -> None:
    assert ExposureLimits(gross_cap=1.5).net_cap == 1.5


def test_limits_keep_explicit_net_cap() -> None:
    assert ExposureLimits(gross_cap=1.5, net_cap=0.0).net_cap == 0.0


# --- single-book gate ------------------------------------------------------------

def test_signed_book_within_gross_cap_passes() -> None:
    # Σ|wᵢ| = 1.0 ≤ gross_cap, even though the signed sum (net) is 0.
    validate_exposure(_book({"A": [-0.5], "B": [0.5]}), ExposureLimits(gross_cap=1.0))


def test_gross_exposure_above_cap_is_rejected_fail_closed() -> None:
    # Σ|wᵢ| = 1.5 > gross_cap 1.0
    allocations = _book({"A": [-0.5], "B": [0.5], "C": [0.5]})

    with pytest.raises(ValueError, match="gross_cap"):
        validate_exposure(allocations, ExposureLimits(gross_cap=1.0))


def test_net_exposure_above_net_cap_is_rejected_fail_closed() -> None:
    # Σ|wᵢ| = 1.0 ≤ gross_cap, but net Σwᵢ = 1.0 > net_cap 0.2 (drifts net-long).
    allocations = _book({"A": [0.5], "B": [0.5]})

    with pytest.raises(ValueError, match="net_cap"):
        validate_exposure(allocations, ExposureLimits(gross_cap=1.0, net_cap=0.2))


def test_market_neutral_book_within_net_cap_passes() -> None:
    # Σ|wᵢ| = 2.0 ≤ gross_cap 2.0, net Σwᵢ = 0.0 ≤ net_cap (market-neutral).
    allocations = _book({"A": [1.0], "B": [-1.0]})

    validate_exposure(allocations, ExposureLimits(gross_cap=2.0, net_cap=0.0))


def test_negative_net_exposure_below_negative_net_cap_is_rejected() -> None:
    # net Σwᵢ = -1.0; |net| = 1.0 > net_cap 0.2 (drifts net-short).
    allocations = _book({"A": [-0.5], "B": [-0.5]})

    with pytest.raises(ValueError, match="net_cap"):
        validate_exposure(allocations, ExposureLimits(gross_cap=1.0, net_cap=0.2))


def test_net_cap_defaults_to_gross_cap_when_omitted() -> None:
    # net Σwᵢ = 1.0 = gross_cap; with no net_cap it defaults to gross and passes.
    validate_exposure(_book({"A": [0.5], "B": [0.5]}), ExposureLimits(gross_cap=1.0))


def test_leveraged_gross_cap_above_one_is_allowed() -> None:
    # Σ|wᵢ| = 1.6 ≤ gross_cap 2.0 (a leveraged book)
    validate_exposure(_book({"A": [-1.0], "B": [0.6]}), ExposureLimits(gross_cap=2.0))


def test_longonly_direction_rejects_negative_weight_fail_closed() -> None:
    allocations = _book({"A": [0.5], "B": [-0.5]})

    with pytest.raises(ValueError, match="longonly"):
        validate_exposure(allocations, ExposureLimits(gross_cap=1.0, direction="longonly"))


def test_shortonly_direction_rejects_positive_weight_fail_closed() -> None:
    allocations = _book({"A": [-0.5], "B": [0.5]})

    with pytest.raises(ValueError, match="shortonly"):
        validate_exposure(allocations, ExposureLimits(gross_cap=1.0, direction="shortonly"))


def test_shortonly_direction_admits_all_negative_book() -> None:
    allocations = _book({"A": [-0.5], "B": [-0.5], "C": [0.0]})

    validate_exposure(allocations, ExposureLimits(gross_cap=1.0, direction="shortonly"))


def test_longonly_sign_flip_caught_despite_passing_gross_and_net_caps() -> None:
    # A sign-flip in a long-only-intended book: [+.5, +.5] -> [-.5, +.5].
    # Σ|wᵢ| = 1.0 (passes gross_cap) and Σwᵢ = 0.0 (passes net_cap), yet the short
    # leg slips past both caps — only the sign guard catches it.
    allocations = _book({"A": [-0.5], "B": [0.5]})

    with pytest.raises(ValueError, match="longonly"):
        validate_exposure(
            allocations, ExposureLimits(gross_cap=1.0, net_cap=1.0, direction="longonly")
        )


def test_default_direction_admits_signed_book() -> None:
    validate_exposure(_book({"A": [0.5], "B": [-0.5]}), ExposureLimits(gross_cap=1.0))


def test_all_nan_row_passes_as_no_rebalance() -> None:
    allocations = _book({"A": [np.nan, 0.6], "B": [np.nan, -0.4]}, periods=2)

    validate_exposure(allocations, ExposureLimits(gross_cap=1.0))


def test_empty_frame_passes() -> None:
    validate_exposure(pd.DataFrame(), ExposureLimits(gross_cap=1.0))


# --- grouped gate ----------------------------------------------------------------

def _candidate_labels(columns: pd.MultiIndex) -> pd.Index:
    return columns.droplevel("symbol")


def test_grouped_frame_gates_each_group_independently() -> None:
    # candidate-a is fully invested both legs (gross 1.0); candidate-b idles.
    allocations = _candidate_frame({"candidate-a": [0.5, -0.5], "candidate-b": [0.0, 0.0]})

    validate_exposure(
        allocations,
        ExposureLimits(gross_cap=1.0, net_cap=0.0),
        group_by=_candidate_labels(allocations.columns),
    )


def test_grouped_breach_names_the_offending_group() -> None:
    # candidate-b breaches gross (Σ|wᵢ| = 1.5) while candidate-a stays within cap.
    allocations = _candidate_frame({"candidate-a": [0.5, 0.5], "candidate-b": [1.0, 0.5]})

    with pytest.raises(ValueError, match="group 'candidate-b' gross exposure"):
        validate_exposure(
            allocations,
            ExposureLimits(gross_cap=1.0),
            group_by=_candidate_labels(allocations.columns),
        )


def test_grouped_net_breach_names_the_offending_group() -> None:
    # candidate-b is market-directional (net 1.0 > net_cap 0.0); candidate-a is neutral.
    allocations = _candidate_frame({"candidate-a": [0.5, -0.5], "candidate-b": [0.5, 0.5]})

    with pytest.raises(ValueError, match="group 'candidate-b' net exposure"):
        validate_exposure(
            allocations,
            ExposureLimits(gross_cap=1.0, net_cap=0.0),
            group_by=_candidate_labels(allocations.columns),
        )


def test_describe_group_phrases_the_offender_in_caller_vocabulary() -> None:
    allocations = _candidate_frame({"candidate-a": [0.5, 0.5], "candidate-b": [1.0, 0.5]})

    with pytest.raises(ValueError, match="candidate 'candidate-b' gross exposure"):
        validate_exposure(
            allocations,
            ExposureLimits(gross_cap=1.0),
            group_by=_candidate_labels(allocations.columns),
            describe_group=lambda candidate: f"candidate {candidate!r}",
        )


def test_multi_level_labels_name_the_offending_tuple() -> None:
    columns = pd.MultiIndex.from_tuples(
        [(10, "fast", "A"), (10, "fast", "B"), (20, "slow", "A"), (20, "slow", "B")],
        names=["window", "mode", "symbol"],
    )
    allocations = pd.DataFrame([[0.4, 0.4, 0.9, 0.9]], index=_index(1), columns=columns)

    with pytest.raises(ValueError, match=r"group \(20, 'slow'\) gross exposure"):
        validate_exposure(
            allocations,
            ExposureLimits(gross_cap=1.0),
            group_by=columns.droplevel("symbol"),
        )


def test_group_by_length_mismatch_is_rejected_fail_closed() -> None:
    allocations = _book({"A": [0.5], "B": [0.5]})

    with pytest.raises(ValueError, match="group_by has 1 labels"):
        validate_exposure(allocations, ExposureLimits(gross_cap=1.0), group_by=["only-one"])


def test_grouped_sign_guard_covers_the_whole_frame() -> None:
    # The sign guard is shape-agnostic: a short leg in any group violates longonly.
    allocations = _candidate_frame({"candidate-a": [0.5, 0.5], "candidate-b": [0.5, -0.5]})

    with pytest.raises(ValueError, match="longonly"):
        validate_exposure(
            allocations,
            ExposureLimits(gross_cap=1.0, direction="longonly"),
            group_by=_candidate_labels(allocations.columns),
        )
