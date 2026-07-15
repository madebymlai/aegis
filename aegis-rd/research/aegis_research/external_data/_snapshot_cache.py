"""Shared selection rules for immutable external-data snapshots."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date
from pathlib import Path
from typing import Protocol


class CoveredSnapshot(Protocol):
    @property
    def covered_start(self) -> str: ...

    @property
    def covered_end(self) -> str: ...

    @property
    def retrieved_at(self) -> str: ...


def covers(snapshot: CoveredSnapshot, start: date, end: date) -> bool:
    """Return whether one immutable snapshot contains the requested interval."""

    return snapshot.covered_start <= start.isoformat() and snapshot.covered_end >= end.isoformat()


def newest_covering[SnapshotT: CoveredSnapshot](
    paths: Iterable[Path],
    loader: Callable[[Path], SnapshotT],
    start: date,
    end: date,
    *,
    empty_error: Exception,
    coverage_error: Exception,
) -> SnapshotT:
    snapshots = tuple(loader(path) for path in paths)
    if not snapshots:
        raise empty_error
    covering = tuple(snapshot for snapshot in snapshots if covers(snapshot, start, end))
    if not covering:
        raise coverage_error
    return max(covering, key=lambda item: (item.covered_end, item.retrieved_at))


def require_covering[SnapshotT: CoveredSnapshot](
    snapshot: SnapshotT,
    start: date,
    end: date,
    *,
    coverage_error: Exception,
) -> SnapshotT:
    if not covers(snapshot, start, end):
        raise coverage_error
    return snapshot
