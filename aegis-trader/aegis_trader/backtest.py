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

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.enums import AccountType, BookType, OmsType
from nautilus_trader.model.identifiers import TraderId, Venue
from nautilus_trader.model.objects import Currency, Money

from aegis_runtime.currency import _major_currency_and_scale

from aegis_trader.bundles.registry import EntryPointBundleRegistry
from aegis_trader.config import load_book_config
from aegis_trader.data import InstrumentSpec, build_equity, wrangle_daily_bars
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

# (ticker, start, end) -> OHLCV frame (native quote) with open/high/low/close/volume.
OhlcvFetcher = Callable[[str, str, str], pd.DataFrame]
# (base, quote, start, end) -> quote units per 1 base (e.g. EUR,USD -> ~1.08).
FxFetcher = Callable[[str, str, str, str], float]

_PRICE_COLS = ("open", "high", "low", "close")


def run_book_backtest(
    book_path: str,
    *,
    start: str,
    end: str,
    fetch_ohlcv: OhlcvFetcher,
    fetch_fx: FxFetcher,
    venue: str = "SIM",
    starting_cash: float = 1_000_000.0,
    trader_id: str = "BACKTEST-001",
) -> BacktestEngine:
    """Build and run the commingled-book backtest; returns the finished engine."""
    book = load_book_config(book_path)
    base = Currency.from_str(book.base_currency)
    registry = EntryPointBundleRegistry()
    sleeves = [(s.name, registry.load(s.wheel_filename)) for s in book.sleeves]

    engine = BacktestEngine(
        BacktestEngineConfig(trader_id=TraderId(trader_id), logging=LoggingConfig(bypass_logging=True))
    )
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
    for _name, bundle in sleeves:
        fx_currencies |= set(bundle.contract.required_fx_currencies)
        for figi, ticker in zip(bundle.contract.figis, bundle.symbols, strict=True):
            if figi in bimap:
                continue  # an instrument shared across sleeves is loaded once
            major, scale = _major_currency_and_scale(bundle.currency_by_symbol[ticker])
            instrument = build_equity(
                InstrumentSpec(figi=figi, venue=venue, quote_currency=major)
            )
            ohlcv = _normalize(fetch_ohlcv(ticker, start, end), scale)
            engine.add_instrument(instrument)
            engine.add_data(wrangle_daily_bars(instrument, ohlcv))
            bimap[figi] = instrument.id

    for ccy in fx_currencies:
        if ccy == book.base_currency:
            continue
        rate = fetch_fx(book.base_currency, ccy, start, end)
        quote = Currency.from_str(ccy)
        # Both directions: base->ccy sizes orders; ccy->base lets net_exposure
        # value a non-base position back into the book's base for realized weights.
        engine.cache.set_mark_xrate(base, quote, rate)
        engine.cache.set_mark_xrate(quote, base, 1.0 / rate)

    strategy = RebalanceStrategy(RebalanceStrategyConfig(book=book, fill_time_in_force=None))
    for name, bundle in sleeves:
        strategy.register_sleeve(name, bundle)
    strategy._figi_bimap = bimap  # backtest assigns InstrumentIds directly
    engine.add_strategy(strategy)

    engine.run()
    return engine


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


def yfinance_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def yfinance_fx(base: str, quote: str, start: str, end: str) -> float:
    import yfinance as yf

    df = yf.download(f"{base}{quote}=X", start=start, end=end, progress=False)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return float(close.dropna().iloc[-1])
