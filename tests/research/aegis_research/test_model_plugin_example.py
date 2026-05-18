from __future__ import annotations

import json
from pathlib import Path


def test_sklearn_model_plugin_notebook_is_valid_explicit_registration_example() -> None:
    notebook_path = Path("docs/examples/model_plugins/sklearn_logistic_plugin.ipynb")
    payload = json.loads(notebook_path.read_text())
    source = "\n".join("".join(cell.get("source", [])) for cell in payload.get("cells", []))

    assert payload["nbformat"] == 4
    assert "ModelRegistry" in source
    assert "model_registry=registry" in source
    assert "examples.sklearn_logistic" in source
    assert "model.kind" not in source
    assert "import_path" not in source


def test_model_plugin_docs_include_pure_python_adaptation_path() -> None:
    readme = Path("docs/examples/model_plugins/README.md").read_text()
    docs = Path("docs/model-plugins.md").read_text()

    assert "pure Python" in readme
    assert "Do not put import paths" in readme
    assert "positive_class_probability" in docs
    assert "export_model_bundle" in docs
