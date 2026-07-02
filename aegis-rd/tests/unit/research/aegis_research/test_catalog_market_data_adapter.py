from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair, Equity, Instrument
from nautilus_trader.model.objects import Currency, Price, Quantity

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.data import load_market_data_result
from research.aegis_research.market_data.adapters import catalog as catalog_adapter
from research.aegis_research.market_data.adapters.catalog import (
    ContinuousRootCollisionError,
    load_catalog_source,
)
from research.aegis_research.market_data.panels import market_data_bundle
from tests.support.research.aegis_research.factories import make_data_config


def _definition(instrument_id: InstrumentId) -> Instrument:
    """A native definition for the fake catalog: an FX symbol resolves to a
    ``CurrencyPair`` (so currency conversion can read its base/quote), anything
    else to a USD ``Equity`` (these adapter tests run USD-base books)."""
    symbol = instrument_id.symbol.value
    if "/" in symbol:
        base, quote = symbol.split("/")
        return CurrencyPair(
            instrument_id=instrument_id,
            raw_symbol=Symbol(symbol),
            base_currency=Currency.from_str(base),
            quote_currency=Currency.from_str(quote),
            price_precision=5,
            size_precision=0,
            price_increment=Price(1e-5, 5),
            size_increment=Quantity.from_int(1),
            ts_event=0,
            ts_init=0,
        )
    return Equity(
        instrument_id=instrument_id,
        raw_symbol=Symbol(symbol),
        currency=Currency.from_str("USD"),
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


@dataclass
class _RecordingCatalogPort:
    frames: dict[InstrumentId, pd.DataFrame]
    requested_ids: tuple[InstrumentId, ...] = ()

    def load_raw_bars(self, request) -> dict[InstrumentId, pd.DataFrame]:
        self.requested_ids = tuple(request.instrument_ids)
        return self.frames

    def instruments(self, instrument_ids: Sequence[InstrumentId]) -> list[Instrument]:
        return [_definition(instrument_id) for instrument_id in instrument_ids]


def test_catalog_adapter_requests_exchange_ids_but_exposes_only_tradeable_columns() -> None:
    aapl = _id("AAPL.NASDAQ")
    esz6 = _id("ESZ6.XCME")
    eurusd = _id("EUR/USD.IDEALPRO")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port = _RecordingCatalogPort(
        frames={
            aapl: _frame(index, close=[10.0, 11.0], volume=[100.0, 110.0]),
            esz6: _frame(index, close=[20.0, 21.0], volume=[200.0, 210.0]),
            eurusd: _frame(index, close=[1.1, 1.2], volume=[0.0, 0.0]),
        }
    )
    config = make_data_config(
        arrays=["Close", "Volume"],
        base_currency="USD",
        instruments=["AAPL.NASDAQ", "ESZ6.XCME"],
        exchange=["EUR/USD.IDEALPRO"],
        start="2024-01-01",
        end="2024-01-03",
    )

    result = load_market_data_result(
        config,
        adapter=lambda current: load_catalog_source(current, port=port),
    )

    bundle = market_data_bundle(result)
    assert port.requested_ids == (
        aapl,
        esz6,
        eurusd,
    )
    assert list(bundle.array("Close").columns) == [aapl, esz6]
    assert bundle.array("Close").iloc[:, 0].tolist() == [10.0, 11.0]
    assert result.metadata.request.requested_instrument_ids == [aapl, esz6]
    assert to_builtin(result.metadata.request.requested_instrument_ids) == [
        "AAPL.NASDAQ",
        "ESZ6.XCME",
    ]
    assert result.metadata.provenance.index_evidence["source"] == "nautilus_catalog"
    assert result.metadata.provenance.provider_metadata == {"source": "nautilus_data_provider_port"}


def test_catalog_adapter_merges_continuous_future_roots_as_tradeable_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aapl = _id("AAPL.NASDAQ")
    es = _id("ES.XCME")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port = _RecordingCatalogPort(
        frames={aapl: _frame(index, close=[10.0, 11.0], volume=[100.0, 110.0])}
    )
    continuous = {es: _frame(index, close=[5000.0, 5010.0], volume=[1.0, 2.0])}

    seen_roots: list = []

    class FakeContinuousModel:
        def __init__(self, _port_arg, root, **_kwargs):
            seen_roots.append(str(root))
            self.continuous_id = es
            self.frame = continuous[es]

        def materialize(self, *, end: str) -> None:
            assert end == "2024-01-03"

    monkeypatch.setattr(catalog_adapter, "ContinuousContractModel", FakeContinuousModel)

    config = make_data_config(
        arrays=["Close", "Volume"],
        base_currency="USD",
        instruments=["AAPL.NASDAQ"],
        futures=["ES"],
        start="2024-01-01",
        end="2024-01-03",
    )

    result = load_market_data_result(
        config,
        adapter=lambda current: load_catalog_source(current, port=port),
    )

    bundle = market_data_bundle(result)
    # Continuous roots are synthetic — never raw-requested from the catalog.
    assert port.requested_ids == (aapl,)
    assert seen_roots == ["ES"]
    # The continuous root is a first-class tradeable column, ordered after raw instruments.
    assert list(bundle.array("Close").columns) == [aapl, es]
    assert bundle.array("Close")[es].tolist() == [5000.0, 5010.0]
    assert bundle.array("Volume")[es].tolist() == [1.0, 2.0]
    assert result.metadata.provenance.source_metadata["continuous_root_ids"] == ["ES.XCME"]


def test_catalog_adapter_rejects_a_continuous_root_colliding_with_a_raw_instrument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A synthetic root id that equals a raw instrument id would silently clobber the raw
    # column on merge — fail loud instead.
    es = _id("ES.XCME")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port = _RecordingCatalogPort(frames={es: _frame(index, close=[10.0, 11.0], volume=[1.0, 1.0])})

    class FakeContinuousModel:
        def __init__(self, _port_arg, _root, **_kwargs):
            self.continuous_id = es
            self.frame = _frame(index, close=[99.0, 99.0], volume=[9.0, 9.0])

        def materialize(self, *, end: str) -> None:
            assert end == "2024-01-03"

    monkeypatch.setattr(catalog_adapter, "ContinuousContractModel", FakeContinuousModel)
    config = make_data_config(
        arrays=["Close"],
        base_currency="USD",
        instruments=["ES.XCME"],
        futures=["ES"],
        start="2024-01-01",
        end="2024-01-03",
    )

    with pytest.raises(ContinuousRootCollisionError, match="collide with raw instrument ids"):
        load_catalog_source(config, port=port)


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def _frame(
    index: pd.DatetimeIndex,
    *,
    close: list[float],
    volume: list[float],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": close,
            "High": close,
            "Low": close,
            "Close": close,
            "Volume": volume,
        },
        index=index,
    )
