"""Integration tests for the entry-point bundle registry (B12).

The registry discovers ExecutionBundles installed as wheels that expose an
``aegis.execution_bundles`` entry point, keyed by the content-addressed wheel
filename the Book Config references.  These tests exercise the discovery + load
path with a fake *discover* seam (no real wheel installed) but a real
``importlib.metadata.EntryPoint``, so the entry-point ``load()`` contract is
exercised end to end.
"""

from __future__ import annotations

from importlib.metadata import EntryPoint

from nautilus_trader.model.identifiers import InstrumentId
import pytest

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
)

from aegis_trader.bundles.registry import (
    BUNDLE_ENTRY_POINT_GROUP,
    BundleNotFoundError,
    EntryPointBundleRegistry,
)

_WHEEL = "trend-deadbeef.whl"
_INSTRUMENT_ID = InstrumentId.from_str("BBG000B9XRY4.TEST")


def _build_bundle() -> ExecutionBundle:
    """A zero-arg bundle factory — the object an entry point resolves to."""
    contract = DataContract(
        instrument_ids=(_INSTRUMENT_ID,),
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        lookback_bars=1,
    )
    manifest = BundleManifest(
        run_id="r", role="x", candidate_key="k",
        component_source_hashes={}, instrument_ids=(_INSTRUMENT_ID,),
    )
    plan = LockedExecutionPlan(
        strategy=ComponentSpec(
            family="strategy", component_id="s", module="m",
            input_names=(), output_names=(), params={},
        ),
        indicators=(),
        gross_cap=1.0,
        net_cap=None,
        direction="both",
    )
    return ExecutionBundle(contract=contract, manifest=manifest, plan=plan)


def _fake_discover(group: str, name: str) -> list[EntryPoint]:
    """Stand in for importlib.metadata.entry_points(group=, name=)."""
    if group == BUNDLE_ENTRY_POINT_GROUP and name == _WHEEL:
        return [EntryPoint(
            name=_WHEEL,
            value="test_bundle_registry:_build_bundle",
            group=group,
        )]
    return []


def test_load_discovers_bundle_from_entry_point():
    """A wheel filename in the Book Config resolves to an installed bundle."""
    registry = EntryPointBundleRegistry(discover=_fake_discover)

    bundle = registry.load(_WHEEL)

    assert isinstance(bundle, ExecutionBundle)
    assert bundle.contract.instrument_ids == (_INSTRUMENT_ID,)


def test_ambiguous_wheel_fails_closed():
    """Two installed wheels claiming the same content-addressed name is
    unresolvable — the registry refuses to silently pick one."""
    def _two_matches(group: str, name: str) -> list[EntryPoint]:
        ep = EntryPoint(name=name, value="test_bundle_registry:_build_bundle", group=group)
        return [ep, ep]

    registry = EntryPointBundleRegistry(discover=_two_matches)

    with pytest.raises(BundleNotFoundError, match="2"):
        registry.load(_WHEEL)


def test_unknown_wheel_fails_closed():
    """A wheel filename with no installed bundle raises — never returns None."""
    registry = EntryPointBundleRegistry(discover=_fake_discover)

    with pytest.raises(BundleNotFoundError, match="no execution-bundle entry point"):
        registry.load("missing-cafef00d.whl")


def test_entry_point_producing_non_bundle_is_rejected():
    """A misconfigured wheel whose factory returns the wrong type fails loudly."""
    def _bad(group: str, name: str) -> list[EntryPoint]:
        return [EntryPoint(name=name, value="test_bundle_registry:_not_a_bundle", group=group)]

    registry = EntryPointBundleRegistry(discover=_bad)

    with pytest.raises(TypeError, match="not ExecutionBundle"):
        registry.load(_WHEEL)


def test_load_contract_returns_the_data_contract():
    """load_contract resolves a sleeve's DataContract without the caller
    handling the full bundle (used before the first bar arrives)."""
    registry = EntryPointBundleRegistry(discover=_fake_discover)

    contract = registry.load_contract(_WHEEL)

    assert isinstance(contract, DataContract)
    assert contract.instrument_ids == (_INSTRUMENT_ID,)
    assert contract.lookback_bars == 1


def _not_a_bundle() -> str:
    """A factory that returns the wrong type — exercises the fail-closed guard."""
    return "not a bundle"
