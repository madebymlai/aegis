from __future__ import annotations

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.currency import (
    MissingFxPairError,
    build_currency_conversion,
)
from tests.support.research.aegis_research.market_data_fixtures import (
    currency_pair_definition,
    equity_definition,
)

_AAPL = InstrumentId.from_str("AAPL.XNAS")
_BMW = InstrumentId.from_str("BMW.XETR")
_EURUSD = InstrumentId.from_str("EUR/USD.IDEALPRO")
_USDEUR = InstrumentId.from_str("USD/EUR.IDEALPRO")
_VOD = InstrumentId.from_str("VOD.XLON")
_INDEX = pd.date_range("2024-01-01", periods=2, freq="D")


def test_derives_native_to_base_rate_inverting_a_base_quote_pair() -> None:
    # EUR base book, USD-quoted AAPL, FX declared as EUR/USD (USD per 1 EUR).
    # USD->EUR is the inverse of that pair's price.
    eurusd = pd.Series([1.10, 1.25], index=_INDEX)

    conversion = build_currency_conversion(
        instruments={_AAPL: equity_definition(_AAPL, "USD"), _BMW: equity_definition(_BMW, "EUR")},
        fx_pairs={_EURUSD: currency_pair_definition(_EURUSD)},
        fx_close={_EURUSD: eurusd},
        base_currency="EUR",
    )

    assert _AAPL in conversion.rate_by_instrument
    assert conversion.rate_by_instrument[_AAPL].tolist() == pytest.approx([1 / 1.10, 1 / 1.25])
    # The base-currency leg needs no conversion, so it is absent from the map.
    assert _BMW not in conversion.rate_by_instrument


def test_derives_native_to_base_rate_directly_from_a_quote_base_pair() -> None:
    # Same book, but FX declared the other way round as USD/EUR (EUR per 1 USD) —
    # that price *is* the USD->EUR rate, no inversion.
    usdeur = pd.Series([0.90, 0.80], index=_INDEX)

    conversion = build_currency_conversion(
        instruments={_AAPL: equity_definition(_AAPL, "USD")},
        fx_pairs={_USDEUR: currency_pair_definition(_USDEUR)},
        fx_close={_USDEUR: usdeur},
        base_currency="EUR",
    )

    assert conversion.rate_by_instrument[_AAPL].tolist() == pytest.approx([0.90, 0.80])


def test_non_base_quote_currency_with_no_exchange_pair_fails_loud() -> None:
    # A GBP-quoted leg with only an EUR/USD pair declared has no path to EUR.
    conversion_args = {
        "instruments": {_VOD: equity_definition(_VOD, "GBP")},
        "fx_pairs": {_EURUSD: currency_pair_definition(_EURUSD)},
        "fx_close": {_EURUSD: pd.Series([1.10, 1.25], index=_INDEX)},
        "base_currency": "EUR",
    }

    with pytest.raises(MissingFxPairError, match="GBP"):
        build_currency_conversion(**conversion_args)
