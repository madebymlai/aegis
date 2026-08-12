"""Nautilus-free live Roll lifecycle state machine."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone

import pandas as pd
from aegis_data.catalog import CatalogBackedDataPort
from aegis_data.continuous_contract_model import (
    ROLL_VOLUME_LOOKBACK,
    ContinuousContractModel,
)
from aegis_data.roll import DatedContract
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.bundles.book import ContinuousRootDeclaration
from aegis_trader.domain.roll import (
    Halt,
    RequestBars,
    RequestInstrument,
    RollEvent,
    RollIntentBatch,
    SubscribeBars,
    UnsubscribeBars,
)
from aegis_trader.domain.startup import StartupGate

InstrumentPresence = Callable[[InstrumentId], bool]
_SubscriptionIntentBatch = tuple[
    SubscribeBars | RequestInstrument | UnsubscribeBars, ...
]


class RollDesk:
    """Own the live continuous-root roll lifecycle behind intent batches."""

    def __init__(
        self,
        *,
        catalog_port: CatalogBackedDataPort,
        instrument_present: InstrumentPresence,
    ) -> None:
        self._catalog_port = catalog_port
        self._instrument_present = instrument_present
        self._models: dict[InstrumentId, ContinuousContractModel] = {}
        self._timeframe_by_continuous_id: dict[InstrumentId, str] = {}
        self._leg_to_continuous_id: dict[InstrumentId, InstrumentId] = {}
        self._recovery_event_ns: dict[InstrumentId, int] = {}
        self._pending_leg_subscriptions: dict[InstrumentId, InstrumentId] = {}
        self._root_by_continuous_id: dict[InstrumentId, str] = {}
        self._history_start_by_continuous_id: dict[InstrumentId, datetime] = {}
        self._subscribed_legs: dict[InstrumentId, set[InstrumentId]] = {}

    def start(
        self,
        *,
        end: datetime,
        warmup: bool,
        declarations: Mapping[str, ContinuousRootDeclaration],
        history_starts: Mapping[str, datetime],
    ) -> RollIntentBatch:
        """Materialize the declared roots and emit front-leg warmup/subscription intents.

        ``declarations`` is the already coherent cross-Sleeve union built by book
        startup; each root materialises under its declaration's bundle-recorded
        adjustment mode and its own declared timeframe (one root, one owning
        Sleeve, one stream — aegis-rd-9qkr.5), so the emitted roll ``Rebasing``
        is multiplicative for ratio and additive for spread automatically, and
        a roll is decided exactly once per root.
        """
        models: dict[InstrumentId, ContinuousContractModel] = {}
        timeframe_by_continuous_id: dict[InstrumentId, str] = {}
        leg_to_continuous_id: dict[InstrumentId, InstrumentId] = {}
        root_by_continuous_id: dict[InstrumentId, str] = {}
        history_start_by_continuous_id: dict[InstrumentId, datetime] = {}
        subscribed_legs: dict[InstrumentId, set[InstrumentId]] = {}
        intents: list[RequestBars | SubscribeBars] = []

        for root, declaration in sorted(declarations.items()):
            history_start = history_starts[root]
            model = ContinuousContractModel(
                self._catalog_port,
                root,
                start=history_start.date().isoformat(),
                timeframe=declaration.timeframe,
                adjustment_mode=declaration.adjustment_mode,
            )
            model.materialize(end=end.date().isoformat())
            if model.continuous_id != declaration.continuous_id:
                return (
                    Halt(
                        gate=StartupGate.CONTINUOUS_IDENTITY,
                        reason=(
                            f"continuous root {root!r} materialized as "
                            f"{model.continuous_id.value}, expected "
                            f"{declaration.continuous_id.value}"
                        ),
                    ),
                )

            front_leg = model.front_leg
            models[declaration.continuous_id] = model
            timeframe_by_continuous_id[declaration.continuous_id] = (
                declaration.timeframe
            )
            leg_to_continuous_id[front_leg] = declaration.continuous_id
            root_by_continuous_id[declaration.continuous_id] = root
            history_start_by_continuous_id[declaration.continuous_id] = history_start
            live_legs = self._live_legs(root, history_start=history_start, end=end)
            subscribed_legs[declaration.continuous_id] = {
                InstrumentId.from_str(leg.symbol) for leg in live_legs
            }
            for instrument_id in sorted(
                subscribed_legs[declaration.continuous_id],
                key=lambda item: item.value,
            ):
                if warmup:
                    intents.append(
                        RequestBars(
                            instrument_id=instrument_id,
                            timeframe=declaration.timeframe,
                            start=max(history_start, end - ROLL_VOLUME_LOOKBACK),
                            end=end,
                        )
                    )
                intents.append(
                    SubscribeBars(
                        instrument_id=instrument_id,
                        timeframe=declaration.timeframe,
                    )
                )

        self._models = models
        self._timeframe_by_continuous_id = timeframe_by_continuous_id
        self._leg_to_continuous_id = leg_to_continuous_id
        self._root_by_continuous_id = root_by_continuous_id
        self._history_start_by_continuous_id = history_start_by_continuous_id
        self._subscribed_legs = subscribed_legs
        return tuple(intents)

    def on_bar(self, bar: Bar) -> RollIntentBatch:
        """Fold a front-leg bar into its root and emit roll intents when the front advances."""
        continuous_id = self._leg_to_continuous_id.get(bar.bar_type.instrument_id)
        if continuous_id is None:
            return ()

        model = self._models[continuous_id]
        front_before = model.front_leg
        model.on_bar(bar)
        front_after = model.front_leg
        intents = list(self._refresh_subscriptions(continuous_id, bar.ts_event))
        if front_after != front_before:
            del self._leg_to_continuous_id[front_before]
            self._leg_to_continuous_id[front_after] = continuous_id
            intents.append(
                RollEvent(continuous_id=continuous_id, rebasing=model.last_rebasing)
            )
        return tuple(intents)

    def recovery_streams(
        self,
        declarations: Mapping[str, ContinuousRootDeclaration],
        history_starts: Mapping[str, datetime],
        end: datetime,
    ) -> tuple[tuple[str, InstrumentId, str], ...]:
        """Return every dated leg whose bars can causally determine a declared root."""
        streams = {
            (root, InstrumentId.from_str(leg.symbol), declaration.timeframe)
            for root, declaration in declarations.items()
            for leg in self._recovery_legs(
                root,
                start=history_starts[root],
                end=end,
            )
        }
        return tuple(
            sorted(streams, key=lambda item: (item[0], item[1].value, item[2]))
        )

    def _recovery_legs(
        self,
        root: str,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[DatedContract, ...]:
        """Return interval legs plus the successor whose volume can trigger a Roll."""
        legs = tuple(
            leg
            for leg in self._catalog_port.resolve_continuous(root).legs
            if leg.last_trade >= start.date()
        )
        end_leg = next(
            (index for index, leg in enumerate(legs) if leg.last_trade >= end.date()),
            len(legs) - 1,
        )
        return legs[: end_leg + 2]

    def _live_legs(
        self,
        root: str,
        *,
        history_start: datetime,
        end: datetime,
    ) -> tuple[DatedContract, ...]:
        return self._recovery_legs(
            root,
            start=max(history_start, end - ROLL_VOLUME_LOOKBACK),
            end=end,
        )

    def start_recovery(
        self,
        *,
        declarations: Mapping[str, ContinuousRootDeclaration],
        history_starts: Mapping[str, datetime],
    ) -> RollIntentBatch:
        """Initialize each root at its replay origin, before chronological folding."""
        models: dict[InstrumentId, ContinuousContractModel] = {}
        timeframes: dict[InstrumentId, str] = {}
        leg_to_continuous: dict[InstrumentId, InstrumentId] = {}
        recovery_event_ns: dict[InstrumentId, int] = {}
        root_by_continuous: dict[InstrumentId, str] = {}
        history_start_by_continuous: dict[InstrumentId, datetime] = {}
        for root, declaration in sorted(declarations.items()):
            history_start = history_starts[root]
            model = ContinuousContractModel(
                self._catalog_port,
                root,
                start=history_start.date().isoformat(),
                timeframe=declaration.timeframe,
                adjustment_mode=declaration.adjustment_mode,
            )
            model.materialize(end=history_start.date().isoformat())
            if model.continuous_id != declaration.continuous_id:
                return (
                    Halt(
                        StartupGate.CONTINUOUS_IDENTITY,
                        (
                            f"continuous root {root!r} materialized as "
                            f"{model.continuous_id.value}, expected "
                            f"{declaration.continuous_id.value}"
                        ),
                    ),
                )
            models[declaration.continuous_id] = model
            timeframes[declaration.continuous_id] = declaration.timeframe
            leg_to_continuous[model.front_leg] = declaration.continuous_id
            recovery_event_ns[declaration.continuous_id] = int(
                history_start.timestamp() * 1_000_000_000
            )
            root_by_continuous[declaration.continuous_id] = root
            history_start_by_continuous[declaration.continuous_id] = history_start

        self._models = models
        self._timeframe_by_continuous_id = timeframes
        self._leg_to_continuous_id = leg_to_continuous
        self._recovery_event_ns = recovery_event_ns
        self._root_by_continuous_id = root_by_continuous
        self._history_start_by_continuous_id = history_start_by_continuous
        self._subscribed_legs = {
            continuous_id: set() for continuous_id in models
        }
        return ()

    def on_recovery_bar(self, bar: Bar) -> RollIntentBatch:
        """Fold historical market time without emitting historical IO intents."""
        continuous_id = self._leg_to_continuous_id.get(bar.bar_type.instrument_id)
        if continuous_id is None:
            return ()
        model = self._models[continuous_id]
        if bar.ts_event <= self._recovery_event_ns[continuous_id]:
            return ()

        front_before = model.front_leg
        model.on_bar(bar)
        self._recovery_event_ns[continuous_id] = bar.ts_event
        front_after = model.front_leg
        if front_after == front_before:
            return ()
        del self._leg_to_continuous_id[front_before]
        self._leg_to_continuous_id[front_after] = continuous_id
        return (RollEvent(continuous_id=continuous_id, rebasing=model.last_rebasing),)

    def live_intents(self) -> RollIntentBatch:
        """Subscribe every candidate stream the reconstructed roll model reads."""
        intents: list[SubscribeBars | RequestInstrument | UnsubscribeBars] = []
        for continuous_id in sorted(self._models, key=lambda item: item.value):
            intents.extend(
                self._refresh_subscriptions(
                    continuous_id,
                    self._recovery_event_ns[continuous_id],
                )
            )
        return tuple(intents)

    def on_instrument(self, instrument_id: InstrumentId) -> RollIntentBatch:
        """Complete a deferred candidate-leg subscription."""
        continuous_id = self._pending_leg_subscriptions.pop(instrument_id, None)
        if continuous_id is None:
            return ()
        return (
            SubscribeBars(
                instrument_id=instrument_id,
                timeframe=self._timeframe_by_continuous_id[continuous_id],
            ),
        )

    def continuous_id(self, leg: InstrumentId) -> InstrumentId | None:
        """The continuous root a dated front leg currently feeds, if any."""
        return self._leg_to_continuous_id.get(leg)

    def front_leg(self, instrument_id: InstrumentId) -> InstrumentId | None:
        """Return the current execution front for a continuous root."""
        model = self._models.get(instrument_id)
        if model is None:
            return None
        return model.front_leg

    def series(self, instrument_id: InstrumentId) -> pd.DataFrame | None:
        """Return the current adjusted series for a continuous root."""
        model = self._models.get(instrument_id)
        if model is None:
            return None
        return model.frame

    def _ensure_subscription(
        self, instrument_id: InstrumentId, continuous_id: InstrumentId
    ) -> SubscribeBars | RequestInstrument:
        if self._instrument_present(instrument_id):
            return SubscribeBars(
                instrument_id=instrument_id,
                timeframe=self._timeframe_by_continuous_id[continuous_id],
            )
        self._pending_leg_subscriptions[instrument_id] = continuous_id
        return RequestInstrument(instrument_id=instrument_id)

    def _refresh_subscriptions(
        self,
        continuous_id: InstrumentId,
        timestamp_ns: int,
    ) -> _SubscriptionIntentBatch:
        as_of = datetime.fromtimestamp(timestamp_ns / 1_000_000_000, tz=timezone.utc)
        desired = {
            InstrumentId.from_str(leg.symbol)
            for leg in self._live_legs(
                self._root_by_continuous_id[continuous_id],
                history_start=self._history_start_by_continuous_id[continuous_id],
                end=as_of,
            )
        }
        subscribed = self._subscribed_legs[continuous_id]
        timeframe = self._timeframe_by_continuous_id[continuous_id]
        intents: list[SubscribeBars | RequestInstrument | UnsubscribeBars] = []
        for instrument_id in sorted(subscribed - desired, key=lambda item: item.value):
            pending = self._pending_leg_subscriptions.pop(instrument_id, None)
            if pending is None:
                intents.append(UnsubscribeBars(instrument_id, timeframe))
        for instrument_id in sorted(desired - subscribed, key=lambda item: item.value):
            intents.append(self._ensure_subscription(instrument_id, continuous_id))
        self._subscribed_legs[continuous_id] = desired
        return tuple(intents)
