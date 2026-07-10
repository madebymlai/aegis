from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from aegis_data.bar_type import mic_canonical_instrument_id
from aegis_data.catalog import (
    CatalogBackedDataPort,
    CatalogCoverageGapError,
    ContinuousRootLegsNotFoundError,
    ContinuousRootVenueMismatchError,
    RawBarRequest,
    catalog_data_port,
    catalog_root,
    continuous_root_legs,
    raw_bar_type,
)
from aegis_data.distributions import (
    Distribution,
    query_distribution_data,
    write_distribution_data,
)
from aegis_data.roll import DatedContract
from aegis_data.testing import FakeCatalog, bars, future


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


class _AdjustedLastProvider:
    def __init__(self, adjusted_last: dict[InstrumentId, pd.Series]) -> None:
        self.adjusted_last = adjusted_last
        self.requests: list[dict[str, Any]] = []

    def request_adjusted_last(self, **kwargs: Any) -> pd.Series:
        self.requests.append(kwargs)
        return self.adjusted_last[kwargs["instrument_id"]]


def _equity(instrument_id: InstrumentId) -> Equity:
    return Equity(
        instrument_id=instrument_id,
        raw_symbol=Symbol(instrument_id.symbol.value),
        currency=USD,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def _write_definition(catalog: ParquetDataCatalog, *instrument_ids: InstrumentId) -> None:
    """Write equity definitions as the IBKR provider stores them — under the MIC venue.

    Bars land under the MIC venue (``raw_bar_type``) and so do definitions
    (``convert_exchange_to_mic_venue``), so a fixture that writes a definition directly
    must key it the same way a real fill would.
    """
    catalog.write_data(
        [_equity(mic_canonical_instrument_id(instrument_id)) for instrument_id in instrument_ids]
    )


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


def test_instruments_resolves_ib_exchange_name_against_mic_stored_definition(
    tmp_path: Path,
) -> None:
    # IBKR stores LSE main-market listings under their MIC venue (.XLON), but a config
    # addresses them by the raw IB exchange name (.LSE). The def boundary normalizes the
    # query like the bar boundary does, and keys the result by the requested id (#81).
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    catalog.write_data([_equity(_id("BRNT.XLON"))])
    port = CatalogBackedDataPort(catalog)

    resolved = port.instruments((_id("BRNT.LSE"),))

    assert set(resolved) == {_id("BRNT.LSE")}
    assert resolved[_id("BRNT.LSE")].id == _id("BRNT.XLON")


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


def test_catalog_port_rejects_unverified_distribution_events(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("AAPL.NASDAQ")
    _write_definition(catalog, instrument_id)
    distribution = Distribution.from_ex_date(
        instrument_id,
        "2024-01-15",
        amount=0.42,
        currency="USD",
    )
    write_distribution_data(catalog, [distribution])
    port = CatalogBackedDataPort(catalog)

    with pytest.raises(CatalogCoverageGapError, match="distribution coverage is missing"):
        port.distributions(
            (instrument_id,),
            start="2024-01-01",
            end="2024-01-31",
        )


def test_catalog_port_verifies_distributions_on_first_read_and_serves_warm(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("SPY.ARCA")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [
            _bar(bar_type, "2024-01-01", 100.0),
            _bar(bar_type, "2024-01-02", 100.0),
            _bar(bar_type, "2024-01-03", 100.0),
        ],
        start="2024-01-01",
        end="2024-01-04",
    )
    _write_definition(catalog, instrument_id)
    dates = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    provider = _AdjustedLastProvider(
        {
            instrument_id: pd.Series(
                [100.0, 100.0 / (1.0 - 0.01), 100.0],
                index=dates,
            )
        }
    )
    port = CatalogBackedDataPort(catalog, distribution_provider=provider)

    first = port.distributions(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-04",
    )
    warm = CatalogBackedDataPort(ParquetDataCatalog(catalog_path)).distributions(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-04",
    )

    assert [(event.ex_date, event.amount, event.currency) for event in first] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(1.0), "USD")
    ]
    assert [(event.ex_date, event.amount, event.currency) for event in warm] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(1.0), "USD")
    ]
    assert provider.requests == [
        {
            "instrument_id": instrument_id,
            "start": pd.Timestamp("2024-01-01", tz="UTC"),
            "end": pd.Timestamp("2024-01-04", tz="UTC"),
            "currency": "USD",
        }
    ]


def test_catalog_port_reports_verified_distribution_coverage(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("SPY.ARCA")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [
            _bar(bar_type, "2024-01-01", 100.0),
            _bar(bar_type, "2024-01-02", 100.0),
            _bar(bar_type, "2024-01-03", 100.0),
        ],
        start="2024-01-01",
        end="2024-01-04",
    )
    _write_definition(catalog, instrument_id)
    provider = _AdjustedLastProvider(
        {
            instrument_id: pd.Series(
                [100.0, 100.0 / (1.0 - 0.01), 100.0],
                index=pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC"),
            )
        }
    )
    port = CatalogBackedDataPort(
        catalog,
        distribution_provider=provider,
        clock_ns=lambda: pd.Timestamp("2026-01-01", tz="UTC").value,
    )
    port.distributions((instrument_id,), start="2024-01-01", end="2024-01-04")

    report = port.distribution_coverage_report(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-04",
    )

    assert report == (
        {
            "instrument_id": "SPY.ARCA",
            "applicable": True,
            "verified_start": "2024-01-01T00:00:00+00:00",
            "verified_end": "2024-01-04T00:00:00+00:00",
            "event_count": 1,
            "checked_at": "2026-01-01T00:00:00+00:00",
        },
    )


def test_catalog_port_verifies_accumulating_distribution_window_as_empty(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("GLD.ARCA")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [
            _bar(bar_type, "2024-01-01", 200.0),
            _bar(bar_type, "2024-01-02", 201.0),
            _bar(bar_type, "2024-01-03", 202.0),
        ],
        start="2024-01-01",
        end="2024-01-04",
    )
    _write_definition(catalog, instrument_id)
    dates = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    provider = _AdjustedLastProvider(
        {
            instrument_id: pd.Series(
                [200.0, 201.0, 202.0],
                index=dates,
            )
        }
    )
    port = CatalogBackedDataPort(catalog, distribution_provider=provider)

    first = port.distributions(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-04",
    )
    warm = CatalogBackedDataPort(ParquetDataCatalog(catalog_path)).distributions(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-04",
    )

    assert first == ()
    assert warm == ()
    assert len(provider.requests) == 1


def test_catalog_port_skips_distribution_verification_for_futures_and_roots(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    dated_leg = _id("ESH4.XCME")
    continuous_root = _id("ES.XCME")
    catalog.write_data(
        [
            future("ESH4.XCME", "2024-03-15"),
            future("ESM4.XCME", "2024-06-21"),
        ]
    )

    dated_events = CatalogBackedDataPort(catalog).distributions(
        (dated_leg,),
        start="2024-01-01",
        end="2024-01-04",
    )
    root_events = CatalogBackedDataPort(catalog).distributions(
        (continuous_root,),
        start="2024-01-01",
        end="2024-01-04",
    )

    assert dated_events == ()
    assert root_events == ()


def test_catalog_port_reports_continuous_root_distribution_coverage_not_applicable(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    continuous_root = _id("ES.XCME")
    catalog.write_data(
        [
            future("ESH4.XCME", "2024-03-15"),
            future("ESM4.XCME", "2024-06-21"),
        ]
    )
    port = CatalogBackedDataPort(catalog)
    port.distributions(
        (continuous_root,),
        start="2024-01-01",
        end="2024-01-04",
    )

    report = port.distribution_coverage_report(
        (continuous_root,),
        start="2024-01-01",
        end="2024-01-04",
    )

    assert report[0]["instrument_id"] == "ES.XCME"
    assert report[0]["applicable"] is False
    assert report[0]["event_count"] == 0
    assert report[0]["checked_at"] is not None


def test_catalog_port_rejects_distribution_read_for_unresolved_instrument(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)

    with pytest.raises(CatalogCoverageGapError, match="cannot resolve"):
        CatalogBackedDataPort(catalog).distributions(
            (_id("TYPO.ARCA"),),
            start="2024-01-01",
            end="2024-01-04",
        )


def test_catalog_port_reports_all_uncovered_distribution_instruments_without_provider(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    spy = _id("SPY.ARCA")
    hyg = _id("HYG.ARCA")
    _write_definition(catalog, spy, hyg)

    with pytest.raises(CatalogCoverageGapError) as error:
        CatalogBackedDataPort(catalog).distributions(
            (spy, hyg),
            start="2024-01-01",
            end="2024-01-04",
        )

    assert "SPY.ARCA" in str(error.value)
    assert "HYG.ARCA" in str(error.value)


def test_catalog_port_rejects_uncovered_distributions_with_bar_only_provider(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("SPY.ARCA")
    _write_definition(catalog, instrument_id)

    with pytest.raises(CatalogCoverageGapError, match="distribution coverage is missing"):
        CatalogBackedDataPort(
            catalog,
            distribution_provider=_ProviderPort([]),
        ).distributions(
            (instrument_id,),
            start="2024-01-01",
            end="2024-01-04",
        )


def test_catalog_port_reverifies_seeded_distribution_store_without_duplicates(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("SPY.ARCA")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [
            _bar(bar_type, "2024-01-01", 100.0),
            _bar(bar_type, "2024-01-02", 100.0),
            _bar(bar_type, "2024-01-03", 100.0),
        ],
        start="2024-01-01",
        end="2024-01-04",
    )
    _write_definition(catalog, instrument_id)
    write_distribution_data(
        catalog,
        [
            Distribution.from_ex_date(
                instrument_id,
                "2024-01-02",
                amount=1.0,
                currency="USD",
            )
        ],
    )
    dates = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    provider = _AdjustedLastProvider(
        {
            instrument_id: pd.Series(
                [100.0, 100.0 / (1.0 - 0.01), 100.0],
                index=dates,
            )
        }
    )

    events = CatalogBackedDataPort(
        catalog,
        distribution_provider=provider,
    ).distributions(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-04",
    )

    assert [(event.ex_date, event.amount) for event in events] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(1.0))
    ]
    assert len(provider.requests) == 1


def test_catalog_port_backward_extension_persists_early_distribution_events(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("SPY.ARCA")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [
            _bar(bar_type, "2024-01-01", 100.0),
            _bar(bar_type, "2024-01-02", 100.0),
            _bar(bar_type, "2024-01-03", 100.0),
            _bar(bar_type, "2024-01-04", 100.0),
            _bar(bar_type, "2024-01-05", 100.0),
        ],
        start="2024-01-01",
        end="2024-01-06",
    )
    _write_definition(catalog, instrument_id)
    dates = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    first_factor = 1.0 / (1.0 - 0.01)
    second_factor = first_factor / (1.0 - 0.02)
    provider = _AdjustedLastProvider(
        {
            instrument_id: pd.Series(
                [100.0, 100.0 * first_factor, 100.0 * first_factor, 100.0 * second_factor, 100.0],
                index=dates,
            )
        }
    )
    port = CatalogBackedDataPort(catalog, distribution_provider=provider)

    later = port.distributions(
        (instrument_id,),
        start="2024-01-03",
        end="2024-01-06",
    )
    extended = port.distributions(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-06",
    )

    assert [(event.ex_date, event.amount) for event in later] == [
        (pd.Timestamp("2024-01-04", tz="UTC"), pytest.approx(2.0))
    ]
    assert [(event.ex_date, event.amount) for event in extended] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(1.0)),
        (pd.Timestamp("2024-01-04", tz="UTC"), pytest.approx(2.0)),
    ]


def test_catalog_port_forward_request_clamps_to_stored_bar_frontier(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("SPY.ARCA")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [
            _bar(bar_type, "2024-01-01", 100.0),
            _bar(bar_type, "2024-01-02", 100.0),
            _bar(bar_type, "2024-01-03", 100.0),
        ],
        start="2024-01-01",
        end="2024-01-04",
    )
    _write_definition(catalog, instrument_id)
    dates = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    provider = _AdjustedLastProvider(
        {
            instrument_id: pd.Series(
                [100.0, 100.0 / (1.0 - 0.01), 100.0],
                index=dates,
            )
        }
    )
    port = CatalogBackedDataPort(catalog, distribution_provider=provider)

    covered = port.distributions(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-04",
    )
    extended = port.distributions(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-08",
    )

    assert [(event.ex_date, event.amount) for event in covered] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(1.0))
    ]
    assert [(event.ex_date, event.amount) for event in extended] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(1.0))
    ]
    assert len(provider.requests) == 1


def test_catalog_port_rejects_distribution_gap_with_too_few_trade_closes(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("SPY.ARCA")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [_bar(bar_type, "2024-01-01", 100.0)],
        start="2024-01-01",
        end="2024-01-02",
    )
    _write_definition(catalog, instrument_id)
    provider = _AdjustedLastProvider(
        {
            instrument_id: pd.Series(
                [100.0],
                index=pd.DatetimeIndex([pd.Timestamp("2024-01-01", tz="UTC")]),
            )
        }
    )

    with pytest.raises(CatalogCoverageGapError, match="fewer than two TRADES closes"):
        CatalogBackedDataPort(catalog, distribution_provider=provider).distributions(
            (instrument_id,),
            start="2024-01-01",
            end="2024-01-04",
        )


def test_catalog_port_fetches_only_missing_distribution_gap_between_verified_ranges(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("SPY.ARCA")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [
            _bar(bar_type, "2024-01-01", 100.0),
            _bar(bar_type, "2024-01-02", 100.0),
            _bar(bar_type, "2024-01-03", 100.0),
            _bar(bar_type, "2024-01-04", 100.0),
            _bar(bar_type, "2024-01-05", 100.0),
            _bar(bar_type, "2024-01-06", 100.0),
        ],
        start="2024-01-01",
        end="2024-01-07",
    )
    _write_definition(catalog, instrument_id)
    provider = _AdjustedLastProvider(
        {
            instrument_id: pd.Series(
                [100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
                index=pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC"),
            )
        }
    )
    port = CatalogBackedDataPort(catalog, distribution_provider=provider)
    port.distributions((instrument_id,), start="2024-01-01", end="2024-01-03")
    port.distributions((instrument_id,), start="2024-01-05", end="2024-01-07")
    provider.requests.clear()

    events = port.distributions(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-07",
    )

    assert events == ()
    assert len(provider.requests) == 1
    assert provider.requests[0]["start"].date() == date(2024, 1, 3)
    assert provider.requests[0]["end"] < pd.Timestamp("2024-01-05", tz="UTC")


def test_distribution_force_reverify_replaces_bounded_window_events(
    tmp_path: Path,
) -> None:
    catalog, instrument_id, provider, dates = _force_reverify_catalog(tmp_path)
    _verify_distribution_window(
        catalog,
        provider,
        instrument_id,
        checked_at="2026-01-01",
    )
    provider.adjusted_last[instrument_id] = _restated_adjusted_last(dates)

    _force_reverify_distribution_window(
        catalog,
        provider,
        instrument_id,
        checked_at="2026-01-02",
    )
    all_stored = query_distribution_data(
        catalog,
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-06",
    )

    assert [(event.ex_date, event.amount) for event in all_stored] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(0.5)),
        (pd.Timestamp("2024-01-04", tz="UTC"), pytest.approx(2.0)),
    ]


def test_distribution_force_reverify_removes_stale_events_when_restated_empty(
    tmp_path: Path,
) -> None:
    catalog, instrument_id, provider, dates = _force_reverify_catalog(tmp_path)
    _verify_distribution_window(
        catalog,
        provider,
        instrument_id,
        checked_at="2026-01-01",
    )
    provider.adjusted_last[instrument_id] = pd.Series([100.0] * len(dates), index=dates)

    _force_reverify_distribution_window(
        catalog,
        provider,
        instrument_id,
        checked_at="2026-01-02",
    )
    all_stored = query_distribution_data(
        catalog,
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-06",
    )

    assert [(event.ex_date, event.amount) for event in all_stored] == [
        (pd.Timestamp("2024-01-04", tz="UTC"), pytest.approx(2.0)),
    ]


def test_distribution_force_reverify_rewrites_event_on_window_end_boundary(
    tmp_path: Path,
) -> None:
    catalog, instrument_id, provider, dates = _force_reverify_catalog(tmp_path)
    _verify_distribution_window(
        catalog,
        provider,
        instrument_id,
        checked_at="2026-01-01",
    )
    provider.adjusted_last[instrument_id] = _boundary_adjusted_last(dates)

    _force_reverify_distribution_window(
        catalog,
        provider,
        instrument_id,
        checked_at="2026-01-02",
    )
    all_stored = query_distribution_data(
        catalog,
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-06",
    )

    assert [(event.ex_date, event.amount) for event in all_stored] == [
        (pd.Timestamp("2024-01-03", tz="UTC"), pytest.approx(0.5)),
        (pd.Timestamp("2024-01-04", tz="UTC"), pytest.approx(2.0)),
    ]


def test_distribution_force_reverify_marks_window_with_fresh_checked_at(
    tmp_path: Path,
) -> None:
    catalog, instrument_id, provider, dates = _force_reverify_catalog(tmp_path)
    _verify_distribution_window(
        catalog,
        provider,
        instrument_id,
        checked_at="2026-01-01",
    )
    provider.adjusted_last[instrument_id] = _restated_adjusted_last(dates)

    _force_reverify_distribution_window(
        catalog,
        provider,
        instrument_id,
        checked_at="2026-01-02",
    )
    refreshed_report = CatalogBackedDataPort(catalog).distribution_coverage_report(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-03",
    )

    assert refreshed_report[0]["checked_at"] == "2026-01-02T00:00:00+00:00"


def test_distribution_coverage_report_uses_oldest_checked_at_in_window(
    tmp_path: Path,
) -> None:
    catalog, instrument_id, provider, dates = _force_reverify_catalog(tmp_path)
    _verify_distribution_window(
        catalog,
        provider,
        instrument_id,
        checked_at="2026-01-01",
    )
    provider.adjusted_last[instrument_id] = _restated_adjusted_last(dates)
    _force_reverify_distribution_window(
        catalog,
        provider,
        instrument_id,
        checked_at="2026-01-02",
    )

    report = CatalogBackedDataPort(catalog).distribution_coverage_report(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-06",
    )

    assert report[0]["checked_at"] == "2026-01-01T00:00:00+00:00"


def test_distribution_force_reverify_preserves_warm_read_over_original_window(
    tmp_path: Path,
) -> None:
    catalog, instrument_id, provider, dates = _force_reverify_catalog(tmp_path)
    _verify_distribution_window(
        catalog,
        provider,
        instrument_id,
        checked_at="2026-01-01",
    )
    provider.adjusted_last[instrument_id] = _restated_adjusted_last(dates)
    _force_reverify_distribution_window(
        catalog,
        provider,
        instrument_id,
        checked_at="2026-01-02",
    )
    provider.requests.clear()

    warm_full = CatalogBackedDataPort(
        catalog,
        distribution_provider=provider,
    ).distributions(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-06",
    )

    assert [(event.ex_date, event.amount) for event in warm_full] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(0.5)),
        (pd.Timestamp("2024-01-04", tz="UTC"), pytest.approx(2.0)),
    ]
    assert provider.requests == []


def _force_reverify_catalog(
    tmp_path: Path,
) -> tuple[ParquetDataCatalog, InstrumentId, _AdjustedLastProvider, pd.DatetimeIndex]:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("SPY.ARCA")
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [
            _bar(bar_type, "2024-01-01", 100.0),
            _bar(bar_type, "2024-01-02", 100.0),
            _bar(bar_type, "2024-01-03", 100.0),
            _bar(bar_type, "2024-01-04", 100.0),
            _bar(bar_type, "2024-01-05", 100.0),
        ],
        start="2024-01-01",
        end="2024-01-06",
    )
    _write_definition(catalog, instrument_id)
    dates = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")
    provider = _AdjustedLastProvider(
        {
            instrument_id: pd.Series(
                [
                    100.0,
                    100.0 / (1.0 - 0.01),
                    100.0,
                    100.0 / (1.0 - 0.02),
                    100.0,
                ],
                index=dates,
            )
        }
    )
    return catalog, instrument_id, provider, dates


def _verify_distribution_window(
    catalog: ParquetDataCatalog,
    provider: _AdjustedLastProvider,
    instrument_id: InstrumentId,
    *,
    checked_at: str,
) -> None:
    CatalogBackedDataPort(
        catalog,
        distribution_provider=provider,
        clock_ns=lambda: pd.Timestamp(checked_at, tz="UTC").value,
    ).distributions((instrument_id,), start="2024-01-01", end="2024-01-06")


def _force_reverify_distribution_window(
    catalog: ParquetDataCatalog,
    provider: _AdjustedLastProvider,
    instrument_id: InstrumentId,
    *,
    checked_at: str,
) -> None:
    CatalogBackedDataPort(
        catalog,
        distribution_provider=provider,
        clock_ns=lambda: pd.Timestamp(checked_at, tz="UTC").value,
    ).force_reverify_distribution_coverage(
        (instrument_id,), start="2024-01-01", end="2024-01-03"
    )


def _restated_adjusted_last(dates: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(
        [
            100.0,
            100.0 / (1.0 - 0.005),
            100.0,
            100.0 / (1.0 - 0.02),
            100.0,
        ],
        index=dates,
    )


def _boundary_adjusted_last(dates: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(
        [
            100.0,
            100.0,
            100.0 / (1.0 - 0.005),
            100.0 / ((1.0 - 0.005) * (1.0 - 0.02)),
            100.0,
        ],
        index=dates,
    )


def test_catalog_port_lists_a_roots_dated_legs_from_catalog_definitions() -> None:
    catalog = FakeCatalog(
        [
            future("ESM4.XCME", "2024-06-21"),
            future("ESH4.XCME", "2024-03-15"),
            future("CLF4.NYMEX", "2024-01-22", underlying="CL"),
        ],
        bars={},
    )
    port = CatalogBackedDataPort(catalog)

    legs = port.resolve_continuous("ES").legs

    assert legs == (
        DatedContract("ESH4.XCME", date(2024, 3, 15)),
        DatedContract("ESM4.XCME", date(2024, 6, 21)),
    )


def test_continuous_root_legs_reads_dated_legs_without_a_port_instance() -> None:
    catalog = FakeCatalog(
        [
            future("ESM4.XCME", "2024-06-21"),
            future("ESH4.XCME", "2024-03-15"),
            future("CLF4.NYMEX", "2024-01-22", underlying="CL"),
        ],
        bars={},
    )

    legs = continuous_root_legs(catalog, "ES")

    assert legs == (
        DatedContract("ESH4.XCME", date(2024, 3, 15)),
        DatedContract("ESM4.XCME", date(2024, 6, 21)),
    )


def test_catalog_port_resolves_continuous_root_to_id_and_legs() -> None:
    catalog = FakeCatalog(
        [
            future("ESM4.XCME", "2024-06-21"),
            future("ESH4.XCME", "2024-03-15"),
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
    catalog = FakeCatalog(
        [
            future("ESH4.XCME", "2024-03-15"),
            future("ESM4.XEUR", "2024-06-21"),
        ],
        bars={},
    )
    port = CatalogBackedDataPort(catalog)

    with pytest.raises(ContinuousRootVenueMismatchError, match="span multiple venues"):
        port.resolve_continuous("ES")


def test_catalog_port_rejects_continuous_root_with_no_legs() -> None:
    catalog = FakeCatalog(
        [future("CLF4.NYMEX", "2024-01-22", underlying="CL")],
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
        index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"]),
    )
    native = bars(instrument_id, frame)
    catalog = FakeCatalog(
        [future("ESH4.XCME", "2024-03-15")],
        bars={str(raw_bar_type(instrument_id, "1D")): native},
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
        index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"]),
    )
    native = bars(instrument_id, frame)
    catalog = FakeCatalog(
        [future("ESH4.XCME", "2024-03-15")],
        bars={str(raw_bar_type(instrument_id, "1D")): native},
    )
    port = CatalogBackedDataPort(catalog)

    volume = port.probe_contract_volume(
        "ESH4.XCME", date(2024, 1, 1), date(2024, 3, 1)
    )

    pd.testing.assert_series_equal(volume, frame["Volume"])
