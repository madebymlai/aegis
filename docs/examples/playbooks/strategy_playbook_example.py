# %% playbook overview
# Strategy playbook example.
# Source: run-provided Close feature. Aegis imports PLAYBOOK_CALLABLE for
# ranked runs and centrally computes portfolio metrics from returned signals.


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
    """Sweep moving-average windows and return signals for central scoring."""

    close = inputs.data.feature("Close")
    windows = (10, 20)
    variants = []
    for window in windows:
        average = close.rolling(window).mean()
        variants.append(
            {
                "variant_id": f"strategy-ma-{window}",
                "params": {"window": window},
                "entries": (close > average).fillna(False),
                "exits": (close < average).fillna(False),
            }
        )
    return {"variant_records": variants}


# %% playground notes
# Playground notes:
# In an interactive session, build StrategyInputs from a run config, then call:
# result = generate_candidates(inputs)
