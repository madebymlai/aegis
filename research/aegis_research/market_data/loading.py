from __future__ import annotations

import csv
from pathlib import Path
from typing import Any
from warnings import warn

import numpy as np
import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration.schema import (
    DENIED_PASSTHROUGH_KEYS,
    SECRET_KEY_RE,
    SECRET_VALUE_RE,
    DataConfig,
    SignalConfig,
    has_data_array_token_shape,
)
from research.aegis_research.configuration.secrets import (
    redact_text,
    resolve_secret_refs,
    to_builtin,
)
from research.aegis_research.configuration.validation import _is_absolute_or_user_path
from research.aegis_research.data_arrays import merge_data_arrays
from research.aegis_research.market_data.contracts import (
    OHLCV_FEATURES,
    QUALITY_DEGRADED_ALLOWED,
    QUALITY_HEALTHY,
    QUALITY_PROVIDER_FAILED,
    QUALITY_REJECTED,
    SAFE_FETCH_KWARG_KEYS,
    SAFE_RETURNED_KWARG_KEYS,
    MarketDataAdapter,
    MarketDataAdapterResult,
    MarketDataQuality,
    MarketDataResult,
    RemoteDataPullError,
)
from research.aegis_research.market_data.sources import (
    vbt_data_source_classes,
)


def load_market_data(config: DataConfig) -> Any:
    result = load_market_data_result(config)
    result.assert_usable()
    return result.native_data


def load_market_data_result(
    config: DataConfig,
    *,
    required_features: tuple[str, ...] | None = None,
    adapters: dict[str, MarketDataAdapter] | None = None,
) -> MarketDataResult:
    """Load data through VBT-backed sources, then apply Aegis evidence/quality contracts."""
    source = config.source.lower()
    source_loaders = {**_default_source_loaders(), **(adapters or {})}
    if source not in source_loaders:
        raise ValueError(f"Unsupported data source: {config.source}")
    requested = config.effective_arrays
    required = merge_data_arrays(requested, required_features or ())

    try:
        adapter_result = source_loaders[source](config)
    except RemoteDataPullError as error:
        return _provider_failed_result(config, error, required_features=required)
    panels = _available_feature_panels(adapter_result.native_data, requested)
    diagnostics, quality = _evaluate_quality(
        config,
        adapter_result.native_data,
        panels,
        required_features=required,
        evidence=adapter_result.evidence,
    )
    metadata = _data_metadata(
        config,
        adapter_result.native_data,
        panels,
        diagnostics=diagnostics,
        quality=quality,
        source_metadata=adapter_result.source_metadata,
        evidence=adapter_result.evidence,
        required_features=required,
    )
    assert_public_metadata_safe(metadata, known_secrets=adapter_result.known_secrets)
    return MarketDataResult(
        native_data=adapter_result.native_data,
        metadata=metadata,
        diagnostics=tuple(diagnostics),
        quality=quality,
        known_secrets=adapter_result.known_secrets,
    )


def _provider_failed_result(
    config: DataConfig,
    error: RemoteDataPullError,
    *,
    required_features: tuple[str, ...],
) -> MarketDataResult:
    reason = f"{config.source} provider failed before usable native data was available"
    quality = MarketDataQuality(
        state=QUALITY_PROVIDER_FAILED,
        reasons=(reason,),
        allowed_degradations=tuple(config.quality.allowed_degradations),
    )
    diagnostics = tuple(
        {
            "symbol": symbol,
            "configured": True,
            "features": {},
            "index_evidence": {"source": "provider_failed"},
            "provider_status": QUALITY_PROVIDER_FAILED,
        }
        for symbol in config.symbols
    )
    metadata: dict[str, Any] = {
        "schema_version": "market_data.v2",
        "source": config.source,
        "provider_class": None,
        "native_class": None,
        "requested_symbols": list(config.symbols),
        "symbols": [],
        "features": [],
        "canonical_features": [],
        "authored_arrays": to_builtin(config.arrays),
        "effective_arrays": list(config.effective_arrays),
        "required_arrays": list(required_features),
        "loaded_arrays": [],
        "unavailable_arrays": list(required_features),
        "timeframe": config.timeframe,
        "shape": {"rows": 0, "symbols": 0, "features": 0, "columns": 0},
        "ohlc_available": dict.fromkeys(OHLCV_FEATURES, False),
        "index_start": None,
        "index_end": None,
        "missing_index": config.missing_index,
        "missing_columns": config.missing_columns,
        "tz_localize": config.tz_localize,
        "tz_convert": config.tz_convert,
        "skip_on_error": config.skip_on_error,
        "silence_warnings": config.silence_warnings,
        "quality": quality.to_metadata(),
        "diagnostics": list(diagnostics),
        "source_metadata": {
            "provider_error_type": type(error).__name__,
            "provider_error_summary": reason,
        },
        "index_evidence": {"source": "provider_failed"},
        "provider_metadata": {},
        "omitted_metadata_fields": [],
        "update_supported": False,
        "cache_policy": "disabled_in_schema_v2",
    }
    metadata = to_builtin(metadata)
    assert_public_metadata_safe(metadata)
    return MarketDataResult(
        native_data=None,
        metadata=metadata,
        diagnostics=diagnostics,
        quality=quality,
    )


def required_ohlcv_features() -> tuple[str, ...]:
    return ("Close",)


def required_experiment_ohlcv_features(
    signal_config: SignalConfig | None = None,
) -> tuple[str, ...]:
    features = list(required_ohlcv_features())
    signal_config = signal_config or SignalConfig()
    if signal_config.execution_timing == "next_open" and "Open" not in features:
        features.append("Open")
    return tuple(features)


def close_from_ohlcv(data: Any) -> pd.DataFrame:
    return feature_from_ohlcv(data, "Close")


def high_from_ohlcv(data: Any) -> pd.DataFrame:
    return feature_from_ohlcv(data, "High")


def low_from_ohlcv(data: Any) -> pd.DataFrame:
    return feature_from_ohlcv(data, "Low")


def feature_from_ohlcv(data: Any, feature: str) -> pd.DataFrame:
    if isinstance(data, MarketDataResult):
        data.assert_usable()
        loaded = tuple(data.metadata.get("loaded_arrays", ()))
        if loaded and feature not in loaded:
            raise ValueError(f"market data feature {feature!r} was not loaded for this run")
        return _canonical_feature_panel(data.native_data, feature)
    if hasattr(data, "get") and not isinstance(data, pd.DataFrame):
        return _feature_panel(data, feature, role=feature)
    return _feature_from_frame(data, feature)


def assert_public_metadata_safe(
    value: Any,
    *,
    known_secrets: tuple[str, ...] = (),
    path: str = "$",
) -> None:
    if isinstance(value, str):
        if any(secret and secret in value for secret in known_secrets) or SECRET_VALUE_RE.search(
            value
        ):
            raise ValueError(f"public data metadata contains secret material at {path}")
        if _is_absolute_or_user_path(value):
            raise ValueError(f"public data metadata contains a non-portable path at {path}")
        return
    if value is None or isinstance(value, bool | int | float):
        return
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if SECRET_KEY_RE.search(key_text) or key_text.lower() in DENIED_PASSTHROUGH_KEYS:
                raise ValueError(f"public data metadata contains secret-like key at {child_path}")
            assert_public_metadata_safe(item, known_secrets=known_secrets, path=child_path)
        return
    if isinstance(value, list | tuple):
        for index, item in enumerate(value):
            assert_public_metadata_safe(item, known_secrets=known_secrets, path=f"{path}[{index}]")
        return
    raise ValueError(f"public data metadata contains unsupported value at {path}")


def _default_source_loaders() -> dict[str, MarketDataAdapter]:
    return {
        "synthetic": _load_synthetic_source,
        "csv": _load_csv_source,
        **{
            source: (
                lambda config, source=source, data_cls=data_cls: _load_vbt_remote_source(
                    source,
                    data_cls,
                    config,
                )
            )
            for source, data_cls in vbt_data_source_classes().items()
        },
    }


def _feature_panel(data: Any, feature: str, *, role: str) -> pd.DataFrame:
    values = data.get(
        feature=feature,
        squeeze_features=False,
        squeeze_symbols=False,
    )
    return _as_panel(values, role=role)


def _feature_from_frame(data: pd.DataFrame, feature: str) -> pd.DataFrame:
    if isinstance(data.columns, pd.MultiIndex):
        if feature in data.columns.get_level_values(-1):
            return _as_panel(data.xs(feature, axis=1, level=-1), role=feature)
        if feature in data.columns.get_level_values(0):
            return _as_panel(data.xs(feature, axis=1, level=0), role=feature)
    if feature in data.columns:
        return _as_panel(data[feature], role=feature)
    raise ValueError(f"Data must contain a {feature} column")


def _as_panel(values: Any, *, role: str) -> pd.DataFrame:
    if isinstance(values, pd.Series):
        return values.to_frame(name=values.name or role)
    if not isinstance(values, pd.DataFrame):
        raise TypeError(f"{role} values must be a pandas Series or DataFrame")
    return values


def _load_synthetic_source(config: DataConfig) -> MarketDataAdapterResult:
    native_data = _synthetic_data(config)
    return MarketDataAdapterResult(
        native_data=native_data,
        source_metadata={"generated": True, "seed": config.seed, "rows": config.rows},
        evidence=_index_evidence(native_data.index, source="generated"),
    )


def _load_csv_source(config: DataConfig) -> MarketDataAdapterResult:
    if config.path is None:
        raise ValueError("data.path is required for csv source")
    frame = _read_csv(config)
    evidence = _index_evidence(frame.index, source="csv_raw")
    feature_data = _csv_feature_data(frame, config)
    native_data = _native_from_feature_data(feature_data, config)
    return MarketDataAdapterResult(
        native_data=native_data,
        source_metadata={"path": "<redacted>", "layout": _csv_layout(frame)},
        evidence=evidence,
    )


def _load_vbt_remote_source(source: str, data_cls, config: DataConfig) -> MarketDataAdapterResult:
    native_data, known_secrets = _pull_remote(data_cls, config)
    return MarketDataAdapterResult(
        native_data=native_data,
        known_secrets=known_secrets,
        source_metadata={"provider_class": f"{data_cls.__module__}.{data_cls.__qualname__}"},
        evidence=_index_evidence(_native_index(native_data), source="post_vectorbt_alignment"),
    )


def _read_csv(config: DataConfig) -> pd.DataFrame:
    path = Path(config.path or "")
    if _csv_looks_multiindex(path, config):
        return _localize_csv_index(pd.read_csv(path, header=[0, 1], index_col=0, parse_dates=True))
    return _localize_csv_index(pd.read_csv(path, index_col=0, parse_dates=True))


def _csv_looks_multiindex(path: Path, config: DataConfig) -> bool:
    rows = _csv_probe_rows(path, limit=2)
    if len(rows) < 2:
        return False
    first_header = set(map(str, rows[0][1:]))
    if first_header & set(config.effective_arrays):
        return False
    second_header = rows[1][1:]
    second_values = set(map(str, second_header))
    multiindex_markers = set(config.symbols) | set(config.effective_arrays)
    return (
        bool(second_header)
        and bool((first_header | second_values) & multiindex_markers)
        and not any(str(value).startswith("Unnamed") for value in second_header)
    )


def _csv_probe_rows(path: Path, *, limit: int) -> list[list[str]]:
    rows: list[list[str]] = []
    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            rows.append(row)
            if len(rows) == limit:
                break
    return rows


def _localize_csv_index(frame: pd.DataFrame) -> pd.DataFrame:
    if isinstance(frame.index, pd.DatetimeIndex) and frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    return frame


def _csv_feature_data(frame: pd.DataFrame, config: DataConfig) -> dict[str, pd.DataFrame]:
    if isinstance(frame.columns, pd.MultiIndex):
        return _multiindex_csv_feature_data(frame, config)
    return _flat_csv_feature_data(frame, config)


def _flat_csv_feature_data(frame: pd.DataFrame, config: DataConfig) -> dict[str, pd.DataFrame]:
    if len(config.symbols) != 1:
        raise ValueError("flat CSV feature input requires exactly one configured symbol")
    symbol = config.symbols[0]
    feature_data = {}
    for feature in _csv_feature_candidates(map(str, frame.columns), config):
        if feature in frame.columns:
            feature_data[feature] = frame[[feature]].rename(columns={feature: symbol})
    if not feature_data:
        raise ValueError("CSV data must contain at least one requested VBT feature column")
    return feature_data


def _multiindex_csv_feature_data(
    frame: pd.DataFrame, config: DataConfig
) -> dict[str, pd.DataFrame]:
    symbol_level, feature_level = _csv_multiindex_levels(frame, config)
    feature_data = {}
    feature_values = set(map(str, frame.columns.get_level_values(feature_level)))
    for feature in _csv_feature_candidates(frame.columns.get_level_values(feature_level), config):
        if feature not in feature_values:
            continue
        panel = frame.xs(feature, axis=1, level=feature_level)
        if isinstance(panel.columns, pd.MultiIndex):
            panel.columns = panel.columns.get_level_values(symbol_level)
        panel = panel.loc[:, [symbol for symbol in config.symbols if symbol in panel.columns]]
        if not panel.empty:
            feature_data[feature] = panel
    if not feature_data:
        raise ValueError("CSV MultiIndex data must contain at least one requested VBT feature")
    return feature_data


def _csv_multiindex_levels(frame: pd.DataFrame, config: DataConfig) -> tuple[int, int]:
    level_values = [
        set(map(str, frame.columns.get_level_values(index)))
        for index in range(frame.columns.nlevels)
    ]
    configured_symbols = set(config.symbols)
    symbol_levels = [
        index for index, values in enumerate(level_values) if configured_symbols & values
    ]
    source_features = set(config.effective_arrays)
    source_features.update(
        value
        for values in level_values
        for value in values
        if value not in configured_symbols and _looks_like_vbt_feature_name(value)
    )
    feature_levels = [
        index for index, values in enumerate(level_values) if source_features & values
    ]
    if not symbol_levels or not feature_levels:
        raise ValueError("CSV MultiIndex columns must include symbol and feature levels")
    symbol_level = symbol_levels[0]
    feature_level = next(
        (level for level in feature_levels if level != symbol_level), feature_levels[0]
    )
    if symbol_level == feature_level:
        raise ValueError("CSV MultiIndex symbol and feature levels must be distinct")
    return symbol_level, feature_level


def _csv_feature_candidates(values: Any, config: DataConfig) -> tuple[str, ...]:
    candidates = tuple(
        value
        for value in dict.fromkeys(map(str, values))
        if value not in config.symbols and _looks_like_vbt_feature_name(value)
    )
    return merge_data_arrays(config.effective_arrays, candidates)


def _looks_like_vbt_feature_name(value: str) -> bool:
    return has_data_array_token_shape(value)


def _csv_layout(frame: pd.DataFrame) -> str:
    return "multiindex" if isinstance(frame.columns, pd.MultiIndex) else "flat"


def _pull_remote(data_cls, config: DataConfig) -> tuple[Any, tuple[str, ...]]:
    wrapper_kwargs, wrapper_secrets = resolve_secret_refs(
        config.wrapper_kwargs,
        "data.wrapper_kwargs",
    )
    provider_kwargs, provider_secrets = resolve_secret_refs(
        config.provider_kwargs,
        "data.provider_kwargs",
    )
    execution_kwargs, execution_secrets = resolve_secret_refs(
        config.execution_kwargs,
        "data.execution_kwargs",
    )
    secrets = wrapper_secrets + provider_secrets + execution_secrets
    error_message = None
    try:
        raw_outputs = data_cls.pull(
            config.symbols,
            start=config.start,
            end=config.end,
            timeframe=config.timeframe,
            missing_index=config.missing_index,
            missing_columns=config.missing_columns,
            tz_localize=config.tz_localize,
            tz_convert=config.tz_convert,
            wrapper_kwargs=wrapper_kwargs,
            skip_on_error=config.skip_on_error,
            silence_warnings=config.silence_warnings,
            execute_kwargs=execution_kwargs,
            return_raw=True,
            **provider_kwargs,
        )
        native_data = _native_from_remote_raw_outputs(
            data_cls,
            config,
            raw_outputs,
            wrapper_kwargs=wrapper_kwargs,
            provider_kwargs=provider_kwargs,
        )
        return native_data, tuple(secrets)
    except Exception as error:
        error_message = redact_text(str(error), secrets)
    raise RemoteDataPullError(config.source, error_message)


def _native_from_remote_raw_outputs(
    data_cls,
    config: DataConfig,
    raw_outputs: list[Any],
    *,
    wrapper_kwargs: dict[str, Any],
    provider_kwargs: dict[str, Any],
) -> Any:
    if len(raw_outputs) != len(config.symbols):
        raise ValueError("remote provider returned a different number of raw outputs than symbols")

    data: dict[str, pd.Series | pd.DataFrame] = {}
    returned_kwargs: dict[str, dict[str, Any]] = {}
    fetch_kwargs = {symbol: dict(provider_kwargs) for symbol in config.symbols}
    tz_localize = config.tz_localize
    tz_convert = config.tz_convert
    from_data_wrapper_kwargs = dict(wrapper_kwargs)
    common_tz_localize = None
    common_tz_convert = None
    common_freq = None

    for symbol, output in zip(config.symbols, raw_outputs, strict=True):
        if output is None:
            continue
        raw_data, raw_returned_kwargs = _remote_raw_data_and_metadata(output)
        projected = _project_remote_symbol_data(raw_data, config.effective_arrays, symbol=symbol)
        if projected.size == 0:
            if not config.silence_warnings:
                warn(f"Symbol {symbol!r} returned an empty array. Skipping.", stacklevel=2)
            continue
        symbol_returned_kwargs = dict(raw_returned_kwargs)
        common_tz_localize, common_tz_convert, common_freq = _update_common_remote_metadata(
            symbol_returned_kwargs,
            common_tz_localize=common_tz_localize,
            common_tz_convert=common_tz_convert,
            common_freq=common_freq,
            silence_warnings=config.silence_warnings,
        )
        data[symbol] = projected
        returned_kwargs[symbol] = symbol_returned_kwargs

    if not data:
        raise ValueError("No symbols could be fetched")
    if tz_localize is None and common_tz_localize is not None:
        tz_localize = common_tz_localize
    if tz_convert is None and common_tz_convert is not None:
        tz_convert = common_tz_convert
    if from_data_wrapper_kwargs.get("freq") is None and common_freq is not None:
        from_data_wrapper_kwargs["freq"] = common_freq

    return data_cls.from_data(
        data,
        single_key=False,
        tz_localize=tz_localize,
        tz_convert=tz_convert,
        missing_index=config.missing_index,
        missing_columns=config.missing_columns,
        wrapper_kwargs=from_data_wrapper_kwargs,
        fetch_kwargs=fetch_kwargs,
        returned_kwargs=returned_kwargs,
        silence_warnings=config.silence_warnings,
    )


def _remote_raw_data_and_metadata(output: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(output, tuple):
        return output[0], dict(output[1])
    return output, {}


def _project_remote_symbol_data(
    raw_data: Any,
    requested_features: tuple[str, ...],
    *,
    symbol: str,
) -> pd.Series | pd.DataFrame:
    if isinstance(raw_data, pd.Series):
        if raw_data.name in requested_features:
            return raw_data
        return raw_data.iloc[0:0]
    if not isinstance(raw_data, pd.DataFrame):
        raise TypeError(
            f"remote provider returned non-tabular data for symbol {symbol!r}; "
            "configured data arrays require named feature columns"
        )
    columns = [feature for feature in requested_features if feature in raw_data.columns]
    return raw_data.loc[:, columns]


def _update_common_remote_metadata(
    returned_kwargs: dict[str, Any],
    *,
    common_tz_localize: Any,
    common_tz_convert: Any,
    common_freq: Any,
    silence_warnings: bool,
) -> tuple[Any, Any, Any]:
    tz = returned_kwargs.pop("tz", None)
    tz_localize = returned_kwargs.pop("tz_localize", None)
    tz_convert = returned_kwargs.pop("tz_convert", None)
    freq = returned_kwargs.pop("freq", None)
    if tz is not None:
        if tz_localize is None:
            tz_localize = tz
        if tz_convert is None:
            tz_convert = tz
    if tz_localize is not None:
        if common_tz_localize is None:
            common_tz_localize = tz_localize
        elif common_tz_localize != tz_localize:
            raise ValueError("Returned objects have different timezones (tz_localize)")
    if tz_convert is not None:
        if common_tz_convert is None:
            common_tz_convert = tz_convert
        elif common_tz_convert != tz_convert:
            if not silence_warnings:
                warn("Returned objects have different timezones (tz_convert). Setting to UTC.", stacklevel=2)
            common_tz_convert = "utc"
    if freq is not None:
        if common_freq is None:
            common_freq = freq
        elif common_freq != freq:
            raise ValueError("Returned objects have different frequencies (freq)")
    return common_tz_localize, common_tz_convert, common_freq


def _available_feature_panels(
    native_data: Any, requested_features: tuple[str, ...]
) -> dict[str, pd.DataFrame]:
    panels = {}
    for feature in requested_features:
        try:
            panels[feature] = _canonical_feature_panel(native_data, feature)
        except (KeyError, ValueError, TypeError):
            continue
    return panels


def _canonical_feature_panel(
    native_data: Any,
    feature: str,
) -> pd.DataFrame:
    return _feature_panel(native_data, feature, role=feature)


def _evaluate_quality(
    config: DataConfig,
    native_data: Any,
    panels: dict[str, pd.DataFrame],
    *,
    required_features: tuple[str, ...],
    evidence: dict[str, Any],
) -> tuple[list[dict[str, Any]], MarketDataQuality]:
    diagnostics = _symbol_diagnostics(config, native_data, panels, evidence=evidence)
    reasons: list[str] = []
    warnings: list[str] = []
    degradations: set[str] = set()
    allowed = set(config.quality.allowed_degradations)

    observed_symbols = set(_native_symbols(native_data, fallback=config.symbols))
    skipped_symbols = [symbol for symbol in config.symbols if symbol not in observed_symbols]
    allowed_skipped_symbols = (
        set(skipped_symbols) if (config.skip_on_error and "skipped_symbols" in allowed) else set()
    )
    if skipped_symbols:
        if allowed_skipped_symbols:
            _record_quality_issue(
                "skipped_symbols",
                f"configured symbols missing from loaded data: {skipped_symbols}",
                allowed,
                reasons,
                warnings,
                degradations,
            )
        else:
            reasons.append(f"configured symbols missing from loaded data: {skipped_symbols}")

    if evidence.get("raw_index_has_duplicates"):
        _record_quality_issue(
            "duplicate_index",
            "raw data index contains duplicate timestamps",
            allowed,
            reasons,
            warnings,
            degradations,
        )
    if evidence.get("raw_index_monotonic_increasing") is False:
        _record_quality_issue(
            "non_monotonic_index",
            "raw data index is not monotonic increasing",
            allowed,
            reasons,
            warnings,
            degradations,
        )

    for feature in required_features:
        if feature not in panels:
            reasons.append(f"required feature {feature!r} is unavailable")
            continue
        panel = panels[feature]
        if panel.empty:
            reasons.append(f"required feature {feature!r} is empty")
            continue
        missing_required_symbols = [
            symbol
            for symbol in config.symbols
            if symbol not in panel.columns and symbol not in allowed_skipped_symbols
        ]
        if missing_required_symbols:
            reasons.append(
                f"required feature {feature!r} is missing symbols {missing_required_symbols}"
            )
        if panel.isna().any().any():
            _record_quality_issue(
                "missing_rows",
                f"required feature {feature!r} contains missing values",
                allowed,
                reasons,
                warnings,
                degradations,
            )
        non_numeric = [
            symbol for symbol in panel.columns if not pd.api.types.is_numeric_dtype(panel[symbol])
        ]
        if non_numeric:
            reasons.append(f"required feature {feature!r} has non-numeric symbols {non_numeric}")

    if reasons:
        state = QUALITY_REJECTED
    elif degradations & allowed:
        state = QUALITY_DEGRADED_ALLOWED
    else:
        state = QUALITY_HEALTHY
    return diagnostics, MarketDataQuality(
        state=state,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        allowed_degradations=tuple(config.quality.allowed_degradations),
    )


def _record_quality_issue(
    degradation: str,
    message: str,
    allowed: set[str],
    reasons: list[str],
    warnings: list[str],
    degradations: set[str],
) -> None:
    degradations.add(degradation)
    if degradation in allowed:
        warnings.append(message)
    else:
        reasons.append(message)


def _symbol_diagnostics(
    config: DataConfig,
    native_data: Any,
    panels: dict[str, pd.DataFrame],
    *,
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    symbols = _native_symbols(native_data, fallback=config.symbols)
    diagnostics = []
    for symbol in symbols:
        feature_diagnostics = {}
        for feature in config.effective_arrays:
            panel = panels.get(feature)
            if panel is None or symbol not in panel.columns:
                feature_diagnostics[feature] = {"available": False}
                continue
            series = panel[symbol]
            missing_count = int(series.isna().sum())
            row_count = len(series)
            feature_diagnostics[feature] = {
                "available": True,
                "rows": row_count,
                "missing": missing_count,
                "coverage": (row_count - missing_count) / row_count if row_count else 0,
                "numeric": bool(pd.api.types.is_numeric_dtype(series)),
                "first_timestamp": str(series.index[0]) if row_count else None,
                "last_timestamp": str(series.index[-1]) if row_count else None,
            }
        diagnostics.append(
            {
                "symbol": str(symbol),
                "configured": symbol in config.symbols,
                "features": feature_diagnostics,
                "index_evidence": evidence,
                "provider_status": "loaded",
            }
        )
    for symbol in config.symbols:
        if symbol not in symbols:
            diagnostics.append(
                {
                    "symbol": symbol,
                    "configured": True,
                    "features": {},
                    "index_evidence": evidence,
                    "provider_status": "skipped",
                }
            )
    return diagnostics


def _data_metadata(
    config: DataConfig,
    native_data: Any,
    panels: dict[str, pd.DataFrame],
    *,
    diagnostics: list[dict[str, Any]],
    quality: MarketDataQuality,
    source_metadata: dict[str, Any],
    evidence: dict[str, Any],
    required_features: tuple[str, ...],
) -> dict[str, Any]:
    index = _native_index(native_data)
    features = _native_features(native_data)
    symbols = _native_symbols(native_data, fallback=config.symbols)
    provider_metadata = _safe_native_data_metadata(native_data, source=config.source)
    metadata: dict[str, Any] = {
        "schema_version": "market_data.v2",
        "source": config.source,
        "provider_class": type(native_data).__name__,
        "native_class": type(native_data).__name__,
        "requested_symbols": list(config.symbols),
        "symbols": symbols,
        "features": features,
        "canonical_features": list(panels),
        "authored_arrays": to_builtin(config.arrays),
        "effective_arrays": list(config.effective_arrays),
        "required_arrays": list(required_features),
        "loaded_arrays": list(panels),
        "unavailable_arrays": [feature for feature in required_features if feature not in panels],
        "timeframe": config.timeframe,
        "shape": {
            "rows": len(index),
            "symbols": len(symbols),
            "features": len(features),
            "columns": len(symbols) * len(features),
        },
        "ohlc_available": {feature: feature in panels for feature in OHLCV_FEATURES},
        "index_start": str(index[0]) if len(index) else None,
        "index_end": str(index[-1]) if len(index) else None,
        "missing_index": config.missing_index,
        "missing_columns": config.missing_columns,
        "tz_localize": config.tz_localize,
        "tz_convert": config.tz_convert,
        "skip_on_error": config.skip_on_error,
        "silence_warnings": config.silence_warnings,
        "quality": quality.to_metadata(),
        "diagnostics": diagnostics,
        "source_metadata": source_metadata,
        "index_evidence": evidence,
        "provider_metadata": provider_metadata["metadata"],
        "omitted_metadata_fields": provider_metadata["omitted"],
        "update_supported": _supports_update(native_data),
        "cache_policy": "disabled_in_schema_v2",
    }
    return to_builtin(metadata)


def _native_index(native_data: Any) -> pd.Index:
    if hasattr(native_data, "index"):
        return native_data.index
    if isinstance(native_data, pd.DataFrame):
        return native_data.index
    if hasattr(native_data, "get"):
        values = native_data.get()
        if isinstance(values, (pd.Series, pd.DataFrame)):
            return values.index
    return pd.Index([])


def _native_features(native_data: Any) -> list[str]:
    if hasattr(native_data, "features"):
        return list(map(str, native_data.features))
    if isinstance(native_data, pd.DataFrame):
        return _frame_features(native_data)
    if hasattr(native_data, "get"):
        values = native_data.get()
        if isinstance(values, pd.DataFrame):
            return _frame_features(values)
    return []


def _frame_features(frame: pd.DataFrame) -> list[str]:
    if isinstance(frame.columns, pd.MultiIndex):
        values = frame.columns.get_level_values(
            "feature" if "feature" in frame.columns.names else -1
        )
        return sorted(set(map(str, values)))
    return list(map(str, frame.columns))


def _native_symbols(native_data: Any, *, fallback: list[str]) -> list[str]:
    if hasattr(native_data, "symbols"):
        return list(map(str, native_data.symbols))
    if isinstance(native_data, pd.DataFrame) and isinstance(native_data.columns, pd.MultiIndex):
        level = "symbol" if "symbol" in native_data.columns.names else 0
        return sorted(set(map(str, native_data.columns.get_level_values(level))))
    return list(fallback)


def _safe_native_data_metadata(native_object: Any, *, source: str) -> dict[str, Any]:
    omitted: list[dict[str, str]] = []
    metadata: dict[str, Any] = {}
    for name in (
        "last_index",
        "delisted",
        "missing_index",
        "missing_columns",
        "tz_localize",
        "tz_convert",
        "freq",
    ):
        if hasattr(native_object, name):
            _project_safe_field(metadata, omitted, name, getattr(native_object, name))
    for name, allowed_keys in (
        ("fetch_kwargs", SAFE_FETCH_KWARG_KEYS),
        ("returned_kwargs", SAFE_RETURNED_KWARG_KEYS),
    ):
        if hasattr(native_object, name):
            projected = _project_provider_mapping(
                getattr(native_object, name),
                allowed_keys=allowed_keys,
                omitted=omitted,
                path=name,
            )
            if projected:
                metadata[name] = projected
    metadata["source"] = source
    metadata["class"] = f"{type(native_object).__module__}.{type(native_object).__qualname__}"
    return {"metadata": metadata, "omitted": omitted}


def _project_safe_field(
    target: dict[str, Any],
    omitted: list[dict[str, str]],
    name: str,
    value: Any,
) -> None:
    projected = _safe_public_value(value, omitted=omitted, path=name)
    if projected is not _OMITTED:
        target[name] = projected


def _project_provider_mapping(
    value: Any,
    *,
    allowed_keys: set[str],
    omitted: list[dict[str, str]],
    path: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        omitted.append({"path": path, "reason": "not a mapping"})
        return {}
    projected: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        child_path = f"{path}.{key_text}"
        if SECRET_KEY_RE.search(key_text) or key_text.lower() in DENIED_PASSTHROUGH_KEYS:
            omitted.append({"path": child_path, "reason": "secret-like or denied key"})
            continue
        if key_text not in allowed_keys:
            omitted.append({"path": child_path, "reason": "field is not allowlisted"})
            continue
        safe_value = _safe_public_value(item, omitted=omitted, path=child_path)
        if safe_value is not _OMITTED:
            projected[key_text] = safe_value
    return projected


class _Omitted:
    pass


_OMITTED = _Omitted()


def _safe_public_value(value: Any, *, omitted: list[dict[str, str]], path: str) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return to_builtin(value)
    if isinstance(value, pd.Timestamp):
        return str(value)
    if isinstance(value, str):
        if SECRET_VALUE_RE.search(value):
            omitted.append({"path": path, "reason": "secret-like value"})
            return _OMITTED
        if _is_absolute_or_user_path(value):
            omitted.append({"path": path, "reason": "non-portable absolute path"})
            return _OMITTED
        return value
    if isinstance(value, dict):
        projected = {}
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if SECRET_KEY_RE.search(key_text) or key_text.lower() in DENIED_PASSTHROUGH_KEYS:
                omitted.append({"path": child_path, "reason": "secret-like or denied key"})
                continue
            safe_value = _safe_public_value(item, omitted=omitted, path=child_path)
            if safe_value is not _OMITTED:
                projected[key_text] = safe_value
        return projected
    if isinstance(value, list | tuple):
        projected = []
        for index, item in enumerate(value):
            safe_value = _safe_public_value(item, omitted=omitted, path=f"{path}[{index}]")
            if safe_value is not _OMITTED:
                projected.append(safe_value)
        return projected
    omitted.append({"path": path, "reason": f"unsupported type {type(value).__name__}"})
    return _OMITTED


def _supports_update(native_data: Any) -> bool:
    if getattr(native_data, "feature_oriented", False):
        return _overrides_vectorbt_update_method(native_data, "update_feature")
    if hasattr(native_data, "symbol_oriented") or hasattr(native_data, "symbols"):
        return _overrides_vectorbt_update_method(native_data, "update_symbol")
    return _overrides_vectorbt_update_method(native_data, "update")


def _overrides_vectorbt_update_method(native_data: Any, method_name: str) -> bool:
    method = getattr(type(native_data), method_name, None)
    base_method = getattr(vbt.Data, method_name, None)
    return callable(getattr(native_data, method_name, None)) and method is not base_method


def _index_evidence(index: pd.Index, *, source: str) -> dict[str, Any]:
    return {
        "source": source,
        "raw_rows": len(index),
        "raw_index_start": str(index[0]) if len(index) else None,
        "raw_index_end": str(index[-1]) if len(index) else None,
        "raw_index_has_duplicates": bool(index.has_duplicates),
        "raw_index_monotonic_increasing": bool(index.is_monotonic_increasing),
        "raw_index_timezone": str(index.tz)
        if isinstance(index, pd.DatetimeIndex) and index.tz
        else None,
    }


def _synthetic_data(config: DataConfig) -> Any:
    rng = np.random.default_rng(config.seed)
    index = pd.date_range(
        config.start or "2020-01-01",
        periods=config.rows,
        freq=config.timeframe,
        tz="UTC",
        name="Open time",
    )
    feature_values: dict[str, dict[str, np.ndarray]] = {feature: {} for feature in OHLCV_FEATURES}
    for symbol_idx, symbol in enumerate(config.symbols):
        drift = 0.00015 + symbol_idx * 0.00003
        volatility = 0.015 + symbol_idx * 0.002
        returns = rng.normal(drift, volatility, size=config.rows)
        close = 100 * np.cumprod(1 + returns)
        spread = np.abs(rng.normal(0.002, 0.001, size=config.rows))
        open_ = close * (1 + rng.normal(0, 0.001, size=config.rows))
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        volume = rng.lognormal(mean=12, sigma=0.25, size=config.rows)
        feature_values["Open"][symbol] = open_
        feature_values["High"][symbol] = high
        feature_values["Low"][symbol] = low
        feature_values["Close"][symbol] = close
        feature_values["Volume"][symbol] = volume
    return _native_from_feature_data(
        {
            feature: pd.DataFrame(values, index=index, columns=config.symbols)
            for feature, values in feature_values.items()
        },
        config,
    )


def _native_from_feature_data(feature_data: dict[str, pd.DataFrame], config: DataConfig) -> Any:
    return vbt.Data.from_data(
        vbt.feature_dict(feature_data),
        columns_are_symbols=True,
        missing_index=config.missing_index,
        missing_columns=config.missing_columns,
        tz_localize=config.tz_localize,
        tz_convert=config.tz_convert,
    )
