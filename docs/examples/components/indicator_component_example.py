from vectorbtpro import vbt

COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "example.ma",
    "version": "1.0.0",
    "input_names": ["close"],
    "param_names": ["window", "wtype"],
    "output_names": ["ma"],
    "default_outputs": ["ma"],
    "default_model_features": [{"output": "ma", "transform": "distance_to_close"}],
    "supported_transforms": ["identity", "distance_to_close"],
}
COMPONENT_CALLABLE = "run"


def run(close, *, params):
    ma = vbt.MA.run(
        close,
        window=[10, 30],
        wtype="simple",
        hide_params=None,
        hide_default=False,
    )
    return ma.ma
