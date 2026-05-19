COMPONENT_MANIFEST = {
    "family": "strategies",
    "id": "example.ma_cross",
    "version": "1.0.0",
    "input_names": ["Close"],
    "signal_outputs": ["entries", "exits"],
    "owns_portfolio": False,
}
COMPONENT_CALLABLE = "run"


def run(bundle):
    window = 10
    close = bundle.data.close
    moving_average = close.rolling(window).mean()
    return {
        "entries": (close > moving_average).fillna(False),
        "exits": (close < moving_average).fillna(False),
    }
