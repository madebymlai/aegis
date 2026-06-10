"""Shared test doubles for pipeline-stage unit tests.

These stand-ins replace production types that carry heavy dependencies
(e.g. MarketDataResult, DataArrayContract) so that pipeline-stage tests
can construct the minimal surface each stage reads without importing
the full data or array stack.
"""

from __future__ import annotations

from typing import Any, ClassVar


class FakeDataResult:
    """Lightweight stand-in for ``MarketDataResult``.

    ``metadata`` is a ClassVar so every instance surfaces identical
    metadata — tests never mutate it during a stage invocation.
    ``quality`` is an instance attribute so it can hold a simple
    stand-in without pulling in the real quality model.
    """

    metadata: ClassVar[dict[str, Any]] = {
        "source": "synthetic",
        "symbols": ["SYN"],
        "timeframe": "1D",
        "loaded_arrays": ["Close", "Open"],
        "shape": (120, 1),
        "index_start": "2020-01-01",
        "index_end": "2020-06-01",
    }

    def __init__(self, *, quality_state: str = "healthy") -> None:
        self.quality = type("_Quality", (), {"state": quality_state})()


class FakeArrayContract:
    """Stand-in for ``DataArrayContract``."""

    def metadata(self) -> dict[str, Any]:
        return {"schema_version": "data_array_contract.v1"}
