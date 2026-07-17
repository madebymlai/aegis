# %% component overview
# Stable export fixture strategy.

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "tests.export_strategy",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["holding_period"],
    "output_name": "target_weights",
    "consumes_outputs": ["signal"],
    "defaults": {"holding_period": 2},
}


# %% lookback
def lookback(**params):
    """Return the strategy holding-period warmup."""
    return int(params["holding_period"])


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    """Return one allocation array per candidate."""
    import numpy as np

    close = inputs.data.array("Close")
    return np.zeros((len(close), n_candidates * len(close.columns)))
