"""Distribution-coverage verification: internal to the Catalog port (ADR-0010).

The marker ledger, applicability rules, and gap verification behind
``CatalogBackedDataPort``'s verified distribution reads.  Only the port
constructs the service; every other caller — production, tests, fixtures —
crosses the port's interface.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

import pandas as pd
from nautilus_trader.core.data import Data
from nautilus_trader.model.custom import customdataclass
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair, FuturesContract

from aegis_data.marking import DeclaredMarkingResolver, RawBarTypeResolver
from aegis_data.catalog import (
    CatalogCoverageGapError,
    DistributionDataProviderPort,
    catalog_definitions,
    continuous_root_legs,
    gap_fill_boundary,
)
from aegis_data.distributions import (
    query_distribution_data,
    replace_distribution_data,
    request_distribution_data,
)

_NANOS_PER_DAY = 86_400_000_000_000


@customdataclass
class DistributionCoverageMarker(Data):
    """Catalog interval marker proving a distribution window was checked."""

    instrument_id: InstrumentId = InstrumentId.from_str("SPY.ARCA")
    applicable: bool = True
    checked_at_ns: int = 0
    event_count: int = 0

    @classmethod
    def schema(cls) -> Any:
        return cls._schema


@dataclass(frozen=True)
class DistributionCoverageService:
    catalog: Any
    provider: DistributionDataProviderPort | None = None
    clock_ns: Callable[[], int] = field(kw_only=True)
    resolver: RawBarTypeResolver = field(kw_only=True, default=DeclaredMarkingResolver())

    def ensure_covered(
        self,
        instrument_ids: tuple[InstrumentId, ...],
        *,
        start: str | int | pd.Timestamp | None,
        end: str | int | pd.Timestamp | None,
    ) -> None:
        if start is None or end is None:
            raise CatalogCoverageGapError(
                "distribution coverage verification requires a bounded start and end"
            )
        request_start = _timestamp_ns(start)
        request_end = _timestamp_ns(end)
        failures: list[str] = []
        provider = _usable_provider(self.provider)
        for instrument_id in _dedupe(instrument_ids):
            applicability = self._applicability(instrument_id)
            coverage_end = request_end
            if applicability.applicable:
                coverage_end = self._clamped_to_bar_frontier(
                    instrument_id, start_ns=request_start, end_ns=request_end
                )
            missing = self._missing(instrument_id, request_start, coverage_end)
            if not missing:
                continue
            if not applicability.applicable:
                self._write_marker(
                    instrument_id,
                    start_ns=request_start,
                    end_ns=request_end,
                    applicable=False,
                    event_count=0,
                )
                continue
            if provider is None:
                failures.append(_gap_message(instrument_id, missing))
                continue
            for start_ns, end_ns in missing:
                self._verify_gap(
                    provider,
                    instrument_id,
                    definition=applicability.definition,
                    start_ns=start_ns,
                    end_ns=end_ns,
                )
        if failures:
            raise CatalogCoverageGapError(
                "distribution coverage is missing for "
                + "; ".join(sorted(failures))
            )

    def coverage_report(
        self,
        instrument_ids: tuple[InstrumentId, ...],
        *,
        start: str | int | pd.Timestamp | None,
        end: str | int | pd.Timestamp | None,
    ) -> tuple[dict[str, Any], ...]:
        if start is None or end is None:
            return ()
        request_start = _timestamp_ns(start)
        request_end = _timestamp_ns(end)
        reports: list[dict[str, Any]] = []
        for instrument_id in _dedupe(instrument_ids):
            applicability = self._applicability(instrument_id)
            coverage_end = request_end
            if applicability.applicable:
                coverage_end = self._clamped_to_bar_frontier(
                    instrument_id, start_ns=request_start, end_ns=request_end
                )
            reports.append(
                {
                    "instrument_id": instrument_id.value,
                    "applicable": applicability.applicable,
                    "verified_start": _timestamp_text(request_start),
                    "verified_end": _timestamp_text(coverage_end),
                    "event_count": self._event_count(
                        instrument_id,
                        start_ns=request_start,
                        end_ns=coverage_end,
                    )
                    if applicability.applicable
                    else 0,
                    "checked_at": self._checked_at(
                        instrument_id,
                        start_ns=request_start,
                        end_ns=coverage_end,
                    ),
                }
            )
        return tuple(reports)

    def force_reverify(
        self,
        instrument_ids: tuple[InstrumentId, ...],
        *,
        start: str | int | pd.Timestamp,
        end: str | int | pd.Timestamp,
    ) -> None:
        provider = _usable_provider(self.provider)
        if provider is None:
            raise CatalogCoverageGapError(
                "distribution force-reverify requires an adjusted-last provider"
            )
        start_ns = _timestamp_ns(start)
        end_ns = _timestamp_ns(end)
        for instrument_id in _dedupe(instrument_ids):
            applicability = self._applicability(instrument_id)
            self.catalog.delete_data_range(
                DistributionCoverageMarker,
                identifier=instrument_id.value,
                start=start_ns,
                end=end_ns,
            )
            if not applicability.applicable:
                self._write_marker(
                    instrument_id,
                    start_ns=start_ns,
                    end_ns=end_ns,
                    applicable=False,
                    event_count=0,
                )
                continue
            self._verify_gap(
                provider,
                instrument_id,
                definition=applicability.definition,
                start_ns=start_ns,
                end_ns=end_ns,
            )

    def _applicability(self, instrument_id: InstrumentId) -> "_Applicability":
        definition = catalog_definitions(self.catalog, [instrument_id]).get(instrument_id)
        if definition is not None:
            # A futures contract carries no distributions; a cash FX pair is a
            # conversion leg, not an income-bearing asset. Both are routine in
            # a window's id set, so neither is an error (they mark not-applicable).
            if isinstance(definition, (FuturesContract, CurrencyPair)):
                return _Applicability.not_applicable()
            return _Applicability.applicable_to(definition)
        if continuous_root_legs(self.catalog, instrument_id.symbol.value):
            return _Applicability.not_applicable()
        raise CatalogCoverageGapError(
            "distribution coverage cannot resolve catalog definitions for "
            f"{instrument_id.value}"
        )

    def _missing(
        self,
        instrument_id: InstrumentId,
        start_ns: int,
        end_ns: int,
    ) -> list[tuple[int, int]]:
        return self.catalog.get_missing_intervals_for_request(
            start_ns,
            end_ns,
            DistributionCoverageMarker,
            identifier=instrument_id.value,
        )

    def _markers_for_interval(
        self,
        instrument_id: InstrumentId,
        *,
        start_ns: int,
        end_ns: int,
    ) -> list[DistributionCoverageMarker]:
        markers = [
            _as_marker(item)
            for item in self.catalog.query(
                DistributionCoverageMarker,
                identifiers=[instrument_id.value],
                start=start_ns,
                end=end_ns,
            )
        ]
        if not markers:
            raise CatalogCoverageGapError(
                "distribution coverage marker interval has no marker row for "
                f"{instrument_id.value} in {_range_text(start_ns, end_ns)}"
            )
        return markers

    def _verify_gap(
        self,
        provider: DistributionDataProviderPort,
        instrument_id: InstrumentId,
        *,
        definition: Any,
        start_ns: int,
        end_ns: int,
    ) -> None:
        decode_start_ns = _decode_start_ns(start_ns)
        trades = self._trade_closes(instrument_id, decode_start_ns, end_ns)
        if len(trades) < 2:
            raise CatalogCoverageGapError(
                "distribution coverage cannot verify "
                f"{instrument_id.value}: fewer than two TRADES closes in "
                f"{_range_text(start_ns, end_ns)}"
            )
        # No vendor type crosses the port: an adjusted-last fetch fault during
        # Ensure Coverage is the same environmental failure as a bar-fill fault.
        with gap_fill_boundary(f"distributions for {instrument_id.value}"):
            events = request_distribution_data(
                provider,
                instrument_id,
                trades=trades,
                start=pd.Timestamp(decode_start_ns, tz="UTC"),
                end=pd.Timestamp(end_ns, tz="UTC"),
                currency=_definition_currency(definition),
            )
        replace_distribution_data(
            self.catalog,
            instrument_id,
            events,
            start=start_ns,
            end=end_ns,
        )
        self._write_marker(
            instrument_id,
            start_ns=start_ns,
            end_ns=end_ns,
            applicable=True,
            event_count=len(events),
        )

    def _trade_closes(
        self,
        instrument_id: InstrumentId,
        start_ns: int,
        end_ns: int,
    ) -> pd.Series:
        # The marking owns the close projection: a bar-marked instrument's own
        # closes, a quote-marked instrument's derived bid/ask mid — the same
        # series the corpus serves, so decode compares like with like.
        marking = self.resolver.resolve(instrument_id, "1D")
        return marking.ohlcv_frame(
            {
                bar_type: self._bars_for(bar_type, start_ns, end_ns)
                for bar_type in marking.mark_bars
            }
        )["Close"]

    def _clamped_to_bar_frontier(
        self,
        instrument_id: InstrumentId,
        *,
        start_ns: int,
        end_ns: int,
    ) -> int:
        bars = self._bars(instrument_id, start_ns, end_ns)
        if not bars:
            return end_ns
        frontier = max(bar.ts_event for bar in bars) + _NANOS_PER_DAY
        return min(end_ns, frontier)

    def _bars(
        self,
        instrument_id: InstrumentId,
        start_ns: int,
        end_ns: int,
    ) -> list[Any]:
        return [
            bar
            for bar_type in self.resolver.resolve(instrument_id, "1D").mark_bars
            for bar in self._bars_for(bar_type, start_ns, end_ns)
        ]

    def _bars_for(self, bar_type: Any, start_ns: int, end_ns: int) -> list[Any]:
        from nautilus_trader.model.data import Bar

        return list(
            self.catalog.query(
                Bar,
                identifiers=[str(bar_type)],
                start=start_ns,
                end=end_ns,
            )
        )

    def _write_marker(
        self,
        instrument_id: InstrumentId,
        *,
        start_ns: int,
        end_ns: int,
        applicable: bool,
        event_count: int,
        checked_at_ns: int | None = None,
    ) -> None:
        checked_at_ns = self.clock_ns() if checked_at_ns is None else checked_at_ns
        marker_points = (start_ns,) if start_ns == end_ns else (start_ns, end_ns)
        markers = [
            DistributionCoverageMarker(
                point,
                point,
                instrument_id=instrument_id,
                applicable=applicable,
                checked_at_ns=checked_at_ns,
                event_count=event_count,
            )
            for point in marker_points
        ]
        self.catalog.write_data(
            markers,
            data_cls=DistributionCoverageMarker,
            identifier=instrument_id.value,
            start=start_ns,
            end=end_ns,
        )

    def _event_count(
        self,
        instrument_id: InstrumentId,
        *,
        start_ns: int,
        end_ns: int,
    ) -> int:
        return len(
            query_distribution_data(
                self.catalog,
                (instrument_id,),
                start=start_ns,
                end=end_ns,
            )
        )

    def _checked_at(
        self,
        instrument_id: InstrumentId,
        *,
        start_ns: int,
        end_ns: int,
    ) -> str | None:
        checked_at_values: list[int] = []
        for marker_start, marker_end in self.catalog.get_intervals(
            DistributionCoverageMarker,
            identifier=instrument_id.value,
        ):
            if marker_end < start_ns or marker_start > end_ns:
                continue
            checked_at_values.extend(
                marker.checked_at_ns
                for marker in self._markers_for_interval(
                    instrument_id,
                    start_ns=marker_start,
                    end_ns=marker_end,
                )
            )
        if not checked_at_values:
            return None
        return _timestamp_text(min(checked_at_values))


@dataclass(frozen=True)
class _Applicability:
    applicable: bool
    definition: Any | None = None

    @classmethod
    def applicable_to(cls, definition: Any) -> "_Applicability":
        return cls(True, definition)

    @classmethod
    def not_applicable(cls) -> "_Applicability":
        return cls(False)


def _dedupe(instrument_ids: tuple[InstrumentId, ...]) -> tuple[InstrumentId, ...]:
    return tuple(dict.fromkeys(instrument_ids))


def _usable_provider(provider: Any) -> DistributionDataProviderPort | None:
    if provider is None or not hasattr(provider, "request_adjusted_last"):
        return None
    return cast(DistributionDataProviderPort, provider)


def _definition_currency(definition: Any) -> str:
    currency = getattr(definition, "currency", None)
    if currency is None:
        currency = getattr(definition, "quote_currency", None)
    if currency is None:
        raise CatalogCoverageGapError(
            f"distribution coverage needs a currency on {definition.id.value}"
        )
    return str(currency).upper()


def _timestamp_ns(value: str | int | pd.Timestamp) -> int:
    if isinstance(value, int):
        return value
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.value


def _timestamp_text(value: int) -> str:
    return pd.Timestamp(value, tz="UTC").isoformat()


def _as_marker(item: Any) -> DistributionCoverageMarker:
    return item.data if hasattr(item, "data") else item


def _decode_start_ns(start_ns: int) -> int:
    return pd.Timestamp(start_ns, tz="UTC").normalize().value


def _gap_message(
    instrument_id: InstrumentId, intervals: list[tuple[int, int]]
) -> str:
    return f"{instrument_id.value} missing={[_range_text(start, end) for start, end in intervals]}"


def _range_text(start_ns: int, end_ns: int) -> str:
    return (
        f"{pd.Timestamp(start_ns, tz='UTC').isoformat()}.."
        f"{pd.Timestamp(end_ns, tz='UTC').isoformat()}"
    )


