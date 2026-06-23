"""Continuous-future feed — the RebalanceStrategy-owned deep module (r8b.9, Model 2).

One feed per bare root.  It owns the back-adjusted continuous series, re-materializing it via
aegis-data's request path (:func:`continuous_ohlcv_frames`), which runs on its **own** ephemeral
``DataEngine`` + ``Cache`` and never touches the live node cache.  The live cache holds only raw
legs; the continuous series lives here.  Because the feed literally runs the research
materializer, ``live@T ≡ research over [start, T]`` holds by construction.

This module hides the whole Nautilus continuous-future query surface behind a small interface:
callers ask for the series and the current front leg; they never learn the chain, the
roll-transition table, or the engine.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.bar_type import timeframe_to_ns
from aegis_data.catalog import CatalogBackedDataPort, bars_to_ohlcv
from aegis_data.catalog_contracts import catalog_contract_calendar, catalog_volume_probe
from aegis_data.continuous_catalog import continuous_ohlcv_frames
from aegis_data.liquidity import liquid_cycle_causal
from aegis_data.roll import roll_lead_days_for_cadence


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
        self._last_roll_spread: float = 0.0

    @property
    def root(self) -> str:
        """The bare root symbol this feed materializes (e.g. ``"ES"``)."""
        return self._root

    @property
    def continuous_id(self) -> InstrumentId:
        """The synthetic continuous-root id (``ES.XCME``) the series is keyed by."""
        if self._continuous_id is None:
            raise ValueError(f"continuous feed for {self._root!r} has not been materialized yet")
        return self._continuous_id

    def materialize(self, *, end: str) -> None:
        """(Re)materialize the back-adjusted series over ``[start, end]`` off-cache.

        Runs aegis-data's request path on its own ephemeral engine + cache, so it re-bases the
        whole history at the current front without ever writing the continuous series into the
        live node cache.
        """
        frames = continuous_ohlcv_frames(
            self._port, [self._root], start=self._start, end=end, timeframe=self._timeframe
        )
        ((self._continuous_id, self._series),) = frames.items()
        self._front_id = self._causal_front(pd.Timestamp(end).date())

    def series(self) -> pd.DataFrame:
        """The current back-adjusted continuous OHLCV frame (the live read surface)."""
        if self._series is None:
            raise ValueError(f"continuous feed for {self._root!r} has not been materialized yet")
        return self._series

    def front_contract(self) -> InstrumentId:
        """The current front leg's native id (the execution target root→front maps to).

        The front is the latest leg that has become the Liquidity Leader by the materialized
        ``end`` — judged causally (volume observed-to-date), so live picks the same leg research
        does; at the window end the two coincide (the liquid-cycle parity guarantee).
        """
        if self._front_id is None:
            raise ValueError(f"continuous feed for {self._root!r} has not been materialized yet")
        return self._front_id

    def last_roll_spread(self) -> float:
        """The uniform additive spread Δ applied at the most recent roll (0.0 if none yet).

        At a roll the whole series re-bases by one Δ (post−pre at the new roll); a caller holding
        co-moving absolute state from before the roll (the SleeveLedger's stored closes) adds Δ to
        carry it into the new basis, keeping live ≡ research across the seam (Slice L).
        """
        return self._last_roll_spread

    def on_bar(self, bar: Bar) -> None:
        """Fold a closed front-leg bar into the series, appended verbatim at offset 0.

        The current front segment has offset 0, so today's continuous value *is* the raw front
        close — appending the front bar's OHLCV verbatim (the same projection the materializer
        uses) gives today's continuous bar without waiting on IBKR historical.  A bar from any
        other leg is ignored (roll detection is handled separately).
        """
        if self._series is None or self._front_id is None:
            raise ValueError(f"continuous feed for {self._root!r} has not been materialized yet")
        bar_day = pd.Timestamp(bar.ts_event, tz="UTC").date()
        if self._causal_front(bar_day) != self._front_id:
            # A roll: the liquidity leader has advanced. Re-materialize the whole series re-based
            # at the new front (a non-event for the live cache) and advance the front leg, recording
            # the uniform additive spread Δ (BACKWARD_SPREAD shifts every earlier segment by the
            # same post−pre gap) so a caller can re-base co-moving state (the SleeveLedger) in step.
            old_series = self._series
            self.materialize(end=bar_day.isoformat())
            self._last_roll_spread = _rebase_spread(old_series, self._series)
            return
        if bar.bar_type.instrument_id != self._front_id:
            return
        row = bars_to_ohlcv([bar])
        # The engine stamps each continuous bar at its bucket boundary, not the raw event time:
        # a close-of-day (00:00) bar already sits on the boundary, an intraday (e.g. 21:00) bar
        # rolls up to the next one. ``ceil`` to the bucket captures both, so the appended row
        # lands on the engine's index regardless of the venue's daily stamp. The value needs no
        # adjustment — the front is offset 0 (today's continuous value IS the raw front close).
        row.index = row.index.ceil(self._timeframe)
        self._series = pd.concat([self._series, row])

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


def _rebase_spread(old: pd.DataFrame, new: pd.DataFrame) -> float:
    """The uniform additive spread Δ between two materializations of the same series.

    A BACKWARD_SPREAD roll shifts every pre-roll close by one Δ, so the gap on any date present in
    both bases is the same; read it off the earliest overlapping close (unambiguously pre-roll).
    """
    common = old.index.intersection(new.index)
    if len(common) == 0:
        return 0.0
    anchor = common[0]
    return float(new.loc[anchor, "Close"] - old.loc[anchor, "Close"])
