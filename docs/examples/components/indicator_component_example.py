from research.aegis_research.config import IndicatorConfig, IndicatorFeatureConfig, IndicatorSpecConfig
from research.aegis_research.indicators import build_indicator_result

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
    config = IndicatorConfig(
        specs=[
            IndicatorSpecConfig(
                id="ma",
                params={"window": params.get("window", [10]), "wtype": params.get("wtype", "simple")},
                outputs=["ma"],
                model_features=[IndicatorFeatureConfig(output="ma", transform="distance_to_close")],
            )
        ]
    )
    return build_indicator_result(close, config)
