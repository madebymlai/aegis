"""Cross-Sleeve continuous-root declaration union (aegis-rd-tkj5.3).

A Commingled Book may combine separate valid DataContracts. Each futures root
must resolve to ONE coherent declaration — synthetic continuous id plus
adjustment mode — before Roll Desk materialises anything. Identical duplicate
declarations collapse; the same root disagreeing on id or mode is a named
conflict carrying the root, the source Sleeves, and both declarations.
"""

from __future__ import annotations

import pytest
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

from aegis_trader.bundles.book_sleeves import (
    ContinuousDeclarationConflictError,
    ContinuousRootDeclaration,
    union_continuous_declarations,
)
from aegis_trader.domain.types import SleeveName

_ES_XCME = InstrumentId.from_str("ES.XCME")
_ES_IFUS = InstrumentId.from_str("ES.IFUS")
_NQ_XCME = InstrumentId.from_str("NQ.XCME")
_AAPL = InstrumentId.from_str("AAPL.NASDAQ")

_RATIO = ContinuousFutureAdjustmentType.BACKWARD_RATIO
_SPREAD = ContinuousFutureAdjustmentType.BACKWARD_SPREAD


def _bundle(
    *,
    instrument_ids: tuple[InstrumentId, ...],
    futures: tuple[str, ...],
    adjustment_mode: ContinuousFutureAdjustmentType | None,
) -> ExecutionBundle:
    contract = DataContract(
        instrument_ids=instrument_ids,
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=1,
        futures=futures,
        adjustment_mode=adjustment_mode,
    )
    manifest = BundleManifest(
        run_id="book-sleeves-test",
        role="best",
        candidate_key="candidate",
        component_source_hashes={},
        instrument_ids=instrument_ids,
    )
    plan = LockedExecutionPlan(
        strategy=ComponentSpec(
            family="strategy",
            component_id="fixed",
            module="tests.fixed",
            input_names=(),
            output_names=(),
            params={},
        ),
        indicators=(),
        instrument_bands={
            instrument_id: DriftBand.symmetric(0.0) for instrument_id in instrument_ids
        },
        gross_cap=1.0,
        net_cap=None,
        direction="both",
    )
    return ExecutionBundle(contract=contract, manifest=manifest, plan=plan)


def test_identical_duplicate_declarations_collapse_to_one_entry() -> None:
    sleeves = (
        (SleeveName("trend"), _bundle(instrument_ids=(_ES_XCME,), futures=("ES",), adjustment_mode=_RATIO)),
        (SleeveName("carry"), _bundle(instrument_ids=(_ES_XCME, _AAPL), futures=("ES",), adjustment_mode=_RATIO)),
    )

    declarations = union_continuous_declarations(sleeves)

    assert declarations == {
        "ES": ContinuousRootDeclaration(continuous_id=_ES_XCME, adjustment_mode=_RATIO)
    }


def test_separate_contracts_may_use_different_modes_for_different_roots() -> None:
    sleeves = (
        (SleeveName("trend"), _bundle(instrument_ids=(_ES_XCME,), futures=("ES",), adjustment_mode=_RATIO)),
        (SleeveName("carry"), _bundle(instrument_ids=(_NQ_XCME,), futures=("NQ",), adjustment_mode=_SPREAD)),
    )

    declarations = union_continuous_declarations(sleeves)

    assert declarations["ES"].adjustment_mode is _RATIO
    assert declarations["NQ"].adjustment_mode is _SPREAD


def test_empty_futures_book_resolves_an_empty_mapping() -> None:
    sleeves = (
        (SleeveName("trend"), _bundle(instrument_ids=(_AAPL,), futures=(), adjustment_mode=None)),
    )

    assert union_continuous_declarations(sleeves) == {}


def test_same_root_with_a_different_continuous_id_conflicts() -> None:
    sleeves = (
        (SleeveName("trend"), _bundle(instrument_ids=(_ES_XCME,), futures=("ES",), adjustment_mode=_RATIO)),
        (SleeveName("carry"), _bundle(instrument_ids=(_ES_IFUS,), futures=("ES",), adjustment_mode=_RATIO)),
    )

    with pytest.raises(ContinuousDeclarationConflictError) as excinfo:
        union_continuous_declarations(sleeves)

    error = excinfo.value
    assert error.root == "ES"
    assert error.sleeves == (SleeveName("trend"), SleeveName("carry"))
    assert error.existing.continuous_id == _ES_XCME
    assert error.conflicting.continuous_id == _ES_IFUS
    message = str(error)
    assert "ES.XCME" in message
    assert "ES.IFUS" in message


def test_same_root_with_a_different_adjustment_mode_conflicts() -> None:
    sleeves = (
        (SleeveName("trend"), _bundle(instrument_ids=(_ES_XCME,), futures=("ES",), adjustment_mode=_RATIO)),
        (SleeveName("carry"), _bundle(instrument_ids=(_ES_XCME,), futures=("ES",), adjustment_mode=_SPREAD)),
    )

    with pytest.raises(ContinuousDeclarationConflictError) as excinfo:
        union_continuous_declarations(sleeves)

    error = excinfo.value
    assert error.root == "ES"
    assert error.sleeves == (SleeveName("trend"), SleeveName("carry"))
    assert error.existing.adjustment_mode is _RATIO
    assert error.conflicting.adjustment_mode is _SPREAD
    message = str(error)
    assert "backward_ratio" in message
    assert "backward_spread" in message
