from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from nautilus_trader.data.client import MarketDataClient
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import ClientId, InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.bar_type import raw_bar_type
from aegis_data.research_bars import CatalogBarWarmer
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey


class _FixtureBarClient(MarketDataClient):
    def __init__(
        self,
        msgbus: Any,
        cache: Any,
        clock: Any,
        bars: tuple[Bar, ...],
        calls: list[CatalogInterval],
    ) -> None:
        super().__init__(ClientId("FIXTURE-HIST"), msgbus, cache, clock, None, None)
        self._bars = bars
        self._calls = calls

    def _connect(self) -> None:
        pass

    def _disconnect(self) -> None:
        pass

    def request_bars(self, request: Any) -> None:
        interval = CatalogInterval(request.start.value, request.end.value)
        self._calls.append(interval)
        selected = [
            bar
            for bar in self._bars
            if interval.start_ns <= bar.ts_event <= interval.end_ns
        ]
        self._handle_bars_py(
            request.bar_type,
            selected,
            request.id,
            request.start,
            request.end,
            request.params,
        )


@dataclass
class _FixtureClientFactory:
    bars: tuple[Bar, ...]
    calls: list[CatalogInterval]

    def __call__(self, msgbus: Any, cache: Any, clock: Any) -> MarketDataClient:
        return _FixtureBarClient(msgbus, cache, clock, self.bars, self.calls)


def test_data_engine_owns_gap_detection_and_records_the_requested_window(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path)
    bar_type = raw_bar_type(InstrumentId.from_str("AAPL.XNAS"), "1D")
    interval = CatalogInterval(
        pd.Timestamp("2024-01-01", tz="UTC").value,
        pd.Timestamp("2024-01-04", tz="UTC").value,
    )
    calls: list[CatalogInterval] = []
    factory = _FixtureClientFactory(
        (_bar(bar_type, "2024-01-03", 10.0),),
        calls,
    )
    warmer = CatalogBarWarmer(catalog, factory)

    first_fetched = warmer.warm_bars(bar_type, interval)
    second_fetched = warmer.warm_bars(bar_type, interval)

    assert first_fetched is True
    assert second_fetched is False
    assert calls == [interval]
    assert catalog.missing(CatalogKey.for_bar(bar_type), interval) == ()
    assert catalog.read(CatalogKey.for_bar(bar_type), interval) == factory.bars


def _bar(bar_type: BarType, timestamp: str, close: float) -> Bar:
    ts_ns = pd.Timestamp(timestamp, tz="UTC").value
    price = Price.from_str(str(close))
    return Bar(
        bar_type=bar_type,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Quantity.from_int(1),
        ts_event=ts_ns,
        ts_init=ts_ns,
    )
