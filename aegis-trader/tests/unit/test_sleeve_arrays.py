"""Complete Sleeve array assembly through one deep module."""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.custom_data import CustomDataProviderPort
from aegis_data.storage import Catalog
from aegis_runtime import DataContract, MissingIndexPolicy

from aegis_trader.data.market_data import MarketBar
from aegis_trader.trader.sleeve_arrays import (
    ArrayNeed,
    InvalidArrayCoverageWindowError,
    SleeveArrayGrid,
    SleeveArrays,
)
from tests.support.custom_data import FixtureRecord

_FIRST = InstrumentId.from_str("AAA.XLON")
_SECOND = InstrumentId.from_str("BBB.XBRU")
_DAY_NS = 86_400_000_000_000


@dataclass
class _Provider(CustomDataProviderPort[FixtureRecord]):
    available: tuple[FixtureRecord, ...]
    requests: list[tuple[pd.Timestamp, pd.Timestamp]] = field(default_factory=list)

    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> tuple[FixtureRecord, ...]:
        self.requests.append((start, end))
        records = tuple(
            record
            for record in self.available
            if record.instrument_id == instrument_id
            and start.value <= record.ts_event <= end.value
        )
        return records


def test_sleeve_arrays_projects_every_required_bar_array_on_the_union_grid(
    tmp_path: Path,
) -> None:
    contract = _contract(
        instrument_ids=(_FIRST, _SECOND),
        required_arrays=("Open", "Close"),
    )
    grid = SleeveArrayGrid.from_bars(contract, _misaligned_bars())
    arrays = SleeveArrays.prepared(catalog=Catalog.open(tmp_path))
    expected_index = pd.DatetimeIndex([0, 86_400_000_000_000, 172_800_000_000_000])
    expected_open = pd.DataFrame(
        {
            _FIRST: [10.0, 11.0, float("nan")],
            _SECOND: [float("nan"), 20.0, 21.0],
        },
        index=expected_index,
    )

    arrays.ensure(grid.need)
    panels = arrays.project(grid)

    assert tuple(panels) == ("Open", "Close")
    assert panels["Close"].index.equals(expected_index)
    assert panels["Close"].columns.tolist() == [_FIRST, _SECOND]
    pd.testing.assert_frame_equal(panels["Open"], expected_open)


def test_sleeve_arrays_heals_catalog_coverage_with_live_provider(
    tmp_path: Path,
) -> None:
    contract = _contract(
        instrument_ids=(_FIRST,),
        required_arrays=("Close", "FixtureValue", "FixtureAvailable"),
    )
    bars = {
        _FIRST: (
            _bar(0, 10.0),
            _bar(_DAY_NS, 11.0),
            _bar(2 * _DAY_NS, 12.0),
        )
    }
    record = FixtureRecord(
        _DAY_NS,
        _DAY_NS,
        instrument_id=_FIRST,
        value=7.0,
        provider="fixture",
    )
    provider = _Provider((record,))
    arrays = SleeveArrays.live(
        catalog=Catalog.open(tmp_path),
        providers={FixtureRecord: provider},
    )
    grid = SleeveArrayGrid.from_bars(contract, bars)

    arrays.ensure(grid.need)

    assert provider.requests == [
        (
            pd.Timestamp(0, tz="UTC"),
            pd.Timestamp(172_800_000_000_000, tz="UTC"),
        )
    ]


def test_sleeve_arrays_projects_custom_panels_after_ensure(tmp_path: Path) -> None:
    contract = _contract(
        instrument_ids=(_FIRST,),
        required_arrays=("Close", "FixtureValue", "FixtureAvailable"),
    )
    bars = {
        _FIRST: (
            _bar(0, 10.0),
            _bar(_DAY_NS, 11.0),
            _bar(2 * _DAY_NS, 12.0),
        )
    }
    record = FixtureRecord(
        _DAY_NS,
        _DAY_NS,
        instrument_id=_FIRST,
        value=7.0,
        provider="fixture",
    )
    arrays = SleeveArrays.live(
        catalog=Catalog.open(tmp_path),
        providers={FixtureRecord: _Provider((record,))},
    )
    grid = SleeveArrayGrid.from_bars(contract, bars)

    arrays.ensure(grid.need)
    panels = arrays.project(grid)

    assert tuple(panels) == ("Close", "FixtureValue", "FixtureAvailable")
    assert panels["Close"].to_numpy().tolist() == [[10.0], [11.0], [12.0]]
    assert panels["FixtureValue"].to_numpy().tolist() == [[0.0], [7.0], [7.0]]
    assert panels["FixtureAvailable"].to_numpy().tolist() == [[0.0], [1.0], [1.0]]


def test_array_need_rejects_an_inverted_coverage_window() -> None:
    with pytest.raises(InvalidArrayCoverageWindowError):
        ArrayNeed(
            names=("Close",),
            instrument_ids=(_FIRST,),
            start=pd.Timestamp("2024-01-02", tz="UTC"),
            end=pd.Timestamp("2024-01-01", tz="UTC"),
        )


def test_sleeve_arrays_projection_treats_absent_custom_data_as_empty(
    tmp_path: Path,
) -> None:
    contract = _contract(
        instrument_ids=(_FIRST,),
        required_arrays=("Close", "FixtureValue", "FixtureAvailable"),
    )
    grid = SleeveArrayGrid.from_bars(
        contract,
        {_FIRST: (_bar(0, 10.0), _bar(_DAY_NS, 11.0))},
    )
    arrays = SleeveArrays.prepared(catalog=Catalog.open(tmp_path))

    panels = arrays.project(grid)

    assert panels["FixtureValue"].to_numpy().tolist() == [[0.0], [0.0]]
    assert panels["FixtureAvailable"].to_numpy().tolist() == [[0.0], [0.0]]


def _contract(
    *,
    instrument_ids: tuple[InstrumentId, ...],
    required_arrays: tuple[str, ...],
) -> DataContract:
    return DataContract(
        instrument_ids=instrument_ids,
        required_arrays=required_arrays,
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.NAN,
        lookback_bars=2,
    )


def _misaligned_bars() -> dict[InstrumentId, tuple[MarketBar, ...]]:
    return {
        _FIRST: (_bar(0, 10.0), _bar(_DAY_NS, 11.0)),
        _SECOND: (_bar(_DAY_NS, 20.0), _bar(2 * _DAY_NS, 21.0)),
    }


def _bar(timestamp_ns: int, price: float) -> MarketBar:
    return MarketBar(timestamp_ns, price, price, price, price, 1_000.0)
