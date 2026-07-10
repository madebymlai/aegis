"""The exported bundle's DataContract carries the run's continuous-future roots (r8b.9 Slice D).

Slice A added ``DataContract.futures``; this wires the value through so the live strategy declares
its continuous universe identically to research — the same field, populated from the same config.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from aegis_data.continuous_future import DEFAULT_ADJUSTMENT_MODE
from aegis_runtime import ComponentSpec, MissingIndexPolicy
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId
from pydantic import TypeAdapter

from research.aegis_research.configuration import DataConfig
from research.aegis_research.execution_bundle import (
    AssembledComponents,
    UnrecordedAdjustmentModeError,
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
        adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
    )

    assert contract.futures == ("ES", "KC")
    assert contract.missing_index is MissingIndexPolicy.DROP
    assert contract.adjustment_mode is ContinuousFutureAdjustmentType.BACKWARD_RATIO


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
        adjustment_mode=None,
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
        SimpleNamespace(data=data),
        _components(),
        (InstrumentId.from_str("AAPL.NASDAQ"),),
        adjustment_mode=None,
    )

    assert contract.futures == ()
    assert contract.adjustment_mode is None


def _futures_data() -> DataConfig:
    return _DATA.validate_python(
        {
            "arrays": ["OHLCV"],
            "base_currency": "USD",
            "instruments": ["AAPL.NASDAQ"],
            "futures": ["ES"],
            "start": "2024-01-01",
            "end": "2024-01-03",
            "timeframe": "1D",
            "missing_index": "drop",
        }
    )


_FUTURES_IDS = (
    InstrumentId.from_str("AAPL.NASDAQ"),
    InstrumentId.from_str("ES.XCME"),
)


def test_bundle_contract_carries_the_locked_runs_recorded_mode_not_the_default() -> None:
    # BACKWARD_SPREAD is deliberately NOT the shipped DEFAULT_ADJUSTMENT_MODE: the
    # exported mode is the locked Run's recorded fact, so a later default change
    # cannot change what an export declares.
    assert DEFAULT_ADJUSTMENT_MODE is not ContinuousFutureAdjustmentType.BACKWARD_SPREAD

    contract = _bundle_contract(
        SimpleNamespace(data=_futures_data()),
        _components(),
        _FUTURES_IDS,
        adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_SPREAD,
    )

    assert contract.adjustment_mode is ContinuousFutureAdjustmentType.BACKWARD_SPREAD


def test_export_retains_the_recorded_mode_after_the_process_default_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Flip the process default everywhere it is actually read (aegis-data and the
    # research adapter's binding): the exported contract must still carry the
    # locked Run's recorded BACKWARD_RATIO, because export never reads the default.
    import aegis_data.continuous_future as continuous_future_module

    from research.aegis_research.market_data.adapters import catalog as catalog_adapter

    monkeypatch.setattr(
        continuous_future_module,
        "DEFAULT_ADJUSTMENT_MODE",
        ContinuousFutureAdjustmentType.BACKWARD_SPREAD,
    )
    monkeypatch.setattr(
        catalog_adapter,
        "DEFAULT_ADJUSTMENT_MODE",
        ContinuousFutureAdjustmentType.BACKWARD_SPREAD,
    )

    contract = _bundle_contract(
        SimpleNamespace(data=_futures_data()),
        _components(),
        _FUTURES_IDS,
        adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
    )

    assert contract.adjustment_mode is ContinuousFutureAdjustmentType.BACKWARD_RATIO


def test_futures_export_without_recorded_mode_fails_with_rerun_guidance() -> None:
    # A pre-evidence Run cannot prove which algebra materialised its frames; export
    # must fail loudly instead of reading the current code default.
    with pytest.raises(UnrecordedAdjustmentModeError, match=r"re-run.*re-lock"):
        _bundle_contract(
            SimpleNamespace(data=_futures_data()),
            _components(),
            _FUTURES_IDS,
            adjustment_mode=None,
        )


def test_bundle_contract_records_the_resolved_mark_mode_per_loadable_leg() -> None:
    """The boundary AC (aegis-rd-tggo.3): the declared mode exported is what a
    bundle-backed consumer reads back — every static leg recorded explicitly
    (LAST included, cash FX bar-marked MID), continuous roots not recorded."""
    data = _DATA.validate_python(
        {
            "arrays": ["OHLCV"],
            "base_currency": "EUR",
            "instruments": ["UEQC.XETR:QUOTE", "VUSA.XLON"],
            "exchange": ["EUR/USD.IDEALPRO"],
            "futures": ["ES"],
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
            InstrumentId.from_str("UEQC.XETR"),
            InstrumentId.from_str("VUSA.XLON"),
            InstrumentId.from_str("ES.XCME"),
        ),
        adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
    )

    assert contract.mark_modes == {
        InstrumentId.from_str("UEQC.XETR"): "QUOTE",
        InstrumentId.from_str("VUSA.XLON"): "LAST",
        InstrumentId.from_str("EUR/USD.IDEALPRO"): "MID",
    }
