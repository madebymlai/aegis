"""Book startup gate funnel."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, TypeAlias

from aegis_data.bar_type import timeframe_to_ns
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.bundles.book import (
    AssembledBook,
    ContinuousRootDeclaration,
)
from aegis_trader.data.market_data import MarketDataPort
from aegis_trader.domain.roll import Halt, RequestBars, RollIntent, RollIntentBatch, SubscribeBars
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.startup import StartupResult
from aegis_trader.portfolio import BookStatePort
from aegis_trader.trader.pipeline import RebalancePipeline

# Calendar inflation from "bars of lookback" to "wall-clock span requested":
# a daily bar accrues every calendar day the venue trades (365/252 ≈ 1.45), so
# 3 is a generous daily cover.  An intraday bar only accrues inside the venue
# session (~6.5h of 24 for equities), so the same lookback needs a much wider
# calendar span: ~24/6.5 session coverage × ~7/5 weekend inflation ≈ 5.2 — 6 is
# the intraday analogue of the daily 3 (aegis-rd-9qkr.1 amendment).
_DAILY_WARMUP_CALENDAR_MULTIPLIER: int = 3
_INTRADAY_WARMUP_CALENDAR_MULTIPLIER: int = 6

_NS_PER_DAY: int = 86_400_000_000_000


class RollStartupPort(Protocol):
    def start(
        self,
        *,
        timeframe: str,
        history_start: datetime,
        end: datetime,
        warmup: bool,
        declarations: Mapping[str, ContinuousRootDeclaration],
    ) -> RollIntentBatch:
        """Materialize the declared continuous roots and return front-leg startup intents."""
        ...


@dataclass(frozen=True)
class SubscribeQuoteTicks:
    """Subscribe to FX reference-pair quotes."""

    instrument_id: InstrumentId


BootIntent: TypeAlias = RollIntent | SubscribeQuoteTicks
BootIntentBatch: TypeAlias = tuple[BootIntent, ...]


@dataclass(frozen=True)
class BootResult:
    """A successful book boot."""

    pipeline: RebalancePipeline
    startup_result: StartupResult
    intents: BootIntentBatch


def bootstrap(
    *,
    now: datetime,
    book: AssembledBook,
    ledger: SleeveLedger,
    book_state: BookStatePort,
    market_data: MarketDataPort,
    roll_desk: RollStartupPort,
    fx_reference_pairs: Sequence[InstrumentId],
    warmup_cache_on_start: bool,
) -> BootResult | Halt:
    """Run the startup gates and return either the boot values or a typed halt."""
    pipeline = RebalancePipeline(
        book_state=book_state,
        market_data=market_data,
        book=book,
        ledger=ledger,
    )
    startup_result = pipeline.startup_check()
    if startup_result.should_halt:
        return _halt_from_startup_result(startup_result)

    roll_timeframe = _roll_timeframe(book)
    roll_intents = roll_desk.start(
        timeframe=roll_timeframe,
        history_start=startup_history_start(
            now,
            timeframe=roll_timeframe,
            required_bar_window=book.continuous_history_bars,
        ),
        end=now,
        warmup=warmup_cache_on_start,
        declarations=book.continuous_declarations,
    )
    halt = _halt_from(roll_intents)
    if halt is not None:
        return halt

    intents: list[BootIntent] = list(roll_intents)
    for requirement in book.required_streams:
        stream = requirement.stream
        intents.append(
            SubscribeBars(instrument_id=stream.instrument_id, timeframe=stream.timeframe)
        )
        if warmup_cache_on_start:
            intents.append(
                RequestBars(
                    instrument_id=stream.instrument_id,
                    timeframe=stream.timeframe,
                    start=startup_history_start(
                        now,
                        timeframe=stream.timeframe,
                        required_bar_window=requirement.history_bars,
                    ),
                    end=now,
                )
            )
    for instrument_id in sorted(fx_reference_pairs, key=lambda item: item.value):
        intents.append(SubscribeQuoteTicks(instrument_id))

    return BootResult(
        pipeline=pipeline,
        startup_result=startup_result,
        intents=tuple(intents),
    )


def _roll_timeframe(book: AssembledBook) -> str:
    """The Roll Desk's one timeframe: the futures Sleeves' shared cadence, or
    (for a Book with no continuous declarations, where it is inert) the first
    Sleeve's contract timeframe."""
    if book.continuous_timeframe is not None:
        return book.continuous_timeframe
    return next(iter(book.sleeves.values())).contract.timeframe


def startup_history_start(
    end: datetime,
    *,
    timeframe: str,
    required_bar_window: int,
) -> datetime:
    periods = max(required_bar_window, 1) * _warmup_calendar_multiplier(timeframe)
    span_ns = timeframe_to_ns(timeframe) * periods
    return end - timedelta(microseconds=span_ns // 1000)


def _warmup_calendar_multiplier(timeframe: str) -> int:
    if timeframe_to_ns(timeframe) < _NS_PER_DAY:
        return _INTRADAY_WARMUP_CALENDAR_MULTIPLIER
    return _DAILY_WARMUP_CALENDAR_MULTIPLIER


def _halt_from(intents: RollIntentBatch) -> Halt | None:
    for intent in intents:
        if isinstance(intent, Halt):
            return intent
    return None


def _halt_from_startup_result(result: StartupResult) -> Halt:
    if result.halt_gate is None or result.halt_reason is None:
        raise RuntimeError("startup check halted without a gate and reason")
    return Halt(result.halt_gate, result.halt_reason)
