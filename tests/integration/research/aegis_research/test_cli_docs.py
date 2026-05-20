from __future__ import annotations

from pathlib import Path


def test_active_cli_docs_use_aerd_contract() -> None:
    docs = Path("docs/vectorbt-scaffold.md").read_text()

    assert "aerd run <config>" in docs
    assert "aerd run --train <config>" in docs
    assert "aerd play" not in docs
    assert "aerd exp" not in docs
    assert "Both run modes require explicit config paths" in docs
    assert "rejected` or `needs_more_evidence` report still exits `0`" in docs
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


def test_model_plugin_docs_keep_yaml_inert_and_aerd_registry_explicit() -> None:
    docs = Path("docs/model-plugins.md").read_text()

    assert "Run YAML selects a stable train-mode model ref; it never imports Python code" in docs
    assert "aerd run --train" in docs
    assert (
        "Default `aerd run` is reserved for playbook-backed sweeps or fixed component-backed strategy/research evidence"
        in docs
    )


def test_component_and_playbook_docs_keep_yaml_inert_and_source_refs_explicit() -> None:
    docs = "\n".join(
        [
            Path("docs/components.md").read_text(),
            Path("docs/playbooks.md").read_text(),
            Path("docs/vectorbt-scaffold.md").read_text(),
        ]
    )

    assert "source: component" in docs
    assert "source: playbook" in docs
    assert "ids: all" in docs
    assert "YAML never imports Python" in docs
    assert "arbitrary notebook paths" in docs
    assert "last-run refs" in docs
    assert "one indicator idea/family" in docs
    assert "exactly one component indicator ID" in docs


def test_active_docs_describe_component_only_labeler_contract() -> None:
    docs = "\n".join(
        [
            Path("README.md").read_text(),
            Path("docs/components.md").read_text(),
            Path("docs/playbooks.md").read_text(),
            Path("docs/vectorbt-scaffold.md").read_text(),
        ]
    )

    assert "labeler:" in docs
    assert "labeler: {id: ...}" in docs
    assert "`labeler` and top-level `strategy` are mutually exclusive" in docs
    assert "Labels are not a playbook family" in docs
    assert "train.label" not in docs
    assert "research/playbooks/{labels,indicators,strategies}/" not in docs


def test_docs_examples_use_top_level_labeler_contract() -> None:
    examples = "\n".join(path.read_text() for path in Path("docs/examples").rglob("*.ipynb"))

    assert "'labeler': {'id': 'example.fixlb'}" in examples
    assert "train.label" not in examples
    assert "'label': {'source': 'component'" not in examples


def test_docs_describe_composed_strategy_candidates_and_manual_promotion() -> None:
    docs = "\n".join(
        [
            Path("README.md").read_text(),
            Path("docs/components.md").read_text(),
            Path("docs/playbooks.md").read_text(),
            Path("docs/vectorbt-scaffold.md").read_text(),
        ]
    )

    assert "complete composed strategy candidates" in docs
    assert "Indicator playbook candidates become rankable only when a strategy playbook consumes" in docs
    assert "playbook_sweep_result.v1" in docs
    assert "candidate_grid.batch_size" in docs
    assert "chunks" in docs
    assert "metric_source" in docs
    assert "manual promotion" in docs
    assert "best indicator" not in docs


def test_component_and_playbook_placeholders_point_to_examples() -> None:
    paths = [
        "research/components/labels/README.md",
        "research/components/indicators/README.md",
        "research/components/strategies/README.md",
        "research/playbooks/indicators/README.md",
        "research/playbooks/strategies/README.md",
    ]

    for path in paths:
        readme = Path(path).read_text()
        assert "docs/examples/" in readme
        assert "ignored by git" in readme
        assert "not secret management" in readme

    assert not Path("research/playbooks/labels/README.md").exists()
