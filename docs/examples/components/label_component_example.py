# %% component overview
# Fixed binary label component promoted for reproducible model training.
# Source: Aegis label helpers over the run-provided Close feature.

# %% imports
from research.aegis_research.labels import LabelConfig, build_label_result


# %% define component metadata
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


# %% main compute
def run(data):
    """Build fixed binary labels using the default Aegis label configuration."""

    config = LabelConfig()
    return build_label_result(data.feature("Close"), config)
