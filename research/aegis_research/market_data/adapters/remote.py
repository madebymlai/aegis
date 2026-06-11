from __future__ import annotations

from typing import Any
from warnings import warn

import pandas as pd

from research.aegis_research.configuration import DataConfig, resolve_env_refs
from research.aegis_research.market_data import native_metadata as _native_metadata
from research.aegis_research.market_data.adapters._support import (
    index_evidence,
    native_index,
)
from research.aegis_research.market_data.contracts import (
    MarketDataAdapter,
    MarketDataAdapterResult,
    RemoteDataPullError,
)
from research.aegis_research.market_data.sources import vbt_data_source_classes

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
_REMOTE_PROVIDER_MAPPINGS = (
    ("fetch_kwargs", SAFE_FETCH_KWARG_KEYS),
    ("returned_kwargs", SAFE_RETURNED_KWARG_KEYS),
)


def remote_source_loaders() -> dict[str, MarketDataAdapter]:
    return {
        source: (
            lambda config, source=source, data_cls=data_cls: load_vbt_remote_source(
                source,
                data_cls,
                config,
            )
        )
        for source, data_cls in vbt_data_source_classes().items()
    }


def load_vbt_remote_source(source: str, data_cls, config: DataConfig) -> MarketDataAdapterResult:
    native_data = _pull_remote(data_cls, config)
    projected = _native_metadata.native_data_metadata(
        native_data,
        source=config.source,
        provider_mappings=_REMOTE_PROVIDER_MAPPINGS,
    )
    return MarketDataAdapterResult(
        native_data=native_data,
        source_metadata={"provider_class": f"{data_cls.__module__}.{data_cls.__qualname__}"},
        evidence=index_evidence(native_index(native_data), source="post_vectorbt_alignment"),
        provider_metadata=projected["metadata"],
        omitted_metadata_fields=projected["omitted"],
    )


def _pull_remote(data_cls, config: DataConfig) -> Any:
    wrapper_kwargs = resolve_env_refs(
        config.wrapper_kwargs,
        "data.wrapper_kwargs",
    )
    provider_kwargs = resolve_env_refs(
        config.provider_kwargs,
        "data.provider_kwargs",
    )
    execution_kwargs = resolve_env_refs(
        config.execution_kwargs,
        "data.execution_kwargs",
    )
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
        return _native_from_remote_raw_outputs(
            data_cls,
            config,
            raw_outputs,
            wrapper_kwargs=wrapper_kwargs,
            provider_kwargs=provider_kwargs,
        )
    except Exception as error:
        raise RemoteDataPullError(config.source, str(error)) from error


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
    requested_arrays: tuple[str, ...],
    *,
    symbol: str,
) -> pd.Series | pd.DataFrame:
    if isinstance(raw_data, pd.Series):
        if raw_data.name in requested_arrays:
            return raw_data
        return raw_data.iloc[0:0]
    if not isinstance(raw_data, pd.DataFrame):
        raise TypeError(
            f"remote provider returned non-tabular data for symbol {symbol!r}; "
            "configured data arrays require named feature columns"
        )
    columns = [name for name in requested_arrays if name in raw_data.columns]
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
                warn(
                    "Returned objects have different timezones (tz_convert). Setting to UTC.",
                    stacklevel=2,
                )
            common_tz_convert = "utc"
    if freq is not None:
        if common_freq is None:
            common_freq = freq
        elif common_freq != freq:
            raise ValueError("Returned objects have different frequencies (freq)")
    return common_tz_localize, common_tz_convert, common_freq
