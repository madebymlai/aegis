from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.data import load_market_data_result
from research.aegis_research.market_data.adapters.catalog import load_catalog_source
from research.aegis_research.market_data.panels import market_data_bundle
from tests.support.research.aegis_research.factories import make_data_config


@dataclass
class _RecordingCatalogPort:
    frames: dict[InstrumentId, pd.DataFrame]
    requested_ids: tuple[InstrumentId, ...] = ()

    def load_raw_bars(self, request) -> dict[InstrumentId, pd.DataFrame]:
        self.requested_ids = tuple(request.instrument_ids)
        return self.frames


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
    assert result.metadata.provenance.provider_metadata == {
        "source": "nautilus_data_provider_port"
    }


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
