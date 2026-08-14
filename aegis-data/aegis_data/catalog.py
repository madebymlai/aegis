from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
from nautilus_trader.core.data import Data
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from platformdirs import user_data_dir

from aegis_data.bar_type import raw_bar_type
from aegis_data.definitions import (
    catalog_definitions,
    continuous_root_legs,
)
from aegis_data._distribution_verification import (
    DistributionDataProviderPort,
    distribution_coverage_report,
    ensure_distribution_window,
    read_distribution_window,
)
from aegis_data.distributions import Distribution, distribution_records
from aegis_data.instrument import native_multiplier, native_size_increment
from aegis_data.marking import DeclaredMarkingResolver, RawBarTypeResolver
from aegis_data.ohlcv import bars_to_ohlcv
from aegis_data.raw_bars import (
    GapFillProviderError,
    NautilusDataProviderPort,
    RawBars,
)
from aegis_data.roll import DatedContract
from aegis_data.storage import Catalog, CatalogInterval

if TYPE_CHECKING:
    from nautilus_trader.model.instruments import Instrument

AEGIS_DATA_DIR_ENV = "AEGIS_DATA_DIR"
CATALOG_DIRNAME = "catalog"


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
class CatalogWindowRequest:
    """One requested catalog window: which ids, over which edges (ADR-0012)."""

    instrument_ids: tuple[InstrumentId, ...]
    start: str
    end: str
    timeframe: str = "1D"


@dataclass(frozen=True)
class CatalogWindow:
    """One coherent catalog read: the requested window's run-constant facts (ADR-0012).

    OHLCV per requested id, complete definitions (guaranteed — the read fails
    loud naming every missing id before verification), native sizing facts,
    verified distributions, and their coverage report.
    """

    ohlcv: dict[InstrumentId, pd.DataFrame]
    instruments: dict[InstrumentId, "Instrument"]
    size_increment_by_instrument: dict[InstrumentId, float]
    multiplier_by_instrument: dict[InstrumentId, float]
    records: tuple[Data, ...]
    distribution_coverage: tuple[dict[str, Any], ...] = ()

    @property
    def distributions(self) -> tuple[Distribution, ...]:
        """Distribution records consumed by return and cash projections."""
        return distribution_records(self.records)


@dataclass(frozen=True)
class ResolvedContinuousRoot:
    instrument_id: InstrumentId
    legs: tuple[DatedContract, ...]


@dataclass(frozen=True)
class CatalogBackedDataPort:
    catalog: Catalog
    provider: NautilusDataProviderPort | None = None
    distribution_provider: DistributionDataProviderPort | None = None
    # Optional Step-1 definition write, fired only when warming reaches a client.
    # Definitions remain a separate, idempotent lifecycle from Bar write-back.
    definition_seeder: Callable[[InstrumentId], None] | None = None
    # The one raw bar-type resolution seam (aegis-rd-tggo): every mark/fill
    # read resolves its bar identity here, so a different marking policy plugs
    # in without reshaping the port.
    resolver: RawBarTypeResolver = DeclaredMarkingResolver()
    raw_bars: RawBars = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "raw_bars",
            RawBars(
                self.catalog,
                provider=self.provider,
                definition_seeder=self.definition_seeder,
                resolver=self.resolver,
            ),
        )

    def load_window(self, request: CatalogWindowRequest) -> CatalogWindow:
        """One coherent read of the requested window (ADR-0012).

        The internal ordering is contract, not style: Bar warming runs FIRST
        (a client request may seed the definition completeness needs), then
        definition completeness is judged before Distribution materialisation.
        """
        ohlcv = self._load_raw_bars(request)
        instruments = self._complete_definitions(request.instrument_ids)
        ensure_distribution_window(
            self.catalog,
            request.instrument_ids,
            start=request.start,
            end=request.end,
            provider=self.distribution_provider,
            raw_bars=self.raw_bars,
        )
        verified = read_distribution_window(
            self.catalog,
            request.instrument_ids,
            start=request.start,
            end=request.end,
            raw_bars=self.raw_bars,
        )
        return CatalogWindow(
            ohlcv=ohlcv,
            instruments=instruments,
            size_increment_by_instrument={
                instrument_id: native_size_increment(instrument)
                for instrument_id, instrument in instruments.items()
            },
            multiplier_by_instrument={
                instrument_id: native_multiplier(instrument)
                for instrument_id, instrument in instruments.items()
            },
            records=verified.records,
            distribution_coverage=verified.coverage,
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
        interval = _request_interval(request)
        for instrument_id in request.instrument_ids:
            marking = self.raw_bars.marking(instrument_id, request.timeframe)
            self.raw_bars.ensure(marking, interval)
            frames[instrument_id] = self.raw_bars.covered(marking, interval).ohlcv
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
        interval = _request_interval(request)
        for instrument_id in request.instrument_ids:
            marking = self.raw_bars.marking(instrument_id, request.timeframe)
            self.raw_bars.ensure(marking, interval)
            sided = self.raw_bars.covered(marking, interval).quote_ohlcv
            if sided is not None:
                frames[instrument_id] = sided
        return frames

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

    def size_increment_for(self, instrument_id: InstrumentId) -> float:
        """Return the native increment from one stored instrument definition."""

        definitions = self._complete_definitions((instrument_id,))
        return native_size_increment(definitions[instrument_id])

    def multiplier_for(self, instrument_id: InstrumentId) -> float:
        """Return the native multiplier from one stored instrument definition."""

        definitions = self._complete_definitions((instrument_id,))
        return native_multiplier(definitions[instrument_id])

    def continuous_size_increment(self, root: str) -> float:
        """Return the one native increment shared by a root's dated legs."""

        return self._continuous_instrument_fact(
            root,
            fact_name="size increments",
            extract=native_size_increment,
        )

    def continuous_multiplier(self, root: str) -> float:
        """Return the one native multiplier shared by a root's dated legs."""

        return self._continuous_instrument_fact(
            root,
            fact_name="multipliers",
            extract=native_multiplier,
        )

    def _continuous_instrument_fact(
        self,
        root: str,
        *,
        fact_name: str,
        extract: Callable[["Instrument"], float],
    ) -> float:
        """Resolve one run-constant native fact shared by all dated legs."""

        leg_ids = tuple(
            InstrumentId.from_str(leg.symbol)
            for leg in self.resolve_continuous(root).legs
        )
        definitions = self._complete_definitions(leg_ids)
        values = {extract(definitions[instrument_id]) for instrument_id in leg_ids}
        if len(values) != 1:
            raise ValueError(
                f"continuous-future root {root!r} has inconsistent native "
                f"{fact_name} across dated legs: {sorted(values)}"
            )
        return next(iter(values))

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
        return distribution_coverage_report(
            self.catalog,
            tuple(instrument_ids),
            start=start,
            end=end,
            raw_bars=self.raw_bars,
        )

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
        return ResolvedContinuousRoot(
            InstrumentId(Symbol(root), next(iter(venues))), legs
        )


def catalog_root(env: Mapping[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    base = values.get(AEGIS_DATA_DIR_ENV)
    if base is None:
        base = user_data_dir("aegis-data")
    return Path(base).expanduser() / CATALOG_DIRNAME


def resolve_catalog_path(path: str | Path | None = None) -> Path:
    """Resolve an explicit or configured catalog path without opening it."""
    return catalog_root() if path is None else Path(path).expanduser()


def open_catalog(path: str | Path | None = None) -> Catalog:
    return Catalog.open(resolve_catalog_path(path))


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
        historic_bar_client_factory,
        seed_instrument_definitions,
    )
    from aegis_data.research_bars import NautilusBarWarmer

    catalog = open_catalog(path)
    provider = IbkrHistoricalProvider()
    return CatalogBackedDataPort(
        catalog,
        provider=NautilusBarWarmer(catalog, historic_bar_client_factory(provider)),
        distribution_provider=provider,
        definition_seeder=lambda instrument_id: seed_instrument_definitions(
            catalog, provider, (instrument_id,)
        ),
        resolver=resolver if resolver is not None else DeclaredMarkingResolver(),
    )


def _request_interval(request: CatalogWindowRequest) -> CatalogInterval:
    return CatalogInterval(
        pd.Timestamp(request.start, tz="UTC").value,
        pd.Timestamp(request.end, tz="UTC").value,
    )


def _bar_cls() -> type:
    from nautilus_trader.model.data import Bar

    return Bar


__all__ = [
    "CatalogBackedDataPort",
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
    "bars_to_ohlcv",
    "catalog_data_port",
    "catalog_root",
    "open_catalog",
    "raw_bar_type",
]
