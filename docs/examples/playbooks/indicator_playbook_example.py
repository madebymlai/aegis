# %% playbook overview
# DEPRECATED — scheduled for removal under issue #32.
# Indicator playbook example for the deprecated candidate-sweep contract
# (result_schema: "playbook_sweep_result.v1"). Indicator playbooks feed only
# the deprecated sweep-contract strategies; optimization sources compute their
# own indicators inline via `vbt.Param`. See `optimization_playbook_example.py`
# for the forward path; do not author new indicator playbooks against this
# contract.
# Source: run-provided Close feature. Indicator variants provide named outputs
# that strategy sources consume; they do not provide leaderboard metrics.

# %% imports
import pandas as pd

from research.aegis_research.candidate_sweeps import candidate_id_from_params

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
                params = {"window": window, "wtype": wtype, "threshold": threshold}
                candidate_id = candidate_id_from_params(
                    "ma",
                    params,
                    keys=("window", "wtype", "threshold"),
                )
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
                        "params": params,
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
