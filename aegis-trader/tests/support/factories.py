"""Test factories for assembling in-memory Execution Bundles."""

from __future__ import annotations

from collections.abc import Mapping

from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    ExecutionBundle,
    LockedExecutionPlan,
    MissingIndexPolicy,
)

from aegis_trader.bundles.book import AssembledBook, assemble_book
from aegis_trader.bundles.stub import StubBundleRegistry
from aegis_trader.domain.book_config import BookConfig

_DEFAULT_INSTRUMENT_ID = InstrumentId.from_str("AAPL.NASDAQ")


def make_bundle(
    *,
    timeframe: str = "1D",
    required_arrays: tuple[str, ...] = ("Close",),
    native_instrument_ids: tuple[InstrumentId, ...] = (_DEFAULT_INSTRUMENT_ID,),
    exchange_instrument_ids: tuple[InstrumentId, ...] = (),
    continuous_futures: Mapping[str, InstrumentId] | None = None,
    adjustment_mode: ContinuousFutureAdjustmentType | None = None,
    instrument_bands: Mapping[InstrumentId, DriftBand] | None = None,
    lookback_bars: int = 20,
    direction: str = "both",
) -> ExecutionBundle:
    """Return a valid Execution Bundle with representative defaults."""
    continuous_futures = continuous_futures or {}
    continuous_items = tuple(sorted(continuous_futures.items()))
    continuous_instrument_ids = tuple(
        instrument_id for _root, instrument_id in continuous_items
    )
    instrument_ids = (*native_instrument_ids, *continuous_instrument_ids)
    if continuous_items and adjustment_mode is None:
        adjustment_mode = ContinuousFutureAdjustmentType.BACKWARD_RATIO
    resolved_bands = (
        dict(instrument_bands)
        if instrument_bands is not None
        else {
            instrument_id: DriftBand.symmetric(0.0)
            for instrument_id in instrument_ids
        }
    )
    contract = DataContract(
        instrument_ids=instrument_ids,
        required_arrays=required_arrays,
        base_currency="EUR",
        timeframe=timeframe,
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=lookback_bars,
        futures=tuple(root for root, _instrument_id in continuous_items),
        exchange=exchange_instrument_ids,
        adjustment_mode=adjustment_mode,
    )
    manifest = BundleManifest(
        run_id="test-run",
        role="best",
        candidate_key="test-candidate",
        component_source_hashes={},
        instrument_ids=instrument_ids,
    )
    plan = LockedExecutionPlan(
        strategy=ComponentSpec(
            family="strategy",
            component_id="test-strategy",
            module="tests.support.bundle_strategy",
            input_names=(),
            output_names=(),
            params={},
        ),
        indicators=(),
        instrument_bands=resolved_bands,
        gross_cap=1.0,
        net_cap=None,
        direction=direction,
    )
    return ExecutionBundle(contract=contract, manifest=manifest, plan=plan)


def assemble_test_book(
    book: BookConfig,
    bundles: Mapping[str, ExecutionBundle],
) -> AssembledBook:
    """Assemble a Book Config against in-memory bundles through its real interface."""
    return assemble_book(book, StubBundleRegistry(dict(bundles)))
