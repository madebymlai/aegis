# %% component overview
# Stable export fixture indicator.

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "tests.export_indicator",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["window"],
    "output_names": ["signal"],
    "defaults": {"window": 5},
}


# %% lookback
def lookback(**params):
    """Return the indicator warmup window."""
    return int(params["window"])


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Return one signal array per candidate."""
    import numpy as np

    close = data.array("Close")
    return {"signal": np.zeros((len(close), n_candidates * len(close.columns)))}
