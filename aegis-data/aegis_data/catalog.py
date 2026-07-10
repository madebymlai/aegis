from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import FuturesContract
from platformdirs import user_data_dir

from aegis_data.bar_type import mic_canonical_instrument_id, raw_bar_type
from aegis_data.distributions import Distribution, query_distribution_data
from aegis_data.roll import DatedContract

if TYPE_CHECKING:
    from nautilus_trader.model.data import Bar, BarType
    from nautilus_trader.model.instruments import Instrument

    from aegis_data._distribution_coverage import DistributionCoverageService

AEGIS_DATA_DIR_ENV = "AEGIS_DATA_DIR"
CATALOG_DIRNAME = "catalog"


class CatalogCoverageGapError(ValueError):
    """Raised when the Nautilus catalog cannot serve the requested window."""


class GapFillProviderError(RuntimeError):
    """The Gap-Fill Provider failed environmentally during Ensure Coverage.

    The port's second environmental error (beside :class:`CatalogCoverageGapError`):
    a gateway drop, request timeout, or dead vendor call while filling a gap.  The
    port translates whatever the provider raised into this one type — no vendor
    error crosses the port contract — with the original chained as the cause.
    """


class ContinuousRootLegsNotFoundError(ValueError):
    """The catalog has no dated legs for a requested continuous root."""


class ContinuousRootVenueMismatchError(ValueError):
    """A continuous root's dated legs span more than one venue."""


@dataclass(frozen=True)
class ServedBars:
    """A provider's answer for one requested window.

    ``served_from`` is the oldest instant the provider verified against the
    source: the requested start when the whole window was walked, or the
    no-data wall when the instrument's history ended first (#75).  The port
    claims catalog coverage from ``served_from`` only — an empty head inside a
    verified window (weekend, holiday) is covered, while a pre-wall head stays
    missing so the coverage gate can judge it.
    """

    bars: tuple[Bar, ...]
    served_from: pd.Timestamp


class NautilusDataProviderPort(Protocol):
    """A pure fetch of bars for a window (ADR-0008): a query, never a write.

    The catalog's write format, ``EXTERNAL`` identity, window, and merge are the
    :class:`CatalogBackedDataPort`'s secret; it is the single writer of record.
    Answers with :class:`ServedBars` — the bars plus how far back the source's
    history actually reached — for the caller to persist.
    """

    def request_bars(
        self,
        bar_type: BarType,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ServedBars: ...


class DistributionDataProviderPort(Protocol):
    """Fetch the adjusted-last series needed to verify distribution coverage."""

    def request_adjusted_last(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
        currency: str = "USD",
    ) -> pd.Series: ...


@dataclass(frozen=True)
class RawBarRequest:
    instrument_ids: tuple[InstrumentId, ...]
    start: str
    end: str
    timeframe: str = "1D"


@dataclass(frozen=True)
class ResolvedContinuousRoot:
    instrument_id: InstrumentId
    legs: tuple[DatedContract, ...]


def continuous_root_legs(catalog: Any, root: str) -> tuple[DatedContract, ...]:
    """List a root's expiry-ordered dated legs from catalog definitions."""
    legs = [
        DatedContract(
            symbol=instrument.id.value,
            last_trade=instrument.expiration_utc.date(),
        )
        for instrument in catalog.instruments(instrument_type=FuturesContract)
        if instrument.underlying == root
    ]
    return tuple(sorted(legs, key=lambda leg: leg.last_trade))


def catalog_definitions(
    catalog: Any, instrument_ids: Sequence[InstrumentId]
) -> dict[InstrumentId, "Instrument"]:
    """Read stored definitions for *instrument_ids*, keyed by the id the caller asked for.

    The single owner of the definition storage-key rule: the IBKR provider stores each
    definition under its ISO MIC venue (``convert_exchange_to_mic_venue``), so the query
    is MIC-canonicalized — ``.LSE`` finds the ``.XLON`` definition — exactly as the bar
    read is (ADR-0005/#81).  Every definition read (the port, currency conversion,
    distribution coverage) goes through here so the rule lives in one place, and each hit
    is keyed back to the caller's authored id.
    """
    by_storage_key = {
        mic_canonical_instrument_id(instrument_id): instrument_id
        for instrument_id in instrument_ids
    }
    found = catalog.instruments(
        instrument_ids=[storage_key.value for storage_key in by_storage_key]
    )
    return {
        by_storage_key[instrument.id]: instrument
        for instrument in found
        if instrument.id in by_storage_key
    }


def _now_ns() -> int:
    return pd.Timestamp.now(tz="UTC").value


@dataclass(frozen=True)
class CatalogBackedDataPort:
    catalog: Any
    provider: NautilusDataProviderPort | None = None
    distribution_provider: DistributionDataProviderPort | None = None
    # Optional Step-1 definition write, fired only when a fill actually serves an
    # instrument (ADR-0008): the bar port stays pure-fetch — definitions are a
    # separate, idempotent lifecycle wired in by the caller, not a port method.
    definition_seeder: Callable[[InstrumentId], None] | None = None
    # The clock that stamps coverage markers' checked-at (ADR-0010): an injected
    # dependency, so deterministic callers cross this seam instead of building
    # the coverage service themselves.
    clock_ns: Callable[[], int] = _now_ns

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

    def instruments(
        self, instrument_ids: Sequence[InstrumentId]
    ) -> dict[InstrumentId, Instrument]:
        """Resolve native instrument definitions for *instrument_ids* from the catalog.

        A consumer (e.g. the currency-conversion view) derives each leg's quote
        currency from its resolved definition; this exposes that read as a port
        method instead of reaching past the port into its catalog.  MIC-canonicalized
        and keyed back to the caller's authored id — callers stay on their ids (#81).
        """
        return catalog_definitions(self.catalog, instrument_ids)

    def distributions(
        self,
        instrument_ids: Sequence[InstrumentId],
        *,
        start: str | int | pd.Timestamp | None = None,
        end: str | int | pd.Timestamp | None = None,
    ) -> tuple[Distribution, ...]:
        """Read stored cash distributions for instruments through the catalog port.

        The port owns the raw catalog query so consumers and fakes declare distribution
        behavior on the same interface they use for bars and definitions.
        """
        # ADR-0008: distributions cross the verified catalog port; direct catalog
        # reads are storage primitives, not research/trader data paths.
        self._coverage_service().ensure_covered(
            tuple(instrument_ids), start=start, end=end
        )
        return query_distribution_data(self.catalog, instrument_ids, start=start, end=end)

    def distribution_coverage_report(
        self,
        instrument_ids: Sequence[InstrumentId],
        *,
        start: str | int | pd.Timestamp | None = None,
        end: str | int | pd.Timestamp | None = None,
    ) -> tuple[dict[str, Any], ...]:
        return self._coverage_service().coverage_report(
            tuple(instrument_ids), start=start, end=end
        )

    def force_reverify_distribution_coverage(
        self,
        instrument_ids: Sequence[InstrumentId],
        *,
        start: str | int | pd.Timestamp,
        end: str | int | pd.Timestamp,
    ) -> None:
        self._coverage_service().force_reverify(
            tuple(instrument_ids), start=start, end=end
        )

    def fetch_contract_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        timeframe: str = "1D",
    ) -> pd.DataFrame:
        """Fetch one dated contract leg's OHLCV frame through the catalog port."""
        instrument_id = InstrumentId.from_str(symbol)
        request = RawBarRequest(
            (instrument_id,), start.isoformat(), end.isoformat(), timeframe
        )
        return self.load_raw_bars(request)[instrument_id]

    def probe_contract_volume(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        timeframe: str = "1D",
    ) -> pd.Series:
        """Read one dated contract leg's daily volume for liquidity leadership."""
        return self.fetch_contract_ohlcv(symbol, start, end, timeframe=timeframe)[
            "Volume"
        ]

    def resolve_continuous(self, root: str) -> ResolvedContinuousRoot:
        """Resolve a bare continuous root to its synthetic id and dated legs."""
        legs = continuous_root_legs(self.catalog, root)
        if not legs:
            raise ContinuousRootLegsNotFoundError(
                f"no dated legs in the catalog for continuous-future root {root!r}"
            )
        venues = {InstrumentId.from_str(leg.symbol).venue for leg in legs}
        if len(venues) != 1:
            raise ContinuousRootVenueMismatchError(
                f"continuous-future root {root!r} legs span multiple venues "
                f"{sorted(venue.value for venue in venues)}; expected one"
            )
        return ResolvedContinuousRoot(InstrumentId(Symbol(root), next(iter(venues))), legs)

    def _coverage_service(self) -> DistributionCoverageService:
        from aegis_data._distribution_coverage import DistributionCoverageService

        return DistributionCoverageService(
            self.catalog, self.distribution_provider, clock_ns=self.clock_ns
        )

    def _ensure_covered(self, bar_type: BarType, request: RawBarRequest) -> None:
        missing = self._missing_intervals(bar_type, request)
        if not missing:
            return
        if self.provider is None:
            raise _coverage_gap(bar_type, missing)
        for start_ns, end_ns in missing:
            try:
                served = self.provider.request_bars(
                    bar_type,
                    start=pd.Timestamp(start_ns, tz="UTC"),
                    end=pd.Timestamp(end_ns, tz="UTC"),
                )
            except Exception as exc:
                raise gap_fill_failure(str(bar_type), exc) from exc
            if served.bars:
                # Claim coverage only from where the source's history actually
                # reached (#75): a pre-wall head stays missing for the gate below,
                # while a fully walked interval is covered edge to edge even where
                # no bars trade (weekends, holidays).
                self.catalog.write_data(
                    list(served.bars),
                    start=max(start_ns, served.served_from.value),
                    end=end_ns,
                )
        self.catalog.consolidate_data(
            _bar_cls(), identifier=str(bar_type), deduplicate=True
        )
        remaining = self._missing_intervals(bar_type, request)
        if remaining:
            raise _coverage_gap(bar_type, remaining)
        # The fill served this instrument's bars; persist its definition too so the
        # shared corpus never holds bars without a definition (ADR-0008).
        if self.definition_seeder is not None:
            try:
                self.definition_seeder(bar_type.instrument_id)
            except Exception as exc:
                raise gap_fill_failure(str(bar_type), exc) from exc

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
        distribution_provider=provider,
        definition_seeder=lambda instrument_id: seed_instrument_definitions(
            catalog, provider, (instrument_id,)
        ),
    )


def gap_fill_failure(subject: str, exc: Exception) -> GapFillProviderError:
    """The port-level translation of a provider fault, named by its subject."""
    return GapFillProviderError(
        f"the gap-fill provider could not serve {subject}: "
        f"{type(exc).__name__}: {exc}"
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
    "ContinuousRootLegsNotFoundError",
    "ContinuousRootVenueMismatchError",
    "Distribution",
    "DistributionDataProviderPort",
    "GapFillProviderError",
    "NautilusDataProviderPort",
    "RawBarRequest",
    "ResolvedContinuousRoot",
    "ServedBars",
    "bars_to_ohlcv",
    "catalog_data_port",
    "catalog_root",
    "parquet_data_catalog",
    "raw_bar_type",
]
