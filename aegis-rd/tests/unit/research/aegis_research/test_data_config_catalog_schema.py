from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from research.aegis_research.configuration import DataConfig

_DATA_ADAPTER = TypeAdapter(DataConfig)


def test_data_config_accepts_native_instrument_id_shape() -> None:
    config = _DATA_ADAPTER.validate_python(
        {
            "arrays": ["OHLCV"],
            "base_currency": "USD",
            "instruments": ["AAPL.NASDAQ", "ESZ6.XCME"],
            "exchange": ["EUR/USD.IDEALPRO"],
            "start": "2024-01-01",
            "end": "2024-01-03",
            "timeframe": "1D",
        }
    )

    assert not hasattr(config, "source")
    assert not hasattr(config, "tickers")
    assert not hasattr(config, "currency_by_symbol")
    assert config.instruments == ["AAPL.NASDAQ", "ESZ6.XCME"]
    assert config.native_instrument_ids == (
        "AAPL.NASDAQ",
        "ESZ6.XCME",
        "EUR/USD.IDEALPRO",
    )


@pytest.mark.parametrize("field_name", ["source", "symbols", "provider"])
def test_data_config_rejects_removed_legacy_fields(field_name: str) -> None:
    raw = {
        "arrays": ["Close"],
        "base_currency": "USD",
        "instruments": ["AAPL.NASDAQ"],
        "start": "2024-01-01",
        "end": "2024-01-03",
        field_name: "legacy",
    }

    with pytest.raises(ValidationError) as error:
        _DATA_ADAPTER.validate_python(raw)

    assert any(item["loc"] == (field_name,) for item in error.value.errors())


def test_data_config_rejects_exchange_id_as_tradeable_duplicate() -> None:
    with pytest.raises(ValidationError, match="both tradeable and exchange-only"):
        _DATA_ADAPTER.validate_python(
            {
                "arrays": ["Close"],
                "base_currency": "USD",
                "instruments": ["EUR/USD.IDEALPRO"],
                "exchange": ["EUR/USD.IDEALPRO"],
                "start": "2024-01-01",
                "end": "2024-01-03",
            }
        )


def test_data_config_requires_a_tradeable_source() -> None:
    with pytest.raises(ValidationError, match="at least one tradeable source"):
        _DATA_ADAPTER.validate_python(
            {
                "arrays": ["Close"],
                "base_currency": "USD",
                "exchange": ["EUR/USD.IDEALPRO"],
                "start": "2024-01-01",
                "end": "2024-01-03",
            }
        )


def test_data_config_accepts_bare_continuous_future_roots() -> None:
    config = _DATA_ADAPTER.validate_python(
        {
            "arrays": ["OHLCV"],
            "base_currency": "USD",
            "instruments": ["AAPL.NASDAQ"],
            "futures": ["ES", "KC"],
            "start": "2024-01-01",
            "end": "2024-01-03",
        }
    )

    assert config.futures == ["ES", "KC"]
    # Continuous roots are synthetic, never raw-read from the catalog, so they stay
    # out of the native-id request set.
    assert config.native_instrument_ids == ("AAPL.NASDAQ",)


def test_data_config_allows_a_futures_only_run() -> None:
    config = _DATA_ADAPTER.validate_python(
        {
            "arrays": ["OHLCV"],
            "base_currency": "USD",
            "futures": ["ES"],
            "start": "2024-01-01",
            "end": "2024-01-03",
        }
    )

    assert config.instruments == []
    assert config.futures == ["ES"]


def test_data_config_rejects_duplicate_futures_roots() -> None:
    with pytest.raises(ValidationError, match="duplicate futures"):
        _DATA_ADAPTER.validate_python(
            {
                "arrays": ["Close"],
                "base_currency": "USD",
                "futures": ["ES", "ES"],
                "start": "2024-01-01",
                "end": "2024-01-03",
            }
        )


def test_data_config_rejects_empty_futures_root() -> None:
    with pytest.raises(ValidationError, match="continuous-future root symbols"):
        _DATA_ADAPTER.validate_python(
            {
                "arrays": ["Close"],
                "base_currency": "USD",
                "futures": [""],
                "start": "2024-01-01",
                "end": "2024-01-03",
            }
        )
