"""Pure Covered History coverage rules for the Historical Store."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd
from aegis_runtime import FuturesRef

from aegis_data.calendars import (
    TradingCalendar,
    as_trading_calendar,
    business_day_offset,
    intraday_session_bars,
)

_DAILY_TIMEFRAMES = frozenset({"1D", "1d"})


class CoverageKey(Protocol):
    @property
    def value(self) -> str: ...


class StoreCoverageError(ValueError):
    """A provider-free Store Read cannot satisfy the requested Covered History."""

    def __init__(self, key: CoverageKey, detail: str) -> None:
        self.key = key
        super().__init__(f"{key.value}: {detail}")


@dataclass(frozen=True)
class CoverageGap:
    """Uncovered half-open interval of expected instrument-calendar bars."""

    start: pd.Timestamp
    end: pd.Timestamp


@dataclass(frozen=True)
class HistoryWindow:
    """Demand for Covered History over a half-open time window."""

    timeframe: str
    calendar: TradingCalendar | str
    start: str | date | pd.Timestamp
    end: str | date | pd.Timestamp

    def __post_init__(self) -> None:
        left = pd.Timestamp(self.start).tz_localize(None)
        right = pd.Timestamp(self.end).tz_localize(None)
        if right <= left:
            raise ValueError(
                f"Store Read end must be after start; got {self.start!r} -> {self.end!r}"
            )
        object.__setattr__(self, "calendar", as_trading_calendar(self.calendar))
        object.__setattr__(self, "start", left)
        object.__setattr__(self, "end", right)

    def expected_index(self) -> pd.DatetimeIndex:
        """Expected bar timestamps over this window."""
        if self.timeframe not in _DAILY_TIMEFRAMES:
            return intraday_session_bars(
                self.calendar, self.timeframe, self.start, self.end
            )
        return _business_days(self.start, self.end, calendar=self.calendar)

    def observed_index(self, index: pd.Index) -> pd.DatetimeIndex:
        """Observed timestamps at the window timeframe's resolution."""
        observed = pd.DatetimeIndex(index).tz_localize(None)
        return observed.normalize() if self.timeframe in _DAILY_TIMEFRAMES else observed


@dataclass(frozen=True)
class Completeness:
    """Rule for which observed rows satisfy a Covered History demand."""

    arrays: tuple[str, ...]
    value_name: str

    @classmethod
    def for_native_bars(cls, arrays: Sequence[str]) -> Completeness:
        return cls(arrays=tuple(arrays), value_name="bar")

    @classmethod
    def for_fx_rates(cls) -> Completeness:
        return cls(arrays=("rate",), value_name="FX rate")

    def complete_index(self, window: HistoryWindow, observed: pd.DataFrame) -> pd.DatetimeIndex:
        columns = _column_lookup(observed)
        if any(array.lower() not in columns for array in self.arrays):
            return pd.DatetimeIndex([])
        sliced = _slice_window(observed, window)
        selected = _select_columns(sliced, columns, self.arrays)
        if selected.empty:
            return pd.DatetimeIndex([])
        complete_rows = selected.loc[~selected.isna().any(axis=1)]
        return window.observed_index(complete_rows.index)

    def slice(
        self,
        key: CoverageKey,
        window: HistoryWindow,
        observed: pd.DataFrame,
    ) -> pd.DataFrame:
        columns = _require_columns(key, observed, self.arrays)
        sliced = _slice_window(observed, window)
        return _select_columns(sliced, columns, self.arrays)


@dataclass(frozen=True)
class StoreCoverage:
    """Frame-in coverage policy for one Historical Store identity."""

    key: CoverageKey
    completeness: Completeness
    tolerate_interior: bool

    @classmethod
    def for_native_bars(
        cls, ref: CoverageKey, *, arrays: Sequence[str]
    ) -> StoreCoverage:
        return cls(
            key=ref,
            completeness=Completeness.for_native_bars(arrays),
            tolerate_interior=isinstance(ref, FuturesRef),
        )

    @classmethod
    def for_fx_rates(cls, pair: CoverageKey) -> StoreCoverage:
        return cls(
            key=pair,
            completeness=Completeness.for_fx_rates(),
            tolerate_interior=False,
        )

    def gaps(
        self, window: HistoryWindow, observed: pd.DataFrame
    ) -> tuple[CoverageGap, ...]:
        expected = window.expected_index()
        missing = self._missing_expected(window, observed, expected=expected)
        return _coverage_gaps(missing, expected)

    def assert_covered(self, window: HistoryWindow, observed: pd.DataFrame) -> None:
        expected = window.expected_index()
        missing = self._missing_expected(window, observed, expected=expected)
        if missing.empty:
            return
        raise StoreCoverageError(
            self.key,
            (
                f"missing expected {window.timeframe} "
                f"{self.completeness.value_name} on {missing[0].isoformat()}"
            ),
        )

    def slice(self, window: HistoryWindow, observed: pd.DataFrame) -> pd.DataFrame:
        selected = self.completeness.slice(self.key, window, observed)
        self.assert_covered(window, observed)
        if selected.isna().any().any():
            raise StoreCoverageError(self.key, "requested arrays contain null values")
        return selected

    def _missing_expected(
        self,
        window: HistoryWindow,
        observed: pd.DataFrame,
        *,
        expected: pd.DatetimeIndex,
    ) -> pd.DatetimeIndex:
        if expected.empty:
            return expected
        complete_index = self.completeness.complete_index(window, observed)
        return _uncovered_expected(
            expected,
            complete_index,
            tolerate_interior=self.tolerate_interior,
        )


def _business_days(
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    calendar: TradingCalendar | str,
) -> pd.DatetimeIndex:
    last_inclusive = (end - pd.Timedelta(days=1)).normalize()
    if last_inclusive < start.normalize():
        return pd.DatetimeIndex([])
    return pd.date_range(start.normalize(), last_inclusive, freq=business_day_offset(calendar))


def _slice_window(frame: pd.DataFrame, window: HistoryWindow) -> pd.DataFrame:
    return frame.loc[(frame.index >= window.start) & (frame.index < window.end)]


def _uncovered_expected(
    expected: pd.DatetimeIndex,
    observed: pd.DatetimeIndex,
    *,
    tolerate_interior: bool,
) -> pd.DatetimeIndex:
    missing = expected.difference(observed)
    if not tolerate_interior or missing.empty or observed.empty:
        return missing
    return missing[(missing < observed.min()) | (missing > observed.max())]


def _coverage_gaps(
    missing: pd.DatetimeIndex,
    expected: pd.DatetimeIndex,
) -> tuple[CoverageGap, ...]:
    if missing.empty:
        return ()
    positions = expected.get_indexer(missing)
    gaps: list[CoverageGap] = []
    group_start = 0
    for offset in range(1, len(positions)):
        if positions[offset] == positions[offset - 1] + 1:
            continue
        gaps.append(_coverage_gap(missing[group_start], missing[offset - 1]))
        group_start = offset
    gaps.append(_coverage_gap(missing[group_start], missing[-1]))
    return tuple(gaps)


def _coverage_gap(first: pd.Timestamp, last: pd.Timestamp) -> CoverageGap:
    return CoverageGap(start=first.normalize(), end=(last + pd.Timedelta(days=1)).normalize())


def _column_lookup(frame: pd.DataFrame) -> dict[str, str]:
    return {str(column).lower(): str(column) for column in frame.columns}


def _require_columns(
    key: CoverageKey,
    frame: pd.DataFrame,
    arrays: tuple[str, ...],
) -> dict[str, str]:
    columns = _column_lookup(frame)
    missing_arrays = tuple(array for array in arrays if array.lower() not in columns)
    if missing_arrays:
        raise StoreCoverageError(key, f"missing arrays {list(missing_arrays)}")
    return columns


def _select_columns(
    frame: pd.DataFrame,
    columns: dict[str, str],
    arrays: tuple[str, ...],
) -> pd.DataFrame:
    selected = frame.loc[:, [columns[array.lower()] for array in arrays]].copy()
    selected.columns = list(arrays)
    return selected


__all__ = [
    "Completeness",
    "CoverageGap",
    "HistoryWindow",
    "StoreCoverage",
    "StoreCoverageError",
]
