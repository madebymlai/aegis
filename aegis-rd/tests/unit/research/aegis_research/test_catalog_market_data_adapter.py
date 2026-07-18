from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from aegis_data.bar_type import mic_canonical_instrument_id
from aegis_data.catalog import CatalogBackedDataPort, CatalogCoverageGapError
from aegis_data.continuous_future import DEFAULT_ADJUSTMENT_MODE
from aegis_data.custom_data import FixtureRecord, ServedCustomData, correct
from aegis_data.marking import DeclaredMarkingResolver, MarkMode
from aegis_data.testing import FakeCatalog, bars, future
from aegis_runtime.currency import MissingFxPairError
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair, Equity, FuturesContract, Instrument
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.data import load_market_data_result
from research.aegis_research.market_data.adapters import catalog as catalog_adapter
from research.aegis_research.market_data.adapters.catalog import (
    ContinuousRootCollisionError,
    load_catalog_source,
)
from research.aegis_research.market_data.contracts import MarketDataUnavailableError
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


class _RecordingFakeCatalog(FakeCatalog):
    """FakeCatalog that records which bar identifiers the port reads.

    The port itself is never faked — the fake sits beneath a real
    ``CatalogBackedDataPort``, so the adapter tests inherit production port
    behavior (window read, completeness, applicability) for free.
    """

    def __init__(self, instruments: list[Instrument], bars: dict[str, list[Bar]]) -> None:
        super().__init__(instruments, bars)
        self.queried_bar_identifiers: list[str] = []

    def query(
        self,
        data_cls: type,
        identifiers: list[str] | None = None,
        start: object = None,
        end: object = None,
        **kwargs: object,
    ) -> list:
        if data_cls is Bar:
            self.queried_bar_identifiers.extend(identifiers or [])
        return super().query(data_cls, identifiers, start, end, **kwargs)


class _FixtureProvider:
    def __init__(self, *, value: float | None = None) -> None:
        self.value = value
        self.requests: list[tuple[InstrumentId, pd.Timestamp, pd.Timestamp]] = []

    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ServedCustomData[FixtureRecord]:
        self.requests.append((instrument_id, start, end))
        records = (
            ()
            if self.value is None
            else (
                FixtureRecord(
                    end.value,
                    end.value,
                    instrument_id=instrument_id,
                    value=self.value,
                    provider="fixture",
                ),
            )
        )
        return ServedCustomData(records=records, served_from=start)


def _fake_port(
    frames: dict[InstrumentId, pd.DataFrame],
    *,
    legs: list[FuturesContract] | None = None,
    exchange: tuple[InstrumentId, ...] = (),
) -> tuple[CatalogBackedDataPort, _RecordingFakeCatalog]:
    """A real port over a fake catalog seeded with *frames* and their definitions.

    ``legs`` seeds dated futures-contract definitions so a continuous root's
    coverage-report diagnostic can resolve its legs.  ``exchange`` carries the
    same structural declaration production supplies: a conversion leg is
    bar-marked MID by the config section that names it, never by symbol shape.
    """
    resolver = DeclaredMarkingResolver(declared=dict.fromkeys(exchange, MarkMode.MID))
    catalog = _RecordingFakeCatalog(
        instruments=[
            *(_definition(mic_canonical_instrument_id(iid)) for iid in frames),
            *(legs or []),
        ],
        # Keyed by the same resolver the port reads with, so seeded keys can
        # never drift from resolved keys.
        bars={
            str(resolver.resolve(iid, "1D").mark_bars[0]): bars(iid, frame)
            for iid, frame in frames.items()
        },
    )
    return CatalogBackedDataPort(catalog, resolver=resolver), catalog


def test_catalog_adapter_requests_exchange_ids_but_exposes_only_tradeable_columns() -> None:
    aapl = _id("AAPL.NASDAQ")
    esz6 = _id("ESZ6.XCME")
    eurusd = _id("EUR/USD.IDEALPRO")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port, catalog = _fake_port(
        {
            aapl: _frame(index, close=[10.0, 11.0], volume=[100.0, 110.0]),
            esz6: _frame(index, close=[20.0, 21.0], volume=[200.0, 210.0]),
            eurusd: _frame(index, close=[1.1, 1.2], volume=[0.0, 0.0]),
        },
        exchange=(eurusd,),
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
        port=port,
    )

    bundle = market_data_bundle(result)
    # The exchange leg is read from the catalog (its MID bar) but never surfaces
    # as a tradeable column.
    assert set(catalog.queried_bar_identifiers) == {
        "AAPL.XNAS-1-DAY-LAST-EXTERNAL",
        "ESZ6.XCME-1-DAY-LAST-EXTERNAL",
        "EUR/USD.IDEALPRO-1-DAY-MID-EXTERNAL",
    }
    assert list(bundle.array("Close").columns) == [aapl, esz6]
    assert bundle.array("Close").iloc[:, 0].tolist() == [10.0, 11.0]
    assert result.metadata.request.requested_instrument_ids == [aapl, esz6]
    assert to_builtin(result.metadata.request.requested_instrument_ids) == [
        "AAPL.NASDAQ",
        "ESZ6.XCME",
    ]
    assert result.metadata.provenance.index_evidence["source"] == "nautilus_catalog"
    port_metadata = result.metadata.provenance.port_metadata
    assert port_metadata["source"] == "nautilus_data_provider_port"
    # The window's coverage report is Run evidence — the FX leg rides the same
    # id set and lands as a not-applicable row, with no caller filtering.
    coverage = {row["instrument_id"]: row for row in port_metadata["distribution_coverage"]}
    assert coverage["EUR/USD.IDEALPRO"]["applicable"] is False
    assert coverage["EUR/USD.IDEALPRO"]["event_count"] == 0
    assert result.distributions == ()


def test_catalog_adapter_loads_custom_arrays_alongside_bar_arrays(
    tmp_path: Path,
) -> None:
    instrument_id = _id("AAPL.NASDAQ")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    catalog_path = tmp_path / "catalog"
    provider = _FixtureProvider(value=7.0)
    port, _catalog = _fake_port(
        {instrument_id: _frame(index, close=[10.0, 11.0], volume=[100.0, 110.0])}
    )
    config = make_data_config(
        arrays=["Close", "FixtureValue", "FixtureAvailable"],
        base_currency="USD",
        instruments=["AAPL.NASDAQ"],
        start="2024-01-01",
        end="2024-01-03",
        path=str(catalog_path),
    )

    result = load_market_data_result(
        config,
        port=port,
        custom_data_providers={FixtureRecord: (provider,)},
    )

    bundle = market_data_bundle(result)
    assert bundle.array("Close")[instrument_id].tolist() == [10.0, 11.0]
    assert bundle.array("FixtureValue")[instrument_id].tolist() == [0.0, 7.0]
    assert bundle.array("FixtureAvailable")[instrument_id].tolist() == [0.0, 1.0]


def test_catalog_adapter_fills_custom_array_coverage_on_cold_load(
    tmp_path: Path,
) -> None:
    instrument_id = _id("AAPL.NASDAQ")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    catalog_path = tmp_path / "catalog"
    provider = _FixtureProvider(value=7.0)
    port, _catalog = _fake_port(
        {instrument_id: _frame(index, close=[10.0, 11.0], volume=[100.0, 110.0])}
    )
    config = make_data_config(
        arrays=["Close", "FixtureValue", "FixtureAvailable"],
        base_currency="USD",
        instruments=["AAPL.NASDAQ"],
        start="2024-01-01",
        end="2024-01-03",
        path=str(catalog_path),
    )

    load_market_data_result(
        config,
        port=port,
        custom_data_providers={FixtureRecord: (provider,)},
    )

    assert provider.requests == [
        (
            instrument_id,
            pd.Timestamp("2024-01-01", tz="UTC"),
            pd.Timestamp("2024-01-02", tz="UTC"),
        )
    ]


def test_catalog_adapter_does_not_request_custom_data_for_covered_window(
    tmp_path: Path,
) -> None:
    instrument_id = _id("AAPL.NASDAQ")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    catalog_path = tmp_path / "catalog"
    _cover_fixture(
        catalog_path,
        instrument_id,
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-01-02", tz="UTC"),
        value=7.0,
    )
    port, _catalog = _fake_port(
        {instrument_id: _frame(index, close=[10.0, 11.0], volume=[100.0, 110.0])}
    )
    config = make_data_config(
        arrays=["Close", "FixtureValue", "FixtureAvailable"],
        base_currency="USD",
        instruments=["AAPL.NASDAQ"],
        start="2024-01-01",
        end="2024-01-03",
        path=str(catalog_path),
    )
    unused = _FixtureProvider()

    load_market_data_result(
        config,
        port=port,
        custom_data_providers={FixtureRecord: (unused,)},
    )

    assert unused.requests == []


def test_catalog_adapter_reports_unavailable_custom_data_without_provider(
    tmp_path: Path,
) -> None:
    instrument_id = _id("AAPL.NASDAQ")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    catalog_path = tmp_path / "catalog"
    port, _catalog = _fake_port(
        {instrument_id: _frame(index, close=[10.0, 11.0], volume=[100.0, 110.0])}
    )
    config = make_data_config(
        arrays=["Close", "FixtureValue", "FixtureAvailable"],
        base_currency="USD",
        instruments=["AAPL.NASDAQ"],
        start="2024-01-01",
        end="2024-01-03",
        path=str(catalog_path),
    )

    result = load_market_data_result(config, port=port)

    assert result.quality.state == "data_unavailable"
    assert result.native_data is None


def test_catalog_adapter_preserves_custom_panels_through_vbt(
    tmp_path: Path,
) -> None:
    first = _id("AAPL.NASDAQ")
    second = _id("MSFT.NASDAQ")
    instrument_ids = (first, second)
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    catalog_path = tmp_path / "catalog"
    start = pd.Timestamp("2024-01-01", tz="UTC")
    end = pd.Timestamp("2024-01-02", tz="UTC")
    _cover_fixture(
        catalog_path,
        first,
        start=start,
        end=end,
        value=7.0,
    )
    _cover_fixture(
        catalog_path,
        second,
        start=start,
        end=end,
    )
    port, _catalog = _fake_port(
        {
            first: _frame(index, close=[10.0, 11.0], volume=[100.0, 110.0]),
            second: _frame(index, close=[20.0, 21.0], volume=[200.0, 210.0]),
        }
    )
    config = make_data_config(
        arrays=["Close", "FixtureValue", "FixtureAvailable"],
        base_currency="USD",
        instruments=["AAPL.NASDAQ", "MSFT.NASDAQ"],
        start="2024-01-01",
        end="2024-01-03",
        path=str(catalog_path),
    )
    expected_value = pd.DataFrame(
        [[0.0, 0.0], [7.0, 0.0]], index=index, columns=instrument_ids
    )
    expected_available = pd.DataFrame(
        [[0.0, 0.0], [1.0, 0.0]], index=index, columns=instrument_ids
    )

    result = load_market_data_result(config, port=port)

    bundle = market_data_bundle(result)
    pd.testing.assert_frame_equal(bundle.array("FixtureValue"), expected_value)
    pd.testing.assert_frame_equal(bundle.array("FixtureAvailable"), expected_available)


def test_catalog_adapter_merges_continuous_future_roots_as_tradeable_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aapl = _id("AAPL.NASDAQ")
    es = _id("ES.XCME")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port, catalog = _fake_port(
        {aapl: _frame(index, close=[10.0, 11.0], volume=[100.0, 110.0])},
        legs=[future("ESH4.XCME", "2024-03-15")],
    )
    continuous = {es: _frame(index, close=[5000.0, 5010.0], volume=[1.0, 2.0])}

    seen_roots: list = []
    seen_modes: list = []

    class FakeContinuousModel:
        quote_currency = "USD"

        def __init__(self, _port_arg, root, *, adjustment_mode, **_kwargs):
            seen_roots.append(str(root))
            seen_modes.append(adjustment_mode)
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
        port=port,
    )

    bundle = market_data_bundle(result)
    # Continuous roots are synthetic — never raw-requested from the catalog.
    assert set(catalog.queried_bar_identifiers) == {"AAPL.XNAS-1-DAY-LAST-EXTERNAL"}
    assert seen_roots == ["ES"]
    # The continuous root is a first-class tradeable column, ordered after raw instruments.
    assert list(bundle.array("Close").columns) == [aapl, es]
    assert bundle.array("Close")[es].tolist() == [5000.0, 5010.0]
    assert bundle.array("Volume")[es].tolist() == [1.0, 2.0]
    assert result.metadata.provenance.source_metadata["continuous_root_ids"] == ["ES.XCME"]
    # The root can never enter the window request (no raw bars), but its
    # not-applicable coverage row still reaches Run evidence through the port's
    # coverage-report diagnostic query.
    coverage = {
        row["instrument_id"]: row
        for row in result.metadata.provenance.port_metadata["distribution_coverage"]
    }
    assert coverage["ES.XCME"]["applicable"] is False
    # The recorded fact IS the value supplied to materialisation — selected once,
    # never a separately re-read constant.
    assert seen_modes == [DEFAULT_ADJUSTMENT_MODE]
    assert result.adjustment_mode is seen_modes[0]


def test_catalog_adapter_converts_a_non_base_continuous_root_through_exchange_fx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A USD-quoted continuous root in a EUR-base book joins the same native->base
    conversion as native instruments (closing the foreign-futures parity gap), and
    the derived root currency lands in source metadata -> Candidate data identity."""
    es = _id("ES.XCME")
    eurusd = _id("EUR/USD.IDEALPRO")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port, _catalog = _fake_port(
        {eurusd: _frame(index, close=[1.25, 1.20], volume=[0.0, 0.0])},
        legs=[future("ESH4.XCME", "2024-03-15")],
        exchange=(eurusd,),
    )

    class FakeContinuousModel:
        quote_currency = "USD"

        def __init__(self, _port_arg, _root, **_kwargs):
            self.continuous_id = es
            self.frame = _frame(index, close=[5000.0, 5010.0], volume=[1.0, 2.0])

        def materialize(self, *, end: str) -> None:
            assert end == "2024-01-03"

    monkeypatch.setattr(catalog_adapter, "ContinuousContractModel", FakeContinuousModel)
    config = make_data_config(
        arrays=["Close", "Volume"],
        base_currency="EUR",
        instruments=[],
        futures=["ES"],
        exchange=["EUR/USD.IDEALPRO"],
        start="2024-01-01",
        end="2024-01-03",
    )

    result = load_catalog_source(config, port=port)

    assert result.source_metadata["continuous_root_currencies"] == {"ES.XCME": "USD"}
    conversion = result.currency_conversion
    assert conversion is not None
    # USD -> EUR is the inverse of the declared EUR/USD pair, applied per period.
    converted = conversion.apply(
        {"Close": pd.DataFrame({es: [5000.0, 5010.0]}, index=index)}
    )["Close"]
    assert converted[es].tolist() == pytest.approx([5000.0 / 1.25, 5010.0 / 1.20])


def test_catalog_adapter_fails_loud_for_a_non_base_continuous_root_without_fx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-base continuous root with no matching FX pair fails at research loading
    exactly as a non-base native instrument does."""
    es = _id("ES.XCME")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port, _catalog = _fake_port({})

    class FakeContinuousModel:
        quote_currency = "USD"

        def __init__(self, _port_arg, _root, **_kwargs):
            self.continuous_id = es
            self.frame = _frame(index, close=[5000.0, 5010.0], volume=[1.0, 2.0])

        def materialize(self, *, end: str) -> None:
            pass

    monkeypatch.setattr(catalog_adapter, "ContinuousContractModel", FakeContinuousModel)
    config = make_data_config(
        arrays=["Close", "Volume"],
        base_currency="EUR",
        instruments=[],
        futures=["ES"],
        start="2024-01-01",
        end="2024-01-03",
    )

    with pytest.raises(MissingFxPairError, match=r"ES\.XCME"):
        load_catalog_source(config, port=port)


def test_catalog_adapter_returns_no_adjustment_mode_without_futures() -> None:
    aapl = _id("AAPL.NASDAQ")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port, _catalog = _fake_port(
        {aapl: _frame(index, close=[10.0, 11.0], volume=[100.0, 110.0])}
    )
    config = make_data_config(
        arrays=["Close", "Volume"],
        base_currency="USD",
        instruments=["AAPL.NASDAQ"],
        start="2024-01-01",
        end="2024-01-03",
    )

    result = load_market_data_result(
        config,
        port=port,
    )

    assert result.adjustment_mode is None


def test_catalog_adapter_rejects_a_continuous_root_colliding_with_a_raw_instrument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A synthetic root id that equals a raw instrument id would silently clobber the raw
    # column on merge — fail loud instead.
    es = _id("ES.XCME")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port, _catalog = _fake_port(
        {es: _frame(index, close=[10.0, 11.0], volume=[1.0, 1.0])}
    )

    class FakeContinuousModel:
        quote_currency = "USD"

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


def test_catalog_adapter_accepts_declared_empty_distributions() -> None:
    aapl = _id("AAPL.NASDAQ")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port, _catalog = _fake_port(
        {aapl: _frame(index, close=[10.0, 11.0], volume=[100.0, 110.0])}
    )
    config = make_data_config(
        arrays=["Close", "Volume"],
        base_currency="USD",
        instruments=["AAPL.NASDAQ"],
        start="2024-01-01",
        end="2024-01-03",
    )

    result = load_catalog_source(config, port=port)

    assert result.distributions == ()


class _AdjustedLastProvider:
    def __init__(self, adjusted_last: pd.Series) -> None:
        self.adjusted_last = adjusted_last

    def request_adjusted_last(self, **_kwargs: Any) -> pd.Series:
        return self.adjusted_last


def test_catalog_adapter_reads_distributions_after_catalog_port_verification(
    tmp_path: Path,
) -> None:
    instrument_id = _id("SPY.ARCA")
    catalog_path = tmp_path / "catalog"
    catalog = _warm_catalog(catalog_path, instrument_id)
    dates = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    port = CatalogBackedDataPort(
        catalog,
        distribution_provider=_AdjustedLastProvider(
            pd.Series([100.0, 100.0 / (1.0 - 0.01), 100.0], index=dates)
        ),
    )
    config = make_data_config(
        arrays=["Close", "Volume"],
        base_currency="USD",
        instruments=["SPY.ARCA"],
        start="2024-01-01",
        end="2024-01-04",
        path=str(catalog_path),
    )

    result = load_catalog_source(config, port=port)

    assert [(event.ex_date, event.amount) for event in result.distributions] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(1.0))
    ]


def test_catalog_adapter_records_distribution_coverage_in_quality_metadata(
    tmp_path: Path,
) -> None:
    instrument_id = _id("SPY.ARCA")
    catalog_path = tmp_path / "catalog"
    catalog = _warm_catalog(catalog_path, instrument_id)
    dates = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    port = CatalogBackedDataPort(
        catalog,
        distribution_provider=_AdjustedLastProvider(
            pd.Series([100.0, 100.0 / (1.0 - 0.01), 100.0], index=dates)
        ),
    )
    config = make_data_config(
        arrays=["Close", "Volume"],
        base_currency="USD",
        instruments=["SPY.ARCA"],
        start="2024-01-01",
        end="2024-01-04",
        path=str(catalog_path),
    )

    result = load_market_data_result(
        config,
        port=port,
    )

    coverage = result.metadata.provenance.port_metadata["distribution_coverage"]
    assert coverage[0]["instrument_id"] == "SPY.ARCA"
    assert coverage[0]["applicable"] is True
    assert coverage[0]["verified_start"] == "2024-01-01T00:00:00+00:00"
    assert coverage[0]["verified_end"] == "2024-01-04T00:00:00+00:00"
    assert coverage[0]["event_count"] == 1
    assert result.quality.warnings == ()


def test_catalog_adapter_fails_loud_without_distribution_provider(
    tmp_path: Path,
) -> None:
    instrument_id = _id("SPY.ARCA")
    catalog_path = tmp_path / "catalog"
    catalog = _warm_catalog(catalog_path, instrument_id)
    config = make_data_config(
        arrays=["Close", "Volume"],
        base_currency="USD",
        instruments=["SPY.ARCA"],
        start="2024-01-01",
        end="2024-01-04",
        path=str(catalog_path),
    )

    # The port's coverage verdict is environmental, so the loader surfaces it in
    # RD vocabulary — still loud, with the port's judgement chained and quoted.
    with pytest.raises(
        MarketDataUnavailableError, match="distribution coverage is missing"
    ) as excinfo:
        load_catalog_source(config, port=CatalogBackedDataPort(catalog))

    assert isinstance(excinfo.value.__cause__, CatalogCoverageGapError)


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


def _cover_fixture(
    catalog_path: Path,
    instrument_id: InstrumentId,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    value: float | None = None,
) -> None:
    records = (
        ()
        if value is None
        else (
            FixtureRecord(
                end.value,
                end.value,
                instrument_id=instrument_id,
                value=value,
                provider="fixture",
            ),
        )
    )
    correct(
        FixtureRecord,
        instrument_id,
        records,
        start=start,
        end=end,
        catalog_path=catalog_path,
    )


def _warm_catalog(path: Path, instrument_id: InstrumentId) -> ParquetDataCatalog:
    catalog = ParquetDataCatalog(path)
    # IBKR stores the definition under the MIC venue, exactly where the bars land.
    catalog.write_data([_definition(mic_canonical_instrument_id(instrument_id))])
    frame = _frame(
        pd.DatetimeIndex(["2024-01-01", "2024-01-02", "2024-01-03"]),
        close=[100.0, 100.0, 100.0],
        volume=[100.0, 100.0, 100.0],
    )
    catalog.write_data(
        bars(instrument_id, frame),
        start=pd.Timestamp("2024-01-01", tz="UTC").value,
        end=pd.Timestamp("2024-01-04", tz="UTC").value,
    )
    return catalog


def test_catalog_adapter_drop_policy_intersects_mixed_exchange_calendars() -> None:
    # An LSE leg and a Xetra/SIX leg share most days but hold disjoint holidays; the
    # declared ``missing_index: drop`` policy must intersect the calendars instead of
    # union-joining a NaN-holed panel the quality gate then rejects.
    lse = _id("SDHY.LSEETF")
    xbru = _id("XAT1.XBRU")
    lse_index = pd.DatetimeIndex(["2024-01-01", "2024-01-02", "2024-01-04"])
    xbru_index = pd.DatetimeIndex(["2024-01-01", "2024-01-03", "2024-01-04"])
    port, _catalog = _fake_port(
        {
            lse: _frame(lse_index, close=[10.0, 11.0, 12.0], volume=[100.0, 110.0, 120.0]),
            xbru: _frame(xbru_index, close=[20.0, 21.0, 22.0], volume=[200.0, 210.0, 220.0]),
        }
    )
    config = make_data_config(
        arrays=["Close", "Volume"],
        base_currency="USD",
        instruments=["SDHY.LSEETF", "XAT1.XBRU"],
        start="2024-01-01",
        end="2024-01-05",
        missing_index="drop",
    )

    result = load_market_data_result(
        config,
        port=port,
    )

    close = market_data_bundle(result).array("Close")
    assert list(close.index) == list(
        pd.DatetimeIndex(["2024-01-01", "2024-01-04"], tz=close.index.tz)
    )
    assert not close.isna().any().any()
    assert close[lse].tolist() == [10.0, 12.0]
    assert close[xbru].tolist() == [20.0, 22.0]
    assert result.quality.state == "healthy"
