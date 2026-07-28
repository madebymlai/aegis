"""Shared resolution policy for a Run's ordered tradeable universe."""

from __future__ import annotations

from dataclasses import dataclass

from aegis_data.catalog import CatalogBackedDataPort
from aegis_runtime import DriftBand
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.configuration import DataConfig, PortfolioConfig


@dataclass(frozen=True)
class TradeableInstrument:
    instrument_id: InstrumentId
    continuous_root: str | None = None

    @property
    def override_key(self) -> str:
        return self.continuous_root or self.instrument_id.value


@dataclass(frozen=True)
class InstrumentResolution:
    tradeables: tuple[TradeableInstrument, ...]

    @property
    def instrument_ids(self) -> tuple[InstrumentId, ...]:
        return tuple(tradeable.instrument_id for tradeable in self.tradeables)

    def instrument_bands(self, portfolio: PortfolioConfig) -> dict[InstrumentId, DriftBand]:
        return {
            tradeable.instrument_id: portfolio.resolved_band_for(tradeable.override_key)
            for tradeable in self.tradeables
        }


def resolve_instruments(
    config: DataConfig,
    *,
    port: CatalogBackedDataPort,
) -> InstrumentResolution:
    native = tuple(
        TradeableInstrument(InstrumentId.from_str(value)) for value in config.instruments
    )
    continuous = tuple(
        TradeableInstrument(
            instrument_id=port.resolve_continuous(root).instrument_id,
            continuous_root=root,
        )
        for root in config.futures
    )
    return InstrumentResolution((*native, *continuous))
