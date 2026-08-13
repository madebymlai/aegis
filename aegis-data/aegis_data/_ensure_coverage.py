"""One internal Ensure Coverage engine for every catalog record type."""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

import pandas as pd

from aegis_data.provider import ProviderAnswer
from aegis_data.storage import CatalogKey


@dataclass(frozen=True)
class CoverageInterval:
    """One inclusive nanosecond interval whose catalog coverage is missing."""

    start_ns: int
    end_ns: int

    def __post_init__(self) -> None:
        if self.start_ns > self.end_ns:
            raise ValueError("coverage interval start must not be after end")

    @property
    def start(self) -> pd.Timestamp:
        return pd.Timestamp(self.start_ns, tz="UTC")

    @property
    def end(self) -> pd.Timestamp:
        return pd.Timestamp(self.end_ns, tz="UTC")

    def from_frontier(
        self, oldest_verified: pd.Timestamp
    ) -> "CoverageInterval | None":
        start_ns = max(self.start_ns, oldest_verified.value)
        if start_ns > self.end_ns:
            return None
        return CoverageInterval(start_ns, self.end_ns)


class CatalogCoverageGapError(ValueError):
    """The Catalog cannot serve a requested covered window."""

    def __init__(
        self,
        subject: CatalogKey[Any],
        missing: Sequence[CoverageInterval],
        *,
        message: str,
    ) -> None:
        self.subject = subject
        self.missing = tuple(missing)
        super().__init__(message)


class GapFillProviderError(RuntimeError):
    """A provider failed environmentally while filling a Catalog gap."""


RecordT = TypeVar("RecordT")
MissingIntervals = Callable[[], list[CoverageInterval]]
CoverageError = Callable[[Sequence[CoverageInterval]], Exception]
CoverageCommit = Callable[[CoverageInterval, tuple[RecordT, ...]], None]
CoverageFilled = Callable[[], None]


RecordFetcher = Callable[[pd.Timestamp, pd.Timestamp], ProviderAnswer[RecordT]]


_CAUSE_SUMMARY_LIMIT = 200


def ensure_coverage(
    *,
    subject: str,
    provider: RecordFetcher[Any] | None,
    missing_intervals: MissingIntervals,
    commit: CoverageCommit[Any],
    coverage_error: CoverageError,
    on_filled: CoverageFilled,
) -> None:
    """Fill and re-verify one requested catalog window.

    One provider answers every initially missing interval. The caller commits
    every provider-verified interval, including empty results, so each record
    domain owns its persistence model.
    An *environmental* failure raised while the provider is being consulted
    (gateway drop, timeout) aborts the whole request —
    deliberately: providers here are complementary (each owns a window), not
    redundant failover, so a source that cannot even be reached fails closed
    rather than silently deferring to a lesser source. Add catch-and-continue
    only when a genuinely redundant provider exists, with a test pinning which
    semantic is wanted.

    ``on_filled`` runs when a fill actually happened and left the window
    clean — never when the window was already covered on arrival. That is not
    the same as "the call returned normally", which is why it is a callback
    rather than a line after the call: a caller that consolidated a window it
    never touched would write during what was a pure read.
    """
    initial_missing = missing_intervals()
    if not initial_missing:
        return
    if provider is None:
        raise coverage_error(initial_missing)

    for missing in initial_missing:
        with gap_fill_boundary(subject):
            served = provider(missing.start, missing.end)
        verified = missing.from_frontier(served.oldest_verified)
        if verified is None:
            continue
        commit(verified, tuple(served.records))

    remaining = missing_intervals()
    if remaining:
        raise coverage_error(remaining)
    on_filled()


@contextmanager
def gap_fill_boundary(subject: str) -> Iterator[None]:
    """Translate provider faults without changing coverage verdicts."""
    try:
        yield
    except CatalogCoverageGapError:
        raise
    except Exception as exc:
        raise GapFillProviderError(
            f"the gap-fill provider could not serve {subject}: "
            f"{type(exc).__name__}: {_cause_summary(exc)}"
        ) from exc


def _cause_summary(exc: Exception) -> str:
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    if len(first_line) <= _CAUSE_SUMMARY_LIMIT:
        return first_line
    return first_line[:_CAUSE_SUMMARY_LIMIT] + "…"


__all__ = [
    "CatalogCoverageGapError",
    "CoverageInterval",
    "GapFillProviderError",
    "ensure_coverage",
    "gap_fill_boundary",
]
