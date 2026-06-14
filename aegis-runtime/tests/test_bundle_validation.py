import numpy as np
import pandas as pd
import pytest

from aegis_runtime.bundle import (
    DataContract,
    MarketDataBundle,
    _assert_latest_row_not_nan,
    _validate_fx_series_contract,
    _validate_market_data,
    validate_exposure,
)


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D")


def _contract(symbols=("A", "B"), required_arrays=("Close",), currency_by_symbol=None):
    currency_by_symbol = currency_by_symbol or {s: "EUR" for s in symbols}
    return DataContract(
        symbols=symbols,
        required_arrays=required_arrays,
        base_currency="EUR",
        required_fx_currencies=(),
        currency_by_symbol=currency_by_symbol,
        timeframe="1D",
    )


def _close(symbols=("A", "B"), n=3) -> MarketDataBundle:
    idx = _index(n)
    return MarketDataBundle({"Close": pd.DataFrame({s: [1.0] * n for s in symbols}, index=idx)})


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


def test_validate_market_data_rejects_array_column_symbol_mismatch() -> None:
    prices = MarketDataBundle({"Close": pd.DataFrame({"A": [1.0], "X": [1.0]}, index=_index(1))})
    with pytest.raises(ValueError, match="do not match"):
        _validate_market_data(prices, _contract())


def test_validate_market_data_rejects_missing_or_extra_arrays() -> None:
    prices = MarketDataBundle(
        {"Close": pd.DataFrame({"A": [1.0], "B": [1.0]}, index=_index(1)),
         "Open": pd.DataFrame({"A": [1.0], "B": [1.0]}, index=_index(1))}
    )
    with pytest.raises(ValueError, match=r"extra=\['Open'\]"):
        _validate_market_data(prices, _contract(required_arrays=("Close",)))


def test_validate_market_data_rejects_currency_map_symbol_mismatch() -> None:
    contract = _contract(symbols=("A", "B"), currency_by_symbol={"A": "EUR"})  # missing B
    with pytest.raises(ValueError, match="currency map symbols do not match"):
        _validate_market_data(_close(), contract)


def test_validate_market_data_rejects_nonunique_index() -> None:
    dup = pd.DatetimeIndex(["2024-01-01", "2024-01-01"])
    prices = MarketDataBundle({"Close": pd.DataFrame({"A": [1.0, 1.0], "B": [1.0, 1.0]}, index=dup)})
    with pytest.raises(ValueError, match="index must be unique"):
        _validate_market_data(prices, _contract())


def test_validate_market_data_rejects_mismatched_indices_across_arrays() -> None:
    prices = MarketDataBundle({
        "Close": pd.DataFrame({"A": [1.0], "B": [1.0]}, index=_index(1)),
        "Open": pd.DataFrame({"A": [1.0], "B": [1.0]}, index=pd.DatetimeIndex(["2024-02-01"])),
    })
    with pytest.raises(ValueError, match="must share one index"):
        _validate_market_data(prices, _contract(required_arrays=("Close", "Open")))


# --- _validate_fx_series_contract --------------------------------------------

def test_fx_series_contract_rejects_missing_required_currency() -> None:
    with pytest.raises(ValueError, match=r"missing=\['USD'\]"):
        _validate_fx_series_contract({}, ("USD",))


def test_fx_series_contract_rejects_extra_currency() -> None:
    with pytest.raises(ValueError, match=r"extra=\['JPY'\]"):
        _validate_fx_series_contract({"JPY": pd.Series(dtype=float)}, ())


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
