# %% playbook overview
# Indicator playbook example.
# Source: run-provided Close feature. Indicator variants provide named outputs
# that strategy sources consume; they do not provide leaderboard metrics.


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
def generate_variants(data):
    """Generate moving-average candidates as strategy-consumable outputs."""

    close = data.feature("Close")
    variant_records = []
    for window in (10, 20, 50):
        for wtype in ("simple", "wilder"):
            for threshold in (0.0, 0.01):
                if wtype == "wilder":
                    average = close.ewm(alpha=1 / window).mean()
                else:
                    average = close.rolling(window).mean()
                variant_records.append(
                    {
                        "candidate_id": f"ma-{window}-{wtype}-{threshold}",
                        "params": {
                            "window": window,
                            "wtype": wtype,
                            "threshold": threshold,
                        },
                        "outputs": {
                            "ma": average.bfill(),
                            "above_threshold": (close > average * (1 + threshold)).fillna(False),
                        },
                        "baseline_component_indicator_id": "example.ma",
                    }
                )
    return {"variant_records": variant_records}


# %% playground notes
# Playground notes:
# Use this cell area for plots and local exploration when opened with Jupytext.
