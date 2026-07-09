"""Nautilus catalog-backed RD market-data adapter."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
from aegis_data.catalog import (
    CatalogBackedDataPort,
    RawBarRequest,
    catalog_data_port,
)
from aegis_data.continuous_contract_model import ContinuousContractModel
from aegis_data.continuous_future import DEFAULT_ADJUSTMENT_MODE
from aegis_data.distributions import Distribution
from aegis_runtime.currency import (
    CurrencyConversion,
    MissingInstrumentDefinitionError,
    build_currency_conversion,
)
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument

from research.aegis_research.configuration import DataConfig
from research.aegis_research.market_data.adapters._support import (
    index_evidence,
    native_from_array_dict,
    native_index,
)
from research.aegis_research.market_data.contracts import MarketDataAdapterResult
from research.aegis_research.market_data.identity import instrument_ids


class ContinuousRootCollisionError(Exception):
    """A synthetic continuous-root id collides with a requested raw instrument id."""


def load_catalog_source(
    config: DataConfig,
    *,
    port: CatalogBackedDataPort | None = None,
) -> MarketDataAdapterResult:
    # ADR-0006: research fills like live — a catalog miss backfills through the
    # port (unconditional, ungated); a warm read never connects. The concrete
    # provider is wired inside aegis-data's factory, so this module depends only on
    # the CatalogBackedDataPort abstraction (DIP).
    data_port = port if port is not None else catalog_data_port(config.path)
    start = _required_window_edge(config.start, "start")
    end = _required_window_edge(config.end, "end")
    raw_frames = data_port.load_raw_bars(
        RawBarRequest(
            instrument_ids=instrument_ids(config.native_instrument_ids),
            start=start,
            end=end,
            timeframe=config.timeframe,
        )
    )
    # Continuous-future roots are synthetic: aegis-data materialises each model as an
    # adjusted series on demand and hands it back as an OHLCV frame keyed by its root id.
    # The effective mode is resolved ONCE here and the same enum flows into every
    # materialisation and out as Run evidence — never a separately re-read constant.
    adjustment_mode: ContinuousFutureAdjustmentType | None = (
        DEFAULT_ADJUSTMENT_MODE if config.futures else None
    )
    continuous_frames = _continuous_frames(
        data_port,
        config.futures,
        start=start,
        end=end,
        timeframe=config.timeframe,
        adjustment_mode=adjustment_mode,
    )
    collisions = set(raw_frames) & set(continuous_frames)
    if collisions:
        raise ContinuousRootCollisionError(
            "continuous-future root ids collide with raw instrument ids: "
            f"{sorted(instrument_id.value for instrument_id in collisions)}"
        )
    frames = {**raw_frames, **continuous_frames}
    tradeable_instrument_ids = (*instrument_ids(config.instruments), *continuous_frames)
    native_data = native_from_array_dict(
        _array_panels(config, frames, tradeable_instrument_ids), config
    )
    # The exchange: FX legs rode in via native_instrument_ids and stay OUT of the
    # tradeable native_data above (no weights/signals/positions); here they become a
    # conversion view instead — native prices in the catalog, base prices per consumer.
    currency_conversion = _currency_conversion(config, data_port, raw_frames)
    distributions = _distribution_data(
        data_port,
        tradeable_instrument_ids,
        start=start,
        end=end,
    )
    provider_metadata: dict[str, object] = {"source": "nautilus_data_provider_port"}
    distribution_coverage = _distribution_coverage_report(
        data_port,
        tradeable_instrument_ids,
        start=start,
        end=end,
    )
    if distribution_coverage:
        provider_metadata["distribution_coverage"] = distribution_coverage
    return MarketDataAdapterResult(
        native_data=native_data,
        source_metadata={
            "catalog_path": config.path,
            "requested_instrument_ids": list(config.native_instrument_ids),
            "tradeable_instrument_ids": list(config.instruments),
            "exchange_instrument_ids": list(config.exchange),
            "continuous_root_ids": [root_id.value for root_id in continuous_frames],
        },
        evidence=index_evidence(native_index(native_data), source="nautilus_catalog"),
        provider_metadata=provider_metadata,
        currency_conversion=currency_conversion,
        adjustment_mode=adjustment_mode,
        distributions=distributions,
    )


def _distribution_data(
    data_port: CatalogBackedDataPort,
    instrument_ids: tuple[InstrumentId, ...],
    *,
    start: str,
    end: str,
) -> tuple[Distribution, ...]:
    # ADR-0008: RD receives distributions only through the verified catalog port.
    return data_port.distributions(instrument_ids, start=start, end=end)


def _distribution_coverage_report(
    data_port: CatalogBackedDataPort,
    instrument_ids: tuple[InstrumentId, ...],
    *,
    start: str,
    end: str,
) -> tuple[dict[str, object], ...]:
    return data_port.distribution_coverage_report(instrument_ids, start=start, end=end)


def _continuous_frames(
    data_port: CatalogBackedDataPort,
    roots: Sequence[str],
    *,
    start: str,
    end: str,
    timeframe: str,
    adjustment_mode: ContinuousFutureAdjustmentType | None,
) -> dict[InstrumentId, pd.DataFrame]:
    if roots and adjustment_mode is None:
        raise ValueError("continuous-future roots require an explicit adjustment mode")
    frames: dict[InstrumentId, pd.DataFrame] = {}
    for root in roots:
        model = ContinuousContractModel(
            data_port,
            root,
            start=start,
            timeframe=timeframe,
            adjustment_mode=adjustment_mode,
        )
        model.materialize(end=end)
        frames[model.continuous_id] = model.frame
    return frames


def _currency_conversion(
    config: DataConfig,
    data_port: CatalogBackedDataPort,
    raw_frames: dict[InstrumentId, pd.DataFrame],
) -> CurrencyConversion | None:
    """Build the non-base → base conversion from resolved instruments + exchange FX.

    Every tradeable leg's currency is read from its resolved catalog ``Instrument``
    (never configured) and matched to a declared ``exchange:`` FX pair. A non-base leg
    with no matching pair fails loud — whether the pair is simply absent or no
    ``exchange:`` was declared at all — so a multi-currency book can never run silently
    unconverted. An all-base book converts nothing (raw instruments only, no synthetic
    continuous-future roots, which carry no catalog definition and are out of scope).
    """
    tradeable_ids = instrument_ids(config.instruments)
    exchange_ids = instrument_ids(config.exchange)
    if not tradeable_ids and not exchange_ids:
        return None
    definitions = _resolve_definitions(data_port, (*tradeable_ids, *exchange_ids))
    return build_currency_conversion(
        instruments={instrument_id: definitions[instrument_id] for instrument_id in tradeable_ids},
        fx_pairs={instrument_id: definitions[instrument_id] for instrument_id in exchange_ids},
        fx_close={
            instrument_id: raw_frames[instrument_id]["Close"] for instrument_id in exchange_ids
        },
        base_currency=config.base_currency,
    )


def _resolve_definitions(
    data_port: CatalogBackedDataPort,
    requested: tuple[InstrumentId, ...],
) -> dict[InstrumentId, Instrument]:
    loaded = data_port.instruments(requested)
    missing = [instrument_id.value for instrument_id in requested if instrument_id not in loaded]
    if missing:
        raise MissingInstrumentDefinitionError(
            "currency conversion needs a catalog instrument definition for every tradeable "
            f"and exchange: id, but the catalog is missing definitions for: {sorted(missing)}"
        )
    return loaded


def _array_panels(
    config: DataConfig,
    frames: dict[InstrumentId, pd.DataFrame],
    instrument_ids: tuple[InstrumentId, ...],
) -> dict[str, pd.DataFrame]:
    # ``missing_index: drop`` promises calendar intersection (vbt's own drop semantics),
    # but the dict-of-Series constructor below union-joins first — on a mixed-calendar
    # book (LSE + Xetra/SIX legs) that would hand vbt a single pre-holed index with
    # nothing left to drop. Intersect here so the declared policy holds; any NaN that
    # survives intersection is a real data defect and still fails the quality gate.
    index = _panel_index(config, frames, instrument_ids)
    panels = {
        array: pd.DataFrame(
            {instrument_id: frames[instrument_id][array] for instrument_id in instrument_ids}
        )
        for array in config.effective_arrays
    }
    if index is None:
        return panels
    return {array: panel.loc[index] for array, panel in panels.items()}


def _panel_index(
    config: DataConfig,
    frames: dict[InstrumentId, pd.DataFrame],
    instrument_ids: tuple[InstrumentId, ...],
) -> pd.Index | None:
    if config.missing_index != "drop" or not instrument_ids:
        return None
    index: pd.Index | None = None
    for instrument_id in instrument_ids:
        leg = frames[instrument_id].index
        index = leg if index is None else index.intersection(leg)
    return index


def _required_window_edge(value: str | None, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} is required for catalog source")
    return value


__all__ = ["ContinuousRootCollisionError", "load_catalog_source"]
