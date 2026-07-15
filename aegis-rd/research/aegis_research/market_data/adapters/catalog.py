"""Nautilus catalog-backed RD market-data adapter."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
from aegis_data.catalog import (
    CatalogBackedDataPort,
    CatalogCoverageGapError,
    CatalogWindowRequest,
    GapFillProviderError,
    catalog_data_port,
)
from aegis_data.continuous_contract_model import ContinuousContractModel
from aegis_data.continuous_future import DEFAULT_ADJUSTMENT_MODE
from aegis_runtime.currency import (
    CurrencyConversion,
    build_currency_conversion_from_codes,
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
from research.aegis_research.market_data.contracts import (
    CONTINUOUS_ROOT_IDS_KEY,
    MarketDataLoad,
    MarketDataUnavailableError,
)
from research.aegis_research.market_data.identity import (
    declared_marking_resolver,
    instrument_ids,
)


class ContinuousRootCollisionError(Exception):
    """A synthetic continuous-root id collides with a requested raw instrument id."""


def load_catalog_source(
    config: DataConfig,
    *,
    port: CatalogBackedDataPort | None = None,
) -> MarketDataLoad:
    # ADR-0006: research fills like live — a catalog miss backfills through the
    # port (unconditional, ungated); a warm read never connects. The concrete
    # provider is wired inside aegis-data's factory, so this module depends only on
    # the CatalogBackedDataPort abstraction (DIP).
    #
    # This module is the only one that talks to the port, so it owns the
    # environmental-vs-authoring triage: the port's two environmental errors
    # (Data ADR-0011) become the RD unavailability error the orchestrator
    # collapses into failure Evidence; authoring errors (the port's missing-
    # definitions error, root collisions, missing window edges) keep propagating.
    data_port = (
        port
        if port is not None
        else catalog_data_port(config.path, resolver=declared_marking_resolver(config))
    )
    try:
        return _load_from_port(data_port, config)
    except (CatalogCoverageGapError, GapFillProviderError) as error:
        raise MarketDataUnavailableError(str(error)) from error


def _load_from_port(
    data_port: CatalogBackedDataPort, config: DataConfig
) -> MarketDataLoad:
    start = _required_window_edge(config.start, "start")
    end = _required_window_edge(config.end, "end")
    # Data ADR-0012: the whole native window — bars, complete definitions,
    # verified distributions, coverage report — is ONE coherent port read.
    window = data_port.load_window(
        CatalogWindowRequest(
            instrument_ids=instrument_ids(config.native_instrument_ids),
            start=start,
            end=end,
            timeframe=config.timeframe,
        )
    )
    raw_frames = window.ohlcv
    # Continuous-future roots are synthetic: aegis-data materialises each model as an
    # adjusted series on demand and hands it back as an OHLCV frame keyed by its root id.
    # The effective mode is resolved ONCE here and the same enum flows into every
    # materialisation and out as Run evidence — never a separately re-read constant.
    adjustment_mode: ContinuousFutureAdjustmentType | None = (
        DEFAULT_ADJUSTMENT_MODE if config.futures else None
    )
    continuous_frames, continuous_currencies = _continuous_frames(
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
    currency_conversion = _currency_conversion(
        config, window.instruments, raw_frames, continuous_currencies
    )
    size_increments = {
        **{
            instrument_id: window.size_increment_by_instrument[instrument_id]
            for instrument_id in instrument_ids(config.instruments)
        },
        **{
            continuous_id: data_port.continuous_size_increment(root)
            for root, continuous_id in zip(
                config.futures, continuous_frames, strict=True
            )
        },
    }
    port_metadata: dict[str, object] = {"source": "nautilus_data_provider_port"}
    # A synthetic root has no raw bars, so it can never enter the window
    # request — but its not-applicable coverage rows are real Run evidence,
    # read through the port's coverage-report diagnostic query.
    distribution_coverage = (
        *window.distribution_coverage,
        *(
            data_port.distribution_coverage_report(
                tuple(continuous_frames), start=start, end=end
            )
            if continuous_frames
            else ()
        ),
    )
    if distribution_coverage:
        port_metadata["distribution_coverage"] = distribution_coverage
    return MarketDataLoad(
        native_data=native_data,
        source_metadata={
            "catalog_path": config.path,
            "requested_instrument_ids": list(config.native_instrument_ids),
            "tradeable_instrument_ids": list(config.instruments),
            "exchange_instrument_ids": list(config.exchange),
            CONTINUOUS_ROOT_IDS_KEY: [root_id.value for root_id in continuous_frames],
            # Derived from each root's dated-leg definitions; rides the existing
            # data-identity projection into Candidate evidence.
            "continuous_root_currencies": {
                root_id.value: currency
                for root_id, currency in continuous_currencies.items()
            },
            "size_increment_by_instrument": {
                instrument_id.value: increment
                for instrument_id, increment in size_increments.items()
            },
        },
        evidence=index_evidence(native_index(native_data), source="nautilus_catalog"),
        port_metadata=port_metadata,
        currency_conversion=currency_conversion,
        adjustment_mode=adjustment_mode,
        distributions=window.distributions,
        size_increment_by_instrument=size_increments,
    )


def _continuous_frames(
    data_port: CatalogBackedDataPort,
    roots: Sequence[str],
    *,
    start: str,
    end: str,
    timeframe: str,
    adjustment_mode: ContinuousFutureAdjustmentType | None,
) -> tuple[
    dict[InstrumentId, pd.DataFrame],
    dict[InstrumentId, str],
]:
    """Materialise each root's adjusted frame plus its derived quote currency.

    The currency is the model's leg-derived fact — a synthetic root carries no
    catalog definition, so this is how it joins the base-currency conversion.
    """
    frames: dict[InstrumentId, pd.DataFrame] = {}
    currencies: dict[InstrumentId, str] = {}
    for root in roots:
        assert adjustment_mode is not None  # the caller selects a mode iff roots exist
        model = ContinuousContractModel(
            data_port,
            root,
            start=start,
            timeframe=timeframe,
            adjustment_mode=adjustment_mode,
        )
        model.materialize(end=end)
        frames[model.continuous_id] = model.frame
        currencies[model.continuous_id] = model.quote_currency
    return frames, currencies


def _currency_conversion(
    config: DataConfig,
    definitions: dict[InstrumentId, Instrument],
    raw_frames: dict[InstrumentId, pd.DataFrame],
    continuous_currencies: dict[InstrumentId, str],
) -> CurrencyConversion | None:
    """Build the non-base → base conversion from the window's instruments + exchange FX.

    Every tradeable leg's currency is read from its resolved catalog ``Instrument``
    (never configured) and matched to a declared ``exchange:`` FX pair. The window's
    completeness guarantee (Data ADR-0012) means every tradeable and ``exchange:`` id
    is present in *definitions* — a missing one already failed the window read with
    the port's authoring error. A synthetic continuous root joins through its
    leg-derived quote currency — no synthetic ``Instrument`` is minted — so a
    non-base continuous future converts exactly like a non-base native. Any non-base
    leg with no matching pair fails loud — whether the pair is simply absent or no
    ``exchange:`` was declared at all — so a multi-currency book can never run
    silently unconverted.
    """
    tradeable_ids = instrument_ids(config.instruments)
    exchange_ids = instrument_ids(config.exchange)
    if not tradeable_ids and not exchange_ids and not continuous_currencies:
        return None
    return build_currency_conversion_from_codes(
        currency_by_instrument_id={
            **{
                instrument_id: definitions[instrument_id].quote_currency.code
                for instrument_id in tradeable_ids
            },
            **continuous_currencies,
        },
        pair_currencies={
            pair_id: (
                definitions[pair_id].base_currency.code,
                definitions[pair_id].quote_currency.code,
            )
            for pair_id in exchange_ids
        },
        fx_close={
            instrument_id: raw_frames[instrument_id]["Close"] for instrument_id in exchange_ids
        },
        base_currency=config.base_currency,
    )


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
