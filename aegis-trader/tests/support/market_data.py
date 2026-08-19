"""Native Raw Bar fixtures shared by backtest tests."""

from __future__ import annotations

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.marking import DeclaredMarkingResolver, MarkMode
from aegis_data.raw_bars import RawBarWindow


def bar_window_from_frames(
    instrument_id: InstrumentId,
    timeframe: str,
    mark_mode: MarkMode,
    frames: tuple[pd.DataFrame, ...],
    *,
    price_precision: int = 2,
) -> RawBarWindow:
    """Build one native Raw Bar window from its mark projections."""
    marking = DeclaredMarkingResolver(
        declared={instrument_id: mark_mode}
    ).resolve(instrument_id, timeframe)
    if len(marking.mark_bars) != len(frames):
        raise ValueError("one frame is required for each marking BarType")
    return RawBarWindow(
        marking=marking,
        by_type={
            bar_type: _bars_from_frame(bar_type, frame, price_precision)
            for bar_type, frame in zip(marking.mark_bars, frames, strict=True)
        },
    )


def _bars_from_frame(
    bar_type: BarType,
    frame: pd.DataFrame,
    price_precision: int,
) -> tuple[Bar, ...]:
    return tuple(
        _bar_from_row(bar_type, timestamp, row, price_precision)
        for timestamp, row in frame.iterrows()
    )


def _bar_from_row(
    bar_type: BarType,
    timestamp: object,
    row: pd.Series,
    price_precision: int,
) -> Bar:
    ts_event = pd.Timestamp(timestamp)
    ts_event = (
        ts_event.tz_localize("UTC")
        if ts_event.tz is None
        else ts_event.tz_convert("UTC")
    )

    def price(column: str) -> Price:
        return Price.from_str(f"{float(row[column]):.{price_precision}f}")

    return Bar(
        bar_type,
        price("Open"),
        price("High"),
        price("Low"),
        price("Close"),
        Quantity.from_int(int(row["Volume"])),
        ts_event.value,
        ts_event.value,
    )
