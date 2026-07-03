from __future__ import annotations

from datetime import date
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
    ContinuousRootLegsNotFoundError,
    ContinuousRootVenueMismatchError,
    RawBarRequest,
    catalog_data_port,
    catalog_root,
    raw_bar_type,
)
from aegis_data.distributions import Distribution, write_distribution_data
from aegis_data.roll import DatedContract
from tests.support.catalog_fakes import _FakeCatalog, _bars, _future


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


def test_catalog_port_reads_distribution_events_from_catalog(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("AAPL.NASDAQ")
    distribution = Distribution.from_ex_date(
        instrument_id,
        "2024-01-15",
        amount=0.42,
        currency="USD",
    )
    write_distribution_data(catalog, [distribution])
    port = CatalogBackedDataPort(catalog)

    events = port.distributions(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-31",
    )

    assert [(event.instrument_id, event.ex_date, event.amount) for event in events] == [
        (instrument_id, distribution.ex_date, pytest.approx(0.42))
    ]


def test_catalog_port_lists_a_roots_dated_legs_from_catalog_definitions() -> None:
    catalog = _FakeCatalog(
        [
            _future("ESM4.XCME", "2024-06-21"),
            _future("ESH4.XCME", "2024-03-15"),
            _future("CLF4.NYMEX", "2024-01-22", underlying="CL"),
        ],
        bars={},
    )
    port = CatalogBackedDataPort(catalog)

    legs = port.resolve_continuous("ES").legs

    assert legs == (
        DatedContract("ESH4.XCME", date(2024, 3, 15)),
        DatedContract("ESM4.XCME", date(2024, 6, 21)),
    )


def test_catalog_port_resolves_continuous_root_to_id_and_legs() -> None:
    catalog = _FakeCatalog(
        [
            _future("ESM4.XCME", "2024-06-21"),
            _future("ESH4.XCME", "2024-03-15"),
        ],
        bars={},
    )
    port = CatalogBackedDataPort(catalog)

    resolved = port.resolve_continuous("ES")

    assert resolved.instrument_id == _id("ES.XCME")
    assert resolved.legs == (
        DatedContract("ESH4.XCME", date(2024, 3, 15)),
        DatedContract("ESM4.XCME", date(2024, 6, 21)),
    )


def test_catalog_port_rejects_continuous_root_legs_across_venues() -> None:
    catalog = _FakeCatalog(
        [
            _future("ESH4.XCME", "2024-03-15"),
            _future("ESM4.XEUR", "2024-06-21"),
        ],
        bars={},
    )
    port = CatalogBackedDataPort(catalog)

    with pytest.raises(ContinuousRootVenueMismatchError, match="span multiple venues"):
        port.resolve_continuous("ES")


def test_catalog_port_rejects_continuous_root_with_no_legs() -> None:
    catalog = _FakeCatalog(
        [_future("CLF4.NYMEX", "2024-01-22", underlying="CL")],
        bars={},
    )
    port = CatalogBackedDataPort(catalog)

    with pytest.raises(ContinuousRootLegsNotFoundError, match="no dated legs"):
        port.resolve_continuous("ES")


def test_catalog_port_fetches_a_legs_ohlcv_over_its_window() -> None:
    instrument_id = _id("ESH4.XCME")
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [101.0, 102.0],
            "Low": [99.0, 100.0],
            "Close": [100.0, 101.0],
            "Volume": [1000.0, 1000.0],
        },
        index=pd.DatetimeIndex(["2024-01-02 21:00:00", "2024-01-03 21:00:00"]),
    )
    bars = _bars(instrument_id, frame)
    catalog = _FakeCatalog(
        [_future("ESH4.XCME", "2024-03-15")],
        bars={str(raw_bar_type(instrument_id, "1D")): bars},
    )
    port = CatalogBackedDataPort(catalog)

    result = port.fetch_contract_ohlcv(
        "ESH4.XCME", date(2024, 1, 1), date(2024, 3, 1)
    )

    pd.testing.assert_frame_equal(result, frame)


def test_catalog_port_probes_a_legs_daily_volume() -> None:
    instrument_id = _id("ESH4.XCME")
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [101.0, 102.0],
            "Low": [99.0, 100.0],
            "Close": [100.0, 101.0],
            "Volume": [1000.0, 1100.0],
        },
        index=pd.DatetimeIndex(["2024-01-02 21:00:00", "2024-01-03 21:00:00"]),
    )
    bars = _bars(instrument_id, frame)
    catalog = _FakeCatalog(
        [_future("ESH4.XCME", "2024-03-15")],
        bars={str(raw_bar_type(instrument_id, "1D")): bars},
    )
    port = CatalogBackedDataPort(catalog)

    volume = port.probe_contract_volume(
        "ESH4.XCME", date(2024, 1, 1), date(2024, 3, 1)
    )

    pd.testing.assert_series_equal(volume, frame["Volume"])
