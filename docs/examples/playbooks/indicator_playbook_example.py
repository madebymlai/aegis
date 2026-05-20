# %% playbook overview
# Indicator playbook example.
# Source: run-provided Close feature. Indicator variants provide named outputs
# that strategy sources consume; they do not provide leaderboard metrics.

# %% imports
import pandas as pd

# %% define playbook metadata
PLAYBOOK_MANIFEST = {
    "family": "indicators",
    "id": "example_ma_explore",
    "version": "1.0.0",
    "stages": ["indicators"],
    "accepted_inputs": ["Close"],
    "result_schema": "playbook_sweep_result.v1",
    "indicator_family": "moving_average",
    "baseline_component_indicator_id": "example.ma",
}
PLAYBOOK_CALLABLE = "generate_variants"


# %% main compute
def generate_variants(data):
    """Generate candidate-indexed moving-average surfaces."""

    close = data.feature("Close")
    candidates = []
    ma_frames = []
    above_threshold_frames = []
    for window in (10, 20, 50):
        for wtype in ("simple", "wilder"):
            for threshold in (0.0, 0.01):
                candidate_id = f"ma-{window}-{wtype}-{threshold}"
                if wtype == "wilder":
                    average = close.ewm(alpha=1 / window).mean()
                else:
                    average = close.rolling(window).mean()
                ma = average.bfill()
                above_threshold = (close > average * (1 + threshold)).fillna(False)
                ma.columns = pd.MultiIndex.from_product(
                    [[candidate_id], list(close.columns)], names=["candidate_id", "symbol"]
                )
                above_threshold.columns = ma.columns
                ma_frames.append(ma)
                above_threshold_frames.append(above_threshold)
                candidates.append(
                    {
                        "candidate_id": candidate_id,
                        "params": {
                            "window": window,
                            "wtype": wtype,
                            "threshold": threshold,
                        },
                    }
                )
    return {
        "contract": "aegis.playbook_sweep.v1",
        "kind": "indicator_surface",
        "candidate_axis": candidates,
        "outputs": {
            "ma": pd.concat(ma_frames, axis=1),
            "above_threshold": pd.concat(above_threshold_frames, axis=1),
        },
    }


# %% playground notes
# Playground notes:
# Use this cell area for plots and local exploration when opened with Jupytext.
