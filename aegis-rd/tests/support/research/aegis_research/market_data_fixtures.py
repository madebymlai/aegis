from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from aegis_data.catalog import CatalogBackedDataPort, raw_bar_type
from aegis_data.testing import FakeCatalog
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair, Equity
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from research.aegis_research.configuration import DataConfig, merge_data_arrays
from research.aegis_research.data import MarketDataResult
from research.aegis_research.market_data.adapters._support import (
    index_evidence,
    native_from_array_dict,
)
from research.aegis_research.market_data.contracts import MarketDataLoad
from research.aegis_research.market_data.diagnostics import observe_source
from research.aegis_research.market_data.metadata import describe
from research.aegis_research.market_data.quality import evaluate

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


def result_from_load(
    config: DataConfig,
    load: MarketDataLoad,
    *,
    required_arrays: tuple[str, ...] | None = None,
) -> MarketDataResult:
    """Drive a hand-built load through the leaf modules — observe → judge →
    describe, the orchestrator's fixed sequence (ADR-0005).

    The seam for loader-unreachable shapes: scenarios the real catalog loader
    cannot emit (synthetic natives, custom index evidence, degenerate loads)
    are exercised against the leaf interfaces directly.  Loader-reachable
    scenarios belong at the port seam via ``load_market_data_result(port=...)``.
    """
    requested = config.effective_arrays
    required = merge_data_arrays(requested, required_arrays or ())
    observation, diagnostics = observe_source(config, load, requested_arrays=requested)
    quality = evaluate(
        config, diagnostics, required_arrays=required, index_evidence=load.evidence
    )
    metadata = describe(
        config,
        source=load,
        observation=observation,
        diagnostics=diagnostics,
        quality=quality,
        required_arrays=required,
    )
    return MarketDataResult(
        native_data=load.native_data,
        metadata=metadata,
        diagnostics=diagnostics,
        quality=quality,
        pnl_native_data=load.pnl_native_data,
        currency_conversion=load.currency_conversion,
        adjustment_mode=load.adjustment_mode,
        distributions=load.distributions,
    )


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
    catalog_path.mkdir(parents=True, exist_ok=True)
    catalog = ParquetDataCatalog(catalog_path)
    panels = deterministic_ohlcv_panels(
        instrument_id_values,
        periods=periods,
        start=start,
        seed=seed,
    )
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = start_ts + pd.Timedelta(days=periods)
    for current_id in instrument_ids(instrument_id_values):
        # The shared corpus holds a definition for every instrument with bars (ADR-0008);
        # currency conversion reads each leg's quote currency from it.
        catalog.write_data([equity_definition(current_id, currency)])
        bar_type = raw_bar_type(current_id, "1D")
        catalog.write_data(
            [
                _bar(
                    bar_type,
                    timestamp=timestamp,
                    open_=panels["Open"].at[timestamp, current_id],
                    high=panels["High"].at[timestamp, current_id],
                    low=panels["Low"].at[timestamp, current_id],
                    close=panels["Close"].at[timestamp, current_id],
                    volume=panels["Volume"].at[timestamp, current_id],
                )
                for timestamp in panels["Close"].index
            ],
            start=start_ts.value,
            end=end_ts.value,
        )
        _verify_zero_distribution_coverage(
            catalog,
            current_id,
            panels=panels,
            start=start_ts,
            end=end_ts,
        )
    return start_ts.date().isoformat(), end_ts.date().isoformat()


def _verify_zero_distribution_coverage(
    catalog: ParquetDataCatalog,
    instrument_id: InstrumentId,
    *,
    panels: dict[str, pd.DataFrame],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> None:
    # ADR-0008: seeded synthetic catalogs must be self-describing for distributions
    # too, so RD integration tests stay warm and never query IBKR for fake symbols.
    # The verified read is the ensure (ADR-0010); the clock is pinned to the window
    # start so seeded corpora stay byte-deterministic.
    events = CatalogBackedDataPort(
        catalog,
        distribution_provider=_ZeroDistributionProvider(panels),
        clock_ns=lambda: start.value,
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
