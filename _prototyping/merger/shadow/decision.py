"""Frozen market-implied q70 policy for prospective shadow decisions."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from .ledger import EventObservation, EventStatus

_Q_MINIMUM = 0.70
_MINIMUM_CONCURRENT = 10
_MAXIMUM_LIFECYCLE_SLOTS = 40
_NAME_CAP = 0.10
_BREAK_LOSS_CAP = 0.02
_MINIMUM_MEDIAN_DOLLAR_VOLUME = 1_000_000.00
_EXPECTED_CLOSE_DAYS = 175
_SLIPPAGE = 0.0005
_FIXED_FEE = 0.35


@dataclass(frozen=True)
class MarketMark:
    """Causally available inputs needed to value one pending cash merger."""

    instrument_id: str
    ticker: str
    observed_at: str
    close: float
    preannouncement_close: float
    market_close: float
    announcement_market_close: float
    beta: float
    median_dollar_volume: float
    annual_cash_rate: float


@dataclass(frozen=True)
class ShadowPosition:
    """One executable whole-share target produced by the frozen policy."""

    event_id: str
    instrument_id: str
    ticker: str
    shares: int
    price: float
    target_weight: float
    q_market: float
    break_loss: float


@dataclass(frozen=True)
class ShadowDecision:
    """A complete, unlevered shadow book including modeled execution drag."""

    as_of: str
    capital: float
    positions: tuple[ShadowPosition, ...]
    estimated_commissions: float
    estimated_slippage: float
    cash_reserve: float


@dataclass(frozen=True)
class _EligibleDeal:
    event: EventObservation
    mark: MarketMark
    q_market: float
    break_loss: float


class FrozenQ70Policy:
    """Apply the unchanged monthly q70 benchmark to one causal snapshot."""

    def decide(
        self,
        events: Iterable[EventObservation],
        marks: Iterable[MarketMark],
        *,
        as_of: datetime,
        capital: float,
    ) -> ShadowDecision:
        if capital <= 0.0:
            raise ValueError("shadow capital must be positive")
        marks_by_instrument = {
            mark.instrument_id: mark for mark in marks if _available(mark.observed_at, as_of)
        }
        current = _latest_by_event(events, as_of)
        eligible = tuple(
            deal
            for event in current
            if (
                deal := _eligible(
                    event,
                    marks_by_instrument.get(event.instrument_id),
                    as_of,
                    capital,
                )
            )
            is not None
        )
        ranked = sorted(eligible, key=lambda item: (-item.q_market, item.event.event_id))
        chosen = ranked[:_MAXIMUM_LIFECYCLE_SLOTS]
        if len(chosen) < _MINIMUM_CONCURRENT:
            return _cash_decision(as_of, capital)

        equal_weight = 1.0 / len(chosen)
        positions = tuple(
            position
            for item in chosen
            if (
                position := _whole_share_position(
                    item,
                    capital=capital,
                    equal_weight=equal_weight,
                )
            )
            is not None
        )
        if len(positions) < _MINIMUM_CONCURRENT:
            return _cash_decision(as_of, capital)

        commissions = len(positions) * _FIXED_FEE
        traded = sum(position.shares * position.price for position in positions)
        slippage = traded * _SLIPPAGE
        return ShadowDecision(
            as_of=as_of.isoformat(),
            capital=capital,
            positions=positions,
            estimated_commissions=round(commissions, 2),
            estimated_slippage=round(slippage, 2),
            cash_reserve=round(capital - traded - commissions - slippage, 2),
        )


def _latest_by_event(
    observations: Iterable[EventObservation], as_of: datetime
) -> tuple[EventObservation, ...]:
    latest: dict[str, EventObservation] = {}
    for observation in sorted(
        (item for item in observations if _available(item.observed_at, as_of)),
        key=lambda item: (item.observed_at, item.event_id, item.source_accession),
    ):
        latest[observation.event_id] = observation
    return tuple(latest[event_id] for event_id in sorted(latest))


def _eligible(
    event: EventObservation,
    mark: MarketMark | None,
    as_of: datetime,
    capital: float,
) -> _EligibleDeal | None:
    if event.status not in {EventStatus.ANNOUNCED, EventStatus.AMENDED}:
        return None
    if event.offer_price is None or mark is None:
        return None
    announced = datetime.fromisoformat(event.observed_at)
    if as_of.date() <= announced.date():
        return None
    remaining_days = max(_EXPECTED_CLOSE_DAYS - (as_of.date() - announced.date()).days, 0)
    discounted_offer = event.offer_price / (1.0 + mark.annual_cash_rate * remaining_days / 365.0)
    fallback = mark.preannouncement_close * math.exp(
        mark.beta * math.log(mark.market_close / mark.announcement_market_close)
    )
    if not fallback < mark.close < discounted_offer:
        return None
    break_loss = (mark.close - fallback) / mark.close
    q_market = (mark.close - fallback) / (discounted_offer - fallback)
    if mark.close > capital * _NAME_CAP:
        return None
    if mark.median_dollar_volume < _MINIMUM_MEDIAN_DOLLAR_VOLUME:
        return None
    if q_market < _Q_MINIMUM:
        return None
    return _EligibleDeal(
        event=event,
        mark=mark,
        q_market=min(q_market, 1.0),
        break_loss=break_loss,
    )


def _whole_share_position(
    deal: _EligibleDeal,
    *,
    capital: float,
    equal_weight: float,
) -> ShadowPosition | None:
    weight = min(_NAME_CAP, equal_weight, _BREAK_LOSS_CAP / deal.break_loss)
    budget = capital * weight
    shares = math.floor((budget - _FIXED_FEE) / (deal.mark.close * (1.0 + _SLIPPAGE)))
    if shares < 1:
        return None
    return ShadowPosition(
        event_id=deal.event.event_id,
        instrument_id=deal.event.instrument_id,
        ticker=deal.event.ticker,
        shares=shares,
        price=deal.mark.close,
        target_weight=round(shares * deal.mark.close / capital, 12),
        q_market=deal.q_market,
        break_loss=deal.break_loss,
    )


def _cash_decision(as_of: datetime, capital: float) -> ShadowDecision:
    return ShadowDecision(
        as_of=as_of.isoformat(),
        capital=capital,
        positions=(),
        estimated_commissions=0.0,
        estimated_slippage=0.0,
        cash_reserve=capital,
    )


def _available(observed_at: str, as_of: datetime) -> bool:
    observed = datetime.fromisoformat(observed_at)
    if observed.tzinfo is None or as_of.tzinfo is None:
        raise ValueError("shadow decision timestamps must include a timezone")
    return observed <= as_of
