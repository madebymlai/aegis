"""Shared test doubles for pipeline-stage unit tests.

These stand-ins replace production types that carry heavy dependencies
(e.g. MarketDataResult, DataArrayContract) so that pipeline-stage tests
can construct the minimal surface each stage reads without importing
the full data or array stack.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.aegis_research.market_data.contracts import (
    ArrayDescriptor,
    CoverageFacet,
    MarketDataMetadataV3,
    MarketDataQuality,
    ProvenanceFacet,
    RequestFacet,
)


def default_metadata(
    *,
    source: str = "synthetic",
    symbols: list[str] | None = None,
    effective_arrays: list[str] | None = None,
    rows: int = 120,
    start: str | None = "2020-01-01",
    end: str | None = "2020-06-01",
) -> MarketDataMetadataV3:
    """Build a minimal ``MarketDataMetadataV3`` for test doubles.

    Callers that need a specific facet shape can pass keyword overrides;
    the defaults represent the simplest healthy synthetic-data fixture.
    """
    syms = symbols or ["SYN"]
    arrays = effective_arrays or ["Close", "Open"]
    return MarketDataMetadataV3(
        schema_version="market_data.v3",
        request=RequestFacet(
            source=source,
            requested_symbols=syms,
            timeframe="1D",
            authored_arrays=arrays,
            effective_arrays=arrays,
        ),
        arrays=[
            ArrayDescriptor(name=name, required=True, loaded=True, observed=True, ohlc=name in {"Close", "Open", "High", "Low", "Volume"})
            for name in arrays
        ],
        coverage=CoverageFacet(symbols=syms, rows=rows, start=start, end=end),
        quality=MarketDataQuality(state="healthy"),
        diagnostics=[],
        provenance=ProvenanceFacet(
            provider_class=None,
            source_metadata={},
            index_evidence={},
            provider_metadata={},
            omitted_metadata_fields=[],
            update_supported=False,
            missing_index="raise",
            missing_columns="raise",
            tz_localize=None,
            tz_convert=None,
            skip_on_error=False,
            silence_warnings=False,
        ),
    )


class FakeDataResult:
    """Lightweight stand-in for ``MarketDataResult``.

    ``metadata`` is a class attribute so every instance surfaces identical
    metadata — tests never mutate it during a stage invocation.
    Pass ``metadata`` to override it for specialised fixtures; otherwise
    :func:`default_metadata` supplies the common healthy-synthetic shape.
    ``quality`` is an instance attribute so it can hold a simple
    stand-in without pulling in the real quality model.
    """

    metadata = default_metadata()

    def __init__(
        self,
        *,
        quality_state: str = "healthy",
        metadata: MarketDataMetadataV3 | None = None,
    ) -> None:
        self.quality = type("_Quality", (), {"state": quality_state})()
        if metadata is not None:
            self.metadata = metadata


class FakeArrayContract:
    """Stand-in for ``DataArrayContract``."""

    def metadata(self) -> dict[str, Any]:
        return {"schema_version": "data_array_contract.v1"}


class FakeManifest:
    """Stand-in for the run manifest surface pipeline stages read and mark."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.status = "running"
        self.started_at = "2025-01-01T00:00:00Z"
        self.finished_at: str | None = None
        self.evidence: dict[str, Any] = {}


class FakeRecorder:
    """Stand-in for ``RunRecorder``.

    ``run_dir`` is optional: publishing reads only ``manifest``; completion
    also reads ``run_dir``/``manifest_path`` and marks the run completed.
    """

    def __init__(self, run_id: str, run_dir: Path | None = None) -> None:
        self.manifest = FakeManifest(run_id)
        self.run_dir = run_dir
        self.manifest_path = run_dir / "manifest.json" if run_dir is not None else None

    def persist(self) -> None:
        pass

    def mark_run_completed(self) -> None:
        self.manifest.status = "completed"
        self.manifest.finished_at = "2025-01-01T01:00:00Z"
        self.persist()

    def run_refs(self) -> dict[str, Any]:
        return {
            "run_id": self.manifest.run_id,
            "run_dir": str(self.run_dir) if self.run_dir is not None else "",
            "manifest_path": str(self.manifest_path) if self.manifest_path is not None else "",
            "status": self.manifest.status,
            "started_at": self.manifest.started_at,
            "finished_at": self.manifest.finished_at,
        }
