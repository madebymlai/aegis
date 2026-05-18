COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "example.ma_cross",
    "version": "1.0.0",
    "signal_outputs": ["entries", "exits"],
    "owns_portfolio": False,
}
COMPONENT_CALLABLE = "run"


def run(bundle):
    window = int(bundle.params.get("window", 10))
    moving_average = bundle.close.rolling(window).mean()
    return {
        "entries": (bundle.close > moving_average).fillna(False),
        "exits": (bundle.close < moving_average).fillna(False),
    }
