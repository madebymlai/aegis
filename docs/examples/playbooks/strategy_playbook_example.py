# %% playbook overview
# Strategy playbook example.
# Source: run-provided Close feature plus source-scoped indicator candidates.
# Aegis centrally computes portfolio metrics from returned signals.

# %% imports
import pandas as pd

# %% define playbook metadata
PLAYBOOK_MANIFEST = {
    "family": "strategies",
    "id": "example_strategy_ma_cross",
    "version": "1.0.0",
    "stages": ["strategies"],
    "accepted_inputs": ["Close"],
    "result_schema": "batched_playbook_result.v1",
}
PLAYBOOK_CALLABLE = "generate_candidates"


# %% main compute
def generate_candidates(inputs):
    """Discover strategy candidates and materialize requested signal batches."""

    close = inputs.data.feature("Close")
    ma_source = inputs.indicators["playbook:example_ma_explore"]
    ma_surface = ma_source["outputs"]["ma"]

    def materialize_signals(request):
        entry_frames = []
        exit_frames = []
        for candidate in request.candidates:
            indicator_id = candidate.indicators[0].candidate_id
            moving_average = ma_surface.xs(indicator_id, level="candidate_id", axis=1, drop_level=True)
            moving_average.columns = close.columns
            threshold = candidate.strategy.params["threshold"]
            entries = (close > moving_average * (1 + threshold)).fillna(False)
            exits = (close < moving_average).fillna(False)
            entries.columns = pd.MultiIndex.from_product(
                [[candidate.candidate_id], list(close.columns)], names=["candidate_id", "symbol"]
            )
            exits.columns = entries.columns
            entry_frames.append(entries)
            exit_frames.append(exits)
        return {
            "contract": "aegis.batched_playbook.v1",
            "kind": "strategy_signals",
            "entries": pd.concat(entry_frames, axis=1),
            "exits": pd.concat(exit_frames, axis=1),
        }

    return {
        "contract": "aegis.batched_playbook.v1",
        "kind": "strategy_axis",
        "candidate_axis": [
            {"candidate_id": "strategy-ma-threshold-0", "params": {"threshold": 0.0}},
            {"candidate_id": "strategy-ma-threshold-1", "params": {"threshold": 0.01}},
        ],
        "materialize_signals": materialize_signals,
    }


# %% playground notes
# Playground notes:
# In an interactive session, build StrategyInputs from a run config, then call
# generate_candidates(inputs) to inspect the strategy axis.
