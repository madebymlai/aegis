from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from aegis_data.catalog import CatalogBackedDataPort, raw_bar_type
from aegis_data.marking import DeclaredMarkingResolver, MarkMode, RawBarTypeResolver
from aegis_data.testing import FakeCatalog
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair, Equity
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from research.aegis_research.configuration import DataConfig
from research.aegis_research.data import MarketDataResult
from research.aegis_research.market_data.adapters._support import (
    index_evidence,
    native_from_array_dict,
)
from research.aegis_research.market_data.contracts import MarketDataLoad

# The orchestrator's own assembly, crossed by leaf-altitude tests for
# hand-built loads — one owner for observe → judge → describe, no drift.
from research.aegis_research.market_data.loading import result_from_load

DEFAULT_INSTRUMENT_ID_VALUES = ("SYN.XNAS", "SYN2.XNAS")
ETF_INSTRUMENT_ID_VALUES = (
    "SPY.XNAS",
    "IWM.XNAS",
    "EEM.XNAS",
    "TLT.XNAS",
    "GLD.XNAS",
    "DBC.XNAS",
    "VNQ.XNAS",
    "UUP.XNAS",
    "XLE.XNAS",
    "XLU.XNAS",
)
OHLCV_ARRAY_NAMES = ("Open", "High", "Low", "Close", "Volume")


def instrument_id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def instrument_ids(values: Sequence[str]) -> tuple[InstrumentId, ...]:
    return tuple(instrument_id(value) for value in values)


def native_data_config_payload(
    *,
    instruments: Sequence[str] = ("SYN.XNAS",),
    arrays: Sequence[str] = ("OHLCV",),
    start: str = "2024-01-01",
    end: str = "2024-05-01",
    timeframe: str = "1D",
    base_currency: str = "EUR",
    path: str | Path | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "arrays": list(arrays),
        "base_currency": base_currency,
        "instruments": list(instruments),
        "start": start,
        "end": end,
        "timeframe": timeframe,
    }
    if path is not None:
        payload["path"] = str(path)
    payload.update(overrides)
    return payload


def deterministic_ohlcv_panels(
    instrument_id_values: Sequence[str],
    *,
    periods: int,
    start: str = "2024-01-01",
    seed: int = 0,
) -> dict[str, pd.DataFrame]:
    ids = instrument_ids(instrument_id_values)
    index = pd.date_range(start, periods=periods, freq="D")
    rng = np.random.default_rng(seed)
    drift = np.linspace(0.0001, 0.0008, len(ids))
    shocks = rng.normal(0.0, 0.01, size=(periods, len(ids)))
    close = 100.0 * np.exp(np.cumsum(drift + shocks, axis=0))
    open_ = close * (1.0 + rng.normal(0.0, 0.001, size=close.shape))
    high = np.maximum(open_, close) * 1.002
    low = np.minimum(open_, close) * 0.998
    volume = np.full(close.shape, 1_000.0)
    columns = pd.Index(ids, name="instrument_id")
    return {
        "Open": pd.DataFrame(open_, index=index, columns=columns),
        "High": pd.DataFrame(high, index=index, columns=columns),
        "Low": pd.DataFrame(low, index=index, columns=columns),
        "Close": pd.DataFrame(close, index=index, columns=columns),
        "Volume": pd.DataFrame(volume, index=index, columns=columns),
    }


def loaded_market_data_result(
    config: DataConfig,
    *,
    periods: int = 120,
    seed: int = 0,
) -> MarketDataResult:
    panels = deterministic_ohlcv_panels(
        config.instruments,
        periods=periods,
        start=config.start or "2024-01-01",
        seed=seed,
    )
    native_data = native_from_array_dict(
        {name: panels[name] for name in config.effective_arrays if name in panels},
        config,
    )
    return result_from_load(
        config,
        MarketDataLoad(
            native_data=native_data,
            evidence=index_evidence(panels["Close"].index, source="test_fixture"),
            port_metadata={"class": "tests.market_data_fixture"},
        ),
    )


class UnservableCatalog(FakeCatalog):
    """A catalog that reports every requested window as missing, so the real
    port's coverage gate judges it unservable (no provider wired: pure gap)."""

    def get_missing_intervals_for_request(
        self, start: int, end: int, *_args: object, **_kwargs: object
    ) -> list[tuple[int, int]]:
        return [(start, end)]


def unservable_port() -> CatalogBackedDataPort:
    """A real port over a catalog that cannot serve any window (no provider):
    every load ends in the coverage gate's verdict."""
    return CatalogBackedDataPort(UnservableCatalog(instruments=[], bars={}))


def seed_catalog_frames(
    catalog_path: Path,
    frames: dict[str, pd.DataFrame],
    *,
    start: str,
    end: str,
    currency: str = "USD",
) -> None:
    """Seed a real catalog from explicit per-instrument OHLCV frames.

    Unlike :func:`seed_catalog_ohlcv` the frames are the scenario — calendar
    gaps and custom values survive into the corpus — so port-altitude quality
    tests can stage real data defects behind the production port. Coverage is
    claimed over ``[start, end]`` and distribution coverage is verified with a
    zero-event source, so a warm read through ``CatalogBackedDataPort`` needs
    no provider.
    """
    catalog_path.mkdir(parents=True, exist_ok=True)
    catalog = ParquetDataCatalog(catalog_path)
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    close_panel = pd.DataFrame(
        {instrument_id(value): frame["Close"] for value, frame in frames.items()}
    )
    for value, frame in frames.items():
        current_id = instrument_id(value)
        catalog.write_data([equity_definition(current_id, currency)])
        bar_type = raw_bar_type(current_id, "1D")
        catalog.write_data(
            [
                _bar(
                    bar_type,
                    timestamp=timestamp,
                    open_=row["Open"],
                    high=row["High"],
                    low=row["Low"],
                    close=row["Close"],
                    volume=row["Volume"],
                )
                for timestamp, row in frame.iterrows()
            ],
            start=start_ts.value,
            end=end_ts.value,
        )
        _verify_zero_distribution_coverage(
            catalog,
            current_id,
            panels={"Close": close_panel},
            start=start_ts,
            end=end_ts,
        )


def seed_catalog_ohlcv(
    catalog_path: Path,
    instrument_id_values: Sequence[str],
    *,
    periods: int,
    start: str = "2024-01-01",
    seed: int = 0,
    currency: str = "EUR",
) -> tuple[str, str]:
    # A projection over seed_catalog_frames: deterministic panels become
    # per-instrument frames; one write-and-verify path serves both seeders.
    panels = deterministic_ohlcv_panels(
        instrument_id_values,
        periods=periods,
        start=start,
        seed=seed,
    )
    frames = {
        value: pd.DataFrame(
            {name: panels[name][instrument_id(value)] for name in OHLCV_ARRAY_NAMES}
        )
        for value in instrument_id_values
    }
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = start_ts + pd.Timedelta(days=periods)
    start_text = start_ts.date().isoformat()
    end_text = end_ts.date().isoformat()
    seed_catalog_frames(
        catalog_path, frames, start=start_text, end=end_text, currency=currency
    )
    return start_text, end_text


def seed_catalog_quote(
    catalog_path: Path,
    value: str,
    *,
    bid_frame: pd.DataFrame,
    ask_frame: pd.DataFrame,
    start: str,
    end: str,
    currency: str = "EUR",
) -> None:
    """Seed a quote-marked instrument: definition + BID and ASK daily bars.

    The thin-ETF corpus shape (aegis-rd-tggo.2): dense quotes, NO LAST series
    and NO stored MID bar — the mid is derived at read time by the marking.
    """
    catalog_path.mkdir(parents=True, exist_ok=True)
    catalog = ParquetDataCatalog(catalog_path)
    current_id = instrument_id(value)
    resolver = DeclaredMarkingResolver(declared={current_id: MarkMode.QUOTE})
    bid_type, ask_type = resolver.resolve(current_id, "1D").mark_bars
    catalog.write_data([equity_definition(current_id, currency)])
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    for bar_type, frame in ((bid_type, bid_frame), (ask_type, ask_frame)):
        catalog.write_data(
            [
                _bar(
                    bar_type,
                    timestamp=timestamp,
                    open_=row["Open"],
                    high=row["High"],
                    low=row["Low"],
                    close=row["Close"],
                    volume=row["Volume"],
                )
                for timestamp, row in frame.iterrows()
            ],
            start=start_ts.value,
            end=end_ts.value,
        )
    mid_close = (bid_frame["Close"] + ask_frame["Close"]) / 2.0
    _verify_zero_distribution_coverage(
        catalog,
        current_id,
        panels={"Close": pd.DataFrame({current_id: mid_close})},
        start=start_ts,
        end=end_ts,
        resolver=resolver,
    )


def _verify_zero_distribution_coverage(
    catalog: ParquetDataCatalog,
    instrument_id: InstrumentId,
    *,
    panels: dict[str, pd.DataFrame],
    start: pd.Timestamp,
    end: pd.Timestamp,
    resolver: RawBarTypeResolver | None = None,
) -> None:
    # ADR-0008: seeded synthetic catalogs must be self-describing for distributions
    # too, so RD integration tests stay warm and never query IBKR for fake symbols.
    # The verified read is the ensure (ADR-0010); the clock is pinned to the window
    # start so seeded corpora stay byte-deterministic.
    events = CatalogBackedDataPort(
        catalog,
        distribution_provider=_ZeroDistributionProvider(panels),
        clock_ns=lambda: start.value,
        resolver=resolver if resolver is not None else DeclaredMarkingResolver(),
    ).distributions((instrument_id,), start=start, end=end)
    assert not events, f"synthetic corpus grew distributions for {instrument_id.value}"


class _ZeroDistributionProvider:
    def __init__(self, panels: dict[str, pd.DataFrame]) -> None:
        self.panels = panels

    def request_adjusted_last(self, **kwargs: Any) -> pd.Series:
        close = self.panels["Close"][kwargs["instrument_id"]]
        adjusted_last = close.map(lambda value: float(_price(value)))
        adjusted_last.index = adjusted_last.index.tz_localize("UTC")
        return adjusted_last


def seed_catalog_fx(
    catalog_path: Path,
    pair_value: str = "EUR/USD.IDEALPRO",
    *,
    periods: int,
    start: str = "2024-01-01",
    base_rate: float = 1.10,
    drift: float = 0.0004,
) -> None:
    """Seed a moving FX ``CurrencyPair`` (definition + daily bars) for conversion.

    The rate drifts each bar so a converted book's *returns* (not just price levels)
    differ from the native book — a flat rate would cancel out of return metrics.
    """
    catalog_path.mkdir(parents=True, exist_ok=True)
    catalog = ParquetDataCatalog(catalog_path)
    pair_id = instrument_id(pair_value)
    catalog.write_data([currency_pair_definition(pair_id)])
    index = pd.date_range(start, periods=periods, freq="D")
    rates = base_rate * np.exp(np.arange(periods) * drift)
    bar_type = raw_bar_type(pair_id, "1D")
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = start_ts + pd.Timedelta(days=periods)
    catalog.write_data(
        [
            _bar(
                bar_type,
                timestamp=timestamp,
                open_=rate,
                high=rate,
                low=rate,
                close=rate,
                volume=1_000_000.0,
            )
            for timestamp, rate in zip(index, rates, strict=True)
        ],
        start=start_ts.value,
        end=end_ts.value,
    )


def equity_definition(instrument_id: InstrumentId, currency: str) -> Equity:
    return Equity(
        instrument_id=instrument_id,
        raw_symbol=Symbol(instrument_id.symbol.value),
        currency=Currency.from_str(currency),
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def currency_pair_definition(instrument_id: InstrumentId) -> CurrencyPair:
    base, quote = instrument_id.symbol.value.split("/")
    return CurrencyPair(
        instrument_id=instrument_id,
        raw_symbol=Symbol(instrument_id.symbol.value),
        base_currency=Currency.from_str(base),
        quote_currency=Currency.from_str(quote),
        price_precision=5,
        size_precision=0,
        price_increment=Price(1e-5, 5),
        size_increment=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def _bar(
    bar_type: BarType,
    *,
    timestamp: pd.Timestamp,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
) -> Bar:
    ts_event = pd.Timestamp(timestamp, tz="UTC").value
    return Bar(
        bar_type,
        Price.from_str(_price(open_)),
        Price.from_str(_price(high)),
        Price.from_str(_price(low)),
        Price.from_str(_price(close)),
        Quantity.from_str(str(int(volume))),
        ts_event,
        ts_event,
    )


def _price(value: float) -> str:
    return f"{max(value, 0.01):.2f}"
