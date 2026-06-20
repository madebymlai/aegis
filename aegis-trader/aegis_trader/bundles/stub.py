"""Stub bundle registry for Slice 1 (tracer) — returns synthetic
ExecutionBundles built from test fixtures.  Real wheel loading + entry-point
discovery arrives in Slice 3.
"""

from __future__ import annotations

from aegis_runtime import DataContract, ExecutionBundle


class StubBundleRegistry:
    """Returns pre-built ExecutionBundle instances keyed by wheel filename.

    Does not touch the filesystem or entry points; the test fixture owns the
    bundle and registers it here.
    """

    def __init__(self, bundles: dict[str, ExecutionBundle] | None = None) -> None:
        self._bundles: dict[str, ExecutionBundle] = dict(bundles) if bundles else {}

    def register(self, wheel_filename: str, bundle: ExecutionBundle) -> None:
        self._bundles[wheel_filename] = bundle

    def load(self, wheel_filename: str) -> ExecutionBundle:
        bundle = self._bundles.get(wheel_filename)
        if bundle is None:
            raise KeyError(f"no bundle registered for {wheel_filename!r}")
        return bundle

    def load_contract(self, wheel_filename: str) -> DataContract:
        return self.load(wheel_filename).contract
