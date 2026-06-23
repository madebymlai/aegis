from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId
from platformdirs import user_data_dir

from aegis_data.bar_type import raw_bar_type

if TYPE_CHECKING:
    from nautilus_trader.model.data import Bar, BarType

AEGIS_DATA_DIR_ENV = "AEGIS_DATA_DIR"
CATALOG_DIRNAME = "catalog"


class CatalogCoverageGapError(ValueError):
    """Raised when the Nautilus catalog cannot serve the requested window."""


class NautilusDataProviderPort(Protocol):
    """A pure fetch of bars for a window (ADR-0008): a query, never a write.

    The catalog's write format, ``EXTERNAL`` identity, window, and merge are the
    :class:`CatalogBackedDataPort`'s secret; it is the single writer of record.
    Mirrors Nautilus's standalone ``HistoricInteractiveBrokersClient``, which
    *returns* bars for the caller to persist.
    """

    def request_bars(
        self,
        bar_type: BarType,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> Sequence[Bar]: ...


@dataclass(frozen=True)
class RawBarRequest:
    instrument_ids: tuple[InstrumentId, ...]
    start: str
    end: str
    timeframe: str = "1D"


@dataclass(frozen=True)
class CatalogBackedDataPort:
    catalog: Any
    provider: NautilusDataProviderPort | None = None
    # Optional Step-1 definition write, fired only when a fill actually serves an
    # instrument (ADR-0008): the bar port stays pure-fetch — definitions are a
    # separate, idempotent lifecycle wired in by the caller, not a port method.
    definition_seeder: Callable[[InstrumentId], None] | None = None

    def load_raw_bars(self, request: RawBarRequest) -> dict[InstrumentId, pd.DataFrame]:
        for instrument_id in request.instrument_ids:
            self._ensure_covered(raw_bar_type(instrument_id, request.timeframe), request)
        return {
            instrument_id: bars_to_ohlcv(bars)
            for instrument_id, bars in self.read_native_bars(request).items()
        }

    def read_native_bars(self, request: RawBarRequest) -> dict[InstrumentId, list[Bar]]:
        """The window's stored native ``Bar``\\ s per instrument — a pure warm read.

        The single owner of the catalog ``Bar`` query (``load_raw_bars`` layers the
        coverage gate + OHLCV projection on top).  Unlike ``load_raw_bars`` it never
        fills: callers that already warmed the catalog (e.g. the continuous-future leg
        read after the chain fetch) get the fixed-point ``Bar``\\ s back, and a window
        past an instrument's life yields only the bars that exist, not a coverage error.
        """
        return {
            instrument_id: list(
                self.catalog.query(
                    _bar_cls(),
                    identifiers=[str(raw_bar_type(instrument_id, request.timeframe))],
                    start=request.start,
                    end=request.end,
                )
            )
            for instrument_id in request.instrument_ids
        }

    def _ensure_covered(self, bar_type: BarType, request: RawBarRequest) -> None:
        missing = self._missing_intervals(bar_type, request)
        if not missing:
            return
        if self.provider is None:
            raise _coverage_gap(bar_type, missing)
        for start_ns, end_ns in missing:
            pulled = self.provider.request_bars(
                bar_type,
                start=pd.Timestamp(start_ns, tz="UTC"),
                end=pd.Timestamp(end_ns, tz="UTC"),
            )
            if pulled:
                self.catalog.write_data(list(pulled), start=start_ns, end=end_ns)
        self.catalog.consolidate_data(
            _bar_cls(), identifier=str(bar_type), deduplicate=True
        )
        remaining = self._missing_intervals(bar_type, request)
        if remaining:
            raise _coverage_gap(bar_type, remaining)
        # The fill served this instrument's bars; persist its definition too so the
        # shared corpus never holds bars without a definition (ADR-0008).
        if self.definition_seeder is not None:
            self.definition_seeder(bar_type.instrument_id)

    def _missing_intervals(
        self, bar_type: BarType, request: RawBarRequest
    ) -> list[tuple[int, int]]:
        return self.catalog.get_missing_intervals_for_request(
            _timestamp_ns(request.start),
            _timestamp_ns(request.end),
            _bar_cls(),
            identifier=str(bar_type),
        )


def catalog_root(env: Mapping[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    base = values.get(AEGIS_DATA_DIR_ENV)
    if base is None:
        base = user_data_dir("aegis-data")
    return Path(base).expanduser() / CATALOG_DIRNAME


def parquet_data_catalog(path: str | Path | None = None) -> Any:
    root = catalog_root() if path is None else Path(path).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    from nautilus_trader.persistence.catalog import ParquetDataCatalog

    return ParquetDataCatalog(root)


def catalog_data_port(path: str | Path | None = None) -> CatalogBackedDataPort:
    """The standard catalog-backed data port (ADR-0006/0008).

    Composition lives here — in the package that owns both the port *and* the IBKR
    adapter — so callers depend only on the :class:`CatalogBackedDataPort`
    abstraction (DIP) and never name the concrete provider.  A backfill fills bars
    from IBKR and persists the instrument definition (an idempotent Step-1 write);
    a warm read never connects.  The IBKR adapter is imported lazily so this port
    module stays adapter-agnostic at import time.
    """
    from aegis_data.ibkr import (
        IbkrHistoricalProvider,
        seed_instrument_definitions,
    )

    catalog = parquet_data_catalog(path)
    provider = IbkrHistoricalProvider()
    return CatalogBackedDataPort(
        catalog,
        provider=provider,
        definition_seeder=lambda instrument_id: seed_instrument_definitions(
            catalog, provider, (instrument_id,)
        ),
    )


def _coverage_gap(
    bar_type: BarType, intervals: Sequence[tuple[int, int]]
) -> CatalogCoverageGapError:
    ranges = [
        f"{pd.Timestamp(start, tz='UTC').isoformat()}..{pd.Timestamp(end, tz='UTC').isoformat()}"
        for start, end in intervals
    ]
    return CatalogCoverageGapError(
        f"catalog cannot serve {bar_type} for requested window; missing={ranges}"
    )


def _timestamp_ns(value: str) -> int:
    return pd.Timestamp(value, tz="UTC").value


def _bar_cls() -> type:
    from nautilus_trader.model.data import Bar

    return Bar


def bars_to_ohlcv(bars: Sequence[Any]) -> pd.DataFrame:
    """Project native ``Bar``\\ s into the corpus OHLCV frame (UTC-naive index, float
    columns).  The single home for the Bar→OHLCV column shape, shared by the port's
    ``load_raw_bars`` and the continuous-future composer."""
    rows: dict[str, list[float]] = {
        "Open": [],
        "High": [],
        "Low": [],
        "Close": [],
        "Volume": [],
    }
    index: list[pd.Timestamp] = []
    for bar in bars:
        index.append(pd.Timestamp(bar.ts_event, tz="UTC").tz_localize(None))
        rows["Open"].append(float(bar.open.as_double()))
        rows["High"].append(float(bar.high.as_double()))
        rows["Low"].append(float(bar.low.as_double()))
        rows["Close"].append(float(bar.close.as_double()))
        rows["Volume"].append(float(bar.volume.as_double()))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index)).sort_index()


__all__ = [
    "CatalogBackedDataPort",
    "CatalogCoverageGapError",
    "NautilusDataProviderPort",
    "RawBarRequest",
    "bars_to_ohlcv",
    "catalog_data_port",
    "catalog_root",
    "parquet_data_catalog",
    "raw_bar_type",
]
