"""Catalog-backed proof that a sparse record interval was checked."""

from dataclasses import dataclass
from typing import Any

from nautilus_trader.core.data import Data
from nautilus_trader.model.custom import customdataclass
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data._ensure_coverage import CoverageInterval


@customdataclass
class _CoverageMarker(Data):
    """Two endpoint records representing one checked interval."""

    instrument_id: InstrumentId = InstrumentId.from_str("SPY.ARCA")
    record_type: str = ""
    start_ns: int = 0
    end_ns: int = 0
    checked_at_ns: int = 0
    applicable: bool = True


@dataclass(frozen=True)
class CoverageMarkerLedger:
    """Own the persisted checked-interval representation for sparse records."""

    catalog: Any

    def missing(
        self,
        record_type: type[Data],
        instrument_id: InstrumentId,
        interval: CoverageInterval,
    ) -> list[CoverageInterval]:
        return [
            CoverageInterval(start_ns, end_ns)
            for start_ns, end_ns in self.catalog.get_missing_intervals_for_request(
                interval.start_ns,
                interval.end_ns,
                _CoverageMarker,
                identifier=self.identifier(record_type, instrument_id),
            )
        ]

    def mark(
        self,
        record_type: type[Data],
        instrument_id: InstrumentId,
        interval: CoverageInterval,
        *,
        checked_at_ns: int,
        applicable: bool,
    ) -> None:
        points = (
            (interval.start_ns,)
            if interval.start_ns == interval.end_ns
            else (interval.start_ns, interval.end_ns)
        )
        markers = [
            _CoverageMarker(
                point,
                point,
                instrument_id=self._marker_instrument_id(record_type, instrument_id),
                record_type=record_type.__name__,
                start_ns=interval.start_ns,
                end_ns=interval.end_ns,
                checked_at_ns=checked_at_ns,
                applicable=applicable,
            )
            for point in points
        ]
        self.catalog.write_data(
            markers,
            data_cls=_CoverageMarker,
            identifier=self.identifier(record_type, instrument_id),
            start=interval.start_ns,
            end=interval.end_ns,
        )

    def checked_at_values(
        self,
        record_type: type[Data],
        instrument_id: InstrumentId,
        interval: CoverageInterval,
    ) -> list[int]:
        markers = self.catalog.query(
            _CoverageMarker,
            identifiers=[self.identifier(record_type, instrument_id)],
            start=interval.start_ns,
            end=interval.end_ns,
        )
        return [
            marker.checked_at_ns
            for item in markers
            for marker in [self._as_marker(item)]
            if marker.end_ns >= interval.start_ns
            and marker.start_ns <= interval.end_ns
        ]

    def consolidate(
        self,
        record_type: type[Data],
        instrument_id: InstrumentId,
        interval: CoverageInterval,
    ) -> None:
        self.catalog.consolidate_data(
            _CoverageMarker,
            identifier=self.identifier(record_type, instrument_id),
            start=interval.start_ns,
            end=interval.end_ns,
            deduplicate=True,
        )

    def delete(
        self,
        record_type: type[Data],
        instrument_id: InstrumentId,
        interval: CoverageInterval,
    ) -> None:
        self.catalog.delete_data_range(
            _CoverageMarker,
            identifier=self.identifier(record_type, instrument_id),
            start=interval.start_ns,
            end=interval.end_ns,
        )

    @staticmethod
    def identifier(record_type: type[Data], instrument_id: InstrumentId) -> str:
        return CoverageMarkerLedger._marker_instrument_id(
            record_type, instrument_id
        ).value

    @staticmethod
    def _marker_instrument_id(
        record_type: type[Data], instrument_id: InstrumentId
    ) -> InstrumentId:
        return InstrumentId.from_str(
            f"{record_type.__name__}-{instrument_id.symbol.value}."
            f"{instrument_id.venue.value}"
        )

    @staticmethod
    def _as_marker(item: object) -> _CoverageMarker:
        value = item.data if hasattr(item, "data") else item
        if not isinstance(value, _CoverageMarker):
            raise TypeError(
                "catalog returned "
                f"{type(value).__name__}, expected {_CoverageMarker.__name__}"
            )
        return value


__all__ = ["CoverageMarkerLedger"]
