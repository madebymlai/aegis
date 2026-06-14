from __future__ import annotations

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from research.aegis_research.market_data.contracts import MarketDataBundle
from research.aegis_research.market_data.currency import (
    assemble_fx_rates,
    convert_bundle_to_base,
    convert_prices_to_base,
    required_fx_currencies,
)


def test_usd_column_is_converted_to_base_by_dividing_the_eur_to_usd_rate() -> None:
    index = pd.to_datetime(["2020-01-02", "2020-01-03"])
    prices = pd.DataFrame({"SGLN.L": [110.0, 105.0]}, index=index)
    # fx_rates carries the native EUR quote (e.g. EURUSD): units of the quote
    # currency per 1 EUR. Convert a quote-currency price to EUR by DIVIDING.
    fx_rates = pd.DataFrame({"USD": [1.10, 1.05]}, index=index)

    converted = convert_prices_to_base(
        prices,
        currency_by_symbol={"SGLN.L": "USD"},
        base_currency="EUR",
        fx_rates=fx_rates,
    )

    expected = pd.DataFrame({"SGLN.L": [100.0, 100.0]}, index=index)
    assert_frame_equal(converted, expected)


def test_base_currency_column_passes_through_unchanged() -> None:
    index = pd.to_datetime(["2020-01-02", "2020-01-03"])
    prices = pd.DataFrame({"VOOL.DE": [50.0, 52.0]}, index=index)
    # A base-currency leg needs no FX series at all (no EUR/EUR rate exists).
    fx_rates = pd.DataFrame(index=index)

    converted = convert_prices_to_base(
        prices,
        currency_by_symbol={"VOOL.DE": "EUR"},
        base_currency="EUR",
        fx_rates=fx_rates,
    )

    assert_frame_equal(converted, prices)


def test_gbp_minor_unit_is_normalised_then_converted_via_the_gbp_rate() -> None:
    index = pd.to_datetime(["2020-01-02", "2020-01-03"])
    # GBUS.L quotes in pence (GBp): the minor unit of GBP, 100 pence = 1 GBP.
    prices = pd.DataFrame({"GBUS.L": [5000.0, 5500.0]}, index=index)
    # EURGBP carries GBP per 1 EUR.
    fx_rates = pd.DataFrame({"GBP": [0.50, 0.55]}, index=index)

    converted = convert_prices_to_base(
        prices,
        currency_by_symbol={"GBUS.L": "GBp"},
        base_currency="EUR",
        fx_rates=fx_rates,
    )

    # 5000 pence -> 50 GBP / 0.50 = 100 EUR ; 5500 -> 55 GBP / 0.55 = 100 EUR.
    expected = pd.DataFrame({"GBUS.L": [100.0, 100.0]}, index=index)
    assert_frame_equal(converted, expected)


def test_missing_fx_series_for_a_declared_currency_fails_closed() -> None:
    index = pd.to_datetime(["2020-01-02", "2020-01-03"])
    prices = pd.DataFrame({"SGLN.L": [110.0, 105.0]}, index=index)
    fx_rates = pd.DataFrame(index=index)  # the USD rate is absent

    with pytest.raises(ValueError, match="USD"):
        convert_prices_to_base(
            prices,
            currency_by_symbol={"SGLN.L": "USD"},
            base_currency="EUR",
            fx_rates=fx_rates,
        )


def test_convert_bundle_converts_price_panels_but_leaves_volume_untouched() -> None:
    index = pd.to_datetime(["2020-01-02", "2020-01-03"])
    close = pd.DataFrame({"SGLN.L": [110.0, 105.0]}, index=index)
    volume = pd.DataFrame({"SGLN.L": [1000.0, 2000.0]}, index=index)
    fx_rates = pd.DataFrame({"USD": [1.10, 1.05]}, index=index)

    converted = convert_bundle_to_base(
        MarketDataBundle(arrays={"Close": close, "Volume": volume}),
        currency_by_symbol={"SGLN.L": "USD"},
        base_currency="EUR",
        fx_rates=fx_rates,
    )

    assert_frame_equal(
        converted.array("Close"),
        pd.DataFrame({"SGLN.L": [100.0, 100.0]}, index=index),
    )
    # Volume is a share count, not a price - it must NOT be divided by FX.
    assert_frame_equal(converted.array("Volume"), volume)


def test_required_fx_currencies_normalises_minor_units_and_excludes_base() -> None:
    needed = required_fx_currencies(
        {
            "VOOL.DE": "EUR",  # base - no FX series needed
            "SGLN.L": "USD",
            "IBC1.L": "USD",  # duplicate major collapses
            "GBUS.L": "GBp",  # minor unit -> its major GBP needs the series
        },
        base_currency="EUR",
    )
    assert needed == {"USD", "GBP"}


def test_assemble_fx_rates_aligns_pairs_to_index_forward_filling_gaps() -> None:
    index = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
    # USD pair is missing 01-06 (an FX holiday) - carry the last rate forward.
    usd = pd.Series(
        [1.10, 1.11], index=pd.to_datetime(["2020-01-02", "2020-01-03"])
    )

    rates = assemble_fx_rates({"USD": usd}, index=index)

    expected = pd.DataFrame({"USD": [1.10, 1.11, 1.11]}, index=index)
    assert_frame_equal(rates, expected)
