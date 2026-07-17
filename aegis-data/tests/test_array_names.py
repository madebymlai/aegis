"""Public Array-name classification contract."""

from aegis_data.array_names import OHLCV_ARRAY_NAMES, is_bar_derived_array


def test_ohlcv_array_names_are_the_bar_derived_authority() -> None:
    expected = ("Open", "High", "Low", "Close", "Volume")

    names = OHLCV_ARRAY_NAMES

    assert names == expected


def test_array_name_classifier_distinguishes_custom_arrays() -> None:
    bar_derived = is_bar_derived_array("Close")
    custom = is_bar_derived_array("DealAvailable")

    assert bar_derived is True
    assert custom is False
