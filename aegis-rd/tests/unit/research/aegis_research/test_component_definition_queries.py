"""Direct tests for the ComponentDefinition query surface and in-memory registry factory.

Covers: undeclared vs unsatisfied params, waiver via module-level param_space,
family-uniform empty results, and the factory's snapshot/fingerprint invariants.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from research.aegis_research.component_registry.contracts import (
    ComponentDefinition,
    ComponentRegistryError,
    ComponentSelection,
    ComponentSourceIdentity,
    IndicatorManifest,
    StrategyManifest,
)
from tests.support.research.aegis_research.factories import make_component_registry

# ── helpers ──────────────────────────────────────────────────────────────────


def _identity(source_hash: str = "abc123") -> ComponentSourceIdentity:
    return ComponentSourceIdentity(
        repo_relative_path="tests/fixtures/component.py",
        source_hash=source_hash,
    )


def _indicator(
    *,
    id: str = "demo.indicator",
    input_names: tuple[str, ...] = ("Close", "Volume"),
    param_names: tuple[str, ...] = ("window", "smooth"),
    output_names: tuple[str, ...] = ("value", "signal"),
    defaults: dict[str, object] | None = None,
    has_param_space: bool = False,
    has_lookback: bool = False,
    file_path: Path | None = None,
    source_hash: str = "abc123",
) -> ComponentDefinition:
    manifest = IndicatorManifest(
        family="indicators",
        id=id,
        version="1.0.0",
        input_names=input_names,
        param_names=param_names,
        output_names=output_names,
        defaults=defaults or {},
    )
    return ComponentDefinition(
        _manifest=manifest,
        _file_path=file_path or Path(f"/fixtures/{id}.py"),
        identity=_identity(source_hash),
        _has_param_space=has_param_space,
        has_lookback=has_lookback,
    )


def _strategy(
    *,
    id: str = "demo.strategy",
    input_names: tuple[str, ...] = ("Close",),
    param_names: tuple[str, ...] = (),
    output_name: str = "active",
    consumes_outputs: tuple[str, ...] = ("value",),
    defaults: dict[str, object] | None = None,
    has_param_space: bool = False,
) -> ComponentDefinition:
    manifest = StrategyManifest(
        family="strategies",
        id=id,
        version="1.0.0",
        input_names=input_names,
        param_names=param_names,
        output_name=output_name,
        consumes_outputs=consumes_outputs,
        defaults=defaults or {},
    )
    return ComponentDefinition(
        _manifest=manifest,
        _file_path=Path(f"/fixtures/{id}.py"),
        identity=_identity(),
        _has_param_space=has_param_space,
    )


# ── undeclared_params ────────────────────────────────────────────────────────


def test_declared_param_names_preserves_manifest_order() -> None:
    definition = _indicator(param_names=("smooth", "window"))

    declared = definition.declared_param_names()

    assert declared == ("smooth", "window")


def test_default_params_returns_declared_defaults() -> None:
    definition = _indicator(defaults={"window": 20, "smooth": 0.5})

    defaults = definition.default_params()

    assert defaults == {"window": 20, "smooth": 0.5}


def test_version_returns_manifest_version() -> None:
    definition = _indicator()

    version = definition.version

    assert version == "1.0.0"


def test_allocation_output_name_returns_strategy_channel() -> None:
    definition = _strategy(output_name="target_weights")

    output_name = definition.allocation_output_name()

    assert output_name == "target_weights"


def test_allocation_output_name_rejects_indicator_with_component_name() -> None:
    definition = _indicator(id="demo.signal")

    with pytest.raises(
        ComponentRegistryError,
        match=r"component indicators/demo\.signal does not declare a strategy allocation output",
    ):
        definition.allocation_output_name()


def test_load_param_space_returns_none_when_entrypoint_is_absent() -> None:
    definition = _indicator(has_param_space=False)

    param_space = definition.load_param_space()

    assert param_space is None


def test_load_param_space_returns_declared_entrypoint(tmp_path: Path) -> None:
    component_path = tmp_path / "component.py"
    component_path.write_text(
        "def param_space():\n    return {'window': 20}\n",
        encoding="utf-8",
    )
    definition = _indicator(has_param_space=True, file_path=component_path)

    param_space = definition.load_param_space()

    assert param_space is not None
    assert param_space() == {"window": 20}


def test_intent_loaders_distinguish_full_source_hashes_with_a_shared_prefix(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.py"
    first_path.write_text("def run():\n    return 'first'\n", encoding="utf-8")
    second_path = tmp_path / "second.py"
    second_path.write_text("def run():\n    return 'second'\n", encoding="utf-8")
    first = _indicator(
        id="demo.shared_prefix",
        file_path=first_path,
        source_hash="abcdef123456" + "1" * 52,
    )
    second = _indicator(
        id="demo.shared_prefix",
        file_path=second_path,
        source_hash="abcdef123456" + "2" * 52,
    )

    first_result = first.load_callable()()
    second_result = second.load_callable()()

    assert first_result == "first"
    assert second_result == "second"


def test_source_text_returns_verbatim_component_source(tmp_path: Path) -> None:
    component_path = tmp_path / "component.py"
    source = "# component source\nVALUE = 'verbatim'\n"
    component_path.write_text(source, encoding="utf-8")
    definition = _indicator(file_path=component_path)

    loaded_source = definition.source_text()

    assert loaded_source == source


def test_warmup_bars_calls_lookback_with_resolved_params(tmp_path: Path) -> None:
    component_path = tmp_path / "component.py"
    component_path.write_text(
        "def lookback(window):\n    return window + 2\n",
        encoding="utf-8",
    )
    definition = _indicator(
        id="demo.lookback",
        file_path=component_path,
        has_lookback=True,
    )

    warmup_bars = definition.warmup_bars({"window": 5})

    assert warmup_bars == 7


def test_warmup_bars_rejects_non_integer_result_with_component_name(tmp_path: Path) -> None:
    component_path = tmp_path / "component.py"
    component_path.write_text(
        "def lookback():\n    return '3'\n",
        encoding="utf-8",
    )
    definition = _indicator(
        id="demo.bad_type",
        file_path=component_path,
        has_lookback=True,
    )

    with pytest.raises(
        ComponentRegistryError,
        match=r"component indicators/demo\.bad_type lookback\(\) must return a non-negative int",
    ):
        definition.warmup_bars({})


def test_warmup_bars_rejects_negative_result_with_component_name(tmp_path: Path) -> None:
    component_path = tmp_path / "component.py"
    component_path.write_text(
        "def lookback():\n    return -1\n",
        encoding="utf-8",
    )
    definition = _indicator(
        id="demo.negative",
        file_path=component_path,
        has_lookback=True,
    )

    with pytest.raises(
        ComponentRegistryError,
        match=r"component indicators/demo\.negative lookback\(\) must return a non-negative int",
    ):
        definition.warmup_bars({})


def test_warmup_bars_rejects_missing_entrypoint_with_component_name() -> None:
    definition = _indicator(id="demo.missing_lookback", has_lookback=False)

    with pytest.raises(
        ComponentRegistryError,
        match=r"component indicators/demo\.missing_lookback has no lookback entrypoint",
    ):
        definition.warmup_bars({})


def test_component_definition_public_surface_is_queries_and_intent_loaders() -> None:
    field_names = _component_definition_field_names()
    public_members = _component_definition_public_members()

    assert field_names == {
        "_manifest",
        "_file_path",
        "identity",
        "_has_param_space",
        "has_lookback",
    }
    assert public_members == {
        "allocation_output_name",
        "consumed_output_names",
        "declared_param_names",
        "default_params",
        "family",
        "has_lookback",
        "id",
        "input_names",
        "load_callable",
        "load_param_space",
        "produced_output_names",
        "public_snapshot",
        "source_text",
        "undeclared_params",
        "unsatisfied_params",
        "version",
        "warmup_bars",
    }


def _component_definition_field_names() -> set[str]:
    return {field.name for field in fields(ComponentDefinition)}


def _component_definition_public_members() -> set[str]:
    return {
        name for name in dir(ComponentDefinition) if not name.startswith("_")
    }


def test_undeclared_params_empty_when_all_provided_are_declared() -> None:
    definition = _indicator(param_names=("window", "smooth"))
    assert definition.undeclared_params(frozenset({"window"})) == frozenset()


def test_undeclared_params_returns_extra_provided_names() -> None:
    definition = _indicator(param_names=("window", "smooth"))
    assert definition.undeclared_params(frozenset({"window", "unknown"})) == frozenset({"unknown"})


def test_undeclared_params_all_unknown_when_none_declared() -> None:
    definition = _strategy(param_names=())
    assert definition.undeclared_params(frozenset({"foo", "bar"})) == frozenset({"foo", "bar"})


def test_undeclared_params_fully_unknown_when_provided_is_superset() -> None:
    definition = _indicator(param_names=("a",))
    assert definition.undeclared_params(frozenset({"a", "b", "c"})) == frozenset({"b", "c"})


# ── unsatisfied_params ───────────────────────────────────────────────────────


def test_unsatisfied_params_all_declared_when_nothing_provided_or_defaulted() -> None:
    definition = _indicator(param_names=("window", "smooth"))
    assert definition.unsatisfied_params(frozenset()) == frozenset({"window", "smooth"})


def test_unsatisfied_params_returns_not_provided_not_defaulted() -> None:
    definition = _indicator(
        param_names=("window", "smooth", "decay"),
        defaults={"decay": 0.95},
    )
    # smooth is declared but neither provided nor defaulted.
    assert definition.unsatisfied_params(frozenset({"window"})) == frozenset({"smooth"})


def test_unsatisfied_params_empty_when_all_provided() -> None:
    definition = _indicator(param_names=("window", "smooth"))
    assert definition.unsatisfied_params(frozenset({"window", "smooth"})) == frozenset()


def test_unsatisfied_params_empty_when_all_defaulted() -> None:
    definition = _indicator(
        param_names=("window", "smooth"),
        defaults={"window": 20, "smooth": 0.5},
    )
    assert definition.unsatisfied_params(frozenset()) == frozenset()


def test_unsatisfied_params_waived_by_param_space_function() -> None:
    definition = _indicator(
        param_names=("window", "smooth", "decay"),
        has_param_space=True,
    )
    # param_space waives all declared params regardless of provided/defaults.
    assert definition.unsatisfied_params(frozenset()) == frozenset()
    assert definition.unsatisfied_params(frozenset({"window"})) == frozenset()


def test_unsatisfied_params_strategy_with_no_params_is_always_empty() -> None:
    definition = _strategy(param_names=())
    assert definition.unsatisfied_params(frozenset()) == frozenset()
    assert definition.unsatisfied_params(frozenset({"unknown"})) == frozenset()


def test_unsatisfied_params_mixed_provided_defaulted_and_missing() -> None:
    definition = _indicator(
        param_names=("a", "b", "c", "d"),
        defaults={"c": 1},
    )
    # a is provided, c is defaulted, b and d are missing.
    assert definition.unsatisfied_params(frozenset({"a"})) == frozenset({"b", "d"})


# ── produced_output_names ────────────────────────────────────────────────────


def test_produced_output_names_indicator_returns_output_names() -> None:
    definition = _indicator(output_names=("signal", "value"))

    output_names = definition.produced_output_names()

    assert output_names == ("signal", "value")


def test_produced_output_names_strategy_returns_empty() -> None:
    definition = _strategy()
    assert definition.produced_output_names() == ()


def test_produced_output_names_indicator_single_output() -> None:
    definition = _indicator(output_names=("returns",))
    assert definition.produced_output_names() == ("returns",)


# ── consumed_output_names ────────────────────────────────────────────────────


def test_consumed_output_names_strategy_returns_consumes_outputs() -> None:
    definition = _strategy(consumes_outputs=("returns", "value"))

    output_names = definition.consumed_output_names()

    assert output_names == ("returns", "value")


def test_consumed_output_names_indicator_returns_empty() -> None:
    definition = _indicator()
    assert definition.consumed_output_names() == ()


def test_consumed_output_names_strategy_empty_consumes() -> None:
    definition = _strategy(consumes_outputs=())
    assert definition.consumed_output_names() == ()


# ── uniform dispatch: both families answer all queries without error ──────────


def test_all_queries_work_on_indicator() -> None:
    definition = _indicator(
        param_names=("window",),
        defaults={"window": 20},
        output_names=("signal",),
    )
    # No error on any query.
    assert definition.undeclared_params(frozenset({"extra"})) == frozenset({"extra"})
    assert definition.unsatisfied_params(frozenset()) == frozenset()
    assert definition.produced_output_names() == ("signal",)
    assert definition.consumed_output_names() == ()


def test_all_queries_work_on_strategy() -> None:
    definition = _strategy(
        param_names=("threshold",),
        consumes_outputs=("signal",),
    )
    assert definition.undeclared_params(frozenset({"extra"})) == frozenset({"extra"})
    assert definition.unsatisfied_params(frozenset()) == frozenset({"threshold"})
    assert definition.produced_output_names() == ()
    assert definition.consumed_output_names() == ("signal",)


# ── in-memory component-registry factory ─────────────────────────────────────


def test_factory_empty_registry_has_no_ids() -> None:
    registry = make_component_registry({})
    assert registry.ids("indicators") == ()
    assert registry.ids("strategies") == ()
    assert registry.fingerprint


def test_factory_registry_with_one_indicator_defines_id_and_snapshot() -> None:
    definition = _indicator(id="demo.signal")
    registry = make_component_registry({"indicators": {"demo.signal": definition}})
    assert registry.ids("indicators") == ("demo.signal",)
    assert registry.ids("strategies") == ()
    snapshot = registry.public_snapshot()
    assert snapshot["families"]["indicators"]["demo.signal"]["id"] == "demo.signal"
    assert snapshot["families"]["indicators"]["demo.signal"]["outputs"] == ["value", "signal"]


def test_factory_registry_with_one_strategy_defines_id_and_snapshot() -> None:
    definition = _strategy(id="demo.rotator", consumes_outputs=("returns",))
    registry = make_component_registry({"strategies": {"demo.rotator": definition}})
    assert registry.ids("indicators") == ()
    assert registry.ids("strategies") == ("demo.rotator",)
    snapshot = registry.public_snapshot()
    assert snapshot["families"]["strategies"]["demo.rotator"]["output_name"] == "active"
    assert snapshot["families"]["strategies"]["demo.rotator"]["consumes_outputs"] == ["returns"]


def test_factory_registry_with_both_families() -> None:
    ind = _indicator(id="demo.ind")
    strat = _strategy(id="demo.strat")
    registry = make_component_registry({
        "indicators": {"demo.ind": ind},
        "strategies": {"demo.strat": strat},
    })
    assert registry.ids("indicators") == ("demo.ind",)
    assert registry.ids("strategies") == ("demo.strat",)
    assert registry.get(ComponentSelection("indicators", "demo.ind")).id == "demo.ind"
    assert registry.get(ComponentSelection("strategies", "demo.strat")).id == "demo.strat"


def test_factory_fingerprint_is_deterministic() -> None:
    definition = _indicator(id="demo.signal")
    first = make_component_registry({"indicators": {"demo.signal": definition}})
    second = make_component_registry({"indicators": {"demo.signal": definition}})
    assert first.fingerprint == second.fingerprint


def test_factory_fingerprint_changes_with_different_definitions() -> None:
    a = make_component_registry({"indicators": {"demo.a": _indicator(id="demo.a")}})
    b = make_component_registry({"indicators": {"demo.b": _indicator(id="demo.b")}})
    assert a.fingerprint != b.fingerprint


def test_fingerprint_changes_when_a_default_value_changes() -> None:
    """A typed component fact moving must move the fingerprint — the snapshot
    and the fingerprint share one projection, so neither can miss it."""
    base = make_component_registry(
        {"indicators": {"demo.signal": _indicator(id="demo.signal", defaults={"window": 20})}}
    )
    changed = make_component_registry(
        {"indicators": {"demo.signal": _indicator(id="demo.signal", defaults={"window": 21})}}
    )
    assert base.fingerprint != changed.fingerprint


def test_fingerprint_changes_with_param_space_presence() -> None:
    without = make_component_registry(
        {"indicators": {"demo.signal": _indicator(id="demo.signal", has_param_space=False)}}
    )
    with_space = make_component_registry(
        {"indicators": {"demo.signal": _indicator(id="demo.signal", has_param_space=True)}}
    )
    assert without.fingerprint != with_space.fingerprint


def test_component_registry_fingerprint_golden_bytes_pin() -> None:
    """Golden pin of the re-based component registry fingerprint (ADR-0003,
    second amendment). A byte move here is a deliberate re-baseline — refresh
    the pin and record why; do not revert to the raw-payload hash."""
    registry = make_component_registry({
        "indicators": {"demo.indicator": _indicator()},
        "strategies": {"demo.strategy": _strategy()},
    })
    assert registry.fingerprint == (
        "b2cd17f0d35ddd6ee252a66042058b6952200d47fc6608b8c4dc18d559fbd023"
    )


def test_factory_sorts_ids_within_family() -> None:
    registry = make_component_registry({
        "indicators": {
            "z.third": _indicator(id="z.third"),
            "a.first": _indicator(id="a.first"),
            "m.middle": _indicator(id="m.middle"),
        },
    })
    assert registry.ids("indicators") == ("a.first", "m.middle", "z.third")


def test_factory_definitions_are_frozen() -> None:
    definition = _indicator(id="demo.signal")
    registry = make_component_registry({"indicators": {"demo.signal": definition}})
    # The FrozenComponentRegistry is immutable.
    with pytest.raises(TypeError):
        registry.definitions["indicators"]["demo.signal"] = definition  # type: ignore[index]


def test_public_snapshot_schema_version() -> None:
    registry = make_component_registry({})
    snapshot = registry.public_snapshot()
    assert snapshot["schema_version"] == "component_registry_snapshot.v1"
    assert "fingerprint" in snapshot
    assert "families" in snapshot


def test_non_finite_default_is_normalised_to_null_in_fingerprint() -> None:
    """A NaN default param is normalised to null in the public snapshot."""
    definition = _indicator(
        id="demo.nan_default",
        defaults={"window": float("nan")},
    )
    snapshot = definition.public_snapshot()
    assert snapshot["params"]["defaults"]["window"] is None

    registry = make_component_registry(
        {"indicators": {"demo.nan_default": definition}}
    )
    # The fingerprint must still be a valid 64-char hex string.
    assert len(registry.fingerprint) == 64
    assert all(c in "0123456789abcdef" for c in registry.fingerprint)


def test_non_finite_default_is_byte_stable() -> None:
    """Fingerprint is deterministic when NaN defaults are normalised to null."""
    a = _indicator(id="demo.nan", defaults={"window": float("nan")})
    b = _indicator(id="demo.nan", defaults={"window": float("nan")})
    r1 = make_component_registry({"indicators": {"demo.nan": a}})
    r2 = make_component_registry({"indicators": {"demo.nan": b}})
    assert r1.fingerprint == r2.fingerprint
