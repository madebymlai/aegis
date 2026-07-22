"""Deep Run-facing market-data loading operation."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from aegis_data.array_names import is_bar_derived_array
from aegis_data.catalog import (
    CatalogBackedDataPort,
    CatalogCoverageGapError,
    CatalogWindow,
    CatalogWindowRequest,
    GapFillProviderError,
    resolve_catalog_path,
)
from aegis_data.continuous_contract_model import ContinuousContractModel
from aegis_data.continuous_future import DEFAULT_ADJUSTMENT_MODE
from aegis_data.custom_data import (
    CustomDataCoverageError,
    CustomDataProviderMap,
    ensure_arrays,
)
from aegis_data.custom_data import (
    arrays as custom_arrays,
)
from aegis_data.distributions import Distribution
from aegis_runtime import MarketDataBundle
from aegis_runtime.currency import CurrencyConversion, build_currency_conversion_from_codes
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId
from vectorbtpro import vbt

from research.aegis_research.configuration import DataConfig
from research.aegis_research.instrument_resolution import (
    InstrumentResolution,
    TradeableInstrument,
    resolve_instruments,
)


class RunDataValidationError(ValueError):
    """The authored Run data contract cannot produce usable Run data."""


class ContinuousRootCollisionError(RunDataValidationError):
    """A synthetic continuous-root id collides with a native Instrument id."""


@dataclass(frozen=True)
class RunDataFailureEvidence:
    schema_version: str
    requested_instrument_ids: tuple[InstrumentId, ...]
    timeframe: str
    start: str
    end: str
    error_type: str
    message: str
    source: str


class RunDataUnavailable(RuntimeError):
    """The Catalog cannot environmentally serve the requested Run data."""

    def __init__(self, evidence: RunDataFailureEvidence) -> None:
        self.evidence = evidence
        super().__init__(evidence.message)


@dataclass(frozen=True)
class RunDataEvidence:
    schema_version: str
    requested_instrument_ids: tuple[InstrumentId, ...]
    tradeables: tuple[TradeableInstrument, ...]
    loaded_arrays: tuple[str, ...]
    timeframe: str
    start: str
    end: str
    missing_index: str
    rows: int
    index_start: str
    index_end: str
    source: str
    catalog_path: str | None
    currency_by_instrument_id: dict[InstrumentId, str]
    continuous_root_currencies: dict[InstrumentId, str]
    size_increment_by_instrument: dict[InstrumentId, float]
    distribution_coverage: tuple[dict[str, object], ...]
    adjustment_mode: str | None


@dataclass(frozen=True)
class RunData:
    bundle: MarketDataBundle
    instrument_resolution: InstrumentResolution
    currency_conversion: CurrencyConversion
    distributions: tuple[Distribution, ...]
    size_increment_by_instrument: dict[InstrumentId, float]
    adjustment_mode: ContinuousFutureAdjustmentType | None
    evidence: RunDataEvidence


def load_run_data(
    config: DataConfig,
    *,
    required_arrays: tuple[str, ...],
    port: CatalogBackedDataPort,
    custom_data_providers: CustomDataProviderMap | None,
) -> RunData:
    """Load one coherent catalog window into usable, eager Run data."""
    start = _required_edge(config.start, "start")
    end = _required_edge(config.end, "end")
    _assert_required_arrays_configured(config, required_arrays)
    resolution = resolve_instruments(config, port=port)
    requested_ids = tuple(InstrumentId.from_str(value) for value in config.native_instrument_ids)
    try:
        window = port.load_window(
            CatalogWindowRequest(
                instrument_ids=requested_ids,
                start=start,
                end=end,
                timeframe=config.timeframe,
            )
        )
    except (CatalogCoverageGapError, GapFillProviderError) as error:
        _raise_unavailable(error, config, requested_ids, start=start, end=end)
    adjustment_mode: ContinuousFutureAdjustmentType | None = (
        DEFAULT_ADJUSTMENT_MODE if config.futures else None
    )
    try:
        continuous_frames, continuous_currencies = _continuous_frames(
            port,
            config.futures,
            start=start,
            end=end,
            timeframe=config.timeframe,
            adjustment_mode=adjustment_mode,
        )
        continuous_coverage = (
            port.distribution_coverage_report(
                tuple(continuous_frames), start=start, end=end
            )
            if continuous_frames
            else ()
        )
    except (CatalogCoverageGapError, GapFillProviderError) as error:
        _raise_unavailable(error, config, requested_ids, start=start, end=end)
    collisions = set(window.ohlcv) & set(continuous_frames)
    if collisions:
        raise ContinuousRootCollisionError(
            "continuous-future root ids collide with raw instrument ids: "
            f"{sorted(instrument_id.value for instrument_id in collisions)}"
        )
    frames = {**window.ohlcv, **continuous_frames}
    try:
        native_bundle = _native_bundle(
            config,
            required_arrays,
            resolution,
            frames,
            custom_data_providers=custom_data_providers,
        )
    except (CustomDataCoverageError, GapFillProviderError) as error:
        _raise_unavailable(error, config, requested_ids, start=start, end=end)
    currency_conversion = _catalog_currency_conversion(
        config,
        resolution,
        window,
        frames,
        continuous_currencies,
    )
    bundle = MarketDataBundle(currency_conversion.apply(native_bundle.arrays))
    size_increments = _size_increments(resolution, window, port)
    index = next(iter(bundle.arrays.values())).index
    return RunData(
        bundle=bundle,
        instrument_resolution=resolution,
        currency_conversion=currency_conversion,
        distributions=window.distributions,
        size_increment_by_instrument=size_increments,
        adjustment_mode=adjustment_mode,
        evidence=RunDataEvidence(
            schema_version="run_data.v1",
            requested_instrument_ids=requested_ids,
            tradeables=resolution.tradeables,
            loaded_arrays=tuple(bundle.arrays),
            timeframe=config.timeframe,
            start=start,
            end=end,
            missing_index=config.missing_index,
            rows=len(index),
            index_start=str(index[0]),
            index_end=str(index[-1]),
            source="nautilus_catalog",
            catalog_path=config.path,
            currency_by_instrument_id=dict(currency_conversion.currency_by_instrument_id),
            continuous_root_currencies=continuous_currencies,
            size_increment_by_instrument=size_increments,
            distribution_coverage=(*window.distribution_coverage, *continuous_coverage),
            adjustment_mode=adjustment_mode.value if adjustment_mode is not None else None,
        ),
    )


def _catalog_currency_conversion(
    config: DataConfig,
    resolution: InstrumentResolution,
    window: CatalogWindow,
    frames: dict[InstrumentId, pd.DataFrame],
    continuous_currencies: dict[InstrumentId, str],
) -> CurrencyConversion:
    exchange_ids = tuple(InstrumentId.from_str(value) for value in config.exchange)
    native_ids = tuple(
        tradeable.instrument_id
        for tradeable in resolution.tradeables
        if tradeable.continuous_root is None
    )
    return build_currency_conversion_from_codes(
        currency_by_instrument_id={
            **{
                instrument_id: window.instruments[instrument_id].quote_currency.code
                for instrument_id in native_ids
            },
            **continuous_currencies,
        },
        pair_currencies={
            instrument_id: (
                window.instruments[instrument_id].base_currency.code,
                window.instruments[instrument_id].quote_currency.code,
            )
            for instrument_id in exchange_ids
        },
        fx_close={
            instrument_id: frames[instrument_id]["Close"] for instrument_id in exchange_ids
        },
        base_currency=config.base_currency,
    )


def _continuous_frames(
    port: CatalogBackedDataPort,
    roots: tuple[str, ...] | list[str],
    *,
    start: str,
    end: str,
    timeframe: str,
    adjustment_mode: ContinuousFutureAdjustmentType | None,
) -> tuple[dict[InstrumentId, pd.DataFrame], dict[InstrumentId, str]]:
    frames: dict[InstrumentId, pd.DataFrame] = {}
    currencies: dict[InstrumentId, str] = {}
    for root in roots:
        assert adjustment_mode is not None
        model = ContinuousContractModel(
            port,
            root,
            start=start,
            timeframe=timeframe,
            adjustment_mode=adjustment_mode,
        )
        model.materialize(end=end)
        frames[model.continuous_id] = model.frame
        currencies[model.continuous_id] = model.quote_currency
    return frames, currencies


def _size_increments(
    resolution: InstrumentResolution,
    window: CatalogWindow,
    port: CatalogBackedDataPort,
) -> dict[InstrumentId, float]:
    increments: dict[InstrumentId, float] = {}
    for tradeable in resolution.tradeables:
        increments[tradeable.instrument_id] = (
            window.size_increment_by_instrument[tradeable.instrument_id]
            if tradeable.continuous_root is None
            else port.continuous_size_increment(tradeable.continuous_root)
        )
    return increments


def _native_bundle(
    config: DataConfig,
    required_arrays: tuple[str, ...],
    resolution: InstrumentResolution,
    frames: dict[InstrumentId, pd.DataFrame],
    *,
    custom_data_providers: CustomDataProviderMap | None,
) -> MarketDataBundle:
    instrument_ids = resolution.instrument_ids
    index = _tradeable_index(config, frames, instrument_ids)
    panels = {
        array: pd.DataFrame(
            {instrument_id: frames[instrument_id][array] for instrument_id in instrument_ids}
        ).loc[index]
        for array in config.effective_arrays
        if is_bar_derived_array(array)
    }
    custom_names = tuple(
        array for array in config.effective_arrays if not is_bar_derived_array(array)
    )
    if custom_names:
        custom_index = pd.DatetimeIndex(index)
        catalog_path = resolve_catalog_path(config.path)
        ensure_arrays(
            dict.fromkeys(instrument_ids, custom_names),
            start=pd.Timestamp(custom_index[0]),
            end=pd.Timestamp(custom_index[-1]),
            providers=custom_data_providers or {},
            catalog_path=catalog_path,
        )
        panels.update(
            custom_arrays(
                custom_names,
                instrument_ids,
                index=custom_index,
                catalog_path=catalog_path,
            )
        )
    panels = {array: panels[array] for array in config.effective_arrays}
    _assert_usable(panels, required_arrays, instrument_ids)
    native = vbt.Data.from_data(
        vbt.feature_dict(panels),
        columns_are_symbols=True,
        missing_index=config.missing_index,
        missing_columns="raise",
        tz_localize=False,
        tz_convert=False,
    )
    return MarketDataBundle(arrays=native.data)


def _raise_unavailable(
    error: Exception,
    config: DataConfig,
    requested_ids: tuple[InstrumentId, ...],
    *,
    start: str,
    end: str,
) -> None:
    raise RunDataUnavailable(
        RunDataFailureEvidence(
            schema_version="run_data_failure.v1",
            requested_instrument_ids=requested_ids,
            timeframe=config.timeframe,
            start=start,
            end=end,
            error_type=type(error).__name__,
            message=str(error),
            source="nautilus_catalog",
        )
    ) from error


def _tradeable_index(
    config: DataConfig,
    frames: dict[InstrumentId, pd.DataFrame],
    instrument_ids: tuple[InstrumentId, ...],
) -> pd.Index:
    index = frames[instrument_ids[0]].index
    for instrument_id in instrument_ids[1:]:
        other = frames[instrument_id].index
        if config.missing_index == "drop":
            index = index.intersection(other)
        elif not index.equals(other):
            raise RunDataValidationError("tradeable Instruments have mismatching indexes")
    return index


def _assert_required_arrays_configured(
    config: DataConfig, required_arrays: tuple[str, ...]
) -> None:
    missing = [array for array in required_arrays if array not in config.effective_arrays]
    if missing:
        raise RunDataValidationError(f"data.arrays is missing required Arrays: {missing}")


def _assert_usable(
    panels: dict[str, pd.DataFrame],
    required_arrays: tuple[str, ...],
    instrument_ids: tuple[InstrumentId, ...],
) -> None:
    for array in required_arrays:
        if array not in panels:
            raise RunDataValidationError(f"required Array {array!r} was not loaded")
        panel = panels[array]
        if panel.empty:
            raise RunDataValidationError(f"required Array {array!r} is empty")
        if tuple(panel.columns) != instrument_ids:
            raise RunDataValidationError(
                f"required Array {array!r} has unexpected Instrument columns"
            )
        if panel.isna().to_numpy().any():
            raise RunDataValidationError(f"required Array {array!r} contains missing values")
        if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in panel.dtypes):
            raise RunDataValidationError(f"required Array {array!r} contains nonnumeric values")


def _required_edge(value: str | None, name: str) -> str:
    if value is None:
        raise RunDataValidationError(f"data.{name} is required")
    return value
