"""The exported bundle's DataContract carries the run's continuous-future roots (r8b.9 Slice D).

Slice A added ``DataContract.futures``; this wires the value through so the live strategy declares
its continuous universe identically to research — the same field, populated from the same config.
"""

from __future__ import annotations

from types import SimpleNamespace

from aegis_runtime import ComponentSpec
from nautilus_trader.model.identifiers import InstrumentId
from pydantic import TypeAdapter

from research.aegis_research import execution_bundle as execution_bundle_module
from research.aegis_research.configuration import DataConfig
from research.aegis_research.execution_bundle import (
    AssembledComponents,
    _bundle_contract,
    _instrument_bands,
    _instrument_ids,
)

_DATA = TypeAdapter(DataConfig)


def _components() -> AssembledComponents:
    return AssembledComponents(
        strategy=ComponentSpec(
            family="strategies",
            component_id="s",
            module="m",
            input_names=("Close",),
            output_names=("weight",),
            params={},
        ),
        indicators=(),
        source_hashes={},
        source_texts={},
        lookback_bars=5,
    )


def test_bundle_contract_carries_the_continuous_future_roots() -> None:
    data = _DATA.validate_python(
        {
            "arrays": ["OHLCV"],
            "base_currency": "USD",
            "instruments": ["AAPL.NASDAQ"],
            "futures": ["ES", "KC"],
            "start": "2024-01-01",
            "end": "2024-01-03",
            "timeframe": "1D",
        }
    )

    contract = _bundle_contract(
        SimpleNamespace(data=data),
        _components(),
        (
            InstrumentId.from_str("AAPL.NASDAQ"),
            InstrumentId.from_str("ES.XCME"),
            InstrumentId.from_str("KC.XNYM"),
        ),
    )

    assert contract.futures == ("ES", "KC")


def test_bundle_contract_has_no_roots_when_none_declared() -> None:
    data = _DATA.validate_python(
        {
            "arrays": ["Close"],
            "base_currency": "USD",
            "instruments": ["AAPL.NASDAQ"],
            "start": "2024-01-01",
            "end": "2024-01-03",
            "timeframe": "1D",
        }
    )

    contract = _bundle_contract(
        SimpleNamespace(data=data), _components(), (InstrumentId.from_str("AAPL.NASDAQ"),)
    )

    assert contract.futures == ()


def test_instrument_ids_do_not_open_catalog_without_futures(monkeypatch) -> None:
    data = _DATA.validate_python(
        {
            "arrays": ["Close"],
            "base_currency": "USD",
            "instruments": ["AAPL.NASDAQ"],
            "start": "2024-01-01",
            "end": "2024-01-03",
            "timeframe": "1D",
        }
    )

    def fail_if_called(_path):
        raise AssertionError("catalog should not be opened without futures")

    monkeypatch.setattr(execution_bundle_module, "catalog_data_port", fail_if_called)

    assert _instrument_ids(SimpleNamespace(data=data)) == (
        InstrumentId.from_str("AAPL.NASDAQ"),
    )


def test_instrument_ids_append_catalog_resolved_continuous_future_ids(monkeypatch) -> None:
    data = _DATA.validate_python(
        {
            "arrays": ["Close"],
            "base_currency": "USD",
            "instruments": ["AAPL.NASDAQ"],
            "futures": ["ES"],
            "path": "/catalog",
            "start": "2024-01-01",
            "end": "2024-01-03",
            "timeframe": "1D",
        }
    )
    calls: list[tuple[object, tuple[str, ...], str, str]] = []

    def fake_catalog_data_port(path):
        return f"port:{path}"

    def fake_continuous_instrument_ids(port, roots, *, start, end):
        calls.append((port, tuple(roots), start, end))
        return (InstrumentId.from_str("ES.XCME"),)

    monkeypatch.setattr(execution_bundle_module, "catalog_data_port", fake_catalog_data_port)
    monkeypatch.setattr(
        execution_bundle_module,
        "continuous_instrument_ids",
        fake_continuous_instrument_ids,
    )

    assert _instrument_ids(SimpleNamespace(data=data)) == (
        InstrumentId.from_str("AAPL.NASDAQ"),
        InstrumentId.from_str("ES.XCME"),
    )
    assert calls == [("port:/catalog", ("ES",), "2024-01-01", "2024-01-03")]


def test_instrument_bands_fan_out_sleeve_policy_to_every_contract_instrument() -> None:
    aapl = InstrumentId.from_str("AAPL.NASDAQ")
    continuous_es = InstrumentId.from_str("ES.XCME")
    config = SimpleNamespace(
        data=SimpleNamespace(instruments=["AAPL.NASDAQ"], futures=["ES"]),
        portfolio=SimpleNamespace(band_up=0.10, band_down=0.20, band_overrides={}),
    )

    bands = _instrument_bands(config, (aapl, continuous_es))

    assert set(bands) == {aapl, continuous_es}
    assert bands[aapl].up == 0.10
    assert bands[aapl].down == 0.20
    assert bands[continuous_es].up == 0.10
    assert bands[continuous_es].down == 0.20


def test_instrument_bands_resolve_per_instrument_overrides_to_contract_ids() -> None:
    aapl = InstrumentId.from_str("AAPL.NASDAQ")
    continuous_es = InstrumentId.from_str("ES.XCME")
    config = SimpleNamespace(
        data=SimpleNamespace(instruments=["AAPL.NASDAQ"], futures=["ES"]),
        portfolio=SimpleNamespace(
            band_up=0.10,
            band_down=0.20,
            band_overrides={
                "AAPL.NASDAQ": SimpleNamespace(up=0.01, down=0.03),
                "ES": SimpleNamespace(up=0.05, down=0.08),
            },
        ),
    )

    bands = _instrument_bands(config, (aapl, continuous_es))

    assert bands[aapl].up == 0.01
    assert bands[aapl].down == 0.03
    assert bands[continuous_es].up == 0.05
    assert bands[continuous_es].down == 0.08
