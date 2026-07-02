import numpy as np
import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.bundle import (
    DataContract,
    MarketDataBundle,
    _assert_latest_row_not_nan,
    _validate_market_data,
    validate_exposure,
)


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D")


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def _contract(
    instrument_ids: tuple[InstrumentId, ...] = (_id("A.XNAS"), _id("B.XNAS")),
    required_arrays=("Close",),
):
    return DataContract(
        instrument_ids=instrument_ids,
        required_arrays=required_arrays,
        base_currency="EUR",
        timeframe="1D",
    )


def _close(instrument_ids: tuple[InstrumentId, ...] = (_id("A.XNAS"), _id("B.XNAS")), n=3) -> MarketDataBundle:
    idx = _index(n)
    return MarketDataBundle(
        {"Close": pd.DataFrame({item: [1.0] * n for item in instrument_ids}, index=idx)}
    )


# --- validate_exposure -------------------------------------------------------

def test_validate_exposure_accepts_compliant_longonly_book() -> None:
    weights = pd.DataFrame({"A": [0.5], "B": [0.5]})
    validate_exposure(weights, gross_cap=1.0, net_cap=1.0, direction="longonly")


def test_validate_exposure_rejects_negative_weight_in_longonly() -> None:
    weights = pd.DataFrame({"A": [0.6], "B": [-0.1]})
    with pytest.raises(ValueError, match="violating direction 'longonly'"):
        validate_exposure(weights, gross_cap=1.0, direction="longonly")


def test_validate_exposure_rejects_gross_over_cap() -> None:
    weights = pd.DataFrame({"A": [0.8], "B": [0.8]})  # gross 1.6
    with pytest.raises(ValueError, match="gross exposure"):
        validate_exposure(weights, gross_cap=1.0, direction="longonly")


def test_validate_exposure_rejects_net_over_cap() -> None:
    weights = pd.DataFrame({"A": [0.6], "B": [0.6]})  # gross 1.2, net 1.2
    with pytest.raises(ValueError, match="net exposure"):
        validate_exposure(weights, gross_cap=2.0, net_cap=1.0, direction="both")


def test_validate_exposure_rejects_nonpositive_gross_cap() -> None:
    with pytest.raises(ValueError, match="gross_cap must be > 0"):
        validate_exposure(pd.DataFrame({"A": [0.5]}), gross_cap=0.0)


def test_validate_exposure_empty_book_is_noop() -> None:
    validate_exposure(pd.DataFrame(), gross_cap=1.0)  # no raise


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
