"""Currency conversion through the catalog load path (AC4 fail-loud, AC5 native).

These exercise the real catalog adapter: instrument definitions are resolved from
the catalog, the ``exchange:`` FX series feeds the conversion, and native prices
stay in the catalog while conversion is a per-consumer view.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research.aegis_research.data import load_market_data_result
from research.aegis_research.market_data.currency import MissingFxPairError
from research.aegis_research.market_data.panels import market_data_bundle
from tests.support.research.aegis_research.factories import make_data_config
from tests.support.research.aegis_research.market_data_fixtures import (
    instrument_id,
    seed_catalog_fx,
    seed_catalog_ohlcv,
)

_PERIODS = 45
_END = "2024-02-01"


def test_non_base_leg_with_no_matching_exchange_pair_fails_loud(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    seed_catalog_ohlcv(catalog, ["AAPL.XNAS"], periods=_PERIODS, currency="USD")
    seed_catalog_ohlcv(catalog, ["7203.XTKS"], periods=_PERIODS, currency="JPY")
    # The exchange only covers USD; the JPY leg has no path to the EUR base.
    seed_catalog_fx(catalog, "EUR/USD.IDEALPRO", periods=_PERIODS)
    config = make_data_config(
        arrays=["Close"],
        base_currency="EUR",
        instruments=["AAPL.XNAS", "7203.XTKS"],
        exchange=["EUR/USD.IDEALPRO"],
        start="2024-01-01",
        end=_END,
        path=str(catalog),
    )

    with pytest.raises(MissingFxPairError, match="JPY"):
        load_market_data_result(config, required_arrays=("Close",))


def test_non_base_book_with_no_exchange_declared_fails_loud(tmp_path: Path) -> None:
    # "No exchange: at all" is just the empty case of "no matching pair" — a USD book
    # on an EUR base must still fail loud, never run silently unconverted.
    catalog = tmp_path / "catalog"
    seed_catalog_ohlcv(catalog, ["AAPL.XNAS"], periods=_PERIODS, currency="USD")
    config = make_data_config(
        arrays=["Close"],
        base_currency="EUR",
        instruments=["AAPL.XNAS"],
        start="2024-01-01",
        end=_END,
        path=str(catalog),
    )

    with pytest.raises(MissingFxPairError, match="USD"):
        load_market_data_result(config, required_arrays=("Close",))


def test_catalog_keeps_native_prices_conversion_is_a_per_consumer_view(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    seed_catalog_ohlcv(catalog, ["AAPL.XNAS"], periods=_PERIODS, currency="USD")
    seed_catalog_fx(catalog, "EUR/USD.IDEALPRO", periods=_PERIODS)
    config = make_data_config(
        arrays=["Close"],
        base_currency="EUR",
        instruments=["AAPL.XNAS"],
        exchange=["EUR/USD.IDEALPRO"],
        start="2024-01-01",
        end=_END,
        path=str(catalog),
    )

    result = load_market_data_result(config, required_arrays=("Close",))
    aapl = instrument_id("AAPL.XNAS")
    native_bundle = market_data_bundle(result)
    native_close = native_bundle.array("Close")[aapl]

    # The conversion is carried as a separate view, not baked into native_data.
    assert result.currency_conversion is not None
    assert aapl in result.currency_conversion.rate_by_instrument

    converted_close = result.currency_conversion.apply(native_bundle.arrays)["Close"][aapl]
    # Catalog/native_data is native (USD); the base-currency (EUR) view differs from it.
    assert not converted_close.equals(native_close)
