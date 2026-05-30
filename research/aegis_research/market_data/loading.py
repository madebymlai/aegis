from __future__ import annotations

from typing import Any

import pandas as pd

from research.aegis_research.configuration.schema import (
    DataConfig,
    SignalConfig,
)
from research.aegis_research.data_arrays import merge_data_arrays
from research.aegis_research.market_data import metadata as _metadata
from research.aegis_research.market_data import panels as _panels
from research.aegis_research.market_data import safety as _safety
from research.aegis_research.market_data.adapters import default_source_loaders
from research.aegis_research.market_data.contracts import (
    QUALITY_DEGRADED_ALLOWED,
    QUALITY_HEALTHY,
    QUALITY_PROVIDER_FAILED,
    QUALITY_REJECTED,
    DataDiagnostics,
    DataFeatureDiagnostics,
    MarketDataAdapter,
    MarketDataQuality,
    MarketDataResult,
    RemoteDataPullError,
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


MarketDataObservation = _metadata.MarketDataObservation


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
    source_loaders = {**default_source_loaders(), **(adapters or {})}
    if source not in source_loaders:
        raise ValueError(f"Unsupported data source: {config.source}")
    requested = config.effective_arrays
    required = merge_data_arrays(requested, required_features or ())

    try:
        adapter_result = source_loaders[source](config)
    except RemoteDataPullError as error:
        return _provider_failed_result(config, error, required_features=required)
    native_data = adapter_result.native_data
    observation = _observe_market_data(config, native_data, requested)
    diagnostics = _symbol_diagnostics(config, observation, evidence=adapter_result.evidence)
    quality = _quality_from_diagnostics(
        config,
        diagnostics,
        required_features=required,
    )
    metadata = _metadata.describe(
        config,
        native_class=_native_class(native_data),
        observation=observation,
        diagnostics=diagnostics,
        quality=quality,
        source_metadata=adapter_result.source_metadata,
        evidence=adapter_result.evidence,
        provider_metadata=adapter_result.provider_metadata,
        omitted_metadata_fields=adapter_result.omitted_metadata_fields,
        update_supported=_update_supported(native_data),
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
    metadata = _metadata.describe(
        config,
        native_class=None,
        observation=_empty_observation(),
        diagnostics=diagnostics,
        quality=quality,
        source_metadata={
            "provider_error_type": type(error).__name__,
            "provider_error_summary": reason,
        },
        evidence={"source": "provider_failed"},
        provider_metadata={},
        omitted_metadata_fields=[],
        update_supported=False,
        required_features=required_features,
    )
    assert_public_metadata_safe(metadata)
    return MarketDataResult(
        native_data=None,
        metadata=metadata,
        diagnostics=diagnostics,
        quality=quality,
    )


def _empty_observation() -> MarketDataObservation:
    return MarketDataObservation(index=pd.Index([]), features=(), symbols=(), panels={})


def _native_class(native_data: Any) -> str | None:
    if native_data is None:
        return None
    return type(native_data).__name__


def _update_supported(native_data: Any) -> bool:
    if native_data is None:
        return False
    return _safety.supports_update(native_data)


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


def _frame_features(frame: pd.DataFrame) -> list[str]:
    if isinstance(frame.columns, pd.MultiIndex):
        values = frame.columns.get_level_values(
            "feature" if "feature" in frame.columns.names else -1
        )
        return sorted(set(map(str, values)))
    return list(map(str, frame.columns))

