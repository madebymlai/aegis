from __future__ import annotations

import pytest

from research.aegis_research.component_registry import (
    ComponentRegistryError,
    ComponentSelection,
    discover_component_registry,
)
from tests.support.research.aegis_research.factories import make_component_registry


def test_component_discovery_is_deterministic_and_fingerprinted(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    _write_component(
        root / "indicators" / "z_second.py",
        "indicators",
        "demo.second",
    )
    _write_component(
        root / "indicators" / "a_first.py",
        "indicators",
        "demo.first",
    )
    _write_component(
        root / "strategies" / "strategy.py",
        "strategies",
        "demo.same",
    )

    first = discover_component_registry(root=root, repo_root=tmp_path)
    second = discover_component_registry(root=root, repo_root=tmp_path)

    assert first.fingerprint == second.fingerprint
    assert first.ids("indicators") == ("demo.first", "demo.second")
    assert first.ids("strategies") == ("demo.same",)
    assert first.get(ComponentSelection("indicators", "demo.first")).identity.source_hash
    assert first.get(
        ComponentSelection("indicators", "demo.first")
    ).identity.repo_relative_path == ("research/components/indicators/a_first.py")


def test_factory_built_registry_fingerprint_equals_discovery_built(tmp_path) -> None:
    """The public freeze seam — not a hand-copied recipe — is what keeps a
    factory-built registry byte-identical to a file-discovered one."""
    root = tmp_path / "research" / "components"
    _write_component(root / "indicators" / "indicator.py", "indicators", "demo.indicator")
    _write_component(root / "strategies" / "strategy.py", "strategies", "demo.strategy")

    discovered = discover_component_registry(root=root, repo_root=tmp_path)
    factory_built = make_component_registry(discovered.definitions)

    assert factory_built.fingerprint == discovered.fingerprint
    assert factory_built.public_snapshot() == discovered.public_snapshot()


def test_component_discovery_rejects_duplicate_ids_within_family(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    _write_component(root / "indicators" / "one.py", "indicators", "duplicate")
    _write_component(root / "indicators" / "two.py", "indicators", "duplicate")

    with pytest.raises(ComponentRegistryError, match="duplicate component id"):
        discover_component_registry(root=root, repo_root=tmp_path)


def test_component_discovery_ignores_archive_directories_at_any_depth(tmp_path) -> None:
    """Anything beneath an ``archive/`` directory (any depth) is provenance, not a
    live component: discovery skips it so it never registers, collides, or runs."""
    root = tmp_path / "research" / "components"
    _write_component(root / "indicators" / "active.py", "indicators", "demo.active")
    # Archived directly under the family root...
    _write_component(root / "indicators" / "archive" / "retired.py", "indicators", "demo.retired")
    # ...and archived nested under a component subpackage (deeper than one level).
    _write_component(
        root / "strategies" / "family" / "archive" / "old.py", "strategies", "demo.old"
    )
    _write_component(root / "strategies" / "live.py", "strategies", "demo.live")

    registry = discover_component_registry(root=root, repo_root=tmp_path)

    assert registry.ids("indicators") == ("demo.active",)
    assert registry.ids("strategies") == ("demo.live",)


def test_archived_component_does_not_collide_with_active_same_id(tmp_path) -> None:
    """An archived predecessor sharing an id with its active replacement must not
    trip the duplicate-id guard — the archive is invisible to discovery."""
    root = tmp_path / "research" / "components"
    _write_component(root / "indicators" / "current.py", "indicators", "demo.signal")
    _write_component(
        root / "indicators" / "archive" / "previous.py", "indicators", "demo.signal"
    )

    registry = discover_component_registry(root=root, repo_root=tmp_path)

    assert registry.ids("indicators") == ("demo.signal",)


def test_component_discovery_rejects_non_literal_metadata(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    path = root / "indicators" / "computed.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "# %% component overview\n"
        "# Fixture used to verify static manifest parsing rejects non-literals.\n"
        "# Source: in-memory pytest component file.\n"
        "\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {'family': 'indicators', 'id': f'bad', 'version': '1'}\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Return the indicator output."""\n'
        "    pass\n"
    )

    with pytest.raises(ComponentRegistryError, match="literal"):
        discover_component_registry(root=root, repo_root=tmp_path)


def test_component_discovery_rejects_bare_percent_cells(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    path = root / "indicators" / "bare_cell.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "# %%\n"
        f"COMPONENT_MANIFEST = {_manifest_for('indicators', 'bare.cell')!r}\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Return the indicator output."""\n'
        "    pass\n"
    )

    with pytest.raises(ComponentRegistryError, match="include a purpose"):
        discover_component_registry(root=root, repo_root=tmp_path)


def test_component_discovery_requires_main_compute_cell(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    path = root / "indicators" / "no_main.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "# %% component overview\n"
        "# Fixture without a main compute cell.\n"
        "# Source: in-memory pytest component file.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {_manifest_for('indicators', 'no.main')!r}\n"
        "def run():\n"
        '    """Return the indicator output."""\n'
        "    pass\n"
    )

    with pytest.raises(ComponentRegistryError, match="# %% main cell"):
        discover_component_registry(root=root, repo_root=tmp_path)


def test_component_discovery_requires_run_entrypoint(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    path = root / "indicators" / "missing_run.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "# %% component overview\n"
        "# Fixture without the fixed run entrypoint.\n"
        "# Source: in-memory pytest component file.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {_manifest_for('indicators', 'missing.run')!r}\n"
        "\n# %% main compute\n"
        "def run_wide():\n"
        '    """Legacy entrypoint name."""\n'
        "    pass\n"
    )

    with pytest.raises(ComponentRegistryError) as excinfo:
        discover_component_registry(root=root, repo_root=tmp_path)
    message = str(excinfo.value)
    assert str(path) in message
    assert "missing required component entry point 'run'" in message


def test_component_discovery_requires_callable_docstring(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    path = root / "indicators" / "missing_docstring.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "# %% component overview\n"
        "# Fixture without a callable docstring.\n"
        "# Source: in-memory pytest component file.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {_manifest_for('indicators', 'missing.docstring')!r}\n"
        "\n# %% main compute\n"
        "def run():\n"
        "    pass\n"
    )

    with pytest.raises(ComponentRegistryError, match="must have a docstring"):
        discover_component_registry(root=root, repo_root=tmp_path)


def test_component_discovery_does_not_execute_top_level_code(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    side_effect = tmp_path / "side-effect.txt"
    path = root / "indicators" / "side_effect.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "# %% component overview\n"
        "# Fixture used to verify registry discovery avoids top-level execution.\n"
        "# Source: in-memory pytest component file.\n"
        "\n"
        "# %% define component metadata\n"
        "from pathlib import Path\n"
        f"Path({str(side_effect)!r}).write_text('executed')\n"
        "COMPONENT_MANIFEST = {\n"
        "    'family': 'indicators',\n"
        "    'id': 'safe.static',\n"
        "    'version': '1.0.0',\n"
        "    'input_names': ['Close'],\n"
        "    'param_names': ['window'],\n"
        "    'output_names': ['value'],\n"
        "}\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Return the indicator output."""\n'
        "    pass\n"
    )

    registry = discover_component_registry(root=root, repo_root=tmp_path)

    assert registry.ids("indicators") == ("safe.static",)
    assert not side_effect.exists()


def test_component_discovery_rejects_symlink_escape(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    outside = tmp_path / "outside.py"
    _write_component(outside, "indicators", "outside")
    link = root / "indicators" / "outside.py"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)

    with pytest.raises(ComponentRegistryError, match="outside approved root"):
        discover_component_registry(root=root, repo_root=tmp_path)


def test_component_discovery_rejects_dangling_symlink_with_registry_error(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    link = root / "indicators" / "missing.py"
    link.parent.mkdir(parents=True)
    link.symlink_to(tmp_path / "missing.py")

    with pytest.raises(ComponentRegistryError, match="symlink target does not exist"):
        discover_component_registry(root=root, repo_root=tmp_path)


def test_component_callable_loads_only_after_selection(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    path = root / "indicators" / "loadable.py"
    _write_component(path, "indicators", "loadable")

    registry = discover_component_registry(root=root, repo_root=tmp_path)
    definition = registry.get(ComponentSelection("indicators", "loadable"))

    assert definition.load_callable()() == "loadable"


def test_component_manifest_exposes_input_names_for_supported_families(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    _write_component(root / "indicators" / "indicator.py", "indicators", "demo.indicator")
    _write_component(root / "strategies" / "strategy.py", "strategies", "demo.strategy")

    registry = discover_component_registry(root=root, repo_root=tmp_path)

    assert registry.get(ComponentSelection("indicators", "demo.indicator")).input_names == (
        "Close",
    )
    assert registry.get(ComponentSelection("strategies", "demo.strategy")).input_names == ("Close",)


def test_component_manifest_exposes_param_space_defaults_and_consumed_outputs(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    _write_component(root / "indicators" / "indicator.py", "indicators", "demo.indicator")
    _write_component(root / "strategies" / "strategy.py", "strategies", "demo.strategy")
    indicator_path = root / "indicators" / "indicator.py"
    strategy_path = root / "strategies" / "strategy.py"
    indicator_path.write_text(
        indicator_path.read_text()
        .replace(
            "'output_names': ['value']",
            "'output_names': ['value'], 'defaults': {'window': 20}",
        )
        .replace(
            "\n# %% main compute\n",
            "\n# %% parameter space\ndef param_space():\n"
            "    return {'window': object()}\n\n# %% main compute\n",
        )
    )
    strategy_path.write_text(
        strategy_path.read_text()
        .replace(
            "'output_name': 'active'",
            "'param_names': ['threshold'], 'output_name': 'active', "
            "'consumes_outputs': ['value'], 'defaults': {'threshold': 0.0}",
        )
        .replace(
            "\n# %% main compute\n",
            "\n# %% parameter space\ndef param_space():\n"
            "    return {'threshold': object()}\n\n# %% main compute\n",
        )
    )

    registry = discover_component_registry(root=root, repo_root=tmp_path)
    indicator_def = registry.get(ComponentSelection("indicators", "demo.indicator"))
    strategy_def = registry.get(ComponentSelection("strategies", "demo.strategy"))
    indicator = indicator_def._manifest
    strategy = strategy_def._manifest

    assert indicator.defaults == {"window": 20}
    assert indicator_def._has_param_space is True
    assert strategy.param_names == ("threshold",)
    assert strategy.output_name == "active"
    assert strategy.consumes_outputs == ("value",)
    assert strategy.defaults == {"threshold": 0.0}
    assert strategy_def._has_param_space is True


def test_component_manifest_rejects_defaults_outside_param_names(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    _write_component(root / "indicators" / "indicator.py", "indicators", "demo.bad")
    path = root / "indicators" / "indicator.py"
    path.write_text(
        path.read_text().replace(
            "'output_names': ['value']",
            "'output_names': ['value'], 'defaults': {'unknown': 20}",
        )
    )

    with pytest.raises(ComponentRegistryError, match="defaults keys"):
        discover_component_registry(root=root, repo_root=tmp_path)


def test_component_manifest_rejects_duplicate_output_names(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    _write_component(root / "indicators" / "indicator.py", "indicators", "demo.bad")
    path = root / "indicators" / "indicator.py"
    path.write_text(
        path.read_text().replace(
            "'output_names': ['value']",
            "'output_names': ['value', 'value']",
        )
    )

    with pytest.raises(ComponentRegistryError, match="output_names must be unique"):
        discover_component_registry(root=root, repo_root=tmp_path)


def test_component_manifest_rejects_malformed_input_names(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    _write_component(root / "indicators" / "indicator.py", "indicators", "demo.bad")
    path = root / "indicators" / "indicator.py"
    path.write_text(path.read_text().replace("'Close'", "'Close '"))

    with pytest.raises(ComponentRegistryError, match="without surrounding whitespace"):
        discover_component_registry(root=root, repo_root=tmp_path)


def test_component_callable_module_is_registered_while_loading(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    path = root / "indicators" / "registered.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Fixture used to verify component modules are registered during import.\n"
        "# Source: in-memory pytest component file.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {_manifest_for('indicators', 'registered')!r}\n"
        "import sys\n"
        "MODULE_REGISTERED = __name__ in sys.modules\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Report whether the module is registered while loading."""\n'
        "    return MODULE_REGISTERED\n"
    )

    registry = discover_component_registry(root=root, repo_root=tmp_path)
    definition = registry.get(ComponentSelection("indicators", "registered"))

    assert definition.load_callable()() is True


@pytest.mark.parametrize("output_name", ["active", "scores", "ranks", "target_weights"])
def test_strategy_manifest_registers_all_allocation_native_shapes(tmp_path, output_name) -> None:
    root = tmp_path / "research" / "components"
    _write_strategy_component(
        root / "strategies" / "strategy.py",
        component_id=f"demo.{output_name}",
        output_name=output_name,
    )

    registry = discover_component_registry(root=root, repo_root=tmp_path)
    definition = registry.get(ComponentSelection("strategies", f"demo.{output_name}"))

    assert definition._manifest.output_name == output_name
    snapshot = registry.public_snapshot()
    strategy_snapshot = snapshot["families"]["strategies"][f"demo.{output_name}"]
    assert strategy_snapshot["output_name"] == output_name
    assert "signal_outputs" not in strategy_snapshot


@pytest.mark.parametrize("legacy_output", ["entries", "exits"])
def test_strategy_manifest_rejects_legacy_signal_output_names(tmp_path, legacy_output) -> None:
    root = tmp_path / "research" / "components"
    _write_strategy_component(
        root / "strategies" / "strategy.py",
        component_id="demo.legacy",
        output_name=legacy_output,
    )

    with pytest.raises(ComponentRegistryError) as excinfo:
        discover_component_registry(root=root, repo_root=tmp_path)
    message = str(excinfo.value)
    assert "unsupported allocation output" in message
    assert "active" in message and "scores" in message
    assert "ranks" in message and "target_weights" in message


def test_strategy_manifest_rejects_unknown_output_name(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    _write_strategy_component(
        root / "strategies" / "strategy.py",
        component_id="demo.unknown",
        output_name="momentum",
    )

    with pytest.raises(ComponentRegistryError) as excinfo:
        discover_component_registry(root=root, repo_root=tmp_path)
    message = str(excinfo.value)
    assert "unsupported allocation output" in message
    assert "'momentum'" in message
    assert "target_weights" in message


def test_strategy_manifest_rejects_legacy_signal_outputs_field(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    path = root / "strategies" / "strategy.py"
    path.parent.mkdir(parents=True)
    manifest = {
        "family": "strategies",
        "id": "demo.legacy_field",
        "version": "1.0.0",
        "input_names": ["Close"],
        "signal_outputs": ["entries", "exits"],
        "owns_portfolio": False,
    }
    path.write_text(
        "# %% component overview\n"
        "# Fixture used to verify legacy signal_outputs field is rejected.\n"
        "# Source: in-memory pytest component file.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {manifest!r}\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Return a fixture value."""\n'
        "    return 'legacy'\n"
    )

    with pytest.raises(ComponentRegistryError) as excinfo:
        discover_component_registry(root=root, repo_root=tmp_path)
    message = str(excinfo.value)
    assert "Extra inputs are not permitted" in message
    assert "signal_outputs" in message


def test_strategy_manifest_rejects_forbidden_gross_cap_key(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    path = root / "strategies" / "strategy.py"
    path.parent.mkdir(parents=True)
    manifest = {
        "family": "strategies",
        "id": "demo.forbidden",
        "version": "1.0.0",
        "input_names": ["Close"],
        "output_name": "active",
        "gross_cap": 0.5,
        "owns_portfolio": False,
    }
    path.write_text(
        "# %% component overview\n"
        "# Fixture used to verify components cannot own portfolio-cap config.\n"
        "# Source: in-memory pytest component file.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {manifest!r}\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Return a fixture value."""\n'
        "    return 'forbidden'\n"
    )

    with pytest.raises(ComponentRegistryError) as excinfo:
        discover_component_registry(root=root, repo_root=tmp_path)
    message = str(excinfo.value)
    assert "Extra inputs are not permitted" in message
    assert "gross_cap" in message


def test_manifest_payload_errors_accumulate_per_file(tmp_path) -> None:
    """Multiple pydantic field-level errors for one manifest surface together.

    When field-level errors are present, pydantic accumulates all of them before
    raising.  Model-validator errors (e.g. ``output_names must not be empty``)
    fire only when every field passes its individual type check, so they are
    tested separately.
    """
    root = tmp_path / "research" / "components"
    path = root / "indicators" / "broken.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "family": "indicators",
        "id": "bad id",
        "version": "",
        "input_names": ["Close", "  bad  "],
        "param_names": [""],
        "output_names": ["ma"],
        "unknown_field": "surprise",
    }
    path.write_text(
        "# %% component overview\n"
        "# Fixture with multiple payload errors.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {manifest!r}\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Return fixture value."""\n'
        "    return 'broken'\n"
    )

    with pytest.raises(ComponentRegistryError) as excinfo:
        discover_component_registry(root=root, repo_root=tmp_path)
    message = str(excinfo.value)
    # pydantic-worded errors, multiple errors accumulated in one message
    assert "String should match pattern" in message
    assert "String should have at least 1 character" in message
    assert "must be a VBT feature name without surrounding whitespace" in message
    assert "Extra inputs are not permitted" in message
    # All errors for one file in one message (separated by "; ")
    assert message.count("; ") >= 3


def _write_strategy_component(path, *, component_id: str, output_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "family": "strategies",
        "id": component_id,
        "version": "1.0.0",
        "input_names": ["Close"],
        "output_name": output_name,
        "owns_portfolio": False,
    }
    path.write_text(
        "# %% component overview\n"
        "# Allocation-native strategy fixture component.\n"
        "# Source: in-memory pytest component file.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {manifest!r}\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Return a deterministic fixture value."""\n'
        f"    return {component_id!r}\n"
    )


def _write_component(path, family: str, component_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = _manifest_for(family, component_id)
    path.write_text(
        "# %% component overview\n"
        "# Generic registry fixture component.\n"
        "# Source: in-memory pytest component file.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {manifest!r}\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Return a deterministic fixture value."""\n'
        f"    return {component_id!r}\n"
    )


def _manifest_for(family: str, component_id: str) -> dict[str, object]:
    base = {"family": family, "id": component_id, "version": "1.0.0"}
    if family == "indicators":
        return {
            **base,
            "input_names": ["Close"],
            "param_names": ["window"],
            "output_names": ["value"],
        }
    if family == "strategies":
        return {
            **base,
            "input_names": ["Close"],
            "output_name": "active",
            "owns_portfolio": False,
        }
    raise AssertionError(f"unknown family {family}")


# Pre-v2 component files declared the callable entry points through manifest keys
# (wide_callable / param_space_callable) or a module-level COMPONENT_CALLABLE
# assignment. ADR-0017 deletes that plumbing forward-first: the v2 contract is the
# manifest dict plus a module-level `run`, so these keys are no longer special-cased.
# A manifest carrying one is just an unknown field rejected by the schema gate, and a
# stray module-level assignment is inert.
@pytest.mark.parametrize("family", ["indicators", "strategies"])
@pytest.mark.parametrize("plumbing_key", ["wide_callable", "param_space_callable"])
def test_manifest_rejects_unknown_callable_plumbing_key(
    tmp_path, family, plumbing_key
) -> None:
    root = tmp_path / "research" / "components"
    manifest = _manifest_for(family, "demo.unknown_key")
    manifest[plumbing_key] = "custom"
    path = root / family / "unknown_key.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Fixture carrying a manifest callable-plumbing key from the pre-v2 contract.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {manifest!r}\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Return fixture value."""\n'
        "    return 'value'\n"
    )

    with pytest.raises(ComponentRegistryError) as excinfo:
        discover_component_registry(root=root, repo_root=tmp_path)
    message = str(excinfo.value)
    assert plumbing_key in message
    assert "Extra inputs are not permitted" in message


def test_component_with_lookback_entrypoint_has_lookback_true(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    path = root / "indicators" / "with_lookback.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Fixture with a lookback() entrypoint.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {_manifest_for('indicators', 'demo.with_lookback')!r}\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Return fixture value."""\n'
        "    return 'value'\n"
        "\n"
        "def lookback(**params):\n"
        '    """Return warmup bars for this component."""\n'
        "    return 42\n"
    )

    registry = discover_component_registry(root=root, repo_root=tmp_path)
    definition = registry.get(ComponentSelection("indicators", "demo.with_lookback"))
    assert definition.has_lookback is True
    assert definition.warmup_bars({"window": 10}) == 42


def test_component_without_lookback_entrypoint_has_lookback_false(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    _write_component(root / "indicators" / "no_lookback.py", "indicators", "demo.no_lookback")

    registry = discover_component_registry(root=root, repo_root=tmp_path)
    definition = registry.get(ComponentSelection("indicators", "demo.no_lookback"))
    assert definition.has_lookback is False


def test_stray_module_level_callable_assignment_is_inert(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    path = root / "indicators" / "stray_assignment.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Fixture with a stray module-level callable-name assignment.\n"
        "\n"
        "# %% define component metadata\n"
        f"COMPONENT_MANIFEST = {_manifest_for('indicators', 'demo.stray_assignment')!r}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run():\n"
        '    """Return fixture value."""\n'
        "    return 'value'\n"
    )

    registry = discover_component_registry(root=root, repo_root=tmp_path)
    assert registry.get(
        ComponentSelection("indicators", "demo.stray_assignment")
    ).identity.source_hash
