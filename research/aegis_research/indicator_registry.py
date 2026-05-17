from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from vectorbtpro import vbt


@dataclass(frozen=True)
class IndicatorDefinition:
    id: str
    kind: str
    input_names: tuple[str, ...]
    param_names: tuple[str, ...]
    output_names: tuple[str, ...]
    default_outputs: tuple[str, ...]
    default_model_features: tuple[dict[str, str], ...]
    supported_transforms: tuple[str, ...]
    indicator_class: Any | None = None
    default_params: dict[str, Any] = field(default_factory=dict)
    default_run_kwargs: dict[str, Any] = field(default_factory=dict)
    allowed_param_values: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    bar_aligned: bool = True


def indicator_registry() -> dict[str, IndicatorDefinition]:
    return dict(_REGISTRY)


def get_indicator_definition(indicator_id: str) -> IndicatorDefinition:
    return _REGISTRY[indicator_id]


def register_indicator_definition(
    registry: dict[str, IndicatorDefinition],
    definition: IndicatorDefinition,
) -> None:
    if definition.id in registry:
        raise ValueError(f"duplicate indicator definition id: {definition.id}")
    registry[definition.id] = definition


def _custom_retvol_apply(close: pd.DataFrame, window: int) -> pd.DataFrame:
    return close.pct_change().rolling(window).std()


CUSTOM_RETVOL = vbt.IF(
    input_names=["close"],
    param_names=["window"],
    output_names=["retvol"],
).with_apply_func(_custom_retvol_apply, keep_pd=True)


_WTYPE_VALUES = ("simple", "exp", "wilder", "wilders")

_REGISTRY: dict[str, IndicatorDefinition] = {}

for _definition in (
    IndicatorDefinition(
        id="returns",
        kind="primitive",
        input_names=("close",),
        param_names=("window",),
        output_names=("returns",),
        default_outputs=("returns",),
        default_model_features=({"output": "returns", "transform": "identity"},),
        supported_transforms=("identity",),
    ),
    IndicatorDefinition(
        id="ma",
        kind="vectorbt",
        input_names=("close",),
        param_names=("window", "wtype"),
        output_names=("ma",),
        default_outputs=("ma",),
        default_model_features=({"output": "ma", "transform": "distance_to_close"},),
        supported_transforms=("identity", "distance_to_close"),
        indicator_class=vbt.MA,
        default_params={"wtype": "simple"},
        default_run_kwargs={"hide_params": None, "hide_default": False},
        allowed_param_values={"wtype": _WTYPE_VALUES},
    ),
    IndicatorDefinition(
        id="volatility",
        kind="primitive",
        input_names=("close",),
        param_names=("window",),
        output_names=("volatility",),
        default_outputs=("volatility",),
        default_model_features=({"output": "volatility", "transform": "identity"},),
        supported_transforms=("identity",),
    ),
    IndicatorDefinition(
        id="rsi",
        kind="vectorbt",
        input_names=("close",),
        param_names=("window", "wtype"),
        output_names=("rsi",),
        default_outputs=("rsi",),
        default_model_features=({"output": "rsi", "transform": "scale_0_1"},),
        supported_transforms=("identity", "scale_0_1"),
        indicator_class=vbt.RSI,
        default_params={"wtype": "wilder"},
        default_run_kwargs={"hide_params": None, "hide_default": False},
        allowed_param_values={"wtype": _WTYPE_VALUES},
    ),
    IndicatorDefinition(
        id="custom_retvol",
        kind="custom",
        input_names=("close",),
        param_names=("window",),
        output_names=("retvol",),
        default_outputs=("retvol",),
        default_model_features=({"output": "retvol", "transform": "identity"},),
        supported_transforms=("identity",),
        indicator_class=CUSTOM_RETVOL,
        default_run_kwargs={"hide_params": None, "hide_default": False},
    ),
):
    register_indicator_definition(_REGISTRY, _definition)
