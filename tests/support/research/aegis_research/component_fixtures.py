from __future__ import annotations

from pathlib import Path


def write_label_component(path: Path, *, body: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = body or (
        "from research.aegis_research.labels import LabelConfig, build_label_result\n"
        "def run(data):\n"
        "    return build_label_result(data.feature('Close'), LabelConfig())\n"
    )
    body = body.replace(
        "def run(data):\n",
        "# %% main compute\n"
        "def run(data):\n"
        '    """Build fixed binary labels from the Close feature."""\n',
        1,
    )
    path.write_text(
        "# %% component overview\n"
        "# Label fixture component used by integration tests.\n"
        "# Source: synthetic Close data supplied by the test fixture.\n"
        "\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'labels', 'id': 'demo.fixlb', 'version': '1.0.0', "
        "'input_names': ['Close'], "
        "'target_role': 'supervised_target', 'target_kind': 'binary_classification', "
        "'output_names': ['labels']}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% imports and definitions\n"
        f"{body}"
    )


def write_indicator_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Indicator fixture component used by integration tests.\n"
        "# Source: synthetic Close data supplied by the test fixture.\n"
        "\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'indicators', 'id': 'demo.returns', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': [], 'output_names': ['returns'], "
        "'default_outputs': ['returns'], "
        "'default_model_features': [{'output': 'returns', 'transform': 'identity'}], "
        "'supported_transforms': ['identity']}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "\n# %% main compute\n"
        "def run(data):\n"
        '    """Compute fixed one-bar Close returns with the initial value filled."""\n'
        "    return data.feature('Close').pct_change().fillna(0.0)\n"
    )
