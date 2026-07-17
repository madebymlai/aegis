import numpy as np
import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.bundle import (
    SLEEVE_GROSS_LIMIT,
    ComponentSpec,
    DataContract,
    LockedExecutionPlan,
    MarketDataMissingIndexError,
    MarketDataBundle,
    MissingIndexPolicy,
    _assert_latest_row_not_nan,
    _validate_market_data,
)
from aegis_runtime.drift_band import DriftBand
from aegis_runtime.exposure_validation import InvalidExposureLimits


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D")


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def _contract(
    instrument_ids: tuple[InstrumentId, ...] = (_id("A.XNAS"), _id("B.XNAS")),
    required_arrays=("Close",),
    missing_index=MissingIndexPolicy.DROP,
):
    return DataContract(
        instrument_ids=instrument_ids,
        required_arrays=required_arrays,
        base_currency="EUR",
        timeframe="1D",
        missing_index=missing_index,
    )


def _close(instrument_ids: tuple[InstrumentId, ...] = (_id("A.XNAS"), _id("B.XNAS")), n=3) -> MarketDataBundle:
    idx = _index(n)
    return MarketDataBundle(
        {"Close": pd.DataFrame({item: [1.0] * n for item in instrument_ids}, index=idx)}
    )


# --- LockedExecutionPlan exposure contract -----------------------------------

def _plan(direction: str) -> LockedExecutionPlan:
    return LockedExecutionPlan(
        strategy=ComponentSpec(
            family="strategy", component_id="s", module="m",
            input_names=(), output_names=(), params={},
        ),
        indicators=(),
        instrument_bands={_id("A.XNAS"): DriftBand.symmetric(0.0)},
        direction=direction,
    )


def test_locked_execution_plan_rejects_illegal_direction_at_construction() -> None:
    # An illegal direction must fail when the plan is built (bundle load), not on
    # the first weight computation.
    with pytest.raises(InvalidExposureLimits, match="direction must be one of"):
        _plan("sideways")


def test_locked_execution_plan_builds_unit_gross_exposure_limits() -> None:
    # The sleeve weight contract is fixed: unit gross, net bounded by gross.
    # Only direction is locked per bundle.
    limits = _plan("longonly").exposure_limits

    assert limits.gross_cap == SLEEVE_GROSS_LIMIT == 1.0
    assert limits.net_cap == SLEEVE_GROSS_LIMIT
    assert limits.direction == "longonly"


# --- _validate_market_data ---------------------------------------------------

def test_validate_market_data_accepts_matching_contract() -> None:
    _validate_market_data(_close(), _contract())  # no raise


def test_validate_market_data_accepts_native_futures_leg_id_contract() -> None:
    instrument_id = _id("ESZ6.XCME")
    prices = MarketDataBundle({"Close": pd.DataFrame({instrument_id: [1.0]}, index=_index(1))})

    _validate_market_data(prices, _contract(instrument_ids=(instrument_id,)))


def test_validate_market_data_rejects_array_column_symbol_mismatch() -> None:
    prices = MarketDataBundle(
        {"Close": pd.DataFrame({_id("A.XNAS"): [1.0], _id("X.XNAS"): [1.0]}, index=_index(1))}
    )
    with pytest.raises(ValueError, match="do not match"):
        _validate_market_data(prices, _contract())


def test_validate_market_data_rejects_missing_or_extra_arrays() -> None:
    instrument_ids = (_id("A.XNAS"), _id("B.XNAS"))
    prices = MarketDataBundle(
        {"Close": pd.DataFrame({instrument_ids[0]: [1.0], instrument_ids[1]: [1.0]}, index=_index(1)),
         "Open": pd.DataFrame({instrument_ids[0]: [1.0], instrument_ids[1]: [1.0]}, index=_index(1))}
    )
    with pytest.raises(ValueError, match=r"extra=\['Open'\]"):
        _validate_market_data(prices, _contract(required_arrays=("Close",)))


def test_validate_market_data_rejects_nonunique_index() -> None:
    dup = pd.DatetimeIndex(["2024-01-01", "2024-01-01"])
    instrument_ids = (_id("A.XNAS"), _id("B.XNAS"))
    prices = MarketDataBundle(
        {"Close": pd.DataFrame({instrument_ids[0]: [1.0, 1.0], instrument_ids[1]: [1.0, 1.0]}, index=dup)}
    )
    with pytest.raises(ValueError, match="index must be unique"):
        _validate_market_data(prices, _contract())


def test_validate_market_data_rejects_mismatched_indices_across_arrays() -> None:
    instrument_ids = (_id("A.XNAS"), _id("B.XNAS"))
    prices = MarketDataBundle({
        "Close": pd.DataFrame({instrument_ids[0]: [1.0], instrument_ids[1]: [1.0]}, index=_index(1)),
        "Open": pd.DataFrame({instrument_ids[0]: [1.0], instrument_ids[1]: [1.0]}, index=pd.DatetimeIndex(["2024-02-01"])),
    })
    with pytest.raises(ValueError, match="must share one index"):
        _validate_market_data(prices, _contract(required_arrays=("Close", "Open")))


def test_validate_market_data_rejects_nan_values_under_drop_policy() -> None:
    instrument_ids = (_id("A.XNAS"), _id("B.XNAS"))
    prices = MarketDataBundle(
        {
            "Close": pd.DataFrame(
                {instrument_ids[0]: [1.0], instrument_ids[1]: [np.nan]},
                index=_index(1),
            )
        }
    )

    with pytest.raises(MarketDataMissingIndexError, match="missing_index='drop'"):
        _validate_market_data(prices, _contract(instrument_ids=instrument_ids))


def test_validate_market_data_rejects_nan_values_under_raise_policy() -> None:
    instrument_ids = (_id("A.XNAS"), _id("B.XNAS"))
    prices = MarketDataBundle(
        {
            "Close": pd.DataFrame(
                {instrument_ids[0]: [1.0], instrument_ids[1]: [np.nan]},
                index=_index(1),
            )
        }
    )

    with pytest.raises(MarketDataMissingIndexError, match="missing_index='raise'"):
        _validate_market_data(
            prices,
            _contract(
                instrument_ids=instrument_ids,
                missing_index=MissingIndexPolicy.RAISE,
            ),
        )


def test_validate_market_data_allows_nan_values_under_nan_policy() -> None:
    instrument_ids = (_id("A.XNAS"), _id("B.XNAS"))
    prices = MarketDataBundle(
        {
            "Close": pd.DataFrame(
                {instrument_ids[0]: [1.0], instrument_ids[1]: [np.nan]},
                index=_index(1),
            )
        }
    )

    _validate_market_data(
        prices,
        _contract(instrument_ids=instrument_ids, missing_index=MissingIndexPolicy.NAN),
    )


# --- _assert_latest_row_not_nan ----------------------------------------------

def test_assert_latest_row_not_nan_raises_on_nan_tail() -> None:
    weights = pd.DataFrame({"A": [0.5, np.nan]})
    with pytest.raises(ValueError, match="latest weight row contains NaN"):
        _assert_latest_row_not_nan(weights)


def test_assert_latest_row_not_nan_passes_on_clean_tail() -> None:
    _assert_latest_row_not_nan(pd.DataFrame({"A": [np.nan, 0.5]}))  # only tail matters


# --- MarketDataBundle --------------------------------------------------------

def test_market_data_bundle_array_raises_on_missing_array() -> None:
    with pytest.raises(ValueError, match="market data array 'Open' was not supplied"):
        MarketDataBundle({"Close": pd.DataFrame()}).array("Open")
