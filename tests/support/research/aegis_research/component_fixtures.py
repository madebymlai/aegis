from __future__ import annotations

from pathlib import Path


def write_label_component(path: Path, *, body: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = body or (
        "from research.aegis_research.labels import LabelConfig, build_label_result\n"
        "def run(data):\n"
        "    return build_label_result(data.feature('Close'), LabelConfig())\n"
    )
    path.write_text(
        "COMPONENT_MANIFEST = {"
        "'family': 'labels', 'id': 'demo.fixlb', 'version': '1.0.0', "
        "'input_names': ['Close'], "
        "'target_role': 'supervised_target', 'target_kind': 'binary_classification', "
        "'output_names': ['labels']}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        f"{body}"
    )


def write_indicator_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "COMPONENT_MANIFEST = {"
        "'family': 'indicators', 'id': 'demo.returns', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': [], 'output_names': ['returns'], "
        "'default_outputs': ['returns'], "
        "'default_model_features': [{'output': 'returns', 'transform': 'identity'}], "
        "'supported_transforms': ['identity']}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "def run(data):\n"
        "    return data.feature('Close').pct_change().fillna(0.0)\n"
    )
