"""Bundle-derived drift bands for live rebalance decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from aegis_runtime import DriftBand, ExecutionBundle, InstrumentId

from aegis_trader.domain.types import SleeveName


class InstrumentBandError(ValueError):
    """A bundle band map cannot be converted to one unambiguous book-wide map."""


@dataclass(frozen=True)
class BundleBands:
    """Book-wide bundle bands plus each band's owning sleeve.

    Bands are research-calibrated at standalone-sleeve scale; ownership lets the
    rebalancer re-scale each band by its sleeve's allocator multiplier
    (aegis-rd-reyj), so the calibration transfers to book scale exactly.
    """

    bands: Mapping[InstrumentId, DriftBand]
    owner_by_instrument: Mapping[InstrumentId, SleeveName]


def build_instrument_bands(
    bundles: Mapping[SleeveName, ExecutionBundle],
) -> BundleBands:
    """Merge loaded sleeve bundle bands into one flat, ownership-tagged map.

    Each live instrument must be owned by exactly one sleeve bundle. A held
    instrument absent from this map is no longer in any current bundle and the
    rebalancer trades it straight to flat.
    """
    owners: dict[InstrumentId, SleeveName] = {}
    bands: dict[InstrumentId, DriftBand] = {}

    for sleeve_name in sorted(bundles, key=lambda name: name.value):
        bundle = bundles[sleeve_name]
        for instrument_id, band in sorted(
            bundle.instrument_bands.items(), key=lambda item: item[0].value
        ):
            owner = owners.get(instrument_id)
            if owner is not None:
                raise InstrumentBandError(
                    f"instrument {instrument_id.value!r} has drift bands in both "
                    f"sleeve {owner.value!r} and sleeve {sleeve_name.value!r}"
                )
            owners[instrument_id] = sleeve_name
            bands[instrument_id] = band

    return BundleBands(
        bands=MappingProxyType(bands),
        owner_by_instrument=MappingProxyType(owners),
    )
