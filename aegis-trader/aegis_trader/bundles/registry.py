"""Entry-point bundle registry — discovers an ExecutionBundle for a Book Config
sleeve's content-addressed wheel filename.

An execution-bundle wheel, once installed, advertises itself through an
``aegis.execution_bundles`` entry point whose *name* is the content-addressed
wheel filename the Book Config references and whose value is a zero-arg factory
returning the wheel's :class:`ExecutionBundle`.  The registry resolves that
filename to the installed bundle, failing closed when none is found.

The Slice 1 :class:`~aegis_trader.bundles.stub.StubBundleRegistry` remains for
tests that own their bundles in-memory; this is the real, install-grounded
loader.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from importlib.metadata import EntryPoint, entry_points

from aegis_runtime import DataContract, ExecutionBundle

BUNDLE_ENTRY_POINT_GROUP = "aegis.execution_bundles"

# Discovery seam: importlib.metadata.entry_points selected by group + name.
# Injected in tests so the discovery + load contract can be exercised without
# installing a real wheel.
DiscoverFn = Callable[[str, str], Sequence[EntryPoint]]


class BundleNotFoundError(LookupError):
    """No installed execution-bundle entry point matches the wheel filename."""


def _default_discover(group: str, name: str) -> Sequence[EntryPoint]:
    return list(entry_points(group=group, name=name))


class EntryPointBundleRegistry:
    """Loads ExecutionBundles installed as wheels via ``aegis.execution_bundles``."""

    def __init__(self, *, discover: DiscoverFn | None = None) -> None:
        self._discover: DiscoverFn = discover if discover is not None else _default_discover

    def load(self, wheel_filename: str) -> ExecutionBundle:
        """Return the ExecutionBundle advertised under *wheel_filename*."""
        matches = list(self._discover(BUNDLE_ENTRY_POINT_GROUP, wheel_filename))
        if not matches:
            raise BundleNotFoundError(
                f"no execution-bundle entry point named {wheel_filename!r} "
                f"in group {BUNDLE_ENTRY_POINT_GROUP!r}"
            )
        if len(matches) > 1:
            raise BundleNotFoundError(
                f"{len(matches)} execution-bundle entry points named "
                f"{wheel_filename!r}; a content-addressed wheel must resolve to "
                f"exactly one bundle"
            )
        factory = matches[0].load()
        bundle = factory()
        if not isinstance(bundle, ExecutionBundle):
            raise TypeError(
                f"entry point {wheel_filename!r} produced "
                f"{type(bundle).__name__}, not ExecutionBundle"
            )
        return bundle

    def load_contract(self, wheel_filename: str) -> DataContract:
        return self.load(wheel_filename).contract
