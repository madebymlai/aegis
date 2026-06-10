from __future__ import annotations

from pathlib import Path


def test_active_cli_docs_use_aerd_contract() -> None:
    docs = Path("docs/vectorbt-scaffold.md").read_text()

    assert "aerd run <config>" in docs
    assert "aerd run --train" not in docs
    assert "aerd play" not in docs
    assert "aerd exp" not in docs
    assert "Both run configs require explicit config paths" in docs
    assert "| `execution_failure` | 10 |" in docs
    assert "aegis-research run" not in docs
    assert "python -m research.aegis_research.cli" not in docs


def test_active_docs_use_vbt_data_arrays_not_feature_map() -> None:
    docs = "\n".join(
        [
            Path("README.md").read_text(),
            Path("docs/components.md").read_text(),
            Path("docs/playbooks.md").read_text(),
            Path("docs/vectorbt-scaffold.md").read_text(),
        ]
    )

    assert "data.arrays" in docs
    assert "arrays: [OHLCV" in docs
    assert "Data.features" in docs
    assert "DATA_ARRAY_SHORTCUTS" in docs
    assert "data.feature_map" not in docs


def test_model_plugin_docs_are_removed_from_active_surface() -> None:
    assert not Path("docs/model-plugins.md").exists()
    assert not Path("docs/examples/model_plugins").exists()


def test_component_docs_keep_yaml_inert_and_component_refs_direct() -> None:
    docs = "\n".join(
        [
            Path("docs/components.md").read_text(),
            Path("docs/playbooks.md").read_text(),
            Path("docs/vectorbt-scaffold.md").read_text(),
        ]
    )

    assert "strategy:\n  id:" in docs
    assert "indicators:\n  - id:" in docs
    assert "strategy.source" in docs
    assert "indicator `ids`" in docs
    assert "YAML never imports Python" in docs
    assert "arbitrary notebook paths" in docs
    assert "last-run refs" in docs
    assert "one indicator entry per component id" in docs
    assert "no longer a supported `aerd run` authoring surface" in docs

    # Docs now point at the schema guides for authoring contracts
    components_doc = Path("docs/components.md").read_text()
    assert "`aerd show indicator-schema`" in components_doc
    assert "`aerd show strategy-schema`" in components_doc
    assert "`aerd show components`" in components_doc


def test_active_docs_remove_labeler_contract() -> None:
    docs = "\n".join(
        [
            Path("README.md").read_text(),
            Path("docs/components.md").read_text(),
            Path("docs/playbooks.md").read_text(),
            Path("docs/vectorbt-scaffold.md").read_text(),
        ]
    )

    assert "labeler:" not in docs
    assert "labeler: {id: ...}" not in docs
    assert "top-level `labeler`" not in docs
    assert "train.label" not in docs
    assert "research/playbooks/{labels,indicators,strategies}/" not in docs


def test_docs_examples_remove_train_notebooks() -> None:
    examples = "\n".join(
        path.read_text() for path in Path("docs/examples").rglob("*") if path.is_file()
    )

    assert "labeler" not in examples
    assert "train.label" not in examples
    assert "model_plugin" not in examples
    assert not Path("docs/examples/scaffold_experiment_walkthrough.ipynb").exists()


def test_docs_describe_composed_strategy_candidates_and_manual_lock() -> None:
    docs = "\n".join(
        [
            Path("README.md").read_text(),
            Path("docs/components.md").read_text(),
            Path("docs/playbooks.md").read_text(),
            Path("docs/vectorbt-scaffold.md").read_text(),
        ]
    )

    assert "complete composed strategy candidates" in docs
    assert "Component locks use persisted candidate rows" in docs
    assert "candidate_grid.batch_size" not in docs
    assert "unknown to the forward schema" in docs
    assert "lock_id" in docs
    assert "candidate_id" in docs
    assert "best indicator" not in docs

    # Docs point at schema guides, not duplicate contract facts
    components_doc = Path("docs/components.md").read_text()
    assert "`aerd show indicator-schema`" in components_doc
    assert "`aerd show strategy-schema`" in components_doc


def test_component_placeholders_point_to_examples() -> None:
    paths = [
        "research/components/indicators/README.md",
        "research/components/strategies/README.md",
    ]

    for path in paths:
        readme = Path(path).read_text()
        assert "component_registry/indicator_example.py" in readme or \
               "component_registry/strategy_example.py" in readme
        assert "ignored by git" in readme
        assert "not secret management" in readme

    assert not Path("research/playbooks/labels/README.md").exists()
    assert not Path("research/playbooks/indicators/README.md").exists()
    assert not Path("research/playbooks/strategies/README.md").exists()


def test_configs_readme_points_at_config_schema() -> None:
    """The configs README has no field tables or contract enumerations —
    only pointers at aerd show config-schema plus directory-level concerns."""
    readme = Path("research/configs/README.md").read_text()

    # Points at the CLI guide
    assert "`aerd show config-schema`" in readme
    assert "`aerd show splitters" in readme
    assert "`aerd show components`" in readme

    # Directory-level concerns remain
    assert "ignored by git" in readme
    assert "layout carries no semantics" in readme
    assert "not secret management" in readme

    # No field tables or contract enumerations (these live in the guide now)
    assert "| Field |" not in readme
    assert "| `schema_version` |" not in readme
    assert "| `data.arrays` |" not in readme

    # No YAML schema snippet (the example lives in the guide now)
    assert "schema_version: 8" not in readme


def test_components_doc_points_at_guides_not_contract() -> None:
    """docs/components.md has no field tables, entry-point signatures, or
    return-shape descriptions — only pointers at the schema guides plus
    directory-level concerns."""
    doc = Path("docs/components.md").read_text()

    # Points at the CLI guides
    assert "`aerd show indicator-schema`" in doc
    assert "`aerd show strategy-schema`" in doc
    assert "`aerd show components`" in doc

    # Directory-level concerns remain
    assert "ignored by git" in doc
    assert "not secret management" in doc

    # No field tables or contract enumerations
    assert "| Field |" not in doc
    assert "| `output_names` |" not in doc
    assert "| `consumes_outputs` |" not in doc

    # No entry-point signatures or return-shape descriptions
    assert "def run(" not in doc
    assert "NaN-selection" not in doc.lower()
    assert "batch-invariance" not in doc.lower()


def test_docs_examples_are_pointers_to_packaged_examples() -> None:
    """Old docs/examples/ files point at the packaged examples."""
    indicator = Path("docs/examples/components/indicator_component_example.py").read_text()
    strategy = Path("docs/examples/components/strategy_component_example.py").read_text()

    assert "research/aegis_research/component_registry/indicator_example.py" in indicator
    assert "research/aegis_research/component_registry/strategy_example.py" in strategy

    # No actual component source (def run, COMPONENT_MANIFEST, imports)
    assert "COMPONENT_MANIFEST = {" not in indicator
    assert "def run(" not in indicator
    assert "COMPONENT_MANIFEST = {" not in strategy
    assert "def run(" not in strategy
