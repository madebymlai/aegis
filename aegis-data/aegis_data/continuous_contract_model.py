"""Stateful continuous-futures model shared by research and live."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TypeVar

import pandas as pd
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import timeframe_to_ns
from aegis_data.catalog import CatalogBackedDataPort, bars_to_ohlcv
from aegis_data.chain import fetch_contract_chain
from aegis_data.continuous_future import ContinuousFuture, continuous_future
from aegis_data.continuous_materialize import materialize_continuous_bars
from aegis_data.liquidity import liquid_roll_schedule
from aegis_data.marking import InstrumentMarking
from aegis_data.raw_bars import RawBars
from aegis_runtime.domain.rebasing import IDENTITY, Rebasing
from aegis_data.roll import roll_lead_days_for_cadence
from aegis_data.storage import CatalogInterval

_T = TypeVar("_T")
ROLL_VOLUME_LOOKBACK = timedelta(days=90)


class ContinuousContractModelError(Exception):
    """Base class for continuous-contract model lifecycle failures."""


class ContinuousContractModelNotMaterializedError(ContinuousContractModelError):
    """A model read was attempted before materialization."""


class ContinuousFrontLegUnavailableError(ContinuousContractModelError):
    """The roll schedule has no liquid front leg for the requested as-of."""


class ContinuousLegCurrencyError(ContinuousContractModelError):
    """A root's resolved dated legs declare no, or conflicting, quote currencies."""


class ContinuousContractModel:
    """The adjusted continuous series and front-leg lifecycle for one bare root."""

    def __init__(
        self,
        port: CatalogBackedDataPort,
        root: str,
        *,
        start: str,
        timeframe: str = "1D",
        adjustment_mode: ContinuousFutureAdjustmentType,
    ) -> None:
        self._port = port
        self._raw_bars: RawBars = port.raw_bars
        self._root = root
        self._start = start
        self._timeframe = timeframe
        self._adjustment_mode = adjustment_mode
        self._bar_cadence = pd.Timedelta(
            timeframe_to_ns(timeframe), unit="ns"
        ).to_pytimedelta()
        self._roll_lead_days = roll_lead_days_for_cadence(self._bar_cadence)
        self._continuous_id: InstrumentId | None = None
        self._frame: pd.DataFrame | None = None
        self._front_leg: InstrumentId | None = None
        self._future: ContinuousFuture | None = None
        self._quote_currency: str | None = None
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
    def quote_currency(self) -> str:
        """The one quote currency every resolved dated leg declares.

        A synthetic continuous root has no catalog definition of its own, so this
        derived fact is how the root joins a base-currency conversion.
        """
        return self._materialized(self._quote_currency)

    @property
    def last_rebasing(self) -> Rebasing:
        """The re-basing recorded at the most recent roll, or identity before one."""
        return self._last_rebasing

    def materialize(self, *, end: str) -> None:
        """(Re)materialize the adjusted frame over ``[start, end]`` off-cache.

        Bounded by ``_readable_end``: the frame reaches as far as the Catalog
        has been checked, never past it.
        """
        readable = self._readable_end(pd.Timestamp(end).date())
        future, frame, quote_currency = self._materialize_frame(readable.isoformat())
        self._future = future
        self._continuous_id = future.instrument_id
        self._frame = frame
        self._quote_currency = quote_currency
        self._front_leg = self.front_leg_as_of(readable)

    def front_leg_as_of(self, as_of: str | date | pd.Timestamp) -> InstrumentId:
        """Return the front leg named by the liquidity-timed roll schedule at ``as_of``."""
        end = self._readable_end(pd.Timestamp(as_of).date())
        start = max(
            pd.Timestamp(self._start).date(),
            end - ROLL_VOLUME_LOOKBACK,
        )
        candidates = self._port.resolve_continuous(self._root).legs
        volume_by_symbol = {
            leg.symbol: self._stored_contract_volume(leg.symbol, start, end)
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

    def _materialize_frame(self, end: str) -> tuple[ContinuousFuture, pd.DataFrame, str]:
        resolved = self._port.resolve_continuous(self._root)
        legs = resolved.legs
        chain = fetch_contract_chain(
            self._root,
            pd.Timestamp(self._start).date(),
            pd.Timestamp(end).date(),
            list_contracts=lambda *_args: legs,
            fetch=self._ensure_contract_ohlcv,
            bar_cadence=self._bar_cadence,
            probe_volume=self._ensure_contract_volume,
        )
        future = continuous_future(
            chain,
            resolved.instrument_id,
            timeframe=self._timeframe,
            adjustment_mode=self._adjustment_mode,
        )
        leg_ids = tuple(InstrumentId.from_str(symbol) for symbol in chain.symbols)
        interval = self._interval(
            pd.Timestamp(self._start).date(),
            pd.Timestamp(end).date(),
        )
        leg_bars = {
            instrument_id: self._raw_bars.stored(
                self._raw_bars.marking(instrument_id, self._timeframe),
                interval,
            ).bars
            for instrument_id in leg_ids
        }
        leg_instruments = tuple(self._port.instruments(leg_ids).values())
        quote_currency = self._leg_quote_currency(leg_instruments)
        bars = materialize_continuous_bars(
            future,
            leg_instruments=leg_instruments,
            leg_bars=leg_bars,
            start=pd.Timestamp(self._start, tz="UTC"),
            end=pd.Timestamp(end, tz="UTC"),
        )
        return future, bars_to_ohlcv(bars), quote_currency

    def _ensure_contract_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        marking, interval = self._contract_window(symbol, start, end)
        self._raw_bars.ensure(marking, interval)
        return self._raw_bars.stored(marking, interval).ohlcv

    def _ensure_contract_volume(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.Series:
        return self._ensure_contract_ohlcv(symbol, start, end)["Volume"]

    def _stored_contract_volume(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.Series:
        marking, interval = self._contract_window(symbol, start, end)
        return self._raw_bars.stored(marking, interval).ohlcv["Volume"]

    def _readable_end(self, requested: date) -> date:
        """The last date this model can answer for.

        A model that can fill answers for whatever it was asked — it goes and
        gets the window. A model that can only read answers for what the
        Catalog reports as checked, because that is all it has. Liquidity is a
        comparison *across* legs, so the frontier is the earliest of them: a
        leg that has not been checked as far as its rivals cannot be ranked
        against them yet.

        This is what keeps a live session from needing a coverage verdict about
        the instant it is living through. It asks the Catalog how far it has
        been checked instead of asserting an answer.
        """
        if self._raw_bars.can_fill:
            return requested
        frontiers = [
            self._raw_bars.covered_through(bar_type)
            for leg in self._port.resolve_continuous(self._root).legs
            for bar_type in self._raw_bars.marking(
                InstrumentId.from_str(leg.symbol), self._timeframe
            ).mark_bars
        ]
        if not frontiers or None in frontiers:
            return requested
        earliest = min(frontier for frontier in frontiers if frontier is not None)
        return min(requested, pd.Timestamp(earliest, tz="UTC").date())

    def _contract_window(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> tuple[InstrumentMarking, CatalogInterval]:
        instrument_id = InstrumentId.from_str(symbol)
        return (
            self._raw_bars.marking(instrument_id, self._timeframe),
            self._interval(start, end),
        )

    @staticmethod
    def _interval(start: date, end: date) -> CatalogInterval:
        return CatalogInterval(
            pd.Timestamp(start, tz="UTC").value,
            pd.Timestamp(end, tz="UTC").value,
        )

    def _leg_quote_currency(self, leg_instruments: tuple[object, ...]) -> str:
        currencies = sorted(
            {instrument.quote_currency.code for instrument in leg_instruments}  # type: ignore[attr-defined]
        )
        if len(currencies) != 1:
            raise ContinuousLegCurrencyError(
                f"continuous-future root {self._root!r} needs exactly one leg quote "
                f"currency; resolved legs declare {currencies or 'none'}"
            )
        return currencies[0]

    def _materialized(self, value: _T | None) -> _T:
        if value is None:
            raise ContinuousContractModelNotMaterializedError(
                f"continuous contract model for {self._root!r} has not been materialized yet"
            )
        return value


__all__ = [
    "ROLL_VOLUME_LOOKBACK",
    "ContinuousContractModel",
    "ContinuousContractModelError",
    "ContinuousContractModelNotMaterializedError",
    "ContinuousFrontLegUnavailableError",
    "ContinuousLegCurrencyError",
]
