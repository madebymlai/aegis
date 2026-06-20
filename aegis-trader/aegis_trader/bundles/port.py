"""Bundle registry port — loads an ExecutionBundle from a wheel filename.

In Slice 1 (tracer) this returns a synthetic in-memory bundle for testing;
real entry-point discovery + wheel loading arrives in Slice 3.
"""

from __future__ import annotations

from typing import Protocol

from aegis_runtime import DataContract, ExecutionBundle


class BundleRegistryPort(Protocol):
    """Loads (or stubs) an ExecutionBundle for a given Book Config sleeve."""

    def load(self, wheel_filename: str) -> ExecutionBundle:
        """Return the ExecutionBundle identified by *wheel_filename*."""
        ...

    def load_contract(self, wheel_filename: str) -> DataContract:
        """Return the DataContract for *wheel_filename* without instantiating the
        full bundle (used by the strategy to know required arrays/lookback/FX
        before the first bar arrives)."""
        ...
