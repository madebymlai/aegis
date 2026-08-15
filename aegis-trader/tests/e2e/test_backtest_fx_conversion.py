"""E2E: a USD-quoted sleeve must trade in a EUR-base book (aegis-rd-reyj).

The commingled-book failure mode: bundle contracts that omit the FX conversion
legs leave the backtest with no EUR/USD data, so every USD-quoted delta is
silently dropped in sizing (no fx rate) and the sleeve never trades.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency, Price, Quantity

from aegis_data.catalog import CatalogBackedDataPort, raw_bar_type
from aegis_data.raw_bars import RawBars
from aegis_data.storage import Catalog, CatalogInterval
from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
    MissingIndexPolicy,
)

from aegis_runtime.domain.currency import CurrencyConversion

from aegis_data.bar_type import external_bar_type
from aegis_data.marking import DeclaredMarkingResolver, MarkMode
from aegis_data.ibkr import historic_catalog_client_factory
from aegis_data.custom_data import CustomDataWarmer
from aegis_trader.backtest import CatalogBacktestDataSource, run_book_backtest
from aegis_trader.bundles.stub import StubBundleRegistry
from aegis_trader.data import build_currency_pair
from nautilus_trader.model.data import Bar

_USD_INSTRUMENT_ID = InstrumentId.from_str("AAPL.XNAS")
_EURUSD_ID = InstrumentId.from_str("EUR/USD.IDEALPRO")
_WHEEL = "synth-usd-floor.whl"

_BOOK_TOML = f"""
base_currency = "EUR"

[[sleeves]]
name = "usd_floor"
wheel_filename = "{_WHEEL}"
risk_share = 1.0
group = "Floor"
"""


class _UsdFixedWeightBundle(ExecutionBundle):
    """Synthetic bundle holding one USD-quoted instrument at a fixed weight."""

    def __init__(self, weight: float) -> None:
        self._weight = weight
        contract = DataContract(
            instrument_ids=(_USD_INSTRUMENT_ID,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
            exchange=(_EURUSD_ID,),
            # As a real export records it: the tradeable explicit, the
            # exchange conversion leg bar-marked MID by its section.
            mark_modes={_USD_INSTRUMENT_ID: "LAST", _EURUSD_ID: "MID"},
        )
        manifest = BundleManifest(
            run_id="fx-conversion-synth",
            role="synth",
            candidate_key="fx-conversion-synth-key",
            component_source_hashes={},
            instrument_ids=(_USD_INSTRUMENT_ID,),
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
            instrument_bands={_USD_INSTRUMENT_ID: DriftBand.symmetric(0.02)},
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
            {_USD_INSTRUMENT_ID: [self._weight] * len(close)},
            index=close.index,
        )
        weights.columns.name = "instrument_id"
        return weights


def test_usd_quoted_sleeve_trades_in_eur_base_book(tmp_path) -> None:
    book_path = tmp_path / "book.toml"
    book_path.write_text(_BOOK_TOML)
    catalog_path = tmp_path / "catalog"
    _seed_usd_catalog(catalog_path, closes=[100.0, 101.0, 102.0, 103.0])
    _seed_fx_catalog(catalog_path, rates=[1.10, 1.10, 1.10, 1.10])
    registry = StubBundleRegistry({_WHEEL: _UsdFixedWeightBundle(0.5)})

    result = run_book_backtest(
        book_path,
        start="2020-01-01",
        end="2020-01-05",
        catalog_path=catalog_path,
        registry=registry,
        data_source=_zero_distribution_source(catalog_path),
    )
    engine = result.engine

    fills = [order for order in engine.cache.orders() if order.is_closed]
    assert [order.instrument_id for order in fills] == [_USD_INSTRUMENT_ID]
    engine.dispose()


def _seed_usd_catalog(catalog_path, closes: list[float]) -> None:
    catalog = Catalog.open(catalog_path)
    instrument = Equity(
        instrument_id=_USD_INSTRUMENT_ID,
        raw_symbol=Symbol(_USD_INSTRUMENT_ID.symbol.value),
        currency=Currency.from_str("USD"),
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )
    catalog.store_definitions([instrument])
    start_ns = pd.Timestamp("2020-01-01", tz="UTC").value
    end_ns = start_ns + len(closes) * 86_400_000_000_000
    bar_type = raw_bar_type(_USD_INSTRUMENT_ID, "1D")
    RawBars(catalog).record_verified(
        bar_type,
        CatalogInterval(start_ns, end_ns),
        tuple(
            _bar(raw_bar_type(_USD_INSTRUMENT_ID, "1D"), day, close)
            for day, close in zip(
                pd.date_range("2020-01-01", periods=len(closes), freq="D"),
                closes,
                strict=True,
            )
        ),
    )


def _seed_fx_catalog(catalog_path, rates: list[float]) -> None:
    catalog = Catalog.open(catalog_path)
    pair = build_currency_pair("EUR", "USD", "IDEALPRO")
    catalog.store_definitions([pair])
    start_ns = pd.Timestamp("2020-01-01", tz="UTC").value
    end_ns = start_ns + len(rates) * 86_400_000_000_000
    bar_type = external_bar_type(_EURUSD_ID, "1D", "MID")
    RawBars(catalog).record_verified(
        bar_type,
        CatalogInterval(start_ns, end_ns),
        tuple(
            _bar(bar_type, day, rate, precision=5)
            for day, rate in zip(
                pd.date_range("2020-01-01", periods=len(rates), freq="D"),
                rates,
                strict=True,
            )
        ),
    )


def _bar(
    bar_type: BarType, day: pd.Timestamp, close: float, *, precision: int = 2
) -> Bar:
    ts_event = pd.Timestamp(day, tz="UTC").value
    price = Price(close, precision)
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


class _AdjustedLastProvider:
    def __init__(self, adjusted_last: dict[InstrumentId, pd.Series]) -> None:
        self.adjusted_last = adjusted_last

    def request_adjusted_last(self, **kwargs: Any) -> pd.Series:
        return self.adjusted_last[kwargs["instrument_id"]]


def _zero_distribution_source(catalog_path) -> CatalogBacktestDataSource:
    # Distribution coverage exists only for the tradeable: an FX conversion
    # pair pays no distributions and must never be part of the distribution
    # request (the real verified store has no coverage record for it).
    dates = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
    adjusted_last = {
        _USD_INSTRUMENT_ID: pd.Series([100.0] * len(dates), index=dates),
    }
    catalog = Catalog.open(catalog_path)
    return CatalogBacktestDataSource(
        port=CatalogBackedDataPort(
            catalog,
            custom_data_warmer=CustomDataWarmer(
                catalog,
                historic_catalog_client_factory(
                    _AdjustedLastProvider(adjusted_last)
                ),
            ),
            # The port reads what the bundle records: the FX conversion leg is
            # bar-marked MID by declaration, never by symbol shape.
            resolver=DeclaredMarkingResolver(declared={_EURUSD_ID: MarkMode.MID}),
        )
    )
