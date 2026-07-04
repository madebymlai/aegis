"""Stateful continuous-futures model shared by research and live."""

from __future__ import annotations

from datetime import date
from typing import TypeVar

import pandas as pd
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import timeframe_to_ns
from aegis_data.catalog import CatalogBackedDataPort, RawBarRequest, bars_to_ohlcv
from aegis_data.chain import fetch_contract_chain
from aegis_data.continuous_future import ContinuousFuture, continuous_future
from aegis_data.continuous_materialize import materialize_continuous_bars
from aegis_data.liquidity import liquid_roll_schedule
from aegis_data.rebasing import IDENTITY, Rebasing
from aegis_data.roll import roll_lead_days_for_cadence

_T = TypeVar("_T")


class ContinuousContractModelError(Exception):
    """Base class for continuous-contract model lifecycle failures."""


class ContinuousContractModelNotMaterializedError(ContinuousContractModelError):
    """A model read was attempted before materialization."""


class ContinuousFrontLegUnavailableError(ContinuousContractModelError):
    """The roll schedule has no liquid front leg for the requested as-of."""


class ContinuousContractModel:
    """The adjusted continuous series and front-leg lifecycle for one bare root."""

    def __init__(
        self,
        port: CatalogBackedDataPort,
        root: str,
        *,
        start: str,
        timeframe: str = "1D",
    ) -> None:
        self._port = port
        self._root = root
        self._start = start
        self._timeframe = timeframe
        self._bar_cadence = pd.Timedelta(
            timeframe_to_ns(timeframe), unit="ns"
        ).to_pytimedelta()
        self._roll_lead_days = roll_lead_days_for_cadence(self._bar_cadence)
        self._continuous_id: InstrumentId | None = None
        self._frame: pd.DataFrame | None = None
        self._front_leg: InstrumentId | None = None
        self._future: ContinuousFuture | None = None
        self._last_rebasing: Rebasing = IDENTITY

    @property
    def root(self) -> str:
        """The bare root symbol this model materializes, for example ``"ES"``."""
        return self._root

    @property
    def continuous_id(self) -> InstrumentId:
        """The synthetic continuous-root id the frame is keyed by."""
        return self._materialized(self._continuous_id)

    @property
    def frame(self) -> pd.DataFrame:
        """The current adjusted continuous OHLCV frame."""
        return self._materialized(self._frame)

    @property
    def front_leg(self) -> InstrumentId:
        """The current front leg's native id."""
        return self._materialized(self._front_leg)

    @property
    def last_rebasing(self) -> Rebasing:
        """The re-basing recorded at the most recent roll, or identity before one."""
        return self._last_rebasing

    def materialize(self, *, end: str) -> None:
        """(Re)materialize the adjusted frame over ``[start, end]`` off-cache."""
        future, frame = self._materialize_frame(end)
        self._future = future
        self._continuous_id = future.instrument_id
        self._frame = frame
        self._front_leg = self.front_leg_as_of(end)

    def front_leg_as_of(self, as_of: str | date | pd.Timestamp) -> InstrumentId:
        """Return the front leg named by the liquidity-timed roll schedule at ``as_of``."""
        start = pd.Timestamp(self._start).date()
        end = pd.Timestamp(as_of).date()
        candidates = self._port.resolve_continuous(self._root).legs
        volume_by_symbol = {
            leg.symbol: self._port.probe_contract_volume(
                leg.symbol, start, end, timeframe=self._timeframe
            )
            for leg in candidates
        }
        schedule = liquid_roll_schedule(
            candidates,
            volume_by_symbol,
            start,
            end,
            roll_lead_days=self._roll_lead_days,
        )
        if not schedule.symbols:
            raise ContinuousFrontLegUnavailableError(
                f"continuous-future root {self._root!r} has no liquid front leg by {end}"
            )
        return InstrumentId.from_str(schedule.symbols[-1])

    def on_bar(self, bar: Bar) -> None:
        """Fold a closed front-leg bar into the frame, or re-materialize across a roll."""
        series = self.frame
        front_before = self.front_leg
        bar_day = pd.Timestamp(bar.ts_event, tz="UTC").date()
        front_after = self.front_leg_as_of(bar_day)
        if front_after != front_before:
            self._roll_across(bar, front_before)
            return
        if bar.bar_type.instrument_id != front_before:
            return
        self._frame = pd.concat([series, self._closed_row(bar)])

    def _roll_across(self, bar: Bar, front_before: InstrumentId) -> None:
        """Re-materialize across the roll ``bar`` triggered, without dropping the
        boundary buckets.  The walk only emits a bucket once a later bar closes it,
        so it is bounded by the trigger's bucket close — reaching the last complete
        bucket — and a trigger owned by the new front is folded back in at offset
        zero, where its raw bar equals the adjusted bar."""
        self.materialize(end=self._bucket_close(bar).isoformat())
        self._last_rebasing = self._materialized(self._future).rebasing_for_roll(
            front_before, self.front_leg
        )
        if bar.bar_type.instrument_id == self.front_leg:
            self._frame = pd.concat([self.frame, self._closed_row(bar)])

    def _closed_row(self, bar: Bar) -> pd.DataFrame:
        row = bars_to_ohlcv([bar])
        row.index = pd.DatetimeIndex([self._bucket_close(bar)])
        return row

    def _bucket_close(self, bar: Bar) -> pd.Timestamp:
        return (
            pd.Timestamp(bar.ts_init, tz="UTC").ceil(self._timeframe).tz_localize(None)
        )

    def _materialize_frame(self, end: str) -> tuple[ContinuousFuture, pd.DataFrame]:
        resolved = self._port.resolve_continuous(self._root)
        legs = resolved.legs
        chain = fetch_contract_chain(
            self._root,
            pd.Timestamp(self._start).date(),
            pd.Timestamp(end).date(),
            list_contracts=lambda *_args: legs,
            fetch=lambda symbol, start, end: self._port.fetch_contract_ohlcv(
                symbol, start, end, timeframe=self._timeframe
            ),
            bar_cadence=self._bar_cadence,
            probe_volume=lambda symbol, start, end: self._port.probe_contract_volume(
                symbol, start, end, timeframe=self._timeframe
            ),
        )
        future = continuous_future(
            chain, resolved.instrument_id, timeframe=self._timeframe
        )
        leg_ids = tuple(InstrumentId.from_str(symbol) for symbol in chain.symbols)
        leg_bars = self._port.read_native_bars(
            RawBarRequest(leg_ids, self._start, end, self._timeframe)
        )
        leg_instruments = self._port.instruments(leg_ids)
        bars = materialize_continuous_bars(
            future,
            leg_instruments=leg_instruments,
            leg_bars=leg_bars,
            start=pd.Timestamp(self._start, tz="UTC"),
            end=pd.Timestamp(end, tz="UTC"),
        )
        return future, bars_to_ohlcv(bars)

    def _materialized(self, value: _T | None) -> _T:
        if value is None:
            raise ContinuousContractModelNotMaterializedError(
                f"continuous contract model for {self._root!r} has not been materialized yet"
            )
        return value


__all__ = [
    "ContinuousContractModel",
    "ContinuousContractModelError",
    "ContinuousContractModelNotMaterializedError",
    "ContinuousFrontLegUnavailableError",
]
