"""Commingled-book backtest runner (closes finding a5 for real).

Composes the pieces into a runnable ``BacktestEngine``: load ``book.toml`` ->
resolve each sleeve's bundle (registry) -> derive each instrument's identity
(FIGI) + native quote currency from the bundle -> fetch OHLCV + FX (injected,
provider-agnostic) -> build instruments and bars via the data/ load side ->
feed the engine, set FX marks, register the sleeves, and run the overlay.

The fetchers are injected so the core is provider-agnostic and testable; the
defaults pull daily bars and a latest FX mark from yfinance.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Currency, Money

from aegis_runtime import ExecutionBundle
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
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

@dataclass(frozen=True)
class BarRequest:
    """What the backtest asks a provider for one instrument, derived from the
    sleeve's ``DataContract``: the provider ticker, the arrays the contract
    declares, and the date window.  A provider adapter returns those arrays;
    the runner keys identity off the contract's FIGI, not the ticker."""

    ticker: str
    required_arrays: tuple[str, ...]
    start: str
    end: str


# BarRequest -> OHLCV frame (native quote) with open/high/low/close/volume.
OhlcvFetcher = Callable[[BarRequest], pd.DataFrame]
# (base, quote, start, end) -> per-date FX series, quote units per 1 base
# (e.g. EUR,USD -> a daily series around ~1.08).
FxFetcher = Callable[[str, str, str, str], pd.Series]

_PRICE_COLS = ("open", "high", "low", "close")


class ContractDataError(ValueError):
    """Fetched data does not satisfy a sleeve's DataContract — the backtest fails
    closed rather than running the overlay on data that wouldn't pass research."""

    def __init__(self, sleeve: str, figi: str, detail: str) -> None:
        self.sleeve = sleeve
        self.figi = figi
        super().__init__(f"sleeve {sleeve!r} ({figi}): {detail}")


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
    fetch_ohlcv: OhlcvFetcher,
    fetch_fx: FxFetcher,
    registry: BundleRegistryPort | None = None,
    venue: str = "SIM",
    starting_cash: float = 1_000_000.0,
    trader_id: str = "BACKTEST-001",
) -> BacktestEngine:
    """Build and run the commingled-book backtest; returns the finished engine."""
    book = load_book_config(book_path)
    base = Currency.from_str(book.base_currency)
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

    engine = BacktestEngine(build_backtest_engine_config(trader_id=trader_id))
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

    bimap: dict[str, InstrumentId] = {}
    fx_currencies: set[str] = set()
    bar_index: set[pd.Timestamp] = set()
    for sleeve_name, bundle in sleeves:
        fx_currencies |= set(bundle.contract.required_fx_currencies)
        for figi, ticker in zip(bundle.contract.figis, bundle.symbols, strict=True):
            if figi in bimap:
                continue  # an instrument shared across sleeves is loaded once
            major, scale = _major_currency_and_scale(bundle.currency_by_symbol[ticker])
            instrument = build_equity(
                InstrumentSpec(figi=figi, venue=venue, quote_currency=major)
            )
            raw = fetch_ohlcv(
                BarRequest(
                    ticker=ticker,
                    required_arrays=bundle.contract.required_arrays,
                    start=start,
                    end=end,
                )
            )
            _validate_contract_data(
                raw,
                sleeve=sleeve_name.value,
                figi=figi,
                required_arrays=bundle.contract.required_arrays,
                min_rows=bundle.contract.lookback_bars + 1,
            )
            ohlcv = _normalize(raw, scale)
            bar_index |= set(ohlcv.index)
            engine.add_instrument(instrument)
            engine.add_data(wrangle_bars(instrument, ohlcv, book_timeframe))
            bimap[figi] = instrument.id

    # FX as quote-tick'd CurrencyPair instruments (same path as live): the
    # overlay's on_quote_tick mirrors these into cache mark xrates for sizing,
    # and the accounting layer values foreign legs from the same quotes — so a
    # bar-fed backtest no longer fails to compute account-state exchange rates.
    fx_index = pd.DatetimeIndex(sorted(bar_index))
    # Sorted: a bare set iteration is hash-seed-dependent, so the order FX pairs
    # are added to the data stream — and thus same-timestamp tie-breaks against
    # bars at valuation time — would vary run-to-run (aegis-rd-10d).
    for ccy in sorted(fx_currencies):
        if ccy == book.base_currency:
            continue
        fx_series = fetch_fx(book.base_currency, ccy, start, end)
        aligned = fx_series.reindex(fx_index).ffill()
        if aligned.isna().any():
            first_uncovered = aligned.index[aligned.isna()][0]
            raise FxDataError(
                book.base_currency,
                ccy,
                f"no rate at/before {first_uncovered.date()}; "
                f"the series must cover the run window",
            )
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
    strategy._figi_bimap = bimap  # backtest assigns InstrumentIds directly
    engine.add_strategy(strategy)

    engine.run()
    return engine


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


def _requires_margin_account(sleeves: list[tuple[SleeveName, ExecutionBundle]]) -> bool:
    return any(_bundle_direction(bundle) in {"both", "shortonly"} for _name, bundle in sleeves)


def _bundle_direction(bundle: object) -> str:
    plan = getattr(bundle, "plan", None) or getattr(bundle, "_plan", None)
    return str(getattr(plan, "direction", "longonly"))


def _account_currencies(
    base_currency: str,
    sleeves: list[tuple[SleeveName, ExecutionBundle]],
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
    figi: str,
    required_arrays: tuple[str, ...],
    min_rows: int,
) -> None:
    """Fail closed unless *ohlcv* satisfies the contract: every required array is
    present (matched case-insensitively against the provider's columns) and at
    least *min_rows* (lookback + 1) rows are available."""
    columns = {str(c).lower() for c in ohlcv.columns}
    missing = tuple(a for a in required_arrays if a.lower() not in columns)
    if missing:
        raise ContractDataError(sleeve, figi, f"missing required arrays {list(missing)}")
    if len(ohlcv) < min_rows:
        raise ContractDataError(
            sleeve, figi,
            f"{len(ohlcv)} rows fetched, need at least {min_rows} (lookback + 1)",
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


# -- default yfinance fetchers (provider-specific; injected, not core) -----------
#
# ``threads=False`` on every download: each call pulls a single ticker, so the
# download pool buys nothing, and its worker threads each open a connection to
# yfinance's peewee/sqlite timezone cache that yfinance's atexit hook never
# closes (it only closes the main thread's) — those leaked connections surface
# as ``ResourceWarning: unclosed database`` at GC time. Single-threaded downloads
# keep every tz-cache connection on the main thread, where it is closed cleanly.


def yfinance_ohlcv(request: BarRequest) -> pd.DataFrame:
    import yfinance as yf

    df = yf.download(
        request.ticker, start=request.start, end=request.end,
        auto_adjust=True, progress=False, threads=False,
    )
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def yfinance_fx(base: str, quote: str, start: str, end: str) -> pd.Series:
    import yfinance as yf

    df = yf.download(f"{base}{quote}=X", start=start, end=end, progress=False, threads=False)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.dropna()
