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


@pytest.mark.parametrize(
    "field_name",
    [
        "source",
        "symbols",
        "provider",
        # The VBT-loader-era knobs retired with the market_data.v4 reshape: a
        # config still setting one fails loudly, naming the offending field.
        "missing_columns",
        "tz_localize",
        "tz_convert",
        "skip_on_error",
        "silence_warnings",
    ],
)
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
    with pytest.raises(ValidationError, match="bare root"):
        _DATA_ADAPTER.validate_python(
            {
                "arrays": ["Close"],
                "base_currency": "USD",
                "futures": [""],
                "start": "2024-01-01",
                "end": "2024-01-03",
            }
        )


def test_data_config_rejects_venue_qualified_futures_root() -> None:
    # A continuous-future root is a bare symbol; a venue-qualified id (which parses as an
    # InstrumentId) is rejected by the SAME shared validator live's DataContract uses.
    with pytest.raises(ValidationError, match="bare root"):
        _DATA_ADAPTER.validate_python(
            {
                "arrays": ["Close"],
                "base_currency": "USD",
                "futures": ["ES.XCME"],
                "start": "2024-01-01",
                "end": "2024-01-03",
            }
        )


def test_data_config_parses_a_declared_mark_mode_token_off_the_instrument() -> None:
    config = _DATA_ADAPTER.validate_python(
        {
            "arrays": ["Close"],
            "base_currency": "USD",
            "instruments": ["UEQC.IBIS:QUOTE", "AAPL.NASDAQ"],
            "start": "2024-01-01",
            "end": "2024-01-03",
        }
    )

    assert config.instruments == ["UEQC.IBIS", "AAPL.NASDAQ"]
    assert config.mark_modes == {"UEQC.IBIS": "QUOTE"}


def test_data_config_round_trips_parsed_mark_modes() -> None:
    # A config lock serializes the parsed form (bare ids + mark_modes); loading
    # it back yields the same declarations without a token.
    parsed = _DATA_ADAPTER.validate_python(
        {
            "arrays": ["Close"],
            "base_currency": "USD",
            "instruments": ["UEQC.IBIS:QUOTE"],
            "start": "2024-01-01",
            "end": "2024-01-03",
        }
    )

    reloaded = _DATA_ADAPTER.validate_python(
        {
            "arrays": ["Close"],
            "base_currency": "USD",
            "instruments": list(parsed.instruments),
            "mark_modes": dict(parsed.mark_modes),
            "start": "2024-01-01",
            "end": "2024-01-03",
        }
    )

    assert reloaded.instruments == ["UEQC.IBIS"]
    assert reloaded.mark_modes == {"UEQC.IBIS": "QUOTE"}


def test_data_config_rejects_an_unknown_mark_mode_token() -> None:
    with pytest.raises(ValidationError, match="unknown mark-mode token"):
        _DATA_ADAPTER.validate_python(
            {
                "arrays": ["Close"],
                "base_currency": "USD",
                "instruments": ["UEQC.IBIS:FOO"],
                "start": "2024-01-01",
                "end": "2024-01-03",
            }
        )


def test_data_config_rejects_conflicting_mark_mode_declarations() -> None:
    with pytest.raises(ValidationError, match="conflicting mark modes"):
        _DATA_ADAPTER.validate_python(
            {
                "arrays": ["Close"],
                "base_currency": "USD",
                "instruments": ["UEQC.IBIS:QUOTE"],
                "mark_modes": {"UEQC.IBIS": "MID"},
                "start": "2024-01-01",
                "end": "2024-01-03",
            }
        )


def test_data_config_rejects_a_mark_mode_token_on_an_exchange_leg() -> None:
    with pytest.raises(ValidationError, match="conversion-only"):
        _DATA_ADAPTER.validate_python(
            {
                "arrays": ["Close"],
                "base_currency": "USD",
                "instruments": ["AAPL.NASDAQ"],
                "exchange": ["EUR/USD.IDEALPRO:QUOTE"],
                "start": "2024-01-01",
                "end": "2024-01-03",
            }
        )
