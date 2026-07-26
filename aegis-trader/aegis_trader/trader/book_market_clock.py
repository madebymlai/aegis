"""Observed-market cadence for one Commingled Book."""

from __future__ import annotations

from aegis_data.bar_type import timeframe_to_ns
from aegis_data.marking import RawBarTypeResolver
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.bundles.book import AssembledBook
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.pipeline import CompletedRebalancePeriod, DueSleeve


class BookMarketClock:
    """Own the observed market periods and coalesced due set for one Book."""

    def __init__(
        self,
        *,
        book: AssembledBook,
        bar_type_resolver: RawBarTypeResolver,
    ) -> None:
        consumers: dict[BarType, dict[SleeveName, None]] = {}
        continuous_consumers: dict[InstrumentId, dict[SleeveName, None]] = {}
        for sleeve, streams in book.sleeve_streams.items():
            for stream in streams:
                marking = bar_type_resolver.resolve(
                    stream.instrument_id, stream.timeframe
                )
                for bar_type in marking.mark_bars:
                    consumers.setdefault(bar_type, {})[sleeve] = None
        for sleeve, bundle in book.sleeves.items():
            for continuous_id in bundle.contract.continuous_instrument_ids:
                continuous_consumers.setdefault(continuous_id, {})[sleeve] = None

        self._consumers = {
            bar_type: tuple(names) for bar_type, names in consumers.items()
        }
        self._continuous_consumers = {
            continuous_id: tuple(names)
            for continuous_id, names in continuous_consumers.items()
        }
        self._period_ns = {
            name: timeframe_to_ns(bundle.contract.timeframe)
            for name, bundle in book.sleeves.items()
        }
        self._current_period: dict[SleeveName, int | None] = {
            name: None for name in book.sleeves
        }
        self._pending_due: dict[SleeveName, CompletedRebalancePeriod] = {}

    def advance(
        self,
        bar_type: BarType,
        ts_ns: int,
        *,
        continuous_id: InstrumentId | None = None,
    ) -> None:
        """Fold one physical bar into every Sleeve whose market time it advances."""
        consumers = self._consumers.get(bar_type)
        if consumers is None and continuous_id is not None:
            consumers = self._continuous_consumers.get(continuous_id)
        for sleeve in consumers or ():
            self._advance_sleeve(sleeve, ts_ns)

    @property
    def has_pending_due(self) -> bool:
        """Whether at least one Sleeve completed a period since the last drain."""
        return bool(self._pending_due)

    def drain(self) -> tuple[DueSleeve, ...]:
        """Return the coalesced due set in Sleeve-name order and empty it."""
        due = tuple(
            DueSleeve(sleeve=sleeve, period=period)
            for sleeve, period in sorted(
                self._pending_due.items(), key=lambda item: item[0].value
            )
        )
        self._pending_due.clear()
        return due

    def _advance_sleeve(self, sleeve: SleeveName, timestamp_ns: int) -> None:
        period_ns = self._period_ns[sleeve]
        period = timestamp_ns // period_ns
        completed = self._current_period[sleeve]
        self._current_period[sleeve] = period
        if completed is None or period == completed:
            return
        self._pending_due[sleeve] = CompletedRebalancePeriod(
            period=completed,
            period_ns=period_ns,
        )
