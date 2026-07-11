from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
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
from aegis_data.marking import DeclaredMarkingResolver, RawBarTypeResolver
from aegis_data.ohlcv import bars_to_ohlcv
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


class MissingCatalogDefinitionsError(ValueError):
    """A window read requested ids with no stored catalog definition.

    An authoring error, never environmental: it names every missing id at
    once and is deliberately NOT the runtime currency package's
    missing-definition error — consumers must not collapse it into
    unavailability (ADR-0011/0012).
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
class CatalogWindowRequest:
    """One requested catalog window: which ids, over which edges (ADR-0012)."""

    instrument_ids: tuple[InstrumentId, ...]
    start: str
    end: str
    timeframe: str = "1D"


@dataclass(frozen=True)
class CatalogWindow:
    """One coherent catalog read: the requested window's run-constant facts (ADR-0012).

    OHLCV per requested id, the complete definitions (guaranteed — the read
    fails loud naming every missing id before any verification runs), the
    verified distributions, and the distribution coverage report (defaulted so
    consumers that never read it never mention it).
    """

    ohlcv: dict[InstrumentId, pd.DataFrame]
    instruments: dict[InstrumentId, "Instrument"]
    distributions: tuple[Distribution, ...]
    distribution_coverage: tuple[dict[str, Any], ...] = ()


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
    # The one raw bar-type resolution seam (aegis-rd-tggo): every mark/fill
    # read resolves its bar identity here, so a different marking policy plugs
    # in without reshaping the port.
    resolver: RawBarTypeResolver = DeclaredMarkingResolver()

    def load_window(self, request: CatalogWindowRequest) -> CatalogWindow:
        """One coherent read of the requested window (ADR-0012).

        The internal ordering is contract, not style: the bar coverage-gate /
        lazy-fill pass runs FIRST (a fill's Step-1 write may seed the very
        definition completeness needs), definition completeness is judged
        BEFORE distribution verification (a missing definition is an authoring
        fault and must never surface as the environmental coverage-gap error),
        and ONE verification pass serves both the returned distributions and
        the coverage report.
        """
        ohlcv = self._load_raw_bars(request)
        instruments = self._complete_definitions(request.instrument_ids)
        distribution_coverage = self._coverage_service().verify_window(
            request.instrument_ids, start=request.start, end=request.end
        )
        return CatalogWindow(
            ohlcv=ohlcv,
            instruments=instruments,
            distributions=query_distribution_data(
                self.catalog,
                request.instrument_ids,
                start=request.start,
                end=request.end,
            ),
            distribution_coverage=distribution_coverage,
        )

    def _complete_definitions(
        self, instrument_ids: tuple[InstrumentId, ...]
    ) -> dict[InstrumentId, Instrument]:
        definitions = catalog_definitions(self.catalog, instrument_ids)
        missing = [
            instrument_id.value
            for instrument_id in instrument_ids
            if instrument_id not in definitions
        ]
        if missing:
            raise MissingCatalogDefinitionsError(
                "the catalog window needs a stored definition for every requested "
                f"id, but the catalog is missing: {sorted(missing)}"
            )
        return definitions

    def _load_raw_bars(
        self, request: CatalogWindowRequest
    ) -> dict[InstrumentId, pd.DataFrame]:
        # Internal since ADR-0012's contraction: the window read and the
        # contract-leg OHLCV fetch are the only callers.
        frames: dict[InstrumentId, pd.DataFrame] = {}
        for instrument_id in request.instrument_ids:
            marking = self.resolver.resolve(instrument_id, request.timeframe)
            for bar_type in marking.mark_bars:
                self._ensure_covered(bar_type, request)
            # The marking owns the frame projection: a bar-marked instrument's
            # own OHLCV, a quote-marked instrument's derived bid/ask mid.
            frames[instrument_id] = marking.ohlcv_frame(
                {
                    bar_type: self._query_bars(bar_type, request)
                    for bar_type in marking.mark_bars
                }
            )
        return frames

    def load_quote_frames(
        self, request: CatalogWindowRequest
    ) -> dict[InstrumentId, tuple[pd.DataFrame, pd.DataFrame]]:
        """The ``(bid, ask)`` OHLCV frames for the quote-marked legs in *request*.

        The research fill projection's feed: a quote-marked instrument's two
        sided series, coverage-gated like the window read's bar pass; bar-marked legs
        are simply absent.  Live never reads this — the fill projection is
        derived research-side and never serialized (aegis-rd-tggo.5).
        """
        frames: dict[InstrumentId, tuple[pd.DataFrame, pd.DataFrame]] = {}
        for instrument_id in request.instrument_ids:
            marking = self.resolver.resolve(instrument_id, request.timeframe)
            for bar_type in marking.mark_bars:
                self._ensure_covered(bar_type, request)
            sided = marking.quote_ohlcv_frames(
                {
                    bar_type: self._query_bars(bar_type, request)
                    for bar_type in marking.mark_bars
                }
            )
            if sided is not None:
                frames[instrument_id] = sided
        return frames

    def read_native_bars(self, request: CatalogWindowRequest) -> dict[InstrumentId, list[Bar]]:
        """The window's stored native ``Bar``\\ s per instrument — a pure warm read.

        The single owner of the catalog ``Bar`` query (the window read's bar pass
        layers the coverage gate + OHLCV projection on top).  Unlike that pass it never
        fills: callers that already warmed the catalog (e.g. the continuous-future leg
        read after the chain fetch) get the fixed-point ``Bar``\\ s back, and a window
        past an instrument's life yields only the bars that exist, not a coverage error.
        """
        return {
            instrument_id: [
                bar
                for bar_type in self._mark_bars(instrument_id, request.timeframe)
                for bar in self._query_bars(bar_type, request)
            ]
            for instrument_id in request.instrument_ids
        }

    def _query_bars(self, bar_type: BarType, request: CatalogWindowRequest) -> list[Bar]:
        bars = self.catalog.query(
            _bar_cls(),
            identifiers=[str(bar_type)],
            start=request.start,
            end=request.end,
        )
        # Gap-fill serves overlapping yearly batches, so a dense series (BID/ASK) can
        # persist two bars for one ts_event at a batch boundary - the same trading day
        # fetched twice. Nautilus' identity dedupe keeps both when their values/ts_init
        # differ, so collapse to one bar per ts_event here (last wins): a sparse LAST
        # series has no boundary bar and is untouched, but a quote-derived frame must
        # have a unique index or its mid/reindex breaks downstream.
        by_ts_event: dict[int, Bar] = {bar.ts_event: bar for bar in bars}
        return [by_ts_event[ts_event] for ts_event in sorted(by_ts_event)]

    def _mark_bars(self, instrument_id: InstrumentId, timeframe: str) -> tuple[BarType, ...]:
        return self.resolver.resolve(instrument_id, timeframe).mark_bars

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

    def distribution_coverage_report(
        self,
        instrument_ids: Sequence[InstrumentId],
        *,
        start: str | int | pd.Timestamp | None = None,
        end: str | int | pd.Timestamp | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """The coverage diagnostic for ids OUTSIDE a window read (ADR-0012).

        The window read already carries its own report; this pure query serves
        ids that can never enter a window request — a continuous root has no
        raw bars, yet its not-applicable rows are real Run evidence.  An
        unresolvable id still fails loud.
        """
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
        request = CatalogWindowRequest(
            (instrument_id,), start.isoformat(), end.isoformat(), timeframe
        )
        return self._load_raw_bars(request)[instrument_id]

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
            self.catalog,
            self.distribution_provider,
            clock_ns=self.clock_ns,
            resolver=self.resolver,
        )

    def _ensure_covered(self, bar_type: BarType, request: CatalogWindowRequest) -> None:
        missing = self._missing_intervals(bar_type, request)
        if not missing:
            return
        if self.provider is None:
            raise _coverage_gap(bar_type, missing)
        for start_ns, end_ns in missing:
            with gap_fill_boundary(str(bar_type)):
                served = self.provider.request_bars(
                    bar_type,
                    start=pd.Timestamp(start_ns, tz="UTC"),
                    end=pd.Timestamp(end_ns, tz="UTC"),
                )
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
            with gap_fill_boundary(str(bar_type)):
                self.definition_seeder(bar_type.instrument_id)

    def _missing_intervals(
        self, bar_type: BarType, request: CatalogWindowRequest
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


def catalog_data_port(
    path: str | Path | None = None,
    *,
    resolver: RawBarTypeResolver | None = None,
) -> CatalogBackedDataPort:
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
        resolver=resolver if resolver is not None else DeclaredMarkingResolver(),
    )


# The persisted failure message is the port's interface: one bounded line in
# port vocabulary. The full vendor error rides only the chained cause (logs),
# never a shared Evidence artifact.
_CAUSE_SUMMARY_LIMIT = 200


@contextmanager
def gap_fill_boundary(subject: str) -> Iterator[None]:
    """The port's one translation rule for Ensure Coverage: a provider fault
    becomes :class:`GapFillProviderError` named by *subject*; the coverage
    gate's own verdicts pass through untouched."""
    try:
        yield
    except CatalogCoverageGapError:
        raise
    except Exception as exc:
        raise _gap_fill_failure(subject, exc) from exc


def _gap_fill_failure(subject: str, exc: Exception) -> GapFillProviderError:
    return GapFillProviderError(
        f"the gap-fill provider could not serve {subject}: "
        f"{type(exc).__name__}: {_cause_summary(exc)}"
    )


def _cause_summary(exc: Exception) -> str:
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    if len(first_line) <= _CAUSE_SUMMARY_LIMIT:
        return first_line
    return first_line[:_CAUSE_SUMMARY_LIMIT] + "…"


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


__all__ = [
    "CatalogBackedDataPort",
    "CatalogCoverageGapError",
    "CatalogWindow",
    "ContinuousRootLegsNotFoundError",
    "ContinuousRootVenueMismatchError",
    "Distribution",
    "DistributionDataProviderPort",
    "GapFillProviderError",
    "MissingCatalogDefinitionsError",
    "NautilusDataProviderPort",
    "CatalogWindowRequest",
    "ResolvedContinuousRoot",
    "ServedBars",
    "bars_to_ohlcv",
    "catalog_data_port",
    "catalog_root",
    "parquet_data_catalog",
    "raw_bar_type",
]
