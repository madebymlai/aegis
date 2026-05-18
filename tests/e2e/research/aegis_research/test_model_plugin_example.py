from __future__ import annotations

import json
import subprocess
from pathlib import Path

import nbformat
from nbclient import NotebookClient

OLD_SYNTHETIC_CONFIG_PATHS = (
    "/".join(("research", "configs", "experiments", "synthetic_ml_" + "baseline.yaml")),
    "/".join(
        (
            "research",
            "configs",
            "experiments",
            "synthetic_purged_fixlb_" + "baseline.yaml",
        )
    ),
)


def _notebook_source(path: str) -> tuple[dict[str, object], str]:
    notebook_path = Path(path)
    payload = json.loads(notebook_path.read_text())
    source = "\n".join("".join(cell.get("source", [])) for cell in payload.get("cells", []))
    return payload, source


def _execute_notebook(path: str) -> None:
    notebook_path = Path(path)
    notebook = nbformat.read(notebook_path, as_version=4)

    NotebookClient(
        notebook,
        timeout=300,
        kernel_name="python3",
        resources={"metadata": {"path": str(notebook_path.parent)}},
    ).execute()


def _assert_not_tracked(path: str) -> None:
    result = subprocess.run(["git", "ls-files", "--error-unmatch", path], check=False)

    assert result.returncode != 0


def test_sklearn_model_plugin_notebook_is_valid_explicit_registration_example() -> None:
    payload, source = _notebook_source("docs/examples/model_plugins/sklearn_logistic_plugin.ipynb")

    assert payload["nbformat"] == 4
    assert "ModelRegistry" in source
    assert "model_registry=registry" in source
    assert "examples.sklearn_logistic" in source
    assert "TemporaryDirectory" in source
    assert "find_repo_root" in source
    assert "run_id=" not in source
    assert "runs/example_model_plugin" not in source
    assert "model.kind" not in source
    assert "import_path" not in source
    for old_path in OLD_SYNTHETIC_CONFIG_PATHS:
        assert old_path not in source


def test_scaffold_walkthrough_notebook_is_valid_runnable_example() -> None:
    payload, source = _notebook_source("docs/examples/scaffold_experiment_walkthrough.ipynb")

    assert payload["nbformat"] == 4
    assert "SCAFFOLD_CONFIG" in source
    assert "make_default_model_registry" in source
    assert "model_registry=registry" in source
    assert "TemporaryDirectory" in source
    assert "scaffold evidence only" in source
    assert "not validated trading methodology" in source
    assert "empirical edge" in source
    assert "investment advice" in source
    assert "API keys" in source
    assert "environment-backed secret references" in source
    assert "run_id=" not in source
    assert "find_repo_root" in source
    for old_path in OLD_SYNTHETIC_CONFIG_PATHS:
        assert old_path not in source


def test_scaffold_walkthrough_notebook_executes() -> None:
    _execute_notebook("docs/examples/scaffold_experiment_walkthrough.ipynb")
    _execute_notebook("docs/examples/scaffold_experiment_walkthrough.ipynb")


def test_sklearn_model_plugin_notebook_executes() -> None:
    _execute_notebook("docs/examples/model_plugins/sklearn_logistic_plugin.ipynb")
    _execute_notebook("docs/examples/model_plugins/sklearn_logistic_plugin.ipynb")


def test_experiment_config_directory_is_generic_readme_pointer() -> None:
    readme = Path("research/configs/experiments/README.md").read_text()
    gitignore = Path(".gitignore").read_text()

    assert "docs/examples/scaffold_experiment_walkthrough.ipynb" in readme
    assert "scaffold evidence only" in readme
    assert "not validated trading methodology" in readme
    assert "empirical edge" in readme
    assert "investment advice" in readme
    assert "API keys" in readme
    assert "environment-backed secret references" in readme
    assert "git add -f" not in readme
    assert "etf_cspx_dtla_sgln_yfinance_ml" not in readme
    assert "research/configs/experiments/*" in gitignore
    assert "!research/configs/experiments/README.md" in gitignore
    for old_path in OLD_SYNTHETIC_CONFIG_PATHS:
        _assert_not_tracked(old_path)


def test_experiment_config_directory_ignore_rules_keep_only_readme_trackable() -> None:
    ignored_yaml = subprocess.run(
        [
            "git",
            "check-ignore",
            "--no-index",
            "--quiet",
            "research/configs/experiments/example.yaml",
        ],
        check=False,
    )
    ignored_readme = subprocess.run(
        [
            "git",
            "check-ignore",
            "--no-index",
            "--quiet",
            "research/configs/experiments/README.md",
        ],
        check=False,
    )
    tracked_files = subprocess.run(
        ["git", "ls-files", "research/configs/experiments"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert ignored_yaml.returncode == 0
    assert ignored_readme.returncode == 1
    assert tracked_files.stdout.splitlines() == ["research/configs/experiments/README.md"]


def test_active_docs_do_not_reference_old_synthetic_experiment_configs() -> None:
    active_docs = [
        Path("docs/vectorbt-scaffold.md"),
        Path("docs/examples/model_plugins/README.md"),
        Path("docs/examples/model_plugins/sklearn_logistic_plugin.ipynb"),
        Path("docs/examples/scaffold_experiment_walkthrough.ipynb"),
    ]

    active_source = "\n".join(path.read_text() for path in active_docs)

    for old_path in OLD_SYNTHETIC_CONFIG_PATHS:
        assert old_path not in active_source


def test_model_plugin_docs_include_pure_python_adaptation_path() -> None:
    readme = Path("docs/examples/model_plugins/README.md").read_text()
    docs = Path("docs/model-plugins.md").read_text()

    assert "pure Python" in readme
    assert "Do not put import paths" in readme
    assert "positive_class_probability" in docs
    assert "export_model_bundle" in docs
