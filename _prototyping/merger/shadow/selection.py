"""Market-anchored cash-merger selection with swappable completion engines."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Protocol

from .break_value import BreakValueModel
from .ledger import EventObservation, EventStatus
from .timeline import DealTimeline

_MINIMUM_CONCURRENT = 10
_MAXIMUM_LIFECYCLE_SLOTS = 40
_NAME_CAP = 0.10
_BREAK_LOSS_CAP = 0.02
_MINIMUM_MEDIAN_DOLLAR_VOLUME = 1_000_000.00
_SLIPPAGE = 0.0005
_AUTO_FX_CONVERSION_RATE = 0.0003
_TIERED_BASE_COMMISSION_PER_SHARE = 0.0035
_TIERED_BASE_COMMISSION_MINIMUM = 0.35
_TIERED_BASE_COMMISSION_VALUE_CAP = 0.01


class SelectionError(ValueError):
    """A completion engine violated the cash-merger selection contract."""


class SelectionInputError(SelectionError):
    """The selector received an invalid market snapshot or capital amount."""


class EngineIdentityError(SelectionError):
    """A completion engine supplied invalid immutable identity metadata."""


class EngineCoverageError(SelectionError):
    """A completion engine omitted, duplicated, or invented a deal forecast."""


class EngineCausalityError(SelectionError):
    """A completion engine used training or features unavailable at selection time."""


class EngineProbabilityError(SelectionError):
    """A completion engine supplied an invalid probability interval."""


class EngineRankingError(SelectionError):
    """A completion engine supplied an invalid ranking score."""


class SelectionAuthority(StrEnum):
    """Which forecast is allowed to control the executable shadow decision."""

    MARKET_BASELINE = "market_baseline"
    QUALIFIED_CHALLENGER = "qualified_challenger"


class SelectionExclusionReason(StrEnum):
    """Why a deal could not reach the completion-engine seam."""

    INACTIVE = "inactive"
    MISSING_OFFER_OR_MARK = "missing_offer_or_mark"
    ANNOUNCEMENT_NOT_YET_TRADEABLE = "announcement_not_yet_tradeable"
    TIMELINE_UNAVAILABLE = "timeline_unavailable"
    NO_POSITIVE_DISCOUNTED_SPREAD = "no_positive_discounted_spread"
    BREAK_VALUE_UNIDENTIFIED = "break_value_unidentified"
    WHOLE_SHARE_NAME_CAP = "whole_share_name_cap"
    INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"


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
    preannouncement_closes: tuple[float, ...] = ()


@dataclass(frozen=True)
class CompletionCase:
    """One causally valued deal presented to every completion engine."""

    event_id: str
    instrument_id: str
    ticker: str
    selection_as_of: str
    event_observed_at: str
    market_observed_at: str
    agreement_date: str
    offer_price: float
    close: float
    expected_close: str
    latest_close: str
    discounted_offer: float
    fallback_price: float
    break_value_lower: float
    break_value_upper: float
    raw_market_probability: float
    market_probability: float
    market_probability_lower: float
    market_probability_upper: float
    break_loss: float
    days_since_announcement: int


@dataclass(frozen=True)
class CompletionForecast:
    """One engine's independently auditable forecast for a valued deal."""

    event_id: str
    feature_timestamp: str
    model_probability: float
    lower_probability: float
    selected: bool
    rank_score: float


@dataclass(frozen=True)
class SelectionEngineIdentity:
    """Immutable identity shared by every forecast from one fitted engine."""

    engine_id: str
    model_artifact_id: str
    training_cutoff: str | None


class CompletionSelectionEngine(Protocol):
    """The sole seam for replacing deal-selection logic."""

    identity: SelectionEngineIdentity

    def forecast(
        self,
        cases: tuple[CompletionCase, ...],
    ) -> tuple[CompletionForecast, ...]: ...


@dataclass(frozen=True)
class SelectionAssessment:
    """The market baseline and one engine forecast recorded side by side."""

    event_id: str
    instrument_id: str
    ticker: str
    as_of: str
    raw_market_probability: float
    market_probability: float
    market_probability_lower: float
    market_probability_upper: float
    expected_close: str
    latest_close: str
    discounted_offer: float
    break_value_lower: float
    break_value_central: float
    break_value_upper: float
    completion_gain: float
    break_loss: float
    feature_timestamp: str
    model_probability: float
    lower_probability: float
    probability_edge: float
    market_gross_expected_payoff: float
    model_gross_expected_payoff: float
    selected: bool
    rank_score: float


@dataclass(frozen=True)
class SelectionExclusion:
    """One event rejected before a completion engine could assess it."""

    event_id: str
    instrument_id: str
    ticker: str
    reason: SelectionExclusionReason


@dataclass(frozen=True)
class ShadowPosition:
    """One executable whole-share target produced by the selector."""

    event_id: str
    instrument_id: str
    ticker: str
    shares: int
    price: float
    target_weight: float
    q_market: float
    model_probability: float
    probability_edge: float
    break_loss: float


@dataclass(frozen=True)
class ShadowDecision:
    """A complete, unlevered shadow book including modeled execution drag."""

    as_of: str
    capital: float
    positions: tuple[ShadowPosition, ...]
    estimated_base_commission: float
    estimated_slippage: float
    estimated_fx_conversion: float
    cash_reserve: float


@dataclass(frozen=True)
class _ExecutionCostQuote:
    """One authoritative execution-cost estimate for a position or book."""

    base_commission: float
    slippage: float
    fx_conversion: float

    @property
    def total(self) -> float:
        return self.base_commission + self.slippage + self.fx_conversion


@dataclass(frozen=True)
class _ExecutionCostModel:
    """Quote affordability and book costs under one IBKR pricing assumption."""

    slippage_rate: float
    auto_fx_conversion_rate: float
    base_commission_per_share: float
    base_commission_minimum: float
    base_commission_value_cap: float

    def quote_book(self, positions: Iterable[ShadowPosition]) -> _ExecutionCostQuote:
        positions = tuple(positions)
        notional = sum(position.shares * position.price for position in positions)
        return _ExecutionCostQuote(
            base_commission=sum(
                self._base_commission(position.shares, position.price)
                for position in positions
            ),
            slippage=notional * self.slippage_rate,
            fx_conversion=notional * self.auto_fx_conversion_rate,
        )

    def affordable_shares(self, budget: float, price: float) -> int:
        proportional_rate = self.slippage_rate + self.auto_fx_conversion_rate
        shares = math.floor(budget / (price * (1.0 + proportional_rate)))
        while shares > 0 and self._order_total(shares, price) > budget:
            shares -= 1
        return shares

    def _order_total(self, shares: int, price: float) -> float:
        notional = shares * price
        return (
            notional
            + self._base_commission(shares, price)
            + notional * (self.slippage_rate + self.auto_fx_conversion_rate)
        )

    def _base_commission(self, shares: int, price: float) -> float:
        trade_value = shares * price
        commission = max(
            shares * self.base_commission_per_share,
            self.base_commission_minimum,
        )
        return min(commission, trade_value * self.base_commission_value_cap)


_EXECUTION_COST_MODEL = _ExecutionCostModel(
    slippage_rate=_SLIPPAGE,
    auto_fx_conversion_rate=_AUTO_FX_CONVERSION_RATE,
    base_commission_per_share=_TIERED_BASE_COMMISSION_PER_SHARE,
    base_commission_minimum=_TIERED_BASE_COMMISSION_MINIMUM,
    base_commission_value_cap=_TIERED_BASE_COMMISSION_VALUE_CAP,
)


@dataclass(frozen=True)
class SelectionResult:
    """The auditable forecasts and executable decision for one snapshot."""

    engine: SelectionEngineIdentity
    decision_engine_id: str
    assessments: tuple[SelectionAssessment, ...]
    exclusions: tuple[SelectionExclusion, ...]
    decision: ShadowDecision


class MarketImpliedSelectionEngine:
    """The mandatory no-alpha benchmark: select only market q of at least 70%."""

    identity = SelectionEngineIdentity(
        engine_id="market-implied-q70",
        model_artifact_id="market-implied-v1",
        training_cutoff=None,
    )

    def forecast(
        self,
        cases: tuple[CompletionCase, ...],
    ) -> tuple[CompletionForecast, ...]:
        return tuple(
            CompletionForecast(
                event_id=case.event_id,
                feature_timestamp=case.market_observed_at,
                model_probability=case.market_probability,
                lower_probability=case.market_probability_lower,
                selected=case.market_probability_lower >= 0.70,
                rank_score=case.market_probability_lower,
            )
            for case in cases
        )


class CashMergerSelector:
    """Value, validate, select, rank, and size deals behind one interface."""

    def __init__(
        self,
        engine: CompletionSelectionEngine | None = None,
        *,
        authority: SelectionAuthority = SelectionAuthority.MARKET_BASELINE,
        timeline: DealTimeline | None = None,
        break_value_model: BreakValueModel | None = None,
    ) -> None:
        self._engine = engine or MarketImpliedSelectionEngine()
        self._timeline = timeline or DealTimeline()
        self._break_value_model = break_value_model or BreakValueModel()
        self._engine_owns_decision = (
            engine is None or authority is SelectionAuthority.QUALIFIED_CHALLENGER
        )

    @property
    def engine_identity(self) -> SelectionEngineIdentity:
        """Return the identity used to freeze and retrieve this engine's evidence."""

        return self._engine.identity

    @property
    def decision_engine_id(self) -> str:
        """Return the engine allowed to control executable shadow positions."""

        if self._engine_owns_decision:
            return self._engine.identity.engine_id
        return MarketImpliedSelectionEngine.identity.engine_id

    def select(
        self,
        events: Iterable[EventObservation],
        marks: Iterable[MarketMark],
        *,
        as_of: datetime,
        capital: float,
    ) -> SelectionResult:
        if capital <= 0.0:
            raise SelectionInputError("shadow capital must be positive")
        marks_by_instrument = {
            mark.instrument_id: mark
            for mark in marks
            if _available(mark.observed_at, as_of)
        }
        cases: list[CompletionCase] = []
        exclusions: list[SelectionExclusion] = []
        histories = _histories_by_event(events, as_of)
        for event_id in sorted(histories):
            history = histories[event_id]
            case, exclusion = _completion_case(
                history,
                marks_by_instrument.get(history[-1].instrument_id),
                as_of,
                capital,
                timeline=self._timeline,
                break_value_model=self._break_value_model,
            )
            if case is not None:
                cases.append(case)
            if exclusion is not None:
                exclusions.append(exclusion)
        frozen_cases = tuple(cases)
        forecasts = self._engine.forecast(frozen_cases)
        assessments = _assess(
            frozen_cases,
            self._engine.identity,
            forecasts,
            as_of=as_of,
        )
        chosen = tuple(
            sorted(
                (
                    (case, assessment)
                    for case, assessment in zip(frozen_cases, assessments, strict=True)
                    if _selected_for_decision(
                        case,
                        assessment,
                        engine_owns_decision=self._engine_owns_decision,
                    )
                ),
                key=lambda item: (
                    -_decision_rank(
                        item[0],
                        item[1],
                        engine_owns_decision=self._engine_owns_decision,
                    ),
                    item[0].event_id,
                ),
            )[:_MAXIMUM_LIFECYCLE_SLOTS]
        )
        decision = _decision(chosen, as_of=as_of, capital=capital)
        return SelectionResult(
            self._engine.identity,
            self.decision_engine_id,
            assessments,
            tuple(exclusions),
            decision,
        )


def _completion_case(
    history: tuple[EventObservation, ...],
    mark: MarketMark | None,
    as_of: datetime,
    capital: float,
    *,
    timeline: DealTimeline,
    break_value_model: BreakValueModel,
) -> tuple[CompletionCase | None, SelectionExclusion | None]:
    event = history[-1]
    if event.status not in {EventStatus.ANNOUNCED, EventStatus.AMENDED}:
        return None, _exclusion(event, SelectionExclusionReason.INACTIVE)
    if event.offer_price is None or mark is None:
        return None, _exclusion(event, SelectionExclusionReason.MISSING_OFFER_OR_MARK)
    close_range = timeline.estimate(history, as_of=as_of)
    if close_range is None:
        return None, _exclusion(event, SelectionExclusionReason.TIMELINE_UNAVAILABLE)
    announced = datetime.fromisoformat(close_range.announced_at)
    if as_of.date() <= announced.date():
        return None, _exclusion(
            event, SelectionExclusionReason.ANNOUNCEMENT_NOT_YET_TRADEABLE
        )
    age = (as_of.date() - announced.date()).days
    remaining_days = max(
        (date.fromisoformat(close_range.expected_close) - as_of.date()).days,
        0,
    )
    discounted_offer = event.offer_price / (
        1.0 + mark.annual_cash_rate * remaining_days / 365.0
    )
    break_value = break_value_model.estimate(mark)
    if mark.close >= discounted_offer:
        return None, _exclusion(
            event, SelectionExclusionReason.NO_POSITIVE_DISCOUNTED_SPREAD
        )
    if break_value.central >= mark.close:
        return None, _exclusion(
            event, SelectionExclusionReason.BREAK_VALUE_UNIDENTIFIED
        )
    if mark.close > capital * _NAME_CAP:
        return None, _exclusion(event, SelectionExclusionReason.WHOLE_SHARE_NAME_CAP)
    if mark.median_dollar_volume < _MINIMUM_MEDIAN_DOLLAR_VOLUME:
        return None, _exclusion(event, SelectionExclusionReason.INSUFFICIENT_LIQUIDITY)
    raw_market_probability = _raw_probability(
        mark.close,
        discounted_offer,
        break_value.central,
    )
    market_probability = _bounded_probability(raw_market_probability)
    market_probability_lower = _bounded_probability(
        _raw_probability(mark.close, discounted_offer, break_value.upper)
    )
    market_probability_upper = _bounded_probability(
        _raw_probability(mark.close, discounted_offer, break_value.lower)
    )
    return CompletionCase(
        event_id=event.event_id,
        instrument_id=event.instrument_id,
        ticker=event.ticker,
        selection_as_of=as_of.isoformat(),
        event_observed_at=event.observed_at,
        market_observed_at=mark.observed_at,
        agreement_date=event.agreement_date,
        offer_price=event.offer_price,
        close=mark.close,
        expected_close=close_range.expected_close,
        latest_close=close_range.latest_close,
        discounted_offer=discounted_offer,
        fallback_price=break_value.central,
        break_value_lower=break_value.lower,
        break_value_upper=break_value.upper,
        raw_market_probability=raw_market_probability,
        market_probability=market_probability,
        market_probability_lower=market_probability_lower,
        market_probability_upper=market_probability_upper,
        break_loss=max((mark.close - break_value.central) / mark.close, 0.0),
        days_since_announcement=age,
    ), None


def _raw_probability(close: float, offer: float, break_value: float) -> float:
    if break_value >= close:
        return 0.0
    return (close - break_value) / (offer - break_value)


def _bounded_probability(raw_probability: float) -> float:
    return min(max(raw_probability, 0.0), 1.0)


def _exclusion(
    event: EventObservation,
    reason: SelectionExclusionReason,
) -> SelectionExclusion:
    return SelectionExclusion(
        event_id=event.event_id,
        instrument_id=event.instrument_id,
        ticker=event.ticker,
        reason=reason,
    )


def _assess(
    cases: tuple[CompletionCase, ...],
    identity: SelectionEngineIdentity,
    forecasts: tuple[CompletionForecast, ...],
    *,
    as_of: datetime,
) -> tuple[SelectionAssessment, ...]:
    _validate_identity(identity, as_of=as_of)
    forecasts_by_event = {forecast.event_id: forecast for forecast in forecasts}
    if len(forecasts_by_event) != len(forecasts):
        raise EngineCoverageError("completion engine returned duplicate event forecasts")
    expected = {case.event_id for case in cases}
    if set(forecasts_by_event) != expected:
        raise EngineCoverageError(
            "completion engine must forecast every presented event exactly once"
        )
    assessments: list[SelectionAssessment] = []
    for case in cases:
        forecast = forecasts_by_event[case.event_id]
        if not _available(forecast.feature_timestamp, as_of):
            raise EngineCausalityError(
                "completion forecast uses a future feature timestamp"
            )
        if not 0.0 <= forecast.model_probability <= 1.0:
            raise EngineProbabilityError(
                "model_probability must be between zero and one"
            )
        if not 0.0 <= forecast.lower_probability <= forecast.model_probability:
            raise EngineProbabilityError(
                "lower_probability must not exceed model_probability"
            )
        if not math.isfinite(forecast.rank_score):
            raise EngineRankingError("completion rank_score must be finite")
        assessments.append(
            SelectionAssessment(
                event_id=case.event_id,
                instrument_id=case.instrument_id,
                ticker=case.ticker,
                as_of=case.selection_as_of,
                raw_market_probability=case.raw_market_probability,
                market_probability=case.market_probability,
                market_probability_lower=case.market_probability_lower,
                market_probability_upper=case.market_probability_upper,
                expected_close=case.expected_close,
                latest_close=case.latest_close,
                discounted_offer=case.discounted_offer,
                break_value_lower=case.break_value_lower,
                break_value_central=case.fallback_price,
                break_value_upper=case.break_value_upper,
                completion_gain=(case.discounted_offer - case.close) / case.close,
                break_loss=case.break_loss,
                feature_timestamp=forecast.feature_timestamp,
                model_probability=forecast.model_probability,
                lower_probability=forecast.lower_probability,
                probability_edge=forecast.model_probability - case.market_probability,
                market_gross_expected_payoff=_expected_payoff(
                    case.market_probability,
                    completion_gain=(case.discounted_offer - case.close) / case.close,
                    break_loss=case.break_loss,
                ),
                model_gross_expected_payoff=_expected_payoff(
                    forecast.model_probability,
                    completion_gain=(case.discounted_offer - case.close) / case.close,
                    break_loss=case.break_loss,
                ),
                selected=forecast.selected,
                rank_score=forecast.rank_score,
            )
        )
    return tuple(assessments)


def _validate_identity(identity: SelectionEngineIdentity, *, as_of: datetime) -> None:
    if not identity.engine_id.strip():
        raise EngineIdentityError("completion engine_id must be non-empty")
    if not identity.model_artifact_id.strip():
        raise EngineIdentityError("model_artifact_id must be non-empty")
    if identity.training_cutoff is None:
        return
    try:
        training_cutoff = date.fromisoformat(identity.training_cutoff)
    except ValueError as error:
        raise EngineCausalityError("training_cutoff must be an ISO date") from error
    if training_cutoff > as_of.date():
        raise EngineCausalityError("training_cutoff exceeds selection as_of")


def _selected_for_decision(
    case: CompletionCase,
    assessment: SelectionAssessment,
    *,
    engine_owns_decision: bool,
) -> bool:
    if engine_owns_decision:
        return assessment.selected
    return case.market_probability_lower >= 0.70


def _decision_rank(
    case: CompletionCase,
    assessment: SelectionAssessment,
    *,
    engine_owns_decision: bool,
) -> float:
    return (
        assessment.rank_score
        if engine_owns_decision
        else case.market_probability_lower
    )


def _expected_payoff(
    probability: float,
    *,
    completion_gain: float,
    break_loss: float,
) -> float:
    return probability * completion_gain - (1.0 - probability) * break_loss


def _decision(
    chosen: tuple[tuple[CompletionCase, SelectionAssessment], ...],
    *,
    as_of: datetime,
    capital: float,
) -> ShadowDecision:
    if len(chosen) < _MINIMUM_CONCURRENT:
        return _cash_decision(as_of, capital)
    equal_weight = 1.0 / len(chosen)
    positions = tuple(
        position
        for case, assessment in chosen
        if (
            position := _whole_share_position(
                case,
                assessment,
                capital=capital,
                equal_weight=equal_weight,
            )
        )
        is not None
    )
    if len(positions) < _MINIMUM_CONCURRENT:
        return _cash_decision(as_of, capital)
    traded = sum(position.shares * position.price for position in positions)
    costs = _EXECUTION_COST_MODEL.quote_book(positions)
    return ShadowDecision(
        as_of=as_of.isoformat(),
        capital=capital,
        positions=positions,
        estimated_base_commission=_money(costs.base_commission),
        estimated_slippage=_money(costs.slippage),
        estimated_fx_conversion=_money(costs.fx_conversion),
        cash_reserve=_money(
            capital - traded - costs.total,
        ),
    )


def _whole_share_position(
    case: CompletionCase,
    assessment: SelectionAssessment,
    *,
    capital: float,
    equal_weight: float,
) -> ShadowPosition | None:
    weight = min(_NAME_CAP, equal_weight, _BREAK_LOSS_CAP / case.break_loss)
    budget = capital * weight
    shares = _EXECUTION_COST_MODEL.affordable_shares(budget, case.close)
    if shares < 1:
        return None
    return ShadowPosition(
        event_id=case.event_id,
        instrument_id=case.instrument_id,
        ticker=case.ticker,
        shares=shares,
        price=case.close,
        target_weight=round(shares * case.close / capital, 12),
        q_market=case.market_probability,
        model_probability=assessment.model_probability,
        probability_edge=assessment.probability_edge,
        break_loss=case.break_loss,
    )


def _money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _cash_decision(as_of: datetime, capital: float) -> ShadowDecision:
    return ShadowDecision(
        as_of=as_of.isoformat(),
        capital=capital,
        positions=(),
        estimated_base_commission=0.0,
        estimated_slippage=0.0,
        estimated_fx_conversion=0.0,
        cash_reserve=capital,
    )


def _histories_by_event(
    observations: Iterable[EventObservation], as_of: datetime
) -> dict[str, tuple[EventObservation, ...]]:
    histories: dict[str, list[EventObservation]] = {}
    for observation in sorted(
        (item for item in observations if _available(item.observed_at, as_of)),
        key=lambda item: (item.observed_at, item.event_id, item.source_accession),
    ):
        histories.setdefault(observation.event_id, []).append(observation)
    return {event_id: tuple(history) for event_id, history in histories.items()}


def _available(observed_at: str, as_of: datetime) -> bool:
    observed = datetime.fromisoformat(observed_at)
    if observed.tzinfo is None or as_of.tzinfo is None:
        raise SelectionInputError("selection timestamps must include a timezone")
    return observed <= as_of
