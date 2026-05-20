# %% component overview
# Fixed moving-average crossover strategy component promoted from playbook research.
# Source: run-provided Close feature and centrally configured Aegis portfolio settings.

# %% define component metadata
COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "example.ma_cross",
    "version": "1.0.0",
    "input_names": ["Close"],
    "signal_outputs": ["entries", "exits"],
    "owns_portfolio": False,
}
COMPONENT_CALLABLE = "run"


# %% main compute
def run(bundle):
    """Emit entries/exits from a fixed 20-bar moving-average crossover."""

    window = 20
    close = bundle.data.feature("Close")
    moving_average = close.rolling(window).mean()
    return {
        "entries": (close > moving_average).fillna(False),
        "exits": (close < moving_average).fillna(False),
    }
