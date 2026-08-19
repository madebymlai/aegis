from nautilus_trader.core.data import Data
from nautilus_trader.model.custom import customdataclass
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.custom_kinds import (
    ArrayProjection,
    CustomDataKind,
    CustomDataRegistry,
    HistoricalDataCapability,
    LiveDataCapability,
)


@customdataclass
class FixtureRecord(Data):
    instrument_id: InstrumentId = InstrumentId.from_str("SPY.ARCA")
    value: float = 0.0
    provider: str = "fixture"


@customdataclass
class DormantFixtureRecord(Data):
    instrument_id: InstrumentId = InstrumentId.from_str("SPY.ARCA")
    value: float = 0.0


FIXTURE_CUSTOM_DATA_KINDS = CustomDataRegistry(
    (
        CustomDataKind(
            FixtureRecord,
            ArrayProjection(
                "FixtureValue",
                "FixtureAvailable",
                "FixtureAgeDays",
                "value",
            ),
            historical=HistoricalDataCapability(),
            live=LiveDataCapability(),
        ),
        CustomDataKind(
            DormantFixtureRecord,
            ArrayProjection(
                "DormantFixtureValue",
                "DormantFixtureAvailable",
                "DormantFixtureAgeDays",
                "value",
            ),
            historical=None,
        ),
    )
)
