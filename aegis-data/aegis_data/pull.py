"""Covered History Pull loop."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import pandas as pd
from aegis_runtime import InstrumentRef

from aegis_data.store import CoveredWindow, FxPair, HistoricalStore, WriteMode


@dataclass(frozen=True)
class FetchWindow:
    """Provider fetch window for one coverage gap."""

    timeframe: str
    start: str | pd.Timestamp
    end: str | pd.Timestamp
    arrays: Sequence[str]


class GapFetch(Protocol):
    """Provider adapter that returns a store-ready frame for one fetch window."""

    def __call__(self, window: FetchWindow) -> pd.DataFrame: ...


def pull(
    key: InstrumentRef | FxPair,
    window: CoveredWindow,
    *,
    store: HistoricalStore,
    fetch: GapFetch,
) -> None:
    """Fill Covered History gaps by fetching, admitting, then merging provider facts."""
    for gap in store.coverage_gaps(key, window):
        gap_window = window.narrowed_to(gap)
        frame = fetch(
            FetchWindow(
                timeframe=window.timeframe,
                start=gap.start,
                end=gap.end,
                arrays=window.arrays,
            )
        )
        store.assert_admissible(key, frame, gap_window)
        store.write(key, frame, gap_window, mode=WriteMode.MERGE)


__all__ = ["FetchWindow", "GapFetch", "pull"]
