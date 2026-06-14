import numpy as np
import pandas as pd
import pytest

from aegis_runtime.currency import (
    assemble_fx_rates,
    convert_arrays_to_base,
    convert_prices_to_base,
    required_fx_currencies,
    requires_conversion,
)


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D")


def test_requires_conversion_compares_major_currency_to_base() -> None:
    assert requires_conversion("USD", "EUR") is True
    assert requires_conversion("EUR", "EUR") is False
    # GBp (pence) is a minor unit of GBP — its major currency drives the decision.
    assert requires_conversion("GBp", "GBP") is False
    assert requires_conversion("GBp", "EUR") is True


def test_required_fx_currencies_excludes_base_and_resolves_minor_units() -> None:
    needed = required_fx_currencies(
        {"A": "USD", "B": "EUR", "C": "GBp"}, base_currency="EUR"
    )
    # USD foreign; GBp resolves to its major GBP (also foreign); EUR is base.
    assert needed == {"USD", "GBP"}


def test_assemble_fx_rates_ffills_calendar_gaps_and_keeps_leading_nan() -> None:
    index = _index(4)
    sparse = pd.Series([1.2, 1.4], index=index[[1, 3]])

    rates = assemble_fx_rates({"USD": sparse}, index)

    # day 0 has no prior value (leading NaN kept); day 2 forward-fills day 1.
    assert np.isnan(rates["USD"].iloc[0])
    assert rates["USD"].tolist()[1:] == [1.2, 1.2, 1.4]


def test_convert_prices_to_base_passes_through_base_currency_unchanged() -> None:
    index = _index(3)
    prices = pd.DataFrame({"B": [10.0, 11.0, 12.0]}, index=index)
    fx = pd.DataFrame(index=index)

    out = convert_prices_to_base(prices, {"B": "EUR"}, "EUR", fx)

    pd.testing.assert_series_equal(out["B"], prices["B"])


def test_convert_prices_to_base_divides_foreign_leg_by_fx_rate() -> None:
    index = _index(2)
    prices = pd.DataFrame({"A": [100.0, 125.0]}, index=index)
    fx = pd.DataFrame({"USD": [1.25, 1.25]}, index=index)

    out = convert_prices_to_base(prices, {"A": "USD"}, "EUR", fx)

    # base->quote EURUSD=1.25 => EUR price = USD price / 1.25
    assert out["A"].tolist() == [80.0, 100.0]


def test_convert_prices_to_base_scales_minor_units_then_passes_through_major() -> None:
    index = _index(2)
    prices = pd.DataFrame({"C": [500.0, 600.0]}, index=index)  # pence
    fx = pd.DataFrame(index=index)

    out = convert_prices_to_base(prices, {"C": "GBp"}, "GBP", fx)

    # 500 pence -> £5.00 (×0.01), then GBP == base so no FX division.
    assert out["C"].tolist() == [5.0, 6.0]


def test_convert_prices_to_base_raises_when_fx_series_is_missing() -> None:
    index = _index(2)
    prices = pd.DataFrame({"A": [100.0, 125.0]}, index=index)
    fx = pd.DataFrame(index=index)  # no USD column

    with pytest.raises(ValueError, match="no FX series for quote currency 'USD'"):
        convert_prices_to_base(prices, {"A": "USD"}, "EUR", fx)


def test_convert_arrays_to_base_converts_prices_but_leaves_volume_untouched() -> None:
    index = _index(2)
    close = pd.DataFrame({"A": [100.0, 125.0]}, index=index)
    volume = pd.DataFrame({"A": [10, 20]}, index=index)
    fx = pd.DataFrame({"USD": [1.25, 1.25]}, index=index)

    out = convert_arrays_to_base(
        {"Close": close, "Volume": volume}, {"A": "USD"}, "EUR", fx
    )

    assert out["Close"]["A"].tolist() == [80.0, 100.0]
    pd.testing.assert_frame_equal(out["Volume"], volume)  # non-price passes through
