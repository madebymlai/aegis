"""Mutable Execution Bundle test doubles for orchestration failure seams."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import (
    BundleManifest,
    DataContract,
    DriftBand,
    ExecutionBundle,
    LockedExecutionPlan,
)
from aegis_trader.bundles.stub import StubBundleRegistry


class BundleDouble:
    """Copy one valid root's public facts onto a mutable test collaborator."""

    def __init__(
        self,
        *,
        contract: DataContract,
        manifest: BundleManifest,
        plan: LockedExecutionPlan,
    ) -> None:
        root = ExecutionBundle(contract=contract, manifest=manifest, plan=plan)
        self.contract = root.contract
        self.manifest = root.manifest
        self.plan = root.plan

    @property
    def direction(self) -> str:
        return self.plan.direction

    @property
    def instrument_bands(self) -> Mapping[InstrumentId, DriftBand]:
        return self.plan.instrument_bands


def make_bundle_registry(bundles: Mapping[str, object]) -> StubBundleRegistry:
    """Adapt structural test doubles at the test-only registry boundary."""
    typed = cast(dict[str, ExecutionBundle], dict(bundles))
    return StubBundleRegistry(typed)
