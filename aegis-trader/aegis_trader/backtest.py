"""Catalog-backed Trader backtest entrypoints.

The runner is intentionally forward-only: Execution Bundles declare native
Nautilus ``InstrumentId`` values, raw bars come from the Nautilus
``ParquetDataCatalog`` through the Aegis Data catalog port, and the same
``RebalanceStrategy`` used by paper/live is run inside Nautilus'
``BacktestEngine``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Currency, Money

from aegis_data.catalog import (
    CatalogBackedDataPort,
    NautilusDataProviderPort,
    RawBarRequest,
    parquet_data_catalog,
)
from aegis_runtime import ExecutionBundle

from aegis_trader.bundles.port import BundleRegistryPort
from aegis_trader.bundles.registry import EntryPointBundleRegistry
from aegis_trader.config import load_book_config
from aegis_trader.data import bar_type, resolve_book_timeframe, wrangle_bars
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.types import SleeveName
from aegis_trader.portfolio.performance import (
    BookEquityRecorder,
    BookEquityRecorderConfig,
    return_stats,
)
from aegis_trader.trader.costs import build_simulated_cost_models
from aegis_trader.trader.financing import build_financing_modules
from aegis_trader.trader.modes import (
    DEFAULT_BACKTEST_BAR_CAPACITY,
    build_backtest_engine_config,
)
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

_PRICE_COLS = ("Open", "High", "Low", "Close")
_OHLCV_ARRAYS = (*_PRICE_COLS, "Volume")

_SleeveBundles = tuple[tuple[SleeveName, ExecutionBundle], ...]


class CatalogInstrumentError(ValueError):
    """Raised when the catalog does not hold a requested instrument definition."""


class ContractDataError(ValueError):
    """Catalog bars do not satisfy an Execution Bundle's ``DataContract``."""

    def __init__(self, sleeve: str, instrument_id: InstrumentId, detail: str) -> None:
        self.sleeve = sleeve
        self.instrument_id = instrument_id
        super().__init__(f"sleeve {sleeve!r} ({instrument_id.value}): {detail}")


@dataclass(frozen=True)
class BacktestMarketData:
    """Catalog material the runner feeds into Nautilus' ``BacktestEngine``."""

    instruments: Mapping[InstrumentId, Instrument]
    ohlcv: Mapping[InstrumentId, pd.DataFrame]


class BacktestDataSource(Protocol):
    """Loads native instruments and raw OHLCV frames for a backtest window."""

    def load(
        self,
        instrument_ids: tuple[InstrumentId, ...],
        *,
        timeframe: str,
        start: str,
        end: str,
    ) -> BacktestMarketData:
        """Return catalog instruments and OHLCV frames for *instrument_ids*."""
        ...


@dataclass(frozen=True)
class CatalogBacktestDataSource:
    """Backtest data source backed by Aegis Data's Nautilus catalog port."""

    catalog_path: Path | None = None
    provider: NautilusDataProviderPort | None = None

    def load(
        self,
        instrument_ids: tuple[InstrumentId, ...],
        *,
        timeframe: str,
        start: str,
        end: str,
    ) -> BacktestMarketData:
        catalog = parquet_data_catalog(self.catalog_path)
        instruments = _catalog_instruments(catalog, instrument_ids)
        frames = CatalogBackedDataPort(catalog, provider=self.provider).load_raw_bars(
            RawBarRequest(
                instrument_ids=instrument_ids,
                start=start,
                end=end,
                timeframe=timeframe,
            )
        )
        return BacktestMarketData(instruments=instruments, ohlcv=frames)


def run_book_backtest(
    book_path: str | Path,
    *,
    start: str,
    end: str,
    catalog_path: Path | None = None,
    registry: BundleRegistryPort | None = None,
    data_source: BacktestDataSource | None = None,
    provider: NautilusDataProviderPort | None = None,
    starting_cash: float = 1_000_000.0,
    trader_id: str = "BACKTEST-001",
) -> BacktestEngine:
    """Build and run a commingled-book backtest from the Nautilus catalog.

    There is no Historical Store, symbol map, or provider-specific identity on
    this path.  The catalog must hold instrument definitions keyed by the same
    native ``InstrumentId`` values declared by the Execution Bundles.  Raw bars
    are read through ``CatalogBackedDataPort``, so catalog coverage gaps fail
    before the Nautilus engine starts.
    """
    book = load_book_config(book_path)
    registry = registry if registry is not None else EntryPointBundleRegistry()
    sleeves = _load_sleeves(book, registry)
    book_timeframe = resolve_book_timeframe(
        bundle.contract.timeframe for _name, bundle in sleeves
    )
    instrument_ids = _contract_instrument_ids(sleeves)
    source = data_source or CatalogBacktestDataSource(
        catalog_path=catalog_path,
        provider=provider,
    )
    market_data = source.load(
        instrument_ids,
        timeframe=book_timeframe,
        start=start,
        end=end,
    )
    _validate_market_data(sleeves, market_data)

    engine = BacktestEngine(
        build_backtest_engine_config(
            trader_id=trader_id,
            bar_capacity=_cache_bar_capacity(sleeves),
        )
    )
    _add_venues(
        engine,
        book=book,
        instruments=tuple(market_data.instruments.values()),
        sleeves=sleeves,
        starting_cash=starting_cash,
    )
    _add_instruments_and_bars(
        engine,
        market_data=market_data,
        timeframe=book_timeframe,
    )
    engine.sort_data()
    _add_equity_recorder(engine, book=book, instrument_ids=instrument_ids, timeframe=book_timeframe)
    _add_strategy(engine, book=book, sleeves=sleeves)

    engine.run()
    return engine


def book_return_stats(engine: BacktestEngine) -> dict[str, float]:
    """Base-currency return statistics for a finished book backtest."""
    for actor in engine.trader.actors():
        if isinstance(actor, BookEquityRecorder):
            return return_stats(actor.equity_curve)
    return {}


def _load_sleeves(book: BookConfig, registry: BundleRegistryPort) -> _SleeveBundles:
    return tuple((s.name, registry.load(s.wheel_filename)) for s in book.sleeves)


def _contract_instrument_ids(sleeves: _SleeveBundles) -> tuple[InstrumentId, ...]:
    unique: dict[str, InstrumentId] = {}
    for _name, bundle in sleeves:
        for instrument_id in bundle.contract.instrument_ids:
            unique.setdefault(instrument_id.value, instrument_id)
    return tuple(sorted(unique.values(), key=lambda instrument_id: instrument_id.value))


def _catalog_instruments(
    catalog: object,
    instrument_ids: tuple[InstrumentId, ...],
) -> dict[InstrumentId, Instrument]:
    loaded = {
        instrument.id.value: instrument
        for instrument in catalog.instruments(
            instrument_ids=[instrument_id.value for instrument_id in instrument_ids]
        )
    }
    missing = [
        instrument_id.value
        for instrument_id in instrument_ids
        if instrument_id.value not in loaded
    ]
    if missing:
        raise CatalogInstrumentError(
            "catalog is missing instrument definitions for native "
            f"InstrumentIds: {missing}"
        )
    return {instrument_id: loaded[instrument_id.value] for instrument_id in instrument_ids}


def _validate_market_data(sleeves: _SleeveBundles, market_data: BacktestMarketData) -> None:
    for sleeve_name, bundle in sleeves:
        contract = bundle.contract
        for instrument_id in contract.instrument_ids:
            if instrument_id not in market_data.instruments:
                raise CatalogInstrumentError(
                    "data source did not return instrument definition for "
                    f"{instrument_id.value}"
                )
            frame = market_data.ohlcv.get(instrument_id)
            if frame is None:
                raise ContractDataError(
                    sleeve_name.value,
                    instrument_id,
                    "data source did not return raw bars",
                )
            _validate_contract_frame(
                frame,
                sleeve=sleeve_name.value,
                instrument_id=instrument_id,
                required_arrays=contract.required_arrays,
                min_rows=contract.lookback_bars + 1,
            )


def _validate_contract_frame(
    frame: pd.DataFrame,
    *,
    sleeve: str,
    instrument_id: InstrumentId,
    required_arrays: tuple[str, ...],
    min_rows: int,
) -> None:
    columns = {str(column).lower() for column in frame.columns}
    required = tuple(dict.fromkeys((*_OHLCV_ARRAYS, *required_arrays)))
    missing = [name for name in required if name.lower() not in columns]
    if missing:
        raise ContractDataError(
            sleeve,
            instrument_id,
            f"missing required arrays {missing}",
        )
    if len(frame.dropna()) < min_rows:
        raise ContractDataError(
            sleeve,
            instrument_id,
            f"{len(frame.dropna())} rows read, need at least {min_rows} (lookback + 1)",
        )


def _cache_bar_capacity(sleeves: _SleeveBundles) -> int:
    required = max(bundle.contract.lookback_bars for _name, bundle in sleeves) + 1
    return max(DEFAULT_BACKTEST_BAR_CAPACITY, required)


def _add_venues(
    engine: BacktestEngine,
    *,
    book: BookConfig,
    instruments: Sequence[Instrument],
    sleeves: _SleeveBundles,
    starting_cash: float,
) -> None:
    account_currencies = _account_currencies(book, instruments)
    native_venues = _instrument_venues(instruments)
    account_type = (
        AccountType.MARGIN
        if len(native_venues) > 1 or _requires_margin_account(sleeves)
        else AccountType.CASH
    )
    starting_balances, balance_currencies = _starting_balances(
        book,
        account_currencies,
        starting_cash,
    )
    for index, native_venue in enumerate(native_venues):
        cost_models = build_simulated_cost_models(book)
        financing_modules = build_financing_modules(book.costs)
        engine.add_venue(
            native_venue,
            oms_type=OmsType.NETTING,
            account_type=account_type,
            base_currency=None,
            starting_balances=starting_balances
            if index == 0
            else _zero_balances(balance_currencies),
            modules=financing_modules,
            fill_model=cost_models.fill_model,
            fee_model=cost_models.fee_model,
            book_type=BookType.L1_MBP,
            allow_cash_borrowing=account_type == AccountType.MARGIN
            or len(balance_currencies) > 1,
        )


def _add_instruments_and_bars(
    engine: BacktestEngine,
    *,
    market_data: BacktestMarketData,
    timeframe: str,
) -> None:
    for instrument_id, instrument in market_data.instruments.items():
        engine.add_instrument(instrument)
        bars = _wrangle_external_bars(instrument, market_data.ohlcv[instrument_id], timeframe)
        engine.add_data(bars, sort=False)


def _wrangle_external_bars(
    instrument: Instrument,
    ohlcv: pd.DataFrame,
    timeframe: str,
) -> list[Bar]:
    frame = _normalize_ohlcv(ohlcv)
    return wrangle_bars(instrument, frame, timeframe)


def _normalize_ohlcv(ohlcv: pd.DataFrame) -> pd.DataFrame:
    columns = {str(column).lower(): column for column in ohlcv.columns}
    normalized = pd.DataFrame(index=ohlcv.index)
    for name in _OHLCV_ARRAYS:
        normalized[name.lower()] = ohlcv[columns[name.lower()]]
    normalized = normalized.dropna().copy()
    normalized["high"] = normalized[[col.lower() for col in _PRICE_COLS]].max(axis=1)
    normalized["low"] = normalized[[col.lower() for col in _PRICE_COLS]].min(axis=1)
    return normalized


def _add_equity_recorder(
    engine: BacktestEngine,
    *,
    book: BookConfig,
    instrument_ids: tuple[InstrumentId, ...],
    timeframe: str,
) -> None:
    engine.add_actor(
        BookEquityRecorder(
            BookEquityRecorderConfig(
                base_currency=book.base_currency,
                bar_types=tuple(
                    str(bar_type(instrument_id.value, timeframe))
                    for instrument_id in instrument_ids
                ),
            )
        )
    )


def _add_strategy(
    engine: BacktestEngine,
    *,
    book: BookConfig,
    sleeves: _SleeveBundles,
) -> None:
    strategy = RebalanceStrategy(
        RebalanceStrategyConfig(
            book=book,
            fill_time_in_force=None,
            warmup_cache_on_start=False,
        )
    )
    for name, bundle in sleeves:
        strategy.register_sleeve(name, bundle)
    engine.add_strategy(strategy)


def _starting_balances(
    book: BookConfig,
    account_currencies: tuple[str, ...],
    starting_cash: float,
) -> tuple[list[Money], tuple[str, ...]]:
    declared = dict(book.starting_balances)
    if declared:
        currencies = tuple(sorted(set(account_currencies) | set(declared)))
        balances = [
            Money(declared.get(currency, 0.0), Currency.from_str(currency))
            for currency in currencies
        ]
    else:
        currencies = account_currencies
        balances = [
            Money(
                starting_cash if currency == book.base_currency else 0.0,
                Currency.from_str(currency),
            )
            for currency in currencies
        ]
    return balances, currencies


def _zero_balances(currencies: tuple[str, ...]) -> list[Money]:
    return [Money(0.0, Currency.from_str(currency)) for currency in currencies]


def _requires_margin_account(sleeves: _SleeveBundles) -> bool:
    return any(_bundle_direction(bundle) in {"both", "shortonly"} for _name, bundle in sleeves)


def _bundle_direction(bundle: object) -> str:
    plan = getattr(bundle, "plan", None) or getattr(bundle, "_plan", None)
    return str(getattr(plan, "direction", "longonly"))


def _account_currencies(
    book: BookConfig,
    instruments: Sequence[Instrument],
) -> tuple[str, ...]:
    currencies = {book.base_currency}
    for instrument in instruments:
        currencies.add(instrument.quote_currency.code)
    return tuple(sorted(currencies))


def _instrument_venues(instruments: Sequence[Instrument]) -> tuple[Venue, ...]:
    venues = {instrument.id.venue.value: instrument.id.venue for instrument in instruments}
    return tuple(venues[key] for key in sorted(venues))
