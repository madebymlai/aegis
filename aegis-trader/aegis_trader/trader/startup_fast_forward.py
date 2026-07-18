"""Replay-first live startup recovery behind one concrete lifecycle."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeAlias

from aegis_data.bar_type import timeframe_to_ns
from aegis_data.marking import RawBarTypeResolver
from nautilus_trader.core.data import Data
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.bundles.book import AssembledBook
from aegis_trader.domain.roll import Halt, RollEvent, SubscribeBars
from aegis_trader.domain.startup import StartupGate, StartupResult
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.book_startup import (
    BootIntentBatch,
    SubscribeQuoteTicks,
    startup_history_start,
)
from aegis_trader.trader.pipeline import (
    CompletedRebalancePeriod,
    DueSleeve,
    RebalancePipeline,
    RebalanceRequest,
)
from aegis_trader.trader.roll_desk import RollDesk


@dataclass(frozen=True, order=True)
class HistoryRequestKey:
    """Opaque identity pairing one physical history request with its callback."""

    value: int


@dataclass(frozen=True)
class HistoryRequest:
    """One exact physical Nautilus history request."""

    key: HistoryRequestKey
    bar_type: BarType
    start: datetime
    end: datetime
    update_catalog: bool = True


@dataclass(frozen=True)
class RecoveryProgress:
    """Correctness-derived recovery work visible to the operator."""

    loaded_requests: int
    planned_requests: int
    received_events: int
    book_activity: int | None


@dataclass(frozen=True)
class Recovering:
    """Recovery is still order-gated."""

    requests: tuple[HistoryRequest, ...]
    progress: RecoveryProgress


@dataclass(frozen=True)
class Ready:
    """Recovery completed and these live subscriptions may be released."""

    intents: BootIntentBatch
    book_activity: int | None
    resume_periods: tuple[tuple[SleeveName, int], ...]
    stream_watermarks: tuple[tuple[BarType, int], ...]
    startup_result: StartupResult


RecoveryUpdate: TypeAlias = Recovering | Ready | Halt

RECOVERY_TOPIC = "aegis.startup.recovery"


class RecoveryProtocolError(RuntimeError):
    """The adapter called the recovery lifecycle in an impossible order."""


class _BookMarketClock:
    """Own per-Sleeve market periods across recovery and live delivery."""

    def __init__(
        self,
        *,
        book: AssembledBook,
        bar_type_resolver: RawBarTypeResolver,
    ) -> None:
        consumers: dict[BarType, dict[SleeveName, None]] = {}
        continuous_consumers: dict[InstrumentId, dict[SleeveName, None]] = {}
        for sleeve, streams in book.sleeve_streams.items():
            for stream in streams:
                marking = bar_type_resolver.resolve(
                    stream.instrument_id, stream.timeframe
                )
                for bar_type in marking.mark_bars:
                    consumers.setdefault(bar_type, {})[sleeve] = None
        for sleeve, bundle in book.sleeves.items():
            for continuous_id in bundle.contract.continuous_instrument_ids:
                continuous_consumers.setdefault(continuous_id, {})[sleeve] = None

        self._consumers = {
            bar_type: tuple(names) for bar_type, names in consumers.items()
        }
        self._continuous_consumers = {
            continuous_id: tuple(names)
            for continuous_id, names in continuous_consumers.items()
        }
        self._period_ns = {
            name: timeframe_to_ns(bundle.contract.timeframe)
            for name, bundle in book.sleeves.items()
        }
        self._current_period: dict[SleeveName, int | None] = {
            name: None for name in book.sleeves
        }

    def consumers(
        self,
        bar_type: BarType,
        *,
        continuous_id: InstrumentId | None = None,
    ) -> tuple[SleeveName, ...]:
        """Return the Sleeves whose market clock this physical bar advances."""
        direct = self._consumers.get(bar_type)
        if direct is not None:
            return direct
        if continuous_id is None:
            return ()
        return self._continuous_consumers.get(continuous_id, ())

    def advance(
        self, sleeve: SleeveName, timestamp_ns: int
    ) -> CompletedRebalancePeriod | None:
        """Fold one event time and return the period it completed, if any."""
        period_ns = self._period_ns[sleeve]
        period = timestamp_ns // period_ns
        completed = self._current_period[sleeve]
        self._current_period[sleeve] = period
        if completed is None or period == completed:
            return None
        return CompletedRebalancePeriod(period=completed, period_ns=period_ns)

    def resume_periods(self) -> tuple[tuple[SleeveName, int], ...]:
        return tuple(
            (sleeve, period)
            for sleeve, period in sorted(
                self._current_period.items(), key=lambda item: item[0].value
            )
            if period is not None
        )


class StartupFastForward:
    """Plan, collect, and replay a Book's bounded startup history."""

    def __init__(
        self,
        *,
        book: AssembledBook,
        pipeline: RebalancePipeline,
        roll_desk: RollDesk | None,
        bar_type_resolver: RawBarTypeResolver,
        fx_reference_pairs: Sequence[InstrumentId],
    ) -> None:
        self._book = book
        self._pipeline = pipeline
        self._roll_desk = roll_desk
        self._resolver = bar_type_resolver
        self._fx_reference_pairs = tuple(fx_reference_pairs)
        self._requests: dict[HistoryRequestKey, HistoryRequest] = {}
        self._required_events: dict[HistoryRequestKey, int] = {}
        self._received: dict[tuple[BarType, int], Bar] = {}
        self._loaded: set[HistoryRequestKey] = set()
        self._market_clock = _BookMarketClock(
            book=book,
            bar_type_resolver=bar_type_resolver,
        )
        self._terminal: Ready | Halt | None = None
        self._begun = False
        self._book_activity: int | None = None
        self._startup_result: StartupResult | None = None
        self._continuous_history_starts: dict[str, datetime] = {}
        self._continuous_root_by_bar_type: dict[BarType, str] = {}

    def begin(self, *, through: datetime) -> RecoveryUpdate:
        """Plan exact history requests through the startup event-time boundary."""
        if self._begun:
            raise RecoveryProtocolError("startup fast-forward began more than once")
        self._begun = True

        startup = self._pipeline.startup_check()
        self._startup_result = startup
        if startup.should_halt:
            return self._halt(
                startup.halt_gate or StartupGate.ACCOUNT_INTEGRITY,
                startup.halt_reason or "startup integrity check failed",
            )

        requests: list[HistoryRequest] = []
        next_key = 0
        continuous_ids = {
            declaration.continuous_id
            for declaration in self._book.continuous_declarations.values()
        }
        for requirement in self._book.required_streams:
            stream = requirement.stream
            if stream.instrument_id in continuous_ids:
                continue
            marking = self._resolver.resolve(stream.instrument_id, stream.timeframe)
            start = startup_history_start(
                through,
                timeframe=stream.timeframe,
                required_bar_window=requirement.history_bars,
            )
            for bar_type in marking.mark_bars:
                key = HistoryRequestKey(next_key)
                next_key += 1
                request = HistoryRequest(key, bar_type, start, through)
                self._requests[key] = request
                self._required_events[key] = requirement.history_bars
                requests.append(request)

        if self._book.continuous_declarations:
            if self._roll_desk is None:
                return self._halt(
                    StartupGate.CONTINUOUS_IDENTITY,
                    "continuous futures declared without a Roll Desk",
                )
            self._continuous_history_starts = {
                root: startup_history_start(
                    through,
                    timeframe=declaration.timeframe,
                    required_bar_window=self._book.continuous_history_bars[root],
                )
                for root, declaration in self._book.continuous_declarations.items()
            }
            start_by_timeframe = {
                declaration.timeframe: min(
                    self._continuous_history_starts[root]
                    for root, candidate in self._book.continuous_declarations.items()
                    if candidate.timeframe == declaration.timeframe
                )
                for declaration in self._book.continuous_declarations.values()
            }
            try:
                recovery_streams = self._roll_desk.recovery_streams(
                    self._book.continuous_declarations
                )
            except Exception as exc:
                return self._halt(
                    StartupGate.RECOVERY_HISTORY,
                    f"failed to resolve continuous recovery streams: {exc}",
                )
            for root, instrument_id, timeframe in recovery_streams:
                marking = self._resolver.resolve(instrument_id, timeframe)
                for bar_type in marking.mark_bars:
                    key = HistoryRequestKey(next_key)
                    next_key += 1
                    request = HistoryRequest(
                        key,
                        bar_type,
                        start_by_timeframe[timeframe],
                        through,
                    )
                    self._requests[key] = request
                    self._required_events[key] = 0
                    self._continuous_root_by_bar_type[bar_type] = root
                    requests.append(request)

        if not requests:
            return self._ready()
        return Recovering(tuple(requests), self._progress())

    def receive_history(self, data: Data) -> RecoveryUpdate:
        """Collect one historical delivery without exposing arrival order to replay."""
        if self._terminal is not None:
            return self._terminal
        self._require_recovering()
        if not isinstance(data, Bar):
            return Recovering((), self._progress())
        matching = tuple(
            request
            for request in self._requests.values()
            if request.bar_type == data.bar_type
        )
        if not matching:
            return Recovering((), self._progress())
        if not any(
            int(request.start.timestamp() * 1_000_000_000)
            <= data.ts_event
            <= int(request.end.timestamp() * 1_000_000_000)
            for request in matching
        ):
            return self._halt(
                StartupGate.RECOVERY_HISTORY,
                f"historical bar outside requested interval: {data.bar_type} at {data.ts_event}",
            )

        identity = (data.bar_type, data.ts_event)
        existing = self._received.get(identity)
        if existing is not None and existing != data:
            return self._halt(
                StartupGate.RECOVERY_HISTORY,
                f"conflicting historical bars for {data.bar_type} at {data.ts_event}",
            )
        self._received[identity] = data
        return Recovering((), self._progress())

    def history_loaded(self, request: HistoryRequestKey) -> RecoveryUpdate:
        """Close one physical request and replay after the Book-wide barrier."""
        if self._terminal is not None:
            return self._terminal
        self._require_recovering()
        if request not in self._requests:
            return self._halt(
                StartupGate.RECOVERY_HISTORY,
                f"unknown history request key {request.value}",
            )
        self._loaded.add(request)
        if len(self._loaded) != len(self._requests):
            return Recovering((), self._progress())

        incomplete = tuple(
            key
            for key, planned in self._requests.items()
            if self._received_count(planned.bar_type) < self._required_events[key]
        )
        if incomplete:
            keys = [key.value for key in incomplete]
            return self._halt(
                StartupGate.RECOVERY_HISTORY,
                f"incomplete required history for request keys {keys}",
            )
        marking_halt = self._validate_marking_pairs()
        if marking_halt is not None:
            return marking_halt

        if self._roll_desk is not None and self._book.continuous_declarations:
            effective_starts = dict(self._continuous_history_starts)
            for root in self._book.continuous_declarations:
                timestamps = [
                    timestamp
                    for (bar_type, timestamp) in self._received
                    if self._continuous_root_by_bar_type.get(bar_type) == root
                ]
                if not timestamps:
                    return self._halt(
                        StartupGate.RECOVERY_HISTORY,
                        f"continuous root {root!r} received no historical bars",
                    )
                first_event = datetime.fromtimestamp(
                    min(timestamps) / 1_000_000_000,
                    tz=timezone.utc,
                )
                effective_starts[root] = max(effective_starts[root], first_event)
            start_outcome = self._roll_desk.start_recovery(
                declarations=self._book.continuous_declarations,
                history_starts=effective_starts,
            )
            if start_outcome:
                outcome = start_outcome[0]
                if isinstance(outcome, Halt):
                    self._terminal = outcome
                    return outcome
        replay_halt = self._replay()
        if replay_halt is not None:
            return replay_halt
        for root, declaration in self._book.continuous_declarations.items():
            series = (
                self._roll_desk.series(declaration.continuous_id)
                if self._roll_desk
                else None
            )
            required = self._book.continuous_history_bars[root]
            if series is None or len(series) < required:
                return self._halt(
                    StartupGate.RECOVERY_HISTORY,
                    f"continuous root {root!r} recovered {0 if series is None else len(series)} bars; required {required}",
                )
        return self._ready()

    def _replay(self) -> Halt | None:
        by_timestamp: dict[int, list[Bar]] = {}
        for bar in self._received.values():
            by_timestamp.setdefault(bar.ts_event, []).append(bar)

        for timestamp_ns in sorted(by_timestamp):
            bars = sorted(
                by_timestamp[timestamp_ns],
                key=lambda bar: str(bar.bar_type),
            )
            marks: dict[InstrumentId, float] = {}
            due: dict[SleeveName, CompletedRebalancePeriod] = {}
            for bar in bars:
                continuous_id = None
                if self._roll_desk is not None:
                    continuous_id = self._roll_desk.continuous_id(
                        bar.bar_type.instrument_id
                    )
                roll_halt = self._apply_rolls(bar)
                if roll_halt is not None:
                    return roll_halt
                observed_id = continuous_id or bar.bar_type.instrument_id
                marks[observed_id] = float(bar.close)
                for sleeve in self._market_clock.consumers(
                    bar.bar_type,
                    continuous_id=continuous_id,
                ):
                    completed = self._market_clock.advance(sleeve, timestamp_ns)
                    if completed is not None:
                        due[sleeve] = completed
            self._project_marks(by_timestamp[timestamp_ns], marks)
            request = RebalanceRequest(
                due=tuple(
                    DueSleeve(sleeve=name, period=period)
                    for name, period in sorted(
                        due.items(), key=lambda item: item[0].value
                    )
                ),
                timestamp_ns=timestamp_ns,
            )
            self._pipeline.recover_market(request, marks)
            self._book_activity = timestamp_ns
        return None

    def _project_marks(
        self,
        bars: Sequence[Bar],
        marks: dict[InstrumentId, float],
    ) -> None:
        latest = {bar.bar_type: bar for bar in bars}
        continuous_ids = {
            declaration.continuous_id
            for declaration in self._book.continuous_declarations.values()
        }
        for requirement in self._book.required_streams:
            stream = requirement.stream
            if stream.instrument_id in continuous_ids:
                continue
            marking = self._resolver.resolve(stream.instrument_id, stream.timeframe)
            observed = {
                bar_type: latest.get(bar_type) for bar_type in marking.mark_bars
            }
            if any(bar is None for bar in observed.values()):
                continue
            derived = marking.derived_mark(observed)
            if derived is not None:
                marks[stream.instrument_id] = float(derived)
            elif len(marking.mark_bars) == 1:
                bar = observed[marking.mark_bars[0]]
                if bar is not None:
                    marks[stream.instrument_id] = float(bar.close)

    def _validate_marking_pairs(self) -> Halt | None:
        for requirement in self._book.required_streams:
            stream = requirement.stream
            marking = self._resolver.resolve(stream.instrument_id, stream.timeframe)
            if len(marking.mark_bars) < 2:
                continue
            timestamp_sets = [
                {
                    timestamp
                    for (observed, timestamp) in self._received
                    if observed == bar_type
                }
                for bar_type in marking.mark_bars
            ]
            if any(
                timestamps != timestamp_sets[0] for timestamps in timestamp_sets[1:]
            ):
                return self._halt(
                    StartupGate.RECOVERY_HISTORY,
                    f"incomplete same-timestamp marking inputs for {stream.instrument_id.value}",
                )
        return None

    def _apply_rolls(self, bar: Bar) -> Halt | None:
        if self._roll_desk is None:
            return None
        for intent in self._roll_desk.on_recovery_bar(bar):
            if isinstance(intent, RollEvent):
                self._pipeline.apply_roll(intent)
            elif isinstance(intent, Halt):
                self._terminal = intent
                return intent
        return None

    def _ready(self) -> Ready:
        if self._startup_result is None:
            raise RecoveryProtocolError("startup fast-forward completed before begin")
        subscriptions = [
            SubscribeBars(
                requirement.stream.instrument_id,
                requirement.stream.timeframe,
            )
            for requirement in self._book.required_streams
            if requirement.stream.instrument_id
            not in {
                declaration.continuous_id
                for declaration in self._book.continuous_declarations.values()
            }
        ]
        roll_intents = self._roll_desk.live_intents() if self._roll_desk else ()
        quotes = [
            SubscribeQuoteTicks(instrument_id)
            for instrument_id in sorted(
                self._fx_reference_pairs, key=lambda item: item.value
            )
        ]
        ready = Ready(
            tuple((*subscriptions, *roll_intents, *quotes)),
            self._book_activity,
            self._market_clock.resume_periods(),
            tuple(
                sorted(
                    (
                        (
                            bar_type,
                            max(
                                timestamp
                                for observed, timestamp in self._received
                                if observed == bar_type
                            ),
                        )
                        for bar_type in {
                            observed for observed, _timestamp in self._received
                        }
                    ),
                    key=lambda item: str(item[0]),
                )
            ),
            self._startup_result,
        )
        self._terminal = ready
        return ready

    def _halt(self, gate: StartupGate, reason: str) -> Halt:
        halt = Halt(gate, reason)
        self._terminal = halt
        return halt

    def _progress(self) -> RecoveryProgress:
        return RecoveryProgress(
            loaded_requests=len(self._loaded),
            planned_requests=len(self._requests),
            received_events=len(self._received),
            book_activity=self._book_activity,
        )

    def _received_count(self, bar_type: BarType) -> int:
        return sum(1 for observed, _timestamp in self._received if observed == bar_type)

    def _require_recovering(self) -> None:
        if not self._begun:
            raise RecoveryProtocolError(
                "startup fast-forward received data before begin"
            )
        if self._terminal is not None:
            raise RecoveryProtocolError(
                "startup fast-forward received data after terminal outcome"
            )


__all__ = [
    "HistoryRequest",
    "HistoryRequestKey",
    "Ready",
    "Recovering",
    "RecoveryProgress",
    "RecoveryProtocolError",
    "RecoveryUpdate",
    "RECOVERY_TOPIC",
    "StartupFastForward",
]
