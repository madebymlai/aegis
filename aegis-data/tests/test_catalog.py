from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from aegis_data.catalog import (
    CatalogBackedDataPort,
    CatalogCoverageGapError,
    RawBarRequest,
    catalog_data_port,
    catalog_root,
    raw_bar_type,
)


def _bar(bar_type: BarType, day: str, close: float) -> Bar:
    ts_event = pd.Timestamp(day, tz="UTC").value
    return Bar(
        bar_type,
        Price.from_str(f"{close:.2f}"),
        Price.from_str(f"{close + 1:.2f}"),
        Price.from_str(f"{close - 1:.2f}"),
        Price.from_str(f"{close:.2f}"),
        Quantity.from_str("100"),
        ts_event,
        ts_event,
    )


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def _write_span(
    catalog: ParquetDataCatalog,
    bars: list[Bar],
    *,
    start: str,
    end: str,
) -> None:
    catalog.write_data(
        bars,
        start=pd.Timestamp(start, tz="UTC").value,
        end=pd.Timestamp(end, tz="UTC").value,
    )


class _ProviderPort:
    def __init__(self, bars: list[Bar]) -> None:
        self.bars = bars
        self.requests: list[BarType] = []

    def request_bars(
        self,
        bar_type: BarType,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> list[Bar]:
        self.requests.append(bar_type)
        return self.bars


def test_catalog_root_uses_aegis_data_dir_catalog_subpath(tmp_path: Path) -> None:
    root = catalog_root({"AEGIS_DATA_DIR": str(tmp_path / "aegis-data")})

    assert root == tmp_path / "aegis-data" / "catalog"


def test_catalog_writes_nautilus_native_bar_layout(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    bar_type = raw_bar_type(_id("AAPL.NASDAQ"), "1D")

    _write_span(
        catalog,
        [_bar(bar_type, "2024-01-01", 10.0)],
        start="2024-01-01",
        end="2024-01-02",
    )

    layout = sorted(
        path.relative_to(catalog_path).parts[:3] for path in catalog_path.rglob("*.parquet")
    )

    assert layout == [("data", "bar", "AAPL.XNAS-1-DAY-LAST-EXTERNAL")]


def test_catalog_port_reads_cache_hit_without_backfill(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("AAPL.NASDAQ")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [_bar(bar_type, "2024-01-01", 10.0)],
        start="2024-01-01",
        end="2024-01-02",
    )
    provider = _ProviderPort([])
    port = CatalogBackedDataPort(catalog, provider=provider)

    frames = port.load_raw_bars(
        RawBarRequest(
            instrument_ids=(instrument_id,),
            start="2024-01-01",
            end="2024-01-02",
        )
    )

    assert frames[instrument_id]["Close"].tolist() == [10.0]
    assert provider.requests == []


def test_catalog_port_reads_mic_cache_hit_for_ib_exchange_alias(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    requested_id = _id("TLT.NASDAQ")
    canonical_id = _id("TLT.XNAS")
    canonical_bar_type = raw_bar_type(canonical_id, "1D")
    _write_span(
        catalog,
        [_bar(canonical_bar_type, "2024-01-01", 99.0)],
        start="2024-01-01",
        end="2024-01-02",
    )
    provider = _ProviderPort([])
    port = CatalogBackedDataPort(catalog, provider=provider)

    frames = port.load_raw_bars(
        RawBarRequest(
            instrument_ids=(requested_id,),
            start="2024-01-01",
            end="2024-01-02",
        )
    )

    assert frames[requested_id]["Close"].tolist() == [99.0]
    assert provider.requests == []


def test_catalog_port_backfills_missing_tail_with_update_catalog(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("AAPL.NASDAQ")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [_bar(bar_type, "2024-01-01", 10.0)],
        start="2024-01-01",
        end="2024-01-02",
    )
    provider = _ProviderPort([_bar(bar_type, "2024-01-02", 11.0)])
    port = CatalogBackedDataPort(catalog, provider=provider)

    first = port.load_raw_bars(
        RawBarRequest(
            instrument_ids=(instrument_id,),
            start="2024-01-01",
            end="2024-01-03",
        )
    )
    second = port.load_raw_bars(
        RawBarRequest(
            instrument_ids=(instrument_id,),
            start="2024-01-01",
            end="2024-01-03",
        )
    )

    assert first[instrument_id]["Close"].tolist() == [10.0, 11.0]
    assert second[instrument_id]["Close"].tolist() == [10.0, 11.0]
    assert provider.requests == [bar_type]


def test_catalog_data_port_factory_wires_fill_and_definition_seeder(tmp_path: Path) -> None:
    """The factory returns a ready CatalogBackedDataPort with the fill provider and
    the definition seeder wired — callers depend only on the abstraction (DIP)."""
    port = catalog_data_port(tmp_path / "catalog")

    assert isinstance(port, CatalogBackedDataPort)
    assert port.provider is not None
    assert port.definition_seeder is not None


def test_catalog_port_seeds_instrument_definition_on_backfill(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("AAPL.NASDAQ")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [_bar(bar_type, "2024-01-01", 10.0)],
        start="2024-01-01",
        end="2024-01-02",
    )
    provider = _ProviderPort([_bar(bar_type, "2024-01-02", 11.0)])
    seeded: list[InstrumentId] = []
    port = CatalogBackedDataPort(
        catalog, provider=provider, definition_seeder=seeded.append
    )

    port.load_raw_bars(
        RawBarRequest(
            instrument_ids=(instrument_id,),
            start="2024-01-01",
            end="2024-01-03",
        )
    )

    assert seeded == [_id("AAPL.XNAS")]


def test_catalog_port_does_not_seed_definition_on_cache_hit(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("AAPL.NASDAQ")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [_bar(bar_type, "2024-01-01", 10.0)],
        start="2024-01-01",
        end="2024-01-02",
    )
    seeded: list[InstrumentId] = []
    port = CatalogBackedDataPort(
        catalog, provider=_ProviderPort([]), definition_seeder=seeded.append
    )

    port.load_raw_bars(
        RawBarRequest(
            instrument_ids=(instrument_id,),
            start="2024-01-01",
            end="2024-01-02",
        )
    )

    assert seeded == []


def test_read_native_bars_is_a_warm_read_returning_bars_without_the_coverage_gate(
    tmp_path: Path,
) -> None:
    """The native-bar read is a pure warm read: it returns the stored ``Bar``\\ s for the
    window and never invokes the coverage gate/provider — so a rolled-off futures leg,
    read over a window past its life, yields just its bars instead of a coverage error."""
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("AAPL.NASDAQ")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [_bar(bar_type, "2024-01-01", 10.0)],
        start="2024-01-01",
        end="2024-01-02",
    )
    provider = _ProviderPort([_bar(bar_type, "2024-01-15", 11.0)])
    port = CatalogBackedDataPort(catalog, provider=provider)

    bars = port.read_native_bars(
        RawBarRequest(
            instrument_ids=(instrument_id,),
            start="2024-01-01",
            end="2024-01-31",
        )
    )

    assert isinstance(bars[instrument_id][0], Bar)
    assert [bar.close.as_double() for bar in bars[instrument_id]] == [10.0]
    assert provider.requests == []  # warm read: no coverage gate, no backfill


def test_catalog_port_raises_coverage_gap_when_window_is_unservable(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    port = CatalogBackedDataPort(catalog)

    with pytest.raises(CatalogCoverageGapError, match="catalog cannot serve AAPL.XNAS"):
        port.load_raw_bars(
            RawBarRequest(
                instrument_ids=(_id("AAPL.NASDAQ"),),
                start="2024-01-01",
                end="2024-01-02",
            )
        )
