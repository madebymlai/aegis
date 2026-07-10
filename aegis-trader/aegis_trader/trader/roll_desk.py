"""Nautilus-free live Roll lifecycle state machine."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime

import pandas as pd
from aegis_data.catalog import CatalogBackedDataPort
from aegis_data.continuous_contract_model import ContinuousContractModel
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
        self._timeframe: str | None = None
        self._models: dict[InstrumentId, ContinuousContractModel] = {}
        self._leg_to_continuous_id: dict[InstrumentId, InstrumentId] = {}
        self._pending_leg_subscriptions: set[InstrumentId] = set()

    def start(
        self,
        *,
        timeframe: str,
        history_start: datetime,
        end: datetime,
        warmup: bool,
        declarations: Mapping[str, ContinuousRootDeclaration],
    ) -> RollIntentBatch:
        """Materialize the declared roots and emit front-leg warmup/subscription intents.

        ``declarations`` is the already coherent cross-Sleeve union built by book
        startup; each root materialises under its declaration's bundle-recorded
        adjustment mode, so the emitted roll ``Rebasing`` is multiplicative for
        ratio and additive for spread automatically.
        """
        self._timeframe = timeframe
        models: dict[InstrumentId, ContinuousContractModel] = {}
        leg_to_continuous_id: dict[InstrumentId, InstrumentId] = {}
        intents: list[RequestBars | SubscribeBars] = []

        for root, declaration in sorted(declarations.items()):
            model = ContinuousContractModel(
                self._catalog_port,
                root,
                start=history_start.date().isoformat(),
                timeframe=timeframe,
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
            leg_to_continuous_id[front_leg] = declaration.continuous_id
            if warmup:
                intents.append(
                    RequestBars(
                        instrument_id=front_leg,
                        timeframe=timeframe,
                        start=history_start,
                        end=end,
                    )
                )
            intents.append(SubscribeBars(instrument_id=front_leg, timeframe=timeframe))

        self._models = models
        self._leg_to_continuous_id = leg_to_continuous_id
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
        if front_after == front_before:
            return ()

        del self._leg_to_continuous_id[front_before]
        self._leg_to_continuous_id[front_after] = continuous_id
        return (
            UnsubscribeBars(instrument_id=front_before, timeframe=self._require_timeframe()),
            self._ensure_front_leg(front_after),
            RollEvent(continuous_id=continuous_id, rebasing=model.last_rebasing),
        )

    def on_instrument(self, instrument_id: InstrumentId) -> RollIntentBatch:
        """Complete a deferred front-leg subscription."""
        if instrument_id not in self._pending_leg_subscriptions:
            return ()
        self._pending_leg_subscriptions.discard(instrument_id)
        return (SubscribeBars(instrument_id=instrument_id, timeframe=self._require_timeframe()),)

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

    def _ensure_front_leg(self, instrument_id: InstrumentId) -> SubscribeBars | RequestInstrument:
        if self._instrument_present(instrument_id):
            return SubscribeBars(
                instrument_id=instrument_id,
                timeframe=self._require_timeframe(),
            )
        self._pending_leg_subscriptions.add(instrument_id)
        return RequestInstrument(instrument_id=instrument_id)

    def _require_timeframe(self) -> str:
        if self._timeframe is None:
            raise RuntimeError("roll desk queried before start resolved its timeframe")
        return self._timeframe
