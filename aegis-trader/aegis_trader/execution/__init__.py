"""Execution port — provider-agnostic order translation and instrument resolution.

For Slice 3: FIGI→InstrumentId Security Master (bimap from OpenFIGI +
exchange table).  Netting happens in FIGI space; resolution to Nautilus
InstrumentId only at the execution edge.
"""

from aegis_trader.execution.figi_resolver import (
    FigiInstrumentResolver,
    FigiResolutionError,
)

__all__ = [
    "FigiInstrumentResolver",
    "FigiResolutionError",
]
