# %% playbook overview
# Label playbook example.
# Source: run-provided Close feature. Label playbooks are percent-cell Python
# sources selected by stable ID.


# %% define playbook metadata
PLAYBOOK_MANIFEST = {
    "family": "labels",
    "id": "example_label_threshold",
    "version": "1.0.0",
    "stages": ["labels"],
    "accepted_inputs": ["Close"],
    "result_schema": "playbook_result.v1",
}
PLAYBOOK_CALLABLE = "generate_variants"


# %% main compute
def generate_variants(_inputs):
    """Return a fixed threshold candidate for label experimentation."""

    threshold = 0.0
    return {
        "variant_records": [
            {
                "variant_id": "label-threshold",
                "params": {"threshold": threshold},
            }
        ]
    }


# %% playground notes
# Playground notes:
# Use this cell area for label distribution checks and local iteration.
