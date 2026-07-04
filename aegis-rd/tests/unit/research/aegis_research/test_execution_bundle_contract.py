"""The exported bundle's DataContract carries the run's continuous-future roots (r8b.9 Slice D).

Slice A added ``DataContract.futures``; this wires the value through so the live strategy declares
its continuous universe identically to research — the same field, populated from the same config.
"""

from __future__ import annotations

from types import SimpleNamespace

from aegis_runtime import ComponentSpec, MissingIndexPolicy
from nautilus_trader.model.identifiers import InstrumentId
from pydantic import TypeAdapter

from research.aegis_research.configuration import DataConfig
from research.aegis_research.execution_bundle import (
    AssembledComponents,
    _bundle_contract,
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
            "missing_index": "drop",
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
    assert contract.missing_index is MissingIndexPolicy.DROP


def test_bundle_contract_carries_the_fx_conversion_legs() -> None:
    """Regression (aegis-rd-reyj): ``data.exchange`` FX pairs must ship in the
    contract, or the trader loads no FX data and every non-base-quoted leg's
    orders are silently dropped in sizing (the book runs tail-only)."""
    data = _DATA.validate_python(
        {
            "arrays": ["OHLCV"],
            "base_currency": "EUR",
            "instruments": ["LQDH.LSEETF"],
            "exchange": ["EUR/USD.IDEALPRO"],
            "start": "2024-01-01",
            "end": "2024-01-03",
            "timeframe": "1D",
            "missing_index": "drop",
        }
    )

    contract = _bundle_contract(
        SimpleNamespace(data=data),
        _components(),
        (InstrumentId.from_str("LQDH.LSEETF"),),
    )

    assert contract.exchange == (InstrumentId.from_str("EUR/USD.IDEALPRO"),)
    assert contract.instrument_ids == (InstrumentId.from_str("LQDH.LSEETF"),)


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
