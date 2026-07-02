"""Book startup gate funnel."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, TypeAlias

from aegis_data.bar_type import timeframe_to_ns
from aegis_runtime import ExecutionBundle
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.data.market_data import MarketDataPort
from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.book_timeframe import MixedTimeframeError, resolve_book_timeframe
from aegis_trader.domain.roll import Halt, RequestBars, RollIntent, RollIntentBatch, SubscribeBars
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.startup import StartupGate, StartupResult
from aegis_trader.domain.types import SleeveName
from aegis_trader.portfolio import BookStatePort
from aegis_trader.trader.pipeline import RebalancePipeline

_LIVE_WARMUP_CALENDAR_MULTIPLIER: int = 3


class RollStartupPort(Protocol):
    def start(
        self,
        *,
        timeframe: str,
        history_start: datetime,
        end: datetime,
        warmup: bool,
    ) -> RollIntentBatch:
        """Materialize continuous roots and return front-leg startup intents."""
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
    timeframe: str
    startup_result: StartupResult
    intents: BootIntentBatch


def bootstrap(
    *,
    now: datetime,
    book: BookConfig,
    sleeve_to_bundle: Mapping[SleeveName, ExecutionBundle],
    ledger: SleeveLedger,
    book_state: BookStatePort,
    market_data: MarketDataPort,
    roll_desk: RollStartupPort,
    fx_reference_pairs: Sequence[InstrumentId],
    warmup_cache_on_start: bool,
) -> BootResult | Halt:
    """Run the startup gates and return either the boot values or a typed halt."""
    try:
        timeframe = resolve_book_timeframe(
            bundle.contract.timeframe for bundle in sleeve_to_bundle.values()
        )
    except MixedTimeframeError as exc:
        return Halt(StartupGate.BOOK_TIMEFRAME, str(exc))

    pipeline = RebalancePipeline(
        book_state=book_state,
        market_data=market_data,
        book=book,
        sleeve_to_bundle=sleeve_to_bundle,
        ledger=ledger,
    )
    startup_result = pipeline.startup_check()
    if startup_result.should_halt:
        return _halt_from_startup_result(startup_result)

    history_start = startup_history_start(
        now,
        timeframe=timeframe,
        lookback_bars=max(bundle.contract.lookback_bars for bundle in sleeve_to_bundle.values()),
    )
    roll_intents = roll_desk.start(
        timeframe=timeframe,
        history_start=history_start,
        end=now,
        warmup=warmup_cache_on_start,
    )
    halt = _halt_from(roll_intents)
    if halt is not None:
        return halt

    intents: list[BootIntent] = list(roll_intents)
    native_ids = _native_instrument_ids(sleeve_to_bundle)
    for instrument_id in native_ids:
        intents.append(SubscribeBars(instrument_id=instrument_id, timeframe=timeframe))
        if warmup_cache_on_start:
            intents.append(
                RequestBars(
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                    start=history_start,
                    end=now,
                )
            )
    for instrument_id in sorted(fx_reference_pairs, key=lambda item: item.value):
        intents.append(SubscribeQuoteTicks(instrument_id))

    return BootResult(
        pipeline=pipeline,
        timeframe=timeframe,
        startup_result=startup_result,
        intents=tuple(intents),
    )


def startup_history_start(
    end: datetime,
    *,
    timeframe: str,
    lookback_bars: int,
) -> datetime:
    periods = max(lookback_bars + 1, 1) * _LIVE_WARMUP_CALENDAR_MULTIPLIER
    span_ns = timeframe_to_ns(timeframe) * periods
    return end - timedelta(microseconds=span_ns // 1000)


def _native_instrument_ids(
    sleeve_to_bundle: Mapping[SleeveName, ExecutionBundle]
) -> tuple[InstrumentId, ...]:
    instrument_ids = {
        instrument_id
        for bundle in sleeve_to_bundle.values()
        for instrument_id in bundle.contract.native_instrument_ids
    }
    return tuple(sorted(instrument_ids, key=lambda instrument_id: instrument_id.value))


def _halt_from(intents: RollIntentBatch) -> Halt | None:
    for intent in intents:
        if isinstance(intent, Halt):
            return intent
    return None


def _halt_from_startup_result(result: StartupResult) -> Halt:
    if result.halt_gate is None or result.halt_reason is None:
        raise RuntimeError("startup check halted without a gate and reason")
    return Halt(result.halt_gate, result.halt_reason)
