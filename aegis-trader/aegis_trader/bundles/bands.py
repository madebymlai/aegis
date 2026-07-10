"""Bundle-derived drift bands for live rebalance decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from aegis_runtime import DriftBand, InstrumentId

from aegis_trader.domain.types import SleeveName


class InstrumentBandError(ValueError):
    """A bundle band map cannot be converted to one unambiguous book-wide map."""

    def __init__(
        self,
        *,
        instrument_id: InstrumentId,
        sleeves: tuple[SleeveName, SleeveName],
    ) -> None:
        self.instrument_id = instrument_id
        self.sleeves = sleeves
        super().__init__(
            f"instrument {instrument_id.value!r} has drift bands in both "
            f"sleeve {sleeves[0].value!r} and sleeve {sleeves[1].value!r}"
        )


@dataclass(frozen=True)
class BundleBands:
    """Book-wide bundle bands plus each band's owning sleeve.

    Bands are research-calibrated at standalone-sleeve scale; ownership lets the
    rebalancer re-scale each band by its sleeve's allocator multiplier
    (aegis-rd-reyj), so the calibration transfers to book scale exactly.
    """

    bands: Mapping[InstrumentId, DriftBand]
    owner_by_instrument: Mapping[InstrumentId, SleeveName]
