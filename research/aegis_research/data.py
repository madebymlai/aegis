from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Protocol

import numpy as np
import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import (
    DENIED_PASSTHROUGH_KEYS,
    SECRET_KEY_RE,
    SECRET_VALUE_RE,
    DataConfig,
    LabelConfig,
    redact_text,
    resolve_secret_refs,
    to_builtin,
)

OHLCV_FEATURES = ("Open", "High", "Low", "Close", "Volume")
LOGICAL_FEATURES = {
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "volume": "Volume",
}
QUALITY_HEALTHY = "healthy"
QUALITY_DEGRADED_ALLOWED = "degraded_allowed"
QUALITY_REJECTED = "rejected"
QUALITY_PROVIDER_FAILED = "provider_failed"
SAFE_FETCH_KWARG_KEYS = {
    "delay",
    "end",
    "exchange",
    "find_earliest_date",
    "klines_type",
    "limit",
    "period",
    "retries",
    "start",
    "timeframe",
    "tz",
}
SAFE_RETURNED_KWARG_KEYS = {"freq", "tz", "tz_convert", "tz_localize"}
REMOTE_DATA_CLASSES = {
    "yfinance": lambda: vbt.YFData,
    "binance": lambda: vbt.BinanceData,
    "ccxt": lambda: vbt.CCXTData,
}


class RemoteDataPullError(ValueError):
    def __init__(self, source: str, message: str) -> None:
        self.source = source
        super().__init__(f"Failed to pull {source} data: {message}")


class MarketDataQualityError(ValueError):
    def __init__(self, quality: MarketDataQuality) -> None:
        self.quality = quality
        details = "; ".join(quality.reasons) or quality.state
        super().__init__(f"Market data quality check failed: {details}")


class MarketDataAdapter(Protocol):
    def __call__(self, config: DataConfig) -> MarketDataAdapterResult: ...


@dataclass(frozen=True)
class MarketDataQuality:
    state: str
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    allowed_degradations: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return self.state in {QUALITY_HEALTHY, QUALITY_DEGRADED_ALLOWED}

    def to_metadata(self) -> dict[str, Any]:
        return to_builtin(asdict(self))


@dataclass(frozen=True)
class MarketDataAdapterResult:
    native_data: Any
    known_secrets: tuple[str, ...] = ()
    source_metadata: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketDataResult:
    native_data: Any
    metadata: dict[str, Any]
    diagnostics: tuple[dict[str, Any], ...]
    quality: MarketDataQuality
    known_secrets: tuple[str, ...] = ()

    def feature(self, feature: str) -> pd.DataFrame:
        return feature_from_ohlcv(self, feature)

    def assert_usable(self) -> None:
        if not self.quality.usable:
            raise MarketDataQualityError(self.quality)


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
    source = config.source.lower()
    registry = {**_default_adapters(), **(adapters or {})}
    if source not in registry:
        raise ValueError(f"Unsupported data source: {config.source}")

    try:
        adapter_result = registry[source](config)
    except RemoteDataPullError as error:
        return _provider_failed_result(config, error)
    required = required_features or ("Close",)
    panels = _available_feature_panels(adapter_result.native_data, config)
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
    )
    assert_public_metadata_safe(metadata, known_secrets=adapter_result.known_secrets)
    return MarketDataResult(
        native_data=adapter_result.native_data,
        metadata=metadata,
        diagnostics=tuple(diagnostics),
        quality=quality,
        known_secrets=adapter_result.known_secrets,
    )


def _provider_failed_result(config: DataConfig, error: RemoteDataPullError) -> MarketDataResult:
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
        "schema_version": "market_data.v1",
        "source": config.source,
        "provider_class": None,
        "native_class": None,
        "requested_symbols": list(config.symbols),
        "symbols": [],
        "features": [],
        "canonical_features": [],
        "feature_map": dict(config.feature_map),
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
        "cache_policy": "disabled_in_schema_v1",
    }
    metadata = to_builtin(metadata)
    assert_public_metadata_safe(metadata)
    return MarketDataResult(
        native_data=None,
        metadata=metadata,
        diagnostics=diagnostics,
        quality=quality,
    )


def required_ohlcv_features(label_config: LabelConfig | str | None = None) -> tuple[str, ...]:
    label_kind = label_config.kind if isinstance(label_config, LabelConfig) else label_config
    if label_kind in {"trendlb", "pivotlb"}:
        return ("Close", "High", "Low")
    return ("Close",)


def close_from_ohlcv(data: Any) -> pd.DataFrame:
    return feature_from_ohlcv(data, "Close")


def high_from_ohlcv(data: Any) -> pd.DataFrame:
    return feature_from_ohlcv(data, "High")


def low_from_ohlcv(data: Any) -> pd.DataFrame:
    return feature_from_ohlcv(data, "Low")


def feature_from_ohlcv(data: Any, feature: str) -> pd.DataFrame:
    if isinstance(data, MarketDataResult):
        data.assert_usable()
        return _canonical_feature_panel(
            data.native_data,
            feature,
            data.metadata.get("feature_map", {}),
        )
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
        if any(secret and secret in value for secret in known_secrets) or SECRET_VALUE_RE.search(value):
            raise ValueError(f"public data metadata contains secret material at {path}")
        if _looks_like_absolute_path(value):
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


def _default_adapters() -> dict[str, MarketDataAdapter]:
    return {
        "synthetic": _synthetic_adapter,
        "csv": _csv_adapter,
        "yfinance": lambda config: _remote_adapter("yfinance", REMOTE_DATA_CLASSES["yfinance"](), config),
        "binance": lambda config: _remote_adapter("binance", REMOTE_DATA_CLASSES["binance"](), config),
        "ccxt": lambda config: _remote_adapter("ccxt", REMOTE_DATA_CLASSES["ccxt"](), config),
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


def _synthetic_adapter(config: DataConfig) -> MarketDataAdapterResult:
    native_data = _synthetic_data(config)
    return MarketDataAdapterResult(
        native_data=native_data,
        source_metadata={"generated": True, "seed": config.seed, "rows": config.rows},
        evidence=_index_evidence(native_data.index, source="generated"),
    )


def _csv_adapter(config: DataConfig) -> MarketDataAdapterResult:
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


def _remote_adapter(source: str, data_cls, config: DataConfig) -> MarketDataAdapterResult:
    native_data, known_secrets = _pull_remote(data_cls, config)
    return MarketDataAdapterResult(
        native_data=native_data,
        known_secrets=known_secrets,
        source_metadata={"provider_class": f"{data_cls.__module__}.{data_cls.__qualname__}"},
        evidence=_index_evidence(_native_index(native_data), source="post_vectorbt_alignment"),
    )


def _read_csv(config: DataConfig) -> pd.DataFrame:
    flat = _localize_csv_index(pd.read_csv(Path(config.path or ""), index_col=0, parse_dates=True))
    if _flat_csv_has_features(flat, config):
        return flat
    try:
        multi = pd.read_csv(Path(config.path or ""), header=[0, 1], index_col=0, parse_dates=True)
    except (pd.errors.ParserError, ValueError):
        return flat
    multi = _localize_csv_index(multi)
    if isinstance(multi.columns, pd.MultiIndex) and not any(
        str(value).startswith("Unnamed") for value in multi.columns.get_level_values(1)
    ):
        return multi
    return flat


def _localize_csv_index(frame: pd.DataFrame) -> pd.DataFrame:
    if isinstance(frame.index, pd.DatetimeIndex) and frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC")
    return frame


def _flat_csv_has_features(frame: pd.DataFrame, config: DataConfig) -> bool:
    if isinstance(frame.columns, pd.MultiIndex):
        return False
    source_names = {_source_feature_name(feature, config.feature_map) for feature in OHLCV_FEATURES}
    return bool(set(map(str, frame.columns)) & source_names)


def _csv_feature_data(frame: pd.DataFrame, config: DataConfig) -> dict[str, pd.DataFrame]:
    if isinstance(frame.columns, pd.MultiIndex):
        return _multiindex_csv_feature_data(frame, config)
    return _flat_csv_feature_data(frame, config)


def _flat_csv_feature_data(frame: pd.DataFrame, config: DataConfig) -> dict[str, pd.DataFrame]:
    if len(config.symbols) != 1:
        raise ValueError("flat CSV OHLCV input requires exactly one configured symbol")
    symbol = config.symbols[0]
    feature_data = {}
    for feature in OHLCV_FEATURES:
        source_feature = _source_feature_name(feature, config.feature_map)
        if source_feature in frame.columns:
            feature_data[feature] = frame[[source_feature]].rename(columns={source_feature: symbol})
    if not feature_data:
        raise ValueError("CSV data must contain at least one OHLCV feature column")
    return feature_data


def _multiindex_csv_feature_data(frame: pd.DataFrame, config: DataConfig) -> dict[str, pd.DataFrame]:
    symbol_level, feature_level = _csv_multiindex_levels(frame, config)
    feature_data = {}
    for feature in OHLCV_FEATURES:
        source_feature = _source_feature_name(feature, config.feature_map)
        feature_values = set(map(str, frame.columns.get_level_values(feature_level)))
        if source_feature not in feature_values:
            continue
        panel = frame.xs(source_feature, axis=1, level=feature_level)
        if isinstance(panel.columns, pd.MultiIndex):
            panel.columns = panel.columns.get_level_values(symbol_level)
        panel = panel.loc[:, [symbol for symbol in config.symbols if symbol in panel.columns]]
        if not panel.empty:
            feature_data[feature] = panel
    if not feature_data:
        raise ValueError("CSV MultiIndex data must contain at least one mapped OHLCV feature")
    return feature_data


def _csv_multiindex_levels(frame: pd.DataFrame, config: DataConfig) -> tuple[int, int]:
    level_values = [set(map(str, frame.columns.get_level_values(index))) for index in range(frame.columns.nlevels)]
    symbol_levels = [index for index, values in enumerate(level_values) if set(config.symbols) & values]
    source_features = {_source_feature_name(feature, config.feature_map) for feature in OHLCV_FEATURES}
    feature_levels = [index for index, values in enumerate(level_values) if source_features & values]
    if not symbol_levels or not feature_levels:
        raise ValueError("CSV MultiIndex columns must include symbol and feature levels")
    symbol_level = symbol_levels[0]
    feature_level = next((level for level in feature_levels if level != symbol_level), feature_levels[0])
    if symbol_level == feature_level:
        raise ValueError("CSV MultiIndex symbol and feature levels must be distinct")
    return symbol_level, feature_level


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
        return (
            data_cls.pull(
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
                **provider_kwargs,
            ),
            tuple(secrets),
        )
    except Exception as error:
        error_message = redact_text(str(error), secrets)
    raise RemoteDataPullError(config.source, error_message)


def _available_feature_panels(native_data: Any, config: DataConfig) -> dict[str, pd.DataFrame]:
    panels = {}
    for feature in OHLCV_FEATURES:
        try:
            panels[feature] = _canonical_feature_panel(native_data, feature, config.feature_map)
        except (KeyError, ValueError, TypeError):
            continue
    return panels


def _canonical_feature_panel(
    native_data: Any,
    feature: str,
    feature_map: dict[str, str],
) -> pd.DataFrame:
    try:
        return _feature_panel(native_data, feature, role=feature)
    except (KeyError, ValueError, TypeError):
        source_feature = _source_feature_name(feature, feature_map)
        if source_feature == feature:
            raise
        return _feature_panel(native_data, source_feature, role=feature)


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
    allowed_skipped_symbols = set(skipped_symbols) if (
        config.skip_on_error and "skipped_symbols" in allowed
    ) else set()
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
        non_numeric = [symbol for symbol in panel.columns if not pd.api.types.is_numeric_dtype(panel[symbol])]
        if non_numeric:
            reasons.append(f"required feature {feature!r} has non-numeric symbols {non_numeric}")

    missing_optional = [feature for feature in OHLCV_FEATURES if feature not in required_features and feature not in panels]
    if missing_optional:
        warnings.append(f"optional OHLCV features unavailable: {missing_optional}")
        degradations.add("missing_optional_features")

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
        for feature in OHLCV_FEATURES:
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
) -> dict[str, Any]:
    index = _native_index(native_data)
    features = _native_features(native_data)
    symbols = _native_symbols(native_data, fallback=config.symbols)
    provider_metadata = _safe_native_data_metadata(native_data, source=config.source)
    metadata: dict[str, Any] = {
        "schema_version": "market_data.v1",
        "source": config.source,
        "provider_class": type(native_data).__name__,
        "native_class": type(native_data).__name__,
        "requested_symbols": list(config.symbols),
        "symbols": symbols,
        "features": features,
        "canonical_features": list(panels),
        "feature_map": dict(config.feature_map),
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
        "cache_policy": "disabled_in_schema_v1",
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
        values = frame.columns.get_level_values("feature" if "feature" in frame.columns.names else -1)
        return sorted(set(map(str, values)))
    return [feature for feature in OHLCV_FEATURES if feature in frame.columns]


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
        if _looks_like_absolute_path(value):
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


def _looks_like_absolute_path(value: str) -> bool:
    if "://" in value:
        return False
    if value == "~" or value.startswith("~"):
        return True
    try:
        return (
            Path(value).is_absolute()
            or PurePosixPath(value).is_absolute()
            or PureWindowsPath(value).is_absolute()
        )
    except ValueError:
        return False


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


def _source_feature_name(feature: str, feature_map: dict[str, str]) -> str:
    logical = feature.lower()
    return feature_map.get(logical, feature)


def _index_evidence(index: pd.Index, *, source: str) -> dict[str, Any]:
    return {
        "source": source,
        "raw_rows": len(index),
        "raw_index_start": str(index[0]) if len(index) else None,
        "raw_index_end": str(index[-1]) if len(index) else None,
        "raw_index_has_duplicates": bool(index.has_duplicates),
        "raw_index_monotonic_increasing": bool(index.is_monotonic_increasing),
        "raw_index_timezone": str(index.tz) if isinstance(index, pd.DatetimeIndex) and index.tz else None,
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
