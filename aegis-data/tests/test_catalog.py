from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair, Equity
from nautilus_trader.model.objects import Currency
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from aegis_data.bar_type import external_bar_type, mic_canonical_instrument_id
from aegis_data.catalog import (
    CatalogBackedDataPort,
    CatalogCoverageGapError,
    ContinuousRootLegsNotFoundError,
    ContinuousRootVenueMismatchError,
    GapFillProviderError,
    MissingCatalogDefinitionsError,
    CatalogWindowRequest,
    ServedBars,
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
from aegis_data.ibkr import IbkrRequestError
from aegis_data.marking import DeclaredMarkingResolver, MarkMode
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
    def __init__(self, bars: list[Bar], *, served_from: str | None = None) -> None:
        self.bars = bars
        self.served_from = served_from
        self.requests: list[BarType] = []

    def request_bars(
        self,
        bar_type: BarType,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ServedBars:
        self.requests.append(bar_type)
        served_from = (
            start
            if self.served_from is None
            else pd.Timestamp(self.served_from, tz="UTC")
        )
        return ServedBars(tuple(self.bars), served_from)


class _AdjustedLastProvider:
    def __init__(self, adjusted_last: dict[InstrumentId, pd.Series]) -> None:
        self.adjusted_last = adjusted_last
        self.requests: list[dict[str, Any]] = []

    def request_adjusted_last(self, **kwargs: Any) -> pd.Series:
        self.requests.append(kwargs)
        return self.adjusted_last[kwargs["instrument_id"]]


def _seed_fx_pair(catalog: ParquetDataCatalog, fx_pair: InstrumentId) -> None:
    """Definition plus covered MID bars: a cash FX leg ready for a window read.

    The MID key is stated where the leg is seeded — exactly as production
    declares it — matching the resolver the reading port carries."""
    catalog.write_data([_currency_pair(fx_pair)])
    bar_type = external_bar_type(fx_pair, "1D", "MID")
    _write_span(
        catalog,
        [
            _bar(bar_type, "2024-01-01", 1.10),
            _bar(bar_type, "2024-01-02", 1.11),
            _bar(bar_type, "2024-01-03", 1.12),
        ],
        start="2024-01-01",
        end="2024-01-04",
    )


def _fx_mid_resolver(fx_pair: InstrumentId) -> DeclaredMarkingResolver:
    """The declaration production supplies for a conversion leg: MID by the
    config section that names it, never by symbol shape."""
    return DeclaredMarkingResolver(declared={fx_pair: MarkMode.MID})


def _currency_pair(instrument_id: InstrumentId) -> CurrencyPair:
    base, quote = instrument_id.symbol.value.split("/")
    return CurrencyPair(
        instrument_id=instrument_id,
        raw_symbol=Symbol(instrument_id.symbol.value),
        base_currency=Currency.from_str(base),
        quote_currency=Currency.from_str(quote),
        price_precision=5,
        size_precision=0,
        price_increment=Price(1e-5, 5),
        size_increment=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


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

    frames = port._load_raw_bars(
        CatalogWindowRequest(
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

    frames = port._load_raw_bars(
        CatalogWindowRequest(
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

    first = port._load_raw_bars(
        CatalogWindowRequest(
            instrument_ids=(instrument_id,),
            start="2024-01-01",
            end="2024-01-03",
        )
    )
    second = port._load_raw_bars(
        CatalogWindowRequest(
            instrument_ids=(instrument_id,),
            start="2024-01-01",
            end="2024-01-03",
        )
    )

    assert first[instrument_id]["Close"].tolist() == [10.0, 11.0]
    assert second[instrument_id]["Close"].tolist() == [10.0, 11.0]
    assert provider.requests == [bar_type]


def test_catalog_port_serves_a_quote_marked_instrument_as_the_derived_mid(
    tmp_path: Path,
) -> None:
    """A declared-QUOTE instrument loads the mid derived from its stored BID/ASK
    bars — no MID-EXTERNAL series exists anywhere in the read (aegis-rd-tggo.2)."""
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("UEQC.XETR")
    resolver = DeclaredMarkingResolver(declared={instrument_id: MarkMode.QUOTE})
    bid_type, ask_type = resolver.resolve(instrument_id, "1D").mark_bars
    _write_span(
        catalog,
        [_bar(bid_type, "2024-01-01", 100.0), _bar(ask_type, "2024-01-01", 101.0)],
        start="2024-01-01",
        end="2024-01-02",
    )
    provider = _ProviderPort([])
    port = CatalogBackedDataPort(catalog, provider=provider, resolver=resolver)

    frames = port._load_raw_bars(
        CatalogWindowRequest(
            instrument_ids=(instrument_id,),
            start="2024-01-01",
            end="2024-01-02",
        )
    )

    assert frames[instrument_id]["Close"].tolist() == [100.5]
    assert provider.requests == []


def test_catalog_port_collapses_duplicate_ts_event_from_overlapping_batches(
    tmp_path: Path,
) -> None:
    """A stored series with two bars for one ts_event (see `_query_bars` for how a
    dense gap-filled series acquires them) reads back with a unique index: the read
    seam collapses per ts_event, or the quote-mid frame's index breaks downstream
    (the UEQC.IBIS:QUOTE regression, aegis-rd-bkom)."""
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("UEQC.XETR")
    resolver = DeclaredMarkingResolver(declared={instrument_id: MarkMode.QUOTE})
    bid_type, ask_type = resolver.resolve(instrument_id, "1D").mark_bars
    # The gap-fill's overlapping yearly batches consolidate into one file that carries TWO
    # bars for the boundary day 01-02 (the same day served twice with a slightly different
    # value; Nautilus' identity dedupe keeps both). Reproduce that persisted state directly:
    # one written series with a duplicated ts_event on each side.
    _write_span(
        catalog,
        [_bar(bid_type, "2024-01-01", 100.0), _bar(ask_type, "2024-01-01", 101.0),
         _bar(bid_type, "2024-01-02", 100.4), _bar(ask_type, "2024-01-02", 101.4),
         _bar(bid_type, "2024-01-02", 102.0), _bar(ask_type, "2024-01-02", 103.0),
         _bar(bid_type, "2024-01-03", 104.0), _bar(ask_type, "2024-01-03", 105.0)],
        start="2024-01-01",
        end="2024-01-04",
    )
    port = CatalogBackedDataPort(catalog, provider=_ProviderPort([]), resolver=resolver)

    frame = port._load_raw_bars(
        CatalogWindowRequest(
            instrument_ids=(instrument_id,),
            start="2024-01-01",
            end="2024-01-04",
        )
    )[instrument_id]

    # One row per ts_event: the boundary duplicate (01-02) is collapsed and the index stays
    # unique (before the fix the duplicate made a two-row index that broke downstream).
    assert frame.index.is_unique
    assert len(frame) == 3
    # The undisputed days mark at their mids; the boundary day is a single mid, not two.
    assert frame["Close"].iloc[0] == 100.5
    assert frame["Close"].iloc[-1] == 104.5


def test_catalog_port_cold_fills_a_quote_marked_instrument_from_bid_and_ask(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("UEQC.XETR")
    resolver = DeclaredMarkingResolver(declared={instrument_id: MarkMode.QUOTE})
    bid_type, ask_type = resolver.resolve(instrument_id, "1D").mark_bars
    provider = _QuoteProviderPort(
        {
            bid_type: [_bar(bid_type, "2024-01-01", 100.0)],
            ask_type: [_bar(ask_type, "2024-01-01", 101.0)],
        }
    )
    port = CatalogBackedDataPort(catalog, provider=provider, resolver=resolver)

    frames = port._load_raw_bars(
        CatalogWindowRequest(
            instrument_ids=(instrument_id,),
            start="2024-01-01",
            end="2024-01-02",
        )
    )

    assert frames[instrument_id]["Close"].tolist() == [100.5]
    assert provider.requests == [bid_type, ask_type]


def test_catalog_port_serves_sided_quote_frames_for_quote_marked_legs_only(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    quote_id = _id("UEQC.XETR")
    last_id = _id("AAPL.XNAS")
    resolver = DeclaredMarkingResolver(declared={quote_id: MarkMode.QUOTE})
    bid_type, ask_type = resolver.resolve(quote_id, "1D").mark_bars
    _write_span(
        catalog,
        [
            _bar(bid_type, "2024-01-01", 100.0),
            _bar(ask_type, "2024-01-01", 101.0),
            _bar(raw_bar_type(last_id, "1D"), "2024-01-01", 10.0),
        ],
        start="2024-01-01",
        end="2024-01-02",
    )
    port = CatalogBackedDataPort(catalog, provider=_ProviderPort([]), resolver=resolver)

    frames = port.load_quote_frames(
        CatalogWindowRequest(
            instrument_ids=(quote_id, last_id),
            start="2024-01-01",
            end="2024-01-02",
        )
    )

    assert set(frames) == {quote_id}
    bid_frame, ask_frame = frames[quote_id]
    assert bid_frame["Close"].tolist() == [100.0]
    assert ask_frame["Close"].tolist() == [101.0]


class _QuoteProviderPort:
    """Provider fake serving distinct bars per requested bar type."""

    def __init__(self, bars_by_type: dict[BarType, list[Bar]]) -> None:
        self.bars_by_type = bars_by_type
        self.requests: list[BarType] = []

    def request_bars(
        self,
        bar_type: BarType,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ServedBars:
        self.requests.append(bar_type)
        return ServedBars(tuple(self.bars_by_type[bar_type]), start)


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

    port._load_raw_bars(
        CatalogWindowRequest(
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

    port._load_raw_bars(
        CatalogWindowRequest(
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
        CatalogWindowRequest(
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
        port._load_raw_bars(
            CatalogWindowRequest(
                instrument_ids=(_id("AAPL.NASDAQ"),),
                start="2024-01-01",
                end="2024-01-02",
            )
        )


def test_catalog_port_persists_partial_fill_and_raises_gap_at_the_wall(
    tmp_path: Path,
) -> None:
    """The no-data wall at port altitude (#75): the provider returns only the
    history that exists, the port still writes those bars — even a failed fill
    leaves the catalog warmer — and the coverage gate, the sole unsatisfiability
    judge, raises naming the interval that remains missing."""
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("AAPL.NASDAQ")
    bar_type = raw_bar_type(instrument_id, "1D")
    provider = _ProviderPort(
        [_bar(bar_type, "2024-01-04", 10.0), _bar(bar_type, "2024-01-05", 11.0)],
        served_from="2024-01-04",
    )
    port = CatalogBackedDataPort(catalog, provider=provider)
    request = CatalogWindowRequest(
        instrument_ids=(instrument_id,),
        start="2024-01-01",
        end="2024-01-05",
    )

    with pytest.raises(CatalogCoverageGapError, match="2024-01-01") as excinfo:
        port._load_raw_bars(request)

    assert "missing=" in str(excinfo.value)
    warmed = port.read_native_bars(request)[instrument_id]
    assert len(warmed) == 2
    assert pd.Timestamp(warmed[0].ts_event, tz="UTC") == pd.Timestamp("2024-01-04", tz="UTC")
    assert pd.Timestamp(warmed[1].ts_event, tz="UTC") == pd.Timestamp("2024-01-05", tz="UTC")


def test_catalog_port_translates_a_provider_failure_into_a_port_error(
    tmp_path: Path,
) -> None:
    """No vendor type crosses the port: a Gap-Fill Provider failure during Ensure
    Coverage (gateway drop, timeout, stuck qualification) surfaces to the port
    caller as ``GapFillProviderError`` naming the fetch, with the vendor error
    chained as the cause."""
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("AAPL.NASDAQ")

    class _BrokenProvider:
        def request_bars(self, bar_type: BarType, **kwargs: Any) -> ServedBars:
            raise IbkrRequestError("IBKR could not fetch historical bars: ib down")

    port = CatalogBackedDataPort(catalog, provider=_BrokenProvider())
    request = CatalogWindowRequest(
        instrument_ids=(instrument_id,), start="2024-01-01", end="2024-01-05"
    )

    with pytest.raises(GapFillProviderError, match="AAPL.XNAS") as excinfo:
        port._load_raw_bars(request)

    assert not isinstance(excinfo.value, IbkrRequestError)
    assert isinstance(excinfo.value.__cause__, IbkrRequestError)


def test_gap_fill_failure_bounds_the_vendor_prose(tmp_path: Path) -> None:
    """The persisted message is the port's interface: it names the fault in one
    bounded line (type + the cause's first line, truncated); the full vendor
    error stays on the chained cause for logs."""
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    vendor_prose = "gateway fault " + "x" * 400 + "\nraw vendor stack line two"

    class _VerboseProvider:
        def request_bars(self, bar_type: BarType, **kwargs: Any) -> ServedBars:
            raise RuntimeError(vendor_prose)

    port = CatalogBackedDataPort(catalog, provider=_VerboseProvider())

    with pytest.raises(GapFillProviderError) as excinfo:
        port._load_raw_bars(
            CatalogWindowRequest(
                instrument_ids=(_id("AAPL.NASDAQ"),), start="2024-01-01", end="2024-01-05"
            )
        )

    message = str(excinfo.value)
    assert "RuntimeError" in message
    assert "gateway fault" in message
    assert "\n" not in message
    assert "line two" not in message
    assert len(message) < 320
    assert str(excinfo.value.__cause__) == vendor_prose


def test_catalog_port_translates_a_definition_seeder_failure_into_a_port_error(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("AAPL.NASDAQ")
    bar_type = raw_bar_type(instrument_id, "1D")
    provider = _ProviderPort(
        [_bar(bar_type, "2024-01-02", 10.0), _bar(bar_type, "2024-01-03", 11.0)]
    )

    def _broken_seeder(_: InstrumentId) -> None:
        raise IbkrRequestError("IBKR could not fetch instrument definitions: ib down")

    port = CatalogBackedDataPort(
        catalog, provider=provider, definition_seeder=_broken_seeder
    )

    with pytest.raises(GapFillProviderError) as excinfo:
        port._load_raw_bars(
            CatalogWindowRequest(
                instrument_ids=(instrument_id,), start="2024-01-02", end="2024-01-03"
            )
        )

    assert isinstance(excinfo.value.__cause__, IbkrRequestError)


def test_catalog_port_translates_a_distribution_fetch_failure_into_a_port_error(
    tmp_path: Path,
) -> None:
    """The adjusted-last fetch during Ensure Coverage is the same environmental
    failure as a bar-fill fault: it surfaces as ``GapFillProviderError``, never as
    the vendor error — while the coverage gate's own verdicts pass through."""
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

    class _BrokenAdjustedLast:
        def request_adjusted_last(self, **kwargs: Any) -> pd.Series:
            raise IbkrRequestError("IBKR could not fetch ADJUSTED_LAST closes: ib down")

    port = CatalogBackedDataPort(
        catalog, distribution_provider=_BrokenAdjustedLast()
    )

    with pytest.raises(GapFillProviderError, match="SPY.ARCA") as excinfo:
        port.load_window(CatalogWindowRequest((instrument_id,), start="2024-01-01", end="2024-01-04")).distributions

    assert isinstance(excinfo.value.__cause__, IbkrRequestError)


def test_catalog_port_rejects_unverified_distribution_events(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("AAPL.NASDAQ")
    _write_definition(catalog, instrument_id)
    bar_type = raw_bar_type(instrument_id, "1D")
    _write_span(
        catalog,
        [
            _bar(bar_type, "2024-01-01", 100.0),
            _bar(bar_type, "2024-01-02", 100.0),
            _bar(bar_type, "2024-01-03", 100.0),
        ],
        start="2024-01-01",
        end="2024-01-31",
    )
    distribution = Distribution.from_ex_date(
        instrument_id,
        "2024-01-15",
        amount=0.42,
        currency="USD",
    )
    write_distribution_data(catalog, [distribution])
    port = CatalogBackedDataPort(catalog)

    with pytest.raises(CatalogCoverageGapError, match="distribution coverage is missing"):
        port.load_window(CatalogWindowRequest(
            (instrument_id,),
            start="2024-01-01",
            end="2024-01-31",
        )).distributions


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

    first = port.load_window(CatalogWindowRequest(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-04",
    )).distributions
    warm = CatalogBackedDataPort(ParquetDataCatalog(catalog_path)).load_window(CatalogWindowRequest(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-04",
    )).distributions

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
    port.load_window(CatalogWindowRequest((instrument_id,), start="2024-01-01", end="2024-01-04")).distributions

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

    first = port.load_window(CatalogWindowRequest(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-04",
    )).distributions
    warm = CatalogBackedDataPort(ParquetDataCatalog(catalog_path)).load_window(CatalogWindowRequest(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-04",
    )).distributions

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
    bar_type = raw_bar_type(dated_leg, "1D")
    _write_span(
        catalog,
        [
            _bar(bar_type, "2024-01-01", 5000.0),
            _bar(bar_type, "2024-01-02", 5010.0),
        ],
        start="2024-01-01",
        end="2024-01-04",
    )

    # A dated futures leg rides the window read: not-applicable, no provider needed.
    window = CatalogBackedDataPort(catalog).load_window(CatalogWindowRequest(
        (dated_leg,),
        start="2024-01-01",
        end="2024-01-04",
    ))
    # A continuous root has no raw bars and can never enter a window request;
    # its verdict comes from the surviving coverage-report diagnostic query.
    root_report = CatalogBackedDataPort(catalog).distribution_coverage_report(
        (continuous_root,),
        start="2024-01-01",
        end="2024-01-04",
    )

    assert window.distributions == ()
    assert window.distribution_coverage[0]["applicable"] is False
    assert root_report[0]["applicable"] is False


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

    # The surviving diagnostic query (ADR-0012): a pure report for an id that
    # can never enter a window request — no verification is attempted, so no
    # marker is ever written for the root.
    report = port.distribution_coverage_report(
        (continuous_root,),
        start="2024-01-01",
        end="2024-01-04",
    )

    assert report[0]["instrument_id"] == "ES.XCME"
    assert report[0]["applicable"] is False
    assert report[0]["event_count"] == 0
    assert report[0]["checked_at"] is None


def test_catalog_port_skips_distribution_verification_for_cash_fx(
    tmp_path: Path,
) -> None:
    # A cash FX conversion leg in the id set is routine, not an error: no
    # provider is wired, so an applicable-but-unverified id would fail loud —
    # succeeding proves verification was never attempted for the pair.
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    fx_pair = _id("EUR/USD.IDEALPRO")
    _seed_fx_pair(catalog, fx_pair)

    events = CatalogBackedDataPort(
        catalog, resolver=_fx_mid_resolver(fx_pair)
    ).load_window(CatalogWindowRequest(
        (fx_pair,),
        start="2024-01-01",
        end="2024-01-04",
    )).distributions

    assert events == ()


def test_catalog_port_reports_cash_fx_distribution_coverage_not_applicable(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    fx_pair = _id("EUR/USD.IDEALPRO")
    _seed_fx_pair(catalog, fx_pair)
    port = CatalogBackedDataPort(catalog, resolver=_fx_mid_resolver(fx_pair))
    port.load_window(CatalogWindowRequest(
        (fx_pair,),
        start="2024-01-01",
        end="2024-01-04",
    )).distributions

    report = port.distribution_coverage_report(
        (fx_pair,),
        start="2024-01-01",
        end="2024-01-04",
    )

    assert report[0]["instrument_id"] == "EUR/USD.IDEALPRO"
    assert report[0]["applicable"] is False
    assert report[0]["event_count"] == 0
    assert report[0]["checked_at"] is not None


def test_catalog_port_cash_fx_distribution_reads_are_idempotent(
    tmp_path: Path,
) -> None:
    # The second read's clock runs EARLIER than the first's, and the report
    # surfaces the oldest marker in the window — so an unchanged checked_at
    # proves the second read wrote no duplicate marker.
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    fx_pair = _id("EUR/USD.IDEALPRO")
    _seed_fx_pair(catalog, fx_pair)
    window = {"start": "2024-01-01", "end": "2024-01-04"}
    CatalogBackedDataPort(
        catalog,
        clock_ns=lambda: pd.Timestamp("2026-01-02", tz="UTC").value,
        resolver=_fx_mid_resolver(fx_pair),
    ).load_window(CatalogWindowRequest((fx_pair,), **window)).distributions

    CatalogBackedDataPort(
        catalog,
        clock_ns=lambda: pd.Timestamp("2026-01-01", tz="UTC").value,
        resolver=_fx_mid_resolver(fx_pair),
    ).load_window(CatalogWindowRequest((fx_pair,), **window)).distributions

    report = CatalogBackedDataPort(catalog).distribution_coverage_report(
        (fx_pair,), **window
    )
    assert report[0]["applicable"] is False
    assert report[0]["checked_at"] == "2026-01-02T00:00:00+00:00"


def test_not_applicable_coverage_marks_disjointly_across_overlapping_windows(
    tmp_path: Path,
) -> None:
    """A not-applicable leg shared by two configs (a cash FX conversion pair) verified
    over OVERLAPPING windows must write DISJOINT coverage markers.  The second window
    marks only its missing tail, not the whole window over the first marker - which
    Nautilus rejects as a non-disjoint interval (the EUR/USD.IDEALPRO regression: the
    commodity book marked 2020-01-23..2025-01-01, the put-write book 2020-08-10..2026-07-01)."""
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    fx_pair = _id("EUR/USD.IDEALPRO")
    catalog.write_data([_currency_pair(fx_pair)])
    mid = external_bar_type(fx_pair, "1D", "MID")
    _write_span(
        catalog,
        [_bar(mid, "2020-02-03", 1.10), _bar(mid, "2026-06-01", 1.11)],
        start="2020-01-01",
        end="2027-01-01",
    )
    resolver = _fx_mid_resolver(fx_pair)

    # First config's window verifies + marks the shared leg over 2020-01-23..2025-01-01.
    CatalogBackedDataPort(catalog, resolver=resolver).load_window(
        CatalogWindowRequest((fx_pair,), start="2020-01-23", end="2025-01-01")
    )
    # Second config's OVERLAPPING window must not collide on the shared leg's marker.
    CatalogBackedDataPort(catalog, resolver=resolver).load_window(
        CatalogWindowRequest((fx_pair,), start="2020-08-10", end="2026-07-01")
    )

    # The union is fully marked: a read across both windows finds no coverage gap.
    report = CatalogBackedDataPort(catalog).distribution_coverage_report(
        (fx_pair,), start="2020-01-23", end="2026-07-01"
    )
    assert report[0]["applicable"] is False


def test_catalog_port_rejects_distribution_read_for_unresolved_instrument(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)

    # The surviving diagnostic query still fails loud for an unresolvable id
    # (through the window read the same typo fails earlier, at the bar gate
    # or the completeness check).
    with pytest.raises(CatalogCoverageGapError, match="cannot resolve"):
        CatalogBackedDataPort(catalog).distribution_coverage_report(
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
    for instrument_id in (spy, hyg):
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

    with pytest.raises(CatalogCoverageGapError) as error:
        CatalogBackedDataPort(catalog).load_window(CatalogWindowRequest(
            (spy, hyg),
            start="2024-01-01",
            end="2024-01-04",
        )).distributions

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

    with pytest.raises(CatalogCoverageGapError, match="distribution coverage is missing"):
        CatalogBackedDataPort(
            catalog,
            distribution_provider=_ProviderPort([]),
        ).load_window(CatalogWindowRequest(
            (instrument_id,),
            start="2024-01-01",
            end="2024-01-04",
        )).distributions


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
    ).load_window(CatalogWindowRequest(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-04",
    )).distributions

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

    later = port.load_window(CatalogWindowRequest(
        (instrument_id,),
        start="2024-01-03",
        end="2024-01-06",
    )).distributions
    extended = port.load_window(CatalogWindowRequest(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-06",
    )).distributions

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
    # The span is verified through 01-08 (a walked window can cover bar-less
    # days), but the bar FRONTIER sits at the last stored bar — verification
    # must clamp to it rather than chase days no close exists for.
    _write_span(
        catalog,
        [
            _bar(bar_type, "2024-01-01", 100.0),
            _bar(bar_type, "2024-01-02", 100.0),
            _bar(bar_type, "2024-01-03", 100.0),
        ],
        start="2024-01-01",
        end="2024-01-08",
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

    covered = port.load_window(CatalogWindowRequest(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-04",
    )).distributions
    extended = port.load_window(CatalogWindowRequest(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-08",
    )).distributions

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
        end="2024-01-04",
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
        CatalogBackedDataPort(catalog, distribution_provider=provider).load_window(CatalogWindowRequest(
            (instrument_id,),
            start="2024-01-01",
            end="2024-01-04",
        )).distributions


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
    port.load_window(CatalogWindowRequest((instrument_id,), start="2024-01-01", end="2024-01-03")).distributions
    port.load_window(CatalogWindowRequest((instrument_id,), start="2024-01-05", end="2024-01-07")).distributions
    provider.requests.clear()

    events = port.load_window(CatalogWindowRequest(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-07",
    )).distributions

    assert events == ()
    assert len(provider.requests) == 1
    assert provider.requests[0]["start"].date() == date(2024, 1, 3)
    assert provider.requests[0]["end"] < pd.Timestamp("2024-01-05", tz="UTC")


def test_catalog_port_load_window_returns_one_coherent_value(
    tmp_path: Path,
) -> None:
    # ADR-0012: one call answers the whole window — bars, complete definitions,
    # verified distributions, and the coverage report. The cash FX leg rides in
    # the same id set with no caller filtering, and ONE verification pass serves
    # both the distributions and the report (exactly one adjusted-last request).
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    equity_id = _id("SPY.ARCA")
    fx_pair = _id("EUR/USD.IDEALPRO")
    equity_bar_type = raw_bar_type(equity_id, "1D")
    fx_bar_type = external_bar_type(fx_pair, "1D", "MID")
    _write_span(
        catalog,
        [
            _bar(equity_bar_type, "2024-01-01", 100.0),
            _bar(equity_bar_type, "2024-01-02", 100.0),
            _bar(equity_bar_type, "2024-01-03", 100.0),
        ],
        start="2024-01-01",
        end="2024-01-04",
    )
    _write_span(
        catalog,
        [
            _bar(fx_bar_type, "2024-01-01", 1.10),
            _bar(fx_bar_type, "2024-01-02", 1.11),
            _bar(fx_bar_type, "2024-01-03", 1.12),
        ],
        start="2024-01-01",
        end="2024-01-04",
    )
    _write_definition(catalog, equity_id)
    catalog.write_data([_currency_pair(fx_pair)])
    provider = _AdjustedLastProvider(
        {
            equity_id: pd.Series(
                [100.0, 100.0 / (1.0 - 0.01), 100.0],
                index=pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC"),
            )
        }
    )
    port = CatalogBackedDataPort(
        catalog,
        distribution_provider=provider,
        resolver=_fx_mid_resolver(fx_pair),
    )

    window = port.load_window(
        CatalogWindowRequest(
            instrument_ids=(equity_id, fx_pair),
            start="2024-01-01",
            end="2024-01-04",
        )
    )

    assert set(window.ohlcv) == {equity_id, fx_pair}
    assert list(window.ohlcv[equity_id]["Close"]) == [100.0, 100.0, 100.0]
    assert set(window.instruments) == {equity_id, fx_pair}
    assert [(event.ex_date, event.amount) for event in window.distributions] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(1.0))
    ]
    coverage = {row["instrument_id"]: row for row in window.distribution_coverage}
    assert coverage["SPY.ARCA"]["applicable"] is True
    assert coverage["SPY.ARCA"]["event_count"] == 1
    assert coverage["EUR/USD.IDEALPRO"]["applicable"] is False
    assert coverage["EUR/USD.IDEALPRO"]["event_count"] == 0
    assert len(provider.requests) == 1


def test_catalog_port_load_window_completeness_passes_via_fill_seeded_definition(
    tmp_path: Path,
) -> None:
    # Ordering is contract: the lazy fill runs FIRST and its Step-1 write seeds
    # the definition, so completeness judged after filling must pass for an id
    # the fill itself resolves.
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("AAPL.XNAS")
    bar_type = raw_bar_type(instrument_id, "1D")
    provider = _ProviderPort(
        [
            _bar(bar_type, "2024-01-01", 10.0),
            _bar(bar_type, "2024-01-02", 10.0),
            _bar(bar_type, "2024-01-03", 10.0),
        ]
    )
    adjusted_last = _AdjustedLastProvider(
        {
            instrument_id: pd.Series(
                [10.0, 10.0, 10.0],
                index=pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC"),
            )
        }
    )
    port = CatalogBackedDataPort(
        catalog,
        provider=provider,
        distribution_provider=adjusted_last,
        definition_seeder=lambda seeded_id: _write_definition(catalog, seeded_id),
    )

    window = port.load_window(
        CatalogWindowRequest(
            instrument_ids=(instrument_id,),
            start="2024-01-01",
            end="2024-01-04",
        )
    )

    assert set(window.instruments) == {instrument_id}
    assert window.distributions == ()


def test_catalog_port_load_window_rejects_missing_definitions_as_authoring(
    tmp_path: Path,
) -> None:
    # Ordering is contract: completeness is judged BEFORE distribution
    # verification, so a missing definition surfaces as ONE authoring error
    # naming every missing id — never as the environmental coverage-gap error.
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    first, second = _id("SPY.ARCA"), _id("QQQ.XNAS")
    for instrument_id in (first, second):
        bar_type = raw_bar_type(instrument_id, "1D")
        _write_span(
            catalog,
            [
                _bar(bar_type, "2024-01-01", 100.0),
                _bar(bar_type, "2024-01-02", 100.0),
            ],
            start="2024-01-01",
            end="2024-01-03",
        )

    with pytest.raises(MissingCatalogDefinitionsError) as excinfo:
        CatalogBackedDataPort(catalog).load_window(
            CatalogWindowRequest(
                instrument_ids=(first, second),
                start="2024-01-01",
                end="2024-01-03",
            )
        )

    assert "SPY.ARCA" in str(excinfo.value)
    assert "QQQ.XNAS" in str(excinfo.value)
    assert not isinstance(excinfo.value, CatalogCoverageGapError)


def test_catalog_port_load_window_raises_environmental_errors_unchanged(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    catalog = ParquetDataCatalog(catalog_path)
    instrument_id = _id("SPY.ARCA")

    with pytest.raises(CatalogCoverageGapError, match="catalog cannot serve"):
        CatalogBackedDataPort(catalog).load_window(
            CatalogWindowRequest(
                instrument_ids=(instrument_id,),
                start="2024-01-01",
                end="2024-01-04",
            )
        )


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
    ).load_window(CatalogWindowRequest(
        (instrument_id,),
        start="2024-01-01",
        end="2024-01-06",
    )).distributions

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
    ).load_window(CatalogWindowRequest((instrument_id,), start="2024-01-01", end="2024-01-06")).distributions


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
