"""Continuous-future feed — the RebalanceStrategy-owned deep module (r8b.9, Model 2).

One feed per bare root.  It owns the back-adjusted continuous series, re-materializing it via
aegis-data's request path (:func:`continuous_frame_and_future`), which runs on its **own** ephemeral
``DataEngine`` + ``Cache`` and never touches the live node cache.  The live cache holds only raw
legs; the continuous series lives here.  Because the feed literally runs the research
materializer, ``live@T ≡ research over [start, T]`` holds by construction.

This module hides the whole Nautilus continuous-future query surface behind a small interface:
callers ask for the series and the current front leg; they never learn the chain, the
roll-transition table, or the engine.
"""

from __future__ import annotations

from datetime import date
from typing import TypeVar

import pandas as pd
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import timeframe_to_ns
from aegis_data.catalog import CatalogBackedDataPort, bars_to_ohlcv
from aegis_data.catalog_contracts import catalog_contract_calendar, catalog_volume_probe
from aegis_data.continuous_catalog import continuous_frame_and_future
from aegis_data.continuous_future import ContinuousFuture
from aegis_data.liquidity import liquid_cycle_causal
from aegis_data.rebasing import IDENTITY, Rebasing
from aegis_data.roll import roll_lead_days_for_cadence

_T = TypeVar("_T")


class ContinuousFeed:
    """The back-adjusted continuous series for one bare ``root`` (e.g. ``"ES"``)."""

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
        bar_cadence = pd.Timedelta(timeframe_to_ns(timeframe), unit="ns").to_pytimedelta()
        self._roll_lead_days = roll_lead_days_for_cadence(bar_cadence)
        self._continuous_id: InstrumentId | None = None
        self._series: pd.DataFrame | None = None
        self._front_id: InstrumentId | None = None
        self._future: ContinuousFuture | None = None
        self._last_rebasing: Rebasing = IDENTITY

    @property
    def root(self) -> str:
        """The bare root symbol this feed materializes (e.g. ``"ES"``)."""
        return self._root

    @property
    def continuous_id(self) -> InstrumentId:
        """The synthetic continuous-root id (``ES.XCME``) the series is keyed by."""
        return self._materialized(self._continuous_id)

    def _materialized(self, value: _T | None) -> _T:
        """Return *value*, or raise if the feed has not been materialized yet.

        The single not-yet-materialized guard every accessor shares: :meth:`materialize` sets
        the continuous id, the series, the front leg, and the future together, so any one of them
        being ``None`` means no materialization has run.
        """
        if value is None:
            raise ValueError(f"continuous feed for {self._root!r} has not been materialized yet")
        return value

    def materialize(self, *, end: str) -> None:
        """(Re)materialize the back-adjusted series over ``[start, end]`` off-cache.

        Runs aegis-data's request path on its own ephemeral engine + cache, so it re-bases the
        whole history at the current front without ever writing the continuous series into the
        live node cache.  Keeps the materialized :class:`ContinuousFuture` so a roll can read its
        exact seam re-basing from the transition leg closes.
        """
        future, frame = continuous_frame_and_future(
            self._port, self._root, start=self._start, end=end, timeframe=self._timeframe
        )
        self._future = future
        self._continuous_id = future.instrument_id
        self._series = frame
        self._front_id = self._causal_front(pd.Timestamp(end).date())

    def series(self) -> pd.DataFrame:
        """The current back-adjusted continuous OHLCV frame (the live read surface)."""
        return self._materialized(self._series)

    def front_contract(self) -> InstrumentId:
        """The current front leg's native id (the execution target root→front maps to).

        The front is the latest leg that has become the Liquidity Leader by the materialized
        ``end`` — judged causally (volume observed-to-date), so live picks the same leg research
        does; at the window end the two coincide (the liquid-cycle parity guarantee).
        """
        return self._materialized(self._front_id)

    def last_rebasing(self) -> Rebasing:
        """The re-basing applied at the most recent roll (a no-op identity if none yet).

        At a roll the whole series re-bases at the new front — additively under a spread mode,
        multiplicatively under a ratio mode (the :class:`Rebasing` owns which).  A caller holding
        co-moving absolute state from before the roll (the SleeveLedger's stored closes) applies this
        to carry it into the new basis, keeping live ≡ research across the seam (Slice L) for whichever
        adjustment mode is in force.
        """
        return self._last_rebasing

    def on_bar(self, bar: Bar) -> None:
        """Fold a closed front-leg bar into the series, appended verbatim at offset 0.

        The current front segment has offset 0, so today's continuous value *is* the raw front
        close — appending the front bar's OHLCV verbatim (the same projection the materializer
        uses) gives today's continuous bar without waiting on IBKR historical.  A bar from any
        other leg is ignored (roll detection is handled separately).
        """
        series = self._materialized(self._series)
        front_id = self._materialized(self._front_id)
        bar_day = pd.Timestamp(bar.ts_event, tz="UTC").date()
        if self._causal_front(bar_day) != front_id:
            # A roll: the liquidity leader has advanced. Re-materialize the whole series re-based at
            # the new front (a non-event for the live cache) and advance the front leg, recording the
            # roll's Rebasing read EXACTLY from the seam transition leg closes (additive under a
            # spread mode, multiplicative under a ratio mode) so a caller can carry co-moving state
            # (the SleeveLedger) into the new basis in step — for whichever adjustment mode is in force.
            self.materialize(end=bar_day.isoformat())
            self._last_rebasing = self._materialized(self._future).rebasing_for_roll(
                front_id, self._materialized(self._front_id)
            )
            return
        if bar.bar_type.instrument_id != front_id:
            return
        row = bars_to_ohlcv([bar])
        # The materializer stamps each continuous bar at the bucket close of the leg bar's
        # AVAILABILITY time (ts_init), not its event time.  Real venue daily bars carry
        # ts_event = session open (00:00 UTC) but ts_init = session close (23:59:59.999…), so the
        # bar belongs to the bucket closing the NEXT day; a synthetic bar with ts_init == ts_event
        # at 00:00 closes the same day.  ``bars_to_ohlcv`` indexes by ts_event, so re-stamp from
        # ts_init's bucket close to land on the materializer's index for either.  The value needs no
        # adjustment — the front is offset 0 (today's continuous value IS the raw front close).
        close_stamp = pd.Timestamp(bar.ts_init, tz="UTC").ceil(self._timeframe).tz_localize(None)
        row.index = pd.DatetimeIndex([close_stamp])
        self._series = pd.concat([series, row])

    def _causal_front(self, end: date) -> InstrumentId:
        start = pd.Timestamp(self._start).date()
        candidates = catalog_contract_calendar(self._port.catalog)(self._root, start, end)
        probe = catalog_volume_probe(self._port, timeframe=self._timeframe)
        volume_by_symbol = {leg.symbol: probe(leg.symbol, start, end) for leg in candidates}
        cycle = liquid_cycle_causal(
            candidates, volume_by_symbol, end, roll_lead_days=self._roll_lead_days
        )
        if not cycle:
            raise ValueError(
                f"continuous-future root {self._root!r} has no liquid front leg by {end}"
            )
        return InstrumentId.from_str(cycle[-1].symbol)
