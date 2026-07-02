"""End-to-end catalog-backed Trader backtest runner tests.

The runner composes the forward path: Book Config -> Execution Bundle contracts
with native ``InstrumentId`` values -> Nautilus ``ParquetDataCatalog`` -> real
``BacktestEngine`` -> live ``RebalanceStrategy``.
"""

from __future__ import annotations

import pandas as pd
import pytest
from aegis_data.distributions import Distribution, write_distribution_data
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from aegis_data.catalog import CatalogCoverageGapError, raw_bar_type
from aegis_data.rebasing import Rebasing, spread_rebasing
from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
)

from aegis_trader.backtest import (
    BacktestMarketData,
    CatalogBacktestDataSource,
    CatalogInstrumentError,
    run_book_backtest,
)
from aegis_trader.bundles.stub import StubBundleRegistry
from aegis_trader.domain.roll import RollEvent, SubscribeBars, UnsubscribeBars
from aegis_trader.domain.types import SleeveName
from aegis_trader.portfolio import NautilusBookState
from aegis_trader.trader.strategy import RebalanceStrategy

_INSTRUMENT_ID = InstrumentId.from_str("VUSA.XLON")
_SECOND_INSTRUMENT_ID = InstrumentId.from_str("AAPL.XNAS")
_ES = InstrumentId.from_str("ES.XCME")
_ES_OLD = InstrumentId.from_str("ESM4.XCME")
_ES_NEW = InstrumentId.from_str("ESU4.XCME")
_WHEEL = "synth-trend.whl"
_TREND = SleeveName("trend")

_BOOK_TOML = f"""
base_currency = "EUR"

[[sleeves]]
name = "trend"
wheel_filename = "{_WHEEL}"
risk_share = 1.0
group = "Floor"
"""


class _FixedWeightBundle(ExecutionBundle):
    """Synthetic bundle that returns one fixed target weight."""

    def __init__(self, instrument_id: InstrumentId, weight: float) -> None:
        self._instrument_id = instrument_id
        self._weight = weight
        contract = DataContract(
            instrument_ids=(instrument_id,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            lookback_bars=1,
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
            gross_cap=1.0,
            net_cap=None,
            direction="longonly",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(self, prices: MarketDataBundle) -> pd.DataFrame:
        close = prices.array("Close")
        weights = pd.DataFrame(
            {self._instrument_id: [self._weight] * len(close)},
            index=close.index,
        )
        weights.columns.name = "instrument_id"
        return weights


class _TwoVenueBundle(ExecutionBundle):
    """Synthetic bundle that targets instruments on two native venues."""

    def __init__(self) -> None:
        self._instrument_ids = (_INSTRUMENT_ID, _SECOND_INSTRUMENT_ID)
        contract = DataContract(
            instrument_ids=self._instrument_ids,
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            lookback_bars=1,
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
                instrument_id: DriftBand.symmetric(0.0) for instrument_id in self._instrument_ids
            },
            gross_cap=1.0,
            net_cap=None,
            direction="longonly",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(self, prices: MarketDataBundle) -> pd.DataFrame:
        close = prices.array("Close")
        weights = pd.DataFrame(
            {
                _INSTRUMENT_ID: [0.25] * len(close),
                _SECOND_INSTRUMENT_ID: [0.25] * len(close),
            },
            index=close.index,
        )
        weights.columns.name = "instrument_id"
        return weights


class _ContinuousRootBundle(ExecutionBundle):
    """Synthetic bundle that targets the declared continuous-root id."""

    def __init__(self) -> None:
        contract = DataContract(
            instrument_ids=(_ES,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            lookback_bars=1,
            futures=("ES",),
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
            gross_cap=1.0,
            net_cap=None,
            direction="longonly",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(self, prices: MarketDataBundle) -> pd.DataFrame:
        close = prices.array("Close")
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
            ohlcv={_ES: self._frame},
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
            ohlcv={
                _ES: self._frame,
                _ES_OLD: self._frame.iloc[:1],
                _ES_NEW: self._frame.iloc[1:],
            },
        )


def test_run_book_backtest_runs_live_strategy_from_catalog(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_catalog(catalog_path, _INSTRUMENT_ID, [100.0, 101.0, 102.0, 103.0])
    registry = StubBundleRegistry({_WHEEL: _FixedWeightBundle(_INSTRUMENT_ID, 0.5)})

    engine = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        catalog_path=catalog_path,
        registry=registry,
    )

    fills = [order for order in engine.cache.orders() if order.is_closed]
    assert len(fills) == 1
    assert fills[0].instrument_id == _INSTRUMENT_ID
    engine.dispose()


def test_run_book_backtest_trades_a_declared_continuous_root(
    tmp_path, monkeypatch
) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    frame = _ohlcv_frame([100.0, 101.0, 102.0, 103.0])
    desk = _StaticContinuousDesk(frame)

    def build_static_desk(
        self: RebalanceStrategy, _book_timeframe: str, *, history_start: object
    ) -> _StaticContinuousDesk:
        _ = (self, history_start)
        return desk

    monkeypatch.setattr(RebalanceStrategy, "_build_roll_desk", build_static_desk)
    registry = StubBundleRegistry({_WHEEL: _ContinuousRootBundle()})

    engine = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        data_source=_ContinuousRootDataSource(frame),
        registry=registry,
    )

    fills = [order for order in engine.cache.orders() if order.is_closed]
    assert fills
    assert {order.instrument_id for order in fills} == {_ES}
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

    def build_rolling_desk(
        self: RebalanceStrategy, _book_timeframe: str, *, history_start: object
    ) -> _RollingContinuousDesk:
        _ = (self, history_start)
        return desk

    monkeypatch.setattr(RebalanceStrategy, "_build_roll_desk", build_rolling_desk)
    registry = StubBundleRegistry({_WHEEL: _ContinuousRootBundle()})

    engine = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-06",
        data_source=_RollingContinuousRootDataSource(frame),
        registry=registry,
    )
    strategy = _strategy(engine)
    fills = [order for order in engine.cache.orders() if order.is_closed]

    assert desk.rolled is True
    assert fills
    assert {order.instrument_id for order in fills} == {_ES_NEW}
    assert strategy.last_attribution[_TREND] == pytest.approx(0.0)
    engine.dispose()


def test_run_book_backtest_does_not_duplicate_cash_across_native_venues(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_catalog(catalog_path, _INSTRUMENT_ID, [100.0, 100.0, 100.0, 100.0])
    _seed_catalog(catalog_path, _SECOND_INSTRUMENT_ID, [100.0, 100.0, 100.0, 100.0])
    registry = StubBundleRegistry({_WHEEL: _TwoVenueBundle()})

    engine = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        catalog_path=catalog_path,
        registry=registry,
    )

    fills = [order for order in engine.cache.orders() if order.is_closed]
    nav = NautilusBookState(
        portfolio=engine.portfolio,
        cache=engine.cache,
        base_currency=Currency.from_str("EUR"),
        covered_instrument_ids=frozenset((_INSTRUMENT_ID, _SECOND_INSTRUMENT_ID)),
    ).nav()
    assert len(fills) == 2
    assert nav == pytest.approx(1_000_000.0, abs=100.0)
    engine.dispose()


def test_catalog_backtest_data_source_loads_distribution_events(tmp_path) -> None:
    catalog_path = tmp_path / "catalog"
    _seed_catalog(catalog_path, _INSTRUMENT_ID, [100.0, 100.0, 100.0, 100.0])
    distribution = Distribution.from_ex_date(
        _INSTRUMENT_ID,
        "2020-01-03",
        amount=0.75,
        currency="EUR",
    )
    write_distribution_data(ParquetDataCatalog(catalog_path), [distribution])

    data = CatalogBacktestDataSource(catalog_path=catalog_path).load(
        (_INSTRUMENT_ID,),
        timeframe="1D",
        start="2020-01-01",
        end="2020-01-05",
    )

    assert [(item.instrument_id, item.ex_date, item.amount) for item in data.distributions] == [
        (_INSTRUMENT_ID, distribution.ex_date, pytest.approx(0.75))
    ]


def test_run_book_backtest_books_distribution_cash(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_catalog(catalog_path, _INSTRUMENT_ID, [100.0, 100.0, 100.0, 100.0, 100.0])
    distribution = Distribution.from_ex_date(
        _INSTRUMENT_ID,
        "2020-01-04",
        amount=1.0,
        currency="EUR",
    )
    write_distribution_data(ParquetDataCatalog(catalog_path), [distribution])
    registry = StubBundleRegistry({_WHEEL: _FixedWeightBundle(_INSTRUMENT_ID, 0.5)})

    engine = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-06",
        catalog_path=catalog_path,
        registry=registry,
    )

    nav = NautilusBookState(
        portfolio=engine.portfolio,
        cache=engine.cache,
        base_currency=Currency.from_str("EUR"),
        covered_instrument_ids=frozenset((_INSTRUMENT_ID,)),
    ).nav()
    assert nav == pytest.approx(1_005_000.0, abs=100.0)
    engine.dispose()


def test_run_book_backtest_fails_on_missing_catalog_instrument(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    catalog_path.mkdir()
    registry = StubBundleRegistry({_WHEEL: _FixedWeightBundle(_INSTRUMENT_ID, 0.5)})

    with pytest.raises(CatalogInstrumentError, match="VUSA.XLON"):
        run_book_backtest(
            book_path,
            start="2020-01-01",
            end="2020-01-05",
            catalog_path=catalog_path,
            registry=registry,
        )


def test_run_book_backtest_fails_on_catalog_coverage_gap(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_catalog(catalog_path, _INSTRUMENT_ID, [100.0])
    registry = StubBundleRegistry({_WHEEL: _FixedWeightBundle(_INSTRUMENT_ID, 0.5)})

    with pytest.raises(CatalogCoverageGapError, match="VUSA.XLON"):
        run_book_backtest(
            book_path,
            start="2020-01-01",
            end="2020-01-05",
            catalog_path=catalog_path,
            registry=registry,
        )


def _seed_catalog(
    catalog_path,
    instrument_id: InstrumentId,
    closes: list[float],
) -> None:
    catalog = ParquetDataCatalog(catalog_path)
    instrument = _equity(instrument_id)
    catalog.write_data([instrument])
    bars = [
        _bar(raw_bar_type(instrument_id, "1D"), day, close)
        for day, close in zip(pd.date_range("2020-01-01", periods=len(closes), freq="D"), closes, strict=True)
    ]
    catalog.write_data(
        bars,
        start=pd.Timestamp("2020-01-01", tz="UTC").value,
        end=pd.Timestamp("2020-01-01", tz="UTC").value
        + len(closes) * 86_400_000_000_000,
    )


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


def _strategy(engine) -> RebalanceStrategy:
    strategies = [
        strategy
        for strategy in engine.trader.strategies()
        if isinstance(strategy, RebalanceStrategy)
    ]
    assert len(strategies) == 1
    return strategies[0]
