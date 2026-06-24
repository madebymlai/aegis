"""Volume liquidity-leadership eligibility — the Liquid Cycle.

A continuous futures series should hold only the dated contracts a desk actually
trades (the **Liquid Cycle**) and skip thin **Serial Months**.  Membership is read
from data: a contract is eligible iff it is *ever* the **Liquidity Leader** — the
highest daily-volume contract among the contemporaneously-live contracts of its root
— over its own life.  Leadership is judged on volume smoothed over the roll-lead
window so a single anomalous print cannot admit a serial (ADR-0001).

Pure: no I/O.  Volume is supplied by the caller (read from the OHLCV Raw Futures
Legs), so this stays a deterministic function of a candidate set and its volumes.
Inclusion only — the calendar roll (:mod:`aegis_data.roll`) still decides timing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

import pandas as pd

from aegis_data.roll import (
    DatedContract,
    FuturesChainSchedule,
    RollAgreement,
    assert_roll_agreement,
    roll_date,
    roll_schedule,
)


def liquid_roll_schedule(
    candidates: Sequence[DatedContract],
    volume_by_symbol: Mapping[str, pd.Series],
    start: date,
    end: date,
    *,
    roll_lead_days: int,
) -> FuturesChainSchedule:
    """Calendar roll schedule moved earlier to the Liquidity-Leader migration.

    The calendar rule (:func:`roll.roll_schedule`) rolls a fixed lead before last-trade,
    but for thin roots (palladium, platinum, the ICE softs) liquidity migrates to the next
    contract weeks earlier; the front then stops printing while still 'front' by the
    calendar, and the stitch drops the in-between days the already-liquid next contract
    traded.  This caps each seam's roll at the day the next contract becomes the
    trailing-smoothed Liquidity Leader — **never later** than the calendar roll, so a root
    whose liquidity tracks expiry is unchanged.  Leadership is judged on trailing volume
    only, so the capped roll dates are identical whether computed acausally (research, full
    window) or causally (live, volume-so-far) — the backtest/live roll stays in parity.

    ``roll_schedule`` selects the window's legs by the **calendar** front alone, so when ``end``
    lands between a leg's liquidity crossover and its calendar roll — always the live case, where
    ``end`` is now and is mid-roll-window for the current front — it truncates the next, already-liquid
    leg (its calendar front-window starts after ``end``).  The cap alone could then only move existing
    seams earlier, never recover the dropped leg, stranding the series on the thinning front.  So the
    window's late edge is extended onto every eligible successor that has taken liquidity leadership by
    ``end``, rolling onto it at the (capped) crossover.
    """
    eligible = liquid_cycle(candidates, volume_by_symbol, roll_lead_days=roll_lead_days)
    calendar = roll_schedule(eligible, start, end, roll_lead_days=roll_lead_days)
    if not calendar.symbols:
        return calendar
    forward = _legs_from_window_front(_by_expiry(eligible), calendar.symbols[0])
    crossovers = _leadership_crossovers(
        tuple(contract.symbol for contract in forward), volume_by_symbol, roll_lead_days
    )
    count = _front_count_by_end(forward, len(calendar.symbols), crossovers, end)
    if count == len(calendar.symbols):
        # No successor was truncated, so the calendar window already names every leg front by `end`:
        # pass its legs through verbatim (only capping the seam dates onto any earlier crossover,
        # exactly as before), keeping an unextended chain byte-identical to the calendar rule.
        return FuturesChainSchedule(
            symbols=calendar.symbols,
            expiries=calendar.expiries,
            roll_dates=_cap_rolls(calendar.roll_dates, crossovers[: count - 1]),
        )
    chain = forward[:count]
    calendar_rolls = tuple(roll_date(contract, roll_lead_days=roll_lead_days) for contract in chain[:-1])
    return FuturesChainSchedule(
        symbols=tuple(contract.symbol for contract in chain),
        expiries=tuple(contract.last_trade for contract in chain),
        roll_dates=_cap_rolls(calendar_rolls, crossovers[: count - 1]),
    )


def _legs_from_window_front(
    ordered: Sequence[DatedContract], window_front_symbol: str
) -> tuple[DatedContract, ...]:
    """The expiry-ordered eligible legs from the calendar window's front leg onward — the forward
    chain the late-edge extension walks, including successors ``roll_schedule``'s window truncated."""
    first = next(
        index for index, contract in enumerate(ordered) if contract.symbol == window_front_symbol
    )
    return tuple(ordered[first:])


def _front_count_by_end(
    forward: Sequence[DatedContract],
    calendar_count: int,
    crossovers: Sequence[date | None],
    end: date,
) -> int:
    """How many of ``forward`` (the eligible legs from the window start) are front by ``end``.

    Begins at the calendar window's leg count and walks forward, taking each successor whose
    smoothed leadership crossover is on/before ``end`` — recovering the legs ``roll_schedule``'s
    calendar window truncated because their calendar roll falls after ``end``.  Stops at the first
    successor not yet liquidity-leading by ``end``, so legs that have not taken over stay excluded.
    """
    count = calendar_count
    while count < len(forward):
        crossover = crossovers[count - 1]  # the seam forward[count - 1] -> forward[count]
        if crossover is None or crossover > end:
            break
        count += 1
    return count


def liquid_cycle(
    candidates: Sequence[DatedContract],
    volume_by_symbol: Mapping[str, pd.Series],
    *,
    roll_lead_days: int,
) -> tuple[DatedContract, ...]:
    """The subset of ``candidates`` that is ever the Liquidity Leader over its life.

    Each day, the leader is the candidate with the highest roll-lead-smoothed daily
    volume among those live (printing a bar) that day; a candidate is eligible iff it
    leads on at least one day.  Smoothing over ``roll_lead_days`` keeps a lone spike
    (an expiry-day / roll-spread print) from admitting a Serial Month.  A candidate
    with no supplied volume never leads and is excluded.  Ties resolve to the
    earliest-expiring candidate, deterministically.
    """
    leaders = _ever_leader_symbols(candidates, volume_by_symbol, roll_lead_days)
    return tuple(
        contract for contract in _by_expiry(candidates) if contract.symbol in leaders
    )


def liquid_cycle_causal(
    candidates: Sequence[DatedContract],
    volume_by_symbol: Mapping[str, pd.Series],
    as_of: date,
    *,
    roll_lead_days: int,
) -> tuple[DatedContract, ...]:
    """The Liquid Cycle judged only on volume observed on/before ``as_of``.

    Live selection cannot read a contract's future volume, so a contract is eligible
    once it *has* been the Liquidity Leader by ``as_of`` — not if it ever will be.  At
    the window end this coincides with the acausal :func:`liquid_cycle` over the same
    volume, which is what the research/live parity guard relies on.
    """
    cutoff = pd.Timestamp(as_of)
    observed = {
        symbol: volume[volume.index <= cutoff]
        for symbol, volume in volume_by_symbol.items()
    }
    return liquid_cycle(candidates, observed, roll_lead_days=roll_lead_days)


def assert_liquid_cycle_agreement(
    root: str,
    research_candidates: Sequence[DatedContract],
    research_volume: Mapping[str, pd.Series],
    live_candidates: Sequence[DatedContract],
    live_volume: Mapping[str, pd.Series],
    start: date,
    end: date,
    *,
    roll_lead_days: int,
) -> RollAgreement:
    """Assert the research and live Liquid Cycle roll schedules agree.

    Each substrate's candidates are first narrowed to its Liquid Cycle — research over
    full-window volume (acausal), live over volume observed through ``end`` (causal) —
    so feed-specific serial listings that never lead drop out before the comparison.
    The filtered sets pass through the unchanged :func:`roll.assert_roll_agreement`,
    which fails closed (``RollAgreementError`` naming ``root``) when a cross-feed volume
    difference would make the substrates hold different contracts.
    """
    research_eligible = liquid_cycle(
        research_candidates, research_volume, roll_lead_days=roll_lead_days
    )
    live_eligible = liquid_cycle_causal(
        live_candidates, live_volume, end, roll_lead_days=roll_lead_days
    )
    return assert_roll_agreement(
        root, research_eligible, live_eligible, start, end, roll_lead_days=roll_lead_days
    )


def _leadership_crossovers(
    symbols: Sequence[str],
    volume_by_symbol: Mapping[str, pd.Series],
    roll_lead_days: int,
) -> tuple[date | None, ...]:
    """Per-seam date the next contract first becomes the (monotone) Liquidity Leader.

    One entry per seam (``len(symbols) - 1``).  The daily leader is the highest
    trailing-smoothed volume among the contracts printing that day; ``cummax`` over the
    expiry order makes leadership monotone front→back (no flip back to an earlier
    contract).  ``None`` for a seam whose next contract never leads within the supplied
    volume — that seam keeps its calendar roll.
    """
    if len(symbols) < 2:
        return ()
    live = {
        symbol: volume_by_symbol[symbol]
        for symbol in symbols
        if symbol in volume_by_symbol and len(volume_by_symbol[symbol]) > 0
    }
    if not live:
        return tuple(None for _ in symbols[:-1])
    # Judge leadership on a continuous daily grid, carrying each contract's smoothed volume
    # across short non-print gaps (``ffill`` bounded to the smoothing window): a single
    # missed session keeps the leader leading, but once a contract has not printed for the
    # whole window its carried value lapses to NaN — it is no longer actively trading and
    # cannot lead, so liquidity hands over.  (The Liquid-Cycle inclusion smoothing, judged on
    # each contract's own sparse index, is left untouched.)
    grid = pd.bdate_range(min(v.index.min() for v in live.values()),
                          max(v.index.max() for v in live.values()))
    window = max(1, roll_lead_days)
    columns: dict[str, pd.Series] = {
        symbol: _smoothed(live[symbol], roll_lead_days).reindex(grid).ffill(limit=window)
        for symbol in symbols
        if symbol in live
    }
    panel = pd.DataFrame(columns).reindex(columns=[s for s in symbols if s in columns])
    if panel.empty:
        return tuple(None for _ in symbols[:-1])
    position = {symbol: index for index, symbol in enumerate(symbols)}
    rank = panel.idxmax(axis=1).map(position).cummax()
    crossovers: list[date | None] = []
    for seam in range(1, len(symbols)):
        reached = rank.index[rank >= seam]
        crossovers.append(reached.min().date() if len(reached) else None)
    return tuple(crossovers)


def _cap_rolls(
    calendar_rolls: Sequence[date], crossovers: Sequence[date | None]
) -> tuple[date, ...]:
    """Each seam's roll, moved earlier to its crossover but never below the prior roll.

    ``min(calendar, crossover)`` only ever rolls earlier; a noisy crossover that would
    invert the schedule (land on/before the previous seam) falls back to the calendar
    roll, keeping roll dates strictly increasing.
    """
    capped: list[date] = []
    previous: date | None = None
    for calendar, crossover in zip(calendar_rolls, crossovers):
        roll = calendar if crossover is None else min(calendar, crossover)
        if previous is not None and roll <= previous:
            roll = calendar
        capped.append(roll)
        previous = roll
    return tuple(capped)


def _ever_leader_symbols(
    candidates: Sequence[DatedContract],
    volume_by_symbol: Mapping[str, pd.Series],
    roll_lead_days: int,
) -> set[str]:
    panel = _smoothed_volume_panel(candidates, volume_by_symbol, roll_lead_days)
    if panel.empty:
        return set()
    return set(panel.idxmax(axis=1).dropna())


def _smoothed_volume_panel(
    candidates: Sequence[DatedContract],
    volume_by_symbol: Mapping[str, pd.Series],
    roll_lead_days: int,
) -> pd.DataFrame:
    """Daily smoothed-volume columns, expiry-ordered so ties break to the front.

    Columns are earliest-expiry first; ``idxmax`` returns the first column at a tie,
    so the nearer contract wins a dead-heat day.  A candidate with no bars contributes
    no column and so can never be a daily leader.
    """
    columns: dict[str, pd.Series] = {}
    for contract in _by_expiry(candidates):
        volume = volume_by_symbol.get(contract.symbol)
        if volume is None or len(volume) == 0:
            continue
        columns[contract.symbol] = _smoothed(volume, roll_lead_days)
    return pd.DataFrame(columns)


def _smoothed(volume: pd.Series, roll_lead_days: int) -> pd.Series:
    """Volume averaged over the trailing roll-lead window — a single noisy day is not
    a leadership signal.  ``min_periods=1`` so a contract's first days still rank."""
    window = max(1, roll_lead_days)
    return volume.rolling(window=window, min_periods=1).mean()


def _by_expiry(candidates: Sequence[DatedContract]) -> tuple[DatedContract, ...]:
    return tuple(
        sorted(candidates, key=lambda contract: (contract.last_trade, contract.symbol))
    )


__all__ = [
    "assert_liquid_cycle_agreement",
    "liquid_cycle",
    "liquid_cycle_causal",
    "liquid_roll_schedule",
]
