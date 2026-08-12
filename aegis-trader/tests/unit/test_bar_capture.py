"""Subscribed Bar capture through the ordinary Raw Bars collaborator."""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.bar_type import raw_bar_type
from aegis_data.provider import ProviderAnswer
from aegis_data.raw_bars import RawBars
from aegis_data.storage import Catalog, CatalogInterval
from aegis_trader.trader.bar_capture import BarCapture


@dataclass
class _Provider:
    requests: list[tuple[pd.Timestamp, pd.Timestamp]] = field(default_factory=list)

    def request_bars(
        self,
        _bar_type: BarType,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ProviderAnswer[Bar]:
        self.requests.append((start, end))
        return ProviderAnswer.verified((), oldest_verified=start)


def test_silent_subscribed_weekend_is_verified_empty_and_needs_no_fill(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path)
    instrument_id = InstrumentId.from_str("AAPL.XNAS")
    bar_type = raw_bar_type(instrument_id, "1D")
    provider = _Provider()
    raw_bars = RawBars(catalog, provider=provider)
    friday = pd.Timestamp("2024-01-05", tz="UTC").value
    monday = pd.Timestamp("2024-01-08", tz="UTC").value
    capture = BarCapture(raw_bars)

    capture.subscribe(bar_type, at_ns=friday)
    capture.observe(_bar(bar_type, "2024-01-05", 10.0))
    capture.verify_through(monday - 1)
    capture.observe(_bar(bar_type, "2024-01-08", 11.0))
    capture.verify_through(monday)
    marking = raw_bars.marking(instrument_id, "1D")
    raw_bars.ensure(marking, CatalogInterval(friday, monday))
    window = raw_bars.covered(marking, CatalogInterval(friday, monday))

    assert [bar.close.as_double() for bar in window.bars] == [10.0, 11.0]
    assert provider.requests == []


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
