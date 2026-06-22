from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
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

    def load_raw_bars(self, request: RawBarRequest) -> dict[InstrumentId, pd.DataFrame]:
        frames: dict[InstrumentId, pd.DataFrame] = {}
        for instrument_id in request.instrument_ids:
            bar_type = raw_bar_type(instrument_id, request.timeframe)
            self._ensure_covered(bar_type, request)
            frames[instrument_id] = _bars_to_ohlcv(
                self.catalog.query(
                    _bar_cls(),
                    identifiers=[str(bar_type)],
                    start=request.start,
                    end=request.end,
                )
            )
        return frames

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


def _bars_to_ohlcv(bars: Sequence[Any]) -> pd.DataFrame:
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
    "catalog_root",
    "parquet_data_catalog",
    "raw_bar_type",
]
