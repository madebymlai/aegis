"""One config contract shared by merger shadow collection and history replay."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml
from nautilus_trader.model.identifiers import InstrumentId


class PrototypeConfigError(ValueError):
    """The prototype YAML cannot define a merger observation."""


@dataclass(frozen=True)
class ResearchCapital:
    """Positive finite research notional supplied to the merger selector."""

    value: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.value) or self.value <= 0.0:
            raise PrototypeConfigError("shadow_capital must be positive and finite")


@dataclass(frozen=True)
class CashMergerPrototypeConfig:
    """Inputs authored once for both prospective and historical prototype runs."""

    capital: ResearchCapital
    instrument_ids: tuple[InstrumentId, ...]
    market_instrument_id: InstrumentId
    catalog_path: Path | None


def load_prototype_config(path: Path) -> CashMergerPrototypeConfig:
    """Load the single merger-prototype YAML contract."""

    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict):
        raise PrototypeConfigError("merger config must be a YAML mapping")
    unknown = set(payload) - {
        "shadow_capital",
        "instrument_ids",
        "market_instrument_id",
        "catalog_path",
    }
    if unknown:
        raise PrototypeConfigError(f"unknown merger config fields: {sorted(unknown)}")
    try:
        capital_value = float(payload.get("shadow_capital", 0.0))
    except (TypeError, ValueError) as error:
        raise PrototypeConfigError("shadow_capital must be numeric") from error
    capital = ResearchCapital(capital_value)
    raw_ids = payload.get("instrument_ids")
    if not isinstance(raw_ids, list) or not raw_ids or not all(
        isinstance(instrument_id, str) for instrument_id in raw_ids
    ):
        raise PrototypeConfigError(
            "instrument_ids must be a non-empty list of InstrumentId strings"
        )
    raw_market_id = payload.get("market_instrument_id", "SPY.ARCA")
    if not isinstance(raw_market_id, str):
        raise PrototypeConfigError("market_instrument_id must be an InstrumentId string")
    try:
        instrument_ids = tuple(
            dict.fromkeys(InstrumentId.from_str(value) for value in raw_ids)
        )
        market_instrument_id = InstrumentId.from_str(raw_market_id)
    except ValueError as error:
        raise PrototypeConfigError(f"invalid InstrumentId: {error}") from error
    catalog = payload.get("catalog_path")
    if catalog is not None and not isinstance(catalog, str):
        raise PrototypeConfigError("catalog_path must be a path string")
    return CashMergerPrototypeConfig(
        capital=capital,
        instrument_ids=instrument_ids,
        market_instrument_id=market_instrument_id,
        catalog_path=Path(catalog).expanduser() if catalog is not None else None,
    )
