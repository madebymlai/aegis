"""End-to-end catalog-backed Trader backtest runner tests.

The runner composes the forward path: Book Config -> Execution Bundle contracts
with native ``InstrumentId`` values -> Nautilus ``ParquetDataCatalog`` -> real
``BacktestEngine`` -> live ``RebalanceStrategy``.
"""

from __future__ import annotations

import pandas as pd
import pytest
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from aegis_data.catalog import CatalogCoverageGapError, raw_bar_type
from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
)

from aegis_trader.backtest import CatalogInstrumentError, run_book_backtest
from aegis_trader.bundles.stub import StubBundleRegistry
from aegis_trader.portfolio import NautilusBookState

_INSTRUMENT_ID = InstrumentId.from_str("VUSA.XLON")
_SECOND_INSTRUMENT_ID = InstrumentId.from_str("AAPL.NASDAQ")
_WHEEL = "synth-trend.whl"

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


def _bar(bar_type: str, day: pd.Timestamp, close: float) -> Bar:
    ts_event = pd.Timestamp(day, tz="UTC").value
    price = Price.from_str(f"{close:.2f}")
    return Bar(
        BarType.from_str(bar_type),
        price,
        price,
        price,
        price,
        Quantity.from_int(1000),
        ts_event,
        ts_event,
    )
