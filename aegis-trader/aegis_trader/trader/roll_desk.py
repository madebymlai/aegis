"""Nautilus-free live Roll lifecycle state machine."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime

import pandas as pd
from aegis_data.catalog import CatalogBackedDataPort
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.data.continuous_feed import ContinuousFeed
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


class RollDesk:
    """Own the live continuous-root roll lifecycle behind intent batches."""

    def __init__(
        self,
        *,
        catalog_port: CatalogBackedDataPort,
        instrument_present: InstrumentPresence,
        declared_continuous_ids_by_root: Mapping[str, InstrumentId],
        timeframe: str,
        history_start: datetime,
    ) -> None:
        self._catalog_port = catalog_port
        self._instrument_present = instrument_present
        self._declared_continuous_ids_by_root = dict(declared_continuous_ids_by_root)
        self._timeframe = timeframe
        self._history_start = history_start
        self._feeds: dict[InstrumentId, ContinuousFeed] = {}
        self._leg_to_continuous_id: dict[InstrumentId, InstrumentId] = {}
        self._pending_leg_subscriptions: set[InstrumentId] = set()

    def start(self, *, end: datetime, warmup: bool) -> RollIntentBatch:
        """Materialize declared roots and emit front-leg warmup/subscription intents."""
        feeds: dict[InstrumentId, ContinuousFeed] = {}
        leg_to_continuous_id: dict[InstrumentId, InstrumentId] = {}
        intents: list[RequestBars | SubscribeBars] = []

        for root, declared_id in sorted(self._declared_continuous_ids_by_root.items()):
            feed = ContinuousFeed(
                self._catalog_port,
                root,
                start=self._history_start.date().isoformat(),
                timeframe=self._timeframe,
            )
            feed.materialize(end=end.date().isoformat())
            if feed.continuous_id != declared_id:
                return (
                    Halt(
                        gate=StartupGate.CONTINUOUS_IDENTITY,
                        reason=(
                            f"continuous root {root!r} materialized as "
                            f"{feed.continuous_id.value}, expected {declared_id.value}"
                        ),
                    ),
                )

            front_leg = feed.front_contract()
            feeds[declared_id] = feed
            leg_to_continuous_id[front_leg] = declared_id
            if warmup:
                intents.append(
                    RequestBars(
                        instrument_id=front_leg,
                        timeframe=self._timeframe,
                        start=self._history_start,
                        end=end,
                    )
                )
            intents.append(SubscribeBars(instrument_id=front_leg, timeframe=self._timeframe))

        self._feeds = feeds
        self._leg_to_continuous_id = leg_to_continuous_id
        return tuple(intents)

    def on_bar(self, bar: Bar) -> RollIntentBatch:
        """Fold a front-leg bar into its root and emit roll intents when the front advances."""
        continuous_id = self._leg_to_continuous_id.get(bar.bar_type.instrument_id)
        if continuous_id is None:
            return ()

        feed = self._feeds[continuous_id]
        front_before = feed.front_contract()
        feed.on_bar(bar)
        front_after = feed.front_contract()
        if front_after == front_before:
            return ()

        del self._leg_to_continuous_id[front_before]
        self._leg_to_continuous_id[front_after] = continuous_id
        return (
            UnsubscribeBars(instrument_id=front_before, timeframe=self._timeframe),
            self._ensure_front_leg(front_after),
            RollEvent(continuous_id=continuous_id, rebasing=feed.last_rebasing()),
        )

    def on_instrument(self, instrument_id: InstrumentId) -> RollIntentBatch:
        """Complete a deferred front-leg subscription."""
        if instrument_id not in self._pending_leg_subscriptions:
            return ()
        self._pending_leg_subscriptions.discard(instrument_id)
        return (SubscribeBars(instrument_id=instrument_id, timeframe=self._timeframe),)

    def front_leg(self, instrument_id: InstrumentId) -> InstrumentId | None:
        """Return the current execution front for a continuous root."""
        feed = self._feeds.get(instrument_id)
        if feed is None:
            return None
        return feed.front_contract()

    def series(self, instrument_id: InstrumentId) -> pd.DataFrame | None:
        """Return the current adjusted series for a continuous root."""
        feed = self._feeds.get(instrument_id)
        if feed is None:
            return None
        return feed.series()

    def _ensure_front_leg(self, instrument_id: InstrumentId) -> SubscribeBars | RequestInstrument:
        if self._instrument_present(instrument_id):
            return SubscribeBars(instrument_id=instrument_id, timeframe=self._timeframe)
        self._pending_leg_subscriptions.add(instrument_id)
        return RequestInstrument(instrument_id=instrument_id)
