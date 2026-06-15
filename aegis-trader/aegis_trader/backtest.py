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

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Currency, Money

from aegis_runtime.currency import _major_currency_and_scale

from aegis_trader.bundles.port import BundleRegistryPort
from aegis_trader.bundles.registry import EntryPointBundleRegistry
from aegis_trader.config import load_book_config
from aegis_trader.data import (
    InstrumentSpec,
    build_equity,
    resolve_book_timeframe,
    wrangle_bars,
)
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
# (base, quote, start, end) -> quote units per 1 base (e.g. EUR,USD -> ~1.08).
FxFetcher = Callable[[str, str, str, str], float]

_PRICE_COLS = ("open", "high", "low", "close")


class ContractDataError(ValueError):
    """Fetched data does not satisfy a sleeve's DataContract — the backtest fails
    closed rather than running the overlay on data that wouldn't pass research."""

    def __init__(self, sleeve: str, figi: str, detail: str) -> None:
        self.sleeve = sleeve
        self.figi = figi
        super().__init__(f"sleeve {sleeve!r} ({figi}): {detail}")


def run_book_backtest(
    book_path: str,
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

    engine = BacktestEngine(build_backtest_engine_config(trader_id=trader_id))
    engine.add_venue(
        Venue(venue),
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=base,
        starting_balances=[Money(starting_cash, base)],
        book_type=BookType.L1_MBP,
    )

    bimap: dict[str, object] = {}
    fx_currencies: set[str] = set()
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
            engine.add_instrument(instrument)
            engine.add_data(wrangle_bars(instrument, ohlcv, book_timeframe))
            bimap[figi] = instrument.id

    for ccy in fx_currencies:
        if ccy == book.base_currency:
            continue
        rate = fetch_fx(book.base_currency, ccy, start, end)
        engine.cache.set_mark_xrate(base, Currency.from_str(ccy), rate)

    strategy = RebalanceStrategy(RebalanceStrategyConfig(book=book, fill_time_in_force=None))
    for name, bundle in sleeves:
        strategy.register_sleeve(name, bundle)
    strategy._figi_bimap = bimap  # backtest assigns InstrumentIds directly
    engine.add_strategy(strategy)

    engine.run()
    return engine


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


def yfinance_fx(base: str, quote: str, start: str, end: str) -> float:
    import yfinance as yf

    df = yf.download(f"{base}{quote}=X", start=start, end=end, progress=False, threads=False)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return float(close.dropna().iloc[-1])
