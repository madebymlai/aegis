from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from aegis_data.bar_type import raw_bar_type
from aegis_data.raw_bars import RawBars
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey


@dataclass
class _Provider:
    catalog: Catalog
    records: tuple[Bar, ...]
    requests: list[BarType] = field(default_factory=list)

    def warm_bars(
        self,
        bar_type: BarType,
        interval: CatalogInterval,
    ) -> bool:
        key = CatalogKey.for_bar(bar_type)
        missing = self.catalog.missing(key, interval)
        if not missing:
            return False
        self.requests.append(bar_type)
        for gap in missing:
            self.catalog.replace(key, gap, self.records)
        return True


def test_stored_reads_payload_without_filling(tmp_path: Path) -> None:
    catalog = Catalog.open(tmp_path)
    instrument_id = InstrumentId.from_str("AAPL.XNAS")
    bar_type = raw_bar_type(instrument_id, "1D")
    interval = _interval()
    catalog.replace(
        CatalogKey.for_bar(bar_type),
        interval,
        (_bar(bar_type, "2024-01-01", 10.0),),
    )
    provider = _Provider(catalog, (_bar(bar_type, "2024-01-01", 20.0),))
    raw_bars = RawBars(catalog, provider=provider)
    marking = raw_bars.marking(instrument_id, "1D")

    stored = raw_bars.stored(marking, interval)

    assert stored.ohlcv["Close"].tolist() == [10.0]
    assert provider.requests == []


def test_a_window_the_data_engine_stored_reads_back(tmp_path: Path) -> None:
    """Bars the Nautilus data engine wrote must read back as ours.

    ``request_bars(update_catalog=True)`` — live in the roll, fast-forward and
    strategy paths — has the engine write its response straight into the
    catalog, naming the file for the window it requested. Those native file
    extents are the only interval state, so the window reads without another
    fetch.
    """
    catalog = Catalog.open(tmp_path)
    instrument_id = InstrumentId.from_str("AAPL.XNAS")
    bar_type = raw_bar_type(instrument_id, "1D")
    interval = _interval()
    # Exactly what the engine does with a response it decided to persist.
    catalog._store.write_data(
        [_bar(bar_type, "2024-01-01", 10.0)],
        interval.start_ns,
        interval.end_ns,
        data_cls=Bar,
        identifier=str(bar_type),
    )
    raw_bars = RawBars(catalog, provider=None)
    marking = raw_bars.marking(instrument_id, "1D")

    window = raw_bars.stored(marking, interval)

    assert window.ohlcv["Close"].tolist() == [10.0]


def test_a_read_returns_empty_for_an_unfilled_window_and_asks_no_provider(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path)
    instrument_id = InstrumentId.from_str("AAPL.XNAS")
    bar_type = raw_bar_type(instrument_id, "1D")
    interval = _interval()
    provider = _Provider(catalog, (_bar(bar_type, "2024-01-01", 20.0),))
    raw_bars = RawBars(catalog, provider=provider)
    marking = raw_bars.marking(instrument_id, "1D")

    window = raw_bars.stored(marking, interval)

    assert window.bars == ()
    assert provider.requests == []


def test_ensure_is_a_command_and_the_read_is_the_following_query(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path)
    instrument_id = InstrumentId.from_str("AAPL.XNAS")
    bar_type = raw_bar_type(instrument_id, "1D")
    provider = _Provider(catalog, (_bar(bar_type, "2024-01-01", 20.0),))
    raw_bars = RawBars(catalog, provider=provider)
    marking = raw_bars.marking(instrument_id, "1D")

    result = raw_bars.ensure(marking, _interval())
    window = raw_bars.stored(marking, _interval())

    assert result is None
    assert window.bars == provider.records
    assert window.ohlcv["Close"].tolist() == [20.0]
    assert provider.requests == [bar_type]


def test_replace_interval_extends_catalog_over_empty_time(
    tmp_path: Path,
) -> None:
    catalog = Catalog.open(tmp_path)
    instrument_id = InstrumentId.from_str("AAPL.XNAS")
    bar_type = raw_bar_type(instrument_id, "1D")
    provider = _Provider(catalog, ())
    raw_bars = RawBars(catalog, provider=provider)
    marking = raw_bars.marking(instrument_id, "1D")
    friday = pd.Timestamp("2024-01-05", tz="UTC").value
    monday = pd.Timestamp("2024-01-08", tz="UTC").value

    raw_bars.replace_interval(
        bar_type,
        CatalogInterval(friday, friday),
        (_bar(bar_type, "2024-01-05", 10.0),),
    )
    raw_bars.replace_interval(
        bar_type,
        CatalogInterval(friday + 1, monday - 1),
        (),
    )
    raw_bars.replace_interval(
        bar_type,
        CatalogInterval(monday, monday),
        (_bar(bar_type, "2024-01-08", 11.0),),
    )
    raw_bars.ensure(marking, CatalogInterval(friday, monday))
    window = raw_bars.stored(marking, CatalogInterval(friday, monday))

    assert [bar.close.as_double() for bar in window.bars] == [10.0, 11.0]
    assert provider.requests == []


def _interval() -> CatalogInterval:
    return CatalogInterval(
        pd.Timestamp("2024-01-01", tz="UTC").value,
        pd.Timestamp("2024-01-02", tz="UTC").value,
    )


def _bar(bar_type: BarType, day: str, close: float) -> Bar:
    timestamp = pd.Timestamp(day, tz="UTC").value
    return Bar(
        bar_type,
        Price.from_str(str(close)),
        Price.from_str(str(close)),
        Price.from_str(str(close)),
        Price.from_str(str(close)),
        Quantity.from_int(1),
        timestamp,
        timestamp,
    )


def _bar_at(bar_type: BarType, at: int) -> Bar:
    price = Price.from_str("470.00")
    return Bar(bar_type, price, price, price, price, Quantity.from_int(1), at, at)


def test_capture_ticks_consolidate_instead_of_accumulating_a_file_each(
    tmp_path: Path,
) -> None:
    """Tidying must keep working while the rest of the day is still unchecked.

    Compaction exists so a captured stream does not leave one durable file per
    arriving Bar. It is narrowed to the run that has been answered, and during
    a session the day's remaining hours legitimately have not been — so the
    range asked about has to end at what was just written, not at midnight, or
    the narrowing declines every merge and the fragments accumulate.
    """
    catalog = Catalog.open(tmp_path)
    bar_type = BarType.from_str("SPY.ARCA-1-MINUTE-LAST-EXTERNAL")
    raw_bars = RawBars(catalog)
    opening = pd.Timestamp("2024-01-08 09:00", tz="UTC").value
    minute = pd.Timedelta(minutes=1).value

    frontier = opening - 1
    for tick in range(1, 13):
        end = opening + tick * minute - 1
        raw_bars.replace_interval(
            bar_type,
            CatalogInterval(frontier + 1, end),
            (_bar_at(bar_type, frontier + 1),),
        )
        frontier = end

    assert len(list(tmp_path.rglob("*.parquet"))) == 1
