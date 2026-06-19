"""Assemble a dated-contract chain for back-adjustment.

Given a futures root + date range, build the calendar roll schedule
(:mod:`aegis_data.roll`), fetch each dated contract's OHLCV over its active
window (extended past the roll dates so consecutive contracts overlap on the
seam), snap each roll date to the latest common trading day, and return a
:class:`ContractChain` ready for the back-adjustment transform.  The per-contract
fetch is injected (``ContractFetcher``) so assembly is testable without I/O.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from aegis_data.roll import DEFAULT_ROLL_LEAD_DAYS, DatedContract, roll_schedule

# Each contract is fetched a little past its roll dates so that, after a
# scheduled roll snaps back to the latest common trading day (holiday/weekend),
# both adjacent contracts still carry that day.
_OVERLAP_BUFFER = timedelta(days=14)

# Fetch one dated contract's OHLCV (columns Open/High/Low/Close/Volume, index by
# date) over an inclusive [start, end] window.
ContractFetcher = Callable[[str, date, date], pd.DataFrame]

# List the dated contracts (symbol + last-trade date) for a root over a window, from
# instrument definitions.  Injected so chain assembly stays provider-free.
ContractCalendar = Callable[[str, date, date], Sequence[DatedContract]]


@dataclass(frozen=True)
class ContractChain:
    """A future's dated-contract chain over a date range.

    ``symbols`` / ``frames`` are chronological and aligned 1:1; ``roll_dates`` has
    one entry per seam (``len(symbols) - 1``).  Adjacent frames overlap on their
    roll date so the back-adjustment can read both contracts' price at the seam.
    """

    symbols: tuple[str, ...]
    roll_dates: tuple[pd.Timestamp, ...]
    frames: tuple[pd.DataFrame, ...]


def fetch_contract_chain(
    root: str,
    start: date,
    end: date,
    *,
    list_contracts: ContractCalendar,
    fetch: ContractFetcher,
    roll_lead_days: int = DEFAULT_ROLL_LEAD_DAYS,
) -> ContractChain:
    """Assemble the dated-contract chain for ``root`` over ``[start, end]``.

    ``list_contracts`` supplies the eligible dated contracts (from instrument
    definitions); the roll schedule is derived from their last-trade dates, so a
    monthly product rolls monthly and a serial/odd-cycle product rolls on whatever it
    actually lists.
    """
    schedule = roll_schedule(
        list_contracts(root, start, end), start, end, roll_lead_days=roll_lead_days
    )
    n = len(schedule.symbols)
    frames: list[pd.DataFrame] = []
    for i, symbol in enumerate(schedule.symbols):
        window_start = schedule.roll_dates[i - 1] - _OVERLAP_BUFFER if i > 0 else start
        window_end = schedule.roll_dates[i] + _OVERLAP_BUFFER if i < n - 1 else end
        frames.append(fetch(symbol, window_start, window_end))
    roll_dates = _snap_roll_dates(schedule.roll_dates, frames)
    return ContractChain(
        symbols=schedule.symbols, roll_dates=roll_dates, frames=tuple(frames)
    )


def _snap_roll_dates(
    scheduled: Sequence[date], frames: Sequence[pd.DataFrame]
) -> tuple[pd.Timestamp, ...]:
    """Snap each scheduled roll to the latest trading day present in BOTH adjacent
    contracts on/before it — so the back-adjustment always has the seam overlap."""
    snapped: list[pd.Timestamp] = []
    for i, roll in enumerate(scheduled):
        common = frames[i].index.intersection(frames[i + 1].index)
        candidates = common[common <= pd.Timestamp(roll)]
        if len(candidates) == 0:
            raise ValueError(
                f"no common trading day on/before roll {roll} for contracts "
                f"{i} and {i + 1}; cannot place the seam"
            )
        snapped.append(candidates.max())
    return tuple(snapped)


__all__ = ["ContractChain", "ContractFetcher", "fetch_contract_chain"]
