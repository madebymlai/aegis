"""Subscribed Bar capture through the ordinary Raw Bars collaborator."""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pytest
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.bar_type import raw_bar_type
from aegis_data.raw_bars import RawBars
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey
from aegis_trader.trader.bar_capture import BarCapture


@dataclass
class _Provider:
    catalog: Catalog
    requests: list[tuple[pd.Timestamp, pd.Timestamp]] = field(default_factory=list)

    def warm_bars(
        self,
        bar_type: BarType,
        interval: CatalogInterval,
    ) -> bool:
        if self.catalog.missing(CatalogKey.for_bar(bar_type), interval):
            self.requests.append((interval.start, interval.end))
            return True
        return False


@dataclass
class _RecordingRawBars:
    intervals: list[CatalogInterval] = field(default_factory=list)

    def covered_through(self, _bar_type: BarType) -> int | None:
        return None

    def record_verified(
        self,
        _bar_type: BarType,
        interval: CatalogInterval,
        _records: tuple[Bar, ...],
    ) -> None:
        self.intervals.append(interval)


def test_capture_frontier_advances_by_exact_nanosecond_adjacency() -> None:
    bar_type = BarType.from_str("SPY.ARCA-1-MINUTE-LAST-EXTERNAL")
    subscribed_at = pd.Timestamp("2024-01-08 09:00", tz="UTC").value
    cadence = pd.Timedelta(minutes=1).value
    raw_bars = _RecordingRawBars()
    capture = BarCapture(raw_bars)  # type: ignore[arg-type]

    capture.subscribe(bar_type, at_ns=subscribed_at)
    capture.verify_clock(subscribed_at + 2 * cadence)

    previous_end = subscribed_at - 1
    written = raw_bars.intervals[0]
    deliberately_gapped = CatalogInterval(subscribed_at + 1, written.end_ns)
    assert written.start_ns == previous_end + 1
    with pytest.raises(AssertionError):
        assert deliberately_gapped.start_ns == previous_end + 1


def test_silent_subscribed_weekend_is_verified_empty_and_needs_no_fill(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path)
    instrument_id = InstrumentId.from_str("AAPL.XNAS")
    bar_type = raw_bar_type(instrument_id, "1D")
    provider = _Provider(catalog)
    raw_bars = RawBars(catalog, provider=provider)
    friday = pd.Timestamp("2024-01-05", tz="UTC").value
    monday = pd.Timestamp("2024-01-08", tz="UTC").value
    capture = BarCapture(raw_bars)

    capture.subscribe(bar_type, at_ns=friday)
    capture.observe(_bar(bar_type, "2024-01-05", 10.0))
    capture.verify_clock(monday)
    capture.observe(_bar(bar_type, "2024-01-08", 11.0))
    capture.verify_clock(monday + _ONE_DAY_NS)
    marking = raw_bars.marking(instrument_id, "1D")
    raw_bars.ensure(marking, CatalogInterval(friday, monday))
    window = raw_bars.covered(marking, CatalogInterval(friday, monday))

    assert [bar.close.as_double() for bar in window.bars] == [10.0, 11.0]
    assert provider.requests == []


def test_one_streams_arrival_never_declares_another_stream_silent(
    tmp_path: Path,
) -> None:
    """A verdict may only come from the clock, never from a peer's arrival.

    Daily Bars are stamped at their UTC close, so two instruments that traded
    the same session carry the identical ``ts_event``. Whichever is delivered
    first must not make the other one's day a checked, empty fact.
    """
    catalog = Catalog.open(tmp_path)
    raw_bars = RawBars(catalog)
    capture = BarCapture(raw_bars)
    speaker = raw_bar_type(InstrumentId.from_str("AAPL.XNAS"), "1D")
    peer = raw_bar_type(InstrumentId.from_str("MSFT.XNAS"), "1D")
    thursday = pd.Timestamp("2024-01-04", tz="UTC").value
    close = pd.Timestamp("2024-01-05", tz="UTC").value
    capture.subscribe(speaker, at_ns=thursday)
    capture.subscribe(peer, at_ns=thursday)

    capture.observe(_bar(speaker, "2024-01-05", 10.0))

    assert raw_bars.covered_through(peer) is None
    capture.observe(_bar(peer, "2024-01-05", 20.0))
    capture.verify_clock(close + _ONE_DAY_NS)
    marking = raw_bars.marking(InstrumentId.from_str("MSFT.XNAS"), "1D")
    window = raw_bars.covered(marking, CatalogInterval(thursday, close))
    assert [bar.close.as_double() for bar in window.bars] == [20.0]


_ONE_DAY_NS = 86_400_000_000_000


def _bar(bar_type: BarType, day: str, close: float) -> Bar:
    timestamp = pd.Timestamp(day, tz="UTC").value
    price = Price.from_str(str(close))
    return Bar(
        bar_type,
        price,
        price,
        price,
        price,
        Quantity.from_int(1),
        timestamp,
        timestamp,
    )
