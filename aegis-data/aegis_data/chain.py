"""Assemble a dated-contract chain for the continuous-future roll-transition table.

Given a futures root + date range, build the calendar roll schedule
(:mod:`aegis_data.roll`), fetch each dated contract's OHLCV over its active
window (extended past the roll dates so consecutive contracts overlap on the
seam), snap each roll date to the latest common trading day, and return a
:class:`ContractChain` ready for the roll-transition table
(:mod:`aegis_data.continuous_future`), which Nautilus's engine back-adjusts on
demand (Path A).  The per-contract fetch is injected (``ContractFetcher``) so
assembly is testable without I/O.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from aegis_data.liquidity import liquid_roll_schedule
from aegis_data.roll import (
    DatedContract,
    FuturesChainSchedule,
    roll_lead_days_for_cadence,
    roll_schedule,
)

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

# Probe one candidate's *daily* volume over [start, end] for liquidity-leadership
# ranking.  Daily regardless of the deliverable bar cadence (ADR-0001): inclusion is a
# low-frequency decision, so it must not depend on intraday sampling.  Injected so the
# liquidity filter stays provider-free.
VolumeProbe = Callable[[str, date, date], pd.Series]


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
    bar_cadence: timedelta,
    probe_volume: VolumeProbe | None = None,
) -> ContractChain:
    """Assemble the dated-contract chain for ``root`` over ``[start, end]``.

    ``list_contracts`` supplies the candidate dated contracts (from instrument
    definitions).  When ``probe_volume`` is given, the candidates are first narrowed
    to the **Liquid Cycle** — those ever the daily Liquidity Leader — so the series
    holds only the contracts a desk trades and skips thin serial months (inclusion);
    the calendar roll still decides timing.  The roll schedule is then derived from the
    eligible contracts' last-trade dates, so a monthly product rolls monthly and a
    serial/odd-cycle product rolls on whatever it lists.  The roll lead is derived from
    ``bar_cadence``, never configured.
    """
    roll_lead_days = roll_lead_days_for_cadence(bar_cadence)
    candidates = list_contracts(root, start, end)
    schedule = _roll_schedule(candidates, start, end, probe_volume, roll_lead_days)
    n = len(schedule.symbols)
    frames: list[pd.DataFrame] = []
    for i, symbol in enumerate(schedule.symbols):
        # Reach back past the prior roll for seam overlap, but never before ``start``: the
        # first leg begins at ``start``, so the seam intersection cannot use earlier days,
        # and a fetch before the provider's available history aborts the pull (a 422 at the
        # window's left edge).  Symmetric to the expiry clamp on the late edge below.
        window_start = (
            max(schedule.roll_dates[i - 1] - _OVERLAP_BUFFER, start) if i > 0 else start
        )
        if i < n - 1:
            # The +overlap buffer past the roll is a best-effort seam fetch, not
            # required seam input: a rolled-off contract has no bars past its last
            # trade, and the buffer reaches past expiry, so demanding those days
            # aborts the pull (aegis-rd-lqz).  Clamp to the contract's last trade.
            # The seam overlap is preserved — last_trade falls after the roll date,
            # so the on/before-roll days where adjacent contracts overlap stay in
            # range.  The final leg keeps the requested ``end`` (it is the front
            # contract through the window edge, not a rolled-off one).
            window_end = min(
                schedule.roll_dates[i] + _OVERLAP_BUFFER, schedule.expiries[i]
            )
        else:
            window_end = end
        frames.append(fetch(symbol, window_start, window_end))
    roll_dates = _snap_roll_dates(schedule.roll_dates, frames)
    return ContractChain(
        symbols=schedule.symbols, roll_dates=roll_dates, frames=tuple(frames)
    )


def _roll_schedule(
    candidates: Sequence[DatedContract],
    start: date,
    end: date,
    probe_volume: VolumeProbe | None,
    roll_lead_days: int,
) -> FuturesChainSchedule:
    """The Liquid-Cycle, liquidity-timed roll schedule when a volume probe is supplied,
    else the plain calendar schedule over every listed candidate.

    With a probe, each candidate's daily volume is read over its own life and fed to
    :func:`liquid_roll_schedule`, which narrows to the Liquid Cycle (drops thin serials)
    and rolls on Liquidity-Leader migration capped by the calendar rule.  Each probe
    window ends at ``min(last_trade, end)``, never the full multi-year chain edge, so the
    per-contract definitions snapshot — anchored at the window's late edge — lands inside
    the contract's listed life: a contract is only listed a bounded horizon before expiry
    (ICE lists ~10 months out), so probing every candidate to the full edge left far-dated
    contracts unresolvable (a provider 422).  With no probe the chain rolls on the calendar
    through whatever was listed — a caller that does not rank liquidity.
    """
    if probe_volume is None:
        return roll_schedule(candidates, start, end, roll_lead_days=roll_lead_days)
    # A candidate whose last trade falls before the window start is listed only by the
    # calendar's lookback anchor; it expired before the window opens, so its probe window
    # would invert (``start`` > ``min(last_trade, end)``).  It can never be the Liquidity
    # Leader, so skip the probe — ``liquid_roll_schedule`` then drops it for having no volume.
    volume_by_symbol = {
        contract.symbol: probe_volume(
            contract.symbol, start, min(contract.last_trade, end)
        )
        for contract in candidates
        if contract.last_trade >= start
    }
    return liquid_roll_schedule(
        candidates, volume_by_symbol, start, end, roll_lead_days=roll_lead_days
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


__all__ = ["ContractChain", "ContractFetcher", "VolumeProbe", "fetch_contract_chain"]
