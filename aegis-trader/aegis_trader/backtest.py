"""Catalog-backed Trader backtest entrypoints.

The runner is intentionally forward-only: Execution Bundles declare native
Nautilus ``InstrumentId`` values, raw bars come from the Nautilus
``ParquetDataCatalog`` through the Aegis Data catalog port, and the same
``RebalanceStrategy`` used by paper/live is run inside Nautilus'
``BacktestEngine``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
from aegis_data.array_names import OHLCV_ARRAY_NAMES
from aegis_data.custom_data import (
    VOCABULARY as CUSTOM_ARRAY_VOCABULARY,
    records_for_arrays,
)
from aegis_data.distributions import Distribution, distribution_records
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import CacheConfig, LoggingConfig
from nautilus_trader.core.data import Data
from nautilus_trader.model.data import Bar, CustomData, DataType
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import ClientId, InstrumentId, Venue
from nautilus_trader.model.instruments import CurrencyPair, Instrument
from nautilus_trader.model.objects import Currency, Money
from nautilus_trader.portfolio.config import PortfolioConfig
from nautilus_trader.risk.config import RiskEngineConfig

from aegis_data.marking import DeclaredMarkingResolver, RawBarTypeResolver
from aegis_data.catalog import (
    CatalogBackedDataPort,
    NautilusDataProviderPort,
    CatalogWindowRequest,
    catalog_root,
    parquet_data_catalog,
)

from aegis_trader.bundles.book import AssembledBook, assemble_book
from aegis_trader.bundles.marking import recorded_marking_resolver
from aegis_trader.bundles.port import BundleRegistryPort
from aegis_trader.bundles.registry import EntryPointBundleRegistry
from aegis_trader.config import load_book_config
from aegis_trader.data import wrangle_bars, wrangle_fx_quotes, wrangle_quote_bars
from aegis_trader.domain.analytics_horizon import AnalyticsHorizon
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.risk_guard import RiskGuardConfig
from aegis_trader.domain.streams import MarketStream
from aegis_trader.portfolio.performance import (
    BookEquityRecorder,
    BookEquityRecorderConfig,
    return_stats,
)
from aegis_trader.trader.costs import build_simulated_cost_models
from aegis_trader.trader.dividends import build_dividend_modules
from aegis_trader.trader.financing import FinancingModule, build_financing_module
from aegis_trader.trader.sleeve_arrays import SleeveArrays
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

_PRICE_COLS = ("Open", "High", "Low", "Close")

# The backtest cache holds the rolling bar window the strategy reads each period;
# at least the deepest sleeve's lookback (+1) must fit, so the runner widens it
# from this floor when a contract needs more.
DEFAULT_BACKTEST_BAR_CAPACITY = 10_000
_CUSTOM_DATA_CLIENT_ID = ClientId("AEGIS-CUSTOM")


class CatalogInstrumentError(ValueError):
    """A sleeve's contract declared an id the loaded market data does not carry.

    Trader's own book-assembly concern, distinct from catalog completeness —
    a definition the catalog does not hold fails inside the port's window read
    with its authoring error (Data ADR-0012)."""


class ContractDataError(ValueError):
    """Catalog bars do not satisfy an Execution Bundle's ``DataContract``."""

    def __init__(self, sleeve: str, instrument_id: InstrumentId, detail: str) -> None:
        self.sleeve = sleeve
        self.instrument_id = instrument_id
        super().__init__(f"sleeve {sleeve!r} ({instrument_id.value}): {detail}")


@dataclass(frozen=True)
class BacktestMarketData:
    """Catalog material the runner feeds into Nautilus' ``BacktestEngine``.

    ``ohlcv`` is each instrument's mark series (a quote-marked leg's derived
    mid).  ``quote_frames`` carries the ``(bid, ask)`` sided frames for
    quote-marked legs only — the research fill projection's feed, derived here
    and never serialized (aegis-rd-tggo.5).
    """

    instruments: Mapping[InstrumentId, Instrument]
    ohlcv: Mapping[InstrumentId, pd.DataFrame]
    records: tuple[Data, ...] = ()
    quote_frames: Mapping[InstrumentId, tuple[pd.DataFrame, pd.DataFrame]] = field(
        default_factory=dict
    )

    @property
    def distributions(self) -> tuple[Distribution, ...]:
        """Distribution records consumed by the dividend cash module."""
        return distribution_records(self.records)


@dataclass(frozen=True)
class BookBacktestResult:
    """Finished book backtest plus book-level financing diagnostics."""

    engine: BacktestEngine
    financing_totals: dict[str, float]
    analytics_horizon: AnalyticsHorizon


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
    resolver: RawBarTypeResolver = DeclaredMarkingResolver()

    def load(
        self,
        instrument_ids: tuple[InstrumentId, ...],
        *,
        timeframe: str,
        start: str,
        end: str,
    ) -> BacktestMarketData:
        data_port = self._data_port()
        request = CatalogWindowRequest(
            instrument_ids=instrument_ids,
            start=start,
            end=end,
            timeframe=timeframe,
        )
        # Data ADR-0012: the whole window — bars, complete definitions, verified
        # distributions — is ONE coherent port read.  Definition completeness and
        # distribution applicability (a cash FX pair pays no distributions) are
        # the port's guarantees now, not caller-side triage or filtering.
        window = data_port.load_window(request)
        return BacktestMarketData(
            instruments=window.instruments,
            ohlcv=window.ohlcv,
            records=window.records,
            quote_frames=data_port.load_quote_frames(request),
        )

    def _data_port(self) -> CatalogBackedDataPort:
        if self.port is not None:
            return self.port
        catalog = parquet_data_catalog(self.catalog_path)
        return CatalogBackedDataPort(
            catalog,
            provider=self.provider,
            resolver=self.resolver,
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
    bar_type_resolver: RawBarTypeResolver | None = None,
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
    assembled_book = assemble_book(book, registry)
    # The one raw bar-type resolution seam (aegis-rd-tggo.1), shared by the data
    # source, the wrangler, the equity recorder, and the strategy so they name
    # identical bars.  The sim/fill projection below is DERIVED from the resolved
    # markings, research-side only, and never serialized (aegis-rd-tggo.5).
    resolver = (
        bar_type_resolver
        if bar_type_resolver is not None
        else _book_resolver(assembled_book)
    )
    source = data_source or CatalogBacktestDataSource(
        catalog_path=catalog_path,
        provider=provider,
        resolver=resolver,
    )
    loaded = tuple(
        (
            timeframe,
            source.load(instrument_ids, timeframe=timeframe, start=start, end=end),
        )
        for timeframe, instrument_ids in _stream_load_groups(assembled_book)
    )
    market_data = _merged_market_data(loaded)
    _validate_market_data(assembled_book, market_data)

    engine = BacktestEngine(
        build_backtest_engine_config(
            trader_id=trader_id,
            bar_capacity=max(
                DEFAULT_BACKTEST_BAR_CAPACITY,
                *(
                    requirement.history_bars
                    for requirement in assembled_book.required_streams
                ),
                *assembled_book.continuous_history_bars.values(),
            ),
            # Quote-marked legs mark P&L at the quote mid via MarkPriceUpdate;
            # bar-marked legs fall back to their bar close.
            use_mark_prices=bool(market_data.quote_frames),
        )
    )
    financing_module = _add_venues(
        engine,
        book=assembled_book,
        instruments=tuple(market_data.instruments.values()),
        distributions=market_data.distributions,
        starting_cash=starting_cash,
        quote_marked_ids=frozenset(market_data.quote_frames),
    )
    added_instrument_ids: set[InstrumentId] = set()
    for timeframe, group_data in loaded:
        _add_instruments_and_bars(
            engine,
            market_data=group_data,
            timeframe=timeframe,
            resolver=resolver,
            added_instrument_ids=added_instrument_ids,
        )
    custom_catalog_path = catalog_path if catalog_path is not None else catalog_root()
    array_records = records_for_arrays(
        _custom_array_requirements(assembled_book),
        start=pd.Timestamp(start),
        end=pd.Timestamp(end),
        catalog_path=custom_catalog_path,
    )
    _add_custom_data(engine, (*market_data.records, *array_records))
    engine.sort_data()
    _add_equity_recorder(
        engine,
        book=book,
        streams=tuple(
            requirement.stream for requirement in assembled_book.required_streams
        ),
        resolver=resolver,
    )
    _add_strategy(
        engine,
        book=assembled_book,
        resolver=resolver,
        custom_catalog_path=custom_catalog_path,
    )

    # ``end`` keeps the engine advancing the clock past the final data event,
    # so a re-net alert scheduled 1ns after the last bar still fires and the
    # final completed periods rebalance exactly as they do live.
    engine.run(end=end)
    financing_totals = (
        financing_module.totals.by_currency if financing_module is not None else {}
    )
    return BookBacktestResult(
        engine=engine,
        financing_totals=financing_totals,
        analytics_horizon=assembled_book.analytics_horizon,
    )


def _stream_load_groups(
    book: AssembledBook,
) -> tuple[tuple[str, tuple[InstrumentId, ...]], ...]:
    """The catalog load plan: the Book's required streams grouped per timeframe.

    Continuous-root material (dated legs, definitions) arrives through the
    port beside whatever cash ids are requested, so a Book with continuous
    declarations always has a load group at the continuous timeframe — a
    futures-only Book makes that one call with no cash ids at all.
    """
    ids_by_timeframe: dict[str, dict[str, InstrumentId]] = {}
    for declaration in book.continuous_declarations.values():
        ids_by_timeframe.setdefault(declaration.timeframe, {})
    for requirement in book.required_streams:
        stream = requirement.stream
        ids_by_timeframe.setdefault(stream.timeframe, {})[
            stream.instrument_id.value
        ] = stream.instrument_id
    return tuple(
        (timeframe, tuple(ids[key] for key in sorted(ids)))
        for timeframe, ids in sorted(ids_by_timeframe.items())
    )


def _merged_market_data(
    loaded: tuple[tuple[str, BacktestMarketData], ...],
) -> BacktestMarketData:
    """One Book-wide view of the per-timeframe loads, for validation and venues."""
    if len(loaded) == 1:
        return loaded[0][1]
    instruments: dict[InstrumentId, Instrument] = {}
    ohlcv: dict[InstrumentId, pd.DataFrame] = {}
    records: list[Data] = []
    quote_frames: dict[InstrumentId, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for _timeframe, market_data in loaded:
        instruments.update(market_data.instruments)
        ohlcv.update(market_data.ohlcv)
        records.extend(market_data.records)
        quote_frames.update(market_data.quote_frames)
    return BacktestMarketData(
        instruments=instruments,
        ohlcv=ohlcv,
        records=tuple(records),
        quote_frames=quote_frames,
    )


def _book_resolver(book: AssembledBook) -> RawBarTypeResolver:
    """The runner's marking resolver for *book*: the recorded markings, always.

    The backtest resolves exactly the read-only view live consumes, so research
    validation and deployment share one truth — including the failure: a bundle
    that records no marking for a leg fails here with the same re-export error
    live gives, never a silent default (forward-first; no pre-recording path).
    """
    return recorded_marking_resolver(book)


def _custom_array_requirements(
    book: AssembledBook,
) -> dict[InstrumentId, tuple[str, ...]]:
    names_by_instrument_id: dict[InstrumentId, dict[str, None]] = {}
    for bundle in book.sleeves.values():
        custom_names = tuple(
            name
            for name in bundle.contract.required_arrays
            if name in CUSTOM_ARRAY_VOCABULARY
        )
        for instrument_id in bundle.contract.instrument_ids:
            names_by_instrument_id.setdefault(instrument_id, {}).update(
                dict.fromkeys(custom_names)
            )
    return {
        instrument_id: tuple(names)
        for instrument_id, names in names_by_instrument_id.items()
        if names
    }


def book_return_stats(
    engine: BacktestEngine, horizon: AnalyticsHorizon
) -> dict[str, float]:
    """Base-currency return statistics for a finished book backtest."""
    for actor in engine.trader.actors():
        if isinstance(actor, BookEquityRecorder):
            return return_stats(actor.equity_curve, horizon=horizon)
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
    use_mark_prices: bool = False,
) -> BacktestEngineConfig:
    """Build the backtest engine config.

    Mirrors the live node's RiskEngine wiring so the overlay validated in backtest
    is constructed the same way it trades — "what you backtest is what you trade".
    The runner adds venues, instruments, data, and the strategy to the resulting
    ``BacktestEngine`` and pairs it with a plain ``MARKET`` (``fill_time_in_force``
    ``None``), which fills at the execution bar's close.

    ``use_mark_prices`` is set when the book carries quote-marked legs: the
    Portfolio then values positions at the fed ``MarkPriceUpdate`` (the quote
    mid) while fills stay at the venue book's touch (aegis-rd-tggo.5).
    """
    return BacktestEngineConfig(
        trader_id=trader_id,
        cache=CacheConfig(bar_capacity=bar_capacity),
        risk_engine=build_risk_engine_config(risk_guard_config),
        portfolio=PortfolioConfig(use_mark_prices=use_mark_prices),
        logging=LoggingConfig(),
    )


def _validate_market_data(book: AssembledBook, market_data: BacktestMarketData) -> None:
    for sleeve_name, bundle in book.sleeves.items():
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
                min_rows=contract.lookback_bars + 1,
            )


def _validate_contract_frame(
    frame: pd.DataFrame,
    *,
    sleeve: str,
    instrument_id: InstrumentId,
    min_rows: int,
) -> None:
    columns = {str(column).lower() for column in frame.columns}
    required = OHLCV_ARRAY_NAMES
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


def _add_venues(
    engine: BacktestEngine,
    *,
    book: AssembledBook,
    instruments: Sequence[Instrument],
    distributions: Sequence[Distribution],
    starting_cash: float,
    quote_marked_ids: frozenset[InstrumentId] = frozenset(),
) -> FinancingModule | None:
    config = book.config
    account_currencies = _account_currencies(config, instruments)
    native_venues = _instrument_venues(instruments)
    account_type = (
        AccountType.MARGIN
        if (
            len(native_venues) > 1
            or book.requires_margin
            or config.costs.margin_interest.annual_debit_rates
        )
        else AccountType.CASH
    )
    starting_balances, balance_currencies = _starting_balances(
        config,
        account_currencies,
        starting_cash,
    )
    financing_module = build_financing_module(config.costs)
    # A venue hosting a quote-marked leg fills from the real bid/ask book; its
    # crossing cost IS the observed spread, so the book-global one-tick
    # prob_slippage retires there (aegis-rd-tggo.5).  Nautilus fill models are
    # per-venue, so a bar-marked leg co-hosted on such a venue loses the knob
    # too — its fills stay at the bar close, unslipped.
    quote_marked_venues = {
        instrument.id.venue
        for instrument in instruments
        if instrument.id in quote_marked_ids
    }
    for index, native_venue in enumerate(native_venues):
        cost_models = build_simulated_cost_models(config)
        fill_model = (
            None if native_venue in quote_marked_venues else cost_models.fill_model
        )
        modules = [
            *(
                [financing_module]
                if index == 0 and financing_module is not None
                else []
            ),
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
            fill_model=fill_model,
            fee_model=cost_models.fee_model,
            book_type=BookType.L1_MBP,
            # Fills rely on bars/quotes only, never trade ticks (aegis-rd-tggo.5):
            # Nautilus defaults this True, so the guard must be explicit — a
            # quote-marked leg's sparse trade prints must never drive a fill.
            trade_execution=False,
            allow_cash_borrowing=account_type == AccountType.MARGIN
            or len(balance_currencies) > 1,
        )
    return financing_module


def _add_instruments_and_bars(
    engine: BacktestEngine,
    *,
    market_data: BacktestMarketData,
    timeframe: str,
    resolver: RawBarTypeResolver,
    added_instrument_ids: set[InstrumentId],
) -> None:
    """Register one timeframe group's instruments and bars.

    A reference instrument shared across timeframe groups (e.g. an FX
    conversion leg consumed hourly and daily) registers its definition and
    FX quotes once; its bars still load under every required BarType.
    """
    for instrument_id, instrument in market_data.instruments.items():
        already_added = instrument_id in added_instrument_ids
        if not already_added:
            engine.add_instrument(instrument)
            added_instrument_ids.add(instrument_id)
        frame = market_data.ohlcv[instrument_id]
        sided = market_data.quote_frames.get(instrument_id)
        if sided is not None:
            # Quote-marked (aegis-rd-tggo.5): BID + ASK EXTERNAL bars are the
            # single source — the venue pairs them into L1 quotes (fills at the
            # real touch), and the strategy both signals on and publishes the
            # derived mid mark from the same bars (the one publisher, research
            # and live alike — aegis-rd-tggo.3).  No LAST/MID bar exists.
            bid_frame, ask_frame = sided
            engine.add_data(
                _wrangle_quote_external_bars(
                    instrument, bid_frame, ask_frame, timeframe, resolver
                ),
                sort=False,
            )
            continue
        bars = _wrangle_external_bars(instrument, frame, timeframe, resolver)
        engine.add_data(bars, sort=False)
        if isinstance(instrument, CurrencyPair) and not already_added:
            # An FX conversion leg feeds the cache mark xrate the same way live
            # does: one quote per bar close (strategy.on_quote_tick), so sizing's
            # fx_rate read works from the same series the panel conversion uses.
            engine.add_data(_fx_quotes(instrument, frame), sort=False)


def _wrangle_quote_external_bars(
    instrument: Instrument,
    bid_ohlcv: pd.DataFrame,
    ask_ohlcv: pd.DataFrame,
    timeframe: str,
    resolver: RawBarTypeResolver,
) -> list[Bar]:
    return wrangle_quote_bars(
        instrument,
        _normalize_ohlcv(bid_ohlcv),
        _normalize_ohlcv(ask_ohlcv),
        timeframe,
        resolver=resolver,
    )


def _add_custom_data(
    engine: BacktestEngine,
    records: Sequence[Data],
) -> None:
    if not records:
        return
    engine.add_data(
        [
            CustomData(data_type=DataType(type(record)), data=record)
            for record in records
        ],
        client_id=_CUSTOM_DATA_CLIENT_ID,
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
    resolver: RawBarTypeResolver,
) -> list[Bar]:
    frame = _normalize_ohlcv(ohlcv)
    return wrangle_bars(instrument, frame, timeframe, resolver=resolver)


def _normalize_ohlcv(ohlcv: pd.DataFrame) -> pd.DataFrame:
    columns = {str(column).lower(): column for column in ohlcv.columns}
    normalized = pd.DataFrame(index=ohlcv.index)
    for name in OHLCV_ARRAY_NAMES:
        normalized[name.lower()] = ohlcv[columns[name.lower()]]
    normalized = normalized.dropna().copy()
    normalized["high"] = normalized[[col.lower() for col in _PRICE_COLS]].max(axis=1)
    normalized["low"] = normalized[[col.lower() for col in _PRICE_COLS]].min(axis=1)
    return normalized


def _add_equity_recorder(
    engine: BacktestEngine,
    *,
    book: BookConfig,
    streams: tuple[MarketStream, ...],
    resolver: RawBarTypeResolver,
) -> None:
    engine.add_actor(
        BookEquityRecorder(
            BookEquityRecorderConfig(
                base_currency=book.base_currency,
                bar_types=tuple(
                    str(bar_type)
                    for stream in streams
                    for bar_type in resolver.resolve(
                        stream.instrument_id, stream.timeframe
                    ).mark_bars
                ),
            )
        )
    )


def _add_strategy(
    engine: BacktestEngine,
    *,
    book: AssembledBook,
    resolver: RawBarTypeResolver,
    custom_catalog_path: Path,
) -> None:
    strategy = RebalanceStrategy(
        RebalanceStrategyConfig(
            book=book.config,
            fill_time_in_force=None,
            warmup_cache_on_start=False,
        ),
        arrays=SleeveArrays.prepared(catalog_path=custom_catalog_path),
        bar_type_resolver=resolver,
    )
    strategy.register_book(book)
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
    venues = {
        instrument.id.venue.value: instrument.id.venue for instrument in instruments
    }
    return tuple(venues[key] for key in sorted(venues))
