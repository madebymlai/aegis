from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from warnings import warn

import numpy as np
import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.configuration.schema import (
    DataConfig,
    SignalConfig,
    has_data_array_token_shape,
)
from research.aegis_research.configuration.secrets import (
    redact_text,
    resolve_secret_refs,
    to_builtin,
)
from research.aegis_research.data_arrays import merge_data_arrays
from research.aegis_research.market_data import panels as _panels
from research.aegis_research.market_data import safety as _safety
from research.aegis_research.market_data.contracts import (
    OHLCV_FEATURES,
    QUALITY_DEGRADED_ALLOWED,
    QUALITY_HEALTHY,
    QUALITY_PROVIDER_FAILED,
    QUALITY_REJECTED,
    DataDiagnostics,
    DataFeatureDiagnostics,
    MarketDataAdapter,
    MarketDataAdapterResult,
    MarketDataQuality,
    MarketDataResult,
    RemoteDataPullError,
)
from research.aegis_research.market_data.sources import (
    vbt_data_source_classes,
)

assert_public_metadata_safe = _safety.assert_public_metadata_safe
close_from_ohlcv = _panels.close_from_ohlcv
feature_from_ohlcv = _panels.feature_from_ohlcv
high_from_ohlcv = _panels.high_from_ohlcv
low_from_ohlcv = _panels.low_from_ohlcv

__all__ = [
    "assert_public_metadata_safe",
    "close_from_ohlcv",
    "feature_from_ohlcv",
    "high_from_ohlcv",
    "load_market_data",
    "load_market_data_result",
    "low_from_ohlcv",
    "required_experiment_ohlcv_features",
    "required_ohlcv_features",
]


@dataclass(frozen=True)
class MarketDataObservation:
    index: pd.Index
    features: tuple[str, ...]
    symbols: tuple[str, ...]
    panels: dict[str, pd.DataFrame]


_MISSING = object()


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
    observation = _observe_market_data(config, adapter_result.native_data, requested)
    diagnostics = _symbol_diagnostics(config, observation, evidence=adapter_result.evidence)
    quality = _quality_from_diagnostics(
        config,
        diagnostics,
        required_features=required,
    )
    metadata = _data_metadata(
        config,
        adapter_result.native_data,
        observation,
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
        diagnostics=diagnostics,
        quality=quality,
        known_secrets=adapter_result.known_secrets,
    )


def _provider_failed_result(
    config: DataConfig,
    error: RemoteDataPullError,
    *,
    required_features: tuple[str, ...],
) -> MarketDataResult:
    diagnostics = tuple(
        DataDiagnostics(
            symbol=symbol,
            configured=True,
            features={},
            index_evidence={"source": "provider_failed"},
            provider_status=QUALITY_PROVIDER_FAILED,
        )
        for symbol in config.symbols
    )
    quality = _quality_from_diagnostics(
        config,
        diagnostics,
        required_features=required_features,
    )
    reason = quality.reasons[0] if quality.reasons else quality.state
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
        "diagnostics": _diagnostics_metadata(diagnostics),
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
    feature_data: dict[str, pd.DataFrame] = {}
    for feature in _csv_feature_candidates(map(str, frame.columns), config):
        if feature in frame.columns:
            panel = frame.loc[:, [feature]].copy()
            panel.columns = pd.Index([symbol] * len(panel.columns), name=frame.columns.name)
            feature_data[feature] = panel
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


def _quality_from_diagnostics(
    config: DataConfig,
    diagnostics: tuple[DataDiagnostics, ...],
    *,
    required_features: tuple[str, ...],
) -> MarketDataQuality:
    reasons: list[str] = []
    warnings: list[str] = []
    degradations: set[str] = set()
    allowed = set(config.quality.allowed_degradations)

    provider_failed = [
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.configured and diagnostic.provider_status == QUALITY_PROVIDER_FAILED
    ]
    if provider_failed:
        return MarketDataQuality(
            state=QUALITY_PROVIDER_FAILED,
            reasons=(f"{config.source} provider failed before usable native data was available",),
            allowed_degradations=tuple(config.quality.allowed_degradations),
        )

    skipped_symbols = [
        diagnostic.symbol
        for diagnostic in diagnostics
        if diagnostic.configured and diagnostic.provider_status == "skipped"
    ]
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

    index_evidence = _combined_index_evidence(diagnostics)
    if index_evidence.get("raw_index_has_duplicates"):
        _record_quality_issue(
            "duplicate_index",
            "raw data index contains duplicate timestamps",
            allowed,
            reasons,
            warnings,
            degradations,
        )
    if index_evidence.get("raw_index_monotonic_increasing") is False:
        _record_quality_issue(
            "non_monotonic_index",
            "raw data index is not monotonic increasing",
            allowed,
            reasons,
            warnings,
            degradations,
        )

    configured_diagnostics = [
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.configured and diagnostic.symbol not in allowed_skipped_symbols
    ]
    for feature in required_features:
        feature_diagnostics = [
            (diagnostic, diagnostic.features.get(feature))
            for diagnostic in configured_diagnostics
        ]
        available = [
            (diagnostic, feature_diagnostic)
            for diagnostic, feature_diagnostic in feature_diagnostics
            if feature_diagnostic is not None and feature_diagnostic.available
        ]
        if not available:
            reasons.append(f"required feature {feature!r} is unavailable")
            continue
        if all(feature_diagnostic.rows == 0 for _, feature_diagnostic in available):
            reasons.append(f"required feature {feature!r} is empty")
            continue
        missing_required_symbols = [
            diagnostic.symbol
            for diagnostic, feature_diagnostic in feature_diagnostics
            if feature_diagnostic is None or not feature_diagnostic.available
        ]
        if missing_required_symbols:
            reasons.append(
                f"required feature {feature!r} is missing symbols {missing_required_symbols}"
            )
        if any(feature_diagnostic.missing > 0 for _, feature_diagnostic in available):
            _record_quality_issue(
                "missing_rows",
                f"required feature {feature!r} contains missing values",
                allowed,
                reasons,
                warnings,
                degradations,
            )
        non_numeric = [
            diagnostic.symbol
            for diagnostic, feature_diagnostic in available
            if feature_diagnostic.numeric is False
        ]
        if non_numeric:
            reasons.append(f"required feature {feature!r} has non-numeric symbols {non_numeric}")

    if reasons:
        state = QUALITY_REJECTED
    elif degradations & allowed:
        state = QUALITY_DEGRADED_ALLOWED
    else:
        state = QUALITY_HEALTHY
    return MarketDataQuality(
        state=state,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        allowed_degradations=tuple(config.quality.allowed_degradations),
    )


def _combined_index_evidence(diagnostics: tuple[DataDiagnostics, ...]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for diagnostic in diagnostics:
        if diagnostic.index_evidence.get("raw_index_has_duplicates"):
            evidence["raw_index_has_duplicates"] = True
        if diagnostic.index_evidence.get("raw_index_monotonic_increasing") is False:
            evidence["raw_index_monotonic_increasing"] = False
    return evidence


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
    observation: MarketDataObservation,
    *,
    evidence: dict[str, Any],
) -> tuple[DataDiagnostics, ...]:
    diagnostics: list[DataDiagnostics] = []
    panels = observation.panels
    observed_symbols = set(observation.symbols)
    for symbol in observation.symbols:
        diagnostics.append(
            DataDiagnostics(
                symbol=str(symbol),
                configured=symbol in config.symbols,
                features=_feature_diagnostics(
                    panels,
                    symbol=symbol,
                    features=config.effective_arrays,
                ),
                index_evidence=evidence,
                provider_status="loaded",
            )
        )
    for symbol in config.symbols:
        if symbol not in observed_symbols:
            diagnostics.append(
                DataDiagnostics(
                    symbol=symbol,
                    configured=True,
                    features={},
                    index_evidence=evidence,
                    provider_status="skipped",
                )
            )
    return tuple(diagnostics)


def _feature_diagnostics(
    panels: dict[str, pd.DataFrame],
    *,
    symbol: str,
    features: tuple[str, ...],
) -> dict[str, DataFeatureDiagnostics]:
    diagnostics: dict[str, DataFeatureDiagnostics] = {}
    for feature in features:
        panel = panels.get(feature)
        if panel is None or symbol not in panel.columns:
            diagnostics[feature] = DataFeatureDiagnostics(available=False)
            continue
        diagnostics[feature] = _available_feature_diagnostics(panel[symbol])
    return diagnostics


def _available_feature_diagnostics(series: pd.Series) -> DataFeatureDiagnostics:
    missing_count = int(series.isna().sum())
    row_count = len(series)
    return DataFeatureDiagnostics(
        available=True,
        rows=row_count,
        missing=missing_count,
        coverage=(row_count - missing_count) / row_count if row_count else 0,
        numeric=bool(pd.api.types.is_numeric_dtype(series)),
        first_timestamp=str(series.index[0]) if row_count else None,
        last_timestamp=str(series.index[-1]) if row_count else None,
    )


def _data_metadata(
    config: DataConfig,
    native_data: Any,
    observation: MarketDataObservation,
    *,
    diagnostics: tuple[DataDiagnostics, ...],
    quality: MarketDataQuality,
    source_metadata: dict[str, Any],
    evidence: dict[str, Any],
    required_features: tuple[str, ...],
) -> dict[str, Any]:
    index = observation.index
    features = list(observation.features)
    symbols = list(observation.symbols)
    panels = observation.panels
    provider_metadata = _safety.safe_native_data_metadata(native_data, source=config.source)
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
        "diagnostics": _diagnostics_metadata(diagnostics),
        "source_metadata": source_metadata,
        "index_evidence": evidence,
        "provider_metadata": provider_metadata["metadata"],
        "omitted_metadata_fields": provider_metadata["omitted"],
        "update_supported": _safety.supports_update(native_data),
        "cache_policy": "disabled_in_schema_v2",
    }
    return to_builtin(metadata)


def _observe_market_data(
    config: DataConfig,
    native_data: Any,
    requested_features: tuple[str, ...],
) -> MarketDataObservation:
    index = _optional_attr(native_data, "index")
    features = _optional_attr(native_data, "features")
    symbols = _optional_attr(native_data, "symbols")
    values = None
    if index is _MISSING or features is _MISSING or symbols is _MISSING:
        values = _native_values(native_data)
    return MarketDataObservation(
        index=_observed_index(index, values),
        features=tuple(_observed_features(features, values)),
        symbols=tuple(_observed_symbols(symbols, values, fallback=config.symbols)),
        panels=_observed_feature_panels(native_data, requested_features, values=values),
    )


def _optional_attr(native_data: Any, name: str) -> Any:
    try:
        return getattr(native_data, name)
    except AttributeError:
        return _MISSING


def _native_values(native_data: Any) -> Any:
    if isinstance(native_data, pd.DataFrame | pd.Series):
        return native_data
    getter = getattr(native_data, "get", None)
    if callable(getter):
        return getter()
    return None


def _observed_index(index: Any, values: Any) -> pd.Index:
    if index is not _MISSING:
        return index
    if isinstance(values, (pd.Series, pd.DataFrame)):
        return values.index
    return pd.Index([])


def _observed_features(features: Any, values: Any) -> list[str]:
    if features is not _MISSING and features is not None:
        return list(map(str, features))
    if isinstance(values, pd.DataFrame):
        return _frame_features(values)
    return []


def _observed_symbols(symbols: Any, values: Any, *, fallback: list[str]) -> list[str]:
    if symbols is not _MISSING and symbols is not None:
        return list(map(str, symbols))
    if isinstance(values, pd.DataFrame) and isinstance(values.columns, pd.MultiIndex):
        level = "symbol" if "symbol" in values.columns.names else 0
        return sorted(set(map(str, values.columns.get_level_values(level))))
    return list(fallback)


def _observed_feature_panels(
    native_data: Any,
    requested_features: tuple[str, ...],
    *,
    values: Any,
) -> dict[str, pd.DataFrame]:
    if isinstance(values, pd.DataFrame):
        return _frame_feature_panels(values, requested_features)
    if isinstance(values, pd.Series):
        return _series_feature_panels(values, requested_features)
    return _panels.available_feature_panels(native_data, requested_features)


def _frame_feature_panels(
    values: pd.DataFrame,
    requested_features: tuple[str, ...],
) -> dict[str, pd.DataFrame]:
    panels = {}
    for feature in requested_features:
        try:
            panels[feature] = _panels.feature_from_frame(values, feature)
        except (KeyError, ValueError, TypeError):
            continue
    return panels


def _series_feature_panels(
    values: pd.Series,
    requested_features: tuple[str, ...],
) -> dict[str, pd.DataFrame]:
    if str(values.name) not in requested_features:
        return {}
    return {str(values.name): _panels.as_panel(values, role=str(values.name))}


def _diagnostics_metadata(diagnostics: tuple[DataDiagnostics, ...]) -> list[dict[str, Any]]:
    return [diagnostic.to_metadata() for diagnostic in diagnostics]


def _native_index(native_data: Any) -> pd.Index:
    try:
        return native_data.index
    except AttributeError:
        pass
    if isinstance(native_data, pd.DataFrame):
        return native_data.index
    if callable(getattr(native_data, "get", None)):
        values = native_data.get()
        if isinstance(values, (pd.Series, pd.DataFrame)):
            return values.index
    return pd.Index([])


def _native_features(native_data: Any) -> list[str]:
    try:
        features = native_data.features
    except AttributeError:
        features = None
    if features is not None:
        return list(map(str, features))
    if isinstance(native_data, pd.DataFrame):
        return _frame_features(native_data)
    if callable(getattr(native_data, "get", None)):
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
    try:
        symbols = native_data.symbols
    except AttributeError:
        symbols = None
    if symbols is not None:
        return list(map(str, symbols))
    if isinstance(native_data, pd.DataFrame) and isinstance(native_data.columns, pd.MultiIndex):
        level = "symbol" if "symbol" in native_data.columns.names else 0
        return sorted(set(map(str, native_data.columns.get_level_values(level))))
    return list(fallback)


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
            feature: pd.DataFrame(values, index=index, columns=pd.Index(config.symbols))
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
