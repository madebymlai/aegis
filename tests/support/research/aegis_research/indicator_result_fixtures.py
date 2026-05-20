from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.data_schema import table_shape
from research.aegis_research.indicators import (
    FEATURE_COLUMN_NAMES,
    IndicatorResult,
    _apply_transform,
    _feature_name,
    _params_token,
)
from research.aegis_research.market_data.contracts import MarketDataBundle


def returns_indicator_result(close: pd.DataFrame, windows: Sequence[int] = (1,)) -> IndicatorResult:
    return _indicator_result(
        close,
        specs=[
            _Spec(
                indicator_id="returns",
                output_name="returns",
                transform="identity",
                param_rows=[{"window": window} for window in windows],
                values=lambda params: close.pct_change(int(params["window"])),
            )
        ],
    )


def ma_indicator_result(close: pd.DataFrame, windows: Sequence[int] = (3,)) -> IndicatorResult:
    return _indicator_result(
        close,
        specs=[
            _Spec(
                indicator_id="ma",
                output_name="ma",
                transform="distance_to_close",
                param_rows=[{"window": window, "wtype": "simple"} for window in windows],
                values=lambda params: close.rolling(int(params["window"])).mean(),
            )
        ],
    )


def native_indicator_result(data: MarketDataBundle | pd.DataFrame) -> IndicatorResult:
    close = data if isinstance(data, pd.DataFrame) else data.feature("Close")
    ma = vbt.MA.run(
        close,
        window=[10, 30],
        wtype="simple",
        hide_params=None,
        hide_default=False,
    )
    rsi = vbt.RSI.run(
        close,
        window=14,
        wtype="wilder",
        hide_params=None,
        hide_default=False,
    )
    result = _indicator_result(
        close,
        specs=[
            _Spec(
                indicator_id="returns",
                output_name="returns",
                transform="identity",
                param_rows=[{"window": window} for window in (1, 5, 20)],
                values=lambda params: close.pct_change(int(params["window"])),
            ),
            _Spec(
                indicator_id="ma",
                output_name="ma",
                transform="distance_to_close",
                param_rows=[{"window": window, "wtype": "simple"} for window in (10, 30)],
                values=lambda params: close.rolling(int(params["window"])).mean(),
            ),
            _Spec(
                indicator_id="volatility",
                output_name="volatility",
                transform="identity",
                param_rows=[{"window": 20}],
                values=lambda params: close.pct_change().rolling(int(params["window"])).std(),
            ),
            _Spec(
                indicator_id="rsi",
                output_name="rsi",
                transform="scale_0_1",
                param_rows=[{"window": 14, "wtype": "wilder"}],
                values=lambda _params: _single_param_output(rsi.rsi, close),
            ),
        ],
        native_objects={"ma": ma, "rsi": rsi},
    )
    result.metadata["native_object_ids"] = ["ma", "rsi"]
    return result


@dataclass(frozen=True)
class _Spec:
    indicator_id: str
    output_name: str
    transform: str
    param_rows: list[dict[str, Any]]
    values: Callable[[dict[str, Any]], pd.DataFrame]


def _indicator_result(
    close: pd.DataFrame,
    *,
    specs: Sequence[_Spec],
    native_objects: dict[str, Any] | None = None,
) -> IndicatorResult:
    feature_series: list[pd.Series] = []
    feature_columns: list[tuple[str, str, str, str, str, str]] = []
    native_outputs: dict[str, dict[str, pd.DataFrame]] = {}
    lineage: list[dict[str, Any]] = []
    feature_mapping: dict[str, dict[str, Any]] = {}
    metadata_specs: list[dict[str, Any]] = []

    for spec in specs:
        output_frame = _output_frame(close, spec)
        native_outputs[spec.indicator_id] = {spec.output_name: output_frame}
        for params, raw_values in _iter_param_values(close, spec):
            for symbol in close.columns:
                symbol_name = str(symbol)
                values = _apply_transform(
                    close, raw_values[symbol], symbol=symbol_name, transform=spec.transform
                )
                feature_name = _feature_name(
                    spec.indicator_id, spec.output_name, spec.transform, params
                )
                params_token = _params_token(params)
                feature_series.append(values.rename(feature_name))
                feature_columns.append(
                    (
                        feature_name,
                        spec.indicator_id,
                        spec.output_name,
                        spec.transform,
                        params_token,
                        symbol_name,
                    )
                )
                lineage_record = {
                    "feature": feature_name,
                    "indicator_id": spec.indicator_id,
                    "kind": "test_fixture",
                    "output": spec.output_name,
                    "transform": spec.transform,
                    "params": params,
                    "symbol": symbol_name,
                }
                lineage.append(lineage_record)
                feature_mapping.setdefault(
                    feature_name,
                    {
                        "indicator_id": spec.indicator_id,
                        "kind": "test_fixture",
                        "output": spec.output_name,
                        "transform": spec.transform,
                        "params": params,
                    },
                )
        metadata_specs.append(
            {
                "id": spec.indicator_id,
                "parameter_combinations": spec.param_rows,
                "grid_size": len(spec.param_rows),
            }
        )

    frame = pd.concat(feature_series, axis=1)
    frame.columns = pd.MultiIndex.from_tuples(feature_columns, names=FEATURE_COLUMN_NAMES)
    return IndicatorResult(
        frame=frame,
        native_objects=native_objects or {},
        native_outputs=native_outputs,
        lineage=lineage,
        feature_mapping=feature_mapping,
        diagnostics={
            "features": lineage,
            "total_missing_count": int(frame.isna().sum().sum()),
            "total_inf_count": int(frame.isin([float("inf"), float("-inf")]).sum().sum()),
        },
        metadata={
            "invalid_value_policy": "drop_rows",
            "specs": metadata_specs,
            "shape": table_shape(frame),
            "columns": list(map(str, frame.columns)),
            "feature_count": len(feature_mapping),
            "native_object_ids": sorted((native_objects or {}).keys()),
        },
    )


def _output_frame(close: pd.DataFrame, spec: _Spec) -> pd.DataFrame:
    values = []
    columns = []
    for params, raw_values in _iter_param_values(close, spec):
        for symbol in close.columns:
            columns.append((*params.values(), str(symbol)))
            values.append(raw_values[symbol])
    frame = pd.concat(values, axis=1)
    frame.columns = pd.MultiIndex.from_tuples(
        columns,
        names=[*(f"{spec.indicator_id}_{key}" for key in spec.param_rows[0]), "symbol"],
    )
    return frame


def _iter_param_values(close: pd.DataFrame, spec: _Spec):
    for params in spec.param_rows:
        raw_values = spec.values(params)
        yield params, raw_values.reindex(index=close.index, columns=close.columns)


def _single_param_output(frame: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.columns, pd.MultiIndex):
        return frame
    values = []
    for symbol in close.columns:
        matching = [column for column in frame.columns if str(column[-1]) == str(symbol)]
        if not matching and len(close.columns) == 1 and len(frame.columns) == 1:
            matching = [frame.columns[0]]
        values.append(frame[matching[0]].rename(symbol))
    return pd.concat(values, axis=1)
