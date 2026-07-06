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
from typing import Any, Protocol

import pandas as pd
from aegis_data.distributions import Distribution
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import CacheConfig, LoggingConfig
from nautilus_trader.model.data import Bar, CustomData, DataType
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.instruments import CurrencyPair, Instrument
from nautilus_trader.model.objects import Currency, Money
from nautilus_trader.risk.config import RiskEngineConfig

from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog import (
    CatalogBackedDataPort,
    NautilusDataProviderPort,
    RawBarRequest,
    parquet_data_catalog,
)

from aegis_trader.bundles.book_sleeves import (
    SleeveBundles,
    load_book_sleeves,
    union_loadable_instrument_ids,
)
from aegis_trader.bundles.port import BundleRegistryPort
from aegis_trader.bundles.registry import EntryPointBundleRegistry
from aegis_trader.config import load_book_config
from aegis_trader.data import wrangle_bars, wrangle_fx_quotes
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.book_timeframe import resolve_book_timeframe
from aegis_trader.domain.risk_guard import RiskGuardConfig
from aegis_trader.portfolio.performance import (
    BookEquityRecorder,
    BookEquityRecorderConfig,
    return_stats,
)
from aegis_trader.trader.costs import build_simulated_cost_models
from aegis_trader.trader.dividends import build_dividend_modules
from aegis_trader.trader.financing import FinancingModule, build_financing_module
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

_PRICE_COLS = ("Open", "High", "Low", "Close")
_OHLCV_ARRAYS = (*_PRICE_COLS, "Volume")

# The backtest cache holds the rolling bar window the strategy reads each period;
# at least the deepest sleeve's lookback (+1) must fit, so the runner widens it
# from this floor when a contract needs more.
DEFAULT_BACKTEST_BAR_CAPACITY = 10_000


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
    distributions: tuple[Distribution, ...] = ()


@dataclass(frozen=True)
class BookBacktestResult:
    """Finished book backtest plus book-level financing diagnostics."""

    engine: BacktestEngine
    financing_totals: dict[str, float]


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
    port: CatalogBackedDataPort | None = None

    def load(
        self,
        instrument_ids: tuple[InstrumentId, ...],
        *,
        timeframe: str,
        start: str,
        end: str,
    ) -> BacktestMarketData:
        data_port = self._data_port()
        instruments = _catalog_instruments(data_port, instrument_ids)
        frames = data_port.load_raw_bars(
            RawBarRequest(
                instrument_ids=instrument_ids,
                start=start,
                end=end,
                timeframe=timeframe,
            )
        )
        # ADR-0008: Trader backtests consume distributions through the same verified
        # catalog-port seam as RD, never by querying distribution storage directly.
        # A cash FX pair pays no distributions — the verified store carries no
        # coverage record for conversion legs, so they are excluded from the request.
        distribution_ids = tuple(
            instrument_id
            for instrument_id in instrument_ids
            if not isinstance(instruments[instrument_id], CurrencyPair)
        )
        distributions = data_port.distributions(
            distribution_ids,
            start=start,
            end=end,
        )
        return BacktestMarketData(
            instruments=instruments,
            ohlcv=frames,
            distributions=distributions,
        )

    def _data_port(self) -> CatalogBackedDataPort:
        if self.port is not None:
            return self.port
        catalog = parquet_data_catalog(self.catalog_path)
        return CatalogBackedDataPort(
            catalog,
            provider=self.provider,
            distribution_provider=_distribution_provider(self.provider),
        )


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
) -> BookBacktestResult:
    """Build and run a commingled-book backtest from the Nautilus catalog.

    There is no Historical Store, symbol map, or provider-specific identity on
    this path.  The catalog must hold instrument definitions keyed by the same
    native ``InstrumentId`` values declared by the Execution Bundles.  Raw bars
    are read through ``CatalogBackedDataPort``, so catalog coverage gaps fail
    before the Nautilus engine starts.
    """
    book = load_book_config(book_path)
    registry = registry if registry is not None else EntryPointBundleRegistry()
    sleeves = load_book_sleeves(book, registry)
    book_timeframe = resolve_book_timeframe(
        bundle.contract.timeframe for _name, bundle in sleeves
    )
    instrument_ids = union_loadable_instrument_ids(sleeves)
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
    financing_module = _add_venues(
        engine,
        book=book,
        instruments=tuple(market_data.instruments.values()),
        sleeves=sleeves,
        distributions=market_data.distributions,
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
    financing_totals = (
        financing_module.totals.by_currency if financing_module is not None else {}
    )
    return BookBacktestResult(engine=engine, financing_totals=financing_totals)


def _distribution_provider(provider: NautilusDataProviderPort | None) -> Any | None:
    if provider is None or not hasattr(provider, "request_adjusted_last"):
        return None
    return provider


def book_return_stats(engine: BacktestEngine) -> dict[str, float]:
    """Base-currency return statistics for a finished book backtest."""
    for actor in engine.trader.actors():
        if isinstance(actor, BookEquityRecorder):
            return return_stats(actor.equity_curve)
    return {}


def build_risk_engine_config(
    risk_guard_config: RiskGuardConfig | None = None,
) -> RiskEngineConfig:
    """The backtest RiskEngine config (``BacktestEngine`` requires the non-live
    variant).

    Mirrors the live node's RiskEngine wiring (:func:`aegis_trader.trader.node.
    build_live_risk_engine_config`) so the overlay validated in backtest is
    constructed the same way it trades — never bypassed, carrying the RiskGuard's
    order submit/modify rate limits.
    """
    guard = risk_guard_config or RiskGuardConfig()
    return RiskEngineConfig(
        bypass=False,
        max_order_submit_rate=guard.max_order_submit_rate,
        max_order_modify_rate=guard.max_order_modify_rate,
    )


def build_backtest_engine_config(
    *,
    trader_id: str = "BACKTEST-001",
    risk_guard_config: RiskGuardConfig | None = None,
    bar_capacity: int = DEFAULT_BACKTEST_BAR_CAPACITY,
) -> BacktestEngineConfig:
    """Build the backtest engine config.

    Mirrors the live node's RiskEngine wiring so the overlay validated in backtest
    is constructed the same way it trades — "what you backtest is what you trade".
    The runner adds venues, instruments, data, and the strategy to the resulting
    ``BacktestEngine`` and pairs it with a plain ``MARKET`` (``fill_time_in_force``
    ``None``), which fills at the execution bar's close.
    """
    return BacktestEngineConfig(
        trader_id=trader_id,
        cache=CacheConfig(bar_capacity=bar_capacity),
        risk_engine=build_risk_engine_config(risk_guard_config),
        logging=LoggingConfig(),
    )


def _catalog_instruments(
    data_port: CatalogBackedDataPort,
    instrument_ids: tuple[InstrumentId, ...],
) -> dict[InstrumentId, Instrument]:
    loaded = {
        instrument.id.value: instrument
        for instrument in data_port.instruments(instrument_ids)
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


def _validate_market_data(sleeves: SleeveBundles, market_data: BacktestMarketData) -> None:
    for sleeve_name, bundle in sleeves:
        contract = bundle.contract
        for instrument_id in contract.exchange:
            # A conversion leg with no data means every non-base-quoted delta is
            # silently dropped in sizing — fail before the engine starts.
            if instrument_id not in market_data.instruments:
                raise CatalogInstrumentError(
                    "data source did not return the FX conversion pair "
                    f"{instrument_id.value} declared by sleeve {sleeve_name.value!r}"
                )
            if market_data.ohlcv.get(instrument_id) is None:
                raise ContractDataError(
                    sleeve_name.value,
                    instrument_id,
                    "data source did not return raw bars for the FX conversion leg",
                )
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


def _cache_bar_capacity(sleeves: SleeveBundles) -> int:
    required = max(bundle.contract.lookback_bars for _name, bundle in sleeves) + 1
    return max(DEFAULT_BACKTEST_BAR_CAPACITY, required)


def _add_venues(
    engine: BacktestEngine,
    *,
    book: BookConfig,
    instruments: Sequence[Instrument],
    sleeves: SleeveBundles,
    distributions: Sequence[Distribution],
    starting_cash: float,
) -> FinancingModule | None:
    account_currencies = _account_currencies(book, instruments)
    native_venues = _instrument_venues(instruments)
    account_type = (
        AccountType.MARGIN
        if (
            len(native_venues) > 1
            or _requires_margin_account(sleeves)
            or book.costs.margin_interest.annual_debit_rates
        )
        else AccountType.CASH
    )
    starting_balances, balance_currencies = _starting_balances(
        book,
        account_currencies,
        starting_cash,
    )
    financing_module = build_financing_module(book.costs)
    for index, native_venue in enumerate(native_venues):
        cost_models = build_simulated_cost_models(book)
        modules = [
            *([financing_module] if index == 0 and financing_module is not None else []),
            *build_dividend_modules(distributions),
        ]
        # Financing is book-level: it nets the shared cache across all venue
        # accounts and must live only on the starting-balance venue.
        engine.add_venue(
            native_venue,
            oms_type=OmsType.NETTING,
            account_type=account_type,
            base_currency=None,
            starting_balances=starting_balances
            if index == 0
            else _zero_balances(balance_currencies),
            modules=modules,
            fill_model=cost_models.fill_model,
            fee_model=cost_models.fee_model,
            book_type=BookType.L1_MBP,
            allow_cash_borrowing=account_type == AccountType.MARGIN
            or len(balance_currencies) > 1,
        )
    return financing_module


def _add_instruments_and_bars(
    engine: BacktestEngine,
    *,
    market_data: BacktestMarketData,
    timeframe: str,
) -> None:
    for instrument_id, instrument in market_data.instruments.items():
        engine.add_instrument(instrument)
        frame = market_data.ohlcv[instrument_id]
        bars = _wrangle_external_bars(instrument, frame, timeframe)
        engine.add_data(bars, sort=False)
        if isinstance(instrument, CurrencyPair):
            # An FX conversion leg feeds the cache mark xrate the same way live
            # does: one quote per bar close (strategy.on_quote_tick), so sizing's
            # fx_rate read works from the same series the panel conversion uses.
            engine.add_data(_fx_quotes(instrument, frame), sort=False)
    _add_distribution_data(engine, market_data.distributions)


def _add_distribution_data(
    engine: BacktestEngine,
    distributions: Sequence[Distribution],
) -> None:
    if not distributions:
        return
    data_type = DataType(Distribution)
    engine.add_data(
        [
            CustomData(data_type=data_type, data=distribution)
            for distribution in distributions
        ],
        validate=False,
        sort=False,
    )


def _fx_quotes(pair: CurrencyPair, ohlcv: pd.DataFrame) -> list[Any]:
    frame = _normalize_ohlcv(ohlcv)
    closes = frame["close"]
    if closes.index.tz is None:
        closes = closes.tz_localize("UTC")
    return wrangle_fx_quotes(pair, closes)


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
                    str(raw_bar_type(instrument_id, timeframe))
                    for instrument_id in instrument_ids
                ),
            )
        )
    )


def _add_strategy(
    engine: BacktestEngine,
    *,
    book: BookConfig,
    sleeves: SleeveBundles,
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


def _requires_margin_account(sleeves: SleeveBundles) -> bool:
    return any(bundle.direction in {"both", "shortonly"} for _name, bundle in sleeves)


def _account_currencies(
    book: BookConfig,
    instruments: Sequence[Instrument],
) -> tuple[str, ...]:
    currencies = {book.base_currency}
    for instrument in instruments:
        currencies.add(instrument.quote_currency.code)
    for currency, _rate in book.costs.margin_interest.annual_debit_rates:
        currencies.add(currency)
    return tuple(sorted(currencies))


def _instrument_venues(instruments: Sequence[Instrument]) -> tuple[Venue, ...]:
    venues = {instrument.id.venue.value: instrument.id.venue for instrument in instruments}
    return tuple(venues[key] for key in sorted(venues))
