from __future__ import annotations

import pytest

from research.aegis_research.component_registry import (
    ComponentRegistryError,
    ComponentSelection,
    discover_component_registry,
)


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


def test_component_discovery_rejects_duplicate_ids_within_family(tmp_path) -> None:
    root = tmp_path / "research" / "components"
    _write_component(root / "indicators" / "one.py", "indicators", "duplicate")
    _write_component(root / "indicators" / "two.py", "indicators", "duplicate")

    with pytest.raises(ComponentRegistryError, match="duplicate component id"):
        discover_component_registry(root=root, repo_root=tmp_path)


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
        "COMPONENT_CALLABLE = 'run'\n"
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
        "COMPONENT_CALLABLE = 'run'\n"
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
        "COMPONENT_CALLABLE = 'run'\n"
        "def run():\n"
        '    """Return the indicator output."""\n'
        "    pass\n"
    )

    with pytest.raises(ComponentRegistryError, match="# %% main cell"):
        discover_component_registry(root=root, repo_root=tmp_path)


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
        "COMPONENT_CALLABLE = 'run'\n"
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
        "COMPONENT_CALLABLE = 'run'\n"
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
        "COMPONENT_CALLABLE = 'run'\n"
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
        "COMPONENT_CALLABLE = 'run'\n"
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
            "signal_outputs": ["entries", "exits"],
            "owns_portfolio": False,
        }
    raise AssertionError(f"unknown family {family}")
