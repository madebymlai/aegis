# %% playbook overview
# Strategy playbook example.
# Source: run-provided Close feature plus source-scoped indicator candidates.
# Aegis centrally computes portfolio metrics from returned signals.


# %% define playbook metadata
PLAYBOOK_MANIFEST = {
    "family": "strategies",
    "id": "example_strategy_ma_cross",
    "version": "1.0.0",
    "stages": ["strategies"],
    "accepted_inputs": ["Close"],
    "result_schema": "playbook_result.v1",
}
PLAYBOOK_CALLABLE = "generate_candidates"


# %% main compute
def generate_candidates(inputs):
    """Sweep trade-rule thresholds over selected indicator candidates."""

    close = inputs.data.feature("Close")
    ma_source = inputs.indicators["playbook:example_ma_explore"]
    moving_average = ma_source["outputs"]["ma"]
    thresholds = (0.0, 0.01)
    variants = []
    for threshold in thresholds:
        variants.append(
            {
                "variant_id": f"strategy-ma-threshold-{threshold}",
                "params": {"threshold": threshold},
                "entries": (close > moving_average * (1 + threshold)).fillna(False),
                "exits": (close < moving_average).fillna(False),
            }
        )
    return {"variant_records": variants}


# %% playground notes
# Playground notes:
# In an interactive session, build StrategyInputs from a run config, then call:
# result = generate_candidates(inputs)
