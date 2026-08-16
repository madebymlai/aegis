"""End-to-end catalog-backed Trader backtest runner tests.

The runner composes the forward path: Book Config -> Execution Bundle contracts
with native ``InstrumentId`` values -> Nautilus ``ParquetDataCatalog`` -> real
``BacktestEngine`` -> live ``RebalanceStrategy``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from aegis_data.custom_data import CustomDataProviderPort, ensure_arrays
from tests.support.custom_data import FixtureRecord
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency, Price, Quantity

from aegis_data.catalog import (
    CatalogBackedDataPort,
    MissingCatalogDefinitionsError,
    raw_bar_type,
)
from aegis_data.custom_data import CustomDataWarmer
from aegis_data.ibkr import historic_catalog_client_factory
from aegis_data.marking import MarkMode
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey
from aegis_data.testing import store_instrument_fixtures
from aegis_runtime.domain.rebasing import Rebasing, spread_rebasing
from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    LockedExecutionPlan,
    MarketDataBundle,
    MissingIndexPolicy,
)

from aegis_runtime.domain.currency import CurrencyConversion

from aegis_trader.backtest import (
    BacktestMarketData,
    CatalogBacktestDataSource,
    CatalogInstrumentError,
    ContractDataError,
    run_book_backtest,
)
from aegis_trader.domain.roll import RollEvent, SubscribeBars, UnsubscribeBars
from aegis_trader.domain.types import SleeveName
from aegis_trader.portfolio import NautilusBookState
from aegis_trader.trader.strategy import RebalanceStrategy
from tests.support.bundle_double import BundleDouble, make_bundle_registry
from tests.support.market_data import bar_window_from_frames

_INSTRUMENT_ID = InstrumentId.from_str("VUSA.XLON")
_SECOND_INSTRUMENT_ID = InstrumentId.from_str("AAPL.XNAS")
_ES = InstrumentId.from_str("ES.XCME")
_ES_OLD = InstrumentId.from_str("ESM4.XCME")
_ES_NEW = InstrumentId.from_str("ESU4.XCME")
_WHEEL = "synth-trend.whl"
_TREND = SleeveName("trend")
# One accrual per night actually held: the coalesced re-net alert submits
# orders 1ns after the trigger bar, so the venue's financing module no longer
# sees a just-created borrow during the same event and never charges the
# phantom day-of-borrowing that the pre-coalescing flow accrued
# (aegis-rd-9qkr.3).
_FINANCING_FIXTURE_EXPECTED_COST = 150.059254

_BOOK_TOML = f"""
base_currency = "EUR"

[[sleeves]]
name = "trend"
wheel_filename = "{_WHEEL}"
risk_share = 1.0
group = "Floor"
"""

_FINANCING_BOOK_TOML = f"""
base_currency = "EUR"
gross_cap = 2.0
net_cap = 2.0

[costs.margin_interest]
EUR = 0.036

[[sleeves]]
name = "trend"
wheel_filename = "{_WHEEL}"
risk_share = 1.0
group = "Floor"
"""

_ZERO_RATE_FINANCING_BOOK_TOML = _FINANCING_BOOK_TOML.replace(
    "EUR = 0.036",
    "EUR = 0.0",
)


class _FixedWeightBundle(BundleDouble):
    """Synthetic bundle that returns one fixed target weight."""

    def __init__(
        self,
        instrument_id: InstrumentId,
        weight: float,
    ) -> None:
        self._instrument_id = instrument_id
        self._weight = weight
        contract = DataContract(
            instrument_ids=(instrument_id,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
            mark_modes={instrument_id: "LAST"},
        )
        manifest = BundleManifest(
            run_id="catalog-runner-synth",
            role="synth",
            candidate_key="catalog-runner-synth-key",
            component_source_hashes={},
            instrument_ids=(instrument_id,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="fixed_weight",
                module="synth",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            instrument_bands={instrument_id: DriftBand.symmetric(0.02)},
            direction="longonly",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        weights = pd.DataFrame(
            {self._instrument_id: [self._weight] * len(close)},
            index=close.index,
        )
        weights.columns.name = "instrument_id"
        return weights


class _FixtureArrayBundle(BundleDouble):
    """Synthetic bundle whose target is supplied by a Custom Data panel."""

    def __init__(self, instrument_id: InstrumentId) -> None:
        self._instrument_id = instrument_id
        contract = DataContract(
            instrument_ids=(instrument_id,),
            required_arrays=("Close", "FixtureValue", "FixtureAvailable"),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
            mark_modes={instrument_id: "LAST"},
        )
        manifest = BundleManifest(
            run_id="catalog-runner-fixture-array",
            role="synth",
            candidate_key="catalog-runner-fixture-array-key",
            component_source_hashes={},
            instrument_ids=(instrument_id,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="fixture_array_weight",
                module="synth",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            instrument_bands={instrument_id: DriftBand.symmetric(0.02)},
            direction="longonly",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        available = native_prices.array("FixtureAvailable")
        value = native_prices.array("FixtureValue")
        return value.where(available == 1.0, 0.0)


class _FixtureProvider(CustomDataProviderPort[FixtureRecord]):
    def __init__(self) -> None:
        self.requests: list[tuple[InstrumentId, pd.Timestamp, pd.Timestamp]] = []

    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> tuple[FixtureRecord, ...]:
        self.requests.append((instrument_id, start, end))
        timestamp = pd.Timestamp("2020-01-01", tz="UTC").value
        return (
            FixtureRecord(
                timestamp,
                timestamp,
                instrument_id=instrument_id,
                value=0.5,
                provider="fixture",
            ),
        )


class _AdjustedLastProvider:
    def __init__(self, adjusted_last: dict[InstrumentId, pd.Series]) -> None:
        self.adjusted_last = adjusted_last

    def request_adjusted_last(self, **kwargs: Any) -> pd.Series:
        return self.adjusted_last[kwargs["instrument_id"]]


def _adjusted_close_warmer(catalog: Catalog, provider: Any) -> CustomDataWarmer:
    return CustomDataWarmer(
        catalog,
        historic_catalog_client_factory(provider),
    )


class _TwoVenueBundle(BundleDouble):
    """Synthetic bundle that targets instruments on two native venues."""

    def __init__(self) -> None:
        self._instrument_ids = (_INSTRUMENT_ID, _SECOND_INSTRUMENT_ID)
        contract = DataContract(
            instrument_ids=self._instrument_ids,
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
            mark_modes={
                instrument_id: "LAST" for instrument_id in self._instrument_ids
            },
        )
        manifest = BundleManifest(
            run_id="catalog-runner-two-venue",
            role="synth",
            candidate_key="catalog-runner-two-venue-key",
            component_source_hashes={},
            instrument_ids=self._instrument_ids,
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="two_venue_fixed_weight",
                module="synth",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            instrument_bands={
                instrument_id: DriftBand.symmetric(0.0)
                for instrument_id in self._instrument_ids
            },
            direction="longonly",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        weights = pd.DataFrame(
            {
                _INSTRUMENT_ID: [0.25] * len(close),
                _SECOND_INSTRUMENT_ID: [0.25] * len(close),
            },
            index=close.index,
        )
        weights.columns.name = "instrument_id"
        return weights


class _ContinuousRootBundle(BundleDouble):
    """Synthetic bundle that targets the declared continuous-root id."""

    def __init__(self) -> None:
        contract = DataContract(
            instrument_ids=(_ES,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
            futures=("ES",),
            adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
        )
        manifest = BundleManifest(
            run_id="catalog-runner-continuous-root",
            role="synth",
            candidate_key="catalog-runner-continuous-root-key",
            component_source_hashes={},
            instrument_ids=(_ES,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="continuous_root_fixed_weight",
                module="synth",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            instrument_bands={_ES: DriftBand.symmetric(0.02)},
            direction="longonly",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        weights = pd.DataFrame({_ES: [0.1] * len(close)}, index=close.index)
        weights.columns.name = "instrument_id"
        return weights


class _StaticContinuousDesk:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def start(self, **_kwargs: object) -> tuple[object, ...]:
        return (SubscribeBars(_ES, "1D"),)

    def series(self, instrument_id: InstrumentId) -> pd.DataFrame | None:
        if instrument_id != _ES:
            return None
        return self._frame

    def front_leg(self, instrument_id: InstrumentId) -> InstrumentId | None:
        if instrument_id != _ES:
            return None
        return _ES

    def continuous_id(self, leg: InstrumentId) -> InstrumentId | None:
        return _ES if leg == _ES else None

    def on_bar(self, _bar: Bar) -> tuple[object, ...]:
        return ()

    def on_instrument(self, _instrument_id: InstrumentId) -> tuple[object, ...]:
        return ()


class _RollingContinuousDesk:
    def __init__(
        self,
        frame: pd.DataFrame,
        *,
        front: InstrumentId,
        roll_to: InstrumentId,
        rebasing: Rebasing,
    ) -> None:
        self._frame = frame
        self._front = front
        self._roll_to = roll_to
        self._rebasing = rebasing
        self._rolled = False

    def start(self, **_kwargs: object) -> tuple[object, ...]:
        return (SubscribeBars(self._front, "1D"),)

    def series(self, instrument_id: InstrumentId) -> pd.DataFrame | None:
        if instrument_id != _ES:
            return None
        return self._frame

    def front_leg(self, instrument_id: InstrumentId) -> InstrumentId | None:
        if instrument_id != _ES:
            return None
        return self._front

    def continuous_id(self, leg: InstrumentId) -> InstrumentId | None:
        return _ES if leg == self._front else None

    def on_bar(self, bar: Bar) -> tuple[object, ...]:
        if self._rolled or bar.bar_type.instrument_id != self._front:
            return ()
        old_front = self._front
        self._front = self._roll_to
        self._rolled = True
        return (
            UnsubscribeBars(old_front, "1D"),
            SubscribeBars(self._front, "1D"),
            RollEvent(continuous_id=_ES, rebasing=self._rebasing),
        )

    def on_instrument(self, _instrument_id: InstrumentId) -> tuple[object, ...]:
        return ()

    @property
    def rolled(self) -> bool:
        return self._rolled


class _ContinuousRootDataSource:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def load(
        self,
        instrument_ids: tuple[InstrumentId, ...],
        *,
        timeframe: str,
        start: str,
        end: str,
    ) -> BacktestMarketData:
        assert instrument_ids == ()
        assert (timeframe, start, end) == ("1D", "2020-01-01", "2020-01-05")
        return BacktestMarketData(
            instruments={_ES: _equity(_ES)},
            bar_windows={
                _ES: bar_window_from_frames(_ES, "1D", MarkMode.LAST, (self._frame,))
            },
        )


class _RollingContinuousRootDataSource:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def load(
        self,
        instrument_ids: tuple[InstrumentId, ...],
        *,
        timeframe: str,
        start: str,
        end: str,
    ) -> BacktestMarketData:
        assert instrument_ids == ()
        assert (timeframe, start, end) == ("1D", "2020-01-01", "2020-01-06")
        return BacktestMarketData(
            instruments={
                _ES: _equity(_ES),
                _ES_OLD: _equity(_ES_OLD),
                _ES_NEW: _equity(_ES_NEW),
            },
            bar_windows={
                _ES: bar_window_from_frames(_ES, "1D", MarkMode.LAST, (self._frame,)),
                _ES_OLD: bar_window_from_frames(
                    _ES_OLD, "1D", MarkMode.LAST, (self._frame.iloc[:1],)
                ),
                _ES_NEW: bar_window_from_frames(
                    _ES_NEW, "1D", MarkMode.LAST, (self._frame.iloc[1:],)
                ),
            },
        )


def test_run_book_backtest_runs_live_strategy_from_catalog(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_catalog(catalog_path, _INSTRUMENT_ID, [100.0, 101.0, 102.0, 103.0])
    registry = make_bundle_registry({_WHEEL: _FixedWeightBundle(_INSTRUMENT_ID, 0.5)})

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        catalog_path=catalog_path,
        registry=registry,
        data_source=_zero_distribution_source(catalog_path, (_INSTRUMENT_ID,)),
    )
    engine = result.engine

    fills = _closed_orders(engine)
    assert len(fills) == 1
    assert fills[0].instrument_id == _INSTRUMENT_ID
    engine.dispose()


def test_run_book_backtest_feeds_native_catalog_bars_to_nautilus(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    catalog = Catalog.open(catalog_path)
    store_instrument_fixtures(catalog, [_equity(_INSTRUMENT_ID)])
    bar_type = raw_bar_type(_INSTRUMENT_ID, "1D")
    bars = (
        _bar_with_init_delay(bar_type, "2020-01-01", 100.0),
        _bar_with_init_delay(bar_type, "2020-01-02", 101.0),
        _bar_with_init_delay(bar_type, "2020-01-03", 102.0),
        _bar_with_init_delay(bar_type, "2020-01-04", 103.0),
    )
    catalog.replace(
        CatalogKey.for_bar(bar_type),
        CatalogInterval(
            pd.Timestamp("2020-01-01", tz="UTC").value,
            pd.Timestamp("2020-01-05", tz="UTC").value,
        ),
        bars,
    )
    registry = make_bundle_registry({_WHEEL: _FixedWeightBundle(_INSTRUMENT_ID, 0.5)})

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        catalog_path=catalog_path,
        registry=registry,
        data_source=_zero_distribution_source(catalog_path, (_INSTRUMENT_ID,)),
    )

    try:
        assert result.engine.cache.bar(bar_type) == bars[-1]
    finally:
        result.engine.dispose()


def test_run_book_backtest_computes_with_a_declared_custom_array(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_catalog(catalog_path, _INSTRUMENT_ID, [100.0, 101.0, 102.0, 103.0])
    provider = _FixtureProvider()
    registry = make_bundle_registry({_WHEEL: _FixtureArrayBundle(_INSTRUMENT_ID)})

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        catalog_path=catalog_path,
        registry=registry,
        data_source=_zero_distribution_source(catalog_path, (_INSTRUMENT_ID,)),
        custom_data_providers={FixtureRecord: provider},
    )

    try:
        fills = _closed_orders(result.engine)
        assert len(fills) == 1
        assert fills[0].instrument_id == _INSTRUMENT_ID
    finally:
        result.engine.dispose()


def test_run_book_backtest_fills_custom_array_coverage_on_cold_catalog(
    tmp_path,
) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_catalog(catalog_path, _INSTRUMENT_ID, [100.0, 101.0, 102.0, 103.0])
    provider = _FixtureProvider()
    registry = make_bundle_registry({_WHEEL: _FixtureArrayBundle(_INSTRUMENT_ID)})

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        catalog_path=catalog_path,
        registry=registry,
        data_source=_zero_distribution_source(catalog_path, (_INSTRUMENT_ID,)),
        custom_data_providers={FixtureRecord: provider},
    )

    try:
        assert provider.requests == [
            (
                _INSTRUMENT_ID,
                pd.Timestamp("2020-01-01", tz="UTC"),
                pd.Timestamp("2020-01-05", tz="UTC"),
            )
        ]
    finally:
        result.engine.dispose()


def test_run_book_backtest_does_not_request_covered_custom_arrays(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_catalog(catalog_path, _INSTRUMENT_ID, [100.0, 101.0, 102.0, 103.0])
    ensure_arrays(
        {_INSTRUMENT_ID: ("FixtureValue",)},
        start=pd.Timestamp("2020-01-01", tz="UTC"),
        end=pd.Timestamp("2020-01-05", tz="UTC"),
        providers={FixtureRecord: _FixtureProvider()},
        catalog=Catalog.open(catalog_path),
    )
    registry = make_bundle_registry({_WHEEL: _FixtureArrayBundle(_INSTRUMENT_ID)})
    unused = _FixtureProvider()

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        catalog_path=catalog_path,
        registry=registry,
        data_source=_zero_distribution_source(catalog_path, (_INSTRUMENT_ID,)),
        custom_data_providers={FixtureRecord: unused},
    )

    try:
        assert unused.requests == []
    finally:
        result.engine.dispose()


def test_run_book_backtest_produces_whole_share_equity_orders(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    catalog = Catalog.open(catalog_path)
    store_instrument_fixtures(
        catalog,
        [
            Equity(
                instrument_id=_INSTRUMENT_ID,
                raw_symbol=Symbol(_INSTRUMENT_ID.symbol.value),
                currency=Currency.from_str("EUR"),
                price_precision=2,
                price_increment=Price.from_str("0.01"),
                lot_size=Quantity.from_int(1),
                ts_event=0,
                ts_init=0,
            )
        ],
    )
    _seed_catalog_bars_only(catalog_path, _INSTRUMENT_ID, [30.0] * 4)
    registry = make_bundle_registry({_WHEEL: _FixedWeightBundle(_INSTRUMENT_ID, 0.4)})

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        catalog_path=catalog_path,
        registry=registry,
        data_source=_zero_distribution_source(catalog_path, (_INSTRUMENT_ID,)),
        starting_cash=100.0,
    )
    try:
        fills = _closed_orders(result.engine)
        assert len(fills) == 1
        assert float(fills[0].quantity) == 1.0
    finally:
        result.engine.dispose()


def test_run_book_backtest_trades_a_declared_continuous_root(
    tmp_path, monkeypatch
) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    frame = _ohlcv_frame([100.0, 101.0, 102.0, 103.0])
    desk = _StaticContinuousDesk(frame)

    def build_static_desk(self: RebalanceStrategy) -> _StaticContinuousDesk:
        _ = self
        return desk

    monkeypatch.setattr(RebalanceStrategy, "_build_roll_desk", build_static_desk)
    registry = make_bundle_registry({_WHEEL: _ContinuousRootBundle()})

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        data_source=_ContinuousRootDataSource(frame),
        registry=registry,
    )
    engine = result.engine

    assert _closed_order_instrument_ids(engine) == {_ES}
    engine.dispose()


def test_run_book_backtest_preserves_attribution_across_a_roll(
    tmp_path, monkeypatch
) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    frame = _ohlcv_frame([100.0, 110.0, 120.0, 130.0, 140.0])
    desk = _RollingContinuousDesk(
        frame,
        front=_ES_OLD,
        roll_to=_ES_NEW,
        rebasing=spread_rebasing(50.0),
    )

    def build_rolling_desk(self: RebalanceStrategy) -> _RollingContinuousDesk:
        _ = self
        return desk

    monkeypatch.setattr(RebalanceStrategy, "_build_roll_desk", build_rolling_desk)
    registry = make_bundle_registry({_WHEEL: _ContinuousRootBundle()})

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-06",
        data_source=_RollingContinuousRootDataSource(frame),
        registry=registry,
    )
    engine = result.engine
    strategy = _strategy(engine)

    assert desk.rolled is True
    assert _closed_order_instrument_ids(engine) == {_ES_NEW}
    assert strategy.last_attribution[_TREND] == pytest.approx(0.0)
    engine.dispose()


def test_run_book_backtest_does_not_duplicate_cash_across_native_venues(
    tmp_path,
) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_catalog(catalog_path, _INSTRUMENT_ID, [100.0, 100.0, 100.0, 100.0])
    _seed_catalog(catalog_path, _SECOND_INSTRUMENT_ID, [100.0, 100.0, 100.0, 100.0])
    registry = make_bundle_registry({_WHEEL: _TwoVenueBundle()})

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        catalog_path=catalog_path,
        registry=registry,
        data_source=_zero_distribution_source(
            catalog_path,
            (_INSTRUMENT_ID, _SECOND_INSTRUMENT_ID),
        ),
    )
    engine = result.engine

    nav = NautilusBookState(
        portfolio=engine.portfolio,
        cache=engine.cache,
        base_currency=Currency.from_str("EUR"),
        covered_instrument_ids=frozenset((_INSTRUMENT_ID, _SECOND_INSTRUMENT_ID)),
    ).nav()
    assert len(_closed_orders(engine)) == 2
    assert nav == pytest.approx(1_000_000.0, abs=100.0)
    engine.dispose()


def test_run_book_backtest_reports_margin_interest_totals(tmp_path) -> None:
    financed, zero_rate = _run_margin_interest_fixture(tmp_path)

    try:
        assert financed.financing_totals["EUR"] == pytest.approx(
            _FINANCING_FIXTURE_EXPECTED_COST
        )
    finally:
        financed.engine.dispose()
        zero_rate.engine.dispose()


def test_run_book_backtest_reports_no_totals_for_zero_rate_book(tmp_path) -> None:
    financed, zero_rate = _run_margin_interest_fixture(tmp_path)

    try:
        assert zero_rate.financing_totals == {}
    finally:
        financed.engine.dispose()
        zero_rate.engine.dispose()


def test_run_book_backtest_equity_drag_matches_margin_interest_totals(tmp_path) -> None:
    financed, zero_rate = _run_margin_interest_fixture(tmp_path)

    financed_nav = _book_nav(financed.engine, (_INSTRUMENT_ID,))
    zero_rate_nav = _book_nav(zero_rate.engine, (_INSTRUMENT_ID,))
    try:
        assert zero_rate_nav - financed_nav == pytest.approx(
            _FINANCING_FIXTURE_EXPECTED_COST, abs=0.02
        )
    finally:
        financed.engine.dispose()
        zero_rate.engine.dispose()


def _run_margin_interest_fixture(tmp_path):
    book_path = tmp_path / "book.toml"
    book_path.write_text(_FINANCING_BOOK_TOML)
    zero_book_path = tmp_path / "zero_book.toml"
    zero_book_path.write_text(_ZERO_RATE_FINANCING_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_catalog(
        catalog_path,
        _INSTRUMENT_ID,
        [100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
    )
    registry = make_bundle_registry({_WHEEL: _FixedWeightBundle(_INSTRUMENT_ID, 1.5)})

    financed = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-07",
        catalog_path=catalog_path,
        registry=registry,
        data_source=_zero_distribution_source(catalog_path, (_INSTRUMENT_ID,)),
    )
    zero_rate = run_book_backtest(
        zero_book_path,
        start="2020-01-01",
        end="2020-01-07",
        catalog_path=catalog_path,
        registry=registry,
        data_source=_zero_distribution_source(catalog_path, (_INSTRUMENT_ID,)),
    )

    return financed, zero_rate


def test_run_book_backtest_reports_no_financing_for_cash_funded_book(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_FINANCING_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_catalog(catalog_path, _INSTRUMENT_ID, [100.0, 100.0, 100.0, 100.0])
    registry = make_bundle_registry({_WHEEL: _FixedWeightBundle(_INSTRUMENT_ID, 0.5)})

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        catalog_path=catalog_path,
        registry=registry,
        data_source=_zero_distribution_source(catalog_path, (_INSTRUMENT_ID,)),
    )

    try:
        assert result.financing_totals == {}
    finally:
        result.engine.dispose()


def test_catalog_backtest_data_source_loads_distribution_events(tmp_path) -> None:
    catalog_path = tmp_path / "catalog"
    _seed_catalog(catalog_path, _INSTRUMENT_ID, [100.0, 100.0, 100.0, 100.0])
    catalog = Catalog.open(catalog_path)
    data_port = CatalogBackedDataPort(
        catalog,
        custom_data_warmer=_adjusted_close_warmer(
            catalog,
            _AdjustedLastProvider(
                {
                    _INSTRUMENT_ID: _adjusted_last_for_distribution(
                        "2020-01-03", amount=0.75
                    )
                }
            ),
        ),
    )

    data = CatalogBacktestDataSource(port=data_port).load(
        (_INSTRUMENT_ID,),
        timeframe="1D",
        start="2020-01-01",
        end="2020-01-05",
    )

    assert [
        (item.instrument_id, item.ex_date, item.amount) for item in data.distributions
    ] == [(_INSTRUMENT_ID, pd.Timestamp("2020-01-03", tz="UTC"), pytest.approx(0.75))]


def test_catalog_backtest_data_source_preserves_native_bars(tmp_path) -> None:
    catalog_path = tmp_path / "catalog"
    catalog = Catalog.open(catalog_path)
    store_instrument_fixtures(catalog, [_equity(_INSTRUMENT_ID)])
    bar_type = raw_bar_type(_INSTRUMENT_ID, "1D")
    ts_event = pd.Timestamp("2020-01-01", tz="UTC").value
    price = Price.from_str("100.00")
    bar = Bar(
        bar_type,
        price,
        price,
        price,
        price,
        Quantity.from_int(1000),
        ts_event,
        ts_event + 37,
    )
    catalog.replace(
        CatalogKey.for_bar(bar_type),
        CatalogInterval(ts_event, pd.Timestamp("2020-01-02", tz="UTC").value),
        (bar,),
    )
    data_source = _zero_distribution_source(
        catalog_path,
        (_INSTRUMENT_ID,),
    )

    data = data_source.load(
        (_INSTRUMENT_ID,),
        timeframe="1D",
        start="2020-01-01",
        end="2020-01-02",
    )

    assert data.bars == {_INSTRUMENT_ID: (bar,)}


def test_run_book_backtest_books_distribution_cash(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_catalog(catalog_path, _INSTRUMENT_ID, [100.0, 100.0, 100.0, 100.0, 100.0])
    catalog = Catalog.open(catalog_path)
    data_port = CatalogBackedDataPort(
        catalog,
        custom_data_warmer=_adjusted_close_warmer(
            catalog,
            _AdjustedLastProvider(
                {
                    _INSTRUMENT_ID: _adjusted_last_for_distribution(
                        "2020-01-04", amount=1.0
                    )
                }
            ),
        ),
    )
    registry = make_bundle_registry({_WHEEL: _FixedWeightBundle(_INSTRUMENT_ID, 0.5)})

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-06",
        registry=registry,
        data_source=CatalogBacktestDataSource(port=data_port),
    )
    engine = result.engine

    nav = NautilusBookState(
        portfolio=engine.portfolio,
        cache=engine.cache,
        base_currency=Currency.from_str("EUR"),
        covered_instrument_ids=frozenset((_INSTRUMENT_ID,)),
    ).nav()
    assert nav == pytest.approx(1_005_000.0, abs=100.0)
    engine.dispose()


def test_run_book_backtest_fails_on_missing_catalog_instrument(tmp_path) -> None:
    # Bars are covered but the definition is not stored: the window read's
    # completeness guarantee fails with the port's authoring error (Data
    # ADR-0012) — never the environmental coverage-gap error.
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_catalog_bars_only(catalog_path, _INSTRUMENT_ID, [100.0, 100.0, 100.0, 100.0])
    registry = make_bundle_registry({_WHEEL: _FixedWeightBundle(_INSTRUMENT_ID, 0.5)})

    with pytest.raises(MissingCatalogDefinitionsError, match="VUSA.XLON"):
        run_book_backtest(
            book_path,
            start="2020-01-01",
            end="2020-01-05",
            catalog_path=catalog_path,
            registry=registry,
        )


class _EmptyDataSource:
    def load(
        self,
        instrument_ids: tuple[InstrumentId, ...],
        *,
        timeframe: str,
        start: str,
        end: str,
    ) -> BacktestMarketData:
        return BacktestMarketData(instruments={}, bar_windows={})


class _MissingBarWindowDataSource:
    def load(
        self,
        instrument_ids: tuple[InstrumentId, ...],
        *,
        timeframe: str,
        start: str,
        end: str,
    ) -> BacktestMarketData:
        return BacktestMarketData(
            instruments={_INSTRUMENT_ID: _equity(_INSTRUMENT_ID)},
            bar_windows={},
        )


def test_run_book_backtest_fails_when_data_source_omits_a_contract_instrument(
    tmp_path,
) -> None:
    # Sleeve-contract validation is Trader's own book-assembly concern, distinct
    # from catalog completeness: a declared id the loaded market data does not
    # carry still fails with Trader's own error before the engine starts.
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    registry = make_bundle_registry({_WHEEL: _FixedWeightBundle(_INSTRUMENT_ID, 0.5)})

    with pytest.raises(
        CatalogInstrumentError, match="did not return instrument definition"
    ):
        run_book_backtest(
            book_path,
            start="2020-01-01",
            end="2020-01-05",
            registry=registry,
            data_source=_EmptyDataSource(),
        )


def test_run_book_backtest_fails_preflight_without_native_bars(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    registry = make_bundle_registry({_WHEEL: _FixedWeightBundle(_INSTRUMENT_ID, 0.5)})

    with pytest.raises(ContractDataError, match="did not return raw bars"):
        run_book_backtest(
            book_path,
            start="2020-01-01",
            end="2020-01-05",
            registry=registry,
            data_source=_MissingBarWindowDataSource(),
        )


def _seed_catalog(
    catalog_path,
    instrument_id: InstrumentId,
    closes: list[float],
) -> None:
    store_instrument_fixtures(Catalog.open(catalog_path), [_equity(instrument_id)])
    _seed_catalog_bars_only(catalog_path, instrument_id, closes)


def _seed_catalog_bars_only(
    catalog_path,
    instrument_id: InstrumentId,
    closes: list[float],
) -> None:
    catalog = Catalog.open(catalog_path)
    bars = [
        _bar(raw_bar_type(instrument_id, "1D"), day, close)
        for day, close in zip(
            pd.date_range("2020-01-01", periods=len(closes), freq="D"),
            closes,
            strict=True,
        )
    ]
    interval = CatalogInterval(
        pd.Timestamp("2020-01-01", tz="UTC").value,
        pd.Timestamp("2020-01-01", tz="UTC").value + len(closes) * 86_400_000_000_000,
    )
    key = CatalogKey.for_bar(raw_bar_type(instrument_id, "1D"))
    catalog.replace(key, interval, tuple(bars))


def _adjusted_last_for_distribution(ex_date: str, *, amount: float) -> pd.Series:
    dates = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
    values = pd.Series([100.0] * len(dates), index=dates)
    values.loc[pd.Timestamp(ex_date, tz="UTC")] = 100.0 / (1.0 - amount / 100.0)
    return values


def _zero_distribution_source(
    catalog_path,
    instrument_ids: tuple[InstrumentId, ...],
) -> CatalogBacktestDataSource:
    adjusted_last = {
        instrument_id: pd.Series(
            [100.0] * 10,
            index=pd.date_range("2020-01-01", periods=10, freq="D", tz="UTC"),
        )
        for instrument_id in instrument_ids
    }
    catalog = Catalog.open(catalog_path)
    return CatalogBacktestDataSource(
        port=CatalogBackedDataPort(
            catalog,
            custom_data_warmer=_adjusted_close_warmer(
                catalog,
                _AdjustedLastProvider(adjusted_last),
            ),
        )
    )


def _book_nav(engine, instrument_ids: tuple[InstrumentId, ...]) -> float:
    return NautilusBookState(
        portfolio=engine.portfolio,
        cache=engine.cache,
        base_currency=Currency.from_str("EUR"),
        covered_instrument_ids=frozenset(instrument_ids),
    ).nav()


def _ohlcv_frame(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": [1_000.0] * len(closes),
        },
        index=pd.date_range("2020-01-01", periods=len(closes), freq="D"),
    )


def _equity(instrument_id: InstrumentId) -> Equity:
    return Equity(
        instrument_id=instrument_id,
        raw_symbol=Symbol(instrument_id.symbol.value),
        currency=Currency.from_str("EUR"),
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def _bar(bar_type: BarType, day: pd.Timestamp, close: float) -> Bar:
    ts_event = pd.Timestamp(day, tz="UTC").value
    price = Price.from_str(f"{close:.2f}")
    return Bar(
        bar_type,
        price,
        price,
        price,
        price,
        Quantity.from_int(1000),
        ts_event,
        ts_event,
    )


def _bar_with_init_delay(bar_type: BarType, day: str, close: float) -> Bar:
    ts_event = pd.Timestamp(day, tz="UTC").value
    price = Price.from_str(f"{close:.2f}")
    return Bar(
        bar_type,
        price,
        price,
        price,
        price,
        Quantity.from_int(1000),
        ts_event,
        ts_event + 37,
    )


def _closed_orders(engine: Any) -> list[Any]:
    return [order for order in engine.cache.orders() if order.is_closed]


def _closed_order_instrument_ids(engine: Any) -> set[InstrumentId]:
    return {order.instrument_id for order in _closed_orders(engine)}


def _strategy(engine) -> RebalanceStrategy:
    strategies = [
        strategy
        for strategy in engine.trader.strategies()
        if isinstance(strategy, RebalanceStrategy)
    ]
    assert len(strategies) == 1
    return strategies[0]
