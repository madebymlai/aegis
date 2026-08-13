"""Catalog-backed proof that a sparse record interval was checked."""

from dataclasses import dataclass
from nautilus_trader.core.data import Data
from nautilus_trader.model.custom import customdataclass
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data._ensure_coverage import CoverageInterval
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey


_COVERAGE_DATASET_ID = InstrumentId.from_str("COVERAGE.AEGIS")


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

    catalog: Catalog

    def missing(
        self,
        subject: CatalogKey[Data],
        interval: CoverageInterval,
    ) -> list[CoverageInterval]:
        """The parts of *interval* no claim answers for.

        Answered from the claims themselves, which carry the interval they
        checked. How those claims are laid out in files is a storage concern
        and decides nothing: merging two files cannot invent a checked day,
        and splitting one cannot lose it.
        """
        remaining = [interval]
        for marker in self.catalog.read_all(self._key(subject)):
            claim = CoverageInterval(marker.start_ns, marker.end_ns)
            remaining = [
                residual
                for pending in remaining
                for residual in _subtract(pending, claim)
            ]
        return sorted(remaining, key=lambda gap: gap.start_ns)

    def mark(
        self,
        subject: CatalogKey[Data],
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
                instrument_id=_COVERAGE_DATASET_ID,
                record_type=subject.record_type.__name__,
                start_ns=interval.start_ns,
                end_ns=interval.end_ns,
                checked_at_ns=checked_at_ns,
                applicable=applicable,
            )
            for point in points
        ]
        self.catalog.replace(
            self._key(subject),
            CatalogInterval(interval.start_ns, interval.end_ns),
            tuple(markers),
        )

    def claim_missing(
        self,
        subject: CatalogKey[Data],
        window: CoverageInterval,
        *,
        checked_at_ns: int,
        applicable: bool,
    ) -> None:
        """Claim whatever part of *window* no claim answers for yet.

        Exactly the missing intervals are marked, never the whole window: a
        claim over part of it predates this answer and must survive it. A
        window already answered for is left untouched, so reading it twice
        stays a pure read.

        This is the shape every caller wants that is recording an answer it
        did not have to fetch — there was nothing to go and get, only the fact
        that the question was asked.
        """
        missing = self.missing(subject, window)
        if not missing:
            return
        for interval in missing:
            self.mark(
                subject,
                interval,
                checked_at_ns=checked_at_ns,
                applicable=applicable,
            )
        self.consolidate(subject, window)

    def checked_at_values(
        self,
        subject: CatalogKey[Data],
        interval: CoverageInterval,
    ) -> list[int]:
        markers = self.catalog.read_all(self._key(subject))
        return [
            marker.checked_at_ns
            for marker in markers
            if marker.end_ns >= interval.start_ns
            and marker.start_ns <= interval.end_ns
        ]

    def covered_through(self, subject: CatalogKey[Data]) -> int | None:
        """Return the latest verified endpoint for *subject*, if one exists."""
        markers = self.catalog.read_all(self._key(subject))
        return max((marker.end_ns for marker in markers), default=None)

    def consolidate(
        self,
        subject: CatalogKey[Data],
        interval: CoverageInterval,
    ) -> None:
        self.catalog.compact(
            self._key(subject),
            CatalogInterval(interval.start_ns, interval.end_ns),
        )

    def repair_interval_descriptions(self, subject: CatalogKey[Data]) -> None:
        self.catalog.repair_interval_descriptions(self._key(subject))

    def delete(
        self,
        subject: CatalogKey[Data],
        interval: CoverageInterval,
    ) -> None:
        key = self._key(subject)
        claims = {
            (
                marker.start_ns,
                marker.end_ns,
                marker.checked_at_ns,
                marker.applicable,
            )
            for marker in self.catalog.read_all(key)
            if marker.end_ns >= interval.start_ns
            and marker.start_ns <= interval.end_ns
        }
        for start_ns, end_ns, checked_at_ns, applicable in claims:
            self.catalog.drop(key, CatalogInterval(start_ns, end_ns))
            for residual in _subtract(
                CoverageInterval(start_ns, end_ns), interval
            ):
                self.mark(
                    subject,
                    residual,
                    checked_at_ns=checked_at_ns,
                    applicable=applicable,
                )

    @staticmethod
    def _key(subject: CatalogKey[Data]) -> CatalogKey[_CoverageMarker]:
        return CatalogKey.for_coverage(
            _CoverageMarker,
            subject,
        )


def _subtract(
    claimed: CoverageInterval,
    removed: CoverageInterval,
) -> tuple[CoverageInterval, ...]:
    residuals: list[CoverageInterval] = []
    if claimed.start_ns < removed.start_ns:
        residuals.append(
            CoverageInterval(
                claimed.start_ns,
                min(claimed.end_ns, removed.start_ns - 1),
            )
        )
    if claimed.end_ns > removed.end_ns:
        residuals.append(
            CoverageInterval(
                max(claimed.start_ns, removed.end_ns + 1),
                claimed.end_ns,
            )
        )
    return tuple(residuals)


__all__ = ["CoverageMarkerLedger"]
