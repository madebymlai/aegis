from research.aegis_research.labels import LabelConfig, build_label_result

COMPONENT_MANIFEST = {
    "family": "labels",
    "id": "example.fixlb_binary",
    "version": "1.0.0",
    "input_names": ["Close"],
    "target_role": "supervised_target",
    "target_kind": "binary_classification",
    "output_names": ["labels"],
    "split_safety": {"purging_required": True},
}
COMPONENT_CALLABLE = "run"


def run(data):
    config = LabelConfig()
    return build_label_result(data.close, config)
