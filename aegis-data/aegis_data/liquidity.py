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

from aegis_data.roll import DatedContract, RollAgreement, assert_roll_agreement


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


__all__ = ["assert_liquid_cycle_agreement", "liquid_cycle", "liquid_cycle_causal"]
