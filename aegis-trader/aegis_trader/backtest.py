"""Commingled-book Store Read backtest runner.

Composes the pieces into a runnable ``BacktestEngine``: load ``book.toml`` ->
resolve each sleeve's bundle (registry) -> derive each instrument's baked
``InstrumentRef`` + native quote currency from the bundle -> read Native Market
Bars and FX History from ``aegis-data`` -> adapt those frames to Nautilus bars and
quotes at the Trader boundary -> register the sleeves and run the overlay.

Trader backtests never Pull and never fetch remote history. Missing Covered
History fails closed before the Nautilus engine runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Currency, Money

from aegis_data.calendars import TradingCalendar
from aegis_data.store import FxPair, read_fx_history, read_native_bars
from aegis_runtime import ExecutionBundle, InstrumentRef
from aegis_runtime.currency import _major_currency_and_scale

from aegis_trader.bundles.port import BundleRegistryPort
from aegis_trader.bundles.registry import EntryPointBundleRegistry
from aegis_trader.config import load_book_config
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.types import SleeveName
from aegis_trader.data import (
    InstrumentSpec,
    bar_type,
    build_currency_pair,
    build_equity,
    resolve_book_timeframe,
    wrangle_bars,
    wrangle_fx_quotes,
)
from aegis_trader.portfolio.performance import (
    BookEquityRecorder,
    BookEquityRecorderConfig,
    return_stats,
)
from aegis_trader.trader.costs import build_simulated_cost_models
from aegis_trader.trader.financing import build_financing_modules
from aegis_trader.trader.modes import build_backtest_engine_config
from aegis_trader.trader.pipeline import FixtureInstrumentResolver
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

_PRICE_COLS = ("open", "high", "low", "close")
_STORE_OHLCV_ARRAYS = (*_PRICE_COLS, "volume")

_SleeveBundles = list[tuple[SleeveName, ExecutionBundle]]


class ContractDataError(ValueError):
    """Store Read data does not satisfy a sleeve's DataContract — the backtest
    fails closed rather than running the overlay on data that would not pass the
    bundle contract."""

    def __init__(self, sleeve: str, ref: str, detail: str) -> None:
        self.sleeve = sleeve
        self.ref = ref
        super().__init__(f"sleeve {sleeve!r} ({ref}): {detail}")


class FxDataError(ValueError):
    """A required FX cross series does not cover the run window — the backtest
    fails closed rather than valuing foreign legs on a fabricated rate."""

    def __init__(self, base: str, quote: str, detail: str) -> None:
        self.base = base
        self.quote = quote
        super().__init__(f"FX {base}/{quote}: {detail}")


def run_book_backtest(
    book_path: str | Path,
    *,
    start: str,
    end: str,
    store_dir: Path | None = None,
    registry: BundleRegistryPort | None = None,
    venue: str = "SIM",
    starting_cash: float = 1_000_000.0,
    trader_id: str = "BACKTEST-001",
) -> BacktestEngine:
    """Build and run the commingled-book backtest from ``aegis-data`` Store Read.

    ``store_dir`` is a test/deployment override for the Historical Store root;
    absent, ``aegis-data`` uses its OS-global store. There is deliberately no
    remote-fetch, Pull, source, or ``DataConfig`` parameter on this path.
    """
    book = load_book_config(book_path)
    registry = registry if registry is not None else EntryPointBundleRegistry()
    sleeves = [(s.name, registry.load(s.wheel_filename)) for s in book.sleeves]
    book_timeframe = resolve_book_timeframe(
        bundle.contract.timeframe for _name, bundle in sleeves
    )
    account_currencies = _account_currencies(book.base_currency, sleeves)
    account_type = AccountType.MARGIN if _requires_margin_account(sleeves) else AccountType.CASH
    starting_balances, balance_currencies = _starting_balances(
        book, account_currencies, starting_cash
    )

    instrument_inputs = _read_instrument_inputs(
        sleeves,
        timeframe=book_timeframe,
        start=start,
        end=end,
        store_dir=store_dir,
    )
    fx_inputs = _read_fx_inputs(
        book,
        sleeves,
        timeframe=book_timeframe,
        start=start,
        end=end,
        bar_index=instrument_inputs.bar_index,
        store_dir=store_dir,
    )

    engine = BacktestEngine(
        build_backtest_engine_config(
            trader_id=trader_id,
            bar_capacity=_cache_bar_capacity(sleeves),
        )
    )
    cost_models = build_simulated_cost_models(book)
    financing_modules = build_financing_modules(book.costs)
    engine.add_venue(
        Venue(venue),
        oms_type=OmsType.NETTING,
        account_type=account_type,
        base_currency=None,  # multi-currency account; base-currency returns come from BookEquityRecorder/return_stats
        starting_balances=starting_balances,
        modules=financing_modules,
        fill_model=cost_models.fill_model,
        fee_model=cost_models.fee_model,
        book_type=BookType.L1_MBP,
        allow_cash_borrowing=len(balance_currencies) > 1,
    )

    bimap: dict[object, InstrumentId] = {}
    for bars in instrument_inputs.bars:
        instrument = build_equity(
            InstrumentSpec(
                figi=bars.ref.value,
                venue=venue,
                quote_currency=bars.quote_currency,
            )
        )
        engine.add_instrument(instrument)
        engine.add_data(wrangle_bars(instrument, bars.ohlcv, book_timeframe))
        bimap[bars.ref] = instrument.id

    # FX as quote-tick'd CurrencyPair instruments (same path as live): the
    # overlay's on_quote_tick mirrors these into cache mark xrates for sizing,
    # and the accounting layer values foreign legs from the same quotes.
    for ccy, aligned in fx_inputs.items():
        pair = build_currency_pair(book.base_currency, ccy, venue)
        engine.add_instrument(pair)
        engine.add_data(wrangle_fx_quotes(pair, aligned))

    # Reporting-only: sample base-currency NAV per bar so headline return stats
    # (Sharpe, vol, PnL%) can be computed over a single-currency equity curve —
    # Nautilus' own analyzer cannot, for a base_currency=None account (aegis-rd-syp).
    engine.add_actor(
        BookEquityRecorder(
            BookEquityRecorderConfig(
                base_currency=book.base_currency,
                bar_types=tuple(
                    str(bar_type(instr_id.value, book_timeframe))
                    for instr_id in bimap.values()
                ),
            )
        )
    )

    strategy = RebalanceStrategy(RebalanceStrategyConfig(book=book, fill_time_in_force=None))
    for name, bundle in sleeves:
        strategy.register_sleeve(name, bundle)
    strategy.set_instrument_resolver(FixtureInstrumentResolver(bimap))
    engine.add_strategy(strategy)

    engine.run()
    return engine


def _cache_bar_capacity(sleeves: _SleeveBundles) -> int:
    required = max(bundle.contract.lookback_bars for _name, bundle in sleeves) + 1
    return max(10_000, required)


def book_return_stats(engine: BacktestEngine) -> dict[str, float]:
    """Base-currency return statistics for a finished book backtest.

    Reads the :class:`BookEquityRecorder` that :func:`run_book_backtest` installs
    and runs the standard return stats over its base-currency NAV equity curve —
    the multi-currency-account remedy Nautilus' native ``stats_returns`` omits
    (aegis-rd-syp).  Returns an empty mapping when no recorder is present (nothing
    to report), so reporting never fails closed on a stats-only concern.
    """
    for actor in engine.trader.actors():
        if isinstance(actor, BookEquityRecorder):
            return return_stats(actor.equity_curve)
    return {}


@dataclass(frozen=True)
class _InstrumentBars:
    ref: InstrumentRef
    quote_currency: str
    ohlcv: pd.DataFrame


@dataclass(frozen=True)
class _InstrumentInputs:
    bars: tuple[_InstrumentBars, ...]
    bar_index: frozenset[pd.Timestamp]


def _read_instrument_inputs(
    sleeves: _SleeveBundles,
    *,
    timeframe: str,
    start: str,
    end: str,
    store_dir: Path | None,
) -> _InstrumentInputs:
    loaded: set[InstrumentRef] = set()
    bars: list[_InstrumentBars] = []
    bar_index: set[pd.Timestamp] = set()
    for sleeve_name, bundle in sleeves:
        for ref, symbol in zip(bundle.contract.refs, bundle.symbols, strict=True):
            if ref in loaded:
                continue
            major, scale = _major_currency_and_scale(bundle.currency_by_symbol[symbol])
            raw = _read_native_market_bars(
                ref,
                required_arrays=bundle.contract.required_arrays,
                timeframe=timeframe,
                start=start,
                end=end,
                store_dir=store_dir,
            )
            _validate_contract_data(
                raw,
                sleeve=sleeve_name.value,
                ref=ref.value,
                required_arrays=bundle.contract.required_arrays,
                min_rows=bundle.contract.lookback_bars + 1,
            )
            normalized = _normalize(raw, scale)
            bars.append(_InstrumentBars(ref=ref, quote_currency=major, ohlcv=normalized))
            bar_index.update(normalized.index)
            loaded.add(ref)
    return _InstrumentInputs(bars=tuple(bars), bar_index=frozenset(bar_index))


def _read_native_market_bars(
    ref: InstrumentRef,
    *,
    required_arrays: tuple[str, ...],
    timeframe: str,
    start: str,
    end: str,
    store_dir: Path | None,
) -> pd.DataFrame:
    # Trader's book universe is US-listed (yfinance) and CME futures (GLBX); both
    # expect bars on the XNYS calendar.
    frames = read_native_bars(
        (ref,),
        arrays=_store_read_arrays(required_arrays),
        timeframe=timeframe,
        start=start,
        end=end,
        calendar=TradingCalendar.XNYS,
        store_dir=store_dir,
    )
    return frames[ref]


def _read_fx_inputs(
    book: BookConfig,
    sleeves: _SleeveBundles,
    *,
    timeframe: str,
    start: str,
    end: str,
    bar_index: frozenset[pd.Timestamp],
    store_dir: Path | None,
) -> dict[str, pd.Series]:
    fx_index = pd.DatetimeIndex(sorted(bar_index))
    aligned: dict[str, pd.Series] = {}
    for ccy in sorted(_required_fx_currencies(sleeves)):
        if ccy == book.base_currency:
            continue
        pair = FxPair(book.base_currency, ccy)
        history = read_fx_history(
            (pair,),
            timeframe=timeframe,
            start=start,
            end=end,
            calendar=TradingCalendar.WEEKDAY,
            store_dir=store_dir,
        )
        fx_series = history[pair]
        aligned[ccy] = _align_fx_to_bars(
            fx_series,
            fx_index=fx_index,
            base=book.base_currency,
            quote=ccy,
        )
    return aligned


def _align_fx_to_bars(
    fx_series: pd.Series,
    *,
    fx_index: pd.DatetimeIndex,
    base: str,
    quote: str,
) -> pd.Series:
    aligned = fx_series.reindex(fx_index).ffill()
    if aligned.isna().any():
        first_uncovered = aligned.index[aligned.isna()][0]
        raise FxDataError(
            base,
            quote,
            f"no rate at/before {first_uncovered.date()}; "
            f"the series must cover the run window",
        )
    return aligned


def _required_fx_currencies(sleeves: _SleeveBundles) -> set[str]:
    currencies: set[str] = set()
    for _name, bundle in sleeves:
        currencies.update(bundle.contract.required_fx_currencies)
    return currencies


def _store_read_arrays(required_arrays: tuple[str, ...]) -> tuple[str, ...]:
    arrays: list[str] = []
    seen: set[str] = set()
    for array in (*_STORE_OHLCV_ARRAYS, *required_arrays):
        key = array.lower()
        if key in seen:
            continue
        seen.add(key)
        arrays.append(array)
    return tuple(arrays)


def _starting_balances(
    book: BookConfig,
    account_currencies: tuple[str, ...],
    starting_cash: float,
) -> tuple[list[Money], tuple[str, ...]]:
    """Per-currency venue funding, plus the funded currency set.

    ``book.toml`` ``[starting_balances]`` funds the declared currencies (traded
    currencies not declared start at zero and are reached via per-currency margin
    loans); absent, a single ``base_currency`` balance is funded with
    ``starting_cash``.
    """
    declared = dict(book.starting_balances)
    if declared:
        currencies = tuple(sorted(set(account_currencies) | set(declared)))
        balances = [Money(declared.get(ccy, 0.0), Currency.from_str(ccy)) for ccy in currencies]
    else:
        currencies = account_currencies
        balances = [
            Money(starting_cash if ccy == book.base_currency else 0.0, Currency.from_str(ccy))
            for ccy in currencies
        ]
    return balances, currencies


def _requires_margin_account(sleeves: _SleeveBundles) -> bool:
    return any(_bundle_direction(bundle) in {"both", "shortonly"} for _name, bundle in sleeves)


def _bundle_direction(bundle: object) -> str:
    plan = getattr(bundle, "plan", None) or getattr(bundle, "_plan", None)
    return str(getattr(plan, "direction", "longonly"))


def _account_currencies(
    base_currency: str,
    sleeves: _SleeveBundles,
) -> tuple[str, ...]:
    currencies = {base_currency}
    for _name, bundle in sleeves:
        currencies |= set(bundle.contract.required_fx_currencies)
        for currency in bundle.currency_by_symbol.values():
            major, _scale = _major_currency_and_scale(currency)
            currencies.add(major)
    return tuple(sorted(currencies))


def _validate_contract_data(
    ohlcv: pd.DataFrame,
    *,
    sleeve: str,
    ref: str,
    required_arrays: tuple[str, ...],
    min_rows: int,
) -> None:
    """Fail closed unless *ohlcv* satisfies the contract: every required array is
    present (matched case-insensitively against the Store Read frame's columns)
    and at least *min_rows* (lookback + 1) rows are available."""
    columns = {str(c).lower() for c in ohlcv.columns}
    missing = tuple(a for a in required_arrays if a.lower() not in columns)
    if missing:
        raise ContractDataError(sleeve, ref, f"missing required arrays {list(missing)}")
    if len(ohlcv) < min_rows:
        raise ContractDataError(
            sleeve, ref,
            f"{len(ohlcv)} rows read, need at least {min_rows} (lookback + 1)",
        )


def _normalize(ohlcv: pd.DataFrame, scale: float) -> pd.DataFrame:
    """OHLCV ready for the wrangler: lower-cased columns, minor-unit prices
    (pence) divided into majors, and OHLC consistency enforced (adjusted-close
    data can leave a row's high < close / low > open, which the wrangler rejects).
    """
    df = ohlcv.rename(columns=str.lower)[[*_PRICE_COLS, "volume"]].dropna().copy()
    if scale != 1:
        for col in _PRICE_COLS:
            df[col] = df[col] / scale
    df["high"] = df[list(_PRICE_COLS)].max(axis=1)
    df["low"] = df[list(_PRICE_COLS)].min(axis=1)
    return df
