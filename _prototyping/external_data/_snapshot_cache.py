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


class SnapshotCacheMiss(RuntimeError):
    pass


def covers(snapshot: CoveredSnapshot, start: date, end: date) -> bool:
    """Return whether one immutable snapshot contains the requested interval."""

    return snapshot.covered_start <= start.isoformat() and snapshot.covered_end >= end.isoformat()


def newest_covering[SnapshotT: CoveredSnapshot](
    paths: Iterable[Path],
    loader: Callable[[Path], SnapshotT],
    start: date,
    end: date,
) -> SnapshotT:
    snapshots = tuple(loader(path) for path in paths)
    if not snapshots:
        raise SnapshotCacheMiss("snapshot cache is empty")
    covering = tuple(snapshot for snapshot in snapshots if covers(snapshot, start, end))
    if not covering:
        raise SnapshotCacheMiss("snapshot cache has no entry covering the requested range")
    return max(covering, key=lambda item: (item.covered_end, item.retrieved_at))


def sync_on_miss(read: Callable[[], CoveredSnapshot], fetch: Callable[[], None]) -> None:
    """Fetch once only when the validated cache query cannot cover a request."""

    try:
        read()
    except SnapshotCacheMiss:
        fetch()
