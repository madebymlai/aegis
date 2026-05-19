from vectorbtpro import vbt

COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "example.ma",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": ["window", "wtype"],
    "output_names": ["ma"],
    "default_outputs": ["ma"],
    "default_model_features": [{"output": "ma", "transform": "distance_to_close"}],
    "supported_transforms": ["identity", "distance_to_close"],
}
COMPONENT_CALLABLE = "run"


def run(data):
    ma = vbt.MA.run(
        data.close,
        window=[10, 30],
        wtype="simple",
        hide_params=None,
        hide_default=False,
    )
    return ma.ma
