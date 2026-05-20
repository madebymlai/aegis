# %% playbook overview
# Indicator playbook example.
# Source: run-provided Close feature. This playbook describes an indicator
# idea/family and candidate params; it does not provide leaderboard metrics.


# %% define playbook metadata
PLAYBOOK_MANIFEST = {
    "family": "indicators",
    "id": "example_ma_explore",
    "version": "1.0.0",
    "stages": ["indicators"],
    "accepted_inputs": ["Close"],
    "result_schema": "playbook_result.v1",
    "indicator_family": "moving_average",
    "baseline_component_indicator_id": "example.ma",
}
PLAYBOOK_CALLABLE = "generate_variants"


# %% main compute
def generate_variants(_inputs):
    """Generate the moving-average parameter grid for later promotion."""

    variant_records = []
    for window in (10, 20, 50):
        for wtype in ("simple", "wilder"):
            for threshold in (0.0, 0.01):
                variant_records.append(
                    {
                        "variant_id": f"ma-{window}-{wtype}-{threshold}",
                        "params": {
                            "window": window,
                            "wtype": wtype,
                            "threshold": threshold,
                        },
                        "baseline_component_indicator_id": "example.ma",
                    }
                )
    return {"variant_records": variant_records}


# %% playground notes
# Playground notes:
# Use this cell area for plots and local exploration when opened with Jupytext.
